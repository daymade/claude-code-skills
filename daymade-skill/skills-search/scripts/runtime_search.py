#!/usr/bin/env python3
"""Runtime cold-library Skill discovery (Agent-native catalog + exact search),
bounded on-demand loader, locked telemetry, and self-learning aliases.

Zero external dependencies (Python 3.9+ stdlib only) for fast (<50ms) runtime invocation
from CLI or MCP across Claude Code, Codex, and Antigravity.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata


DEFAULT_INSTALLED_ROOT = Path.home() / ".agents" / "skills"
DEFAULT_SOURCES_CONFIG = Path.home() / ".config" / "skills-search" / "sources.json"
DEFAULT_GOVERNANCE_DIR = Path.home() / ".config" / "skill-governance"
DEFAULT_TELEMETRY_PATH = Path.home() / ".local" / "share" / "skill-governance" / "telemetry.jsonl"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "skills-search" / "runtime-index.json"

DEFAULT_GET_MAX_CHARS = 16000
HARD_GET_MAX_CHARS = 32000
DEFAULT_BROWSE_MAX_ITEMS = 45
HARD_BROWSE_MAX_CHARS = 24000
MAX_TELEMETRY_QUERY_CHARS = 80
PRUNE_WALK_DIRS = {"__pycache__", "node_modules", ".venv", "venv", ".git", "dist", "build", ".pytest_cache"}

CATEGORY_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "finance-due-diligence",
        "金融投研、财报、企查查尽调、企业核验、A股/美股/港股/会计",
        ("qcc", "kyb", "kyc", "ic-memo", "financial", "finance", "stock", "equity", "credit", "esg",
         "accounting", "salary", "tax", "llc", "corp-finance", "fundraising", "analyst", "seeking-alpha",
         "longbridge", "ifind", "gangtise", "bigdata", "pharma", "due-diligence", "尽调", "企查查", "财报", "金融", "会计", "股权"),
    ),
    (
        "wechat-feishu-social",
        "微信、公众号、企微、飞书、小红书、抖音、B站、豆瓣、Twitter/X、收藏与消息同步",
        ("wechat", "wecom", "feishu", "lark", "douyin", "bilibili", "douban", "twitter", "xiaohongshu",
         "fav", "lenny", "weread", "newsletter", "微信", "公众号", "飞书", "企微", "抖音", "豆瓣", "收藏"),
    ),
    (
        "media-video-audio",
        "视频剪辑、剪映/CapCut、配音/TTS/ASR、字幕、音频、视频理解、图片/海报/画图/音乐",
        ("video", "audio", "tts", "asr", "subtitle", "capcut", "jianying", "dji", "youtube", "suno",
         "music", "image", "shader", "excalidraw", "mermaid", "design-style", "poster", "voice", "mic",
         "recording", "ezviz", "daudio", "剪辑", "视频", "配音", "字幕", "音频", "图片", "录音"),
    ),
    (
        "docs-writing-slides",
        "写作、文档、PPT/演示稿、PDF/DOCX/Excel、翻译、表单、HTML报告、研报/纪要",
        ("write", "writing", "writer", "docx", "pdf", "ppt", "pptx", "slide", "slides", "deck", "excel",
         "xlsx", "markdown", "report", "html", "translate", "zh-tw", "copy", "content", "minutes",
         "meeting", "fact-check", "book", "calibre", "wps", "写作", "文档", "报告", "纪要", "翻译"),
    ),
    (
        "browser-web-scrape",
        "浏览器自动化、登录态/Cookie、网页抓取/反爬、搜索、代理/网络排障",
        ("browser", "chrome", "ego", "cookie", "scrape", "scraper", "crawl", "webreach", "proxy",
         "tunnel", "network", "cloudflare", "domain", "spaceship", "dns", "curl", "monid",
         "抓取", "爬虫", "浏览器", "代理", "网络"),
    ),
    (
        "macos-infra-ops",
        "macOS 系统运维、CPU/电池/磁盘/打印/权限、NAS、阿里云、远程机器、VMware/WSL/Docker/安卓",
        ("macos", "ios", "android", "aliyun", "nas", "homelab", "remote", "wsl", "windows",
         "vmware", "lume", "docker", "disk", "battery", "load-doctor", "print", "watchdog",
         "hammerspoon", "ghostty", "terminal", "screenshot", "capture", "lazycat", "ssh", "infra",
         "系统", "磁盘", "电池", "进程", "服务器", "阿里云", "打印"),
    ),
    (
        "agent-skill-ops",
        "Claude Code/Codex/Kimi Agent 编排、Skill/Hook/MCP、对话历史、复盘、交接、模型管理",
        ("claude", "codex", "kimi", "agent", "skill", "skills", "hook", "hooks", "mcp", "harness",
         "gru", "dstack", "loopx", "prompt", "llm", "context", "history", "retrospective",
         "onboarding", "handover", "chatgpt", "openclaw", "workbuddy", "peer-message"),
    ),
    (
        "dev-code-git",
        "软件开发、Git/GitHub/PR、测试/评测/基准、Flutter/Kotlin/小程序/桌面应用发布",
        ("git", "github", "repo", "worktree", "flutter", "kotlin", "miniapp", "xcode", "benchmark",
         "eval", "testing", "debug", "refactor", "build", "release", "electron", "swiftui", "cli",
         "开发", "代码", "测试", "评测"),
    ),
]

# Precompile ASCII word-boundary matchers once (P2-1 fix: no bare substring collisions like 'test' in 'latest')
_COMPILED_CATEGORY_RULES: list[tuple[str, str, list[tuple[str, re.Pattern | None]]]] = []
for _cid, _lbl, _kws in CATEGORY_RULES:
    compiled_kws: list[tuple[str, re.Pattern | None]] = []
    for _kw in _kws:
        if re.fullmatch(r"[a-z0-9_-]+", _kw):
            compiled_kws.append((_kw, re.compile(rf"(?<![a-z0-9]){re.escape(_kw)}(?![a-z0-9])")))
        else:
            compiled_kws.append((_kw, None))
    _COMPILED_CATEGORY_RULES.append((_cid, _lbl, compiled_kws))

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "find", "for",
    "from", "help", "how", "i", "in", "is", "it", "me", "my", "need", "of", "on",
    "or", "please", "search", "skill", "skills", "that", "the", "this", "to", "tool",
    "tools", "use", "want", "with", "帮我", "一下", "一个", "什么", "怎么", "技能",
}

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
ASCII_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+-]*")
SENSITIVE_QUERY_RE = re.compile(r"(https?://\S+|/Users/\S+|sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+)", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def sanitize_telemetry_query(query: str | None) -> str:
    """Strip paths/URLs/tokens and cap length before persisting query text to telemetry."""
    if not query:
        return ""
    cleaned = " ".join(str(query).split())
    cleaned = SENSITIVE_QUERY_RE.sub("[redacted]", cleaned).strip()
    if len(cleaned) > MAX_TELEMETRY_QUERY_CHARS:
        cleaned = cleaned[: MAX_TELEMETRY_QUERY_CHARS - 1].rstrip() + "…"
    return cleaned


@contextmanager
def file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def atomic_json_write(path: Path, data: object) -> None:
    target = path.resolve() if path.is_symlink() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    orig_mode = None
    try:
        orig_mode = target.stat().st_mode & 0o777
    except OSError:
        orig_mode = 0o644
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, orig_mode)
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_json_safe(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def parse_frontmatter(raw: str) -> dict[str, str]:
    """Parse minimal YAML frontmatter (name, description) without external PyYAML."""
    text = raw.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end_idx = None
    for idx in range(1, min(len(lines), 200)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}
    fm_lines = lines[1:end_idx]
    result: dict[str, str] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        m = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in {">", ">-", "|", "|-", ">+", "|+"}:
            block: list[str] = []
            i += 1
            while i < len(fm_lines):
                nxt = fm_lines[i]
                if nxt.startswith((" ", "\t")):
                    block.append(nxt.strip())
                    i += 1
                elif nxt.strip() == "":
                    block.append("")
                    i += 1
                else:
                    break
            sep = "\n" if val.startswith("|") else " "
            result[key] = sep.join(part for part in block if part or sep == "\n").strip()
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            if val[0] == '"':
                try:
                    val = json.loads(val)
                except ValueError:
                    val = val[1:-1]
            else:
                val = val[1:-1].replace("''", "'")
        result[key] = val
        i += 1
    return result


def tokenize(text: str) -> list[str]:
    """Bilingual tokenizer: ASCII tokens + hyphen splits + CJK phrases and bigrams."""
    norm = normalize(text)
    tokens: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        tok = tok.strip()
        if not tok or tok in STOPWORDS or tok in seen:
            return
        seen.add(tok)
        tokens.append(tok)

    for m in ASCII_TOKEN_RE.finditer(norm):
        tok = m.group(0)
        if len(tok) >= 2:
            add(tok)
        if "-" in tok:
            for part in tok.split("-"):
                if len(part) >= 2:
                    add(part)

    for m in CJK_RE.finditer(norm):
        chunk = m.group(0)
        if len(chunk) >= 2:
            add(chunk)
        if len(chunk) > 2:
            for n in (2, 3):
                for start in range(0, len(chunk) - n + 1):
                    add(chunk[start : start + n])
        elif len(chunk) == 1:
            add(chunk)

    return tokens


def classify_skill(item: dict) -> str:
    """Deterministically group a skill into a compact domain category using word-boundary rules."""
    norm_name = normalize(f"{item['name']} {item['entry']}")
    norm_desc = normalize(item["description"])
    best_cat = "life-productivity-misc"
    best_hits = 0
    for cat_id, _label, kw_patterns in _COMPILED_CATEGORY_RULES:
        hits = 0
        for kw, pat in kw_patterns:
            if pat is not None:
                if pat.search(norm_name):
                    hits += 3
                elif pat.search(norm_desc):
                    hits += 1
            else:
                if kw in norm_name:
                    hits += 3
                elif kw in norm_desc:
                    hits += 1
        if hits > best_hits:
            best_hits = hits
            best_cat = cat_id
    return best_cat


def _compact_one_liner(item: dict, max_desc_chars: int = 96) -> str:
    desc = " ".join(item["description"].split())
    if len(desc) > max_desc_chars:
        desc = desc[: max_desc_chars - 1].rstrip() + "…"
    return f"- {item['name']}: {desc}"


def load_aliases(governance_dir: Path) -> dict[str, list[str]]:
    data = load_json_safe(governance_dir / "aliases.json")
    if not data:
        return {}
    raw = data.get("aliases", {})
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for skill, terms in raw.items():
        if isinstance(skill, str) and isinstance(terms, list):
            cleaned[skill] = [str(t).strip() for t in terms if isinstance(t, str) and t.strip()]
    return cleaned


def load_surface_sets(governance_dir: Path) -> tuple[set[str], set[str], set[str]]:
    """Return (hot_set, router_children, blocked_cold) from hot-set.json if present."""
    data = load_json_safe(governance_dir / "hot-set.json")
    if not data:
        return set(), set(), set()
    pinned = set(data.get("pinned", [])) if isinstance(data.get("pinned"), list) else set()
    dynamic = set(data.get("dynamic_hot", [])) if isinstance(data.get("dynamic_hot"), list) else set()
    children = set(data.get("router_children", [])) if isinstance(data.get("router_children"), list) else set()
    blocked = set(data.get("blocked_cold", [])) if isinstance(data.get("blocked_cold"), list) else set()
    return pinned | dynamic, children, blocked


def _scan_dir_skills(root: Path, origin: str) -> list[dict]:
    items: list[dict] = []
    if not root.is_dir():
        return items
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return items
    for entry in entries:
        if entry.startswith("."):
            continue
        skill_dir = root / entry
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            raw = skill_md.read_text(encoding="utf-8", errors="replace")
            st = skill_md.stat()
            real_md = skill_md.resolve()
        except OSError:
            continue
        fm = parse_frontmatter(raw)
        name = fm.get("name") or entry
        desc = fm.get("description") or ""
        if not desc:
            for line in raw.splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "---", "```")):
                    desc = s[:200]
                    break
        real_dir = real_md.parent
        items.append({
            "entry": entry,
            "name": name,
            "description": desc,
            "origin": origin,
            "skill_md_path": str(skill_md),
            "real_skill_md_path": str(real_md),
            "skill_dir": str(real_dir),
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
            "has_scripts": (real_dir / "scripts").is_dir(),
            "has_references": (real_dir / "references").is_dir(),
        })
    return items


def _extra_configured_skill_roots(sources_config: Path) -> list[tuple[str, Path]]:
    data = load_json_safe(sources_config)
    if not data or not isinstance(data.get("sources"), list):
        return []
    roots: list[tuple[str, Path]] = []
    for src in data["sources"]:
        if not isinstance(src, dict) or not src.get("enabled"):
            continue
        base = Path(str(src.get("path", "")))
        if not base.is_dir():
            continue
        src_id = str(src.get("id", base.name))
        if isinstance(src.get("skill_roots"), list):
            for rel in src["skill_roots"]:
                cand = base / str(rel)
                if cand.is_dir():
                    roots.append((f"repo:{src_id}", cand))
    return roots


def _compute_cache_sig(roots: list[tuple[str, Path]], sources_config: Path) -> str:
    """Fast (~3ms) stat fingerprint over sources_config + every SKILL.md (catches edits & deletes)."""
    h = hashlib.sha256()
    try:
        st_cfg = sources_config.stat()
        h.update(f"cfg:{st_cfg.st_mtime_ns}:{st_cfg.st_size}|".encode())
    except OSError:
        h.update(b"cfg:none|")
    for origin, r in roots:
        if not r.is_dir():
            h.update(f"{origin}:{r}:absent|".encode())
            continue
        try:
            entries = sorted(os.listdir(r))
        except OSError:
            h.update(f"{origin}:{r}:err|".encode())
            continue
        h.update(f"{origin}:{r}|".encode())
        for entry in entries:
            if entry.startswith("."):
                continue
            md = r / entry / "SKILL.md"
            try:
                st = md.stat()
                h.update(f"{origin}/{entry}:{st.st_mtime_ns}:{st.st_size}|".encode())
            except OSError:
                continue
    return h.hexdigest()


def build_index(
    installed_root: Path = DEFAULT_INSTALLED_ROOT,
    sources_config: Path = DEFAULT_SOURCES_CONFIG,
    project_root: Path | None = None,
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    force_refresh: bool = False,
) -> list[dict]:
    roots: list[tuple[str, Path]] = [("installed", installed_root)]
    roots.extend(_extra_configured_skill_roots(sources_config))
    if project_root is not None:
        proj = project_root.expanduser().resolve()
        for rel in (".agents/skills", ".claude/skills"):
            cand = proj / rel
            if cand.is_dir():
                roots.append((f"project:{rel}", cand))

    cache_sig = _compute_cache_sig(roots, sources_config) if (cache_path and project_root is None) else None

    if not force_refresh and cache_sig and cache_path and cache_path.is_file():
        cached = load_json_safe(cache_path)
        if cached and cached.get("schema") == 2 and cached.get("sig") == cache_sig and isinstance(cached.get("items"), list):
            return cached["items"]

    by_real: dict[str, dict] = {}
    items: list[dict] = []
    for origin, r in roots:
        for item in _scan_dir_skills(r, origin):
            real_key = item["real_skill_md_path"]
            if real_key in by_real:
                continue
            by_real[real_key] = item
            items.append(item)

    if cache_sig and cache_path:
        try:
            atomic_json_write(cache_path, {"schema": 2, "sig": cache_sig, "items": items})
        except OSError:
            pass
    return items


def append_telemetry(telemetry_path: Path | None, record: dict) -> None:
    """Append one JSONL line under shared sidecar lock (matches prune_telemetry_file lock protocol)."""
    if telemetry_path is None:
        return
    try:
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = telemetry_path.with_name(telemetry_path.name + ".lock")
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with file_lock(lock_path):
            # Open AFTER acquiring lock so any concurrent atomic os.replace() is visible
            with open(telemetry_path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
    except OSError:
        pass


def valid_category_ids() -> list[str]:
    return [cid for cid, _, _ in CATEGORY_RULES] + ["life-productivity-misc"]


def list_skill_categories(
    installed_root: Path = DEFAULT_INSTALLED_ROOT,
    sources_config: Path = DEFAULT_SOURCES_CONFIG,
    governance_dir: Path = DEFAULT_GOVERNANCE_DIR,
    project_root: Path | None = None,
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    include_hot: bool = False,
) -> dict:
    """List compact domain categories of cold (or all) skills (~220 tokens as text).
    Does NOT write to watched telemetry.jsonl so it never eats WatchPaths cooldown before `load`.
    """
    items = build_index(installed_root, sources_config, project_root, cache_path)
    hot_set, router_children, blocked_cold = load_surface_sets(governance_dir)
    labels = {cid: lbl for cid, lbl, _ in CATEGORY_RULES}
    labels["life-productivity-misc"] = "日常效率、待办、旅行、房产、个人知识库及其他单点工具"

    grouped: dict[str, list[dict]] = {}
    for it in items:
        if it["entry"] in blocked_cold or it["name"] in blocked_cold:
            continue
        if it["entry"] in router_children or it["name"] in router_children:
            continue
        is_hot = it["entry"] in hot_set or it["name"] in hot_set
        if not include_hot and is_hot:
            continue
        cat = classify_skill(it)
        grouped.setdefault(cat, []).append(it)

    categories = []
    for cat_id, members in sorted(grouped.items(), key=lambda x: (-len(x[1]), x[0])):
        categories.append({
            "category": cat_id,
            "label": labels.get(cat_id, cat_id),
            "count": len(members),
        })

    return {
        "schema": 2,
        "scope": "all" if include_hot else "cold_only",
        "total_skills": sum(c["count"] for c in categories),
        "categories": categories,
    }


def format_categories_compact(res: dict) -> str:
    lines = [f"Cold local skills ({res['total_skills']} total, scope={res['scope']}):"]
    for c in res["categories"]:
        lines.append(f"- `{c['category']}` ({c['count']}): {c['label']}")
    return "\n".join(lines)


def browse_skill_category(
    category: str,
    installed_root: Path = DEFAULT_INSTALLED_ROOT,
    sources_config: Path = DEFAULT_SOURCES_CONFIG,
    governance_dir: Path = DEFAULT_GOVERNANCE_DIR,
    project_root: Path | None = None,
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    include_hot: bool = False,
    max_items: int = DEFAULT_BROWSE_MAX_ITEMS,
    offset: int = 0,
    confirm_full_scan: bool = False,
) -> dict:
    """Return compact 1-line-per-skill summaries for one category (or 'all' with explicit confirm_full_scan)."""
    target_cat = category.strip().lower()
    allowed = set(valid_category_ids())
    if not target_cat or (target_cat != "all" and target_cat not in allowed):
        raise ValueError(f"Unknown category '{category}'. Valid categories: {sorted(allowed)} (or 'all')")
    if target_cat == "all" and not confirm_full_scan:
        raise ValueError(
            "category='all' dumps ~260 skills (~10K tokens). Call list_skill_categories() and browse one specific "
            "category instead, OR pass confirm_full_scan=true from an isolated subagent."
        )

    items = build_index(installed_root, sources_config, project_root, cache_path)
    hot_set, router_children, blocked_cold = load_surface_sets(governance_dir)

    selected: list[dict] = []
    for it in items:
        if it["entry"] in blocked_cold or it["name"] in blocked_cold:
            continue
        if it["entry"] in router_children or it["name"] in router_children:
            continue
        is_hot = it["entry"] in hot_set or it["name"] in hot_set
        if not include_hot and is_hot:
            continue
        cat = classify_skill(it)
        if target_cat == "all" or cat == target_cat:
            selected.append({**it, "_category": cat})

    selected.sort(key=lambda x: (x["_category"], x["name"]))
    total_in_cat = len(selected)
    start = max(0, int(offset))
    cap_items = total_in_cat if target_cat == "all" else max(1, min(int(max_items), 100))
    page = selected[start : start + cap_items]

    blocks: list[str] = []
    char_count = 0
    truncated = (start + len(page)) < total_in_cat
    emitted = 0
    cur_cat = None

    for it in page:
        line = _compact_one_liner(it, max_desc_chars=84 if target_cat == "all" else 108)
        prefix = ""
        if target_cat == "all" and it["_category"] != cur_cat:
            cur_cat = it["_category"]
            prefix = f"\n## {cur_cat}\n"
        addition = prefix + line
        if char_count + len(addition) > HARD_BROWSE_MAX_CHARS and emitted > 0:
            truncated = True
            break
        blocks.append(addition)
        char_count += len(addition) + 1
        emitted += 1

    catalog_md = "\n".join(blocks).strip()
    next_offset = (start + emitted) if truncated else None

    return {
        "schema": 2,
        "category": target_cat,
        "total": total_in_cat,
        "offset": start,
        "count": emitted,
        "truncated": truncated,
        "next_offset": next_offset,
        "catalog": catalog_md,
    }


def search_skills(
    query: str,
    terms: list[str] | None = None,
    limit: int = 8,
    installed_root: Path = DEFAULT_INSTALLED_ROOT,
    sources_config: Path = DEFAULT_SOURCES_CONFIG,
    governance_dir: Path = DEFAULT_GOVERNANCE_DIR,
    project_root: Path | None = None,
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    telemetry_path: Path | None = DEFAULT_TELEMETRY_PATH,
    host: str = "unknown",
    cold_only: bool = False,
    include_blocked: bool = False,
) -> dict:
    if not str(query or "").strip() and not terms:
        raise ValueError("Provide a non-empty capability query or --term")

    items = build_index(installed_root, sources_config, project_root, cache_path)
    aliases = load_aliases(governance_dir)
    hot_set, router_children, blocked_cold = load_surface_sets(governance_dir)

    raw_terms = list(terms) if terms else []
    query_tokens = tokenize(query)
    for t in raw_terms:
        for tok in tokenize(t):
            if tok not in query_tokens:
                query_tokens.append(tok)
        nt = normalize(t).strip()
        if nt and nt not in query_tokens:
            query_tokens.append(nt)

    # P1-3 fix: fallback to raw normalized tokens (supports 1-char names like "X", "C", or stopword-only input)
    if not query_tokens:
        query_tokens = [tok for tok in re.findall(r"[^\s]+", normalize(query)) if tok]
    if not query_tokens:
        raise ValueError("Provide a non-empty capability query or --term")

    norm_query = normalize(query).strip()
    matches: list[dict] = []

    for item in items:
        entry_name = item["entry"]
        skill_name = item["name"]
        if not include_blocked and (entry_name in blocked_cold or skill_name in blocked_cold):
            continue
        if entry_name in hot_set or skill_name in hot_set:
            surface = "hot"
        elif entry_name in router_children or skill_name in router_children:
            surface = "router-child"
        else:
            surface = "cold"
        if cold_only and surface == "hot":
            continue

        norm_name = normalize(skill_name)
        norm_entry = normalize(entry_name)
        norm_desc = normalize(item["description"])
        skill_aliases = [normalize(a) for a in aliases.get(skill_name, []) + aliases.get(entry_name, [])]
        alias_blob = " ".join(skill_aliases)

        score = 0
        matched: list[str] = []

        if norm_query in {norm_name, norm_entry} or norm_query in skill_aliases:
            score += 20
            matched.append(norm_query)

        for tok in query_tokens:
            hit = False
            if tok == norm_name or tok == norm_entry:
                score += 12
                hit = True
            elif len(tok) >= 2 and (tok in norm_name or tok in norm_entry):
                score += 6
                hit = True
            if alias_blob and (
                (len(tok) >= 2 and tok in alias_blob)
                or (len(tok) == 1 and re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", alias_blob))
            ):
                score += 7
                hit = True
            if len(tok) >= 2 and tok in norm_desc:
                score += 3 if len(tok) >= 3 else 2
                hit = True
            elif len(tok) == 1 and re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", norm_desc):
                score += 2
                hit = True
            if hit:
                matched.append(tok)

        if score > 0:
            router_bonus = 1 if "router" in norm_name else 0
            short_desc = " ".join(item["description"].split())
            if len(short_desc) > 160:
                short_desc = short_desc[:159].rstrip() + "…"
            matches.append({
                "name": skill_name,
                "entry": entry_name,
                "description": short_desc,
                "surface": surface,
                "origin": item["origin"],
                "skill_md_path": item["skill_md_path"],
                "real_skill_md_path": item["real_skill_md_path"],
                "has_scripts": item["has_scripts"],
                "has_references": item["has_references"],
                "score": score + router_bonus,
                "matched_terms": sorted(set(matched)),
            })

    matches.sort(key=lambda m: (-m["score"], m["surface"] == "router-child", m["name"]))
    top = matches[:limit]

    append_telemetry(telemetry_path, {
        "ts": utc_now_iso(),
        "host": host,
        "event": "search",
        "query": sanitize_telemetry_query(query),
        "terms": query_tokens[:10],
        "matched_count": len(matches),
        "top_matches": [m["name"] for m in top[:5]],
        "zero_hit": len(matches) == 0,
    })

    return {
        "schema": 2,
        "query": query,
        "indexed_count": len(items),
        "matched_count": len(matches),
        "candidates": top,
    }


def _list_rel_pruned(real_dir: Path, sub: str, max_files: int = 40) -> list[str]:
    """Pruned os.walk avoiding node_modules/.venv/__pycache__ and stopping early."""
    root = real_dir / sub
    if not root.is_dir():
        return []
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_WALK_DIRS and not d.startswith("."))
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            rel = str(Path(dirpath, fname).relative_to(real_dir))
            found.append(rel)
            if len(found) >= max_files:
                return found
    return found


def _extract_headings(content: str, limit: int = 25) -> list[str]:
    headings: list[str] = []
    in_code = False
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if not in_code and re.match(r"^#{1,3}\s+\S", s):
            headings.append(s[:100])
            if len(headings) >= limit:
                break
    return headings


def get_skill(
    name: str,
    installed_root: Path = DEFAULT_INSTALLED_ROOT,
    sources_config: Path = DEFAULT_SOURCES_CONFIG,
    governance_dir: Path = DEFAULT_GOVERNANCE_DIR,
    project_root: Path | None = None,
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    telemetry_path: Path | None = DEFAULT_TELEMETRY_PATH,
    host: str = "unknown",
    query: str | None = None,
    max_chars: int = DEFAULT_GET_MAX_CHARS,
    offset: int = 0,
) -> dict:
    target = normalize(name).strip()
    if not target:
        raise ValueError("Skill name is required")

    found = None
    content = ""
    for attempt in (0, 1):
        items = build_index(
            installed_root, sources_config, project_root, cache_path, force_refresh=(attempt == 1)
        )
        found = next(
            (it for it in items if normalize(it["name"]) == target or normalize(it["entry"]) == target),
            None,
        )
        if found is None:
            if attempt == 0:
                continue
            raise FileNotFoundError(f"Skill not found in local index: {name}")
        real_md = Path(found["real_skill_md_path"])
        try:
            content = real_md.read_text(encoding="utf-8", errors="replace")
            break
        except FileNotFoundError:
            if attempt == 0:
                continue
            raise

    assert found is not None
    hot_set, router_children, _ = load_surface_sets(governance_dir)
    real_md = Path(found["real_skill_md_path"])
    real_dir = real_md.parent

    # P0-3 fix: enforce bounded max_chars with clean pagination & TOC
    cap = max(1000, min(int(max_chars), HARD_GET_MAX_CHARS))
    start = max(0, int(offset))
    total_chars = len(content)
    slice_end = min(total_chars, start + cap)
    chunk = content[start:slice_end]
    truncated = slice_end < total_chars
    next_offset = slice_end if truncated else None

    surface = (
        "hot" if (found["entry"] in hot_set or found["name"] in hot_set)
        else "router-child" if (found["entry"] in router_children or found["name"] in router_children)
        else "cold"
    )

    # P1-3 fix: only emit load telemetry on initial page (offset == 0) so pagination never multiplies counts
    if start == 0:
        append_telemetry(telemetry_path, {
            "ts": utc_now_iso(),
            "host": host,
            "event": "load",
            "skill": found["name"],
            "entry": found["entry"],
            "surface": surface,
            "query": sanitize_telemetry_query(query),
        })

    return {
        "schema": 2,
        "name": found["name"],
        "entry": found["entry"],
        "surface": surface,
        "skill_md_path": found["skill_md_path"],
        "real_skill_md_path": found["real_skill_md_path"],
        "skill_dir": found["skill_dir"],
        "scripts": _list_rel_pruned(real_dir, "scripts"),
        "references": _list_rel_pruned(real_dir, "references"),
        "total_chars": total_chars,
        "offset": start,
        "truncated": truncated,
        "next_offset": next_offset,
        "toc_headings": _extract_headings(content) if truncated else [],
        "content": chunk,
    }


def format_skill_compact(res: dict) -> str:
    """Format get_local_skill for MCP without JSON-escaping Markdown body (saves tokens)."""
    header = [
        f"skill: {res['name']} (surface={res['surface']})",
        f"skill_dir: {res['skill_dir']}",
        f"skill_md_path: {res['real_skill_md_path']}",
    ]
    if res["scripts"]:
        header.append(f"scripts: {', '.join(res['scripts'][:15])}" + (" …" if len(res["scripts"]) > 15 else ""))
    if res["references"]:
        header.append(f"references: {', '.join(res['references'][:15])}" + (" …" if len(res["references"]) > 15 else ""))
    if res["truncated"]:
        header.append(
            f"truncated: true (showing chars {res['offset']}..{res['offset'] + len(res['content'])} of {res['total_chars']}; "
            f"call get_local_skill(name='{res['name']}', offset={res['next_offset']}) or read_file on skill_md_path)"
        )
        if res["toc_headings"]:
            header.append("toc: " + " | ".join(res["toc_headings"][:12]))
    return "\n".join(header) + "\n\n---\n\n" + res["content"]


def add_alias(skill: str, term: str, governance_dir: Path = DEFAULT_GOVERNANCE_DIR) -> dict:
    path = governance_dir / "aliases.json"
    with file_lock(governance_dir / ".aliases.lock"):
        data = load_json_safe(path) or {"schema": 1, "aliases": {}}
        aliases = data.setdefault("aliases", {})
        current = list(aliases.get(skill, []))
        cleaned = sanitize_telemetry_query(term)
        if cleaned and cleaned not in current:
            current.append(cleaned)
        aliases[skill] = current
        data["updated_at"] = utc_now_iso()
        atomic_json_write(path, data)
    return {"status": "ok", "skill": skill, "aliases": current, "path": str(path)}


def telemetry_stats(telemetry_path: Path = DEFAULT_TELEMETRY_PATH) -> dict:
    if not telemetry_path.is_file():
        return {"exists": False, "searches": 0, "loads": 0, "zero_hits": 0, "top_cold_loads": [], "recent_zero_hits": []}
    searches = loads = zero_hits = 0
    cold_loads: dict[str, int] = {}
    zero_queries: list[str] = []
    with open(telemetry_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ev = rec.get("event")
            if ev == "search":
                searches += 1
                if rec.get("zero_hit"):
                    zero_hits += 1
                    q = str(rec.get("query", "")).strip()
                    if q:
                        zero_queries.append(q)
            elif ev == "load":
                loads += 1
                if rec.get("surface") != "hot":
                    sk = str(rec.get("skill", ""))
                    if sk:
                        cold_loads[sk] = cold_loads.get(sk, 0) + 1
    top_cold = sorted(cold_loads.items(), key=lambda x: (-x[1], x[0]))[:15]
    return {
        "exists": True,
        "path": str(telemetry_path),
        "searches": searches,
        "loads": loads,
        "zero_hits": zero_hits,
        "top_cold_loads": [{"skill": k, "count": v} for k, v in top_cold],
        "recent_zero_hits": zero_queries[-15:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-root", type=Path, default=DEFAULT_INSTALLED_ROOT)
    parser.add_argument("--sources-config", type=Path, default=DEFAULT_SOURCES_CONFIG)
    parser.add_argument("--governance-dir", type=Path, default=DEFAULT_GOVERNANCE_DIR)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--no-telemetry", action="store_true")
    parser.add_argument("--host", default=os.environ.get("SKILL_SEARCH_HOST", "unknown"))

    sub = parser.add_subparsers(dest="command", required=True)

    p_cats = sub.add_parser("categories", help="List compact domain categories of cold Skills")
    p_cats.add_argument("--project", type=Path)
    p_cats.add_argument("--include-hot", action="store_true")
    p_cats.add_argument("--raw", action="store_true")

    p_browse = sub.add_parser("browse", help="Print compact 1-line summaries for one category (or 'all')")
    p_browse.add_argument("category")
    p_browse.add_argument("--project", type=Path)
    p_browse.add_argument("--include-hot", action="store_true")
    p_browse.add_argument("--max-items", type=int, default=DEFAULT_BROWSE_MAX_ITEMS)
    p_browse.add_argument("--offset", type=int, default=0)
    p_browse.add_argument("--confirm-full-scan", action="store_true")
    p_browse.add_argument("--raw", action="store_true")

    p_search = sub.add_parser("search", help="Exact-keyword/alias search across installed/local Skills")
    p_search.add_argument("query")
    p_search.add_argument("--term", action="append")
    p_search.add_argument("--limit", type=int, default=8)
    p_search.add_argument("--project", type=Path)
    p_search.add_argument("--cold-only", action="store_true")
    p_search.add_argument("--include-blocked", action="store_true")

    p_get = sub.add_parser("get", help="Read bounded SKILL.md + scripts/references for a Skill")
    p_get.add_argument("name")
    p_get.add_argument("--query")
    p_get.add_argument("--project", type=Path)
    p_get.add_argument("--max-chars", type=int, default=DEFAULT_GET_MAX_CHARS)
    p_get.add_argument("--offset", type=int, default=0)
    p_get.add_argument("--raw", action="store_true")

    p_alias = sub.add_parser("alias-add", help="Persist a learned search alias for a Skill")
    p_alias.add_argument("--skill", required=True)
    p_alias.add_argument("--term", required=True)

    sub.add_parser("stats", help="Summarize search/load telemetry")

    args = parser.parse_args(argv)
    telem = None if args.no_telemetry else args.telemetry

    try:
        if args.command == "categories":
            res = list_skill_categories(
                installed_root=args.installed_root,
                sources_config=args.sources_config,
                governance_dir=args.governance_dir,
                project_root=args.project,
                cache_path=args.cache,
                include_hot=args.include_hot,
            )
            print(format_categories_compact(res) if args.raw else json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        if args.command == "browse":
            res = browse_skill_category(
                category=args.category,
                installed_root=args.installed_root,
                sources_config=args.sources_config,
                governance_dir=args.governance_dir,
                project_root=args.project,
                cache_path=args.cache,
                include_hot=args.include_hot,
                max_items=args.max_items,
                offset=args.offset,
                confirm_full_scan=args.confirm_full_scan,
            )
            if args.raw:
                # P1-6 fix: never silently truncate --raw output; emit pagination header when truncated
                if res["truncated"]:
                    print(
                        f"[{res['category']}: showing {res['count']}/{res['total']} (offset={res['offset']}, "
                        f"next_offset={res['next_offset']}; pass --offset {res['next_offset']} for more)]"
                    )
                print(res["catalog"])
            else:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        if args.command == "search":
            res = search_skills(
                query=args.query,
                terms=args.term,
                limit=max(1, min(args.limit, 50)),
                installed_root=args.installed_root,
                sources_config=args.sources_config,
                governance_dir=args.governance_dir,
                project_root=args.project,
                cache_path=args.cache,
                telemetry_path=telem,
                host=args.host,
                cold_only=args.cold_only,
                include_blocked=args.include_blocked,
            )
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        if args.command == "get":
            res = get_skill(
                name=args.name,
                installed_root=args.installed_root,
                sources_config=args.sources_config,
                governance_dir=args.governance_dir,
                project_root=args.project,
                cache_path=args.cache,
                telemetry_path=telem,
                host=args.host,
                query=args.query,
                max_chars=args.max_chars,
                offset=args.offset,
            )
            print(format_skill_compact(res) if args.raw else json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        if args.command == "alias-add":
            res = add_alias(args.skill, args.term, args.governance_dir)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        res = telemetry_stats(args.telemetry)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

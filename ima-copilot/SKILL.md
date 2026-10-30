---
name: ima-copilot
description: >-
  Installs, diagnoses, repairs, and personalizes the official Tencent IMA skill (a wrapper around
  upstream ima-skill, not a replacement), including fan-out search across IMA knowledge bases with
  priority boosting. Use when the user mentions IMA / 腾讯 IMA / ima-skill, needs IMA API key setup,
  知识库搜索 / 笔记搜索, imports URLs into a KB to extract content, or hits "Skipped loading skill(s) due to invalid SKILL.md" (ima-skill's
  missing-YAML-frontmatter bug).
---

# IMA Copilot

One-command installer, troubleshooter, and personalization layer for the official Tencent IMA skill.

## Architectural principles (do not violate)

This skill is a **wrapper layer** around ima-skill. The wrapper contract is non-negotiable:

- **Never vendor upstream files.** This skill directory does not contain any copy, fork, or excerpt of ima-skill's own content. When ima-skill ships a new release, users get the new release without any interference from this wrapper.
- **Repairs happen at runtime, not at ship time.** If an upstream bug needs patching, this skill carries the *instructions* for how to patch, not the patched files. Running a repair is idempotent: rerunning after an upstream update re-detects and re-fixes anything that came back.
- **Always ask before touching upstream files.** Modifying `~/.claude/skills/ima-skill/**`, `~/.agents/skills/ima-skill/**`, or any other upstream install directory requires explicit user consent via AskUserQuestion. No silent patching.
- **Teach rather than hide.** When a fix is applied, show the user exactly what changed and where the backup was saved. This is how users learn to maintain their own installs.

## What this skill does

| Capability | Entry point | Detail |
|---|---|---|
| 1. Install upstream ima-skill to supported agents | `scripts/install_ima_skill.sh` | See `references/installation_flow.md` |
| 2. Configure API credentials (XDG style) | Inline workflow below | See `references/api_key_setup.md` |
| 3. Diagnose and fix known upstream issues | `scripts/diagnose.sh` + workflow below | See `references/known_issues.md` |
| 4. Fan-out search with priority boosting | `scripts/search_fanout.py` | See `references/search_best_practices.md` |
| 5. Import URLs and extract page content as structured text | OpenAPI `import_urls` + notes API | See `references/import_and_extract.md` |

## Routing

When this skill is triggered, classify the user's intent and jump to the corresponding capability:

| User says something like… | Go to |
|---|---|
| "装 ima"、"install ima-skill"、"把 ima 装一下"、"我想用 ima" | **Capability 1** |
| "配 ima 的 key"、"configure ima credentials"、"ima API key" | **Capability 2** |
| "ima 报错"、"SKILL.md warning"、"frontmatter 错误"、"ima 加载失败" | **Capability 3** |
| "搜 X"、"在 ima 里搜 X"、"跨知识库搜索"、"扇出搜 X" | **Capability 4** |
| "把这批链接导进 ima 并整理成结构化内容"、"import URLs into a knowledge base"、"让 ima 读这些页面" | **Capability 5** |
| "帮我从头跑一遍 ima" | 1 → 2 → 3 → 4 in sequence |

When in doubt, start with Capability 3 (diagnose) — it surfaces exactly which capabilities are blocked and in what order.

## Capability 1: Install upstream ima-skill

The installer downloads the latest official release from `https://app-dl.ima.qq.com/skills/`, stages it in a temp directory, and hands off to `npx skills add <local-path>` to distribute it across Claude Code, Codex, and OpenClaw.

To run it:

```bash
bash scripts/install_ima_skill.sh
```

The script auto-detects which target agents are installed on the user's machine. For agents that are not present, it skips silently rather than installing anywhere the user hasn't opted in. For agents that are present, it installs globally (`-g`) in vercel skills' default symlink mode: the first detected agent's directory becomes the canonical copy, and the remaining agents are symlinked to it. This means a repair or an upgrade applied once propagates automatically to every agent — `diagnose.sh` detects this sharing and dedupes its reports so you don't see the same issue multiple times.

For a version override, detection logic, troubleshooting, and the full file-by-file layout produced by the installer, read `references/installation_flow.md`.

## Capability 2: Configure API credentials

Credentials are stored in XDG style, decoupled from any agent's skill directory:

- `~/.config/ima/client_id` (mode `600`)
- `~/.config/ima/api_key` (mode `600`)
- `~/.config/ima/` (mode `700`)

Environment variables `IMA_OPENAPI_CLIENTID` and `IMA_OPENAPI_APIKEY` take precedence; missing values fall back to the config files.

Step through the setup with the user:

1. Open `https://ima.qq.com/agent-interface` and create a new Client ID and API Key.
2. Write both values into the XDG config path (or export the environment variables).
3. Make a single liveness call against `https://ima.qq.com/openapi/wiki/v1/search_knowledge_base` with `{"query": "", "cursor": "", "limit": 1}` to confirm the credentials are accepted — a `code: 0, msg: success` response means ready.

The full script and the exact request/response schema lives in `references/api_key_setup.md`.

## Capability 3: Diagnose and fix known issues

This is the reason this skill exists. The upstream package has real bugs that break loading on certain agents, and the fixes are well-understood but need user consent to apply. The diagnose/repair workflow is the **core contract** of this skill.

### Step 1 — Run the read-only diagnosis

```bash
bash scripts/diagnose.sh
```

`diagnose.sh` **never modifies any file**. It prints a structured report with one line per check:

```
✅ upstream ima-skill installed (claude-code)
✅ upstream ima-skill installed (codex)
❌ upstream ima-skill NOT installed (openclaw)
✅ API credentials valid (search_knowledge_base returned <count> KBs)
⚠️ ISSUE-001: notes/SKILL.md missing YAML frontmatter (claude-code)
⚠️ ISSUE-001: knowledge-base/SKILL.md missing YAML frontmatter (claude-code)
⚠️ ISSUE-001: notes/SKILL.md missing YAML frontmatter (codex)
⚠️ ISSUE-001: knowledge-base/SKILL.md missing YAML frontmatter (codex)
```

### Step 2 — Parse the report and ask the user

For each `⚠️` or `❌` line, look up the issue in `references/known_issues.md`. That file is the source of truth for:

- What the issue is (symptom, root cause)
- Which repair strategies exist (`A`, `B`, `skip`)
- The exact shell commands for each strategy
- What files each strategy touches
- Why the upstream maintainer probably hasn't fixed it yet

### Step 3 — Ask for explicit consent before touching upstream files

Use **AskUserQuestion** for every issue that has more than one repair strategy. Frame it plainly — the user may not know what "YAML frontmatter" means. Describe what the bug does to them in user terms ("loader skips two files silently, so note-search and knowledge-base-search don't actually work"), then describe each strategy in terms of the outcome, not the mechanism.

Never offer a single "just fix it" option when multiple strategies exist. The user's pick may legitimately differ based on factors the skill cannot observe — e.g., they might prefer Strategy B (minimal diff) if they plan to manually compare with upstream.

### Step 4 — Execute the chosen strategy

Every repair command in `references/known_issues.md` is written to be:

- **Idempotent** — rerunning after the fix is already applied does nothing harmful and prints a clear "already fixed" message.
- **Backed up** — the repair copies the original file to `/tmp/ima-copilot-backups/<timestamp>/<relative-path>` before modifying anything, then tells the user the backup location.
- **Reversible** — the user can restore from the backup with a single `cp` command shown at the end.

### Step 5 — Re-run diagnose to confirm

After the repair, run `diagnose.sh` a second time and show the user the diff. The issue should flip from `⚠️` to `✅`. If it does not, stop and surface the raw before/after to the user instead of silently retrying — unexpected failures here usually mean upstream shipped an unforeseen change.

### An important note about upstream updates

Upgrading ima-skill can replace local repairs. After an upgrade, rerun `diagnose.sh` and follow the existing repair workflow only for issues that return. If upstream has fixed the issue, diagnosis reports it healthy and no repair is needed.

## Capability 4: Personalized fan-out search

Follow [the search workflow](references/search_best_practices.md) for API constraints,
enumeration, ranking, permissions and truncation handling. Run its bundled helper:

```bash
python3 scripts/search_fanout.py "<query>"
```

The personalization file is **per-user** and private. This skill ships only a template — see `config-template/copilot.json.example`. A user with no config file gets a neutral default: fan out all accessible KBs, sort groups by hit count, no boosting.

For knowledge-base listing parameter errors, use the search workflow's
“Knowledge-base enumeration” procedure before diagnosing authentication or access.

## Capability 5: Import URLs and extract content

When the pages to read are ones the local machine cannot fetch but IMA's servers can, import them with `wiki/v1/import_urls` and have IMA turn them into JSON that is saved as a note and read back over the API. Imports write to the user's account and no delete endpoint is documented, so confirm the target knowledge base and URL list with the user first. Read `references/import_and_extract.md` before starting: it lists which capabilities were not found in the upstream ima-skill docs (delete, full entry body read) and why extraction goes through the desktop app, how entries resolve asynchronously, the extraction protocol and its measured failure modes (unescaped quotes, truncated rounds, empty placeholder objects), and the desktop-app automation traps.

## What this skill refuses to do

- **Never pin an upstream version in SKILL.md.** The installer script carries a default version for fallback purposes, but SKILL.md itself is version-agnostic to survive upstream releases without requiring a skill bump.
- **Never hardcode a user's knowledge base names.** The `priority_kbs` and `skip_kbs` fields in `copilot.json` are 100% user-configured. Example values in `config-template/copilot.json.example` are illustrative only.
- **Never skip the backup step** when executing a repair, no matter how trivial the diff.

#!/usr/bin/env python3
"""Append memory files verbatim into the documents that will own them.

Usage:
    python3 migrate_verbatim.py plan.json [--dry-run]

plan.json:
    {
      "memory_dir": "~/.claude/projects/<slug>/memory",
      "targets": [
        {
          "path": "~/path/to/owning-doc.md",
          "section": "## Migrated from auto memory (2026-09-24)",
          "intro": "> One line on why these entries are here.",
          "items": [{"file": "feedback_x.md", "title": "Short human title"}]
        }
      ]
    }

For each item the body is the memory file minus its YAML frontmatter. Markdown
headings outside code fences are demoted by three levels so they nest under the
new `### <title> (from memory: <stem>)` heading. Nothing else in the body
changes. The section heading and intro are written once per target; a new file
is created when the target does not exist.

An item whose heading is already in the target is skipped, so a rerun after a
partial failure does not append twice. After writing, every non-blank body line
must appear in the target; otherwise the script exits 1 and names the item.

Exit codes: 0 success, 1 verification failure, 2 bad plan or missing source.
"""
import json
import re
import sys
from pathlib import Path

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6}) ")


def strip_frontmatter(text):
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    return text.strip("\n")


def demote(body, levels=3):
    out, in_fence = [], False
    for line in body.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = HEADING.match(line)
            if m:
                depth = min(len(m.group(1)) + levels, 6)
                line = "#" * depth + line[len(m.group(1)):]
        out.append(line)
    return "\n".join(out)


def item_heading(item):
    stem = item["file"][:-3] if item["file"].endswith(".md") else item["file"]
    return f"### {item['title']} (from memory: {stem})"


def render_body(memory_dir, item):
    source = memory_dir / item["file"]
    if not source.is_file():
        raise FileNotFoundError(f"memory file not found: {source}")
    return demote(strip_frontmatter(source.read_text(encoding="utf-8")))


def run(plan, dry_run=False):
    memory_dir = Path(plan["memory_dir"]).expanduser()
    failures = []
    for target in plan["targets"]:
        path = Path(target["path"]).expanduser()
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        parts, written = [], []
        section = target.get("section")
        if section and section not in current:
            intro = target.get("intro", "").strip()
            parts.append(section + ("\n\n" + intro if intro else "") + "\n")
        for item in target["items"]:
            heading = item_heading(item)
            body = render_body(memory_dir, item)
            if heading in current:
                print(f"skip  {path}: {item['file']} already migrated")
                continue
            parts.append(f"{heading}\n\n{body}\n")
            written.append((item, body))
        if not written:
            continue
        joined = "\n".join(parts)
        new_text = (current.rstrip("\n") + "\n\n" + joined) if current.strip() else joined
        if dry_run:
            print(f"would write {path}: +{len(written)} item(s)")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
        final = path.read_text(encoding="utf-8")
        for item, body in written:
            missing = [ln for ln in body.split("\n") if ln.strip() and ln not in final]
            if missing:
                failures.append((path, item["file"], missing[:3]))
        print(f"ok    {path}: +{len(written)} item(s)")
    return failures


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        plan = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        failures = run(plan, dry_run="--dry-run" in argv)
    except (OSError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for path, name, missing in failures:
        print(f"FAIL  {path}: {name} lines missing after write: {missing}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

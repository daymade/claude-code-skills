#!/usr/bin/env python3
"""
init_wrapper_skill.py — Bootstrap scaffold for a new wrapper skill.

Creates the directory layout and writes stub files with placeholders that
point back at the specific step in workflows/wrapper-skill/workflow.md
that fills each placeholder. The placeholders are deliberately ugly so an
unfinished scaffold is obvious on inspection — you cannot accidentally
commit a half-filled wrapper and mistake it for a real one.

Usage:
    uv run python workflows/wrapper-skill/scripts/init_wrapper_skill.py <wrapper-skill-name> \\
        --tool "<display-tool-name>" \\
        --target-dir <path/to/repo>

Example:
    uv run python workflows/wrapper-skill/scripts/init_wrapper_skill.py ima-copilot \\
        --tool "Tencent IMA" \\
        --target-dir <repo-root>

This produces:

    <target-dir>/<wrapper-skill-name>/
    ├── SKILL.md                          (with <FILL-FROM-STEP-4> markers)
    ├── scripts/
    │   ├── install_<slug>.sh              (755, with <FILL-FROM-STEP-5>)
    │   └── diagnose.sh                    (755, with <FILL-FROM-STEP-7>)
    ├── references/
    │   ├── installation_flow.md
    │   ├── credentials_setup.md
    │   ├── known_issues.md
    │   └── best_practices.md
    └── config-template/
        └── <slug>.json.example            (delete if no per-user config)

After running this script, open workflow.md and start at Step 4 to fill
in each file from the Step 2 mining output.
"""

import argparse
import os
import re
import stat
import sys
from pathlib import Path


# Use a shell-unfriendly marker so unfilled placeholders stand out in grep and
# during skill validation runs. The intent: it is impossible to accidentally
# commit an incomplete wrapper skill without a post-build grep surfacing it.
PLACEHOLDER = "<<< FILL FROM Step {step} of workflow.md >>>"

SKILL_MD_TEMPLATE = """---
name: {name}
description: {placeholder_step_4} Describe the wrapper skill in 4-8 sentences. Use the mined Step 2c error strings as literal triggers. Be pushy — false positives are cheaper than false negatives.
---

# {display_name}

{placeholder_step_4} One-sentence purpose.

## Overview

{placeholder_step_4} 2-4 sentence overview of the upstream tool, the friction this wrapper removes, and the scope of coverage.

## Architectural principles (do not violate)

This skill is a wrapper layer around {tool}. The wrapper contract is non-negotiable:

- **Never vendor upstream files.** This directory does not contain any copy, fork, or excerpt of {tool}'s own content.
- **Repairs happen at runtime, not at ship time.** Fixes live as instructions in `references/known_issues.md`, not as patched files.
- **Always ask before touching upstream files.** Modifying installed {tool} files requires explicit user consent via AskUserQuestion.
- **Teach rather than hide.** Every fix shows the user exactly what changed and where the backup was saved.

## What this skill does

| Capability | Entry point | Detail |
|---|---|---|
| Install upstream {tool} | `scripts/install_{slug}.sh` | See `references/installation_flow.md` |
| Configure credentials | Inline workflow below | See `references/credentials_setup.md` |
| Diagnose and fix known issues | `scripts/diagnose.sh` + workflow below | See `references/known_issues.md` |

## Routing

{placeholder_step_4} Fill routing table.

## Capability 1: Install upstream {tool}

{placeholder_step_5} See `references/installation_flow.md` for details.

```bash
bash scripts/install_{slug}.sh
```

## Capability 2: Configure credentials

{placeholder_step_8} See `references/credentials_setup.md`.

## Capability 3: Diagnose and fix known issues

{placeholder_step_6} Read this section carefully during agent runtime. It contains the full diagnose-then-repair-with-consent flow that makes this wrapper safe.

## What this skill refuses to do

- Vendor, fork, or mirror upstream files into this directory
- Pin an upstream version in this SKILL.md (installer uses overridable defaults, SKILL.md stays version-agnostic)
- Silently patch upstream files — every modification path requires explicit consent
- Hardcode user-specific values

## File layout

```
{name}/
├── SKILL.md                         # This file
├── scripts/
│   ├── install_{slug}.sh            # Download → stage → distribute
│   └── diagnose.sh                  # Read-only health report
├── references/
│   ├── installation_flow.md
│   ├── credentials_setup.md
│   ├── known_issues.md              # Issue registry — source of truth
│   └── best_practices.md
└── config-template/
    └── {slug}.json.example          # Optional; delete if no per-user config
```
"""

INSTALL_SH_TEMPLATE = """#!/usr/bin/env bash
#
# install_{slug}.sh — Install upstream {tool} to supported agents.
#
# {placeholder_step_5}
#
# Re-run safely — every step is idempotent.

set -euo pipefail

{upper_slug}_VERSION="${{{upper_slug}_VERSION:-<FILL-DEFAULT-VERSION-FROM-STEP-2a>}}"
BASE_URL="<FILL-ARTIFACT-URL-FROM-STEP-2a>"
STAGING_ROOT="/tmp/{name}-staging"
STAGING_DIR="${{STAGING_ROOT}}/$(date +%s)-$$"

cleanup() {{
  if [ -n "${{STAGING_DIR:-}}" ] && [ -d "$STAGING_DIR" ]; then
    rm -rf "$STAGING_DIR"
  fi
}}
trap cleanup EXIT

# {placeholder_step_5} Fill in the rest of the installer. Key patterns:
# - curl/wget with explicit --fail and HTTP code check
# - unzip/tar into $STAGING_DIR
# - root SKILL.md detection via known-path-first, depth-sort fallback
# - agent auto-detection via $HOME/.claude, $HOME/.agents, $HOME/.openclaw
# - npx -y skills add <path> -g -y -a <agent>... in default symlink mode
# - No --copy flag (symlink mode propagates repairs across agents)
# - Every cp/mv uses `command` prefix to dodge user shell aliases
#
# See skill-creator/workflows/wrapper-skill/patterns.md for the full template.

echo "TODO: fill install logic per workflow.md Step 5" >&2
exit 1
"""

DIAGNOSE_SH_TEMPLATE = """#!/usr/bin/env bash
#
# diagnose.sh — Read-only health check for upstream {tool} installs.
#
# {placeholder_step_7}
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more issues need user action
#   2 — diagnostic itself failed

set -uo pipefail

PASS=0
WARN=0
FAIL=0

status_ok()   {{ echo "✅ $1"; PASS=$((PASS + 1)); }}
status_warn() {{ echo "⚠️  $1"; WARN=$((WARN + 1)); }}
status_fail() {{ echo "❌ $1"; FAIL=$((FAIL + 1)); }}

echo "=== {name} diagnostic report ==="
echo

# {placeholder_step_7} Fill in the diagnostic checks:
#   1. Per-agent install presence + canonical dedup via realpath
#   2. Credential presence + liveness check
#   3. One scan_issue_NNN function per entry in references/known_issues.md
#
# See skill-creator/workflows/wrapper-skill/patterns.md for the full template.

echo "TODO: fill diagnose logic per workflow.md Step 7" >&2
exit 2
"""

REFERENCES_STUB = {
    "installation_flow.md": (
        "# Installation Flow — Deep Dive\n\n"
        "{placeholder_step_5} Fill from Step 2a of the mining output.\n\n"
        "Cover:\n"
        "- Why a wrapper installer exists (what upstream's installer doesn't do)\n"
        "- Prerequisites (curl, unzip, npx, Node.js version)\n"
        "- Agent detection rules\n"
        "- Version override mechanism\n"
        "- What `npx skills add` does under the hood\n"
        "- File layout after install\n"
        "- Uninstall procedure\n"
        "- Troubleshooting common failures\n"
    ),
    "credentials_setup.md": (
        "# Credentials Setup — Deep Dive\n\n"
        "{placeholder_step_8} Fill from Step 2b of the mining output.\n\n"
        "Cover:\n"
        "- Where credentials go (XDG paths, file modes)\n"
        "- Environment variable fallback\n"
        "- Obtaining credentials from the tool's web UI\n"
        "- Saving credentials securely\n"
        "- Liveness test command\n"
        "- Rotation procedure\n"
        "- Security considerations\n"
    ),
    "known_issues.md": (
        "# Known Issues in Upstream {tool}\n\n"
        "{placeholder_step_6} Fill one entry per bug that was actually "
        "encountered and fixed in the distillation source session. "
        "Use the template in skill-creator/workflows/wrapper-skill/patterns.md.\n\n"
        "## How the agent should use this file\n\n"
        "When `scripts/diagnose.sh` reports a `⚠️` line mentioning `ISSUE-<NNN>`:\n\n"
        "1. Explain to the user in plain language.\n"
        "2. Use AskUserQuestion to let them pick a repair strategy.\n"
        "3. Execute the chosen strategy's commands. Every repair backs up originals first.\n"
        "4. Re-run diagnose to confirm the fix.\n"
        "5. Remind the user that upstream upgrades replace these files, so reruns are expected.\n\n"
        "## Issue registry\n\n"
        "<<< Add ISSUE-001, ISSUE-002, ... entries here — one per bug from Step 2c. >>>\n"
    ),
    "best_practices.md": (
        "# Best Practices for Using {tool}\n\n"
        "{placeholder_step_8} Fill from Step 2d of the mining output.\n\n"
        "Cover:\n"
        "- Non-obvious usage patterns discovered during the source session\n"
        "- Recommended defaults\n"
        "- Common pitfalls users should avoid\n"
        "- When to use this tool vs alternatives\n"
    ),
}

CONFIG_TEMPLATE_STUB = """{{
  "_comment_field1": "<FILL-FROM-STEP-9> Explain what field1 does",
  "field1": ["placeholder-value"],

  "_comment_field2": "<FILL-FROM-STEP-9> Explain what field2 does",
  "field2": []
}}
"""


def slugify(name: str) -> str:
    """Convert a skill name to a filename-friendly slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    if not slug:
        raise ValueError(f"cannot slugify empty string from name: {name!r}")
    return slug


def write_file(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a new wrapper skill for a third-party CLI tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "name",
        help="Wrapper skill name (e.g., 'ima-copilot', 'yt-dlp-companion'). Directory name.",
    )
    parser.add_argument(
        "--tool",
        required=True,
        help="Display name of the upstream tool (e.g., 'Tencent IMA', 'yt-dlp').",
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Parent directory where the wrapper skill will be created (default: current dir).",
    )
    parser.add_argument(
        "--no-config-template",
        action="store_true",
        help="Skip creating config-template/ (use when the tool has no meaningful per-user config).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files if the target directory is not empty.",
    )
    args = parser.parse_args(argv)

    target_dir = Path(args.target_dir).expanduser().resolve()
    if not target_dir.is_dir():
        print(f"error: target directory does not exist: {target_dir}", file=sys.stderr)
        return 1

    skill_dir = target_dir / args.name
    if skill_dir.exists() and not args.force:
        if any(skill_dir.iterdir()):
            print(
                f"error: {skill_dir} already exists and is not empty. "
                f"Pass --force to overwrite.",
                file=sys.stderr,
            )
            return 1

    slug = slugify(args.name)
    upper_slug = slug.upper()

    fmt = {
        "name": args.name,
        "display_name": args.name.replace("-", " ").replace("_", " ").title(),
        "tool": args.tool,
        "slug": slug,
        "upper_slug": upper_slug,
        "placeholder_step_4": PLACEHOLDER.format(step="4"),
        "placeholder_step_5": PLACEHOLDER.format(step="5"),
        "placeholder_step_6": PLACEHOLDER.format(step="6"),
        "placeholder_step_7": PLACEHOLDER.format(step="7"),
        "placeholder_step_8": PLACEHOLDER.format(step="8"),
    }

    print(f"▶ Scaffolding wrapper skill: {args.name}")
    print(f"  Location: {skill_dir}")
    print(f"  Tool:     {args.tool}")
    print(f"  Slug:     {slug}")
    print()

    # SKILL.md
    write_file(skill_dir / "SKILL.md", SKILL_MD_TEMPLATE.format(**fmt))
    print(f"  ✓ SKILL.md")

    # scripts/
    write_file(
        skill_dir / "scripts" / f"install_{slug}.sh",
        INSTALL_SH_TEMPLATE.format(**fmt),
        executable=True,
    )
    print(f"  ✓ scripts/install_{slug}.sh")

    write_file(
        skill_dir / "scripts" / "diagnose.sh",
        DIAGNOSE_SH_TEMPLATE.format(**fmt),
        executable=True,
    )
    print(f"  ✓ scripts/diagnose.sh")

    # references/
    for filename, stub_template in REFERENCES_STUB.items():
        write_file(
            skill_dir / "references" / filename,
            stub_template.format(**fmt),
        )
        print(f"  ✓ references/{filename}")

    # config-template/
    if not args.no_config_template:
        write_file(
            skill_dir / "config-template" / f"{slug}.json.example",
            CONFIG_TEMPLATE_STUB,
        )
        print(f"  ✓ config-template/{slug}.json.example")
    else:
        print(f"  (skipped config-template per --no-config-template)")

    print()
    print(f"✓ Wrapper skill scaffolded at: {skill_dir}")
    print()
    print("Next steps:")
    print(f"  1. Open workflow.md and start at Step 2 (Mine the conversation history)")
    print(f"  2. Fill each file in this order: SKILL.md → install script → known_issues.md")
    print(f"     → diagnose.sh → references → (optional) config template")
    print("  3. Grep for '<<< FILL FROM Step' — no matches should remain when done")
    print(f"  4. Run verification_protocol.md before committing")
    return 0


if __name__ == "__main__":
    sys.exit(main())

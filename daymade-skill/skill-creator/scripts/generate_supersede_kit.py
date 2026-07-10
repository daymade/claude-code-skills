#!/usr/bin/env python3
"""Generate a supersede kit for a skill that collides with an installed plugin.

When a user's skill overlaps with another installed skill (typically an
official or marketplace plugin with a near-identical description), Claude
routes between them at random. This generator stamps two battle-tested
scripts into the target skill's scripts/ directory:

  setup_supersede_hook.sh     consent-based installer (install/uninstall/status)
  supersede-routing-hook.sh   the SessionStart routing hook it installs

The installed hook is conditional by design: `install` refuses to do anything
on machines where the competing plugin is absent, and the hook itself goes
silent if either side later disappears. See
references/skill-precedence-and-coexistence.md for the full decision guide
(when a rename or a description tiebreaker is the better fix).

Usage:
  uv run python -m scripts.generate_supersede_kit <target-skill-dir> \
      --competitor-plugin-id skill-creator@claude-plugins-official \
      --competitor-entry skill-creator:skill-creator \
      [--skill-name NAME]            # default: basename of target-skill-dir
      [--self-plugin-grep PATTERN]   # default: "<skill-name>@" — manifest
                                     #   pattern proving this skill is present;
                                     #   for a suite member use "<suite>@"
      [--winner-entry-hint TEXT]     # how the winner appears in the skill list
      [--task-domain TEXT]           # e.g. "PDF generation task"
      [--routing-note TEXT]          # full override of the injected note
      [--force]                      # overwrite existing kit files
"""

import argparse
import re
import shlex
import stat
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "assets" / "supersede-kit"

TEMPLATES = {
    "setup_supersede_hook.sh.template": "setup_supersede_hook.sh",
    "supersede-routing-hook.sh.template": "supersede-routing-hook.sh",
}

DEFAULT_NOTE = (
    "Skill routing note (from the {skill_name} supersede hook): this machine "
    "has BOTH the {skill_name} skill and the competing {competitor_entry} "
    "(from the {competitor_plugin_id} plugin) installed, and their trigger "
    "domains overlap. For ANY {task_domain}, ALWAYS use {winner_entry_hint}. "
    "Do NOT invoke {competitor_entry} unless the user explicitly asks for it "
    "by name."
)


def build_parser():
    p = argparse.ArgumentParser(
        description="Stamp a supersede kit into a skill's scripts/ directory."
    )
    p.add_argument("target", help="path to the skill directory (must contain SKILL.md)")
    p.add_argument(
        "--competitor-plugin-id",
        required=True,
        help="plugin id checked in installed_plugins.json, e.g. name@marketplace",
    )
    p.add_argument(
        "--competitor-entry",
        required=True,
        help="how the competing skill appears in the skill list, e.g. plugin:skill",
    )
    p.add_argument("--skill-name", help="winner skill name (default: target basename)")
    p.add_argument(
        "--self-plugin-grep",
        help='manifest pattern proving this skill is installed (default: "<skill-name>@")',
    )
    p.add_argument(
        "--winner-entry-hint",
        help="how the winner appears in the skill list (default: `<skill-name>`)",
    )
    p.add_argument(
        "--task-domain",
        default="task in this skill's domain",
        help="task phrase used in the routing note",
    )
    p.add_argument("--routing-note", help="full custom routing note (overrides default)")
    p.add_argument("--force", action="store_true", help="overwrite existing kit files")
    return p


def main():
    args = build_parser().parse_args()

    target = Path(args.target).resolve()
    if not (target / "SKILL.md").is_file():
        sys.exit(f"error: {target} does not look like a skill (no SKILL.md)")
    if "@" not in args.competitor_plugin_id:
        sys.exit("error: --competitor-plugin-id must look like name@marketplace")

    skill_name = args.skill_name or target.name
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", skill_name):
        sys.exit("error: skill name must be 1-64 lowercase letters, numbers, or hyphens")
    self_plugin_grep = args.self_plugin_grep or f"{skill_name}@"
    winner_entry_hint = args.winner_entry_hint or f"`{skill_name}`"
    routing_note = args.routing_note or DEFAULT_NOTE.format(
        skill_name=skill_name,
        competitor_entry=args.competitor_entry,
        competitor_plugin_id=args.competitor_plugin_id,
        task_domain=args.task_domain,
        winner_entry_hint=winner_entry_hint,
    )

    replacements = {
        "{{SKILL_NAME_SHELL}}": shlex.quote(skill_name),
        "{{HOOK_BASENAME_SHELL}}": shlex.quote(f"{skill_name}-supersede-hook.sh"),
        "{{COMPETITOR_PLUGIN_ID_SHELL}}": shlex.quote(args.competitor_plugin_id),
        "{{SELF_PLUGIN_GREP_SHELL}}": shlex.quote(self_plugin_grep),
        "{{ROUTING_NOTE_SHELL}}": shlex.quote(routing_note),
    }

    scripts_dir = target / "scripts"
    scripts_dir.mkdir(exist_ok=True)

    written = []
    for template_name, out_name in TEMPLATES.items():
        template_path = TEMPLATE_DIR / template_name
        if not template_path.is_file():
            sys.exit(f"error: missing template {template_path}")
        out_path = scripts_dir / out_name
        if out_path.exists() and not args.force:
            sys.exit(f"error: {out_path} exists (use --force to overwrite)")

        content = template_path.read_text()
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
        leftover = re.search(r"\{\{[A-Z_]+\}\}", content)
        if leftover:
            sys.exit(f"error: unresolved placeholder {leftover.group(0)} in {template_name}")

        out_path.write_text(content)
        out_path.chmod(out_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(out_path)

    print(f"supersede kit generated for '{skill_name}':")
    for path in written:
        print(f"  {path}")
    print()
    print("Next steps:")
    print("  1. Add a coexistence-check section to the skill's SKILL.md")
    print("     (sample wording: references/skill-precedence-and-coexistence.md).")
    print("  2. The skill offers `scripts/setup_supersede_hook.sh install` when it")
    print("     detects the competing plugin — always with the user's consent.")
    print("  3. Verify: run the setup script with CLAUDE_CONFIG_DIR pointed at a")
    print("     sandbox dir to test install/uninstall/status without touching ~/.claude.")


if __name__ == "__main__":
    main()

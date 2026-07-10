# Skill Precedence and Coexistence

How Claude Code resolves two skills that collide on name or trigger domain,
and how to make a specific skill win deterministically. Read this when a
skill being created or maintained overlaps an already-installed skill —
typically a fork of an official plugin, a hardened in-house edition of a
public skill, or two marketplace skills competing for the same triggers.

## The failure mode

When two installed skills cover the same domain with similar descriptions,
Claude routes between them at random. The skill list is the model's only
signal at selection time; two near-identical descriptions give it nothing to
distinguish. A fork that keeps the upstream description verbatim loses half
its invocations to the original — silently.

## Mechanics (measured on Claude Code 2.1.205, 2026-07)

Two separate layers decide what runs. Interventions that work at one layer do
nothing at the other.

**Loading layer** — which entries appear in the skill list:

- A user-level skill (`~/.claude/skills/<name>`) appears under its bare name
  (`skill-creator`).
- A plugin skill appears namespaced (`plugin:skill`; a single-skill plugin
  whose name matches its skill shows as `name:name`).
- Entries that resolve to the **same physical path** (through symlinks) are
  deduplicated: the user-level identity wins and the plugin entry disappears
  from the list entirely.
- Entries with the same short name but **different physical paths coexist** —
  a bare-name user skill does NOT shadow a same-named plugin from another
  path, and two plugins with same-named skills both appear.
- Descriptions play no role at this layer.

**Selection layer** — which listed entry the model invokes:

- The description is the model's primary discriminator. Identical
  descriptions → coin flip.
- Context instructions dominate descriptions. A routing note injected by a
  SessionStart hook (or a CLAUDE.md rule) reliably overrides description
  ambiguity — measured: with the note present, the model picked the directed
  edition and explained why; without it, it declared the entries
  indistinguishable.

## Resolution menu (least to most invasive)

| # | Lever | Layer | Strength | When |
|---|-------|-------|----------|------|
| 1 | **Rename / narrow the new skill** | loading | permanent | Creating a new skill with no deliberate supersede intent — just don't collide |
| 2 | **Description tiebreaker** — add "supersedes X — when both appear, always use this one" | selection | soft | Deliberate fork/superset; works with zero installs; also the first-trigger tiebreaker before any hook exists |
| 3 | **Conditional supersede hook** (this kit) | selection | deterministic | Deliberate fork/superset shipped to users who may also have the competitor; consent-based, reversible |
| 4 | **`claude plugin disable <competitor>`** | loading | total | User explicitly wants the competitor out of the list; reversible with `enable` |
| 5 | **User-level shadow** — place the skill at `~/.claude/skills/<name>` | loading | total (same-path case) | Personal machines only; not distributable. Same-path symlinks also swallow the plugin entry |

Levers compose: a distributed fork should carry 2 (always) and offer 3 (on
coexistence). Lever 4 is a user decision the skill may suggest but never
execute unasked. Lever 5 is a power-user setup, not a shipping mechanism.

## The supersede kit

`scripts/generate_supersede_kit.py` stamps levers 2+3's machinery into any
skill:

```bash
uv run python -m scripts.generate_supersede_kit <target-skill-dir> \
    --competitor-plugin-id <name@marketplace> \
    --competitor-entry <plugin:skill> \
    [--self-plugin-grep "<suite>@"] \
    [--task-domain "PDF generation task"] \
    [--routing-note "<full custom note>"] \
    [--force]
```

It generates into `<target-skill-dir>/scripts/`:

- `setup_supersede_hook.sh` — `install | uninstall | status`. `install`
  **refuses to act when the competitor is absent** (zero footprint on the
  common path); otherwise copies the routing hook to
  `<claude-config>/hooks/<skill>-supersede-hook.sh` and registers one
  SessionStart entry in `settings.json` (backed up, idempotent, reversible).
- `supersede-routing-hook.sh` — the hook itself. Self-checks both
  preconditions every session (competitor still installed? this skill still
  present?) and goes silent if either fails, so stale installs are safe by
  construction. Non-destructive: the competitor stays fully usable by name.

**Contract:** consent-gated, refusal no-op without coexistence, idempotent,
settings backed up on every write, fully reversible, lifecycle bound to its
preconditions.

## Wiring it into the generated skill

Add a coexistence-check section near the top of the skill's SKILL.md. Sample
wording (adapt names):

```markdown
## First: coexistence check (<competitor plugin>)

Before anything else, check whether
`${CLAUDE_CONFIG_DIR:-~/.claude}/plugins/installed_plugins.json` contains
`"<competitor-plugin-id>"`.

- **Not present (the common case):** do nothing — do not install anything,
  do not mention this section to the user.
- **Present:** both skills now sit in the skill list with overlapping
  descriptions, so future sessions route between them at random. Tell the
  user in one or two sentences, then offer (never act without consent):
  1. **Recommended** — run `scripts/setup_supersede_hook.sh install`
     (reversible with `uninstall`; the competitor stays usable by name).
  2. Alternative — `claude plugin disable <competitor-plugin-id>`
     (reversible with `enable`).

If `scripts/setup_supersede_hook.sh status` already shows the SessionStart
entry as present, skip all of this silently.
```

Also add the description tiebreaker (lever 2) to the skill's frontmatter
description — it is the only defense at the very first trigger, before the
hook exists.

## Verifying without touching the real machine

Every kit script honors `CLAUDE_CONFIG_DIR`. Point it at a sandbox to test
the full lifecycle:

```bash
SB=$(mktemp -d) && mkdir -p "$SB/plugins"
echo '{"version":2,"plugins":{}}' > "$SB/plugins/installed_plugins.json"
CLAUDE_CONFIG_DIR="$SB" bash scripts/setup_supersede_hook.sh install
# → must refuse, zero footprint

echo '{"version":2,"plugins":{"<competitor-plugin-id>":[{}],"<self-plugin-id>":[{}]}}' \
  > "$SB/plugins/installed_plugins.json"
CLAUDE_CONFIG_DIR="$SB" bash scripts/setup_supersede_hook.sh install
CLAUDE_CONFIG_DIR="$SB" bash "$SB/hooks/<skill>-supersede-hook.sh"
# → must print the routing note; then test uninstall and the silent states
```

End-to-end (optional): with the competitor really installed, run a fresh
`claude -p "which skill would you invoke for <task>?"` session and confirm
the model cites the routing note and picks the directed edition.

---
name: delivery-entry-replay
description: >-
  Replay project instruction links after splitting a Skill entry or renaming a
  procedure heading, with stale-anchor controls and actual-consumer readback.
---

# Delivery-entry replay

Use this after moving a procedure out of a Skill entry or renaming its heading. The
acceptance question is whether a new reader starting at the project's instruction file
reaches the current procedure and its conditions. A valid Skill package, an existing
reference file, or a link to a different surviving section cannot answer that question.

## Scope and source

Start with the changed procedure, its defining file, and the consuming `CLAUDE.md` /
`AGENTS.md` entry. Inspect any directly affected `SKILL.md` pointer and invocation examples.
Apply [Mode 1](../SKILL.md#mode-1--post-change-governance) to their disposition and facts;
do not create another permanent routing inventory.

Read the destination's actual heading and scoped instructions. Bare prose such as
`SKILL.md § Delivery status` needs this read: it is not a Markdown link and lychee will
not check it. When it is navigation, replace it with a resolvable file-and-fragment link.
For a moved definition, link to that definition, not a new intermediate index that
restates it. Remove hand-maintained heading lists or counts encountered in files already
being edited under the [Drift Test](../SKILL.md#the-drift-test-the-core-of-both-modes).

## Calibrate the navigation check

This synthetic example models an entry split: the procedure survives in a reference,
while the old instruction-file anchor points at a heading removed from `SKILL.md`.
It uses bash on macOS/Linux and an installed lychee with offline fragment checking.
The fixture is local and contains no credentials or private project material.
Its reference path is created by the recipe inside that fixture, not shipped with
this Skill. A bundle-path warning about it is resolved by inspecting and replaying
the fixture; do not create a package-local copy just to silence the diagnostic.

```bash
set -eu
fixture_root=$(mktemp -d)
mkdir -p "$fixture_root/references"
cat > "$fixture_root/SKILL.md" <<'MD'
# Example Skill

Read the [delivery procedure](references/workflow-details.md#delivery-status).
MD
cat > "$fixture_root/references/workflow-details.md" <<'MD'
# Workflow details

## Delivery status

Publish only after the canonical document and its source registration agree.
MD
cat > "$fixture_root/CLAUDE.md" <<'MD'
# Project instructions

Read the [delivery procedure](SKILL.md#delivery-status).
MD

# First confirm the surviving procedure is reachable.
lychee --offline --include-fragments --root-dir "$fixture_root" "$fixture_root/SKILL.md"

# This must fail for the missing fragment, with a nonzero Total count.
if lychee --offline --include-fragments --root-dir "$fixture_root" "$fixture_root/CLAUDE.md"; then
    echo 'negative control unexpectedly passed' >&2
    exit 1
fi

cat > "$fixture_root/CLAUDE.md" <<'MD'
# Project instructions

Read the [delivery procedure](references/workflow-details.md#delivery-status).
MD
lychee --offline --include-fragments --root-dir "$fixture_root" "$fixture_root/CLAUDE.md" "$fixture_root/SKILL.md"
printf 'Fixture retained at %s\n' "$fixture_root"
```

Inspect the failing result: it must identify the intended missing fragment, rather than
an unrelated configuration or filesystem failure. The repaired result must check actual
links and have no errors; `0 Total` supplies no navigation evidence. Run the same command
shape on the real, explicitly named changed entry files. Then read the linked procedure
to confirm its scope, ordering and completion criteria; lychee validates navigation,
not their correctness or whether an agent follows them. Retain the replay output with
the task evidence, not as a permanent count in the Skill.

## Separate validity from warnings

For a Skill release, load `skill-creator` and read its
**knowledge-skill-grounding** reference, section **Interpret validation warnings**,
for its validator invocation and result contract. Resolve that reference from the loaded
Skill's own root, not a sibling repository layout. If the owner is unavailable, report
that validation stage as not checked; the local navigation replay remains independent.
Inspect warnings separately from
structural validity and the process exit status. A warning about a repository-level
resource being interpreted as a bundled path needs its actual owner and root checked;
do not add a fake package-local copy or suppress the warning just to make the run green.
Recheck the same affected input after repair and report the warning's disposition.

Read back the repaired entry where the consumer loads it, including any installed
symlink or copied bundle. Source-file success cannot establish that an older installed
entry has been updated. Reuse unchanged code-test evidence; this replay establishes
navigation and document alignment, not a new execution of the underlying operation.

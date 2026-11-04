# Background intermediate storage

When a reader wants only canonical documents, keep correction work outside the
library. Configure the existing runtime `config.json` under the resolved
`TRANSCRIPT_FIXER_CONFIG_DIR` (otherwise `~/.transcript-fixer`):

```json
{"paths": {"intermediate_root": "/absolute/private-workspace"}}
```

Preserve every other configuration field. The optional value is null or a
nonempty absolute path; a relative, blank or wrong-type value fails. With no
setting or null, the old adjacent-output defaults remain supported.

Each input gets `<intermediate_root>/<sha256(resolved absolute input path)>/`.
Hash the UTF-8 path string, including its filename. This separates two inputs
with the same basename. Default Stage 1/2, dry-run, diff and review outputs use
that directory. `--output` still overrides run outputs and the default report
location; `--sidecar-dir` independently overrides `_changes.md` and `_needs_review.md`. Explicit paths are intentional
overrides, not proof that a caller followed the library's storage policy.

Ordinary runs register report locations in the existing review database.
`--close-sidecars --input FILE --dry-run --json` discovers the configured workspace
and registered report directories from the canonical input identity. An open or
blocked result keeps the evidence. That result concerns evidence closure, not
permission to archive the canonical document or proof that a person must annotate.
The original quality gate still applies before calling a transcript final.

An ingest consumer must accept the configured per-input location or explicitly
bind its own private temporary workspace. Never relax containment to accept an
arbitrary path announced in producer JSON. Check the actual consumer before
enabling a new default. A temporary caller must preserve review reports before
its workspace expires.

## Existing adjacent files

Freeze the affected directory inventory, original paths and hashes before moving
old intermediates. Preserve every byte and modification time outside the library,
including unique run outputs and reports whose canonical was renamed or moved.
Do not promote an old run output merely to make the directory clean.

For an identified canonical, place its files in the same per-input workspace and
register the report's canonical/path association in `review_report_locations`.
Retain orphaned files under a separate legacy archive with their original-path
map; do not invent a canonical or re-anchor a review row from filename similarity.
Check existing ownership and refuse conflicting destination bytes. Copy and
independently verify the retained bytes before removing an adjacent copy; preserve
an intervening edit and stop that entry. On resume, use the frozen identities and
verified retained copies, not a fresh glob that silently drops missing entries.

Afterward verify every original canonical hash, every retained auxiliary hash,
the same library scope for residual files, and the queue's unchanged rows/verdicts.
Exercise normal location discovery on one migrated pending report. Never use
`skipped`, `kept_original`, report deletion or a directory move as a substitute
for missing wording or identity evidence.

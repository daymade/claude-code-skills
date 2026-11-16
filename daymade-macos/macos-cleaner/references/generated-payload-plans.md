# Classify generated payloads in the plan checker

Use this contract for exact dependency trees, build caches, retired packaged test
Apps, release payloads and generated test/CI copies. It does not prescribe how many
versions an application retains. Follow its owner's current retention policy and
the user's instruction for the specific payload.

Before sending the Phase 2 plan, the executor adds a payload-facts table to the
same classification-table file and runs the ordinary plan checker. Use one exact
target per row, matching its classification target byte for byte. The facts may
also be columns of the classification table. Other plan families keep their
existing table. Conventional paths containing `releases`, `node_modules`, `.venv`,
`target`, `dist`, generated/source/test/build-copy roots or test App names require
these facts even when the table was omitted. List unconventional generated paths
explicitly; path recognition cannot discover every naming scheme.

| Column | Required value |
|---|---|
| Target | The exact classification target |
| Payload kind | `dependency`, `build-cache`, `retired-test-app`, `release` or `generated-test-copy` |
| Current use | `inactive: <current consumer/process/config observation>`, `active: <observation>` or `unknown: <smallest next check>` |
| Unique state | `absent: <inspection/comparison basis>`, `present: <unique edits, local Git, database/auth/user state>` or `unknown: <smallest next check>` |
| Recovery input | Source/ref/lockfile, current installation or other verified recovery locator; `unknown: <next check>` when unverified. For a retired test App or release binary the user explicitly chose to discard, `discard-directed: "<original discard instruction>"` preserves that decision without requiring exact binary reproduction |
| Restoration cost | Rebuild/download cost; `unknown: <next check>` when unverified |
| Retention basis | `none: <consumers finished>`, `historical-only: <old plan/config references>`, `current-use: <observation>`, `current-policy: <current owner policy covering this exact payload>`, `unique-state: <unique value>`, `user-requested: "<original direction for this payload>"` or `unknown: <next check>` |
| Backup plan | `none: <no new copy>`, `unique-state: <reason>` or `user-requested: "<original direction for this copy>"` |

The checker returns `RETIRE-CANDIDATE` for verified inactive, nonunique,
reproducible payloads with understood restoration cost and no current retention
instruction. Put those rows in the candidate action set as REBUILDABLE or
PROPOSABLE. An old plan or configuration mentioning a path is historical evidence;
check the actual current selector, consumer and process before declaring it live.
Historical references alone do not require a complete retained payload or backup.

It returns `PRESERVE` for live, unique, unknown, policy-retained or explicitly retained payloads and
requires those rows outside the action set. Missing, blank and null facts fail the
plan; they are not evidence of absence. A remote recovery locator need not exist
on the executor's local filesystem: verify it through its owner, record that
observation and retain unknown if access cannot be checked. The checker validates
the supplied facts, not their truth; read its decisions and unresolved checks.

Any planned backup needs the existing `--copy-budget` with the same exact target
and basis. Automatic full backup of a nonunique disposable payload fails. A user
request to preserve or copy that specific payload remains valid. None of these
decisions authorizes deletion; Phase 3 still uses current authorization and a
fresh live-state check.

Run the output-level example through the actual entry:

```bash
python3 scripts/check_gate_plan.py \
  --table tests/fixtures/corpus/generated-payload-plan.md \
  --plan tests/fixtures/corpus/generated-payload-plan.md
```

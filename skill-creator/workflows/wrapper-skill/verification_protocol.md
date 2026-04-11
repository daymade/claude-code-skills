# Verification Protocol

How to verify a freshly distilled wrapper skill before commit. A generated wrapper is made of two very different kinds of files, and they require two very different kinds of verification. Confusing the two is a common mistake that will make you either (a) skip verification entirely because "the session already proved it works" or (b) waste effort re-dogfooding things that were already dogfooded.

This protocol names the two kinds and says what to do with each.

## Two tracks of verification

### Track 1 — Literal transcriptions (session cross-reference)

These files are **re-encodings of commands and observations that actually happened in the source session**. They contain nothing that hasn't been run already:

- `scripts/install_<tool>.sh` — a shell script whose every non-trivial line should appear somewhere in the session's history as a command that was executed
- `references/known_issues.md` — each ISSUE entry is a literal transcription of an error message that was observed plus a fix command that was run
- `scripts/diagnose.sh` at the **detection-logic** level — the set of states it checks for corresponds 1:1 to the states the session worked through
- `references/installation_flow.md` and `references/credentials_setup.md` — prose retellings of what the session did

For these files, verification is **session cross-reference**: prove that every artifact in the file is traceable to a moment in the conversation. If something in the file has no provenance in the session, it is speculation — delete it.

**Why not run these files end-to-end instead of cross-referencing**: running `install_<tool>.sh` in a sandbox doesn't prove it's right — it proves it doesn't crash, which is much weaker. The session already proved the commands work in the real environment. What can still be wrong is a **transcription error**: a wrong flag, a paraphrased command, a bug fix applied to the wrong file. Cross-reference catches exactly those.

### Track 2 — Runtime logic (smoke test / unit test)

These files contain **original code that was not literally run in the session** — code that encodes patterns derived from the session but is new as of the distillation:

- `scripts/search_fanout.py`, `scripts/report.js`, or any other language file under `scripts/` whose purpose is to execute logic at skill-run time
- `scripts/diagnose.sh` at the **glue-code** level — string parsing, path resolution, realpath-based dedup, error-message matching — anything that was *written* during distillation rather than transcribed from a session command
- Any cross-platform compatibility shim (different install paths per OS, different shell quoting per environment) because the session ran on exactly one platform
- Any configuration file parser, API client, or data transformation that generates output for the user

For these files, **session cross-reference is insufficient**. The cross-reference only proves that the idea behind the file came from the session — it cannot prove that the implementation of the idea is correct. A `rank_groups()` function inspired by the session's discussion of search-result partitioning still has to actually partition correctly, which requires running it.

For Track 2 files:

1. **Write at least one smoke-test invocation** of the file with realistic input, run it, and confirm the output matches expectations. If the file is a Python script, `python3 scripts/<name>.py <sample-args>`. If it's a shell function, exercise it in a shell with captured output.
2. **If the file has cross-platform code**, test on the platform the session ran on first, then note in the file that other platforms are untested until a user reports running on them. Do not pretend otherwise.
3. **For scripts that depend on external state** (config files, credentials, network resources), use a minimal fake fixture when possible. For `search_fanout.py`-style scripts, a small `IMA_COPILOT_CONFIG` pointing at a test JSON is enough.

If a Track 2 file cannot be smoke-tested without reaching a production system (e.g., it hits an API that requires real credentials), the protocol accepts the limitation but requires the wrapper to ship a **scoped warning** in its `references/installation_flow.md` saying "scripts/<name> is shipped without end-to-end verification; exercise it with a no-op input before relying on its output in production."

### How to tell which track a file belongs to

Ask: **"If I deleted this file and regenerated it from the session transcript alone, would the regeneration be byte-identical to the original?"**

- **Yes** → Track 1. The file is a literal transcription and cross-reference verification is sufficient.
- **No** → Track 2. The file contains original code or decisions not in the transcript, and needs smoke testing in addition to cross-reference.

Most wrappers are ~70% Track 1, ~30% Track 2. The ima-copilot reference is about 60/40 — `install_ima_skill.sh`, `known_issues.md`, and `references/installation_flow.md` are Track 1; `search_fanout.py`, `diagnose.sh` (glue code), and the symlink-dedup logic are Track 2. Both tracks got appropriate treatment in the canonical example.

## The full verification checklist

### Step 1 — Structural validity (both tracks)

Run the repo's standard validation from the repo root. Use the `git rev-parse --show-toplevel` trick to avoid CWD surprises:

```bash
REPO_ROOT=$(git -C . rev-parse --show-toplevel)
cd "$REPO_ROOT/skill-creator"
uv run --with PyYAML python -m scripts.quick_validate "$REPO_ROOT/<wrapper-skill-name>"
uv run python -m scripts.security_scan "$REPO_ROOT/<wrapper-skill-name>"
```

Both should pass. `quick_validate` enforces SKILL.md frontmatter shape, the 1024-char description cap, and path reference integrity. `security_scan` catches committed credentials, personal directories, and company names.

### Step 2 — Track 1 verification: session cross-reference

Walk through every Track 1 file and confirm each non-trivial line traces to the session:

- **`install_<tool>.sh`**: for each shell command, grep the session history for the literal command text. Paraphrases don't count — the script should match the commands that actually ran in the session, not commands that would have been *equivalent*. If a command in the script has no grep hit, either delete it or replace it with the actual command that ran.
- **`known_issues.md` ISSUE entries**: for each entry, locate the session moment where the literal error message first appeared, and the session moment where the fix was applied. The error message in the entry should be byte-identical to what was observed. The fix commands should be byte-identical to what was run.
- **`diagnose.sh` detection states**: each state returned by a check function should correspond to a state the session actually worked through. If `check_submodule` returns code 5 for a state nobody encountered, that's speculative — remove it unless there's a grounded reason (like the Step A5 dual-state fix, which was added because the session explicitly considered and closed the conflict case).
- **`installation_flow.md` prose**: each section should paraphrase something that happened in the session. Sections about "what to do if X fails" are legitimate only if X was observed in the session, even briefly, or is a trivially-obvious failure mode.

When in doubt, grep the conversation history. If grep finds nothing and you can't justify why the content should exist, the content is unsupported — delete it.

### Step 3 — Track 2 verification: smoke test

For every Track 2 file in the wrapper:

1. **Identify the minimum input** that exercises the file's main code path. For a Python script that takes command-line args, this is a sample invocation. For a shell function called from other scripts, this is a shell harness that calls it with test values.
2. **Run it** and inspect the output. The output should match what you expect based on the session's discussion of what the file is supposed to do.
3. **If the file depends on external state** (config file, environment variables, network), use a minimal fake fixture. Example: `IMA_COPILOT_CONFIG=/tmp/test-config.json python3 scripts/search_fanout.py "test query"` with a small hand-written config.
4. **For cross-platform code**, test only on the session's platform. Note any untested platforms in the file's header comment so future users know what's verified.
5. **For scripts that hit real APIs with real credentials**: if you can run a no-op probe (empty-query search, list-with-limit-1, etc.) against a real credential, do that. If not, ship the file with a warning and a TODO to add a mockable test in a follow-up.

The smoke test does not have to catch every bug — it has to catch "the script crashes immediately" and "the script's main code path returns complete nonsense". Anything more sophisticated is a bonus.

### Step 4 — Mental dry-run of the wrapper as a fresh agent

Read the generated `SKILL.md` as if you were a new Claude session and a user has just asked you to install the tool. Walk through the routing:

- Does the description trigger for the symptom the original session started with?
- Does the Capability 1 path lead to a complete install if Claude follows the instructions literally and does not consult its memory of the source session?
- Does the Capability 3 diagnose flow reach each `known_issues.md` entry?
- Would a new user, given only the description and the references, be able to understand each known issue and decide between repair strategies?

If any of these breaks, the wrapper is not yet shippable. The usual fix is adding more signal to the description (for triggering) or adding more concrete detail in a reference file (for understanding).

### Step 5 — Release metadata consistency

Before commit, confirm the marketplace and release docs are consistent with the new skill:

- `marketplace.json`: new `plugins[]` entry exists, `metadata.version` bumped, description list mentions the new skill.
- `CHANGELOG.md`: entry under the new version with a summary of what was added.
- `README.md` and `README.zh-CN.md`: if the repo has a skill index, the new skill is listed with accurate description.
- Repo-level `CLAUDE.md`: if it counts skills, the count is incremented.
- `.security-scan-passed` file exists in the wrapper directory (created by `security_scan.py`).

A common slip is committing the wrapper skill but forgetting to add it to `marketplace.json`. Run a quick guard before `git add`:

```bash
grep -q '"<wrapper-skill-name>"' "$REPO_ROOT/.claude-plugin/marketplace.json" \
  || echo "MISSING: add wrapper to marketplace.json plugins[] and bump metadata.version"
```

The grep must print nothing before you proceed to commit.

## When verification surfaces a problem

If Step 2 (cross-reference) turns up a mismatch between what a Track 1 file says and what the session actually did, the correct fix is to **re-mine the relevant section of Step 2 in the workflow and regenerate the affected file**. Do not patch the generated file to match your memory — patch it to match what the session actually contained, because that is the source of truth.

If Step 3 (smoke test) turns up a runtime failure in a Track 2 file, the correct fix is to **fix the code** (not the session transcript). Runtime failures are bugs in the distillation of a pattern from the session into code — the pattern may be right even if the implementation is wrong.

Common mismatches and their causes:

| Mismatch | Track | Usual cause | Fix |
|---|---|---|---|
| `install_<tool>.sh` contains a flag you don't recognize | 1 | The flag was added during mid-session iteration | Search the session for when the flag was introduced. If the pre-flag version worked, remove it. |
| `known_issues.md` entry has a plausible but slightly off error message | 1 | Paraphrase drift | Search for the literal error and paste it verbatim. |
| Two known issues describe the same underlying problem | 1 | Distillation split a single bug into two entries | Merge them. |
| Credential path in `credentials_setup.md` doesn't match `install_<tool>.sh` | 1 | Distillation drew from two moments of the session | Determine which path the session ended with and use that in both files. |
| `diagnose.sh` detects an issue that `known_issues.md` doesn't describe | 1 or 2 | You added a speculative check | Either add the matching `known_issues.md` entry if the issue is real, or remove the check. |
| `scripts/*.py` crashes on the sample smoke input | 2 | Implementation bug | Fix the code, re-run the smoke test, and add a comment explaining the fix so future maintainers don't regress it. |
| `scripts/*.py` returns nonsense output on the sample smoke input | 2 | Logic bug (wrong partitioning, wrong sort key, wrong fallback) | Fix the code and consider whether the bug is a symptom of a missing test case to commit. |
| A shell function in `diagnose.sh` reports clean on a state it should flag | 2 | Incomplete state coverage in the detection logic | Add the missing state to the check function (see the A5 dual-state fix in `ima-copilot` for an example). |

## Why this matters

It is tempting to skip Track 2 because it feels like duplicated work — "the session already dogfooded this". It isn't. The session dogfooded *the install commands and the fixes*; it did not dogfood *the distillation of those commands and fixes into new Python/shell code*. The distillation is where bugs get introduced. A wrapper that skips Track 2 ships untested code against unexercised paths, and the author won't know until a second user hits a failure mode the author didn't think about.

The simplest heuristic: if you wrote new code (not just pasted commands from the session), run it at least once with a realistic input before you commit it.

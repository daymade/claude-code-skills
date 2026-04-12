# Known Issues in the Gangtise Ecosystem

This file is the **source of truth** for every upstream issue that `gangtise-copilot` is aware of. Unlike a typical wrapper skill, `gangtise-copilot` did not emerge from a session that fixed active upstream bugs — the Gangtise OpenAPI skills are well-maintained and there are no broken files to patch. The issues documented below are instead **discoverability gaps** and **ecosystem traps** that a first-time user is likely to fall into, along with the runtime workarounds that `gangtise-copilot` applies on their behalf.

## How the agent should use this file

When `scripts/diagnose.sh` reports a `⚠️` or `❌` line, or when a user's question matches one of the issue patterns below, use this file as the lookup table:

1. Explain to the user in plain language what's going on and why it matters.
2. Execute the documented fix (for ISSUE-001, ISSUE-002, ISSUE-003, the "fix" is already baked into the installer — the user just needs to understand the what and why).
3. For newly-discovered issues, file a new `ISSUE-NNN` entry with the full schema.

## Issue registry

### ISSUE-001 — Two parallel product lines with overlapping names but different capabilities

**Status**: Observed on the Gangtise OpenAPI skill ecosystem as of April 2026. Likely permanent — these are two intentionally separate product lines, not a bug.

**Symptom**: A user installs `gangtise-data` (the short name) and then fails to find capabilities they expected to be there. They look at the 4 scripts shipped with `gangtise-data` and wonder where `security.py`, `shareholder.py`, `industry_indicator.py`, `block_component.py`, and `index.py` went. Or worse, they install both `gangtise-data` AND `gangtise-data-client` because they look unrelated, then can't tell which one to call for a given task.

**Root cause**: Gangtise maintains **two parallel naming conventions** for its data-retrieval skills:

| Naming pattern | Example | Positioning |
|---|---|---|
| `gangtise-<name>` | `gangtise-data`, `gangtise-file`, `gangtise-kb` | **Legacy minimal** — strict codes only, CSV-focused, smaller scope |
| `gangtise-<name>-client` | `gangtise-data-client`, `gangtise-file-client`, `gangtise-kb-client` | **Full capability** — name resolution, 2-3× more scripts, richer output |

Both lines are actively maintained. Their Last-Modified timestamps on the OBS bucket match exactly (2026-04-10), and they are distributed in two separate aggregate bundles (`gangtise-skills.zip` and `gangtise-skills-client.zip` respectively).

**Capability gap** (what the minimal line is missing vs the client line):

| Function | In `-client` | In minimal | Example script |
|---|:---:|:---:|---|
| Security code resolution | ✓ | ✗ | `security.py` |
| Sector / theme constituents | ✓ | ✗ | `block_component.py` |
| Index catalog | ✓ | ✗ | `index.py` |
| Industry + macro indicators | ✓ | ✗ | `industry_indicator.py` |
| Shareholder / holding data | ✓ | ✗ | `shareholder.py` |
| Chart data | ✓ | ✗ | `chart.py` (file-client only) |
| Internal reports | ✓ | ✗ | `internal_report.py` (file-client only) |
| WeChat messages | ✓ | ✗ | `wechat_message.py` (file-client only) |
| Opinion blocks | ✓ | ✗ | `opinion_blocks.py` (file-client only) |

**Impact**: A user who installs only the minimal line and then tries to do "standard" investment research will hit 5-9 dead ends (one per missing capability), with no upstream error message explaining why the capability isn't there.

**Why upstream probably hasn't "fixed" it**: This is not a bug — it's an intentional product-line decision. The minimal line exists for batch / pipeline use cases where strict inputs are a feature (preventing name-resolution ambiguity at scale), and the client line exists for interactive / research use cases. Gangtise has a legitimate reason to keep both. The problem is that the two lines **look like one line with a suffix typo** to new users, which leads to confusion.

**How to explain it to the user** (plain language):

> Gangtise has two versions of every data skill: a short-name version (`gangtise-data`) that's for batch CSV work and requires strict stock codes, and a long-name version (`gangtise-data-client`) that's for interactive research and accepts Chinese names. Unless you know you specifically want the batch-CSV version, use the `-client` version. Our installer defaults to installing both so you can see the difference, but for workshop use we only recommend the `-client` skills.

**Repair strategy** (already baked into the installer):

- `--preset full` installs **both** lines so users can compare them and understand the difference firsthand.
- `--preset workshop` installs **only** `-client` variants (the recommended interactive line for investor workshops).
- `--preset minimal` installs **only** the legacy minimal line (for users who explicitly want it).

No runtime file modification is needed. The wrapper's choice is at install-preset level.

---

### ISSUE-002 — Two skills exist only inside a bundle ZIP, never standalone

**Status**: Observed on the Gangtise OpenAPI skill ecosystem as of April 2026.

**Symptom**: A diligent user enumerates `gts-download.obs.myhuaweicloud.com/skills/gangtise-*.zip` by trying every plausible skill name they've seen referenced in upstream SKILL.md files. They find standalone ZIPs for most skills, but **`gangtise-stockpool-client` and `gangtise-file-client-no-download` return HTTP 403** (NoSuchKey in Huawei Cloud OBS's dialect). They assume these skills don't exist and write their installer without them, leaving users silently missing 2 capabilities.

**Root cause**: These two skills **only exist inside the `gangtise-skills-client.zip` bundle**. There are no corresponding standalone `gangtise-stockpool-client.zip` or `gangtise-file-client-no-download.zip` files on the OBS bucket. The only way to discover them is to:

1. Download `gangtise-skills-client.zip`
2. Unzip it
3. Find the 2 extra subdirectories alongside the expected `data-client` / `kb-client` / `file-client`

OBS has its LIST permission disabled (403 on `?list-type=2` and friends), so there is no way to programmatically enumerate the bucket. A naive "HEAD on each candidate name" enumerator will not discover these.

**Impact**: A wrapper that does "one HTTP request per expected skill name" will silently drop `stockpool-client` and `file-client-no-download` from the install, and users will not be able to manage stock pools or use the read-only variant of file-client.

**Why upstream probably hasn't "fixed" it**: This is a packaging choice, not a bug. Gangtise maintains `gangtise-skills-client.zip` as a curated bundle that pins a specific combination of skills (including the two that only exist in-bundle) as the recommended install. Standalone ZIPs for every skill would duplicate storage and introduce version-drift risk between the bundle and the standalone. The problem is again discoverability, not function.

**How to explain it to the user** (plain language):

> Two of the Gangtise skills, `gangtise-stockpool-client` and `gangtise-file-client-no-download`, don't have their own download ZIP — they only exist inside the `gangtise-skills-client.zip` bundle. Our installer downloads this bundle and unpacks all 5 skills from it, so you get them for free if you install with the wrapper. But if you were writing your own installer from scratch, you would miss them unless you knew to look inside the bundle.

**Repair strategy** (already baked into the installer):

The installer's bundle map in `scripts/install_gangtise.sh` hard-codes both hidden skills as contents of `gangtise-skills-client.zip`:

```bash
BUNDLES=(
  "gangtise-skills-client:gangtise-data-client,gangtise-file-client,gangtise-file-client-no-download,gangtise-kb-client,gangtise-stockpool-client"
  ...
)
```

When a preset requests `gangtise-stockpool-client`, the installer knows to download `gangtise-skills-client.zip` (not a non-existent `gangtise-stockpool-client.zip`) and extract the nested subdirectory.

---

### ISSUE-003 — `token is invalid` when Authorization header has double `Bearer` prefix

**Status**: Not an upstream bug — it's a common mistake when integrating with the Gangtise OpenAPI from third-party code.

**Symptom**: User's integration code calls a Gangtise API endpoint with a valid `accessToken` but gets back:

```json
{"code":"0000001008","status":false,"msg":"token is invalid"}
```

…despite having just successfully authenticated and received a token from `loginV2`.

**Root cause**: The `loginV2` response returns an `accessToken` value that **already includes** the `Bearer ` prefix:

```json
{"data":{"accessToken":"Bearer REDACTED-TOKEN-EXAMPLE",...}}
```

Many integration guides for other OAuth APIs tell developers to "prepend `Bearer ` to the token when setting the Authorization header". If a developer does this mechanically, they end up with:

```
Authorization: Bearer Bearer REDACTED-TOKEN-EXAMPLE
```

…which Gangtise's auth middleware correctly rejects as invalid.

**Impact**: Every subsequent API call (RAG search, data queries, workflow invocations) fails with `token is invalid`, and the user thinks their credentials are broken when actually their integration code is wrong.

**Why upstream probably hasn't "fixed" it**: The API contract is consistent — `accessToken` is a full, ready-to-use Authorization header value. A developer who reads the Gangtise OpenAPI docs carefully will understand this. The mistake comes from developers copying OAuth integration patterns from other APIs.

**How to explain it to the user** (plain language):

> Gangtise's `loginV2` endpoint returns a token that **already starts with** the word `Bearer `. If you're copying OAuth integration patterns from Stripe or GitHub, you might be adding another `Bearer ` on top of it. Check your Authorization header — if it says `Bearer Bearer <token>`, remove one of them.

**Repair strategy**:

When integrating with Gangtise manually, use this pattern:

```python
# CORRECT
raw_token = response.json()["data"]["accessToken"]
# raw_token already looks like "Bearer fb335616-..."
headers = {"Authorization": raw_token}

# WRONG
raw_token = response.json()["data"]["accessToken"]
headers = {"Authorization": f"Bearer {raw_token}"}  # ❌ double prefix
```

Or, defensively, strip any existing prefix first:

```python
raw_token = response.json()["data"]["accessToken"]
bare_token = raw_token.replace("Bearer ", "", 1)
headers = {"Authorization": f"Bearer {bare_token}"}
```

This issue does not affect `gangtise-copilot` itself — the wrapper's scripts do not touch the Authorization header directly because they delegate to each skill's own `utils.py`, which handles the token correctly. But if you're writing custom Gangtise integration code alongside the wrapper, watch for this.

---

### ISSUE-004 — `the uri can't be accessed` on `skills-backend` admin endpoints

**Status**: Observed as of April 2026. Not a bug — an intentional access restriction.

**Symptom**: User tries to enumerate Gangtise's skill catalog by calling `/application/skills-backend/list` or similar admin endpoints with a valid Bearer token and gets:

```json
{"code":"0000001009","status":false,"msg":"the uri can't be accessed"}
```

**Root cause**: The `skills-backend` service is an **internal admin API** that is not exposed to regular OpenAPI users. The `loginV2` auth path mints tokens with data-query scopes (`rag`, `data`, `file`, `openapi`) but not `skills-backend-admin` scope. Even with a valid token, regular users cannot list the skill manifest.

**Impact**: A developer trying to build a Gangtise skill listing tool by calling the admin API directly will be blocked. This is why `gangtise-copilot`'s installer uses a hard-coded bundle list instead of querying a live manifest — the live manifest is not accessible.

**Why upstream probably hasn't "fixed" it**: This is a deliberate security boundary. `skills-backend` is the admin interface Gangtise's own internal tooling uses; exposing it to OpenAPI clients would leak information about internal skill naming, versioning, and distribution paths that isn't meant to be public.

**How to explain it to the user** (plain language):

> Gangtise has an internal API for listing all available skills, but it's locked down — your OpenAPI account can't call it. The `gangtise-copilot` installer works around this by maintaining a hard-coded list of the 19 known skills. If Gangtise releases a new skill, the installer needs to be updated by hand (or you'll hit ISSUE-005).

**Repair strategy**: None needed on the user side. `gangtise-copilot` maintains the bundle list in `install_gangtise.sh` and updates are pushed via the wrapper's own release cycle. Users who want to discover new skills should check the Gangtise OpenAPI portal or ask their Gangtise account administrator.

---

### ISSUE-005 — New upstream skill added after installer release

**Status**: Hypothetical — hasn't happened yet, but will happen eventually.

**Symptom**: Gangtise releases a new skill (e.g., `gangtise-hotspot-tracker`) that isn't in `gangtise-copilot`'s bundle map. Users who ran the installer before this release do not get the new skill. There is no automatic notification.

**Root cause**: ISSUE-004 combined with the lack of a public release feed from Gangtise. The installer can't enumerate the bucket; Gangtise doesn't publish RSS/webhook notifications for new skills.

**Impact**: Gradual drift between `gangtise-copilot`'s bundle map and upstream reality. Users think they have "all Gangtise skills" but they actually have "all Gangtise skills as of the last wrapper release".

**Why upstream probably hasn't "fixed" it**: Because ISSUE-004. Upstream would need to open a public manifest feed or a release notification channel, which they currently don't offer.

**How to explain it to the user** (plain language):

> `gangtise-copilot` has a hard-coded list of 19 Gangtise skills that were known to exist as of the wrapper's last release. If Gangtise publishes new skills after that, you won't get them automatically. When you hear about a new Gangtise skill, either update `gangtise-copilot` to the latest version (which should include the new skill) or install the new skill manually with `curl + unzip` from the OBS URL.

**Repair strategy**:

- **User side**: File an issue on the `gangtise-copilot` repo mentioning the new skill's name (and, if known, its OBS URL). The maintainer will update the bundle map in the next release.
- **Manual fallback**: Users who can't wait can do:

```bash
cd /tmp
curl -O https://gts-download.obs.myhuaweicloud.com/skills/gangtise-<new-skill>.zip
unzip gangtise-<new-skill>.zip -d $HOME/.claude/skills/
ln -sfn $HOME/.config/gangtise/authorization.json \
        $HOME/.claude/skills/gangtise-<new-skill>/scripts/.authorization
```

This installs the new skill manually; on the next `gangtise-copilot` upgrade the wrapper will take over management of it automatically (or the manual install will coexist harmlessly).

---

### ISSUE-006 — CLI scripts fail after configure because `~/.GTS_AUTHORIZATION` is missing

**Status**: Observed on 2026-04-12 while running the investor Workshop Demo 2 pipeline.

**Symptom**: `diagnose.sh` passes OAuth + RAG checks, but direct upstream CLI script calls fail at import time. Typical failure:

```text
ImportError: cannot import name 'GTS_AUTHORIZATION' from 'utils'
```

This was reproduced with:

```bash
python3 gangtise-data-client/scripts/quote.py --securities 宁德时代 -sd 2026-04-01 -ed 2026-04-10
python3 gangtise-file-client/scripts/report.py -k 宁德时代 -l 5
python3 gangtise-kb-client/scripts/kb.py -q "宁德时代" -l 5
```

**Root cause**: Many upstream scripts read a bare token from `~/.GTS_AUTHORIZATION` at module import time. The wrapper originally wrote only `~/.config/gangtise/authorization.json` and per-skill `.authorization` symlinks. That is enough for OAuth verification, but not enough for scripts whose `utils.py` expects `~/.GTS_AUTHORIZATION`.

**Impact**: A wrapper install can look healthy while the first real data call fails in a workshop.

**Repair strategy**: Run the configurator after install. It now writes both:

- `~/.config/gangtise/authorization.json` — durable accessKey + secretAccessKey config
- `~/.GTS_AUTHORIZATION` — short-lived bare runtime token for upstream CLI scripts

```bash
bash scripts/configure_auth.sh --verify-only
bash scripts/diagnose.sh
```

The runtime token is refreshed every time `configure_auth.sh` succeeds.

---

### ISSUE-007 — `-client` scripts default to `skills-backend`, which regular OpenAPI accounts may not access

**Status**: Observed on 2026-04-12 while running Demo 2. Needs future wrapper follow-up.

**Symptom**: After `~/.GTS_AUTHORIZATION` exists and credentials are valid, the `-client` scripts start but every data/file/kb call returns:

```json
{"code":"0000001009","status":false,"msg":"the uri can't be accessed"}
```

**Root cause**: `gangtise-data-client`, `gangtise-file-client`, and `gangtise-kb-client` default `GANGTISE_DOMAIN` to `https://open.gangtise.com/application/skills-backend`. Regular OpenAPI credentials can authenticate and may have RAG/data/file scope, but are not allowed to call this `skills-backend` route. The legacy openapi skills use public endpoints such as `open-data` and `open-quote`, and worked for the same account.

**Impact**: For live workshop work, `--preset full` is safer than `--preset workshop`: the full preset installs both `-client` and legacy openapi variants. If the client line is blocked by `skills-backend`, use the legacy line.

**Observed working commands**:

```bash
python3 ~/.local/share/gangtise-copilot/skills/gangtise-data/scripts/quote.py \
  --securities 300750.SZ -sd 2026-03-13 -ed 2026-04-11 --limit 100

python3 ~/.local/share/gangtise-copilot/skills/gangtise-file/scripts/report.py \
  -k 宁德时代 --securities 300750.SZ -sd 2026-03-13 -ed 2026-04-11 -l 8 --rank_type 2

python3 ~/.local/share/gangtise-copilot/skills/gangtise-kb/scripts/kb.py \
  -q "宁德时代 近30天 研报 共识 分歧" -sd 2026-03-13 -ed 2026-04-11 \
  --file-types 研究报告,公司公告,会议纪要,调研纪要,首席观点 -l 8
```

**Repair strategy**:

- For now: install `--preset full`, then prefer legacy `gangtise-data/file/kb` scripts when `-client` scripts return `0000001009`.
- Do not patch upstream scripts silently. A future wrapper revision may add a compatibility runner or detect this condition in `diagnose.sh`.
- Record this fallback in demo `run-log.md` so a future agent does not waste time debugging valid credentials.

## Adding new issues to this file

When you discover a new issue worth capturing:

1. Assign the next sequential `ISSUE-<NNN>` number.
2. Fill in the same schema: symptom, root cause, impact, plain-language explanation, at least one repair strategy with idempotent commands.
3. Update `scripts/diagnose.sh` if the issue has a detectable symptom — add a new `scan_issue_NNN` function that returns a distinct status code.
4. **Do not vendor or patch upstream files** as part of a repair. Keep all fixes at the wrapper layer or as documented runtime commands the user executes with explicit consent.

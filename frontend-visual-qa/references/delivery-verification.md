---
name: delivery-verification
description: Compare selected deployed HTTP resources with a frozen release when freshness or deployment is part of a UI acceptance claim.
---

# Verify the selected delivery

The agent preparing acceptance owns this check. Use the project's selected,
already-published artifact as the expected source. Prepare its hashes and stable
component facts before reading the running target; copying the running values
into the expected manifest can certify the old deployment.

Include the changed embedded component's own assets or version facts. Matching
the parent HTML/JS is insufficient when a reader, iframe or independent bundle
is served separately. Select the complete relevant resource set through the
project's release owner; this probe cannot discover or authenticate that set.

## Reuse a build from another source ref

When the release owner reuses a compiled build, record its build ref separately
from the selected published artifact ref in the task's provenance evidence.
Keep the HTTP manifest's `artifact_ref` bound to the selected delivery; matching
HTTP bytes does not establish which source produced them.

The release owner must establish that the production inputs are equivalent:
source, build configuration, dependency lock, generated inputs and relevant
environment. A test-file suffix alone is insufficient: imports, globs or build
plugins may consume that file. If equivalence is unproven, rebuild the selected
artifact or keep source provenance unverified. Then perform the normal resource
readback and affected rendered journey; this reference does not run a build or
grant deployment permission.

| Synthetic provenance case | Disposition |
|---|---|
| Build A and published B differ only in an extra test; the release owner proves it is excluded from all production inputs | Reuse is supportable; retain both refs and the equivalence evidence |
| Only a `.test` file changed, but a production glob consumes it or its participation is unknown | Reuse is unsupported by that filename; rebuild or retain the unresolved provenance |

## Manifest

Use a private task file outside the Skill package. In this synthetic example,
replace the commit and expected values from the selected artifact.

```json
{
  "schema_version": 1,
  "artifact_ref": "0123456789abcdef0123456789abcdef01234567",
  "base_url": "http://127.0.0.1:9000/",
  "resources": [
    {"path": "/assets/app.js", "sha256": "<64 lowercase hex characters>"},
    {"path": "/api/component/status", "json_fields": {"available": true, "version": "release-2"}}
  ]
}
```

Each resource uses exactly one of `sha256` or `json_fields`. Paths are absolute
within the given origin and omit queries/fragments. JSON fields are literal
top-level keys with finite scalar values. Missing keys differ from explicit
null; empty field sets and zero-resource manifests are invalid. Use stable
release facts, not observation timestamps or changing task counts.

Run from the resolved Skill directory:

```bash
uv run --no-project python scripts/verify_delivery.py --manifest <private-manifest.json>
```

Read the JSON status and exit code together:

| Exit | Status | Meaning |
|---|---|---|
| 0 | `matched` | Every supplied byte digest and JSON field matched |
| 1 | `mismatched` | At least one observed resource or required field differed; unknown observations may also be listed |
| 2 | `unprovable` / `invalid` | Observation incomplete or input invalid; never a successful delivery claim |

The report fingerprints target/resource paths and field values rather than
printing response bodies. Match fingerprints to the private manifest when
investigating a failure. The timeout applies per blocking HTTP operation,
not to the entire run; `--max-bytes` bounds each response body.

## One current entry and retired links

Use this route when a hosted report or draft has competing pickup links. Resolve
one current entry from the user or artifact owner; do not choose by newest port,
page title or HTTP status. Freeze the selected local entry's bytes and expected
relative resources before checking the server. Preserve real directory names
and the HTML's literal relative references; verify their exact resolved files.
Keep customer files, URLs, manifests and screenshots in private task evidence.
For a renamed historical reading copy, bind its download links to that historical
HTML/text pair. Preserve the original bytes before repairing references; a newer
draft that returns 200 is a different content identity, even with a similar name.

Retain schema 1 for commit-bound releases. For an independently selected local
HTML artifact without a commit, use schema 2 in the same command; never invent
an `artifact_ref`. Set `artifact_sha256` to the selected entry file's SHA-256 and
include that same digest in its one matching resource. This identifies the local
entry, not its author, source revision or full dependency closure. Add hashes for
the relevant linked files/assets from their selected local sources. Record that
selection, exclusions and the manifest's own hash in the task evidence; do not
derive expectations from the running endpoint.

This synthetic example uses the HTML and SVG bytes in `test_verify_delivery.py`:

```json
{
  "schema_version": 2,
  "artifact_sha256": "553567a09235e2d447549f417920f6d2dcb24caba5304256f93d42e2e58cca68",
  "base_url": "https://current.example.test/",
  "resources": [
    {"path": "/report.html", "sha256": "553567a09235e2d447549f417920f6d2dcb24caba5304256f93d42e2e58cca68"},
    {"path": "/images/hero.svg", "sha256": "ed47ae055cff6e1a10d6246b90ec523dc78ec306a226b751ef253e16db2e5717"}
  ],
  "handoff": {
    "current_url": "https://current.example.test/report.html",
    "legacy_urls": ["https://old.example.test/report.html"]
  }
}
```

Supply encoded absolute URLs. Schema 2 resource paths may include a query;
match it exactly to `current_url`. Fragments remain browser-state evidence.
An explicit empty `legacy_urls` list declares a current-only check; missing,
null or blank URLs are invalid. Each declared old URL must redirect through only
declared aliases to the exact current entry. Cross-origin/port hops are allowed
only along that explicit set. Loops, an unlisted destination, a login redirect,
or a current entry that redirects are failures. A retired URL returning 200 at
its own address fails the unique-entry contract even if its bytes match.

The probe separately GETs and hashes the current entry and every old entry's
final body. Read `checked_entrypoints`, each redirect observation, resource
coverage, status and exit code together. A 200 response carrying another draft,
an old body or a login form mismatches; unavailable resources remain unprovable.
Default schema 1 cross-origin refusal remains unchanged.

Open both the current and declared old links in the authorized real browser.
Read the final URL, visible document/variant identity and distinctive expected
content from the selected source, rather than trusting `<title>` alone. Exercise
the affected selection/reading path, inspect its images at the actual reading
size and open any screenshot used as evidence. Check image decoding and required
relative resources separately: matching HTML alone cannot prove them. Reuse
unchanged same-target/state evidence rather than recapturing the whole page.
Record page availability and content identity separately from adoption,
approval or publication; a usable draft page proves none of those decisions.

Run the synthetic positive/negative transport controls without a live service:

```bash
python3 -m unittest discover -s tests -p test_verify_delivery.py
```

Treat those controls as probe calibration. Complete the real-browser gate above
for the actual handoff; do not promote synthetic success into recipient evidence.

## Completion and recovery

### A deployment changes during acceptance

Synthetic example: the frozen expectation names release A, but a concurrent
authorized rollout makes the target serve B. Preserve A's expected manifest,
the loaded page's identity and the mismatch/partial observations; do not rewrite
them into a pass or roll the other publisher back. Resolve B through the release
owner and independently freeze its published artifact and build inputs before
creating a separately named B expectation. Reload the canonical target, verify
the affected resources, then rerun the affected rendered journey. Unchanged
checks with unchanged inputs remain reusable. If B cannot be established or
the target keeps changing, retain partial status and the precise unresolved
identity; live values copied into a new expectation do not resolve it.

The command only issues GETs, keeps ordinary proxy/TLS behavior, refuses
cross-origin redirects except the schema 2 aliases explicitly bound above, and
does not deploy, restart, sign in or change accounts.
Encoded responses and login-dependent resources require the existing same-state
browser or product-specific readback; an unsupported probe must not narrow the
Skill's existing browser/native coverage.

Run after the authorized rollout is settled. A match is data-plane identity
evidence, not an atomic cross-resource snapshot, source provenance, pixel review
or business acceptance. Continue the canonical journey and inspect its actual
screenshots. If the deployment is authorized and still pending, continue through
the project's owning procedure; if occupied or unauthorized, report the exact
remaining result and recovery condition without claiming overall completion.

For an expansion or transition, capture after the expected content renders and
inspect that content in the image. DOM `open=true`, a screenshot filename or a
completed click cannot prove visible input. Discard a pre-transition or stale
shot as acceptance evidence and give its replacement a distinct path.

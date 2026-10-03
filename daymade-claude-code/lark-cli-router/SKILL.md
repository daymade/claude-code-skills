---
name: lark-cli-router
description: >-
  Routes any Feishu/Lark/Doubao operation through the version-matched lark-cli domain guide embedded
  in the installed CLI, then executes and verifies the task. Use for 飞书/Lark/Doubao docs, drive,
  sheets, Base, wiki, minutes, meetings, calendar, IM, mail, tasks, approval, apps, auth/scope,
  resource URLs or tokens, and lark-cli troubleshooting. This is the single Lark entry point; use
  ima-copilot instead for Tencent IMA.
metadata:
  requires:
    bins: ["lark-cli"]
---

# Lark CLI Router

Use this as the only model-visible Lark entry point. The CLI's embedded `lark-*`
guides are the version-synced source of truth; this router selects and loads them
instead of copying their domain instructions into another static catalog.

## Boundaries

- Tencent IMA is a different product. Route IMA notes or knowledge-base tasks to
  `ima-skill`, not here.
- Do not load all Lark guides. Select the smallest matching guide set for the
  current task.
- Do not bypass `lark-cli` with browser automation, raw `curl`, or guessed API
  contracts while the CLI or one of its embedded guides covers the task.

## Workflow

### 1. Confirm the runtime

Run `lark-cli --version`. If the binary is absent, fail visibly and report that
`lark-cli` is required; do not invent another transport or confuse the separate
Skill-install command with a CLI-binary installer.

Set `LARK_CLI_NO_PROXY=1` for every invocation in this environment. When stable
machine-readable JSON is needed, also set
`LARKSUITE_CLI_NO_UPDATE_NOTIFIER=1` and
`LARKSUITE_CLI_NO_SKILLS_NOTIFIER=1` so notices do not pollute the result.

### 2. Select the embedded guide

Run `lark-cli skills list --json`. Match the user's intent and any URL path or
token to the returned `name`, `description`, and `metadata.cliHelp`.

Do not derive the CLI domain by stripping `lark-` from the guide name: exceptions
exist, and `metadata.cliHelp` or the guide itself is authoritative. These
high-confusion routes need explicit care:

| Intent | Guide |
|---|---|
| auth, login, profile identity, missing scope, user vs bot | `lark-shared` |
| `/wiki/` document content | `lark-doc` |
| wiki space, membership, or node hierarchy | `lark-wiki` |
| future meeting or room scheduling | `lark-calendar` |
| ended meeting search, participants, or meeting artifacts | `lark-vc` |
| known `note_id` | `lark-note` |
| `minute_token`, 妙记 content, or audio-to-minutes | `lark-minutes` |
| live meeting participation or in-meeting events | `lark-vc-agent` |
| file upload, download, move, permissions, metadata, or Office import | `lark-drive` |

For ordinary docs, sheets, Base, slides, mail, IM, tasks, approval, apps, and
other domains, the live `skills list` descriptions are the routing table. A
multi-domain request may select a workflow guide or a small ordered set of domain
guides.

### 3. Load the selected instructions completely

Read the selected guide before acting:

```bash
lark-cli skills read lark-doc
lark-cli skills read lark-doc/references/lark-doc-fetch.md
```

The first form prints the guide's `SKILL.md`; the second reads a referenced file.
Read every file the selected guide marks required for the current branch.

Embedded reads reject `..`. Rebase a sibling pointer such as
`../lark-whiteboard/references/x.md` to:

```bash
lark-cli skills read lark-whiteboard/references/x.md
```

Always try `lark-cli skills read` first for Markdown and reference files. If it
returns `reference ... not found`, resolve that exact guide-relative path under
`~/.agents/skills/<guide-name>/`. Before the first such fallback for a guide,
confirm with the host's SHA-256 tool that its installed `SKILL.md` is byte-identical
to `lark-cli skills read <guide-name>`; a mismatch must fail visibly and trigger a
bundle refresh. This explicitly keeps `lark-apps/creative-design/` reachable even
though the current binary does not embed it.

Machine resources under `scripts/` or `assets/` are never embedded, so resolve
them directly in the same installed bundle. If a required file is absent, stop
and report that the disk bundle must be installed or refreshed; do not fabricate
a replacement.

### 4. Inspect, execute, and verify

1. Treat `metadata.cliHelp` as a help recipe, not always a literal command. Run its
   concrete commands; resolve any placeholder from the loaded guide first. If the
   field is absent, use the guide's own commands or the selected domain's `--help`.
2. Prefer a matching `+shortcut`; otherwise use a typed resource command.
3. Before a typed call whose parameters are not already explicit in the guide,
   run `lark-cli schema <service.resource.method>`.
4. Use `lark-cli api` only as the documented escape hatch when no shortcut or
   typed command covers the endpoint.
5. Preserve any explicitly supplied `--profile`; never guess a profile or identity.
   Use `lark-cli whoami` when identity is material or ambiguous.
   Before a read through another existing profile, confirm that it belongs to the
   requesting user and that the profile/read is already authorized. Keep
   `--profile` explicit; do not switch the global profile or enumerate unrelated
   accounts. If ownership is unknown, skip that candidate and report the gap.
   Different app-specific openIds alone do not establish different people.
6. For writes, use `--dry-run` when the command supports a useful preview. If a
   high-risk write exits `10`, present the proposed action and wait for explicit
   human confirmation; never append `--yes` automatically.
7. Separate transport completion from business success. Process exit `0` alone
   does not prove the requested result; for JSON output, inspect `ok` and errors
   as well. Outer `ok == true` does not prove each item succeeded. Do not test for
   a top-level `code == 0`; interpret domain results using the loaded guide.
   For batches, reconcile each requested resource identity with its returned
   item, error and expected result/artifact. Identify missing, duplicate and
   unrequested items; a duplicate never fills a missing request. Count verified
   successes, explicit failures and missing/unknown results against the request
   total, counting each requested identity at most once; report anomalies
   separately, and report `partial` whenever any requested result is not verified.
   For example, three requested items with one verified
   result, one permission error and one missing item are `partial: 1/3 successful,
   1 failed, 1 missing`, even with exit `0` and outer `ok == true`.
8. After a write, follow the selected guide's domain-specific verification
   contract. If it defines none, perform the narrowest independent read that proves
   the requested state changed. A guide that explicitly forbids an opportunistic
   second query takes precedence. Report partial results or missing coverage.

On authentication or permission errors, load `lark-shared` and its embedded
`lark-shared/references/lark-shared-identity-and-permissions.md`. Follow its
user/bot and missing-scope branch, and interpret the current CLI's auth status:

```bash
lark-cli --profile "<authorized-profile>" auth status --json
```

Do not classify `needs_refresh` as unusable login. When the status says it will
auto-refresh on the next user API call, an already-authorized ordinary read may
proceed with explicit `--profile` and `--as user`; let the CLI renew normally.
Do not initiate login, new grants/scopes or manual credential writes merely to
handle that state. A ready token still does not prove target read permission.

Scope an actual target read-permission denial to its target/profile/identity and
stop that route. Do not turn authentication failures or that refusal into retry
loops or browser/raw-API fallbacks.
It does not prove that every other already-authorized profile of the requesting
user is denied. Assess another profile only after the ownership/authorization
check above, and verify its own target result rather than assuming access.

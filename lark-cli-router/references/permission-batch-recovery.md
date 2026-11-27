# Resume an authorized permission batch

Use this procedure for page-member permission updates already authorized by the
user. Load the installed CLI version's Drive/Wiki and identity guides first;
take commands, supported fields, retry instructions and limits from those guides
and actual help/schema. Use the router's documented API escape hatch only when
the selected shortcut or typed command cannot express the authorized operation.

## Bind and probe the operation

Keep the explicit profile, user/organization binding, target page identity and
authorized audience fixed. Read a representative page's current collaborators,
sharing settings and original ownership, then execute the smallest authorized
update and independently read it back before expanding the batch. A collaborator
with management permission is not necessarily the original owner. Preserve the
member ID/type, permission scope and role unless changing them is authorized;
do not replace an update with delete-and-add or ownership transfer.

Do not use `drive +member-add` to change an already-present collaborator's role
(for example, upgrading `view` to `edit`): it can return `ok: true` with the
requested `perm` while leaving the collaborator's actual permission unchanged.
To update an existing collaborator's permission, use the router's documented
`lark-cli api PUT /open-apis/drive/v1/permissions/{token}/members/{member_id}`
escape hatch (passing the resource `type` in `--params` and `member_type`,
`perm`, and `type` in `--data`), then confirm the effective role with
`+member-list` readback.

## Cross-tenant grants and export/copy settings

Cross-tenant individual grants via `drive +member-add` require the source account
and the external recipient to be direct external contacts; otherwise the API can
fail (`1063002` or partial success) even when both users share an external group.
Inspect source-tenant contact reachability before proposing a closed-link
named-collaborator rollout, and surface the operational choice up front:

- **Two-hop hub bridge (preferred when an external hub contact exists):** grant a
  hub account that is already a direct external contact `full_access` on the
  source resource (with `external_access=true` and `share_entity="anyone"`), then
  use the hub profile to add or upgrade in-tenant teammates without adding every
  teammate as a direct external contact.
- **Direct external contacts or explicitly authorized link scope:** either add
  the required external contacts first, or—only when the user explicitly approves
  the exposure boundary for that audience—set link sharing (for example,
  `anyone_editable`). Never broaden to internet link sharing silently as a
  workaround for `1063002`.

When opening copy/export/download alongside edit permissions, pass query
parameters via `--params '{"type":"<resource-type>"}'` (never embed `?type=...`
in the `lark-cli api` path). `PATCH /open-apis/drive/v1/permissions/{token}/public`
with `security_entity` often updates Drive v2 `copy_entity` together, but v1
success alone does not establish v2 parity: always read back
`GET /open-apis/drive/v2/permissions/{token}/public` and patch v2 `copy_entity`
only if it still mismatches.

## Retain per-target evidence

Key each action by page, member and permission scope. Retain its observed before
state, intended change, attempt outcome and independent readback. Save exit code
and both stdout and stderr; structured errors can be emitted on stderr. Mark an
action complete only when the readback matches its exact identity and intended
permission. Derive progress from these records when reporting; do not maintain a
separate success counter as authoritative state.

At continuation, reconcile incomplete or uncertain actions with current remote
state. Skip unchanged verified completions. If a write may have succeeded but
readback failed, read first; do not infer failure from the missing receipt or
replay the entire batch. Later manual permission changes invalidate the affected
old plan and need reconciliation against current authorization.

## Classify the failure before continuing

| Observed failure | Recovery and stop boundary |
|---|---|
| API rate limit | Honor documented retry timing; otherwise use bounded backoff and reduce concurrency. Resume only unverified actions. |
| Transient network or TLS timeout | Retain the uncertain outcome, reconcile by reading, then retry the still-needed authorized update within a bounded attempt budget. Persistent transport failure follows the network owner. |
| Missing OAuth scope (for example, `99991679` on `PUT .../members/{id}`) | Classify strictly as a scope gap, never as a `not_owner` / `permission_denied` skip. Use the identity guide's incremental authorization route and [account-bound recovery](auth-recovery.md), then verify the same account and original operation. Never use delete-and-add on an original owner; only if the user explicitly authorizes a temporary fallback for upgrading a non-owner collaborator on a profile holding `member:delete`/`create` without `member:update`, record the brief revoke window and confirm via `+member-list` readback. |
| Resource permission denial or explicit refusal | Stop that target/profile route. Do not treat it as a transient error or switch identities, transport or API form to bypass it. |
| Managed launcher's source-binding rejection | Stop dispatch; locate the install/executor owner and reconcile the reviewed source through its normal release procedure. Do not edit trust records, call a vendor binary directly or change transport to bypass the rejection. |
| Changed page, space, member or permission scope; invalid response/schema | Stop the affected actions and rebuild their plan from verified current state and supported interface. Keep unrelated completed evidence. |
| `drive +member-add` returns `ok: true` but `+member-list` readback still shows the prior role | The collaborator already existed and `+member-add` did not update their role. Switch to `lark-cli api PUT /open-apis/drive/v1/permissions/{token}/members/{member_id}` with explicit `--params` and `--data`, then verify via `+member-list` readback. |

If a needed condition remains unavailable, report the precise incomplete targets
and recovery condition. Follow the router's per-item reconciliation and the
selected domain's verification contract before calling the batch complete.

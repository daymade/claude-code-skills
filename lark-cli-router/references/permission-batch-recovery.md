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
| Missing OAuth scope | Use the identity guide's incremental authorization route and [account-bound recovery](auth-recovery.md). Verify the same account and original operation afterward. |
| Resource permission denial or explicit refusal | Stop that target/profile route. Do not treat it as a transient error or switch identities, transport or API form to bypass it. |
| Managed launcher's source-binding rejection | Stop dispatch; locate the install/executor owner and reconcile the reviewed source through its normal release procedure. Do not edit trust records, call a vendor binary directly or change transport to bypass the rejection. |
| Changed page, space, member or permission scope; invalid response/schema | Stop the affected actions and rebuild their plan from verified current state and supported interface. Keep unrelated completed evidence. |

If a needed condition remains unavailable, report the precise incomplete targets
and recovery condition. Follow the router's per-item reconciliation and the
selected domain's verification contract before calling the batch complete.

# Keychain dialogs that block the desktop

Use this branch after observing a Keychain access dialog or confirming a Keychain
access failure through the original operation. Preserve the reported symptom;
distinguish a normal consent request, an inoperable window and a background failure
without a dialog. A password field alone does not decide which case applies.

## Bind the request and the intended result

Record the visible requesting app, item label, requested action and current
window state without extracting the stored credential. Identify the actual
dialog owner through current process/window evidence; do not assume every
system dialog belongs to `UserNotificationCenter` or `SecurityAgent`.

Separate the requested outcomes: removing an obstructing window, granting item
access, and restoring the original application operation require different
evidence. Do not reset TCC, reset a keychain, change item access controls or
restart the requesting application merely to remove a window.

When standing authorization covers the purpose and a usable credential is already
available, the executing agent first follows
[authorized owner recovery](#recover-through-an-authorized-credential-owner).
An unlocated or unregistered provider is discovery work, not a reason to ask the
person to enter an already supplied password again. Request only a genuinely
missing credential, permission decision or host-required human action after
checking the authorized supported routes; never request a password in chat.
Keep manual entry available when the person chooses it or the host requires it.
Explain the selected button only when needed: Apple documents
one-time access, persistent access and denial as different choices in its
[Keychain access guide](https://support.apple.com/guide/keychain-access/if-youre-asked-for-access-to-your-keychain-kyca1243/mac).
Do not choose persistent access as a troubleshooting default. After the person
or agent acts, inspect the original request's result before retrying it.

## Diagnose an inoperable window without granting access

Use permitted passive observation and read-only process diagnostics first. A
process found waiting in an application event loop does not establish a deadlock
or prove that its window accepts user input. A tool's refusal to automate a
protected dialog is not evidence that the dialog is frozen.

Respect host restrictions and GUI ownership. Do not use another input tool,
process signals or a screenshot path to bypass a protected-interface refusal.
Consider process termination only as a separately authorized cancellation of an
observed obstructing request, where the host permits process management.

<a id="recover-through-an-authorized-registered-provider"></a>

## Recover through an authorized credential owner

Use the task's existing supported credential/session provider or native entry when
standing authorization covers this credential and purpose. Verify that entry's
inputs and behavior through its current owning configuration and implementation;
registration alone neither grants authority nor determines whether recovery is
possible. Do not create another credential store or invent a replacement runner.
This route restores a same-session consumer blocked on Keychain access; it never
creates a grant and never widens an existing one.

1. Locate the supported entry through the task's owning configuration, credential
   source or procedure. A missing default file or provider registration leaves the
   owner unresolved; continue authorized discovery before declaring a human
   dependency. Reuse an already supplied usable credential through its owner;
   do not ask for the same unchanged authorization or password again.

2. Verify the match before invoking: exact machine, account, keychain and security
   context, and that the authorization covers this use of this credential. Any
   mismatch stops this route and keeps the state unknown. Distinguish a locked
   keychain from item ACL/user-presence requirements, a changed signer/requester,
   a different security session and a pending call without a terminal result;
   knowing the password does not establish item access.

3. Invoke the matched owner through its supported execution entry only. Do not pass secret
   values through command arguments, logs or general settings files, and do not copy
   the credential into the task record.

4. Run recovery and the dependent consumer in the security session required by
   that entry. An unlock in another SSH, login or service session does not
   establish access for the blocked requester. Distinguish four states and report them separately:
   the keychain is unlocked, the named item is actually readable, the original
   pending request's state, and the final business result. Only the named protected
   operation succeeding in the original requester and context closes the
   corresponding recovery; an unlock never establishes an ACL, TCC or system-wide
   permission repair.

5. If the original request is still running, do not start a duplicate write
   operation. Wait for a bounded terminal state, inspect any completed side effect,
   and only then decide whether a single retry is warranted.

6. Keep every human path intact: manual password entry, a new explicit grant and
   cancellation of the dialog remain supported routes. If authorized discovery
   establishes that no usable supported entry is available, report that exact
   missing prerequisite. A match failure or native/host permission refusal ends
   this route: keep the state unknown, do not broaden permissions, do not use
   another principal's key or session, and do not control a protected window the
   host refused. One application's recovery does not establish another's cause or
   access; verify each affected original operation.

## Cancel the obstructing dialog only within explicit authority

The executing agent checks the exact target, concurrent authorization work,
expected cancellation effects and a recovery path before offering termination.
Preserve in-flight work or wait when its safety is unresolved. For a shared
`SecurityAgent`, obtain explicit permission for that exact target and explain
that other pending authorization requests may also be cancelled. A generic
permission-repair request or a refused UI call does not supply that permission.

1. Immediately before sending a signal, read the PID, full executable path and
   start time. Bind them to the observed dialog owner. Keep unknown ownership
   unresolved rather than selecting an arbitrary process with a matching name.

   ```bash
   ps -p <confirmed-pid> -o pid=,ppid=,lstart=,comm=
   ```

2. With that authority and preserved work, request normal termination of the
   exact process and record the action time. Never use a process-name/group kill.
   A successful signal command proves neither exit nor removal of the window.

3. Observe process identity and the actual screen within the task's bounded
   wait. If the same process and window remain, recheck the full path and start
   time immediately before considering force termination. Use it only if the
   authorization covers force termination and cancellation effects remain
   acceptable. Otherwise keep that step pending. Do not broaden the target to
   the requesting app, terminal, `securityd` or other services.

4. Read back the process state and the real screen after the action. A new PID
   is a new process generation: do not chase it with repeated kills. If the
   dialog returns, investigate the requesting operation instead of repeating
   termination automatically.

Keep this a manual, bounded recovery branch. The Skill does not install a
watchdog or enforce authorization mechanically.

## Verify the requested outcome and stop at its boundary

For obstruction removal, require a permitted current screenshot showing the
window is gone; a signal exit code or process disappearance is insufficient.
For permission repair, also inspect the original request through its task-owned
handle and verify the named operation in the same requester/context. Do not
duplicate an operation whose prior result or side effect is still unknown.

Report each outcome separately. If only the window was removed, say that access
and application recovery remain unverified and the cause is unknown. Do not
re-trigger unrelated requests solely to improve that report.

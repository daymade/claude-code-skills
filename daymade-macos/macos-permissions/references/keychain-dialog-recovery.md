# Keychain dialogs that block the desktop

Use this branch after observing a Keychain access dialog. Preserve the reported
symptom and distinguish a normal request for consent from a window the user
cannot operate. A password field alone does not decide which case applies.

## Bind the request and the intended result

Record the visible requesting app, item label, requested action and current
window state without extracting the stored credential. Identify the actual
dialog owner through current process/window evidence; do not assume every
system dialog belongs to `UserNotificationCenter` or `SecurityAgent`.

Separate the requested outcomes: removing an obstructing window, granting item
access, and restoring the original application operation require different
evidence. Do not reset TCC, reset a keychain, change item access controls or
restart the requesting application merely to remove a window.

For an operable consent prompt, leave password entry and any required permission
decision to the person under the current host contract. Never request the
password in chat. Explain the selected button only when needed: Apple documents
one-time access, persistent access and denial as different choices in its
[Keychain access guide](https://support.apple.com/guide/keychain-access/if-youre-asked-for-access-to-your-keychain-kyca1243/mac).
Do not choose persistent access as a troubleshooting default. After the person
acts, inspect the original request's result before retrying it.

## Diagnose an inoperable window without granting access

Use permitted passive observation and read-only process diagnostics first. A
process found waiting in an application event loop does not establish a deadlock
or prove that its window accepts user input. A tool's refusal to automate a
protected dialog is not evidence that the dialog is frozen.

Respect host restrictions and GUI ownership. Do not use another input tool,
process signals or a screenshot path to bypass a protected-interface refusal.
Consider process termination only as a separately authorized cancellation of an
observed obstructing request, where the host permits process management.

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

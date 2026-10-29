# Diagnose Local Network access on macOS

Use this branch for a Local Network alert or an app-specific failure to connect to
or discover a local device. Treat `No route to host`, a timeout, and missing
Bonjour results as symptoms, not permission diagnoses. The executing agent makes
the observation and authorization decisions below; this reference adds no automatic
permission grant or process-lifecycle control.

## Bind the failed request

Reuse the original task-owned request and retained result before launching another
attempt. Record the executable or responsible app, user, launch context, destination,
observation time, and exact failure. Distinguish a Terminal/SSH command from a
long-running `launchd` agent. Keep an existing request within its deadline; an
unknown terminal state is not permission to duplicate a business action.

Compare a bounded reachability probe from the same Mac to the same current endpoint
only when it can distinguish the failure. For example, a TCP probe succeeding while
the existing ADB server fails is a process-context difference; it proves neither
that the route is broken nor that Local Network access caused the failure. Match
the actual server's executable and launch context, not just the SSH client issuing
its command.

Apple's [TN3179](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)
documents Local Network privacy on macOS 15 and later. Terminal/SSH command-line
tools and their children are automatically allowed; a `launchd` agent does not
inherit the daemon exception. Access state is per user, and responsible-code
attribution can associate a helper's request with its app. Do not substitute a
different launcher, root execution or a daemon for the failed requester to make
the check pass.

## Observe the permission in the correct user session

Use the host's permitted native observation/control path to read the actual alert
or **System Settings → Privacy & Security → Local Network**, as described in
[Apple's user guide](https://support.apple.com/guide/mac-help/mchla4f49138/mac).
Bind the displayed app to the failed request before changing its access. A lock
screen or an SSH session does not prove that no permission alert is pending in
the console session. Use an already-authorized unlock/control route when one
exists; otherwise leave UI observation unverified and continue independent work.
Respect host refusals and resource ownership rather than switching input tools
or restoring a foreground another user has taken over.

When the matching request or setting is observed, handle it only within the
current task's permission-repair authorization. An explicit owner denial remains
in force. If the requester, user session or permission state cannot be established,
report those fields as unknown. Do not add Full Disk Access, write TCC databases,
reset unrelated grants, or apply system-wide network exceptions as a fallback.

## Verify through the failed requester

After any authorized permission action, read the original request's terminal
result. If it ended, issue one bounded, safe check through the same requester and
launch context; preserve the same target identity and endpoint. A new Terminal
process succeeding, the alert disappearing, or a settings switch turning on is
not that check. Keep expired requests separate from fresh attempts and reconcile
possible completed side effects before repeating a business operation.

For ADB, reuse the same server and target binding; let the Android workflow verify
the physical device and Android user after transport succeeds. A TCP connection
does not establish device identity or a complete recovery journey.

Report the observed permission state, the original-context result, and any missing
evidence separately. If access now works without a witnessed permission correction,
report current accessibility with the earlier cause unknown. If the same request
still fails after an observed grant, retain that failure and return to the owning
network/application diagnosis. Stop changing permissions when the required
original-context check succeeds; do not restart a shared service merely to clear
an old error.

# Window-helper permission diagnostics

Use this procedure when the window-ID helper fails or prints a permission hint.
Keep this file specific to the helper; use
[macos-permissions](../../macos-permissions/SKILL.md) for general dialog classification,
TCC attribution, grant decisions and protected-operation recovery.

## Interpret the helper result

The executing agent reads the original invocation and its actual output first.
A manual permission hint prints guidance for the requested resource and exits
without enumerating windows. It does not test whether permission is denied.
An enumeration failure or missing window title alone does not establish TCC as
the cause; keep the required observation and current result explicit.

Treat invoker paths, runtime names and identity clues as execution context, not
a list of verified grant targets. A script path or a bundled-app path does not
prove which process macOS attributes the protected operation to.

## Select the next action

- If the original operation now works, stop permission changes and continue it;
  keep the earlier cause unknown.
- If the result still needs permission diagnosis, follow the permission owner's
  [request reproduction and attribution](../../macos-permissions/SKILL.md#reproduce-the-reported-denial-first).
  Do not grant to Terminal, Swift or another helper merely because it appears
  in this script's output, and do not require packaging as an `.app` to diagnose it.
- Open the suggested Settings pane only after that diagnosis selects the
  resource/requester and foreground access is authorized. After any grant,
  follow the owner's [request lifecycle](../../macos-permissions/SKILL.md#after-a-grant-or-reset)
  before retrying or considering a relaunch. Preserve shared in-flight work.

Close this helper-diagnosis step with the original result, established identity
or remaining identity gap, and the selected next action. A printed hint, an
enabled Settings switch or a dismissed window does not verify the operation.

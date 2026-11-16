# Headless profile verification

Use this procedure after an authorized provider configuration change or when
a headless verification is denied or appears to succeed without a tool result.
It verifies the selected non-secret pin and tested invocation, not every provider
or permission mode. Stop when its actual result is observed; a denied or missing
result remains incomplete.

Preparing the scratch file requires task write authorization. For a read-only
request, reuse an existing reviewed probe or report that execution is unavailable;
do not substitute an unverified inline command or broaden permissions.

Verify that a new non-secret env pin reaches Bash in a real headless session.
Use the profile launcher so provider settings and credential binding follow their
existing owner. For an authorized effort-pin check whose configured expected
value is `max`, put this condition in a reviewed task-owned scratch file such as
`pin_probe.py` (Python is already a profile-manager prerequisite):

```python
import os
print(os.environ.get("CLAUDE_CODE_EFFORT_LEVEL") == "max")
```

Use that file's literal absolute path in both the approval and prompt:

```bash
claude-profile <name> --print --verbose --output-format stream-json \
  --permission-mode manual \
  --allowedTools 'Bash(python3 /absolute/task/pin_probe.py)' \
  -- 'Run exactly python3 /absolute/task/pin_probe.py via Bash; report whether its actual output is True.'
```

Read the intended non-secret value from the provider settings first; change the
condition when it differs. Keep this temporary probe with local task evidence,
outside the distributed Skill, and preserve its reviewed bytes during the run.
The probe emits only `True` or `False`, never environment
values. Only literal `True` in the successful tool result establishes a match;
`False`, missing/empty pins, empty output, denial or a failed tool leave the pin
unverified. Never print credentials: verify them through a real request using
the credential owner in [setup step 4](../SKILL.md#one-click-setup-workflow). For structured
capture, use [the native-command entry](../SKILL.md#callers-that-capture-native-structured-output).

In `--print`, an action needing approval can be denied without an interactive
prompt. An unavailable auto-mode check or a zero process exit does not establish
that Bash ran. Empty success-looking tool feedback is insufficient too. Inspect
the actual condition output rather than inferring a match from process or tool
exit alone. Do not repair a test by granting blanket shell access or changing
global permission defaults. Use the current documented
[permission modes](https://code.claude.com/docs/en/permission-modes).

For file-scoped approvals, use `Edit(//absolute/path)` for both Edit and Write;
`Edit(/path)` anchors at the settings source, and `Write(path)` is not a matching
file permission rule. Match shell commands exactly, including interpreter,
arguments and absolute versus relative paths. Preserve existing deny/ask rules;
see [permission rule syntax](https://code.claude.com/docs/en/permissions).

Record the native executable/version, launch entry, profile/settings source,
model, permission mode, installed consumer and exact approved command in local
verification evidence, excluding secrets. A passing named-command test proves
that invocation's env delivery; it does not repair or validate a different
permission mode or the user's unchanged daily launcher. Report those separately.

#!/usr/bin/env python3
"""Execute the installer command generators without installing any plugins."""

import errno
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import tempfile
import time
import unittest

if os.name == "posix":
    import pty


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
)
MARKETPLACE = MANIFEST["name"]
REGISTERED = {plugin["name"] for plugin in MANIFEST["plugins"]}
FEATURED = [
    "daymade-skill",
    "github-ops",
    "daymade-docs",
    "daymade-claude-code",
    "teams-channel-post-writer",
    "repomix-unmixer",
    "llm-icon-finder",
]
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
BASH = shutil.which("bash")
POWERSHELL = os.environ.get("POWERSHELL_EXE") or shutil.which("pwsh")


class InstallerContract:
    """Apply the same output and no-install contract to each real script."""

    executable = None
    script = None

    def setUp(self):
        if not self.executable:
            self.skipTest(f"{self.script} runtime is unavailable")

    def run_installer(
        self, replies=(), *, invocation="file", expected_returncode=0,
        claude_available=True, caller_probe=False, strict_mode=False,
        custom_write_error=False, redirected_input="", host_selection=None,
    ):
        with tempfile.TemporaryDirectory(prefix="installer-test-") as directory:
            sandbox = Path(directory)
            home = sandbox / "home"
            home.mkdir()
            bin_dir = sandbox / "bin"
            bin_dir.mkdir()
            call_log = sandbox / "claude-calls"
            call_log.touch()
            if not claude_available:
                pass
            elif os.name == "nt":
                stub = bin_dir / "claude.cmd"
                stub.write_text(
                    '@echo off\necho %* >> "%CLAUDE_CALL_LOG%"\nexit /b 93\n'
                )
            else:
                stub = bin_dir / "claude"
                stub.write_text(
                    '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CLAUDE_CALL_LOG"\nexit 93\n'
                )
                stub.chmod(0o755)
            if os.name == "posix":
                # Bash needs uname for its platform label; keep PATH otherwise isolated.
                (bin_dir / "uname").symlink_to(shutil.which("uname"))
            environment = {
                key: os.environ[key]
                for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")
                if key in os.environ
            }
            environment.update(
                HOME=str(home),
                USERPROFILE=str(home),
                XDG_CONFIG_HOME=str(home / ".config"),
                XDG_CACHE_HOME=str(home / ".cache"),
                PATH=str(bin_dir),
                TERM="dumb",
                NO_COLOR="1",
                CLAUDE_CALL_LOG=str(call_log),
            )
            command = [self.executable]
            if self.script.endswith(".ps1"):
                command.extend(["-NoLogo", "-NoProfile"])
            source = str(ROOT / self.script).replace("'", "''")
            if caller_probe:
                execute = (
                    f"[IO.File]::ReadAllText('{source}') | Invoke-Expression"
                    if invocation == "console-iex" else f"& '{source}'"
                )
                command.extend([
                    "-Command",
                    self.caller_probe_script(
                        execute, strict_mode=strict_mode,
                        custom_write_error=custom_write_error,
                    ),
                ])
            elif host_selection is not None:
                selection = host_selection.replace("'", "''")
                command.extend([
                    "-Command",
                    "function Read-Host { param($Prompt) "
                    "if ($Prompt -like 'Enter your choice*') { '3' } "
                    f"else {{ '{selection}' }} }}; & '{source}'",
                ])
            elif invocation == "console-iex":
                command.extend([
                    "-Command",
                    f"[IO.File]::ReadAllText('{source}') | Invoke-Expression",
                ])
            else:
                if self.script.endswith(".ps1"):
                    command.append("-File")
                command.append(str(ROOT / self.script))
            if replies or host_selection is not None:
                if os.name != "posix":
                    self.skipTest("interactive installer checks require a POSIX PTY")
                returncode, output = self.run_interactive(
                    command, environment, replies, home
                )
            else:
                completed = subprocess.run(
                    command,
                    input=redirected_input,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=home,
                    env=environment,
                    timeout=20,
                    check=False,
                )
                returncode, output = completed.returncode, completed.stdout
            self.assertEqual(call_log.read_text(), "", "generator invoked claude")
            self.record_log(invocation, returncode, output)
            self.assertEqual(returncode, expected_returncode, output)
            return ANSI.sub("", output).replace("\r", "")

    def record_log(self, label, returncode, output):
        log_directory = os.environ.get("INSTALLER_TEST_LOG_DIR")
        if log_directory:
            log_path = Path(log_directory)
            log_path.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", prefix=f"{self.id()}-{label}-",
                suffix=".log", dir=log_path, delete=False,
            ) as log:
                log.write(f"exit={returncode}\n{output}")

    def printed_download_example(self, output):
        heading = "To run interactively, download and run directly:\n"
        self.assertIn(heading, output)
        block = output.split(heading, 1)[1].split("\n\n", 1)[0]
        return "\n".join(
            line[2:] if line.startswith("  ") else line
            for line in block.splitlines()
        )

    def caller_probe_script(self, execute, *, strict_mode, custom_write_error):
        """Observe the real calling scope after an unmodified File/IEX invocation."""
        strict_setup = "Set-StrictMode -Version Latest" if strict_mode else ""
        error_setup = (
            'function Write-Error { param($Message) throw "CALLER_WRITE_ERROR:$Message" }'
            if custom_write_error else ""
        )
        return f"""
{strict_setup}
{error_setup}
$commands = 'CALLER_COMMANDS'
$plugins = 'CALLER_PLUGINS'
$choice = 'CALLER_CHOICE'
$afterInstall = 'CALLER_AFTER_INSTALL_SENTINEL'
$ErrorActionPreference = 'Stop'
$WarningPreference = 'Continue'
$beforeWriteError = (Get-Command Write-Error).Definition
$caught = $false
$caughtMessage = ''
try {{ {execute} }} catch {{ $caught = $true; $caughtMessage = $_.Exception.Message }}
$sameWriteError = (Get-Command Write-Error).Definition -eq $beforeWriteError
$writeErrorCaught = $false
$writeErrorMessage = ''
try {{ Write-Error 'CALLER_CHECK' -ErrorAction Stop }} catch {{
    $writeErrorCaught = $true
    $writeErrorMessage = $_.Exception.Message
}}
$strictPreserved = $false
try {{ $null = $undefinedInstallerProbeVariable }} catch {{ $strictPreserved = $true }}
$result = [ordered]@{{
    caught = $caught
    caughtMessage = $caughtMessage
    commandsPreserved = ($commands -eq 'CALLER_COMMANDS')
    pluginsPreserved = ($plugins -eq 'CALLER_PLUGINS')
    choicePreserved = ($choice -eq 'CALLER_CHOICE')
    afterInstallPreserved = ($afterInstall -eq 'CALLER_AFTER_INSTALL_SENTINEL')
    sameWriteError = $sameWriteError
    writeErrorCaught = $writeErrorCaught
    writeErrorMessage = $writeErrorMessage
    errorPreference = [string]$ErrorActionPreference
    warningPreference = [string]$WarningPreference
    strictPreserved = $strictPreserved
}}
Write-Output ('CALLER_RESULT=' + ($result | ConvertTo-Json -Compress))
Write-Output 'HOST_ALIVE_AFTER_INSTALLER'
"""

    def run_interactive(self, command, environment, replies, cwd):
        master, slave = pty.openpty()
        output = bytearray()
        reply_index = 0
        cursor_queries = 0
        process = subprocess.Popen(
            command,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=environment,
        )
        os.close(slave)
        try:
            deadline = time.monotonic() + 20
            while True:
                if time.monotonic() >= deadline:
                    self.fail(
                        f"installer timed out:\n{output.decode(errors='replace')}"
                    )
                if not select.select([master], [], [], 0.1)[0]:
                    if process.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output.extend(chunk)
                # Answer PowerShell's cursor-position requests as a terminal would.
                while output.count(b"\x1b[6n") > cursor_queries:
                    os.write(master, b"\x1b[1;1R")
                    cursor_queries += 1
                if reply_index < len(replies):
                    prompt, response = replies[reply_index]
                    if prompt.encode() in output:
                        os.write(master, (response + "\n").encode())
                        reply_index += 1
            self.assertEqual(reply_index, len(replies), output.decode(errors="replace"))
            return process.wait(timeout=2), output.decode(errors="replace")
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()

    def assert_commands(self, output, expected):
        installs = re.findall(
            r"^claude plugin install ([^@\s]+)@([^\s]+)$", output, re.MULTILINE
        )
        for name, marketplace in installs:
            self.assertTrue(
                name in REGISTERED, f"unregistered install target: {name}"
            )
            self.assertEqual(marketplace, MARKETPLACE)
        self.assertEqual([name for name, _ in installs], expected, output)
        self.assertEqual(
            output.count(
                "claude plugin marketplace add "
                "https://github.com/daymade/claude-code-skills"
            ),
            1,
            output,
        )
        self.assertIn("RUN IN TERMINAL", output)
        self.assertIn("2. Paste them into your terminal", output)
        self.assertNotIn("Run these commands in Claude Code", output)
        self.assertNotIn("Paste them into Claude Code", output)

    def test_redirected_stdin_recommends_the_core_suite(self):
        output = self.run_installer()
        self.assert_commands(output, ["daymade-skill"])
        self.assertIn(
            "Defaulting to option 1: daymade-skill only (RECOMMENDED)", output
        )

    def test_featured_plugins_preserve_the_advertised_capabilities(self):
        output = self.run_installer([("Enter your choice (1-4)", "2")])
        self.assert_commands(output, FEATURED)
        self.assertIn("2) Featured plugins", output)

    def test_custom_selection_resolves_suite_and_standalone_ids(self):
        output = self.run_installer(
            [
                ("Enter your choice (1-4)", "3"),
                ("numbers separated by spaces", "1 3 4 7"),
            ]
        )
        self.assert_commands(
            output,
            ["daymade-skill", "daymade-docs", "daymade-claude-code", "llm-icon-finder"],
        )
        self.assertIn("3) daymade-docs", output)
        self.assertIn("4) daymade-claude-code", output)

    def test_exit_generates_no_commands(self):
        output = self.run_installer([("Enter your choice (1-4)", "4")])
        self.assertIn("Installation cancelled.", output)
        self.assertNotIn("claude plugin ", output)

    def assert_no_generated_commands(self, output):
        self.assertNotIn("claude plugin ", output)
        self.assertNotIn("RUN IN TERMINAL", output)
        self.assertNotIn("Installation commands generated!", output)

    def test_invalid_menu_fails_without_generating_commands(self):
        output = self.run_installer(
            [("Enter your choice (1-4)", "9")], expected_returncode=1
        )
        self.assertIn("Invalid choice!", output)
        self.assert_no_generated_commands(output)

    def test_custom_selection_preserves_whitespace_leading_zeroes_and_duplicates(self):
        for selection, expected in [
            ("  007   01  7  003  ", [FEATURED[6], FEATURED[0], FEATURED[6], FEATURED[2]]),
            ("1\t3\t\t4 7", [FEATURED[0], FEATURED[2], FEATURED[3], FEATURED[6]]),
            ("0" * 128 + "7", [FEATURED[6]]),
        ]:
            with self.subTest(selection=selection):
                if self.script.endswith(".ps1") and "\t" in selection:
                    # Read-Host's console editor consumes TAB keypresses. Supply
                    # host-returned text to exercise whitespace parsing unchanged.
                    output = self.run_installer(host_selection=selection)
                else:
                    output = self.run_installer([
                        ("Enter your choice (1-4)", "3"),
                        ("numbers separated by spaces", selection),
                    ])
                self.assert_commands(output, expected)

    def test_custom_selection_rejects_the_whole_invalid_list(self):
        for selection in (
            "", "   ", "x", "1 x 3", "1 8", "0", "000", "-1", "+1",
            "1,3", "1 2+2", "1.0", "0x1", "١", "１", "1\\ 3",
            "9" * 128, "18446744073709551617", "1 9999999999999999999999999",
        ):
            with self.subTest(selection=selection):
                output = self.run_installer([
                    ("Enter your choice (1-4)", "3"),
                    ("numbers separated by spaces", selection),
                ], expected_returncode=1)
                self.assertIn("Invalid plugin selection!", output)
                self.assert_no_generated_commands(output)


class BashInstallerTests(InstallerContract, unittest.TestCase):
    executable = BASH
    script = "scripts/install.sh"

    def test_missing_claude_fails_without_generating_commands(self):
        output = self.run_installer(claude_available=False, expected_returncode=1)
        self.assertIn("Claude Code not found!", output)
        self.assert_no_generated_commands(output)

    def test_printed_download_example_runs_only_after_a_successful_download(self):
        output = self.run_installer()
        self.assert_commands(output, [FEATURED[0]])
        example = self.printed_download_example(output)
        with tempfile.TemporaryDirectory(prefix="installer-example-") as directory:
            sandbox = Path(directory)
            bin_dir = sandbox / "bin"
            bin_dir.mkdir()
            (bin_dir / "bash").symlink_to(BASH)
            curl = bin_dir / "curl"
            curl.write_text('''#!/bin/sh
if [ "$DOWNLOAD_OUTCOME" = success ]; then
    printf '%s\\n' 'printf "FRESH_SCRIPT_EXECUTED\\n"' > install.sh
    exit 0
fi
if [ "$DOWNLOAD_OUTCOME" = partial ]; then
    printf '%s\\n' 'printf "PARTIAL_SCRIPT_EXECUTED\\n"' > install.sh
fi
printf '%s\\n' 'FIXTURE_DOWNLOAD_FAILED' >&2
exit 22
''')
            curl.chmod(0o755)
            for outcome in ("success", "failure", "partial"):
                with self.subTest(outcome=outcome):
                    (sandbox / "install.sh").write_text(
                        'printf "OLD_SCRIPT_EXECUTED\\n"\n'
                    )
                    completed = subprocess.run(
                        [BASH, "-c", example], text=True, capture_output=True,
                        cwd=sandbox, timeout=10, check=False,
                        env={"HOME": str(sandbox), "PATH": str(bin_dir),
                             "DOWNLOAD_OUTCOME": outcome},
                    )
                    result = completed.stdout + completed.stderr
                    self.record_log(outcome, completed.returncode, result)
                    self.assertEqual(
                        completed.returncode, 0 if outcome == "success" else 22,
                        result,
                    )
                    self.assertNotIn("OLD_SCRIPT_EXECUTED", result)
                    self.assertNotIn("PARTIAL_SCRIPT_EXECUTED", result)
                    if outcome == "success":
                        self.assertIn("FRESH_SCRIPT_EXECUTED", result)
                    else:
                        self.assertIn("FIXTURE_DOWNLOAD_FAILED", result)
                        self.assertNotIn("FRESH_SCRIPT_EXECUTED", result)


class PowerShellInstallerTests(InstallerContract, unittest.TestCase):
    executable = POWERSHELL
    script = "scripts/install.ps1"

    def test_console_object_pipeline_keeps_interactive_core_selection(self):
        output = self.run_installer(
            [("Enter your choice (1-4)", "1")], invocation="console-iex"
        )
        self.assertIn("What would you like to install?", output)
        self.assertNotIn("Running in non-interactive mode.", output)
        self.assert_commands(output, ["daymade-skill"])

    def test_printed_download_example_stops_failure_and_preserves_the_host(self):
        output = self.run_installer()
        self.assert_commands(output, [FEATURED[0]])
        example = self.printed_download_example(output)
        with tempfile.TemporaryDirectory(prefix="installer-example-") as directory:
            sandbox = Path(directory)
            for outcome in ("success", "failure", "partial"):
                for preference in ("Continue", "Stop"):
                    with self.subTest(outcome=outcome, preference=preference):
                        (sandbox / "install.ps1").write_text(
                            "Write-Output 'OLD_SCRIPT_EXECUTED'\n"
                        )
                        setup = f"""
$ErrorActionPreference = '{preference}'
function Invoke-WebRequest {{
    [CmdletBinding()]
    param($Uri, $OutFile)
    if ('{outcome}' -eq 'success') {{
        Set-Content -LiteralPath $OutFile -Value "Write-Output 'FRESH_SCRIPT_EXECUTED'"
    }} else {{
        if ('{outcome}' -eq 'partial') {{
            Set-Content -LiteralPath $OutFile -Value "Write-Output 'PARTIAL_SCRIPT_EXECUTED'"
        }}
        Write-Error 'FIXTURE_DOWNLOAD_FAILED'
    }}
}}
"""
                        code = setup + f"""
$caught = $false
$caughtMessage = ''
try {{ {example} }} catch {{ $caught = $true; $caughtMessage = $_.Exception.Message }}
$result = @{{
    caught = $caught
    caughtMessage = $caughtMessage
    preference = [string]$ErrorActionPreference
}}
Write-Output ('EXAMPLE_RESULT=' + ($result | ConvertTo-Json -Compress))
Write-Output 'HOST_ALIVE_AFTER_DOWNLOAD'
"""
                        completed = subprocess.run(
                            [self.executable, "-NoLogo", "-NoProfile", "-Command", code],
                            text=True, capture_output=True, cwd=sandbox,
                            timeout=10, check=False,
                            env={"HOME": str(sandbox), "USERPROFILE": str(sandbox),
                                 "PATH": str(sandbox), "NO_COLOR": "1"},
                        )
                        text = ANSI.sub("", completed.stdout + completed.stderr)
                        self.record_log(
                            f"{outcome}-{preference}", completed.returncode, text
                        )
                        self.assertEqual(completed.returncode, 0, text)
                        match = re.search(r"^EXAMPLE_RESULT=(.+)$", text, re.MULTILINE)
                        self.assertIsNotNone(match, text)
                        result = json.loads(match.group(1))
                        self.assertEqual(result["caught"], outcome != "success", text)
                        self.assertEqual(result["preference"], preference, text)
                        self.assertIn("HOST_ALIVE_AFTER_DOWNLOAD", text)
                        self.assertNotIn("OLD_SCRIPT_EXECUTED", text)
                        self.assertNotIn("PARTIAL_SCRIPT_EXECUTED", text)
                        if outcome == "success":
                            self.assertIn("FRESH_SCRIPT_EXECUTED", text)
                        else:
                            self.assertEqual(result["caughtMessage"], "FIXTURE_DOWNLOAD_FAILED")
                            self.assertNotIn("FRESH_SCRIPT_EXECUTED", text)
                        if preference == "Continue" and outcome != "success":
                            # Consume the printed example as separate host inputs.
                            # An outer try block would incorrectly make separate
                            # download/run lines behave as one bounded command.
                            stream = setup + "\n" + example + "\n" + """
$downloadSucceeded = $?
Write-Output ('DOWNLOAD_SUCCEEDED=' + $downloadSucceeded)
Write-Output ('PREFERENCE_PRESERVED=' + ($ErrorActionPreference -eq 'Continue'))
Write-Output 'HOST_ALIVE_AFTER_DOWNLOAD'
"""
                            completed = subprocess.run(
                                [self.executable, "-NoLogo", "-NoProfile", "-Command", "-"],
                                input=stream, text=True, capture_output=True,
                                cwd=sandbox, timeout=10, check=False,
                                env={"HOME": str(sandbox), "USERPROFILE": str(sandbox),
                                     "PATH": str(sandbox), "NO_COLOR": "1"},
                            )
                            text = ANSI.sub("", completed.stdout + completed.stderr)
                            self.record_log(f"{outcome}-stream", completed.returncode, text)
                            self.assertEqual(completed.returncode, 0, text)
                            self.assertIn("DOWNLOAD_SUCCEEDED=False", text)
                            self.assertIn("PREFERENCE_PRESERVED=True", text)
                            self.assertIn("HOST_ALIVE_AFTER_DOWNLOAD", text)
                            self.assertNotIn("OLD_SCRIPT_EXECUTED", text)
                            self.assertNotIn("PARTIAL_SCRIPT_EXECUTED", text)
                            self.assertNotIn("FRESH_SCRIPT_EXECUTED", text)

    def assert_caller_preserved(self, output, *, caught, strict_mode=False):
        match = re.search(r"^CALLER_RESULT=(.+)$", output, re.MULTILINE)
        self.assertIsNotNone(match, output)
        result = json.loads(match.group(1))
        self.assertEqual(result["caught"], caught, output)
        for key in (
            "commandsPreserved", "pluginsPreserved", "choicePreserved",
            "afterInstallPreserved", "sameWriteError", "writeErrorCaught",
        ):
            self.assertTrue(result[key], f"{key}: {output}")
        self.assertEqual(result["errorPreference"], "Stop", output)
        self.assertEqual(result["warningPreference"], "Continue", output)
        self.assertEqual(result["strictPreserved"], strict_mode, output)
        self.assertIn("HOST_ALIVE_AFTER_INSTALLER", output)
        self.assertNotIn("\nCALLER_AFTER_INSTALL_SENTINEL\n", output)
        return result

    def test_file_and_iex_leave_the_calling_host_intact_for_every_menu_branch(self):
        for invocation in ("file", "console-iex"):
            for choice, selection, expected, caught in (
                ("1", None, [FEATURED[0]], False),
                ("2", None, FEATURED, False),
                ("3", "007 1 7", [FEATURED[6], FEATURED[0], FEATURED[6]], False),
                ("4", None, None, False),
                ("9", None, None, True),
                ("3", "1 x 3", None, True),
            ):
                with self.subTest(invocation=invocation, choice=choice, selection=selection):
                    replies = [("Enter your choice (1-4)", choice)]
                    if selection is not None:
                        replies.append(("numbers separated by spaces", selection))
                    output = self.run_installer(
                        replies, invocation=invocation, caller_probe=True,
                        strict_mode=True,
                    )
                    result = self.assert_caller_preserved(output, caught=caught, strict_mode=True)
                    if caught:
                        self.assertIn(
                            "Invalid choice!" if choice == "9" else "Invalid plugin selection!",
                            result["caughtMessage"],
                        )
                    if expected is None:
                        self.assert_no_generated_commands(output)
                    else:
                        self.assert_commands(output, expected)

    def test_iex_noninteractive_preserves_caller_functions_and_preferences(self):
        for strict_mode in (False, True):
            with self.subTest(strict_mode=strict_mode):
                output = self.run_installer(
                    invocation="console-iex", caller_probe=True,
                    strict_mode=strict_mode, custom_write_error=True,
                )
                result = self.assert_caller_preserved(
                    output, caught=False, strict_mode=strict_mode
                )
                self.assertEqual(result["writeErrorMessage"], "CALLER_WRITE_ERROR:CALLER_CHECK")
                self.assert_commands(output, [FEATURED[0]])

    def test_missing_claude_can_be_declined_or_continued_without_stopping_host(self):
        for invocation in ("file", "console-iex"):
            for response in ("n", "y"):
                with self.subTest(invocation=invocation, response=response):
                    replies = [("Continue anyway? (y/n)", response)]
                    if response == "y":
                        replies.append(("Enter your choice (1-4)", "1"))
                    output = self.run_installer(
                        replies,
                        invocation=invocation, caller_probe=True, strict_mode=True,
                        claude_available=False,
                    )
                    result = self.assert_caller_preserved(
                        output, caught=(response == "n"), strict_mode=True
                    )
                    if response == "n":
                        self.assertIn("Claude Code is unavailable", result["caughtMessage"])
                        self.assert_no_generated_commands(output)
                    else:
                        self.assert_commands(output, [FEATURED[0]])

    def test_uncaught_iex_and_file_failures_exit_nonzero(self):
        for invocation in ("file", "console-iex"):
            with self.subTest(invocation=invocation):
                output = self.run_installer(
                    invocation=invocation, claude_available=False,
                    redirected_input="n\n", expected_returncode=1,
                )
                self.assert_no_generated_commands(output)


if __name__ == "__main__":
    unittest.main()

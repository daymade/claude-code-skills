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

    def run_installer(self, replies=(), *, invocation="file"):
        with tempfile.TemporaryDirectory(prefix="installer-test-") as directory:
            sandbox = Path(directory)
            home = sandbox / "home"
            home.mkdir()
            bin_dir = sandbox / "bin"
            bin_dir.mkdir()
            call_log = sandbox / "claude-calls"
            call_log.touch()
            if os.name == "nt":
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
            if invocation == "console-iex":
                source = str(ROOT / self.script).replace("'", "''")
                command.extend([
                    "-Command",
                    f"[IO.File]::ReadAllText('{source}') | Invoke-Expression",
                ])
            else:
                if self.script.endswith(".ps1"):
                    command.append("-File")
                command.append(str(ROOT / self.script))
            if replies:
                if os.name != "posix":
                    self.skipTest("interactive installer checks require a POSIX PTY")
                returncode, output = self.run_interactive(
                    command, environment, replies, home
                )
            else:
                completed = subprocess.run(
                    command,
                    input="",
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
            self.assertEqual(returncode, 0, output)
            return ANSI.sub("", output).replace("\r", "")

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


class BashInstallerTests(InstallerContract, unittest.TestCase):
    executable = BASH
    script = "scripts/install.sh"


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


if __name__ == "__main__":
    unittest.main()

"""The optional native command keeps profile setup outside structured stdout."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claude-profiles.sh"


class NativeCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="profile-native-command-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.home = self.base / "home with spaces"
        self.home.mkdir()
        self.profile = self.home / ".claude-profiles" / "synthetic"
        self.profile.mkdir(parents=True)
        self.settings = self.home / ".claude" / "settings" / "synthetic.json"
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{}\n")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.helpers = self.base / "profile helpers"
        self.helpers.mkdir()
        self.sync_log = self.base / "sync.jsonl"
        for name in ("sync-local-skill-sources.py", "claude-plugins-sync.py"):
            (self.helpers / name).write_text(
                "import json,sys\nfrom pathlib import Path\n"
                "with Path(" + repr(str(self.sync_log)) + ").open('a') as f:"
                "f.write(json.dumps([Path(__file__).name,*sys.argv[1:]])+'\\n')\n"
            )
        self.native_log = self.base / "native.jsonl"
        self.events = self.base / "native-events.jsonl"
        self.native = self.bin / "claude"
        self.callback = self.bin / "native callback"
        self.arguments = ["--print", "--output-format", "stream-json", "--permission-mode", "acceptEdits",
                          "--allowedTools", "Read,Bash(printf *)", "--resume", "original with spaces", "--fork-session"]
        self.write_native(self.native, "native", 0)
        self.write_native(self.callback, "callback", 7)
        # Exercise a distribution-shaped entry without changing any real install.
        self.entry = self.base / "installed profile" / "claude-profiles.sh"
        self.entry.parent.mkdir()
        self.entry.symlink_to(SCRIPT)
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin:/usr/sbin:/sbin",
            "ZDOTDIR": str(self.home), "CLAUDE_PROFILES_CONFIG_DIR": str(self.helpers),
        }
        python = self.bin / "python3"
        python.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
        python.chmod(0o700)

    def write_native(self, destination, identity, code):
        destination.write_text(
            "#!" + sys.executable + "\nimport json,os,sys\nfrom pathlib import Path\n"
            "record=dict(identity=" + repr(identity) + ",argv=sys.argv[1:],uid=os.getuid(),"
            "profile=os.environ.get('CLAUDE_CONFIG_DIR'),input=sys.stdin.read())\n"
            "with Path(" + repr(str(self.native_log)) + ").open('a') as f:f.write(json.dumps(record)+'\\n')\n"
            "body=json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'synthetic report'}]}})+'\\n'\n"
            + ("Path(" + repr(str(self.events)) + ").write_text(body)\n" if identity == "callback" else "")
            + "sys.stdout.write(body)\nprint('NATIVE_STDERR',file=sys.stderr)\nraise SystemExit(" + str(code) + ")\n"
        )
        destination.chmod(0o700)

    def run_profile(self, shell, *, callback=True, profile="synthetic", command=None):
        argv = (["claude-profile-with-command", str(self.callback) if command is None else command]
                if callback else ["claude-profile"])
        code = "set -e\nsource " + shlex.quote(str(self.entry)) + "\n" + shlex.join([*argv, profile, *self.arguments])
        return subprocess.run([shell, "-c", code], env=self.env, input="unchanged input\n",
                              text=True, capture_output=True, timeout=10)

    def shells(self):
        return ["/bin/bash", *(["/bin/zsh"] if Path("/bin/zsh").is_file() else [])]

    def reset_outputs(self):
        for path in (self.native_log, self.sync_log, self.events):
            if path.exists():
                path.unlink()

    def test_explicit_native_command_preserves_profile_policy_arguments_logs_and_exit(self):
        for shell in self.shells():
            for callback in (False, True):
                with self.subTest(shell=shell, callback=callback):
                    self.reset_outputs()
                    result = self.run_profile(shell, callback=callback)
                    self.assertEqual(result.returncode, 7 if callback else 0, result.stderr)
                    launches = [json.loads(line) for line in self.native_log.read_text().splitlines()]
                    self.assertEqual(len(launches), 1)
                    launch = launches[0]
                    self.assertEqual(launch["identity"], "callback" if callback else "native")
                    self.assertEqual(launch["argv"], ["--settings", str(self.settings), *self.arguments])
                    self.assertEqual(launch["profile"], str(self.profile))
                    self.assertEqual(launch["uid"], os.getuid())
                    self.assertEqual(launch["input"], "unchanged input\n")
                    self.assertIn("[LAUNCH] Profile: synthetic", result.stdout)
                    self.assertIn("NATIVE_STDERR", result.stderr)
                    calls = [json.loads(line) for line in self.sync_log.read_text().splitlines()]
                    self.assertEqual(calls, [["sync-local-skill-sources.py", "--apply", "--quiet"],
                                             ["claude-plugins-sync.py", "--profile", "synthetic"]])
                    if callback:
                        events = self.events.read_text()
                        self.assertEqual(len(events.splitlines()), 1)
                        self.assertEqual(json.loads(events)["type"], "assistant")
                        self.assertNotIn("[LAUNCH]", events)
                    else:
                        self.assertFalse(self.events.exists())

    def test_invalid_native_command_fails_before_profile_setup_or_native(self):
        directory_alias = self.base / "directory alias"
        directory_alias.symlink_to(self.base, target_is_directory=True)
        nonexecutable = self.base / "nonexecutable"
        nonexecutable.write_text("synthetic non-executable file\n")
        for shell in self.shells():
            for command in ("", "relative-command", str(self.base / "missing"), str(self.base),
                            str(directory_alias), str(nonexecutable)):
                with self.subTest(shell=shell, command=command):
                    result = self.run_profile(shell, command=command)
                    self.assertIn(result.returncode, (64, 126), result.stderr)
                    self.assertFalse(self.sync_log.exists())
                    self.assertFalse(self.native_log.exists())
                    self.assertFalse(self.events.exists())

    def test_executable_file_symlink_remains_supported(self):
        alias = self.bin / "callback alias"
        alias.symlink_to(self.callback)
        for shell in self.shells():
            with self.subTest(shell=shell):
                self.reset_outputs()
                result = self.run_profile(shell, command=str(alias))
                self.assertEqual(result.returncode, 7, result.stderr)
                launch = json.loads(self.native_log.read_text())
                self.assertEqual(launch["identity"], "callback")
                self.assertEqual(launch["argv"], ["--settings", str(self.settings), *self.arguments])
                self.assertEqual(launch["profile"], str(self.profile))

    def test_missing_profile_and_settings_preserve_refusal_on_both_entries(self):
        for shell in self.shells():
            for callback in (False, True):
                for missing in ("profile", "settings"):
                    with self.subTest(shell=shell, callback=callback, missing=missing):
                        destination = self.settings.with_suffix(".saved")
                        if missing == "settings":
                            self.settings.rename(destination)
                        try:
                            result = self.run_profile(shell, callback=callback,
                                                      profile="missing" if missing == "profile" else "synthetic")
                        finally:
                            if destination.exists():
                                destination.rename(self.settings)
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertFalse(self.native_log.exists())
                        self.assertFalse(self.sync_log.exists())

    def test_setup_failure_does_not_continue_into_either_native_entry(self):
        (self.helpers / "sync-local-skill-sources.py").write_text("raise SystemExit(9)\n")
        for shell in self.shells():
            for callback in (False, True):
                with self.subTest(shell=shell, callback=callback):
                    result = self.run_profile(shell, callback=callback)
                    self.assertEqual(result.returncode, 9, result.stderr)
                    self.assertFalse(self.native_log.exists())
                    self.assertFalse(self.events.exists())


if __name__ == "__main__":
    unittest.main()

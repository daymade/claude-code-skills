from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync-local-skill-sources-daemon.sh"
LABEL = "ai.daymade.claude-skill-source-sync"


class SourceSyncDaemonTests(unittest.TestCase):
    """What --install does to a LaunchAgent somebody else already configured.

    The ruling this suite pins, one test per rule:

      1. no plist / unreadable / not a dict / no ProgramArguments key
         -> first install, writes this script, silent
      2. the key is there but unusable (not a list, empty, non-string [0])
         -> reset, and say what was found
      3. [0] resolves to this script, no extra arguments
         -> reset, silent
      4. [0] resolves to this script but there are extra arguments
         -> reset, and name the arguments being dropped
      5. [0] is another executable -> keep the WHOLE array, say so, and say WHICH
         kind of "another": a different file carrying this script's name (another
         checkout, another cached version) is reported as a different file, never
         as this script and never as something a named party installed
      6. [0] is another path that is gone or not usable -> reset, and name it:
         "not a usable executable file" (a directory, FIFO or dangling symlink
         EXISTS), and an empty path is named as an empty path

    Only rules 1 and 3 may be silent. Anything an operator configured that this
    installer changes has to be said out loud: silence is what let --install
    detach the failure recorder (scripts/sync-daemon-recorder.sh, which works only
    by being ProgramArguments[0]) for as long as it did.

    Rule 3 resolves both sides of the comparison. That joins one file spelled two
    ways (the entry holds the plugin-cache path, the run goes through the ~/.config
    symlink into that same copy) and nothing else: a source checkout and a cached
    plugin copy are two inodes, and they land in rule 5 as "another copy".
    """

    def _prepare(self, root: Path) -> tuple[Path, dict[str, str]]:
        """A temp HOME with the daemon copied beside a stub sync script.

        Everything the installer touches lives under `root`: the owned interpreter,
        stub `uv`/`launchctl` on PATH, and HOME. Returns the copied daemon path and
        the environment to run it with.
        """
        scripts = root / "scripts"
        scripts.mkdir()
        daemon = scripts / SCRIPT.name
        shutil.copyfile(SCRIPT, daemon)
        (scripts / "sync-local-skill-sources.py").write_text(
            "import sys\n"
            "print('/tmp/example/marketplace.json' if '--print-watch-paths' in sys.argv else 'sync-ok')\n"
        )
        owned = root / ".config/claude-switch-models-setup/python/test/bin/python3"
        owned.parent.mkdir(parents=True)
        owned.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        owned.chmod(0o755)
        stubs = root / "bin"
        stubs.mkdir()
        uv = stubs / "uv"
        uv.write_text(f'#!/bin/sh\nif [ "$2" = find ]; then printf "%s\\n" "{owned}"; fi\n')
        uv.chmod(0o755)
        launchctl = stubs / "launchctl"
        launchctl.write_text("#!/bin/sh\nexit 0\n")
        launchctl.chmod(0o755)
        env = {**os.environ, "HOME": str(root), "PATH": str(stubs) + os.pathsep + os.environ["PATH"]}
        return daemon, env

    def _plist_path(self, root: Path) -> Path:
        return root / f"Library/LaunchAgents/{LABEL}.plist"

    def _install(self, daemon: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(["bash", str(daemon), "--install"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Prove the installer actually ran. Without this, a fixture file that shadows
        # `bash` on the stubbed PATH makes the whole install a 0.2s no-op that exits 0,
        # and every assertion below then reads back whatever _write_plist left behind.
        self.assertIn("Installed LaunchAgent:", result.stdout)
        return result

    def _write_plist(self, root: Path, payload: object) -> None:
        plist_path = self._plist_path(root)
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, bytes):
            plist_path.write_bytes(payload)
        else:
            plist_path.write_bytes(plistlib.dumps(payload))

    def _plist_xml(self, body: str) -> bytes:
        """A minimal valid plist around `body`, for shapes plistlib cannot dump."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            f'<plist version="1.0"><dict><key>Label</key><string>{LABEL}</string>'
            f"{body}</dict></plist>\n"
        ).encode()

    def _executable(self, path: Path) -> Path:
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
        return path

    # --- rule 1: nothing was ever configured -> silent first install ------------

    def test_first_install_points_at_itself(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            self.assertFalse(self._plist_path(root).exists())
            result = self._install(daemon, env)
            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertEqual("", result.stderr)

    def test_plist_without_a_program_arguments_key_is_silent(self):
        """Rule 1 keeps the key-absent case silent: absence is not a configuration."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            self._write_plist(root, {"Label": LABEL})
            result = self._install(daemon, env)
            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertEqual("", result.stderr)

    def test_non_dict_plist_is_silent(self):
        for payload in ("just-a-string", ["not", "a", "dict"], 42):
            with self.subTest(payload=payload):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw).resolve()
                    daemon, env = self._prepare(root)
                    self._write_plist(root, payload)
                    result = self._install(daemon, env)
                    plist = plistlib.loads(self._plist_path(root).read_bytes())
                    self.assertEqual(plist["ProgramArguments"], [str(daemon)])
                    self.assertEqual("", result.stderr)

    def test_unreadable_plist_is_a_silent_first_install(self):
        """Rule 1: nothing readable was configured, so there is nothing to name.

        A corrupt binary plist raises something other than the XML path's
        InvalidPlistException, which is why the reader catches broadly.
        """
        for label, payload in (
            ("xml garbage", b"this is not a plist at all"),
            ("corrupt binary", b"bplist00\x00\x00corrupted-body"),
        ):
            with self.subTest(payload=label):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw).resolve()
                    daemon, env = self._prepare(root)
                    self._write_plist(root, payload)
                    result = self._install(daemon, env)
                    plist = plistlib.loads(self._plist_path(root).read_bytes())
                    self.assertEqual(plist["ProgramArguments"], [str(daemon)])
                    self.assertEqual("", result.stderr)

    # --- rule 2: entry present but unusable -> reset, and say what it found -----

    def test_present_but_unusable_entry_resets_and_names_what_it_found(self):
        """Not a list, empty, or a non-string element 0: replace, never quietly.

        The plist format has no null, so `[None]` is written here as the other
        non-string element types a real plist can hold (integer, boolean, bytes,
        date, dict, array); the single isinstance check is what turns every one of
        them — and None, were any loader to produce it — into this branch rather
        than a crash mid-install.
        """
        bodies = [
            "<key>ProgramArguments</key><array/>",
            "<key>ProgramArguments</key><array><integer>17</integer></array>",
            "<key>ProgramArguments</key><array><true/></array>",
            "<key>ProgramArguments</key><array><data>AA==</data></array>",
            "<key>ProgramArguments</key><array><date>2026-09-22T00:00:00Z</date></array>",
            "<key>ProgramArguments</key><array><dict/></array>",
            "<key>ProgramArguments</key><array><array/></array>",
            "<key>ProgramArguments</key><string>not-a-list</string>",
        ]
        for body in bodies:
            with self.subTest(body=body):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw).resolve()
                    daemon, env = self._prepare(root)
                    payload = self._plist_xml(body)
                    self._write_plist(root, payload)
                    found = plistlib.loads(payload)["ProgramArguments"]

                    result = self._install(daemon, env)

                    plist = plistlib.loads(self._plist_path(root).read_bytes())
                    self.assertEqual(plist["ProgramArguments"], [str(daemon)])
                    self.assertNotEqual("", result.stderr)
                    # Name what was there, verbatim, not just "something odd".
                    self.assertIn(repr(found), result.stderr)
                    self.assertIn(str(daemon), result.stderr)

    # --- rule 3: this same script, no extra arguments -> silent repeat ----------

    def test_repeat_install_stays_silent_and_keeps_its_own_entry(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            self._install(daemon, env)
            result = self._install(daemon, env)
            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertEqual("", result.stderr)

    def test_symlinked_self_entry_is_a_silent_repeat_install(self):
        """The same FILE reached by two paths, which is all realpath can join.

        The mirror case: the entry holds the plugin-cache path while the run goes
        through the ~/.config symlink into that same cache copy. The two strings
        differ, so a literal comparison reports an operator wrapper that does not
        exist; resolving both sides says "this script" and stays silent.

        This is the limit of that comparison. An entry pointing at the deployed
        location while --install runs from the source checkout is two different
        inodes and realpath cannot join them -- that case is preserved as another
        copy of this script (see test_same_named_copy_is_not_called_a_wrapper),
        never reset as "already me".
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            deployed = root / "deployed-entry.sh"
            deployed.symlink_to(daemon)
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [str(deployed)]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertEqual("", result.stderr)

    # --- rule 4: this script plus arguments -> name what gets dropped ----------

    def test_extra_arguments_on_a_self_entry_are_named_and_dropped(self):
        """An operator's arguments to this script are not this installer's to keep.

        Dropping them quietly is the same silent-replacement shape as the bug, so
        they are named on stderr.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            self._write_plist(
                root,
                {"Label": LABEL, "ProgramArguments": [str(daemon), "--some-operator-arg"]},
            )

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertIn("--some-operator-arg", result.stderr)

    # --- rule 5: a foreign executable -> keep the whole array ------------------

    def test_same_named_copy_is_not_called_a_wrapper(self):
        """Same NAME, different file: another checkout or another cached version.

        Every cached plugin version ships a file of this name, and so does every
        checkout, so an entry can point at this script's name without being this
        script. realpath cannot join two inodes, and basename must never be used
        to decide "is me" -- that would merge different cached versions into one
        script. It only decides how the message reads: another file with this name,
        not this script, and not an assertion about who put it there.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            other = root / "other-checkout/scripts"
            other.mkdir(parents=True)
            copy = other / SCRIPT.name
            copy.write_text("#!/bin/sh\necho another checkout\n")
            copy.chmod(0o755)
            # Guard the premise: a different file that merely shares a name.
            self.assertNotEqual(
                copy.stat().st_ino, daemon.stat().st_ino, "fixture must be two files"
            )
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [str(copy)]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(copy)])
            self.assertIn("another checkout", result.stderr)
            # A failed install has no evidence about who put an entry there, so no
            # message may claim to know. This holds for BOTH rule-5 messages.
            self.assertNotIn("operator-installed", result.stderr)

    def test_differently_named_symlink_to_a_copy_is_not_called_a_wrapper(self):
        """The false positive: a differently named symlink into another copy.

        The entry is NOT this script and does not share its name, so it lands in
        the other rule-5 message -- which must not claim it was operator-installed
        either. Asserting who configured an entry is outside anything this
        installer can see.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            other = root / "other-checkout/scripts"
            other.mkdir(parents=True)
            copy = other / SCRIPT.name
            copy.write_text("#!/bin/sh\necho another checkout\n")
            copy.chmod(0o755)
            link = root / "sync-wrapper-link.sh"
            link.symlink_to(copy)
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [str(link)]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(link)])
            self.assertIn("an executable other than this script", result.stderr)
            self.assertNotIn("operator-installed", result.stderr)

    def test_install_preserves_an_installed_wrapper(self):
        """The bug this worktree exists for.

        scripts/sync-daemon-recorder.sh takes effect only by being
        ProgramArguments[0], so every --install silently detached the failure
        recorder from the daemon and failing passes went invisible again.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            wrapper = self._executable(root / "bin/sync-daemon-recorder.sh")
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [str(wrapper)]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(wrapper)])
            self.assertIn(str(wrapper), result.stderr)
            self.assertIn("an executable other than this script", result.stderr)
            # It stays wrapped, but the message may not claim to know who wrapped it.
            self.assertNotIn("operator-installed", result.stderr)
            # Only ProgramArguments is preserved; the rest is still this installer's.
            self.assertEqual(plist["StartInterval"], 300)
            self.assertTrue(plist["RunAtLoad"])
            self.assertIn("/tmp/example/marketplace.json", plist["WatchPaths"])
            self.assertEqual(
                plist["StandardErrorPath"],
                str(root / "Library/Logs/claude-switch-models-setup/source-sync.err.log"),
            )

    def test_install_preserves_wrapper_arguments_verbatim(self):
        """A wrapper may take arguments; keeping [0] alone would drop them."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            # NOT under root/bin: that directory is first on PATH, and a file named
            # after a real command there shadows it for the installer itself.
            wraps = root / "wraps"
            wraps.mkdir()
            bash = self._executable(wraps / "bash")
            wrapper = self._executable(wraps / "wrap.sh")
            self._write_plist(
                root, {"Label": LABEL, "ProgramArguments": [str(bash), str(wrapper), "--flag"]}
            )
            self._install(daemon, env)
            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(
                plist["ProgramArguments"], [str(bash), str(wrapper), "--flag"]
            )

    # --- rule 6: a foreign path that is gone or not executable ----------------

    def test_install_replaces_a_stale_entry_and_says_so(self):
        """A vanished wrapper is replaced — never silently, which is the same mistake."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            vanished = root / "bin/gone.sh"
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [str(vanished)]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertIn(str(vanished), result.stderr)

    def test_install_replaces_a_non_executable_entry_and_says_so(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            # Exists but is not executable: keeping it would brick the job.
            plain = root / "bin/recorder.sh"
            plain.write_text("#!/bin/sh\nexit 0\n")
            plain.chmod(0o644)
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [str(plain)]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertIn(str(plain), result.stderr)

    def test_unusable_target_shapes_do_not_claim_the_path_is_gone(self):
        """A directory, a FIFO and a dangling symlink all EXIST.

        "no longer exists" is false for all three, so the message states the real
        condition — not an executable regular file, which is what launchd can run.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            targets: dict[str, Path] = {}
            folder = root / "bin/a-directory-target"
            folder.mkdir(parents=True)
            targets["directory"] = folder
            fifo = root / "bin/a-fifo-target"
            os.mkfifo(fifo)
            targets["fifo"] = fifo
            dangling = root / "bin/a-dangling-target"
            dangling.symlink_to(root / "bin/never-existed.sh")
            targets["dangling symlink"] = dangling

            for label, target in targets.items():
                with self.subTest(shape=label):
                    # Premise: these are not executable regular files, and neither
                    # claim in the old message is true of them.
                    self.assertFalse(os.path.isfile(target), f"{label} must not be a file")
                    self.assertTrue(os.path.lexists(target), f"{label} must exist for the FIFO/dir cases")

                    home = root / f"home-{label.replace(' ', '-')}"
                    home.mkdir()
                    daemon, env = self._prepare(home)
                    self._write_plist(home, {"Label": LABEL, "ProgramArguments": [str(target)]})

                    result = self._install(daemon, env)

                    plist = plistlib.loads(self._plist_path(home).read_bytes())
                    self.assertEqual(plist["ProgramArguments"], [str(daemon)])
                    self.assertIn(str(target), result.stderr)
                    self.assertIn("not a usable executable file", result.stderr)
                    self.assertNotIn("no longer exists", result.stderr)

    def test_empty_entry_says_it_is_an_empty_path(self):
        """An entry of "" names nothing, so echoing it back says nothing.

        The message has to name the SHAPE, not print a blank where the path belongs.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": [""]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertIn("empty path", result.stderr)
            self.assertIn(str(daemon), result.stderr)

    def test_whitespace_entry_is_also_an_empty_path(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            self._write_plist(root, {"Label": LABEL, "ProgramArguments": ["   "]})

            result = self._install(daemon, env)

            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["ProgramArguments"], [str(daemon)])
            self.assertIn("empty path", result.stderr)

    # --- unchanged behaviour the rewrite must not have disturbed ---------------

    def test_install_uses_owned_interpreter_and_retries_periodically(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            daemon, env = self._prepare(root)
            result = self._install(daemon, env)
            plist = plistlib.loads(self._plist_path(root).read_bytes())
            self.assertEqual(plist["StartInterval"], 300)
            self.assertIn("source-sync verified links and profiles at", result.stdout)
            # No silent success marker when either underlying sync fails.
            (root / "scripts/sync-local-skill-sources.py").write_text("raise SystemExit(7)\n")
            result = subprocess.run(["bash", str(daemon)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 7)
            self.assertNotIn("verified links and profiles", result.stdout)


if __name__ == "__main__":
    unittest.main()

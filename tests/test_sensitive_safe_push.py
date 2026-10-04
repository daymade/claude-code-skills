"""Synthetic protocols plus real local Git; no GitHub writes or credentials."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "github-sensitive-data-cleanup/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("tested_safe_push", SCRIPTS / "safe_push.py")
push = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push)
sys.path.pop(0)
IDENTITY = "github.fixture.invalid/synthetic-owner/synthetic-repo"
METADATA = {"visibility": "PRIVATE", "isPrivate": True, "stargazerCount": 0,
            "forkCount": 0, "owner": {"login": "synthetic-owner"}, "name": "synthetic-repo"}


class SafePushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="safe-push-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "GH_", "GITHUB_"))}
        env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_ALLOW_PROTOCOL="file", GIT_NO_LAZY_FETCH="1",
                   GIT_GUARD_OSASCRIPT="/usr/bin/false", GIT_GUARD_TTY=os.devnull,
                   GIT_AUTHOR_NAME="Synthetic Fixture", GIT_COMMITTER_NAME="Synthetic Fixture",
                   GIT_AUTHOR_EMAIL="fixture@example.invalid", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.remote = self.root / "remote.git"
        self.remote.mkdir()
        self.git(self.remote, "init", "--bare", "--initial-branch=main")
        self.a = self.root / "A"
        self.git(self.root, "clone", str(self.remote), str(self.a))
        self.commit(self.a, "baseline", "baseline.txt")
        self.git(self.a, "push", "origin", "main")
        self.old = self.sha(self.a, "HEAD")
        self.commit(self.a, "candidate", "candidate.txt")
        self.candidate = self.sha(self.a, "HEAD")
        self.calls = []
        self.bins = self.root / "bin"
        self.bins.mkdir()
        self.gh_log = self.root / "gh.jsonl"
        fake = self.bins / "gh"
        fake.write_text("#!" + sys.executable + "\n" +
                        "import json, os, sys\nfrom pathlib import Path\n" +
                        "with Path(os.environ['GH_TEST_LOG']).open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n" +
                        "print(os.environ['GH_TEST_METADATA'])\n" +
                        "print(os.environ.get('GH_TEST_STDERR',''), file=sys.stderr)\n" +
                        "sys.exit(int(os.environ.get('GH_TEST_EXIT','0')))\n")
        fake.chmod(0o700)
        os.environ.update(PATH=str(self.bins) + os.pathsep + os.environ["PATH"],
                          GH_TEST_LOG=str(self.gh_log), GH_TEST_METADATA=json.dumps(METADATA))
        self.hook_log = self.root / "hook.jsonl"
        hook = self.a / ".git/hooks/pre-push"
        hook.write_text("#!" + sys.executable + "\n" +
                        "import json, os, subprocess, sys\nfrom pathlib import Path\n" +
                        "name,url=sys.argv[1:]\n" +
                        "resolved=subprocess.check_output(['git','ls-remote','--get-url',name],text=True).strip()\n" +
                        "with Path(os.environ['PUSH_HOOK_LOG']).open('a') as f: f.write(json.dumps({'name':name,'url':url,'resolved':resolved,'updates':sys.stdin.read()})+'\\n')\n" +
                        "sys.exit(int(os.environ.get('PUSH_HOOK_EXIT','0')))\n")
        hook.chmod(0o700)
        os.environ["PUSH_HOOK_LOG"] = str(self.hook_log)

    def git(self, repo, *args, check=True):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        if check and result.returncode:
            self.fail(result.stderr)
        return result

    def sha(self, repo, ref):
        return self.git(repo, "rev-parse", ref).stdout.strip()

    def commit(self, repo, text, file):
        (repo / file).write_text(text + "\n")
        self.git(repo, "add", file)
        self.git(repo, "commit", "-m", "synthetic " + text)

    def invoke(self, **changes):
        inputs = dict(expected_repository=IDENTITY, expected_remote_sha=self.old,
                      verified_local_sha=self.candidate)
        inputs.update(changes)
        actual_run = push.run

        def track(repo, args, **kwargs):
            self.calls.append(args)
            return actual_run(repo, args, **kwargs)

        # Only local URL identity is synthetic. Metadata, Git, lease and native
        # hooks exercise the actual helper; URL parsing has separate cases below.
        with patch.object(push, "url_identity", return_value=tuple(IDENTITY.split("/"))), \
                patch.object(push, "run", side_effect=track), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return push.push(self.a, "origin", "main", **inputs)

    def test_single_lease_and_native_named_remote_hook(self):
        self.git(self.a, "config", "push.followTags", "true")
        self.git(self.a, "tag", "-a", "synthetic-tag", "-m", "synthetic tag")
        self.invoke()
        self.assertEqual(self.sha(self.remote, "main"), self.candidate)
        writes = [args for args in self.calls if args[0] == "push"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][2], self.candidate + ":refs/heads/main")
        self.assertEqual(writes[0][3], "--force-with-lease=refs/heads/main:" + self.old)
        self.assertNotIn("--force", writes[0])
        self.assertIn("--no-follow-tags", writes[0])
        self.assertIn("--recurse-submodules=no", writes[0])
        self.assertNotEqual(self.git(self.remote, "show-ref", "--verify", "refs/tags/synthetic-tag", check=False).returncode, 0)
        record = json.loads(self.hook_log.read_text().strip())
        self.assertTrue(record["name"].startswith("cleanup-push-"))
        self.assertEqual(record["url"], str(self.remote))
        self.assertEqual(record["resolved"], str(self.remote))
        self.assertIn(self.candidate, record["updates"])
        self.assertEqual(self.git(self.a, "remote").stdout.strip(), "origin")
        self.assertEqual(json.loads(self.gh_log.read_text().strip())[2], IDENTITY)

    def test_concurrent_writer_before_preflight_is_preserved(self):
        b = self.root / "B"
        self.git(self.root, "clone", str(self.remote), str(b))
        self.commit(b, "B advancement", "B.txt")
        btip = self.sha(b, "HEAD")
        self.git(b, "push", "origin", "main")
        with self.assertRaises(push.PushError):
            self.invoke()
        self.assertEqual(self.sha(self.remote, "main"), btip)
        self.assertFalse(any(args[0] == "push" for args in self.calls))

    def test_lease_race_after_preflight_has_no_force_retry(self):
        b = self.root / "B"
        self.git(self.root, "clone", str(self.remote), str(b))
        self.commit(b, "B advancement", "B.txt")
        btip = self.sha(b, "HEAD")
        actual_run = push.run
        writes = []

        def race(repo, args, **kwargs):
            if args[0] == "push":
                writes.append(args)
                self.git(b, "push", "origin", "main")
            return actual_run(repo, args, **kwargs)

        with patch.object(push, "url_identity", return_value=tuple(IDENTITY.split("/"))), \
                patch.object(push, "run", side_effect=race), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(push.PushError):
            push.push(self.a, "origin", "main", expected_repository=IDENTITY,
                      expected_remote_sha=self.old, verified_local_sha=self.candidate)
        self.assertEqual(len(writes), 1)
        self.assertEqual(self.sha(self.remote, "main"), btip)

    def test_missing_null_empty_preconditions_and_legacy_call(self):
        for field in ("expected_repository", "expected_remote_sha", "verified_local_sha"):
            supplied = dict(expected_repository=IDENTITY, expected_remote_sha=self.old,
                            verified_local_sha=self.candidate)
            del supplied[field]
            with self.subTest(field=field, value="missing"), self.assertRaises(push.PushError):
                push.push(self.a, "origin", "main", **supplied)
            for value in (None, "", " "):
                with self.subTest(field=field, value=value), self.assertRaises(push.PushError):
                    self.invoke(**{field: value})
        with self.assertRaises(push.PushError):
            push.push(self.a, "origin", "main")
        self.assertFalse(any(args[0] == "push" for args in self.calls))

    def test_wrong_repository_and_all_missing_null_empty_metadata(self):
        bad = json.loads(json.dumps(METADATA))
        bad["owner"]["login"] = "other-owner"
        variants = [bad, [], None, {}]
        for key in METADATA:
            for shape in ("missing", "null", "empty"):
                value = json.loads(json.dumps(METADATA))
                if shape == "missing":
                    del value[key]
                else:
                    value[key] = None if shape == "null" else ({} if key == "owner" else "")
                variants.append(value)
        for shape in ("missing", "null", "empty"):
            value = json.loads(json.dumps(METADATA))
            if shape == "missing":
                del value["owner"]["login"]
            else:
                value["owner"]["login"] = None if shape == "null" else ""
            variants.append(value)
        for metadata in variants:
            with self.subTest(metadata=metadata):
                os.environ["GH_TEST_METADATA"] = json.dumps(metadata)
                with self.assertRaises(push.PushError):
                    self.invoke()
        self.assertFalse(any(args[0] == "push" for args in self.calls))

    def test_metadata_stderr_and_secret_url_are_not_disclosed(self):
        marker = "synthetic-sensitive-diagnostic"
        os.environ.update(GH_TEST_EXIT="1", GH_TEST_STDERR=marker)
        output = io.StringIO()
        with patch.object(push, "url_identity", return_value=tuple(IDENTITY.split("/"))), \
                contextlib.redirect_stderr(output):
            self.assertIsNone(push.get_remote_repo_info(self.a, "origin", expected_repository=IDENTITY))
        self.assertNotIn(marker, output.getvalue())
        credential_url = "https://fixture:" + marker + "@github.fixture.invalid/synthetic-owner/synthetic-repo.git"
        with self.assertRaises(push.PushError) as raised:
            push.url_identity(credential_url)
        self.assertNotIn(marker, str(raised.exception))

    def test_multiple_urls_and_changed_remote_are_rejected(self):
        self.git(self.a, "config", "--add", "remote.origin.pushurl", str(self.remote))
        self.git(self.a, "config", "--add", "remote.origin.pushurl", str(self.root / "other.git"))
        with self.assertRaises(push.PushError):
            self.invoke()
        self.assertFalse(any(args[0] == "push" for args in self.calls))
        self.git(self.a, "config", "--unset-all", "remote.origin.pushurl")
        actual = push.get_remote_repo_info

        def changed(*args, **kwargs):
            info = actual(*args, **kwargs)
            self.git(self.a, "remote", "set-url", "origin", str(self.root / "other.git"))
            return info

        with patch.object(push, "get_remote_repo_info", side_effect=changed), self.assertRaises(push.PushError):
            self.invoke()
        self.assertFalse(any(args[0] == "push" for args in self.calls))

    def test_local_branch_drift_after_metadata_is_rejected(self):
        actual = push.get_remote_repo_info

        def changed(*args, **kwargs):
            info = actual(*args, **kwargs)
            self.commit(self.a, "unverified later work", "later.txt")
            return info

        with patch.object(push, "get_remote_repo_info", side_effect=changed), self.assertRaises(push.PushError):
            self.invoke()
        self.assertFalse(any(args[0] == "push" for args in self.calls))

    def test_no_yes_and_malformed_branches_never_push(self):
        argv = ["safe_push.py", "--repo", str(self.a), "--remote", "origin", "--branch", "main",
                "--expected-repository", IDENTITY, "--expected-remote-sha", self.old,
                "--verified-local-sha", self.candidate]
        with patch.object(sys, "argv", argv), patch.object(push, "push") as write, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(push.main(), 1)
            write.assert_not_called()
        for branch in (None, "", "--all", "main:refs/heads/other", "refs/heads/main", "main\nother", "main\0other", "../main", "main~1"):
            with self.subTest(branch=branch), self.assertRaises(push.PushError):
                push.branch_ref(self.a, branch)

    def test_empty_repo_cli_and_api_do_not_select_cwd(self):
        argv = ["safe_push.py", "--repo", "", "--remote", "origin", "--branch", "main",
                "--expected-repository", IDENTITY, "--expected-remote-sha", self.old,
                "--verified-local-sha", self.candidate, "--yes"]
        with patch.object(sys, "argv", argv), patch.object(push, "push") as write, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(push.main(), 1)
            write.assert_not_called()
        for repo in (None, ""):
            with self.subTest(repo=repo), patch.object(push, "run") as commands, self.assertRaises(push.PushError):
                push.push(repo, "origin", "main", expected_repository=IDENTITY,
                          expected_remote_sha=self.old, verified_local_sha=self.candidate)
            commands.assert_not_called()
        argv[2] = "."
        with patch.object(sys, "argv", argv), patch.object(push, "push") as write:
            self.assertEqual(push.main(), 0)
            self.assertEqual(write.call_args.args[0], Path("."))
        argv[2] = " 合成 路径 "
        with patch.object(sys, "argv", argv), patch.object(push, "push") as write:
            self.assertEqual(push.main(), 0)
            self.assertEqual(write.call_args.args[0], Path(" 合成 路径 "))

    def test_readback_failure_and_hook_rejection_do_not_claim_success(self):
        os.environ["PUSH_HOOK_EXIT"] = "1"
        with self.assertRaises(push.PushError):
            self.invoke()
        self.assertEqual(self.sha(self.remote, "main"), self.old)
        self.assertEqual(len([args for args in self.calls if args[0] == "push"]), 1)
        self.assertTrue(self.hook_log.is_file())

    def test_url_host_binding_and_unknown_alias(self):
        url = "https://github.fixture.invalid/synthetic-owner/synthetic-repo.git"
        self.assertEqual(push.url_identity(url), tuple(IDENTITY.split("/")))
        wrong = "https://other.fixture.invalid/synthetic-owner/synthetic-repo.git"
        with patch.object(push, "selected_push_url", return_value=wrong), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(push.get_remote_repo_info(self.a, "origin", expected_repository=IDENTITY))
        self.assertFalse(self.gh_log.exists())
        with patch.object(push.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "hostname actual.fixture.invalid\n", "")):
            with self.assertRaises(push.PushError):
                push.url_identity("git@unknown-alias:synthetic-owner/synthetic-repo.git")

    def test_git_stderr_is_not_disclosed_and_missing_readback_is_unknown(self):
        actual_run = push.run
        marker = "synthetic-sensitive-git-diagnostic"

        def failed(repo, args, **kwargs):
            if args[0] == "push":
                return subprocess.CompletedProcess([], 1, marker, marker)
            return actual_run(repo, args, **kwargs)

        with patch.object(push, "run", side_effect=failed), self.assertRaises(push.PushError) as raised:
            self.invoke()
        self.assertNotIn(marker, str(raised.exception))
        actual_read = push.remote_sha
        count = 0

        def unknown(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise push.PushError("Remote readback is unavailable or ambiguous")
            return actual_read(*args, **kwargs)

        with patch.object(push, "remote_sha", side_effect=unknown), self.assertRaises(push.PushError):
            self.invoke()
        self.assertEqual(self.sha(self.remote, "main"), self.candidate)

    def test_push_instead_of_cannot_redirect_explicit_pinned_url(self):
        self.git(self.a, "config", "url." + str(self.root / "wrong.git") + ".pushInsteadOf", str(self.remote))
        # Select an explicit pushurl before freeze; the transient name must keep
        # that exact URL even in the presence of a push-only rewrite rule.
        self.git(self.a, "config", "remote.origin.pushurl", str(self.remote))
        self.invoke()
        record = json.loads(self.hook_log.read_text().strip())
        self.assertEqual(record["url"], str(self.remote))
        self.assertEqual(self.sha(self.remote, "main"), self.candidate)

    def test_pinned_url_rewrite_is_rejected_before_transport(self):
        original = push.pinned_remote_environment

        def redirected(url):
            name, env = original(url)
            self.git(self.a, "config", "url." + str(self.root / "wrong.git") + ".insteadOf", url)
            return name, env

        with patch.object(push, "pinned_remote_environment", side_effect=redirected), self.assertRaises(push.PushError):
            self.invoke()
        self.assertFalse(any(args[0] == "push" for args in self.calls))

    def test_post_preflight_config_race_cannot_redirect_push_or_readback(self):
        for location in ("local", "global", "include", "worktree"):
            with self.subTest(location=location):
                alternate = self.root / ("alternate-" + location + ".git")
                self.git(self.root, "clone", "--mirror", "--no-local", str(self.remote), str(alternate))
                included = self.root / "included.config"
                included.write_text("")
                self.git(self.a, "config", "include.path", str(included))
                self.git(self.a, "config", "extensions.worktreeConfig", "true")
                global_file = self.root / "global.config"
                global_file.write_text("")
                os.environ["GIT_CONFIG_GLOBAL"] = str(global_file)
                key = "url." + str(alternate) + ".insteadOf"
                actual = push.run
                shadows = []

                def race(repo, args, **kwargs):
                    if args[0] == "push":
                        shadows.append(Path(kwargs["env"]["GIT_COMMON_DIR"]))
                        self.assertEqual(shadows[-1].stat().st_mode & 0o777, 0o700)
                        self.assertEqual((shadows[-1] / "config").stat().st_mode & 0o777, 0o600)
                        if location == "global":
                            self.git(self.a, "config", "--global", key, str(self.remote))
                        elif location == "include":
                            self.git(self.a, "config", "--file", str(included), key, str(self.remote))
                        elif location == "worktree":
                            self.git(self.a, "config", "--worktree", key, str(self.remote))
                        else:
                            self.git(self.a, "config", key, str(self.remote))
                    return actual(repo, args, **kwargs)

                with patch.object(push, "url_identity", return_value=tuple(IDENTITY.split("/"))), \
                        patch.object(push, "run", side_effect=race), contextlib.redirect_stdout(io.StringIO()):
                    push.push(self.a, "origin", "main", expected_repository=IDENTITY,
                              expected_remote_sha=self.old, verified_local_sha=self.candidate)
                self.assertEqual(self.sha(self.remote, "main"), self.candidate)
                self.assertEqual(self.sha(alternate, "main"), self.old)
                self.assertEqual(len(shadows), 1)
                self.assertFalse(shadows[0].exists())
                # Reset only synthetic fixture state for the next independent case.
                if location == "global":
                    self.git(self.a, "config", "--global", "--unset-all", key)
                elif location == "include":
                    included.write_text("")
                elif location == "worktree":
                    self.git(self.a, "config", "--worktree", "--unset-all", key)
                else:
                    self.git(self.a, "config", "--unset-all", key)
                self.git(self.remote, "update-ref", "refs/heads/main", self.old)

    def test_forwarded_hook_retains_common_receipt_external_query_and_command_config(self):
        common = Path(self.git(self.a, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
        (common / "synthetic-release-receipt").write_text("approved")
        outside = self.root / "outside"
        outside.mkdir()
        self.git(outside, "init", "--initial-branch=main")
        relative = self.a / "relative-hooks"
        relative.mkdir()
        self.git(self.a, "config", "core.hooksPath", "relative-hooks")
        hook = relative / "pre-push"
        hook.write_text("#!" + sys.executable + "\n" +
            "import os,sys,subprocess\nfrom pathlib import Path\n" +
            "def git(*a): return subprocess.check_output(['git',*a],text=True).strip()\n" +
            "assert Path(git('rev-parse','--path-format=absolute','--git-common-dir'),'synthetic-release-receipt').read_text()=='approved'\n" +
            "assert git('config','--get','synthetic.command')=='retained-count'\n" +
            "assert git('config','--get','synthetic.parameters')=='retained-parameters'\n" +
            "assert git('config','--get','remote.'+sys.argv[1]+'.url')==sys.argv[2]\n" +
            "env=os.environ.copy()\n" +
            "for k in git('rev-parse','--local-env-vars').splitlines(): env.pop(k,None)\n" +
            "actual=subprocess.check_output(['git','-C'," + repr(str(outside)) + ",'rev-parse','--show-toplevel'],env=env,text=True).strip()\n" +
            "assert actual==" + repr(str(outside)) + "\n" +
            "assert os.getcwd()==" + repr(str(self.a)) + "\n" +
            "assert sys.stdin.read().strip().split()[1]==" + repr(self.candidate) + "\n" +
            "sys.exit(int(os.environ.get('PUSH_HOOK_EXIT','0')))\n")
        hook.chmod(0o700)
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="synthetic.command",
                          GIT_CONFIG_VALUE_0="retained-count",
                          GIT_CONFIG_PARAMETERS="'synthetic.parameters=retained-parameters'")
        self.invoke()
        self.assertEqual(self.sha(self.remote, "main"), self.candidate)
        self.git(self.remote, "update-ref", "refs/heads/main", self.old)
        os.environ["PUSH_HOOK_EXIT"] = "1"
        with self.assertRaises(push.PushError):
            self.invoke()
        self.assertEqual(self.sha(self.remote, "main"), self.old)

    def test_native_tilde_hook_path_preserves_acceptance_and_rejection_all_layouts(self):
        hookdir = self.home / "tilde-hooks"
        hookdir.mkdir()
        hook = hookdir / "pre-push"
        linked = self.root / "linked"
        self.git(self.a, "worktree", "add", "--detach", str(linked), "HEAD")
        bare = self.root / "mirror.git"
        self.git(self.root, "clone", "--mirror", "--no-local", str(self.a), str(bare))
        self.git(bare, "remote", "set-url", "origin", str(self.remote))
        for repo in (self.a, linked, bare):
            with self.subTest(repo=repo.name):
                self.git(repo, "config", "core.hooksPath", "~/tilde-hooks")
                hook.write_text("#!/bin/sh\nexit 1\n")
                hook.chmod(0o700)
                resolved = self.git(repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-push")
                self.assertEqual(Path(resolved.stdout.removesuffix("\n")), hook)
                native = self.git(repo, "push", "origin", self.candidate + ":refs/heads/main",
                                  "--force-with-lease=refs/heads/main:" + self.old, check=False)
                self.assertNotEqual(native.returncode, 0)
                self.assertEqual(self.sha(self.remote, "main"), self.old)
                with patch.object(push, "url_identity", return_value=tuple(IDENTITY.split("/"))), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaises(push.PushError):
                    push.push(repo, "origin", "main", expected_repository=IDENTITY,
                              expected_remote_sha=self.old, verified_local_sha=self.candidate)
                self.assertEqual(self.sha(self.remote, "main"), self.old)
                hook.write_text("#!/bin/sh\nexit 0\n")
                with patch.object(push, "url_identity", return_value=tuple(IDENTITY.split("/"))), \
                        contextlib.redirect_stdout(io.StringIO()):
                    push.push(repo, "origin", "main", expected_repository=IDENTITY,
                              expected_remote_sha=self.old, verified_local_sha=self.candidate)
                self.assertEqual(self.sha(self.remote, "main"), self.candidate)
                self.git(self.remote, "update-ref", "refs/heads/main", self.old)

    def test_saved_repository_identity_is_bound_to_first_url_across_aba(self):
        alternate = self.root / "B.git"
        self.git(self.root, "clone", "--mirror", "--no-local", str(self.remote), str(alternate))
        identity_b = "github.fixture.invalid/owner-b/synthetic-repo"
        metadata_b = json.loads(json.dumps(METADATA))
        metadata_b["owner"]["login"] = "owner-b"
        os.environ["GH_TEST_METADATA"] = json.dumps(metadata_b)
        identities = {str(self.remote): tuple(IDENTITY.split("/")),
                      str(alternate): tuple(identity_b.split("/"))}
        original = push.run
        queries, writes = [], []

        def aba(repo, args, **kwargs):
            if args == ["remote", "get-url", "--push", "--all", "origin"]:
                selected = alternate if len(queries) == 1 else self.remote
                self.git(self.a, "remote", "set-url", "origin", str(selected))
                queries.append(str(selected))
            if args[0] == "push":
                writes.append(args)
            return original(repo, args, **kwargs)

        with patch.object(push, "url_identity", side_effect=lambda value: identities[value]), \
                patch.object(push, "run", side_effect=aba), self.assertRaises(push.PushError):
            push.push(self.a, "origin", "main", expected_repository=identity_b,
                      expected_remote_sha=self.old, verified_local_sha=self.candidate)
        self.assertEqual(queries, [str(self.remote)])
        self.assertFalse(writes)
        self.assertFalse(self.gh_log.exists())
        self.assertEqual(self.sha(self.remote, "main"), self.old)
        self.assertEqual(self.sha(alternate, "main"), self.old)
        # Healthy control uses the real typed metadata function and a URL-specific
        # identity mapping; no constant identity or metadata-function stub.
        os.environ["GH_TEST_METADATA"] = json.dumps(METADATA)
        with patch.object(push, "url_identity", side_effect=lambda value: identities[value]), \
                contextlib.redirect_stdout(io.StringIO()):
            push.push(self.a, "origin", "main", expected_repository=IDENTITY,
                      expected_remote_sha=self.old, verified_local_sha=self.candidate)
        self.assertEqual(self.sha(self.remote, "main"), self.candidate)
        self.assertEqual(self.sha(alternate, "main"), self.old)

    def test_native_hook_executable_directory_missing_and_nonexec_parity(self):
        hook = self.a / ".git/hooks/pre-push"
        hook.unlink()
        for shape in ("directory", "healthy", "missing", "nonexec"):
            with self.subTest(shape=shape):
                if shape == "directory":
                    hook.mkdir(mode=0o700)
                elif shape in ("healthy", "nonexec"):
                    hook.write_text("#!/bin/sh\nexit " + ("0" if shape == "healthy" else "1") + "\n")
                    hook.chmod(0o700 if shape == "healthy" else 0o600)
                native = self.git(self.a, "push", "origin", self.candidate + ":refs/heads/main",
                                  "--force-with-lease=refs/heads/main:" + self.old, check=False)
                if shape == "directory":
                    self.assertNotEqual(native.returncode, 0)
                    self.assertEqual(self.sha(self.remote, "main"), self.old)
                    with self.assertRaises(push.PushError):
                        self.invoke()
                    self.assertEqual(self.sha(self.remote, "main"), self.old)
                else:
                    self.assertEqual(native.returncode, 0)
                    self.git(self.remote, "update-ref", "refs/heads/main", self.old)
                    self.invoke()
                    self.assertEqual(self.sha(self.remote, "main"), self.candidate)
                    self.git(self.remote, "update-ref", "refs/heads/main", self.old)
                if shape == "directory":
                    hook.rmdir()
                elif shape in ("healthy", "nonexec"):
                    hook.unlink()


if __name__ == "__main__":
    unittest.main()

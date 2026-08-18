"""Tests for scripts/reference_net.sh.

Every case here is a defect that actually shipped in the prose one-liner this script replaced.
The script exists because prose could not validate its inputs or name its own outcomes, so the
assertions are deliberately about *distinguishability*: the failure mode being guarded against is
"printed nothing, exited 0, looked like a clean pass", so several tests assert that two different
situations do NOT produce the same observable result.

Stdlib only, shells out to git. Not registered in scripts/ci/test-suites.txt — see the WHY NO
python-pytest RUNNER note in that file for the repository's audited reason skill-creator's suites
stay out of the shared registry; run this directly:

    python3 -m unittest daymade-skill.skill-creator.tests.test_reference_net -v
    # or, from this directory:  python3 -m unittest test_reference_net -v
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reference_net.sh"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


class ReferenceNetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        git(self.repo, "init", "-q", ".")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "T")
        (self.repo / "d.md").write_text("a\n", encoding="utf-8")
        git(self.repo, "add", "d.md")
        git(self.repo, "commit", "-qm", "init")
        self.base = git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        self._tmp.cleanup()

    def run_script(self, *args):
        env = dict(os.environ)
        env.pop("GIT_DIR", None)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.repo), capture_output=True, text=True,
            encoding="utf-8", env=env, check=False,
        )

    def add_pointer_line(self):
        (self.repo / "d.md").write_text("a\nsee discipline #6\n", encoding="utf-8")

    # ── the states that blinded the prose version ────────────────────────────

    def test_finds_pointer_when_unstaged(self):
        self.add_pointer_line()
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    def test_finds_pointer_when_staged(self):
        """Bare `git diff` shows unstaged changes only; one `git add` used to hide the edit."""
        self.add_pointer_line()
        git(self.repo, "add", "d.md")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    def test_finds_pointer_when_already_committed(self):
        """`git diff HEAD` goes empty once you commit — the check must still see the addition."""
        self.add_pointer_line()
        git(self.repo, "add", "d.md")
        git(self.repo, "commit", "-qm", "add pointer")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    # ── bad input must fail loudly, never silently ───────────────────────────

    def test_unresolvable_base_fails_loudly(self):
        """The defect this script was written for: base that does not resolve used to look clean."""
        self.add_pointer_line()
        r = self.run_script("no-such-ref", "d.md")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIn("does not resolve", r.stderr)

    def test_untracked_path_fails_loudly(self):
        r = self.run_script(self.base, "typo.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not tracked by git", r.stderr)

    def test_missing_arguments_fails_loudly(self):
        r = self.run_script(self.base)
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage:", r.stderr)

    # ── the outcomes prose collapsed into one indistinguishable "nothing" ────

    def test_no_added_lines_is_named(self):
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("IDENTICAL", r.stdout)

    def test_added_but_no_references_is_named_differently(self):
        (self.repo / "d.md").write_text("a\nplain prose, no pointers\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NONE prose-reference-shaped", r.stdout)

    def test_the_two_empty_cases_are_distinguishable(self):
        """The whole point: 'nothing changed' and 'changed, nothing matched' must not look alike."""
        nothing = self.run_script(self.base, "d.md").stdout
        (self.repo / "d.md").write_text("a\nplain prose, no pointers\n", encoding="utf-8")
        changed = self.run_script(self.base, "d.md").stdout
        self.assertNotEqual(nothing.strip(), changed.strip())

    # ── things the prose version got wrong along the way ─────────────────────

    def test_diff_header_is_not_reported_as_a_hit(self):
        """`+++ b/<path>` is a `^\\+` line; a path containing 'step2' used to self-match."""
        sub = self.repo / "step2-dir"
        sub.mkdir()
        (sub / "g.md").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "step2-dir/g.md")
        git(self.repo, "commit", "-qm", "add step2 file")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        (sub / "g.md").write_text("x\nplain prose, no pointers\n", encoding="utf-8")
        r = self.run_script(base, "step2-dir/g.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("+++", r.stdout)
        self.assertIn("NONE prose-reference-shaped", r.stdout)

    def test_markdown_links_are_out_of_scope(self):
        """Machine-resolvable links are lychee's job; this script must not re-implement it."""
        (self.repo / "d.md").write_text("a\n[text](some/path.md)\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NONE prose-reference-shaped", r.stdout)

    # ── regressions from a four-axis review (each of these once shipped green) ──

    def test_color_diff_always_does_not_hide_additions(self):
        """color.diff=always made every content line fail a `^+` match: silent false clean."""
        self.add_pointer_line()
        git(self.repo, "config", "color.diff", "always")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    def test_added_line_starting_with_plus_is_not_stripped_as_a_header(self):
        """`grep -v '^+++'` also deleted real added lines whose own text began with `++`."""
        (self.repo / "d.md").write_text("a\n++ see discipline #6 sample\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    def test_external_diff_driver_does_not_break_parsing(self):
        """An external differ replaces the unified format; --no-ext-diff must neutralise it."""
        self.add_pointer_line()
        git(self.repo, "config", "diff.external", "/usr/bin/true")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    def test_verdict_names_the_repo_relative_path_it_examined(self):
        """A bare relative name resolves against the caller's cwd; the verdict must say which
        file it actually looked at, or a same-named sibling passes for the file you edited."""
        sub = self.repo / "sub"
        sub.mkdir()
        (sub / "d.md").write_text("z\n", encoding="utf-8")
        git(self.repo, "add", "sub/d.md")
        git(self.repo, "commit", "-qm", "add sibling")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        r = subprocess.run(
            ["bash", str(SCRIPT), base, "d.md"],
            cwd=str(sub), capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sub/d.md", r.stdout)

    def test_argument_matching_several_paths_is_refused(self):
        (self.repo / "e.md").write_text("b\n", encoding="utf-8")
        git(self.repo, "add", "e.md")
        git(self.repo, "commit", "-qm", "add e")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        r = self.run_script(base, ".")
        self.assertEqual(r.returncode, 2)
        self.assertIn("matches", r.stderr)

    def test_untracked_path_is_caught_in_any_argument_position(self):
        """The guard loops over every argument; a suite that only ever passes one file would
        stay green if it were narrowed to the first."""
        self.add_pointer_line()
        r = self.run_script(self.base, "d.md", "typo.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not tracked by git", r.stderr)

    def test_every_keyword_in_the_pattern_is_covered(self):
        """Each alternation branch could be deleted and the old suite stayed green."""
        for keyword in ("see", "per", "above", "below", "rule", "discipline", "step"):
            with self.subTest(keyword=keyword):
                (self.repo / "d.md").write_text(f"a\n{keyword} 4\n", encoding="utf-8")
                r = self.run_script(self.base, "d.md")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("prose reference", r.stdout)

    def test_section_sign_keyword_is_covered(self):
        (self.repo / "d.md").write_text("a\n\u00a7 4 explains it\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertIn("prose reference", r.stdout)

    def test_matching_is_case_insensitive(self):
        """Dropping -i left the old suite green: its only fixture was all lowercase."""
        (self.repo / "d.md").write_text("a\nSee Discipline #6\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertIn("prose reference", r.stdout)

    def test_hash_before_the_number_is_optional(self):
        """Making `#` mandatory left the old suite green: its only fixture always had one."""
        (self.repo / "d.md").write_text("a\nsee rule 8 for the rest\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertIn("prose reference", r.stdout)

    def test_reported_counts_match_the_listed_hits(self):
        """Both counts were pure display fields; hardcoding them to 999 stayed green."""
        (self.repo / "d.md").write_text("a\nsee rule 1\nsee rule 2\nplain line\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertIn("2 prose reference(s) in 3 added line(s)", r.stdout)

    def test_every_listed_hit_is_printed_not_just_the_first(self):
        (self.repo / "d.md").write_text("a\nsee rule 1\nsee rule 2\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertIn("see rule 1", r.stdout)
        self.assertIn("see rule 2", r.stdout)

    def test_git_diff_failure_exits_two_not_zero(self):
        """The guard was real and reachable but untested: softening it to exit 0 stayed green."""
        self.add_pointer_line()
        blob = git(self.repo, "rev-parse", f"{self.base}:d.md").stdout.strip()
        obj = self.repo / ".git" / "objects" / blob[:2] / blob[2:]
        if not obj.exists():
            self.skipTest("object is packed; loose-object corruption not applicable here")
        obj.chmod(0o644)  # loose objects land read-only (444)
        obj.write_bytes(b"corrupted-not-a-git-object")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 2, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        self.assertIn("git diff failed", r.stderr)

    def test_deleted_from_worktree_is_not_reported_as_identical(self):
        """`rm` without `git rm` moves real content out; it must not share a verdict with 'unchanged'."""
        identical = self.run_script(self.base, "d.md").stdout
        (self.repo / "d.md").unlink()
        deleted = self.run_script(self.base, "d.md").stdout
        self.assertNotEqual(identical.strip(), deleted.strip())
        self.assertIn("no ADDED lines", deleted)

    def test_identical_file_says_identical(self):
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("IDENTICAL", r.stdout)

    def test_multiple_files_each_get_their_own_verdict(self):
        (self.repo / "e.md").write_text("b\n", encoding="utf-8")
        git(self.repo, "add", "e.md")
        git(self.repo, "commit", "-qm", "add e")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.add_pointer_line()
        r = self.run_script(base, "d.md", "e.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("d.md:", r.stdout)
        self.assertIn("e.md:", r.stdout)

    # ── config and filenames that made the diff show something other than the file ────────────

    def test_non_ascii_filename_is_not_reported_identical(self):
        """`git ls-files` C-quotes unusual names; the escaped string then matched no path at all."""
        (self.repo / "\u6587\u6863.md").write_text("a\n", encoding="utf-8")
        git(self.repo, "add", "\u6587\u6863.md")
        git(self.repo, "commit", "-qm", "add cjk")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        (self.repo / "\u6587\u6863.md").write_text("a\nsee discipline #6\n", encoding="utf-8")
        r = self.run_script(base, "\u6587\u6863.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)
        self.assertNotIn("IDENTICAL", r.stdout)
        # the verdict must name the real path, not the octal-escaped form
        self.assertIn("\u6587\u6863.md:", r.stdout)
        self.assertNotIn("\\346", r.stdout)

    def test_quote_in_filename_is_not_reported_identical(self):
        """Pure ASCII, but git C-escapes `"` unconditionally — core.quotepath=false does not help."""
        name = 'foo"bar.md'
        (self.repo / name).write_text("a\n", encoding="utf-8")
        git(self.repo, "add", name)
        git(self.repo, "commit", "-qm", "add quoted")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        (self.repo / name).write_text("a\nsee rule 7\n", encoding="utf-8")
        r = self.run_script(base, name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see rule 7", r.stdout)
        self.assertNotIn("IDENTICAL", r.stdout)

    def test_textconv_driver_cannot_hide_an_added_pointer(self):
        """A committed .gitattributes diff driver rewrote what the diff showed; --no-ext-diff misses it."""
        strip = self.repo / "strip.sh"
        strip.write_text('#!/bin/sh\nsed "s/see discipline #6/REDACTED/" "$1"\n', encoding="utf-8")
        strip.chmod(0o755)
        git(self.repo, "config", "diff.strip.textconv", str(strip))
        (self.repo / ".gitattributes").write_text("d.md diff=strip\n", encoding="utf-8")
        self.add_pointer_line()
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)

    def test_typechange_diff_header_is_not_reported_as_a_hit(self):
        """A typechange emits TWO file blocks; the second's `+++` header used to be read as content."""
        (self.repo / "sub").mkdir()
        (self.repo / "sub" / "t.txt").write_text("target\n", encoding="utf-8")
        (self.repo / "rule7.md").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "add typechange fixture")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        (self.repo / "rule7.md").unlink()
        (self.repo / "rule7.md").symlink_to("sub/t.txt")
        r = self.run_script(base, "rule7.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("+++", r.stdout)
        self.assertIn("NONE prose-reference-shaped", r.stdout)

    def test_invalid_utf8_byte_does_not_swallow_a_later_pointer(self):
        """In a UTF-8 locale awk aborts on a bad byte; the script then claimed 'no ADDED lines'."""
        (self.repo / "d.md").write_bytes(b"a\nbad \xff byte\nsee rule 8\n")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see rule 8", r.stdout)
        self.assertNotIn("no ADDED lines", r.stdout)

    # ── coverage for guarantees the suite asserted about but never exercised ──────────────────

    def test_pointer_is_found_when_invoked_from_a_subdirectory(self):
        """Without `:(top)` the diff pathspec re-resolves against cwd, matches nothing, reads clean.

        The argument is `../d.md` on purpose: that is the only shape that reaches the pathspec at
        all. A bare `d.md` from here is simply untracked and already fails loudly, which is why
        the pre-existing subdirectory test could never have caught this.
        """
        sub = self.repo / "sub"
        sub.mkdir()
        (sub / "keep.txt").write_text("k\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "add sub")
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.add_pointer_line()
        env = dict(os.environ)
        env.pop("GIT_DIR", None)
        r = subprocess.run(
            ["bash", str(SCRIPT), base, "../d.md"],
            cwd=str(sub), capture_output=True, text=True,
            encoding="utf-8", env=env, check=False,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see discipline #6", r.stdout)
        self.assertNotIn("IDENTICAL", r.stdout)

    def test_reference_to_item_zero_is_matched(self):
        """Every other fixture uses a nonzero digit, so narrowing [0-9] to [1-9] went unnoticed."""
        (self.repo / "d.md").write_text("a\nsee rule 0\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see rule 0", r.stdout)

    def test_reference_with_no_space_is_matched(self):
        """`\u00a74` is ordinary typography; every other fixture uses exactly one space."""
        (self.repo / "d.md").write_text("a\n\u00a74 covers this\n", encoding="utf-8")
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("\u00a74 covers this", r.stdout)

    def test_awk_failure_exits_two_not_zero(self):
        """The parse step is trusted for the whole verdict; if it dies the answer must not be 'clean'."""
        self.add_pointer_line()
        fake = self.repo / "fakebin"
        fake.mkdir()
        (fake / "awk").write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        (fake / "awk").chmod(0o755)
        env = dict(os.environ)
        env.pop("GIT_DIR", None)
        env["PATH"] = f"{fake}:{env['PATH']}"
        r = subprocess.run(
            ["bash", str(SCRIPT), self.base, "d.md"],
            cwd=str(self.repo), capture_output=True, text=True,
            encoding="utf-8", env=env, check=False,
        )
        self.assertEqual(r.returncode, 2, f"stdout={r.stdout!r}")
        self.assertEqual(r.stdout.strip(), "")
        self.assertIn("awk exited non-zero", r.stderr)

    # ── the two states the reader could not tell apart from the verdict alone ─────────────────

    def test_identical_names_the_stale_base_case_when_base_is_head(self):
        """`IDENTICAL` and 'my base already contains my work' printed the same line; the second is
        the likelier one right after committing, and is the only one detectable here."""
        self.add_pointer_line()
        git(self.repo, "add", "d.md")
        git(self.repo, "commit", "-qm", "commit the pointer")
        head = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        r = self.run_script(head, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("IDENTICAL", r.stdout)
        self.assertIn("also your current HEAD", r.stdout)

    def test_identical_against_an_older_base_carries_no_stale_note(self):
        """Negative control. Deliberately NOT 'unchanged file' — with no commits since setUp, base IS
        HEAD, and that state is genuinely ambiguous (nothing changed vs. already committed), so the
        note belongs there. The note must be absent only when the base is genuinely older than HEAD,
        because then IDENTICAL cannot be hiding the reader's own commit."""
        (self.repo / "other.md").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "other.md")
        git(self.repo, "commit", "-qm", "unrelated later commit")
        self.assertNotEqual(
            self.base, git(self.repo, "rev-parse", "HEAD").stdout.strip(), "base must be older"
        )
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("IDENTICAL", r.stdout)
        self.assertNotIn("also your current HEAD", r.stdout)

    def test_untracked_message_names_the_unstaged_new_file_case(self):
        """Creating a references/ file mid-edit is routine; 'typo or wrong directory' misdirects."""
        (self.repo / "brand_new.md").write_text("a\nsee rule 4\n", encoding="utf-8")
        r = self.run_script(self.base, "brand_new.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("git add", r.stderr)
        git(self.repo, "add", "brand_new.md")
        r2 = self.run_script(self.base, "brand_new.md")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("see rule 4", r2.stdout)

    # ── the vector every other test in this file structurally cannot see ─────────────────────

    def test_ambient_git_dir_is_named_not_silently_obeyed(self):
        """Every other test pops GIT_DIR, so the whole suite was blind to it. Left set, git silently
        targets another repo and a clean verdict can describe a file the caller never edited."""
        other = self.repo / "other_repo"
        other.mkdir()
        git(other, "init", "-q", ".")
        git(other, "config", "user.email", "t@example.invalid")
        git(other, "config", "user.name", "T")
        (other / "d.md").write_text("z\n", encoding="utf-8")
        git(other, "add", "d.md")
        git(other, "commit", "-qm", "init other")
        other_base = git(other, "rev-parse", "HEAD").stdout.strip()

        self.add_pointer_line()  # the REAL repo now has an unresolved pointer
        env = dict(os.environ)
        env["GIT_DIR"] = str(other / ".git")
        env["GIT_WORK_TREE"] = str(other)
        r = subprocess.run(
            ["bash", str(SCRIPT), other_base, "d.md"],
            cwd=str(self.repo), capture_output=True, text=True,
            encoding="utf-8", env=env, check=False,
        )
        self.assertIn("GIT_DIR/GIT_WORK_TREE is set", r.stdout)
        self.assertIn("other_repo", r.stdout)

    def test_no_git_dir_note_when_the_environment_is_clean(self):
        """Negative control: the note must be silent in ordinary use, or it is noise on every run."""
        self.add_pointer_line()
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("GIT_DIR", r.stdout)

    def test_ordinary_prose_containing_per_is_not_flagged(self):
        """No leading word boundary meant 'whisper9', 'paper2' and 'upper3' matched via their 'per'."""
        (self.repo / "d.md").write_text(
            "a\nwhisper9 was the codename\npaper2 describes the benchmark\n"
            "the upper3 bound was chosen\nsee rule 8 for the rest\n",
            encoding="utf-8",
        )
        r = self.run_script(self.base, "d.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("see rule 8", r.stdout)
        self.assertNotIn("whisper9", r.stdout)
        self.assertNotIn("paper2", r.stdout)
        self.assertNotIn("upper3", r.stdout)


if __name__ == "__main__":
    unittest.main()

"""CLI regressions using only temporary, synthetic Markdown and stdlib."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import profile_claude_md as profile
import sink_sections as sink


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS /var and /tmp are deliberate symlinks, not part of these cases.
        self.root = Path(self.temp.name).resolve()
        self.source = self.write('CLAUDE.md', b'# Rules\n\n## Move\nOriginal  \n\n## Keep\nKeep\n')
        self.target = self.write('reference.md', b'# Reference\nExisting  \n')
        self.snippet = self.write('snippet.md', b'## Move\n' + b'Concise rule. ' * 20 + b'\n')

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def section(self, **overrides):
        section = dict(key='move', start_heading='## Move', end_heading='## Keep',
                       snippet_file=str(self.snippet), target_ref=str(self.target),
                       provenance_title='Synthetic section')
        section.update(overrides)
        return section

    def spec(self, sections=None):
        return self.write('spec.json', json.dumps(dict(
            source=str(self.source), sections=sections or [self.section()]
        )).encode('utf-8'))

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8')

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def assert_preflight_aborts(self, spec, *args):
        before = self.snapshot()
        result = self.run_script('sink_sections.py', spec, *args)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('ABORT:', result.stderr)
        self.assertEqual(before, self.snapshot(), result.stderr)
        return result

    def test_normal_multi_section_sink_and_backups(self):
        original = self.source.read_bytes()
        old_reference = self.target.read_bytes()
        keep_snippet = self.write('keep.md', b'## Keep\n' + b'Keep rule. ' * 25 + b'\n')
        new_reference = self.root / 'new-reference.md'
        spec = self.spec([self.section(), self.section(
            key='keep', start_heading='## Keep', end_heading=None,
            snippet_file=str(keep_snippet), target_ref=str(new_reference))])
        result = self.run_script('sink_sections.py', spec)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK 2/2', result.stdout)
        self.assertEqual(self.source.read_bytes(), b'# Rules\n\n' +
                         self.snippet.read_bytes() + b'\n' + keep_snippet.read_bytes() + b'\n')
        self.assertIn(b'## Move\nOriginal  \n\n', self.target.read_bytes())
        self.assertIn(b'## Keep\nKeep\n', new_reference.read_bytes())
        self.assertTrue(self.target.read_bytes().startswith(old_reference))
        self.assertEqual(next(self.root.glob('CLAUDE.md.bak.presink.*')).read_bytes(), original)
        self.assertEqual(next(self.root.glob('reference.md.bak.*')).read_bytes(), old_reference)

    def test_crlf_lf_and_eof_whitespace_survive_verbatim(self):
        for newline in (b'\n', b'\r\n'):
            with self.subTest(newline=newline):
                original_section = b'## Move' + newline + '原文  '.encode() + newline + b'\t  '
                original_prefix = b'# Rules  ' + newline + newline
                self.source.write_bytes(original_prefix + original_section)
                snippet = b'## Move' + newline + b'Rule  ' + newline
                self.snippet.write_bytes(snippet)
                result = self.run_script('sink_sections.py', self.spec([
                    self.section(end_heading=None)]), '--min-snippet-bytes', '1')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(self.target.read_bytes().endswith(original_section))
                self.assertEqual(self.source.read_bytes(), original_prefix + snippet + newline)

    def test_both_scripts_ignore_nested_looking_fence_markers(self):
        for opening, short_close, wrong_close, closing in (
                ('````python', '```', '~~~~', '`````'),
                ('~~~~text', '~~~', '````', '~~~~~')):
            with self.subTest(opening=opening):
                original = ('## Move\n' + opening + '\n## Keep\n' + short_close +
                            '\n## Keep\n' + wrong_close + '\n## Keep\n' +
                            closing + '\nOriginal\n\n').encode()
                self.source.write_bytes(original + b'## Keep\nKept\n')
                result = self.run_script('profile_claude_md.py', self.source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('/ 2 headings', result.stdout)
                result = self.run_script('sink_sections.py', self.spec())
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(original, self.target.read_bytes())
                self.assertTrue(self.source.read_bytes().endswith(b'## Keep\nKept\n'))

    def test_fake_and_duplicate_snippet_headings_abort_before_writes(self):
        for snippet in (b'prefix ## Move suffix\n', b'## Move extra\n',
                        b'## Move  \n', b'```\n## Move\n```\n',
                        b'~~~\n## Move\n~~~\n', b'## Move\n## Move\n'):
            with self.subTest(snippet=snippet):
                self.snippet.write_bytes(snippet + b'Rule. ' * 40)
                self.assert_preflight_aborts(self.spec())

    def test_default_snippet_threshold_stays_200_bytes(self):
        self.snippet.write_bytes(b'## Move\nSmall\n')
        result = self.assert_preflight_aborts(self.spec())
        self.assertIn('<200B', result.stderr)

    def test_second_invalid_target_leaves_every_file_unchanged(self):
        directory = self.root / 'directory'
        directory.mkdir()
        parent_file = self.write('not-a-directory', b'file')
        keep_snippet = self.write('keep.md', b'## Keep\n' + b'Rule. ' * 40)
        for target in (self.root / 'missing' / 'reference.md', directory,
                       parent_file / 'reference.md'):
            with self.subTest(target=target):
                spec = self.spec([self.section(), self.section(
                    key='keep', start_heading='## Keep', end_heading=None,
                    snippet_file=str(keep_snippet), target_ref=str(target))])
                self.assert_preflight_aborts(spec)

    def test_symlink_target_and_parent_require_existing_opt_in(self):
        link = self.root / 'linked.md'
        link.symlink_to(self.target)
        parent_link = self.root / 'linked-dir'
        parent_link.symlink_to(self.root, target_is_directory=True)
        for target in (link, parent_link / self.target.name):
            with self.subTest(target=target):
                original = self.source.read_bytes()
                spec = self.spec([self.section(target_ref=str(target))])
                result = self.assert_preflight_aborts(spec)
                self.assertIn('symlink', result.stderr)
                result = self.run_script('sink_sections.py', spec, '--allow-symlinked-target')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.source.write_bytes(original)

    def test_overlap_and_duplicate_source_heading_abort_before_writes(self):
        keep_snippet = self.write('keep.md', b'## Keep\n' + b'Rule. ' * 40)
        spec = self.spec([self.section(end_heading=None), self.section(
            key='keep', start_heading='## Keep', end_heading=None,
            snippet_file=str(keep_snippet))])
        self.assertIn('overlap', self.assert_preflight_aborts(spec).stderr)
        self.source.write_bytes(self.source.read_bytes() + b'\n## Move\nDuplicate\n')
        self.assertIn('ambiguous', self.assert_preflight_aborts(self.spec()).stderr)

    def test_post_splice_heading_failure_restores_source_and_keeps_appends(self):
        original = self.source.read_bytes()
        old_reference = self.target.read_bytes()
        self.snippet.write_bytes(self.snippet.read_bytes() + b'## Keep\nNew conflict\n')
        keep_snippet = self.write('keep.md', b'## Keep\n' + b'Rule. ' * 40)
        spec = self.spec([self.section(), self.section(
            key='keep', start_heading='## Keep', end_heading=None,
            snippet_file=str(keep_snippet))])
        result = self.run_script('sink_sections.py', spec)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('found 2', result.stdout)
        self.assertIn('source rolled back', result.stderr)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertNotEqual(self.target.read_bytes(), old_reference)

    def test_whole_byte_verification_detects_lost_trailing_whitespace(self):
        original = b'## Move\r\nOriginal  \r\n\t  '
        self.source.write_bytes(original)
        spec = self.spec([self.section(end_heading=None)])
        read_bytes = Path.read_bytes

        def corrupt_reference_before_verification(path):
            if path == self.target:
                path.write_bytes(read_bytes(path).rstrip(b' \t\r\n'))
            return read_bytes(path)

        with mock.patch.object(sys, 'argv', ['sink_sections.py', str(spec)]), \
                mock.patch.object(Path, 'read_bytes', corrupt_reference_before_verification), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(SystemExit, 'source rolled back'):
                sink.main()
        self.assertIn('original not whole-string-present', output.getvalue())
        self.assertEqual(self.source.read_bytes(), original)
        self.assertNotIn(original, self.target.read_bytes())

    def test_profile_raw_utf8_bytes_physical_lines_and_empty_file(self):
        for data, count in ((b'', 0), (b'line', 1), (b'line\n', 1),
                            (b'line\n\n', 2), (b'line\r\n', 1), (b'line\r', 1),
                            (b'a\r\nb\rc\n', 3),
                            ('# 标题\r\n文本  \r\n'.encode('utf-8'), 2)):
            with self.subTest(data=data):
                self.source.write_bytes(data)
                before = self.snapshot()
                result = self.run_script('profile_claude_md.py', self.source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'TOTAL {len(data)} bytes / {count} lines', result.stdout)
                self.assertEqual(before, self.snapshot())
                self.assertNotIn('nan', result.stdout.lower())
        lines = profile.split_markdown_lines('# 标题\r\n文本  \r\n')
        rows = profile.section_table(lines, profile.parse_headings(lines))
        self.assertEqual(rows, [(1, '标题', len(''.join(lines).encode()), 2)])

    def test_inline_separators_do_not_create_lines_or_sink_boundaries(self):
        for separator in ('\u2028', '\u2029', '\x0b', '\x0c', '\x85',
                          '\x1c', '\x1d', '\x1e'):
            with self.subTest(separator=repr(separator)):
                data = ('## Move\nParagraph' + separator + '## Keep\nTail\n').encode('utf-8')
                self.source.write_bytes(data)
                result = self.run_script('profile_claude_md.py', self.source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'TOTAL {len(data)} bytes / 3 lines / 1 headings', result.stdout)
                result = self.assert_preflight_aborts(self.spec())
                self.assertIn('end heading not found', result.stderr)

    def test_inline_separator_cannot_make_a_snippet_heading(self):
        self.snippet.write_bytes(('Paragraph\u2028## Move\n' + 'Rule. ' * 40).encode('utf-8'))
        result = self.assert_preflight_aborts(self.spec())
        self.assertIn('snippet start heading not found', result.stderr)


if __name__ == '__main__':
    unittest.main()

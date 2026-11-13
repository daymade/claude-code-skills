#!/usr/bin/env python3
"""Exercise the public CLI and every parser against isolated filesystem targets."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'unmix_repomix.py'
SPEC = importlib.util.spec_from_file_location('unmix_repomix', SCRIPT)
UNMIX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UNMIX)
FORMATS = ('xml', 'markdown', 'json')


def archive(format_name, entries):
    if format_name == 'json':
        return json.dumps({'files': [dict(path=path, content=text) for path, text in entries]})
    if format_name == 'xml':
        return '\n'.join(f'<file path="{path}">\n{text}\n</file>' for path, text in entries)
    return '\n'.join(f'## File: {path}\n```text\n{text}\n```' for path, text in entries)


class UnmixTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()

    def extract(self, format_name, entries, output):
        with contextlib.redirect_stdout(io.StringIO()):
            return getattr(UNMIX, 'unmix_' + format_name)(archive(format_name, entries), output)

    def cli(self, format_name, entries, output=None, script=SCRIPT):
        source = self.base / ('archive.' + format_name)
        source.write_text(archive(format_name, entries), encoding='utf-8')
        command = [sys.executable, str(script), str(source)]
        if output is not None:
            command.append(str(output))
        return subprocess.run(command, cwd=self.base, text=True, capture_output=True, check=False)

    def test_valid_relative_files_and_overwrite(self):
        entries = [('nested/hello.txt', 'hello\nworld'), ('文档/my file.txt', 'café'), ('empty.txt', '')]
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                output = self.base / format_name
                output.mkdir()
                (output / 'empty.txt').write_text('previous')
                self.assertEqual(self.extract(format_name, entries, output), [p for p, _ in entries])
                for path, text in entries:
                    self.assertEqual((output / path).read_text(encoding='utf-8'), text)

    def test_unsafe_paths_reject_entire_archive_before_writes(self):
        sentinel = self.base / 'sentinel.txt'
        sentinel.write_text('ORIGINAL')
        bad_paths = [
            '../sentinel.txt', 'nested/../../sentinel.txt', str(sentinel),
            'safe/../file.txt', '..\\sentinel.txt', 'safe\\file.txt',
            'C:/sentinel.txt', 'C:sentinel.txt', '//server/share/file',
            '\\\\server\\share\\file', '', '.', './', 'null\x00file',
        ]
        for format_name in FORMATS:
            for bad_path in bad_paths:
                with self.subTest(format=format_name, path=bad_path):
                    output = self.base / 'new-output'
                    with self.assertRaisesRegex(ValueError, 'Rejected'):
                        self.extract(format_name, [('valid.txt', 'valid'), (bad_path, 'ATTACK')], output)
                    self.assertFalse(output.exists())
                    self.assertEqual(sentinel.read_text(), 'ORIGINAL')

    def test_invalid_late_entry_preserves_existing_valid_file(self):
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                output = self.base / format_name
                output.mkdir()
                target = output / 'valid.txt'
                target.write_text('ORIGINAL')
                with self.assertRaises(ValueError):
                    self.extract(format_name, [('valid.txt', 'CHANGED'), ('../outside.txt', 'ATTACK')], output)
                self.assertEqual(target.read_text(), 'ORIGINAL')
        self.assertFalse((self.base / 'outside.txt').exists())

    def test_reports_all_rejected_paths(self):
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                with self.assertRaises(ValueError) as error:
                    self.extract(format_name, [('../one', 'a'), ('../two', 'b')], self.base / 'out')
                self.assertIn('../one', str(error.exception))
                self.assertIn('../two', str(error.exception))

    def test_directory_and_file_symlinks_are_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        sentinel = outside / 'sentinel.txt'
        sentinel.write_text('ORIGINAL')
        for format_name in FORMATS:
            for kind in ('directory', 'file', 'dangling', 'inside'):
                with self.subTest(format=format_name, kind=kind):
                    output = self.base / (format_name + '-' + kind)
                    output.mkdir()
                    link = output / 'link'
                    if kind == 'directory':
                        link.symlink_to(outside, target_is_directory=True)
                        path = 'link/sentinel.txt'
                    elif kind == 'inside':
                        (output / 'real').mkdir()
                        link.symlink_to(output / 'real', target_is_directory=True)
                        path = 'link/file.txt'
                    else:
                        link.symlink_to(sentinel if kind == 'file' else outside / 'missing.txt')
                        path = 'link'
                    with self.assertRaises(ValueError):
                        self.extract(format_name, [('first.txt', 'valid'), (path, 'ATTACK')], output)
                    self.assertFalse((output / 'first.txt').exists())
                    self.assertEqual(sentinel.read_text(), 'ORIGINAL')
                    self.assertFalse((outside / 'missing.txt').exists())

    def test_symlinked_output_root_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                output = self.base / (format_name + '-link')
                output.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'output directory'):
                    self.extract(format_name, [('file.txt', 'ATTACK')], output)
                self.assertEqual(list(outside.iterdir()), [])

    def test_dangling_output_root_is_rejected(self):
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                output = self.base / (format_name + '-link')
                output.symlink_to(self.base / 'missing', target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'output directory'):
                    self.extract(format_name, [('file.txt', 'ATTACK')], output)
                self.assertFalse((self.base / 'missing').exists())

    def test_file_and_directory_conflicts_are_preflighted(self):
        for format_name in FORMATS:
            for path in ('directory', 'file/child.txt'):
                with self.subTest(format=format_name, path=path):
                    output = self.base / (format_name + path.replace('/', '-'))
                    output.mkdir()
                    (output / 'directory').mkdir()
                    (output / 'file').write_text('ORIGINAL')
                    with self.assertRaises(ValueError):
                        self.extract(format_name, [('first.txt', 'valid'), (path, 'ATTACK')], output)
                    self.assertFalse((output / 'first.txt').exists())
                    self.assertEqual((output / 'file').read_text(), 'ORIGINAL')

    def test_missing_json_path_is_rejected(self):
        for entry in ({}, {'path': None}, {'path': 42}):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    UNMIX.unmix_json(json.dumps({'files': [entry]}), self.base / 'out')
        self.assertFalse((self.base / 'out').exists())

    def test_cli_rejects_attack_with_nonzero_status(self):
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                result = self.cli(format_name, [('good.txt', 'good'), ('../outside.txt', 'ATTACK')], self.base / 'out')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('../outside.txt', result.stderr)
                self.assertNotIn('Successfully extracted', result.stdout)
                self.assertFalse((self.base / 'out').exists())
                self.assertFalse((self.base / 'outside.txt').exists())

    def test_cli_detects_formats_and_keeps_default_output(self):
        for format_name in FORMATS:
            with self.subTest(format=format_name):
                result = self.cli(format_name, [('hello.txt', format_name)])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Successfully extracted 1 files', result.stdout)
                self.assertEqual((self.base / 'extracted' / 'hello.txt').read_text(), format_name)

    def test_source_backed_entry_with_spaces(self):
        entry = self.base / 'installed skill' / 'unmix_repomix.py'
        entry.parent.mkdir()
        entry.symlink_to(SCRIPT)
        result = self.cli('json', [('nested/file.txt', 'restored')], self.base / 'output with spaces', script=entry)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.base / 'output with spaces/nested/file.txt').read_text(), 'restored')


if __name__ == '__main__':
    unittest.main()

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
RECIPES = (
    ('SKILL.md', '**3. Fetch the body'),
    ('references/lark-cli-api-extraction.md', 'The body field moved between'),
)
CASES = (
    ('empty_outline', {'data': {'document': {'content': '<fragment mode="outline"><outline></outline></fragment>'}}}, 0, False),
    ('healthy_text', {'data': {'document': {'content': '<p>Healthy synthetic body</p>'}}}, 0, True),
    ('legacy_markdown', {'data': {'markdown': 'Healthy synthetic body'}}, 0, True),
    ('media_only', {'data': {'document': {'content': '<img src="https://example.invalid/synthetic.png" alt="synthetic">'}}}, 0, True),
    ('missing_body', {'data': {}}, 0, False),
    ('empty_body', {'data': {'document': {'content': ''}}}, 0, False),
    ('whitespace_markdown', {'data': {'markdown': ' \n\t '}}, 0, False),
    ('whitespace_html', {'data': {'document': {'content': '<p> \n\t </p>'}}}, 0, False),
    ('failed_fetch', {}, 77, False),
)


@unittest.skipUnless(shutil.which('pandoc') and shutil.which('jq'), 'documented recipe dependencies required')
class DocumentedBodyRecipeTests(unittest.TestCase):
    def test_actual_snippets_fail_closed_and_preserve_existing_notes(self):
        observed = 0
        for relative, marker in RECIPES:
            text = (SKILL_ROOT / relative).read_text()
            block = text[text.index(marker):].split('```bash\n', 1)[1].split('\n```', 1)[0]
            for name, data, fetch_exit, succeeds in CASES:
                for preexisting in (False, True):
                    with self.subTest(recipe=relative, case=name, preexisting=preexisting):
                        with tempfile.TemporaryDirectory(prefix='documented-recipe-') as folder:
                            work = Path(folder)
                            input_path = work / 'input.json'
                            input_path.write_text(json.dumps(data))
                            fetch = work / 'fetch.py'
                            fetch.write_text(
                                'from pathlib import Path\n'
                                'import sys\n'
                                'print(Path(sys.argv[1]).read_text())\n'
                                f'sys.exit({fetch_exit})\n'
                            )
                            script = block.replace(
                                'lark-cli',
                                f'{shlex.quote(sys.executable)} {shlex.quote(str(fetch))} {shlex.quote(str(input_path))}',
                            )
                            script = script.replace('<obj_token>', 'synthetic_doc')
                            script = script.replace('/tmp/fetch.json', str(work / 'fetch.json'))
                            script = script.replace('/tmp/fetch.err', str(work / 'fetch.err'))
                            script = script.replace('<sanitized-title>', 'note')
                            note = work / 'note.md'
                            original = b'KEEP SYNTHETIC ORIGINAL\n'
                            if preexisting:
                                note.write_bytes(original)
                            result = subprocess.run(['bash', '-c', script], cwd=work, capture_output=True)
                            observed += 1
                            if preexisting:
                                self.assertNotEqual(result.returncode, 0, result.stderr.decode())
                                self.assertEqual(note.read_bytes(), original)
                            elif succeeds:
                                self.assertEqual(result.returncode, 0, result.stderr.decode())
                                self.assertTrue(note.read_text().strip())
                                self.assertEqual(list(work.glob('*.tmp.*')), [])
                                if name in ('healthy_text', 'media_only'):
                                    self.assertIn(data['data']['document']['content'], (work / 'note.html').read_text())
                            else:
                                self.assertNotEqual(result.returncode, 0, result.stderr.decode())
                                self.assertFalse(note.exists())
        self.assertEqual(observed, len(RECIPES) * len(CASES) * 2)


if __name__ == '__main__':
    unittest.main()

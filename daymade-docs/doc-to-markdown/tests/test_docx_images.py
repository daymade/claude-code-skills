"""Resolve real Pandoc image references from the delivered Markdown directory."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/convert.py'


class DocxImagePaths(unittest.TestCase):
    def test_cli_keeps_images_resolvable_with_default_and_custom_assets(self):
        with tempfile.TemporaryDirectory(prefix='Word image paths ') as folder:
            root = Path(folder)
            image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
            (root / 'figure.png').write_bytes(image)
            (root / 'source.md').write_text('1. First question\n2. Second question\n\n![Reference figure](figure.png)\n')
            source = root / 'case questions.docx'
            subprocess.run(['pandoc', 'source.md', '-o', str(source)], cwd=root, check=True, capture_output=True)
            original = source.read_bytes()
            for name, assets in [('default', None), ('relative', 'shared assets'), ('absolute', str(root / 'external assets')), ('media', 'media')]:
                with self.subTest(assets=name):
                    output_dir = root / name
                    output_dir.mkdir()
                    output = output_dir / 'reading note.md'
                    command = [sys.executable, str(SCRIPT), str(source), '--tool', 'pandoc', '-o', str(output)]
                    if assets is not None:
                        command.extend(['--assets-dir', assets])
                    subprocess.run(command, cwd=output_dir, check=True, capture_output=True)
                    ast = json.loads(subprocess.run(['pandoc', str(output), '-f', 'markdown', '-t', 'json'], check=True, capture_output=True, text=True).stdout)
                    targets = []

                    def visit(node):
                        if isinstance(node, dict):
                            if node.get('t') == 'Image':
                                targets.append(node['c'][2][0])
                            for child in node.values():
                                visit(child)
                        elif isinstance(node, list):
                            for child in node:
                                visit(child)

                    visit(ast)
                    self.assertEqual(len(targets), 1)
                    target = Path(unquote(targets[0]))
                    self.assertFalse(target.is_absolute())
                    self.assertEqual((output_dir / target).read_bytes(), image)
                    self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()

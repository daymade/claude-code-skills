"""Synthetic OOXML controls; no customer documents are included."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from docx_numbering import W, normalize_numbering_xml, pandoc_input, source_numbering
from convert import convert_with_pandoc
from validate_output import validate_conversion


def level(index=0, start=1, extra="", implicit=False, fmt="decimal"):
    attr = '' if implicit else f' w:ilvl="{index}"'
    return (f'<w:lvl{attr}><w:start w:val="{start}"/>'
            f'<w:numFmt w:val="{fmt}"/><w:lvlText w:val="%{index + 1}."/>'
            f'{extra}</w:lvl>')


def paragraph(text, num="1", depth=0, props=None):
    props = (f'<w:numPr><w:ilvl w:val="{depth}"/><w:numId w:val="{num}"/></w:numPr>'
             if props is None and num is not None else props or '')
    return f'<w:p><w:pPr>{props}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'


class NumberingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(['pandoc', '-f', 'gfm', '-t', 'docx'], input=b'Base',
                                capture_output=True, check=True)
        cls.base_zip = result.stdout

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='numbering controls ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source document.docx'
        self.output = self.root / 'reading note.md'

    def make_source(self, paragraphs, lvls=None, overrides='', extra_nums='', style=''):
        import io
        numbering = (f'<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0">'
                     f'{lvls if lvls is not None else level()}</w:abstractNum>'
                     '<w:num w:numId="1"><w:abstractNumId w:val="0"/>'
                     f'{overrides}</w:num>{extra_nums}</w:numbering>')
        with zipfile.ZipFile(io.BytesIO(self.base_zip)) as base, zipfile.ZipFile(self.source, 'w') as out:
            for entry in base.infolist():
                data = base.read(entry.filename)
                if entry.filename == 'word/document.xml':
                    data = f'<w:document xmlns:w="{W}"><w:body>{paragraphs}</w:body></w:document>'.encode()
                elif entry.filename == 'word/numbering.xml':
                    continue
                elif entry.filename == 'word/styles.xml' and style:
                    data = data.replace(b'</w:styles>', style.encode() + b'</w:styles>')
                out.writestr(entry, data)
            out.writestr('word/numbering.xml', numbering)

    def compare(self, markdown):
        self.output.write_text(markdown)
        return validate_conversion(self.source, self.output)

    def test_missing_single_level_is_repaired_without_changing_original_or_other_parts(self):
        self.make_source(paragraph('First') + paragraph('Second'), level(implicit=True))
        original = self.source.read_bytes()
        with pandoc_input(self.source) as copy:
            self.assertNotEqual(copy, self.source)
            with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(copy) as after:
                self.assertEqual(before.namelist(), after.namelist())
                for name in before.namelist():
                    if name != 'word/numbering.xml':
                        self.assertEqual(before.read(name), after.read(name), name)
                self.assertIn(b'w:ilvl="0"', after.read('word/numbering.xml'))
                self.assertNotIn(b'ns0:', after.read('word/numbering.xml'))
        self.assertFalse(copy.exists())
        result = convert_with_pandoc(self.source)
        self.assertTrue(result.success, result.error)
        metrics = self.compare(result.markdown)
        self.assertEqual(metrics.status, 'pass', metrics.errors or metrics.differences)
        self.assertEqual(metrics.source_numbered_item_count, 2)
        self.assertTrue(metrics.numbering_equal)
        self.assertEqual(self.source.read_bytes(), original)

    def test_shared_parser_loss_is_detected_by_original_ooxml_check(self):
        self.make_source(paragraph('First') + paragraph('Second'), level(implicit=True))
        # This is the real failure shape: Pandoc emits body paragraphs without labels.
        run = subprocess.run(['pandoc', str(self.source), '-t', 'gfm'], capture_output=True,
                             text=True, check=True)
        metrics = self.compare(run.stdout)
        self.assertEqual(metrics.source_numbered_item_count, 2)
        self.assertEqual(metrics.output_numbered_item_count, 0)
        self.assertFalse(metrics.numbering_equal)
        self.assertEqual(metrics.status, 'fail')

    def test_missing_wrong_ordinal_and_wrong_level_fail(self):
        self.make_source(paragraph('First') + paragraph('Second'))
        self.assertTrue(self.compare('1. First\n2. Second\n').numbering_equal)
        for broken in ['First\n\nSecond', '3. First\n4. Second\n', '1. First\n   1. Second\n']:
            with self.subTest(broken=broken):
                metrics = self.compare(broken)
                self.assertFalse(metrics.numbering_equal)
                self.assertEqual(metrics.status, 'fail')

    def test_nesting_default_restart_and_start_override(self):
        self.make_source(paragraph('OuterA') + paragraph('InnerA', depth=1)
                         + paragraph('OuterB') + paragraph('InnerB', depth=1), level() + level(1))
        records = source_numbering(self.source)
        self.assertEqual([(r['level'], r['value']) for r in records], [(0, 1), (1, 1), (0, 2), (1, 1)])
        self.assertTrue(self.compare('1. OuterA\n   1. InnerA\n2. OuterB\n   1. InnerB\n').numbering_equal)
        self.assertFalse(self.compare('1. OuterA\n   1. InnerA\n2. OuterB\n   2. InnerB\n').numbering_equal)
        self.make_source(paragraph('First') + paragraph('Second'), overrides=
                         '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="5"/></w:lvlOverride>')
        self.assertEqual([r['value'] for r in source_numbering(self.source)], [5, 6])
        self.assertTrue(self.compare('5. First\n6. Second\n').numbering_equal)

    def test_never_restart_and_distinct_instances(self):
        self.make_source(paragraph('OuterA') + paragraph('InnerA', depth=1)
                         + paragraph('OuterB') + paragraph('InnerB', depth=1),
                         level() + level(1, extra='<w:lvlRestart w:val="0"/>'))
        self.assertEqual([r['value'] for r in source_numbering(self.source)], [1, 1, 2, 2])
        self.make_source(paragraph('First') + paragraph('Restart', num='2'), extra_nums=
                         '<w:num w:numId="2"><w:abstractNumId w:val="0"/></w:num>')
        self.assertEqual([r['value'] for r in source_numbering(self.source)], [1, 1])

    def test_inherited_style_and_explicit_removal(self):
        style = ('<w:style w:type="paragraph" w:styleId="NumberBase"><w:pPr><w:numPr>'
                 '<w:numId w:val="1"/></w:numPr></w:pPr></w:style>'
                 '<w:style w:type="paragraph" w:styleId="NumberChild">'
                 '<w:basedOn w:val="NumberBase"/></w:style>')
        self.make_source(paragraph('Inherited', props='<w:pStyle w:val="NumberChild"/>')
                         + paragraph('Plain', props='<w:pStyle w:val="NumberChild"/>'
                                     '<w:numPr><w:numId w:val="0"/></w:numPr>'), style=style)
        self.assertEqual(source_numbering(self.source), [{'level': 0, 'value': 1, 'text': 'Inherited'}])

    def test_ordinary_and_literal_numbered_text_are_not_false_failures(self):
        self.make_source(paragraph('No numbering', num=None))
        result = self.compare('No numbering')
        self.assertEqual(result.status, 'pass', result.errors)
        self.assertEqual(result.source_numbered_item_count, 0)
        self.assertIsNone(result.numbering_equal)
        with pandoc_input(self.source) as copy:
            self.assertEqual(copy, self.source)
        self.make_source(paragraph('1. Literal', num=None) + paragraph('Generated'))
        self.assertTrue(self.compare('1. Literal\n\n<!-- split -->\n\n1. Generated').numbering_equal)

    def test_ambiguous_missing_levels_and_unknown_formats_are_explicit(self):
        self.make_source(paragraph('First'), level(implicit=True) + level(1, implicit=True))
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            convert = normalize_numbering_xml(zipfile.ZipFile(self.source).read('word/numbering.xml'))
        self.assertFalse(convert_with_pandoc(self.source).success)
        self.make_source(paragraph('First'), level(fmt='upperRoman'))
        result = self.compare('I. First')
        self.assertEqual(result.status, 'fail')
        self.assertIn('scoped/native check', result.errors[0])

    def test_normalization_is_idempotent_and_override_uses_its_own_level(self):
        xml = (f'<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0">{level()}</w:abstractNum>'
               '<w:num w:numId="1"><w:lvlOverride w:ilvl="2">'
               f'{level(2, implicit=True)}</w:lvlOverride></w:num></w:numbering>').encode()
        result = normalize_numbering_xml(xml)
        self.assertIn(b'<w:lvl w:ilvl="2">', result)
        self.assertEqual(normalize_numbering_xml(result), result)

    def test_multi_paragraph_item_binds_only_its_numbered_paragraph(self):
        markdown = '1. First\n\n   Continuation of first item.\n\n2. Second\n'
        subprocess.run(['pandoc', '-f', 'gfm', '-t', 'docx', '-o', str(self.source)],
                       input=markdown, capture_output=True, text=True, check=True)
        good = self.compare(markdown)
        self.assertTrue(good.text_equal)
        self.assertEqual(good.source_numbered_item_count, 2)
        self.assertEqual(good.output_numbered_item_count, 2)
        self.assertTrue(good.numbering_equal)
        self.assertEqual(good.status, 'pass', good.errors)
        # Removing a label must still fail; removing continuation text is a
        # separate body-text defect even when both list ordinals survive.
        missing = self.compare('First\n\nContinuation of first item.\n\n2. Second\n')
        self.assertFalse(missing.numbering_equal)
        self.assertEqual(missing.status, 'fail')
        truncated = self.compare('1. First\n2. Second\n')
        self.assertTrue(truncated.numbering_equal)
        self.assertNotEqual(truncated.status, 'pass')


if __name__ == '__main__':
    unittest.main()

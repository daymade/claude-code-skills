import io
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import archive_attachments as archive
import feishu_extract_refs as refs
import render_api_capture as render

SOURCE = 'https://example.feishu.cn/wiki/SyntheticDocumentToken12345'
TOKEN = 'SyntheticAttachmentToken000001'


def xlsx():
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="urn:synthetic"><sheets><sheet name="Sheet1" sheetId="1"/></sheets></workbook>')
    return b.getvalue()


def card(token=TOKEN, name='template.xlsx', size=None):
    return f'<figure><source token="{token}" name="{name}" size="{len(xlsx()) if size is None else size}" mime="application/xlsx"/></figure>'


class AttachmentReferences(unittest.TestCase):
    def test_observed_card_shape_sanitized_full_capture(self):
        # The layout/attribute shapes come from a real capture; identities/text are synthetic.
        body = (Path(__file__).parent / 'fixtures/source-cards.html').read_text()
        found = refs.extract(body)
        self.assertEqual(len(found), 31)
        self.assertEqual({r['type'] for r in found}, {'file'})
        self.assertEqual({r['ref'] for r in found}, {f'SyntheticAttachmentToken{i:06d}' for i in range(1, 32)})
        self.assertEqual([r['title'] for r in found], [f'{i:02d}_template.xlsx' for i in range(1, 32)])
        self.assertTrue(all(r['size'].isdigit() and r['mime'] for r in found))
        self.assertEqual(render.document_title({'content': body}, 'index'), 'Attachment toolkit')

    def test_attribute_order_quotes_entities_and_missing_token(self):
        r = refs.extract(f"<source size='7' name='a&amp;b.xlsx' token='{TOKEN}'/>")[0]
        self.assertEqual(r['title'], 'a&b.xlsx')
        self.assertEqual(r['size'], '7')
        self.assertEqual(refs.extract('<source name="missing.xlsx"/>')[0]['type'], 'unresolved-attachment')
        self.assertEqual(refs.extract('<p>Text only.</p>'), [])

    def test_existing_reference_variants_survive(self):
        body = ('<cite doc-id="doc" file-type="docx" title="Doc"></cite>'
                '<mention-doc token="wiki" type="wiki">Wiki</mention-doc>'
                '<img src="image"/><image token="legacy-image"/>'
                '<whiteboard token="board"/><sheet token="sheet_tab"/>'
                '<file token="legacy-file">report.pdf</file>')
        self.assertEqual({r['ref'] for r in refs.extract(body)},
                         {'doc', 'wiki', 'image', 'legacy-image', 'board', 'sheet_tab', 'legacy-file'})

    def test_title_attributes_entities_and_fallback(self):
        self.assertEqual(render.document_title({'content': '<TITLE id="x">A &amp; B</TITLE>'}, 'index'), 'A & B')
        self.assertEqual(render.document_title({'title': 'Explicit', 'content': '<title>Other</title>'}, 'index'), 'Explicit')
        for body in ('', '<title id="x"> </title>', '<h1>Heading</h1>'):
            self.assertEqual(render.document_title({'content': body}, 'index'), 'index')

    def test_residual_worklist_in_both_instructions_catches_cards(self):
        skill = SCRIPTS.parent
        for path in (skill / 'SKILL.md', skill / 'references/lark-cli-api-extraction.md'):
            pattern = re.search(r"grep -rlE '([^']+)'", path.read_text())[1]
            self.assertRegex(card(), pattern)


class AttachmentArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.capture = self.root / 'input.json'
        self.output = self.root / 'archive'
        self.calls = []
        self.cli = patch.object(archive.shutil, 'which', return_value='lark-cli')
        self.cli.start()

    def tearDown(self):
        self.cli.stop()
        self.temp.cleanup()

    def save(self, content=None):
        self.capture.write_text(json.dumps({'ok': True, 'data': {'document': {
            'document_id': 'SyntheticDocumentToken12345', 'revision_id': 1,
            'content': content or card()}}}))

    def run_cli(self, cmd, **kw):
        self.calls.append(cmd)
        self.assertEqual(cmd[cmd.index('--as')+1], 'user')
        self.assertEqual(kw['env']['LARK_CLI_NO_PROXY'], '1')
        target = Path(kw['cwd']) / cmd[cmd.index('--output')+1]
        target.write_bytes(xlsx())
        return subprocess.CompletedProcess(cmd, 0, json.dumps({'ok': True}), '')

    def test_download_verify_manifest_and_resume(self):
        self.save()
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            result = archive.archive(self.capture, self.output, SOURCE, workers=1)
            self.assertEqual(result['status'], 'attachments_complete')
            self.assertEqual(result['verified'], 1)
            self.assertEqual(result['reader'], 'not_checked')
            self.assertEqual(result['independent_retention'], 'not_checked')
            saved = json.loads((self.output/'manifest.json').read_text())
            self.assertEqual(archive.validate_manifest(saved), [])
            self.assertEqual(saved['files'][0]['storage'], 'source')
            self.assertEqual(saved['files'][0]['mime'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.assertEqual((self.output/'capture.json').read_bytes(), self.capture.read_bytes())
            archive.archive(self.capture, self.output, SOURCE, workers=1, resume=True)
            self.assertEqual(len(self.calls), 1)
            state = json.loads((self.output/'attachment-state.json').read_text())
            self.assertEqual(state['items'][0]['worksheets'][0]['name'], 'Sheet1')

    def test_partial_failure_retains_success_and_pending_references(self):
        other = 'SyntheticAttachmentToken000002'
        self.save(card()+card(other, 'second.xlsx')+'<file token="legacy">old.pdf</file><cite doc-id="child" file-type="docx"/>')
        def run(cmd, **kw):
            if cmd[cmd.index('--token')+1] == other:
                return subprocess.CompletedProcess(cmd, 1, '', 'permission denied')
            return self.run_cli(cmd, **kw)
        with patch.object(archive.subprocess, 'run', side_effect=run):
            result = archive.archive(self.capture, self.output, SOURCE, workers=1)
        self.assertEqual((result['status'], result['verified'], result['failed']), ('partial', 1, 1))
        self.assertEqual(result['other_references'], 2)
        self.assertFalse((self.output/'attachments/second.xlsx').exists())
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            result = archive.archive(self.capture, self.output, SOURCE, workers=1, resume=True)
        self.assertEqual(result['verified'], 2)
        self.assertEqual(len(self.calls), 2)

    def test_missing_empty_null_metadata_and_filename_collisions(self):
        valid = dict(refs.attachment_sources(card())[0])
        for field in ('token', 'name', 'size'):
            for value in (None, ''):
                attrs = {**valid, field: value}
                text = '<source '+ ' '.join(f'{k}="{v}"' for k,v in attrs.items() if v is not None)+'/>'
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    archive.inventory(text)
        for name in ('../outside.xlsx', 'sub/file.xlsx', 'a\\b.xlsx', 'CON.xlsx', 'tail.xlsx '):
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive.inventory(card(name=name))
        with self.assertRaisesRegex(ValueError, 'filename'):
            archive.inventory(card()+card('SyntheticAttachmentToken000002', 'TEMPLATE.xlsx'))
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            archive.inventory(card()+card(name='different.xlsx'))
        self.assertEqual(len(archive.inventory(card()+card())), 1)

    def test_wrong_bytes_and_false_success_do_not_publish(self):
        self.save(card(size=1))
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            result = archive.archive(self.capture, self.output, SOURCE, workers=1)
        self.assertEqual(result['failed'], 1)
        self.assertFalse((self.output/'attachments/template.xlsx').exists())

    def test_missing_cli_and_null_capture_fail_before_output(self):
        self.save()
        with patch.object(archive.shutil, 'which', return_value=None), self.assertRaisesRegex(ValueError, 'required'):
            archive.archive(self.capture, self.output, SOURCE)
        self.assertFalse(self.output.exists())
        for data in (None, [], {'ok': True}, {'ok': True, 'data': None},
                     {'ok': True, 'data': {'document': None}},
                     {'ok': True, 'data': {'document': {'content': ''}}}):
            self.capture.write_text(json.dumps(data))
            with self.subTest(data=data), self.assertRaises(ValueError):
                archive.archive(self.capture, self.output, SOURCE)
            self.assertFalse(self.output.exists())

    def test_cli_false_success_and_zero_without_file_remain_partial(self):
        self.save()
        for index, reply in enumerate(({'ok': False}, {'ok': True}, [], None, 'unexpected')):
            with patch.object(archive.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(reply), '')):
                result = archive.archive(self.capture, self.root/f'output-{index}', SOURCE)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['verified'], 0)

    def test_enriched_manifest_survives_resume(self):
        other = 'SyntheticAttachmentToken000002'
        self.save(card()+card(other, 'second.xlsx'))
        def partial(cmd, **kw):
            if cmd[cmd.index('--token')+1] == other:
                return subprocess.CompletedProcess(cmd, 1, '', 'transient')
            return self.run_cli(cmd, **kw)
        with patch.object(archive.subprocess, 'run', side_effect=partial):
            self.assertEqual(archive.archive(self.capture, self.output, SOURCE)['status'], 'partial')
        path = self.output/'manifest.json'; m = json.loads(path.read_text())
        original = m['files'][0]
        original['replicas'] = [{'storage': 'oss', 'locator': {'system': 'oss', 'uri': 'oss://synthetic-bucket/object'}}]
        note = b'# index\n'; (self.output/'index.md').write_bytes(note)
        m['files'].append({'role':'document_snapshot','storage':'git','path':'index.md',
                          'bytes':len(note),'sha256':hashlib.sha256(note).hexdigest(),'mime':'text/markdown'})
        m['resource_summary']['owner_annotation'] = 'retained'
        path.write_text(json.dumps(m))
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            self.assertEqual(archive.archive(self.capture, self.output, SOURCE, resume=True)['verified'], 2)
        actual = json.loads(path.read_text())
        self.assertEqual(actual['files'][0], original)
        self.assertIn(m['files'][-1], actual['files'])
        self.assertEqual(actual['resource_summary']['owner_annotation'], 'retained')
        self.assertEqual(archive.validate_manifest(actual), [])

    def test_malformed_response_does_not_lose_other_successful_items(self):
        other = 'SyntheticAttachmentToken000002'
        self.save(card()+card(other, 'second.xlsx'))
        def run(cmd, **kw):
            if cmd[cmd.index('--token')+1] == TOKEN:
                return subprocess.CompletedProcess(cmd, 0, '[]', '')
            return self.run_cli(cmd, **kw)
        with patch.object(archive.subprocess, 'run', side_effect=run):
            result = archive.archive(self.capture, self.output, SOURCE, workers=2)
        self.assertEqual((result['verified'], result['failed']), (1, 1))
        state = json.loads((self.output/'attachment-state.json').read_text())
        self.assertEqual(len(state['items']), 2)
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            result = archive.archive(self.capture, self.output, SOURCE, resume=True)
        self.assertEqual(result['verified'], 2)
        self.assertEqual(len(self.calls), 2)

    def test_corrupt_zip_rejected(self):
        f = self.root/'broken.xlsx'
        f.write_bytes(b'not an office file')
        with self.assertRaises(zipfile.BadZipFile):
            archive.verify_file(f, {'size': f.stat().st_size})

    def test_resume_never_overwrites_changed_file_or_changed_binding(self):
        self.save()
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            archive.archive(self.capture, self.output, SOURCE, workers=1)
        target = self.output/'attachments/template.xlsx'
        changed = target.read_bytes().replace(b'Sheet1', b'Sheet2')
        target.write_bytes(changed)
        with patch.object(archive.subprocess, 'run') as run:
            result = archive.archive(self.capture, self.output, SOURCE, resume=True)
            self.assertEqual(result['failed'], 1)
            self.assertEqual(target.read_bytes(), changed)
            run.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'changed'):
            archive.archive(self.capture, self.output, SOURCE, profile='different', resume=True)

    def test_lock_and_symlink_boundaries(self):
        self.save()
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            archive.archive(self.capture, self.output, SOURCE, workers=1)
        lock = self.output/'.archive-attachments.lock'
        lock.write_text('other writer')
        with self.assertRaises(FileExistsError):
            archive.archive(self.capture, self.output, SOURCE, resume=True)
        self.assertEqual(lock.read_text(), 'other writer')
        lock.unlink()
        target = self.output/'attachments/template.xlsx'
        target.unlink()
        outside = self.root/'outside.xlsx'; outside.write_bytes(xlsx())
        target.symlink_to(outside)
        result = archive.archive(self.capture, self.output, SOURCE, resume=True)
        self.assertEqual(result['failed'], 1)
        self.assertTrue(target.is_symlink())

    def test_resume_rejects_tampered_capture_and_null_state_records(self):
        self.save()
        with patch.object(archive.subprocess, 'run', side_effect=self.run_cli):
            archive.archive(self.capture, self.output, SOURCE)
        saved_capture = self.output/'capture.json'
        saved_capture.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Archived capture changed'):
            archive.archive(self.capture, self.output, SOURCE, resume=True)
        saved_capture.write_bytes(self.capture.read_bytes())
        state = self.output/'attachment-state.json'
        data = json.loads(state.read_text()); data['items'] = None
        state.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'invalid attachment records'):
            archive.archive(self.capture, self.output, SOURCE, resume=True)


if __name__ == '__main__':
    unittest.main()

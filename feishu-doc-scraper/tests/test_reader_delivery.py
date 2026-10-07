import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_reader_delivery as gate
import render_api_capture as render


@unittest.skipUnless(shutil.which('pandoc'), 'actual production Markdown parser required')
class ReaderDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'archive'
        (self.root / 'media').mkdir(parents=True)
        (self.root / 'media/image.png').write_bytes(b'original image')
        (self.root / 'media/course name.mp4').write_bytes(b'original video')
        (self.root / 'note.md').write_text('# Original\n\n![](media/image.png)\n\n![](<media/course name.mp4>)\n\n[video](<media/course name.mp4>)\n')
        self.manifest = self.root / 'manifest.json'
        self.seal()

    def tearDown(self):
        self.temp.cleanup()

    def seal(self):
        files = []
        for p in sorted(self.root.rglob('*')):
            if not p.is_file() or p.name == 'manifest.json':
                continue
            rel = p.relative_to(self.root).as_posix()
            row = {'bytes': p.stat().st_size, 'sha256': gate.sha(p)}
            if p.suffix == '.md':
                row.update(role='document_snapshot', storage='git', path=rel, mime='text/markdown')
            else:
                row.update(role='embedded_media_original', storage='source', cache_path=rel,
                           mime='image/png' if p.suffix == '.png' else 'video/mp4',
                           locator={'system':'feishu', 'source_url':'https://example.feishu.cn/wiki/SyntheticNodeToken1234567890',
                                    'token':'SyntheticImageToken1234567890' if p.suffix=='.png' else 'SyntheticVideoToken1234567890'})
            files.append(row)
        self.manifest.write_text(json.dumps({'files':files}))

    def inspect(self):
        return gate.inspect(self.root, self.manifest, ['note.md'])

    def receipt(self):
        report = self.inspect()
        report_path = self.base / 'inspection.json'
        report_path.write_text(json.dumps(report))
        evidence = {'kind':'user-acceptance', 'reader':'Obsidian',
                    'source_reference':'synthetic-session:message-42', 'quote':'Synthetic acceptance for this exact fixture',
                    'artifact_fingerprint':report['artifact_fingerprint'],
                    'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'entry_notes':report['artifact']['entry_notes']}
        ep = self.base / 'evidence.json';ep.write_text(json.dumps(evidence))
        rp = self.base / 'reader-receipt.json'
        gate.record(report_path, ep, rp)
        return report, ep, rp

    def test_healthy_native_media_and_moved_folder(self):
        report = self.inspect()
        self.assertEqual(report['examined_notes'], 1)
        self.assertEqual(report['examined_files'], 3)
        self.assertEqual(report['actual_reader'], 'not_verified')
        moved = self.base / 'moved'
        shutil.copytree(self.root, moved)
        copied = gate.inspect(moved, moved/'manifest.json', ['note.md'])
        self.assertEqual(copied['artifact_fingerprint'], report['artifact_fingerprint'])

    def test_original_absolute_links_rejected_even_when_file_exists(self):
        asset = self.root/'media/image.png'
        for text in [f'![]({asset})', f'<p><a href="{asset}">video</a></p>',
                     f'![]({asset.as_uri()})', '![](/synthetic-home/.local/share/favbase/media/picture.png)']:
            (self.root/'note.md').write_text(text);self.seal()
            with self.assertRaises(ValueError): self.inspect()

    def test_original_raw_html_video_rejected(self):
        (self.root/'note.md').write_text('<p><a href="media/course%20name.mp4">video</a></p>')
        self.seal()
        with self.assertRaisesRegex(ValueError,'raw HTML'): self.inspect()

    def test_missing_asset_and_same_size_wrong_bytes_rejected(self):
        p=self.root/'media/image.png';p.write_bytes(b'x'*p.stat().st_size)
        with self.assertRaisesRegex(ValueError,'differs from manifest'): self.inspect()
        p.unlink()
        with self.assertRaises(ValueError): self.inspect()

    def test_escaping_and_symlink_paths_rejected(self):
        outside=self.base/'outside.png';outside.write_bytes(b'image')
        (self.root/'note.md').write_text('![](../outside.png)');self.seal()
        with self.assertRaisesRegex(ValueError,'leaves archive'): self.inspect()
        (self.root/'note.md').write_text('![](media/image.png)')
        p=self.root/'media/image.png';p.unlink();p.symlink_to(outside)
        with self.assertRaises(ValueError): self.inspect()

    def test_code_examples_remote_sources_fragments_and_reference_links(self):
        (self.root/'note.md').write_text('''# Good

```html
<img src="/synthetic-home/.local/share/favbase/image.png">
```

`![](/not-an-asset.png)`

[source](https://example.feishu.cn/wiki/SyntheticNodeToken1234567890)
[anchor](#good)
![chart][chart]

[chart]: media/image.png
''');self.seal()
        r=self.inspect();self.assertEqual(r['examined_files'],2)
        self.assertEqual(r['artifact']['notes']['note.md']['images'],['media/image.png'])

    def test_text_only_does_not_require_fake_media_count(self):
        (self.root/'note.md').write_text('# Text\n\nPlain original body.');self.seal()
        (self.root/'media/image.png').unlink()  # Optional cache not referenced by this note.
        r=self.inspect();self.assertEqual(r['examined_files'],1)

    def test_linked_notes_in_root_are_followed(self):
        (self.root/'child.md').write_text('[back](note.md)\n\n![](media/image.png)')
        (self.root/'note.md').write_text('[child](child.md)');self.seal()
        r=self.inspect();self.assertEqual(r['examined_notes'],2);self.assertEqual(r['examined_files'],3)

    def test_wikilink_and_percent_encoded_names(self):
        (self.root/'note.md').write_text('![[media/image.png]]\n\n[video](media/course%20name.mp4)')
        self.seal();r=self.inspect();self.assertEqual(r['examined_files'],3)
        (self.root/'note.md').write_text('![[https://example.org/external.png]]');self.seal()
        with self.assertRaisesRegex(ValueError,'embed is not a movable'):self.inspect()

    def test_finalize_requires_evidence_not_conversion_success(self):
        r,code=gate.finalize(self.root,self.manifest,['note.md'],self.base/'missing.json')
        self.assertEqual(code,3);self.assertEqual(r['status'],'reader_pending')
        _,ep,rp=self.receipt()
        r,code=gate.finalize(self.root,self.manifest,['note.md'],rp)
        self.assertEqual(code,0);self.assertEqual(r['status'],'ready_with_reader_evidence')
        self.assertIs(r['provenance_authenticated'],False)

    def test_note_media_and_evidence_changes_invalidate_receipt(self):
        _,ep,rp=self.receipt()
        ep.write_text(ep.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'evidence source'): gate.finalize(self.root,self.manifest,['note.md'],rp)
        ep.write_text(ep.read_text()[:-1])
        (self.root/'note.md').write_text((self.root/'note.md').read_text()+'\nChanged');self.seal()
        with self.assertRaisesRegex(ValueError,'stale'): gate.finalize(self.root,self.manifest,['note.md'],rp)

    def test_evidence_missing_empty_null_and_wrong_scope(self):
        r=self.inspect()
        healthy={'kind':'user-acceptance','reader':'Obsidian','source_reference':'synthetic:42',
                 'quote':'Accepted synthetic fixture','artifact_fingerprint':r['artifact_fingerprint'],
                 'entry_notes':['note.md'],'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        for field in ['kind','reader','source_reference','quote','observed_at']:
            for value in [None,'']:
                with self.assertRaises((ValueError,TypeError)): gate.validate_observation(r,{**healthy,field:value})
            d=dict(healthy);d.pop(field)
            with self.assertRaises((ValueError,TypeError)): gate.validate_observation(r,d)
        with self.assertRaises(ValueError):gate.validate_observation(r,{**healthy,'entry_notes':['other.md']})
        with self.assertRaises(ValueError):gate.validate_observation(r,{**healthy,'reader':'Different reader'})

    def test_native_observation_coverage_and_retained_capture(self):
        r=self.inspect();expected=r['artifact']['notes']['note.md']
        captured=self.base/'native-capture.txt';captured.write_text('Synthetic native observation fixture')
        row={'note':'note.md','images_displayed':expected['images'],'videos_played':expected['videos'],
             'links_opened':expected['links'],'reopened':True}
        evidence={'kind':'native-reader-observation','reader':'Obsidian','source_reference':'synthetic-tool-record:42',
                  'artifact_fingerprint':r['artifact_fingerprint'],
                  'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'observations':[row],'evidence_files':[{'path':str(captured),'sha256':gate.sha(captured)}]}
        self.assertEqual(gate.validate_observation(r,evidence)['kind'],'native-reader-observation')
        for field in ['images_displayed','videos_played','links_opened']:
            bad={**evidence,'observations':[{**row,field:[]}]}
            with self.assertRaisesRegex(ValueError,'do not cover'):gate.validate_observation(r,bad)
        with self.assertRaises(ValueError):gate.validate_observation(r,{**evidence,'observations':[row,row]})
        captured.write_text('Changed synthetic capture')
        with self.assertRaisesRegex(ValueError,'evidence is missing or changed'):gate.validate_observation(r,evidence)

    def test_handwritten_receipt_cannot_skip_observation_validation(self):
        r,ep,rp=self.receipt()
        e=json.loads(ep.read_text());e.pop('quote');ep.write_text(json.dumps(e))
        receipt=json.loads(rp.read_text());receipt['observation']=e;receipt['evidence_sha256']=gate.sha(ep)
        rp.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'actual quote'):gate.finalize(self.root,self.manifest,['note.md'],rp)

    def test_reference_scanner_mutation_is_detected_by_counts(self):
        with patch.object(gate,'references',return_value=[]):
            r=self.inspect()
        self.assertNotEqual(r['examined_files'],3)
        self.assertEqual(r['examined_files'],1)

    def test_future_and_pre_snapshot_observations_rejected(self):
        r=self.inspect();_,ep,rp=self.receipt();e=json.loads(ep.read_text())
        e['artifact_fingerprint']=r['artifact_fingerprint']
        for time in ['2000-01-01T00:00:00+00:00','2099-01-01T00:00:00+00:00']:
            with self.assertRaisesRegex(ValueError,'follow the inspect'):gate.validate_observation(r,{**e,'observed_at':time})

    def test_renderer_refuses_output_outside_root_before_writing(self):
        capture=self.base/'capture.json'
        capture.write_text(json.dumps({'data':{'document':{'content':'<p>Body</p>','title':'Title'}}}))
        outside=self.base/'outside.md'
        with self.assertRaisesRegex(ValueError,'inside the declared archive'):
            render.render(capture,self.manifest,outside,'https://example.feishu.cn/wiki/SyntheticNodeToken1234567890')
        self.assertFalse(outside.exists())


if __name__=='__main__':unittest.main()

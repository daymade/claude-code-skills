import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import download_original_preview as download
import render_api_capture as render
import build_manual_catalog as catalog


class Response(io.BytesIO):
    def __init__(self, body, content_range, status=206):
        super().__init__(body)
        self.status = status
        self.headers = {'Content-Range': content_range}


class OriginalMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = b'original bytes 012345678'
        self.spec = {'url': 'https://example.feishu.cn/observed-original', 'headers': {},
                     'identity': 'synthetic-token@revision-1', 'size': len(self.data)}
        self.requested = []

    def tearDown(self):
        self.temp.cleanup()

    def open(self, request, timeout):
        lo, hi = map(int, request.get_header('Range').split('=')[1].split('-'))
        self.requested.append((lo, hi))
        return Response(self.data[lo:hi+1], f'bytes {lo}-{hi}/{len(self.data)}')

    def downloader(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = self.open
        return patch.object(download.urllib.request, 'build_opener', return_value=opener)

    def test_original_and_idempotent_reopen(self):
        dest = self.root / 'clip.mp4'
        with self.downloader() as factory:
            result = download.download(self.spec, dest, chunk_size=8, workers=1)
            self.assertEqual(dest.read_bytes(), self.data)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(len(self.requested), 3)
            self.assertEqual(factory.call_args.args[0].proxies, {})
            self.assertEqual(download.download(self.spec, dest, 8, 1)['status'], 'already_verified')
            self.assertEqual(len(self.requested), 3)

    def test_corrupt_partial_is_redownloaded(self):
        dest = self.root / 'clip.mp4'
        dest.with_name(dest.name + '.part').write_bytes(b'badbytes' + self.data[8:])
        dest.with_name(dest.name + '.ranges.json').write_text(json.dumps({
            'identity': self.spec['identity'], 'size': len(self.data), 'chunk_size': 8,
            'chunks': {'0': download.digest(self.data[:8]), '1': download.digest(self.data[8:16])}}))
        with self.downloader():
            download.download(self.spec, dest, 8, 1)
        self.assertEqual(self.requested, [(0, 7), (16, len(self.data)-1)])
        self.assertEqual(dest.read_bytes(), self.data)

    def test_single_writer_and_foreign_state(self):
        dest = self.root / 'clip.mp4'
        with download.writer_lock(dest.with_name(dest.name + '.lock')):
            with self.assertRaisesRegex(ValueError, 'Another writer'):
                download.download(self.spec, dest, 8, 1)
        dest.with_name(dest.name + '.ranges.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'different source'):
            download.download(self.spec, dest, 8, 1)

    def test_bad_range_cannot_publish(self):
        dest = self.root / 'clip.mp4'
        opener = unittest.mock.Mock()
        opener.open.return_value = Response(self.data, 'bytes 0-0/1', status=200)
        with patch.object(download.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'byte range'):
                download.download(self.spec, dest, 8, 1)
        self.assertFalse(dest.exists())
        self.assertFalse(dest.with_name(dest.name + '.verified.json').exists())

    def test_no_credentials_cross_host(self):
        with self.assertRaises(ValueError):
            download.check_url('https://example.org/credential-destination')
        request = download.urllib.request.Request(self.spec['url'], headers={'Cookie': 'synthetic'})
        with self.assertRaisesRegex(ValueError, 'Cross-host'):
            download.FeishuRedirect().redirect_request(request, None, 302, '', {}, 'https://other.feishu.cn/x')

    def test_missing_empty_and_null_request_fields(self):
        for field in ('identity', 'size', 'headers'):
            for value in (None, ''):
                spec = {**self.spec, field: value}
                with self.assertRaises(ValueError): download.download(spec, self.root / 'clip.mp4')
            spec = dict(self.spec)
            spec.pop(field)
            with self.assertRaises(ValueError): download.download(spec, self.root / 'clip.mp4')

    @unittest.skipUnless(shutil.which('pandoc'), 'pandoc required for actual conversion engine')
    def test_actual_pandoc_native_media_not_raw_figure(self):
        root = self.root
        (root / 'media').mkdir()
        (root / 'media/image.png').write_bytes(b'image')
        (root / 'media/course name.mp4').write_bytes(b'video')
        files = [{'storage': 'source', 'locator': {'token': token}, 'cache_path': path, 'bytes': 5}
                 for token, path in [('image-token', 'media/image.png'), ('video-token', 'media/course name.mp4')]]
        (root / 'manifest.json').write_text(json.dumps({'files': files}))
        raw = '<h1>标题</h1><img src="image-token"/><figure><source token="video-token" name="course name.mp4"/></figure>'
        (root / 'capture.json').write_text(json.dumps({'data': {'document': {'title': '标题', 'content': raw}}}))
        result = render.render(root / 'capture.json', root / 'manifest.json', root / 'note.md', 'https://example.feishu.cn/wiki/node')
        text = (root / 'note.md').read_text()
        self.assertIn('![](<media/course name.mp4>)', text)
        self.assertIn('![](<media/image.png>)', text)
        self.assertNotIn('<figure', text)
        self.assertNotIn(str(root), text)
        self.assertEqual(result['media_references'], 2)
        self.assertEqual(result['actual_reader'], 'not_verified')

    def test_missing_mapping_fails_instead_of_false_green(self):
        with self.assertRaisesRegex(ValueError, 'no verified local original'):
            render.prepare('<img src="missing"/>', {})

    @unittest.skipUnless(shutil.which('pandoc'), 'pandoc required for actual conversion engine')
    def test_oss_original_keeps_separate_source_token(self):
        (self.root / 'media').mkdir()
        body = b'synthetic-original'
        (self.root / 'media/original.png').write_bytes(body)
        entry = {'role': 'embedded_media_original', 'storage': 'oss',
                 'locator': {'system': 'oss', 'uri': 'oss://synthetic-bucket/original.png'},
                 'source_token': 'SyntheticMediaToken1234567890', 'cache_path': 'media/original.png',
                 'bytes': len(body), 'sha256': download.digest(body), 'mime': 'image/png'}
        import check_archive_storage
        self.assertEqual(check_archive_storage.validate_manifest({'files': [entry]}), [])
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'files': [entry]}))
        capture = self.root / 'capture.json'
        capture.write_text(json.dumps({'data': {'document': {'title': 'Synthetic lesson',
            'content': '<p>Body.</p><img src="SyntheticMediaToken1234567890"/>'}}}))
        result = render.render(capture, manifest, self.root / 'oss.md', 'https://example.feishu.cn/wiki/node')
        self.assertEqual(result['media_references'], 1)
        self.assertIn('![](<media/original.png>)', (self.root / 'oss.md').read_text())
        entry['storage'] = 'source'
        entry['locator'] = {'system': 'feishu', 'source_url': 'https://example.feishu.cn/wiki/SyntheticNodeToken1234567890',
                            'token': 'DifferentCapturedToken'}
        self.assertEqual(check_archive_storage.validate_manifest({'files': [entry]}), [])
        manifest.write_text(json.dumps({'files': [entry]}))
        with self.assertRaisesRegex(ValueError, 'disagree'):
            render.render(capture, manifest, self.root / 'conflict.md', 'https://example.feishu.cn/wiki/node')

    def test_catalog_preserves_source_identity_and_does_not_classify(self):
        (self.root / 'lesson.md').write_text('---\ntitle: "Lesson"\nsource: "https://example.feishu.cn/wiki/node"\nqmd:\n  metadata:\n    platform: "feishu"\n    key: "node"\n    kind: "course"\n---\n\nOriginal body.\n')
        result = catalog.build(self.root, 'fav-feishu', 'Selected lessons')
        self.assertEqual(result['items'], 1)
        row = json.loads((self.root / '_data/items.jsonl').read_text())
        self.assertEqual(row['key'], 'node')
        self.assertNotIn('cat', row)
        self.assertEqual(catalog.build(self.root, 'fav-feishu', 'Selected lessons')['items'], 1)


if __name__ == '__main__':
    unittest.main()

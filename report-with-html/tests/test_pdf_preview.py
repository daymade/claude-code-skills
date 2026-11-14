from pathlib import Path
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pdf_preview import PDFPreview


@unittest.skipUnless(shutil.which('pdfinfo') and shutil.which('pdftoppm'), 'Poppler required')
class PdfTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'assets/examples/source-preview'
        self.pdf = PDFPreview(root, {'fixture': {'path': 'synthetic.pdf', 'title': 'Synthetic PDF',
                                                'mime': 'application/pdf', 'bytes': (root / 'synthetic.pdf').stat().st_size}})

    def test_exact_page_navigation_and_real_png(self):
        status, mime, body = self.pdf.get('/pdf/fixture', 'page=1')
        self.assertEqual(status, 200);self.assertIn(b'page=2', body)
        for page in (1, 2):
            status, mime, image = self.pdf.get('/pdf-page/fixture', 'page=' + str(page))
            self.assertEqual((status, mime), (200, 'image/png'))
            self.assertTrue(image.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_invalid_page_and_unregistered_source_fail(self):
        for query in ('page=0', 'page=', 'page=999999', 'page=1&page=2', 'file=/etc/passwd'):
            self.assertEqual(self.pdf.get('/pdf/fixture', query)[0], 400)
        self.assertEqual(self.pdf.get('/pdf/unregistered')[0], 404)
        self.assertEqual(self.pdf.get('/pdf/../private')[0], 404)
        self.assertIsNone(self.pdf.get('/asset/fixture'))
        self.pdf.records['fixture']['bytes'] += 1
        self.assertEqual(self.pdf.get('/pdf/fixture')[0], 409)


if __name__ == '__main__': unittest.main()

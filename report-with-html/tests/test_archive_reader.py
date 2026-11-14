import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_archive_reader import build, validate


def catalog():
    return {'title': 'Synthetic archive', 'nodes': [
        {'id': 'course', 'title': 'Course', 'parent': None, 'status': 'current'},
        {'id': 'chapter', 'title': 'Chapter', 'parent': 'course', 'status': 'current'},
        {'id': 'lesson', 'title': 'Lesson', 'parent': 'chapter', 'status': 'current'},
        {'id': 'old', 'title': 'Previous chapter', 'parent': 'course', 'status': 'historical'}],
        'items': [{'id': 'doc1', 'node': 'lesson', 'title': 'Notes', 'kind': 'document', 'url': '/asset/doc1'},
                  {'id': 'video1', 'node': 'lesson', 'title': 'Recording', 'kind': 'video', 'url': '/asset/video1'},
                  {'id': 'pdf1', 'node': 'lesson', 'title': 'Reference', 'kind': 'pdf', 'url': '/pdf/pdf1'},
                  {'id': 'old-doc', 'node': 'old', 'title': 'Historical notes', 'kind': 'document'},
                  {'id': 'unknown-doc', 'title': 'Unknown parent', 'kind': 'document'}]}


class ReaderTests(unittest.TestCase):
    def test_hierarchy_and_related_materials_retain_identity(self):
        source = catalog();text = build(source)
        for item in source['nodes'] + source['items']: self.assertIn('"id": "' + item['id'] + '"', text)
        self.assertIn('归属未核实', text)
        self.assertIn('controls=true', text)
        self.assertIn('显示历史章节', text)

    def test_materials_and_historical_nodes_cannot_silently_disappear(self):
        before = catalog();after = copy.deepcopy(before);after['items'].pop(0)
        with self.assertRaises(ValueError): validate(after, before)
        after = copy.deepcopy(before);after['nodes'].pop()
        with self.assertRaises(ValueError): validate(after, before)
        before['items'].append({'id': 'gap1', 'title': 'Missing page', 'kind': 'gap'})
        after = catalog();after['resolved_gap_ids'] = ['gap1'];validate(after, before)

    def test_duplicate_cycle_and_unsafe_source_url_reject(self):
        for mutate in [lambda c:c['items'].append(c['items'][0]),
                       lambda c:c['nodes'][0].update(parent='lesson'),
                       lambda c:c['items'][0].update(url='javascript:alert(1)')]:
            source = catalog();mutate(source)
            with self.assertRaises(ValueError):validate(source)

    def test_source_script_text_is_inert_json(self):
        source = catalog();source['items'][0]['title'] = '</script><script>unsafe()</script>'
        text = build(source)
        self.assertNotIn('</script><script>unsafe()', text)
        self.assertIn('\\u003c/script>', text)


if __name__ == '__main__': unittest.main()

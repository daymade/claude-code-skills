import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'search_fanout.py'
SPEC = importlib.util.spec_from_file_location('ima_search_fanout', SCRIPT)
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


class KnowledgeBasePagination(unittest.TestCase):
    def response(self, data, code=0):
        response = io.BytesIO(json.dumps({'code': code, 'data': data}).encode())
        return response

    def test_list_uses_accepted_page_size_and_follows_cursor(self):
        requests = []

        def serve(request, **kwargs):
            body = json.loads(request.data)
            requests.append(body)
            self.assertTrue(request.full_url.endswith('/wiki/v1/search_knowledge_base'))
            self.assertEqual(body['limit'], 20)
            if body['cursor'] == '':
                return self.response({'info_list': [{'kb_id': 'one'}],
                                      'next_cursor': 'second-page', 'is_end': False})
            self.assertEqual(body['cursor'], 'second-page')
            return self.response({'info_list': [{'kb_id': 'two'}], 'is_end': True})

        with patch.object(search.urllib.request, 'urlopen', side_effect=serve):
            self.assertEqual(search.list_all_kbs('synthetic-id', 'synthetic-key'),
                             [{'kb_id': 'one'}, {'kb_id': 'two'}])
        self.assertEqual(len(requests), 2)

    def test_listing_api_failure_is_not_an_empty_success(self):
        with patch.object(search.urllib.request, 'urlopen',
                          return_value=self.response({}, code=51)):
            with self.assertRaisesRegex(RuntimeError, 'code=51'):
                search.list_all_kbs('synthetic-id', 'synthetic-key')

    def test_truncation_labels_follow_the_canonical_ceiling(self):
        result = {'kb': {'kb_name': 'Example'}, 'hits': [{'title': 'Example'}],
                  'truncated': True}
        output = io.StringIO()
        with patch.object(search, 'HARD_HIT_CAP', 7), contextlib.redirect_stdout(output):
            search.render_text('template', [], [result], [], [], 1, 1)
        self.assertIn('truncated at 7', output.getvalue())
        self.assertIn('7-result ceiling', output.getvalue())
        self.assertNotIn('100', output.getvalue())

    def test_main_lists_then_searches_and_renders_results(self):
        paths = []

        def serve(request, **kwargs):
            body = json.loads(request.data)
            paths.append(request.full_url)
            if request.full_url.endswith('/search_knowledge_base'):
                self.assertEqual(body['limit'], 20)
                return self.response({'info_list': [{'kb_id': 'one', 'kb_name': 'Example'}],
                                      'is_end': True})
            self.assertEqual(body['knowledge_base_id'], 'one')
            self.assertEqual(body['query'], 'template')
            return self.response({'info_list': [{'title': 'Example template', 'media_id': 'item'}]})

        output = io.StringIO()
        with patch.object(search, 'load_credentials', return_value=('synthetic-id', 'synthetic-key')), \
                patch.object(search, 'load_config', return_value=([], [], 'parallel-then-merge')), \
                patch.object(search.urllib.request, 'urlopen', side_effect=serve), \
                contextlib.redirect_stdout(output):
            search.main(['template', '--json', '--workers', '1'])
        result = json.loads(output.getvalue())
        self.assertEqual(result['others'][0]['hits'][0]['title'], 'Example template')
        self.assertEqual(len(paths), 2)


if __name__ == '__main__':
    unittest.main()

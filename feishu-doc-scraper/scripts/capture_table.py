#!/usr/bin/env python3
"""Capture one Wiki Base/Sheet as raw exports, readable Markdown and a manifest.

Uses the installed lark-cli read shortcuts. No remote writes, paid calls or local
video downloads. An existing output directory is never replaced. Exit 3 retains
an explicitly partial capture; exit 2 is invalid input or an unstarted capture.
"""
import argparse
import datetime
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys

from lark_result import CLIError, parse_cli_result, wiki_token

SAFE_FILES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.pdf', '.txt',
              '.md', '.html', '.csv', '.json', '.xlsx', '.docx', '.pptx'}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid source identifier')
    return value


def child(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Capture path escapes the output root')
    return path


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def call(args, profile, *, receipt_keys=()):
    env = dict(os.environ, LARK_CLI_NO_PROXY='1', LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1',
               LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')
    command = ['lark-cli', '--profile', profile, *args, '--as', 'user']
    if not receipt_keys:
        command += ['--format', 'json']
    # CLI output paths are scoped to its cwd; run inside the selected new capture.
    cwd = None
    for flag in ('--output', '--output-path'):
        if flag in args:
            cwd = str(Path(args[args.index(flag) + 1]).parent)
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, env=env, cwd=cwd)
    return parse_cli_result(result.stdout, result.stderr, result.returncode,
                            receipt_keys=receipt_keys)


def file_refs(value, coordinate, found):
    if isinstance(value, list):
        for item in value:
            file_refs(item, coordinate, found)
    elif isinstance(value, dict):
        token = value.get('file_token')
        if token:
            identifier(token)
            name = value.get('name') or token
            if not isinstance(name, str):
                raise ValueError('Invalid attachment name')
            found.append({'token': token, 'name': name,
                          'declared_bytes': value.get('size'), **coordinate})
        else:
            for item in value.values():
                file_refs(item, coordinate, found)


def cell(value, media):
    if value is None:
        return '<span>空值</span>'
    if isinstance(value, dict) and value.get('file_token') in media:
        row = media[value['file_token']]
        if row.get('cache_path'):
            url = html.escape(row['cache_path'], quote=True)
            title = html.escape(str(value.get('name') or row['token']))
            image = '<br><img loading="lazy" src="%s" alt="%s">' % (url, title) if row['mime'].startswith('image/') else ''
            return '<a href="%s">%s</a>%s' % (url, title, image)
    if isinstance(value, list):
        return '<br>'.join(cell(x, media) for x in value) if value else '[]'
    if isinstance(value, (dict, bool, int, float)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return '<div style="white-space:pre-wrap">' + html.escape(str(value)) + '</div>'


def column(number):
    result = ''
    while number:
        number, rest = divmod(number - 1, 26)
        result = chr(65 + rest) + result
    return result


def capture(source, profile, output, *, attachments='local', max_pages=100,
            max_cells=100000, runner=call):
    token = wiki_token(source)
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; choose a new capture directory')
    output.mkdir(parents=True)
    output = output.resolve()
    manifest = {'schema_version': 1, 'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'source': source, 'node_token': token, 'source_identity': profile + ' / user',
                'scope': 'all table records/readable fields or grid values/formulas; non-video cell attachments',
                'comments': 'not captured here; use fetch_comments.py separately',
                'capture_status': 'partial', 'tables': [], 'files': [], 'gaps': []}
    raw_dir = child(output, '_data');raw_dir.mkdir()
    try:
        node_reply = runner(['wiki', '+node-get', '--node-token', token], profile)
        dump(raw_dir / 'node.json', node_reply)
        node = node_reply['data'].get('node', node_reply['data'])
        app = identifier(node['obj_token']);kind = node['obj_type']
        manifest.update(title=node['title'], document_id=app, obj_type=kind)
        if kind == 'bitable':
            reply = runner(['base', '+table-list', '--base-token', app], profile)
            dump(raw_dir / 'tables.json', reply)
            if reply['data'].get('total') != len(reply['data']['tables']):
                manifest['gaps'].append({'reason': 'table_list_coverage_unknown_or_incomplete'})
            for meta in reply['data']['tables']:
                tid = identifier(meta['id']);directory = child(raw_dir, tid);directory.mkdir()
                schema = runner(['base', '+field-list', '--base-token', app, '--table-id', tid], profile)
                dump(directory / 'fields.json', schema)
                table = {'id': tid, 'name': meta['name'], 'rows': [], 'pages': [],
                         'fields': schema['data']['fields'], 'ignored_fields': []}
                manifest['tables'].append(table)
                for field in table['fields']:
                    if field.get('type') == 'not_support':
                        manifest['gaps'].append({'table_id': tid, 'reason': 'unsupported_field',
                                                 'field_id': field['id'], 'field_name': field['name']})
                seen = set();offset = 0;revisions = set();complete = False
                for _ in range(max_pages):
                    target = directory / ('records-%06d.ndjson' % offset)
                    page = runner(['base', '+record-list', '--base-token', app, '--table-id', tid,
                                   '--limit', '2000', '--offset', str(offset), '--output', str(target)],
                                  profile, receipt_keys=('records_count', 'has_more', 'record_file'))
                    if type(page.get('has_more')) is not bool:
                        raise ValueError('Missing explicit table pagination state')
                    rows = [json.loads(line) for line in target.read_text().splitlines() if line.strip()]
                    context = page.get('query_context', {})
                    if len(rows) != page['records_count'] or context.get('record_scope') != 'all_records' or context.get('field_scope') != 'all_fields':
                        raise ValueError('Record count or all-record/all-field scope mismatch')
                    for row in rows:
                        rid = row['record_id']
                        if rid in seen:raise ValueError('Repeated record across pages')
                        seen.add(rid)
                    table['rows'].extend(rows);revisions.add(page.get('rev'))
                    table['ignored_fields'].extend(page.get('ignored_fields', []))
                    # Localize transport-only output paths; values and schema stay untouched.
                    saved = dict(page)
                    for key in ('record_file', 'manifest_file'):
                        if key in saved:saved[key] = Path(saved[key]).name
                    dump(directory / ('page-%06d.json' % offset), saved)
                    table['pages'].append(str(target.relative_to(output)))
                    if not page['has_more']:complete = True;break
                    next_offset = page.get('next_offset')
                    if type(next_offset) is not int or next_offset <= offset:raise ValueError('Invalid pagination cursor')
                    offset = next_offset
                stable = meta.get('rev') is not None and revisions == {meta['rev']}
                table.update(revision=meta.get('rev'), record_count=len(seen), pagination_complete=complete,
                             revision_stable=stable, count_match=len(seen) == meta.get('records_count'))
                if not (complete and stable and table['count_match']):
                    manifest['gaps'].append({'table_id': tid, 'reason': 'incomplete_or_changed_snapshot'})
                for gap in table['ignored_fields']:
                    manifest['gaps'].append({'table_id': tid, 'reason': 'unsupported_field', **gap})
        elif kind in ('sheet', 'sheets'):
            reply = runner(['sheets', '+workbook-info', '--spreadsheet-token', app], profile)
            dump(raw_dir / 'workbook.json', reply);book = reply['data'];total = 0
            for meta in book['sheets']:
                sid = identifier(meta['sheet_id']);count = meta['row_count'] * meta['column_count'];total += count
                if total > max_cells:raise ValueError('Declared grid exceeds cell budget; choose an explicit smaller source scope')
                area = 'A1:' + column(meta['column_count']) + str(meta['row_count'])
                target = raw_dir / ('cells-' + sid + '.json')
                receipt = runner(['sheets', '+cells-get', '--spreadsheet-token', app, '--sheet-id', sid,
                                  '--range', area, '--include', 'value,formula', '--output-path', str(target)], profile)
                grid = json.loads(target.read_text());dump(raw_dir / ('cells-' + sid + '-receipt.json'), receipt)
                if receipt['data'].get('complete') is not True or grid.get('has_more') is not False or any(x.get('truncated') for x in grid.get('ranges', [])):
                    manifest['gaps'].append({'table_id': sid, 'reason': 'truncated_grid'})
                if book.get('revision') is None or grid.get('revision') != book['revision']:
                    manifest['gaps'].append({'table_id': sid, 'reason': 'changed_grid_revision'})
                for key in ('chart_count', 'float_image_count', 'pivot_table_count'):
                    if meta.get(key):manifest['gaps'].append({'table_id': sid, 'reason': 'non_grid_object', 'kind': key})
                manifest['tables'].append({'id': sid, 'name': meta['sheet_name'], 'grid': grid,
                                           'range': area, 'cell_count': sum(len(r) for g in grid['ranges'] for r in g['cells'])})
        else:
            raise ValueError('Wiki object is not a Base or Sheet: ' + str(kind))
        refs = []
        for table in manifest['tables']:
            for row in table.get('rows', []):
                for field, value in row.items():
                    file_refs(value, {'table_id': table['id'], 'record_id': row['record_id'], 'field': field}, refs)
        unique = {}
        for ref in refs:
            if ref['token'] in unique:
                if (ref['name'], ref['declared_bytes']) != (unique[ref['token']]['name'], unique[ref['token']]['declared_bytes']):
                    raise ValueError('One attachment token has conflicting metadata')
                continue
            unique[ref['token']] = ref
            suffix = Path(ref['name']).suffix.lower();row = dict(ref, status='source_locator_only')
            if attachments == 'local' and suffix in SAFE_FILES and type(ref['declared_bytes']) is int and 0 < ref['declared_bytes'] <= 100 * 1024 * 1024:
                media = child(output, 'media');media.mkdir(exist_ok=True)
                target = child(media, ref['token'] + suffix)
                reply = runner(['drive', '+preview', '--file-token', ref['token'], '--type', 'source_file', '--output', str(target)], profile)
                if target.stat().st_size != ref['declared_bytes']:raise ValueError('Attachment byte count mismatch')
                row.update(status='saved', cache_path=str(target.relative_to(output)), bytes=target.stat().st_size,
                           sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                           mime=reply['data'].get('content_type') or mimetypes.guess_type(ref['name'])[0] or 'application/octet-stream',
                           operation='drive +preview --type source_file', original_match='declared size only; no independent platform hash')
            if row['status'] != 'saved':manifest['gaps'].append({'reason': 'attachment_not_retained', 'token': ref['token']})
            manifest['files'].append(row)
        manifest['attachment_references'] = refs
        manifest['capture_status'] = 'partial' if manifest['gaps'] else 'complete'
    except (CLIError, ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        manifest['gaps'].append({'reason': 'capture_failed', 'error_type': type(exc).__name__,
                                 'message': str(exc), **({'response': exc.envelope} if isinstance(exc, CLIError) and exc.envelope else {})})
    media = {x['token']: x for x in manifest['files']}
    text = ['# ' + html.escape(manifest.get('title', 'Table capture')), '', 'Source: ' + source, '',
            'Capture status: ' + manifest['capture_status'], '']
    for gap in manifest['gaps']:text += ['> Gap: ' + html.escape(json.dumps(gap, ensure_ascii=False)), '']
    for table in manifest['tables']:
        text += ['## ' + html.escape(table['name']), '']
        if 'rows' in table:
            for row in table['rows']:
                text += ['<details><summary>' + html.escape(row['record_id']) + '</summary><table>']
                for field in table['fields']:
                    if field['type'] == 'not_support':continue
                    text += ['<tr><th>' + html.escape(field['name']) + '</th><td>' + cell(row.get(field['name']), media) + '</td></tr>']
                text += ['</table></details>', '']
        else:
            text += ['Saved range ' + table['range'] + '; all raw cells retained; entirely empty rows are omitted below.', '']
            for grid in table['grid']['ranges']:
                for number, cells in zip(grid['row_indices'], grid['cells']):
                    if not any(cells):continue
                    text += ['<details><summary>Row ' + str(number) + '</summary><table>']
                    for col, value in zip(grid['col_indices'], cells):
                        if value:text += ['<tr><th>' + html.escape(col) + '</th><td>' + cell(value, media) + '</td></tr>']
                    text += ['</table></details>', '']
    child(output, 'table.md').write_text('\n'.join(text) + '\n')
    dump(child(output, 'manifest.json'), manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Wiki URL or bare node token')
    parser.add_argument('--profile', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--attachments', choices=('local', 'metadata'), default='local')
    parser.add_argument('--max-pages', type=int, default=100)
    parser.add_argument('--max-cells', type=int, default=100000)
    args = parser.parse_args()
    if args.max_pages < 1 or args.max_cells < 1:parser.error('Budgets must be positive')
    try:result = capture(args.source, args.profile, args.out.absolute(), attachments=args.attachments,
                         max_pages=args.max_pages, max_cells=args.max_cells)
    except (ValueError, OSError) as exc:parser.error(str(exc))
    print(json.dumps({'capture_status': result['capture_status'], 'tables': len(result['tables']),
                      'files': len(result['files']), 'gaps': len(result['gaps'])}))
    return 0 if result['capture_status'] == 'complete' else 3


if __name__ == '__main__':
    sys.exit(main())

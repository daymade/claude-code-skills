"""Render registered local PDF pages for an existing loopback report server.

Requires Poppler pdfinfo/pdftoppm. Does not replace the original asset endpoint.
Caller: response = PDFPreview(root, records).get(path, query); None means unhandled.
"""
import html
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import parse_qs

from preview_report import open_exact


class PDFPreview:
    def __init__(self, root, records):
        self.root, self.records = Path(root).resolve(), records

    def get(self, route, query=''):
        if not route.startswith(('/pdf/', '/pdf-page/')): return None
        match = re.fullmatch(r'/(pdf|pdf-page)/([A-Za-z0-9_-]+)', route)
        if not match: return 404, 'text/plain', b'Unknown PDF'
        mode, key = match.groups()
        record = self.records.get(key)
        if not record or record.get('mime') != 'application/pdf': return 404, 'text/plain', b'Unknown PDF'
        args = parse_qs(query, keep_blank_values=True)
        pages = args.get('page', ['1'])
        if set(args) - {'page'} or len(pages) != 1 or not re.fullmatch(r'[1-9][0-9]{0,5}', pages[0]):
            return 400, 'text/plain', b'Invalid page'
        page = int(pages[0])
        try:
            with open_exact(self.root, record['path']) as stream:
                if os.fstat(stream.fileno()).st_size != record['bytes']: return 409, 'text/plain', b'PDF changed'
                source = '/dev/fd/' + str(stream.fileno())
                kwargs = {'pass_fds': (stream.fileno(),), 'capture_output': True, 'check': True}
                info = subprocess.run(['pdfinfo', source], timeout=20, **kwargs).stdout.decode()
                found = re.search(r'^Pages:\s+(\d+)\s*$', info, re.M)
                if not found: raise ValueError('Page count unavailable')
                count = int(found[1])
                if page > count: return 400, 'text/plain', b'Page outside PDF'
                if mode == 'pdf-page':
                    stream.seek(0)
                    image = subprocess.run(['pdftoppm', '-f', str(page), '-singlefile', '-scale-to', '1600', '-png', source], timeout=40, **kwargs).stdout
                    if not image.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('No rendered page')
                    return 200, 'image/png', image
        except (OSError, KeyError, ValueError, subprocess.SubprocessError):
            return 503, 'text/plain', b'PDF page unavailable; inspect source and Poppler installation'
        nav = (f'<a href="/pdf/{key}?page={page-1}">上一页</a>' if page > 1 else '')
        nav += f'<b>第 {page} / {count} 页</b>'
        if page < count: nav += f'<a href="/pdf/{key}?page={page+1}">下一页</a>'
        title = html.escape(str(record.get('title') or key), quote=True)
        body = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{title}</title>
<style>body{{margin:0;background:#eee;font:15px/1.6 system-ui}}nav{{position:sticky;top:0;background:white;padding:12px;display:flex;gap:24px}}img{{display:block;width:100%;max-width:1000px;height:auto;margin:12px auto}}</style>
<nav>{nav}</nav><img src="/pdf-page/{key}?page={page}" alt="{title}，第 {page} 页"></html>'''
        return 200, 'text/html; charset=utf-8', body.encode()

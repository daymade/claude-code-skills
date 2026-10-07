#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Declare a user-selected Feishu archive for personal favorites consumption.

Only indexes already captured Markdown and its explicit source/qmd identity.
Does not fetch, classify, promote, change the body or choose a destination.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import os
import urllib.parse
from download_original_preview import writer_lock


def scalar(front, name, indent=0):
    match = re.search(rf"(?m)^{' ' * indent}{re.escape(name)}:\s*(.+?)\s*$", front)
    if not match:
        return None
    value = match.group(1)
    return json.loads(value) if value.startswith('"') else value


def build(root, collection, display_name, scope='private'):
    root = Path(root).resolve()
    if not re.fullmatch(r'fav-[a-z][a-z0-9-]{1,39}', collection) or not display_name.strip():
        raise ValueError('Provide a fav-* collection and a display name')
    if scope not in ('private', 'restricted', 'public'):
        raise ValueError('Unknown sharing scope')
    rows = []
    keys = set()
    for path in sorted(root.glob('**/*.md')):
        rel = path.relative_to(root)
        if 'media' in rel.parts or '_data' in rel.parts:
            raise ValueError('Markdown inside cache/catalog directories would enter the qmd mask')
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Body symlinks/escaped paths are unsupported')
        text = path.read_text(encoding='utf-8')
        front = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
        if not front or not text[front.end():].strip():
            raise ValueError('Missing source frontmatter or empty body: ' + str(rel))
        fm = front.group(1)
        title, url = scalar(fm, 'title'), scalar(fm, 'source')
        key, platform, kind = (scalar(fm, k, 4) for k in ('key', 'platform', 'kind'))
        host = urllib.parse.urlsplit(url or '').hostname or ''
        if (platform != 'feishu' or not isinstance(key, str) or not key or key in keys or
                not title or not kind or not host.endswith('.feishu.cn')):
            raise ValueError('Missing/duplicate Feishu source identity: ' + str(rel))
        body_scope = scalar(fm, 'share_scope') or scope
        levels = {'public': 0, 'restricted': 1, 'private': 2}
        if body_scope not in levels or levels[body_scope] < levels[scope]:
            raise ValueError('Body sharing scope exceeds selected archive scope')
        row = {'src': 'feishu', 'key': key, 'title': title, 'url': url, 'kind': kind,
               'body_root': '.', 'body_rel': rel.as_posix(),
               'body_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'share_scope': body_scope}
        row['record_sha256'] = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                                       separators=(',', ':')).encode()).hexdigest()
        rows.append(row)
        keys.add(key)
    if not rows:
        raise ValueError('No source-owned Markdown; refusing an empty declaration')
    declaration = {'schema_version': 1, 'source_kind': 'manual-favorites', 'src': 'feishu',
                   'collection': collection, 'display_name': display_name, 'body_root': '.',
                   'body_glob': '**/*.md', 'exclude_dirs': ['media', '_data'], 'share_scope': scope}
    data = root / '_data'
    if data.is_symlink():
        raise ValueError('Catalog directory symlinks are unsupported')
    data.mkdir(exist_ok=True)
    with writer_lock(data / 'manual-catalog.lock'):
        files = {'items.jsonl': ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows),
                 'source.json': json.dumps(declaration, ensure_ascii=False, indent=2) + '\n'}
        for name, body in files.items():
            p = data / name
            if p.is_symlink():
                raise ValueError('Catalog symlinks are unsupported')
            if p.exists() and p.read_text() == body:
                continue
            temp = p.with_name(name + '.tmp')
            temp.write_text(body, encoding='utf-8')
            os.replace(temp, p)
    return {'status': 'declared', 'collection': collection, 'items': len(rows), 'share_scope': scope}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive_root', type=Path)
    p.add_argument('--collection', required=True)
    p.add_argument('--display-name', required=True)
    p.add_argument('--share-scope', choices=['private', 'restricted', 'public'], default='private')
    a = p.parse_args()
    print(json.dumps(build(a.archive_root, a.collection, a.display_name, a.share_scope), ensure_ascii=False))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Render saved docs +fetch JSON through pandoc with relative verified media.

The source JSON remains untouched. This is a conversion preflight, not proof
that the resulting note displays correctly in the recipient's actual reader.
"""
import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse

from check_archive_storage import FEISHU_HOST_SUFFIXES


WHITEBOARD_MARKER = 'FEISHU-RENDER-WHITEBOARD-'
SOURCE_TYPES = {'docx': 'docx', 'wiki': 'wiki', 'sheets': 'sheet', 'minutes': 'minutes'}


def attrs(tag):
    return {k: html.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', tag)}


def prepare(content, media):
    used = set()

    def image(match):
        a = attrs(match.group())
        token = a.get('src')
        if token not in media:
            raise ValueError('Embedded image has no verified local original: ' + str(token))
        used.add(token)
        return '<img src="' + html.escape(media[token], quote=True) + '" alt="' + html.escape(a.get('alt', ''), quote=True) + '">'

    def video(match):
        a = attrs(match.group())
        token = a.get('token')
        if token not in media:
            raise ValueError('Embedded attachment has no verified local original: ' + str(token))
        used.add(token)
        target = html.escape(media[token], quote=True)
        name = html.escape(a.get('name') or Path(media[token]).name)
        # Pandoc produces a native Markdown embed and a separate filename link.
        embed = f'<p><img src="{target}" alt=""></p>' if Path(urllib.parse.unquote(media[token])).suffix.lower() == '.mp4' else ''
        return embed + f'<p><a href="{target}">{name}</a></p>'

    def whiteboard(match):
        token = attrs(match.group()).get('token')
        if token not in media:
            raise ValueError('Embedded whiteboard has no verified local preview: ' + str(token))
        used.add(token)
        return f'<p>{WHITEBOARD_MARKER}{token}</p>'

    content = re.sub(r'<img\b[^>]*>', image, content)
    content = re.sub(r'<source\b[^>]*>', video, content)
    content = re.sub(r'<whiteboard\b[^>]*>(?:\s*</whiteboard>)?', whiteboard,
                     content, flags=re.DOTALL)
    content = re.sub(r'</?(?:figure|view|span)\b[^>]*>', '', content)
    return content, used


def document_title(document, fallback):
    if document.get('title'):
        return document['title']
    content = document.get('content') or ''
    match = re.search(r'<title\b[^>]*>(.*?)</title\s*>', content,
                      flags=re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else ''
    return title or fallback


def discussion_destination(root, output, discussion):
    if discussion is None:
        return None
    relative = Path(discussion)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Discussion companion must stay inside the archive folder')
    actual = (root / relative).resolve()
    if not actual.is_relative_to(root) or not actual.is_file():
        raise ValueError('Discussion companion is missing from the archive folder')
    relative = Path(os.path.relpath(actual, output.parent)).as_posix()
    if any(c in relative for c in '<>\n\r'):
        raise ValueError('Discussion name cannot be represented by a native Markdown destination')
    return f'[Comments and feedback](<{relative}>)'


def render(capture, manifest, output, source, discussion=None):
    data = json.loads(Path(capture).read_text(encoding='utf-8'))
    document = data['data']['document']
    content = document.get('content')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Capture has no document HTML body')
    manifest = Path(manifest).resolve()
    root = manifest.parent
    output = Path(output).resolve()
    if not output.is_relative_to(root):
        raise ValueError('Output note must stay inside the declared archive folder')
    media = {}
    for item in json.loads(manifest.read_text())['files']:
        if item.get('storage') == 'git' or not item.get('cache_path'):
            continue
        path = Path(item['cache_path'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Local media must live under the archive folder')
        actual = (root / path).resolve()
        if not actual.is_relative_to(root) or not actual.is_file() or actual.stat().st_size != item['bytes']:
            raise ValueError('Local original is missing or has an unexpected byte count')
        source_token = item.get('source_token')
        locator_token = item.get('locator', {}).get('token')
        if source_token and locator_token and source_token != locator_token:
            raise ValueError('Source token and Feishu locator token disagree')
        token = source_token or locator_token
        if not isinstance(token, str) or not token:
            raise ValueError('Local original has no captured source token for rendering')
        relative = Path(os.path.relpath(actual, output.parent)).as_posix()
        media[token] = urllib.parse.quote(relative, safe='/')
    content, used = prepare(content, media)
    origin = urllib.parse.urlsplit(source)
    host_suffixes = tuple('.' + host for host in FEISHU_HOST_SUFFIXES)
    if origin.scheme != 'https' or not origin.hostname or not origin.hostname.endswith(host_suffixes):
        raise ValueError('Source must be an original Feishu/Lark URL')
    source_kind = origin.path.strip('/').split('/')[0]
    source_type = SOURCE_TYPES.get(source_kind, source_kind or 'unknown')
    discussion_link = discussion_destination(root, output, discussion)

    def cite(match):
        a = attrs(match.group())
        kind = a.get('file-type')
        token = a.get('doc-id')
        if kind not in ('wiki', 'docx', 'sheets') or not token:
            return match.group()  # Keep unsupported reference in the prepared source worklist.
        url = f'https://{origin.hostname}/{kind}/{urllib.parse.quote(token, safe="")}'
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(a.get("title") or token)}</a>'

    content = re.sub(r'<cite\b[^>]*>\s*</cite>', cite, content)
    whiteboard_counts = {}
    for token in re.findall(re.escape(WHITEBOARD_MARKER) + r'([A-Za-z0-9_-]+)', content):
        whiteboard_counts[token] = whiteboard_counts.get(token, 0) + 1
    converted = subprocess.run(['pandoc', '-f', 'html', '-t', 'gfm', '--wrap=none'],
                               input=content, text=True, capture_output=True, check=True).stdout
    # Blank lines keep adjacent images independent in Markdown readers.
    converted = converted.replace(')![](', ')\n\n![](')
    if '�' in converted:
        raise ValueError('Conversion contains replacement characters')
    for token, count in whiteboard_counts.items():
        marker = WHITEBOARD_MARKER + token
        if converted.count(marker) != count:
            raise ValueError('Pandoc changed a localized whiteboard marker: ' + token)
        converted = converted.replace(marker, f'![Whiteboard {token}]({media[token]})')
    for token in used:
        if media[token] not in converted:
            raise ValueError('Pandoc dropped a localized media reference')
        decoded = urllib.parse.unquote(media[token])
        if any(c in decoded for c in '<>\n\r'):
            raise ValueError('Media name cannot be represented by a native Markdown destination')
        converted = converted.replace('(' + media[token] + ')', '(<'+ decoded + '>)')
    title = document_title(document, output.stem)
    front = ('---\ntitle: ' + json.dumps(title, ensure_ascii=False) +
             '\nsource: ' + json.dumps(source) +
             '\nsource_type: ' + json.dumps(source_type) +
             ('\nsource_revision: ' + str(document['revision_id']) if document.get('revision_id') is not None else '') +
             '\nextracted: ' + json.dumps(datetime.now(timezone.utc).date().isoformat()) +
             '\ncapture_method: lark-cli-api\npost_process: "saved API HTML → localized media/whiteboards → pandoc GFM"\n' +
             'qmd:\n  metadata:\n    platform: "feishu"\n    key: ' + json.dumps(origin.path.rstrip('/').split('/')[-1]) +
             '\n    kind: "document_snapshot"\n---\n\n')
    if discussion_link:
        front += discussion_link + '\n\n'
    if output.exists():
        raise ValueError('Output already exists; render to a new pilot path and review the diff')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(front + converted, encoding='utf-8')
    return {'output': str(output), 'media_references': len(used),
            'whiteboard_references': sum(whiteboard_counts.values()),
            'discussion_links': int(bool(discussion_link)),
            'status': 'converted_reader_pending', 'actual_reader': 'not_verified'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--source', required=True)
    p.add_argument('--discussion', help='Relative Markdown discussion companion inside the archive')
    a = p.parse_args()
    print(json.dumps(render(a.capture, a.manifest, a.output, a.source, a.discussion), ensure_ascii=False))


if __name__ == '__main__':
    main()

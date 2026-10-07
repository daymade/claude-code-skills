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
import html
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse


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

    content = re.sub(r'<img\b[^>]*>', image, content)
    content = re.sub(r'<source\b[^>]*>', video, content)
    content = re.sub(r'</?(?:figure|view|span)\b[^>]*>', '', content)
    return content, used


def render(capture, manifest, output, source):
    data = json.loads(Path(capture).read_text(encoding='utf-8'))
    document = data['data']['document']
    content = document.get('content')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Capture has no document HTML body')
    manifest = Path(manifest).resolve()
    root = manifest.parent
    output = Path(output).resolve()
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
        token = item.get('locator', {}).get('token')
        relative = Path(os.path.relpath(actual, output.parent)).as_posix()
        media[token] = urllib.parse.quote(relative, safe='/')
    content, used = prepare(content, media)
    origin = urllib.parse.urlsplit(source)
    if origin.scheme != 'https' or not origin.hostname or not origin.hostname.endswith('.feishu.cn'):
        raise ValueError('Source must be the original Feishu URL')

    def cite(match):
        a = attrs(match.group())
        kind = a.get('file-type')
        token = a.get('doc-id')
        if kind not in ('wiki', 'docx', 'sheets') or not token:
            return match.group()  # Keep unsupported reference in the prepared source worklist.
        url = f'https://{origin.hostname}/{kind}/{urllib.parse.quote(token, safe="")}'
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(a.get("title") or token)}</a>'

    content = re.sub(r'<cite\b[^>]*>\s*</cite>', cite, content)
    converted = subprocess.run(['pandoc', '-f', 'html', '-t', 'gfm', '--wrap=none'],
                               input=content, text=True, capture_output=True, check=True).stdout
    # Blank lines keep adjacent images independent in Markdown readers.
    converted = converted.replace(')![](', ')\n\n![](')
    if '\ufffd' in converted:
        raise ValueError('Conversion contains replacement characters')
    for token in used:
        if media[token] not in converted:
            raise ValueError('Pandoc dropped a localized media reference')
        decoded = urllib.parse.unquote(media[token])
        if any(c in decoded for c in '<>\n\r'):
            raise ValueError('Media name cannot be represented by a native Markdown destination')
        converted = converted.replace('(' + media[token] + ')', '(<'+ decoded + '>)')
    title = document.get('title') or output.stem
    front = ('---\ntitle: ' + json.dumps(title, ensure_ascii=False) + '\nsource: ' + json.dumps(source) +
             '\ncapture_method: lark-cli-api\npost_process: "saved API HTML → localized media → pandoc GFM"\n' +
             'qmd:\n  metadata:\n    platform: "feishu"\n    key: ' + json.dumps(origin.path.rstrip('/').split('/')[-1]) +
             '\n    kind: "document_snapshot"\n---\n\n')
    if output.exists():
        raise ValueError('Output already exists; render to a new pilot path and review the diff')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(front + converted, encoding='utf-8')
    return {'output': str(output), 'media_references': len(used), 'actual_reader': 'not_verified'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--source', required=True)
    a = p.parse_args()
    print(json.dumps(render(a.capture, a.manifest, a.output, a.source), ensure_ascii=False))


if __name__ == '__main__':
    main()

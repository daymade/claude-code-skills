#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Download source-card attachments from a saved docs +fetch response.

With --resume --recoveries, reconcile verified original-preview files offline.

Uses the installed lark-cli as user; never logs in, exports browser credentials,
uploads, changes permissions or selects durable storage. Exit 0: all unique
attachments verified; 3: partial downloads; 2: invalid input/local state.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from check_archive_storage import stable_locator_error, validate_manifest
from feishu_extract_refs import attachment_sources, extract


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory(content):
    items, names = {}, {}
    for source in attachment_sources(content):
        token, name, size = (source.get(k) for k in ('token', 'name', 'size'))
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9]{20,}', token):
            raise ValueError('Attachment token missing or invalid')
        if (not isinstance(name, str) or not name or name in {'.', '..'}
                or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name)
                or name.endswith((' ', '.'))
                or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', name)):
            raise ValueError('Attachment name is not a portable single filename')
        if not isinstance(size, str) or not re.fullmatch(r'[0-9]+', size):
            raise ValueError('Attachment size missing or invalid; do not guess it')
        item = {'token': token, 'name': name, 'size': int(size), 'source_mime': source.get('mime')}
        if token in items and items[token] != item:
            raise ValueError('Repeated token has conflicting attachment metadata')
        key = unicodedata.normalize('NFC', name).casefold()
        if key in names and names[key] != token:
            raise ValueError('Different attachments share a destination filename')
        names[key], items[token] = token, item
    return list(items.values())


def verify_file(path, item):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != item['size']:
        raise ValueError('Attachment bytes differ from captured size')
    suffix = path.suffix.lower()
    mime = 'application/octet-stream'
    worksheets = []
    office = {
        '.xlsx': ('xl/workbook.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        '.docx': ('word/document.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        '.pptx': ('ppt/presentation.xml', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'),
    }
    if suffix in office or suffix == '.zip':
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                raise ValueError('Attachment ZIP integrity failed')
            mime = 'application/zip'
            if suffix in office:
                member, mime = office[suffix]
                tree = ET.fromstring(z.read(member))
                ET.fromstring(z.read('[Content_Types].xml'))
                if suffix == '.xlsx':
                    worksheets = [e.attrib for e in tree.iter() if e.tag.endswith('}sheet')]
    elif suffix == '.pdf':
        with path.open('rb') as f:
            if not f.read(5) == b'%PDF-':
                raise ValueError('Attachment is not a PDF')
        mime = 'application/pdf'
    return {'bytes': path.stat().st_size, 'sha256': digest(path), 'mime': mime,
            'worksheets': worksheets}


def write_json(path, value):
    if path.is_symlink():
        raise ValueError('Refuse symlink output')
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.json-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def verified_recoveries(path, binding, items):
    """Bind permitted original-preview receipts to this exact capture, offline."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refuse symlink recovery input')
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('binding') != binding:
        raise ValueError('Recovery capture/source/profile binding changed')
    if binding.get('revision_id') is None:
        raise ValueError('Recovery import needs the captured source revision')
    rows = data.get('items')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Recovery items must be a nonempty list')
    expected = {item['token']: item for item in items}
    recovered = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('token'), str)
                or row['token'] not in expected):
            raise ValueError('Recovery token is not in this capture')
        token = row['token']
        if token in recovered:
            raise ValueError('Duplicate recovery token')
        paths = []
        for key in ('path', 'receipt'):
            value = row.get(key)
            if not isinstance(value, str) or not value or not Path(value).is_absolute():
                raise ValueError('Recovery payload and receipt need explicit absolute paths')
            candidate = Path(value)
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError('Recovery payload or receipt is missing or unsafe')
            paths.append(candidate)
        payload, receipt_path = paths
        receipt = json.loads(receipt_path.read_text())
        identity = f"{token}@{binding['revision_id']}"
        if (not isinstance(receipt, dict) or receipt.get('identity') != identity
                or receipt.get('status') not in ('complete', 'already_verified')
                or receipt.get('proxy') is not False
                or type(receipt.get('bytes')) is not int
                or not isinstance(receipt.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', receipt['sha256'])):
            raise ValueError('Recovery needs a matching original-preview verification receipt')
        verified = verify_file(payload, expected[token])
        if any(receipt[key] != verified[key] for key in ('bytes', 'sha256')):
            raise ValueError('Recovery payload differs from its verified receipt')
        recovered[token] = (payload, verified, identity)
    return recovered


def archive(capture, output, source, profile=None, workers=4, timeout=90, resume=False,
            recoveries=None):
    raw = Path(capture).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('ok') is not True:
        raise ValueError('Capture is not a successful docs +fetch response')
    payload = data.get('data')
    document = payload.get('document') if isinstance(payload, dict) else None
    if not isinstance(document, dict):
        raise ValueError('Capture has no document object')
    content = document.get('content')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Capture has no document content')
    problem = stable_locator_error({'system': 'feishu', 'source_url': source,
                                    'token': 'SyntheticValidationToken12345'}, 'source')
    if problem:
        raise ValueError(problem)
    if not 1 <= workers <= 8 or timeout <= 0:
        raise ValueError('Use 1–8 workers and a positive command timeout')
    if profile is not None and (not isinstance(profile, str) or not profile.strip()):
        raise ValueError('An explicit profile must not be blank')
    items = inventory(content)
    if not items:
        raise ValueError('No source-card attachments; use the reference worklist for other resources')
    if recoveries is not None and not resume:
        raise ValueError('Recovery import requires --resume; it never starts acquisition')
    if recoveries is None and shutil.which('lark-cli') is None:
        raise ValueError('lark-cli is required; prepare the CLI before downloading')
    binding = {'capture_sha256': hashlib.sha256(raw).hexdigest(), 'source': source,
               'profile': profile, 'document_id': document.get('document_id'),
               'revision_id': document.get('revision_id')}
    output = Path(output).absolute()
    if output.is_symlink():
        raise ValueError('Refuse symlink archive root')
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
    elif not output.is_dir():
        raise ValueError('Resume needs the original output directory')
    output = output.resolve()
    lock = output / '.archive-attachments.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        state = output / 'attachment-state.json'
        manifest_path = output / 'manifest.json'
        manifest_before = manifest_path.read_bytes() if manifest_path.is_file() else None
        previous = {}
        prior_results = {}
        prior_manifest = None
        if resume:
            if state.is_symlink() or not state.is_file():
                raise ValueError('Resume state missing or unsafe')
            state_before = state.read_bytes()
            saved = json.loads(state_before)
            if not isinstance(saved, dict) or saved.get('binding') != binding:
                raise ValueError('Capture/source/profile changed; use a new output directory')
            prior_items = saved.get('items')
            if not isinstance(prior_items, list) or any(not isinstance(i, dict) for i in prior_items):
                raise ValueError('Resume state has invalid attachment records')
            if any(not isinstance(i.get('attempts', []), list) for i in prior_items):
                raise ValueError('Invalid prior attempt history; preserve the state')
            stored_capture = output / 'capture.json'
            if stored_capture.is_symlink() or not stored_capture.is_file() or stored_capture.read_bytes() != raw:
                raise ValueError('Archived capture changed; preserve it and use a new output directory')
            previous = {i['token']: i for i in prior_items if i['status'] == 'verified'}
            prior_results = {i['token']: i for i in prior_items}
            manifest_path = output / 'manifest.json'
            if manifest_path.exists() or manifest_path.is_symlink():
                if manifest_path.is_symlink() or not manifest_path.is_file():
                    raise ValueError('Resume manifest missing or unsafe')
                prior_manifest = json.loads(manifest_path.read_text())
                errors = validate_manifest(prior_manifest)
                if errors or prior_manifest.get('source') != source:
                    raise ValueError('Resume manifest invalid or belongs to another source')
                if not isinstance(prior_manifest.get('resource_summary', {}), dict):
                    raise ValueError('Resume manifest resource summary must be an object')
        else:
            (output / 'capture.json').write_bytes(raw)
            write_json(state, {'binding': binding, 'items': []})
            state_before = state.read_bytes()
        recovered = verified_recoveries(recoveries, binding, items) if recoveries is not None else {}
        media = output / 'attachments'
        if media.is_symlink():
            raise ValueError('Refuse symlink attachment directory')
        media.mkdir(exist_ok=True)
        env = dict(os.environ, LARK_CLI_NO_PROXY='1', LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1',
                   LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')

        def download(item):
            dest = media / item['name']
            try:
                if item['token'] in recovered:
                    payload, verified, identity = recovered[item['token']]
                    if not dest.exists() and not dest.is_symlink():
                        with tempfile.TemporaryDirectory(prefix='.recover-', dir=output) as temp:
                            target = Path(temp) / item['name']
                            shutil.copyfile(payload, target)
                            copied = verify_file(target, item)
                            if copied['sha256'] != verified['sha256']:
                                raise ValueError('Recovery payload changed during import')
                            os.link(target, dest)
                    actual = verify_file(dest, item)
                    if actual['sha256'] != verified['sha256']:
                        raise ValueError('Existing attachment differs from recovery; preserve it')
                    return {**item, **actual, 'status': 'verified', 'transfer': 'recovered',
                            'recovery': {'method': 'original_preview', 'identity': identity}}
                if dest.exists() or dest.is_symlink():
                    verified = verify_file(dest, item)
                    if item['token'] not in previous or previous[item['token']]['sha256'] != verified['sha256']:
                        raise ValueError('Existing attachment is unowned or changed; preserve it')
                    return {**item, **verified, 'status': 'verified', 'transfer': 'reused',
                            **({'recovery': previous[item['token']]['recovery']}
                               if 'recovery' in previous[item['token']] else {})}
                if recoveries is not None:
                    return {**item, 'status': 'failed',
                            'error': prior_results.get(item['token'], {}).get(
                                'error', 'Not recovered; acquisition was not attempted')}
                with tempfile.TemporaryDirectory(prefix='.download-', dir=output) as temp:
                    target = Path(temp) / item['name']
                    cmd = ['lark-cli'] + (['--profile', profile] if profile else [])
                    cmd += ['docs', '+media-download', '--token', item['token'], '--as', 'user',
                            '--output', './' + target.relative_to(output).as_posix(), '--format', 'json']
                    result = subprocess.run(cmd, cwd=output, env=env, capture_output=True,
                                            text=True, timeout=timeout)
                    if result.returncode:
                        # Do not put signed URLs or credential-bearing stderr in the manifest.
                        raise ValueError(f'lark-cli download failed (exit {result.returncode}); inspect this token with the current CLI guide')
                    reply = json.loads(result.stdout)
                    if not isinstance(reply, dict) or reply.get('ok') is not True:
                        raise ValueError('lark-cli did not confirm download success')
                    verified = verify_file(target, item)
                    # Atomic no-clobber publication; never replace an existing user's file.
                    os.link(target, dest)
                    return {**item, **verified, 'status': 'verified', 'transfer': 'downloaded'}
            except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile, ET.ParseError,
                    subprocess.TimeoutExpired) as exc:
                return {**item, 'status': 'failed', 'error': str(exc)}

        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(download, items):
                prior = prior_results.get(result['token'], {})
                attempts = prior.get('attempts', [])
                if not isinstance(attempts, list):
                    raise ValueError('Invalid prior attempt history; preserve the state')
                attempted = recoveries is None or result['token'] in recovered
                if prior.get('status') == 'failed' and attempted:
                    attempts = [*attempts, {k: prior[k] for k in ('status', 'error') if k in prior}]
                if attempts:
                    result['attempts'] = attempts
                results.append(result)
                if state.read_bytes() != state_before:
                    raise ValueError('Attachment state changed during this run; preserve the later edit')
                write_json(state, {'binding': binding, 'items': results})
                state_before = state.read_bytes()
        good = [r for r in results if r['status'] == 'verified']
        files = [{'role': 'embedded_media_original', 'storage': 'source',
                  'locator': {'system': 'feishu', 'source_url': source, 'token': r['token']},
                  'cache_path': 'attachments/' + r['name'],
                  **{k: r[k] for k in ('bytes', 'sha256', 'mime')}} for r in good]
        for name in ('capture.json', 'attachment-state.json'):
            path = output / name
            files.append({'role': 'document_snapshot', 'storage': 'git', 'path': name,
                          'bytes': path.stat().st_size, 'sha256': digest(path), 'mime': 'application/json'})
        downloaded_tokens = {r['token'] for r in items}
        pending = [r for r in extract(content)
                   if r['type'] != 'file' or r['ref'] not in downloaded_tokens]
        manifest = prior_manifest or {
            'schema_version': 1, 'source': source,
            'captured_at': datetime.now(timezone.utc).isoformat(), 'files': [],
            'resource_summary': {'reader': 'not_checked', 'independent_retention': 'not_checked'}}
        # Storage/reader owners may have added OSS locators, replicas or notes.
        # Preserve their entries; update only this helper's mutable state snapshots.
        for entry in files:
            key = 'path' if entry['storage'] == 'git' else 'cache_path'
            matches = [i for i, old in enumerate(manifest['files']) if old.get(key) == entry[key]]
            if len(matches) > 1:
                raise ValueError('Resume manifest has duplicate artifact paths')
            if not matches:
                manifest['files'].append(entry)
            elif key == 'path':
                manifest['files'][matches[0]] = entry
            else:
                old = manifest['files'][matches[0]]
                if any(old.get(k) != entry[k] for k in ('bytes', 'sha256')):
                    raise ValueError('Resume artifact metadata changed; preserve the existing manifest')
        summary = manifest.setdefault('resource_summary', {})
        for key in ('requested_attachments', 'verified_attachments'):
            summary.pop(key, None)
        summary.update({
            'failed_attachments': [r for r in results if r['status'] != 'verified'],
            'other_references': pending})
        errors = validate_manifest(manifest)
        if errors:
            raise ValueError('; '.join(errors))
        current_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
        if current_manifest != manifest_before:
            raise ValueError('Manifest changed during this run; preserve the later edit')
        if state.is_symlink() or state.read_bytes() != state_before:
            raise ValueError('Attachment state changed during this run; preserve the later edit')
        write_json(output / 'manifest.json', manifest)
        return {'status': 'attachments_complete' if len(good) == len(items) else 'partial',
                'requested': len(items), 'verified': len(good), 'failed': len(items)-len(good),
                'bytes': sum(r['bytes'] for r in good), 'other_references': len(pending),
                'manifest': str(output / 'manifest.json'), 'reader': 'not_checked',
                'independent_retention': 'not_checked'}
    finally:
        lock.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', help='Complete saved docs +fetch JSON response')
    p.add_argument('--source', required=True, help='Original Feishu/Lark document URL (no share query)')
    p.add_argument('--output', required=True, help='New archive directory, or the existing directory with --resume')
    p.add_argument('--profile', help='Already authorized lark-cli profile; never switches the global profile')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--timeout', type=int, default=90)
    p.add_argument('--resume', action='store_true', help='Reuse only files verified by this exact saved capture')
    p.add_argument('--recoveries', help='Offline import of bound original-preview receipts; requires --resume and does not download')
    a = p.parse_args()
    try:
        result = archive(a.capture, a.output, a.source, a.profile, a.workers, a.timeout, a.resume,
                         a.recoveries)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(json.dumps({'status': 'invalid', 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'attachments_complete' else 3


if __name__ == '__main__':
    raise SystemExit(main())

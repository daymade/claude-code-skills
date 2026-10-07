#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check a movable Markdown archive, then bind actual-reader evidence to its bytes.

inspect: structural/content check only (exit 0, status=reader_pending).
record-reader: validate supplied observation coverage and bind it to inspect.
finalize: re-read the actual archive and require matching reader evidence.
Exit 1 means invalid files/evidence; exit 3 means actual-reader proof is absent.
Evidence records provenance; this tool cannot authenticate an observer or see UI.
"""
import argparse
import datetime
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import urllib.parse
from check_archive_storage import validate_manifest

VIDEO = {'.mp4', '.webm', '.mov', '.mkv'}
IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.heic'}
REMOTE_LINKS = {'http', 'https', 'mailto', 'tel'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()


def local(root, base, target, require_file=True):
    decoded = urllib.parse.unquote(urllib.parse.urlsplit(target).path)
    if not decoded or Path(decoded).is_absolute() or PureWindowsPath(decoded).is_absolute() or '\\' in decoded:
        raise ValueError('Local reference must be a relative archive path: ' + target)
    lexical = base / decoded
    resolved = lexical.resolve()
    if not resolved.is_relative_to(root) or (require_file and not resolved.is_file()):
        raise ValueError('Missing local reference or reference leaves archive: ' + target)
    # Reject even in-root symlinks: they depend on a second filesystem object.
    for p in [lexical, *lexical.parents]:
        if p.is_symlink():
            raise ValueError('Symlink in local delivery path: ' + target)
        if p == root:
            break
    return resolved


class HtmlRefs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, pairs):
        a = dict(pairs)
        if tag in {'img', 'video', 'audio', 'source', 'iframe', 'embed'}:
            self.refs.append((a.get('src', ''), True, tag))
        elif tag == 'object':
            self.refs.append((a.get('data', ''), True, tag))
        elif tag == 'a' and a.get('href'):
            self.refs.append((a['href'], False, tag))


def references(text):
    result = subprocess.run(['pandoc', '-f', 'gfm+wikilinks_title_after_pipe', '-t', 'json'],
                            input=text, capture_output=True, text=True, check=True)
    refs = []

    def walk(value, embedded_wikilink=False):
        if isinstance(value, list):
            for i, child in enumerate(value):
                previous = value[i-1] if i else None
                wiki_embed = (isinstance(child, dict) and child.get('t') == 'Link' and
                              'wikilink' in child['c'][0][1] and isinstance(previous, dict) and
                              previous.get('t') == 'Str' and previous.get('c', '').endswith('!'))
                walk(child, wiki_embed)
        elif isinstance(value, dict):
            kind, c = value.get('t'), value.get('c')
            if kind in {'Code', 'CodeBlock'}:
                return
            if kind in {'Link', 'Image'}:
                refs.append((c[2][0], kind == 'Image' or embedded_wikilink, 'markdown'))
                walk(c[1])  # A linked thumbnail has its own image reference.
            elif kind in {'RawBlock', 'RawInline'} and c[0] == 'html':
                parser = HtmlRefs()
                parser.feed(c[1])
                refs.extend(parser.refs)
            else:
                walk(c)
    walk(json.loads(result.stdout)['blocks'])
    return refs


def inspect(root, manifest_path, notes, reader='Obsidian'):
    root = Path(root).resolve()
    lexical_manifest = Path(manifest_path).absolute()
    manifest_path = lexical_manifest.resolve()
    if not manifest_path.is_relative_to(root) or not root.is_dir():
        raise ValueError('Manifest must belong to the declared delivery root')
    if lexical_manifest.is_symlink():
        raise ValueError('Delivery manifest must be a regular archive file')
    if not isinstance(reader, str) or not reader.strip():
        raise ValueError('Name the intended actual reader')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError('Invalid storage manifest: ' + '; '.join(errors))
    entries = {}
    for item in manifest['files']:
        name = item.get('path') if item['storage'] == 'git' else item.get('cache_path')
        if not name:
            continue
        p = local(root, root, name, require_file=False)
        relative = p.relative_to(root).as_posix()
        if relative in entries:
            raise ValueError('Duplicate local manifest path: ' + relative)
        entries[relative] = item
    initial = sorted({local(root, root, n).relative_to(root).as_posix() for n in notes})
    if not initial or any(Path(n).suffix.lower() != '.md' for n in initial):
        raise ValueError('At least one Markdown entry note is required')
    files, observed, pending = {}, {}, list(initial)

    def verify(p):
        rel = p.relative_to(root).as_posix()
        if rel in files:
            return rel
        item = entries.get(rel)
        if not item or type(item.get('bytes')) is not int or not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', '')):
            raise ValueError('Referenced file lacks manifest byte/hash evidence: ' + rel)
        actual = {'bytes': p.stat().st_size, 'sha256': sha(p)}
        if actual != {k: item[k] for k in actual}:
            raise ValueError('Referenced file differs from manifest: ' + rel)
        files[rel] = actual
        return rel

    while pending:
        rel = pending.pop(0)
        if rel in observed:
            continue
        note = root / rel
        verify(note)
        text = note.read_text(encoding='utf-8')
        if '\ufffd' in text:
            raise ValueError('Replacement characters in final note: ' + rel)
        targets, images, videos, links = set(), set(), set(), set()
        for target, embedded, syntax in references(text):
            parsed = urllib.parse.urlsplit(target)
            if parsed.scheme or parsed.netloc:
                if embedded or parsed.scheme.lower() not in REMOTE_LINKS or (parsed.netloc and not parsed.scheme):
                    raise ValueError('External/local-scheme embed is not a movable original: ' + target)
                continue
            if target.startswith('#'):
                continue
            p = local(root, note.parent, target)
            name = verify(p)
            targets.add(name)
            suffix = p.suffix.lower()
            if syntax != 'markdown' and (embedded or suffix in VIDEO | IMAGES):
                raise ValueError('Media uses raw HTML instead of native Markdown: ' + rel)
            if suffix in IMAGES:
                images.add(name)
            if suffix in VIDEO:
                videos.add(name)
            if not embedded:
                links.add(name)
            if suffix == '.md' and name not in observed:
                pending.append(name)
        observed[rel] = {'targets': sorted(targets), 'images': sorted(images),
                         'videos': sorted(videos), 'links': sorted(links)}
    payload = {'schema_version': 1, 'expected_reader': reader, 'manifest': manifest_path.relative_to(root).as_posix(),
               'manifest_sha256': sha(manifest_path), 'entry_notes': initial,
               'files': dict(sorted(files.items())), 'notes': dict(sorted(observed.items()))}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {'status': 'reader_pending', 'checked_at': now, 'artifact_fingerprint': canonical(payload),
            'artifact': payload, 'examined_notes': len(observed), 'examined_files': len(files),
            'actual_reader': 'not_verified'}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves previous evidence and prevents self-overwrite.
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def stamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing evidence time')
    d = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Evidence time must include a timezone')
    return d


def validate_observation(report, e):
    artifact = report.get('artifact')
    if not isinstance(artifact, dict) or report.get('artifact_fingerprint') != canonical(artifact):
        raise ValueError('Inspect report fingerprint is invalid')
    if (e.get('kind') not in {'user-acceptance', 'native-reader-observation'} or
            e.get('reader') != artifact.get('expected_reader') or
            not isinstance(e.get('source_reference'), str) or not e['source_reference'].strip() or
            e.get('artifact_fingerprint') != report['artifact_fingerprint']):
        raise ValueError('Missing reader/source provenance or artifact fingerprint mismatch')
    observed_at = stamp(e.get('observed_at'))
    if observed_at < stamp(report.get('checked_at')) or observed_at > datetime.datetime.now(datetime.timezone.utc):
        raise ValueError('Observation must follow the inspect snapshot and not be in the future')
    if e['kind'] == 'user-acceptance':
        if not isinstance(e.get('quote'), str) or not e['quote'].strip() or e.get('entry_notes') != artifact['entry_notes']:
            raise ValueError('User acceptance needs the actual quote and exact entry-note scope')
    else:
        rows = e.get('observations')
        if (not isinstance(rows, list) or len(rows) != len(artifact['notes']) or
                {r.get('note') for r in rows if isinstance(r, dict)} != set(artifact['notes'])):
            raise ValueError('Native observation must cover every inspected note')
        for row in rows:
            expected = artifact['notes'][row['note']]
            if (row.get('images_displayed') != expected['images'] or row.get('videos_played') != expected['videos'] or
                    row.get('links_opened') != expected['links'] or row.get('reopened') is not True):
                raise ValueError('Native reader checks do not cover the final references')
        files = e.get('evidence_files')
        if not isinstance(files, list) or not files:
            raise ValueError('Native observation needs actual captured evidence files')
        for row in files:
            p = Path(row.get('path', ''))
            if not p.is_absolute() or not p.is_file() or not p.stat().st_size or sha(p) != row.get('sha256'):
                raise ValueError('Captured native-reader evidence is missing or changed')
    return e


def record(report_path, evidence_path, receipt_path):
    report = json.loads(Path(report_path).read_text())
    evidence_path = Path(evidence_path).resolve()
    e = validate_observation(report, json.loads(evidence_path.read_text()))
    receipt = {'schema_version': 1, 'artifact_fingerprint': report['artifact_fingerprint'],
               'checked_at': report['checked_at'],
               'reader': e['reader'], 'evidence_path': str(evidence_path), 'evidence_sha256': sha(evidence_path),
               'observation': e}
    write_new(receipt_path, receipt)
    return {'status': 'reader_evidence_recorded', 'artifact_fingerprint': report['artifact_fingerprint'],
            'provenance_authenticated': False}


def finalize(root, manifest, notes, receipt_path, reader='Obsidian'):
    report = inspect(root, manifest, notes, reader)
    if not Path(receipt_path).is_file():
        return report, 3
    receipt = json.loads(Path(receipt_path).read_text())
    if receipt.get('schema_version') != 1 or receipt.get('artifact_fingerprint') != report['artifact_fingerprint']:
        raise ValueError('Reader evidence is stale for the current artifact')
    evidence = Path(receipt.get('evidence_path', ''))
    if not evidence.is_file() or sha(evidence) != receipt.get('evidence_sha256') or json.loads(evidence.read_text()) != receipt.get('observation'):
        raise ValueError('Reader evidence source is missing or changed')
    # Revalidate its shape/coverage against the original snapshot time. Avoid
    # promoting arbitrary hand-written receipt fields to completion authority.
    observation = validate_observation({**report, 'checked_at': receipt.get('checked_at')}, receipt['observation'])
    if observation.get('artifact_fingerprint') != report['artifact_fingerprint'] or observation.get('reader') != receipt.get('reader'):
        raise ValueError('Reader observation identity differs')
    report.update(status='ready_with_reader_evidence', actual_reader=receipt['reader'],
                  evidence_kind=observation['kind'], provenance_authenticated=False)
    return report, 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ['inspect', 'finalize']:
        s = sub.add_parser(name)
        s.add_argument('--root', type=Path, required=True)
        s.add_argument('--manifest', type=Path, required=True)
        s.add_argument('--note', action='append', required=True)
        s.add_argument('--reader', required=True, help='Actual intended reader, bound into the artifact fingerprint')
        if name == 'inspect':
            s.add_argument('--report', type=Path, required=True)
        else:
            s.add_argument('--reader-receipt', type=Path, required=True)
    s = sub.add_parser('record-reader')
    s.add_argument('--report', type=Path, required=True)
    s.add_argument('--evidence', type=Path, required=True)
    s.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    try:
        if a.command == 'record-reader':
            result, code = record(a.report, a.evidence, a.receipt), 0
        elif a.command == 'inspect':
            result, code = inspect(a.root, a.manifest, a.note, a.reader), 0
            write_new(a.report, result)
        else:
            result, code = finalize(a.root, a.manifest, a.note, a.reader_receipt, a.reader)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1) from None
    raise SystemExit(code)


if __name__ == '__main__':
    main()

"""Full authorized audio-object evidence for video/audio duration differences."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def report_digest(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def pcm_digest(path):
    try:
        result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
            '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le',
            '-f', 'hash', '-hash', 'sha256', '-'], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as error:
        raise ValueError('full audio decode timed out') from error
    value = result.stdout.strip().removeprefix('SHA256=')
    if result.returncode or not re.fullmatch('[0-9a-f]{64}', value) or value == hashlib.sha256(b'').hexdigest():
        raise ValueError('full audio decode failed or empty')
    return value


def authorized(engine, report, bvid, cid, page):
    verified = engine.evaluate_report(report, bvid, cid, page)
    if not verified['download_allowed'] or verified['source_span']['state'] != 'complete':
        raise ValueError('full selected source access required')
    return verified


def attest(engine, report, bvid, cid, page, source, cookie=None):
    """Read the complete current CID/P audio object; do not persist signed URLs."""
    authorized(engine, report, bvid, cid, page)
    source = Path(source).resolve(strict=True)
    size = source.stat().st_size
    if size <= 0:
        raise ValueError('empty source object')
    local = digest(source)
    mid = report['identity']['mid'] if report['identity']['state'] == 'authenticated' else None
    captures = engine.probe(bvid, cid, page, cookie)
    fresh = engine.evaluate(captures, bvid, cid, page, mid)
    authorized(engine, fresh, bvid, cid, page)
    playurl, status = engine.unwrap(captures.get('playurl'))
    audio = playurl.get('dash', {}).get('audio', [])
    if status['state'] != 'ok' or not isinstance(audio, list):
        raise ValueError('selected audio object unavailable')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    matched = None
    for entry in audio[:8]:
        if not isinstance(entry, dict):
            continue
        url = entry.get('baseUrl', entry.get('base_url'))
        if not isinstance(url, str):
            continue
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or not any(
                parsed.hostname.endswith('.' + domain) for domain in ('bilivideo.com', 'bilivideo.cn', 'bilibili.com')):
            continue
        headers = {'User-Agent': engine.UA, 'Referer': 'https://www.bilibili.com'}
        with opener.open(urllib.request.Request(url, headers={**headers, 'Range': 'bytes=0-0'}), timeout=20) as response:
            content_range = response.headers.get('Content-Range', '')
            if response.status != 206 or content_range != f'bytes 0-0/{size}' or len(response.read(2)) != 1:
                continue
        remote = hashlib.sha256()
        count = 0
        with opener.open(urllib.request.Request(url, headers=headers), timeout=20) as response:
            if response.status != 200:
                continue
            while count <= size:
                data = response.read(min(1024 * 1024, size + 1 - count))
                if not data:
                    break
                count += len(data)
                remote.update(data)
        if count == size and remote.hexdigest() == local:
            matched = {'format_id': entry.get('id'), 'object_bytes': count, 'object_sha256': local,
                       'url_sha256': hashlib.sha256(url.encode()).hexdigest(), 'range': content_range}
            break
    if matched is None:
        raise ValueError('local object differs from complete authorized audio object')
    return {'schema_version': 1, 'target': {'bvid': bvid, 'cid': cid, 'page': page},
            'access_report_sha256': report_digest(report), 'fresh_access_report': fresh,
            'source': {'path': str(source), 'bytes': size, 'sha256': local,
                       'pcm_16000_mono_sha256': pcm_digest(source)}, 'remote': matched}


def verify(engine, report, proof, bvid, cid, page, media):
    authorized(engine, report, bvid, cid, page)
    if (type(proof.get('schema_version')) is not int or proof['schema_version'] != 1
            or proof.get('target') != {'bvid': bvid, 'cid': cid, 'page': page}
            or any(type(proof['target'][key]) is not int for key in ('cid', 'page'))):
        raise ValueError('audio object target mismatch')
    if proof.get('access_report_sha256') != report_digest(report):
        raise ValueError('audio object access report changed')
    fresh = proof['fresh_access_report']
    authorized(engine, fresh, bvid, cid, page)
    if any(fresh['identity'][key] != report['identity'][key] for key in ('state', 'mid')):
        raise ValueError('audio object identity changed')
    if fresh['source_span']['expected_duration_s'] != report['source_span']['expected_duration_s']:
        raise ValueError('selected source declaration changed')
    source, remote = proof['source'], proof['remote']
    path = Path(source['path'])
    size = path.stat().st_size
    if (type(source['bytes']) is not int or type(remote['object_bytes']) is not int
            or size <= 0 or source['bytes'] != size or remote['object_bytes'] != size):
        raise ValueError('audio object byte count mismatch')
    sha = digest(path)
    if sha != source['sha256'] or sha != remote['object_sha256'] or remote['range'] != f'bytes 0-0/{size}':
        raise ValueError('audio object bytes changed')
    if not re.fullmatch('[0-9a-f]{64}', remote['url_sha256']) or type(remote['format_id']) is not int:
        raise ValueError('audio object format missing')
    decoded = pcm_digest(path)
    if decoded != source['pcm_16000_mono_sha256'] or pcm_digest(media) != decoded:
        raise ValueError('ASR input is not the complete source audio conversion')
    return report_digest(proof)

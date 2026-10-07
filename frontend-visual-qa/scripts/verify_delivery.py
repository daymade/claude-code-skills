#!/usr/bin/env python3
"""Compare explicitly selected HTTP resources with a frozen artifact manifest.

Read-only GETs; no deployment, authentication, browser or visual verdict.
Exit 0 = matched, 1 = mismatch, 2 = invalid input or incomplete observation.
"""
import argparse
import hashlib
from http.client import HTTPException
import json
import math
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class InvalidManifest(ValueError):
    pass


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite JSON number')


def decode_json(data):
    return json.loads(data, object_pairs_hook=no_duplicates,
                      parse_constant=reject_constant)


def fingerprint(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def origin(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('HTTP(S) origin required')
    if parts.username is not None or parts.password is not None:
        raise ValueError('URL credentials are unsupported')
    return parts.scheme, parts.hostname.lower(), parts.port or (443 if parts.scheme == 'https' else 80)


def scalar(value):
    return (value is None or type(value) in (str, bool, int)
            or (type(value) is float and math.isfinite(value)))


def equal_scalar(expected, observed):
    if type(expected) in (int, float) and type(observed) in (int, float):
        return expected == observed
    return type(expected) is type(observed) and expected == observed


def validate_manifest(value):
    if not isinstance(value, dict) or set(value) != {'schema_version', 'artifact_ref', 'base_url', 'resources'}:
        raise InvalidManifest('manifest requires schema_version, artifact_ref, base_url and resources')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise InvalidManifest('unsupported manifest schema')
    if not isinstance(value['artifact_ref'], str) or not re.fullmatch('[0-9a-f]{40}', value['artifact_ref']):
        raise InvalidManifest('artifact_ref requires a full immutable commit identifier')
    base = value['base_url']
    if not isinstance(base, str) or any(ord(char) < 32 for char in base):
        raise InvalidManifest('invalid base_url')
    try:
        origin(base)
        parts = urlsplit(base)
    except ValueError as error:
        raise InvalidManifest('invalid HTTP(S) base_url') from error
    if parts.query or parts.fragment:
        raise InvalidManifest('base_url must omit query and fragment')
    resources = value['resources']
    if not isinstance(resources, list) or not 1 <= len(resources) <= 64:
        raise InvalidManifest('resources requires 1 to 64 explicit checks')
    for item in resources:
        if not isinstance(item, dict) or set(item) not in ({'path', 'sha256'}, {'path', 'json_fields'}):
            raise InvalidManifest('each resource needs path and exactly one of sha256 or json_fields')
        path = item['path']
        if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
            raise InvalidManifest('resource path must be an origin-relative absolute path')
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise InvalidManifest('resource query, fragment and foreign origin are unsupported')
        decoded = unquote(path)
        if any(ord(char) < 32 for char in decoded) or '\\' in decoded or '..' in decoded.split('/'):
            raise InvalidManifest('invalid resource path')
        if 'sha256' in item:
            if not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
                raise InvalidManifest('resource sha256 must be a full lowercase digest')
        else:
            fields = item['json_fields']
            if not isinstance(fields, dict) or not fields or any(not isinstance(key, str) or not key for key in fields):
                raise InvalidManifest('json_fields requires nonempty literal top-level keys')
            if not all(scalar(v) for v in fields.values()):
                raise InvalidManifest('json_fields supports finite JSON scalar values only')
    return value


class SameOriginRedirect(HTTPRedirectHandler):
    def __init__(self, allowed):
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            same_origin = origin(newurl) == self.allowed
        except ValueError:
            fp.close()
            raise
        if not same_origin:
            fp.close()
            raise ValueError('cross-origin redirect refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(opener, url, allowed, timeout, max_bytes):
    request = Request(url, method='GET', headers={'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'})
    with opener.open(request, timeout=timeout) as response:
        if origin(response.geturl()) != allowed or response.status != 200:
            raise ValueError('unexpected HTTP response')
        if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
            raise ValueError('encoded response unsupported; use browser verification')
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError('response exceeds byte allowance')
        return body


def verify(manifest, timeout=5, max_bytes=16 * 1024 * 1024):
    validate_manifest(manifest)
    if not math.isfinite(timeout) or timeout <= 0 or type(max_bytes) is not int or max_bytes <= 0:
        raise InvalidManifest('timeout and max_bytes must be positive finite values')
    allowed = origin(manifest['base_url'])
    parts = urlsplit(manifest['base_url'])
    prefix = parts.scheme + '://' + parts.netloc
    opener = build_opener(SameOriginRedirect(allowed))
    report = {'status': 'matched', 'artifact_ref': manifest['artifact_ref'],
              'target_fingerprint': fingerprint(manifest['base_url']),
              'checked_resources': 0, 'checked_json_fields': 0,
              'mismatches': [], 'unknown': [],
              'boundary': 'Only supplied byte digests and JSON fields; no source-authenticity, atomic snapshot or visual acceptance proof.'}
    for item in manifest['resources']:
        ref = fingerprint(item['path'])
        try:
            body = fetch(opener, prefix + item['path'], allowed, timeout, max_bytes)
            report['checked_resources'] += 1
            if 'sha256' in item:
                observed = hashlib.sha256(body).hexdigest()
                if observed != item['sha256']:
                    report['mismatches'].append({'resource_fingerprint': ref, 'kind': 'bytes',
                                                  'expected_sha256': item['sha256'], 'observed_sha256': observed})
            else:
                observed = decode_json(body)
                if not isinstance(observed, dict):
                    raise ValueError('JSON response is not an object')
                for key, expected in item['json_fields'].items():
                    report['checked_json_fields'] += 1
                    if key not in observed:
                        report['mismatches'].append({'resource_fingerprint': ref, 'kind': 'missing_field', 'field': key})
                    elif not scalar(observed[key]) or not equal_scalar(expected, observed[key]):
                        report['mismatches'].append({'resource_fingerprint': ref, 'kind': 'json', 'field': key,
                                                      'expected_fingerprint': fingerprint(expected),
                                                      'observed_fingerprint': fingerprint(observed[key])})
        except (HTTPError, URLError, HTTPException, OSError, ValueError, OverflowError) as error:
            if isinstance(error, HTTPError):
                error.close()
            report['unknown'].append({'resource_fingerprint': ref, 'reason': type(error).__name__})
    if report['mismatches']:
        report['status'] = 'mismatched'
        return report, 1
    if report['unknown']:
        report['status'] = 'unprovable'
        return report, 2
    return report, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=5, help='timeout per blocking HTTP operation; not a total deadline')
    parser.add_argument('--max-bytes', type=int, default=16 * 1024 * 1024)
    args = parser.parse_args(argv)
    try:
        manifest = decode_json(args.manifest.read_bytes())
        report, code = verify(manifest, args.timeout, args.max_bytes)
    except InvalidManifest as error:
        report, code = {'status': 'invalid', 'reason': str(error)}, 2
    except (OSError, ValueError, OverflowError) as error:
        report, code = {'status': 'invalid', 'reason': type(error).__name__}, 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == '__main__':
    sys.exit(main())

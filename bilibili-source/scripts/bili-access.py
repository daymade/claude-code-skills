#!/usr/bin/env python3
"""Read-only Bilibili access diagnosis; offline captures never imply entitlement."""
import argparse
import copy
import http.cookiejar
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA_VERSION = 1
FLAGS = ('is_upower_exclusive', 'is_upower_play', 'is_ugc_pay_preview')
ERROR_CATEGORIES = ('http_error', 'network_error', 'timeout', 'invalid_json', 'unexpected_error')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def identifier(value):
    return type(value) is int and value > 0


def field(obj, key):
    if key not in obj:
        return {'state': 'missing', 'value': None}
    value = obj[key]
    return {'state': 'null' if value is None else 'present', 'value': value}


def unwrap(capture):
    if not isinstance(capture, dict):
        return {}, {'state': 'missing', 'code': None}
    body = capture.get('body', capture)
    if not isinstance(body, dict):
        return {}, {'state': 'invalid', 'code': None}
    code = body.get('code')
    http = capture.get('http', 200)
    error = capture.get('error')
    ok = error is None and type(code) is int and code == 0 and type(http) is int and 200 <= http < 300
    data = body.get('data')
    status = {
        'state': 'ok' if ok and isinstance(data, dict) else 'failed',
        'code': code, 'http': http,
    }
    if error is not None:
        status['error'] = error if error in ERROR_CATEGORIES else 'unexpected_error'
    return (data if isinstance(data, dict) and ok else {}), status


def media_check(expected, ffprobe):
    result = {'state': 'unverified', 'expected_duration_s': expected,
              'actual_duration_s': None, 'tolerance_s': None, 'has_audio': None}
    if ffprobe is None:
        return result
    result['state'] = 'unknown'
    if not isinstance(ffprobe, dict) or ffprobe.get('error'):
        return result
    streams = ffprobe.get('streams')
    if not isinstance(streams, list):
        return result
    audio = [s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'audio']
    result['has_audio'] = bool(audio)
    if not audio or not positive(expected):
        return result
    # Prefer audio duration: container/video duration can mask truncated audio.
    durations = []
    for stream in audio:
        try:
            duration = float(stream['duration'])
        except (KeyError, TypeError, ValueError):
            # Container duration is safe only for an audio-only extracted file.
            if len(streams) != len(audio):
                return result
            try:
                duration = float(ffprobe.get('format', {})['duration'])
            except (KeyError, TypeError, ValueError):
                return result
        if not positive(duration):
            return result
        durations.append(duration)
    actual = min(durations)
    # Integer-second page metadata can round/truncate by <1 second.
    # Add a bounded 50ms policy floor, or the declared AAC frame duration.
    # No percentage slack that grows with content length.
    frame_slack = 0.05
    for stream in audio:
        if stream.get('codec_name') == 'aac':
            try:
                rate = float(stream['sample_rate'])
            except (KeyError, TypeError, ValueError):
                return result
            if not positive(rate) or rate < 8000:
                return result
            frame_slack = max(frame_slack, 1024 / rate)
    tolerance = (1.0 if float(expected).is_integer() else 0.0) + frame_slack
    result.update(actual_duration_s=actual, tolerance_s=tolerance,
                  state='complete' if abs(actual - expected) <= tolerance else 'partial')
    return result


def source_check(expected, playurl, status):
    result = {'state': 'unverified', 'expected_duration_s': expected,
              'actual_duration_s': None, 'tolerance_s': None}
    if status['state'] == 'missing':
        return result
    if status['state'] != 'ok':
        result['state'] = 'unknown'
        return result
    durations = []
    try:
        if 'durl' in playurl:
            durl = playurl['durl']
            if not isinstance(durl, list) or not durl:
                raise ValueError('invalid durl')
            lengths = [part['length'] for part in durl]
            if not all(positive(length) for length in lengths):
                raise ValueError('invalid length')
            durations.append(sum(lengths) / 1000)
        if 'dash' in playurl:
            dash = playurl['dash']
            if not isinstance(dash, dict):
                raise ValueError('invalid dash')
            if 'duration' in dash:
                duration = float(dash['duration'])
                if not positive(duration):
                    raise ValueError('invalid duration')
                durations.append(duration)
        if not durations:
            return result
        if not positive(expected):
            raise ValueError('missing part duration')
        tolerance = 1.05 if float(expected).is_integer() else 0.05
        result.update(actual_duration_s=min(durations), tolerance_s=tolerance,
                      state='complete' if all(abs(duration - expected) <= tolerance for duration in durations) else 'partial')
    except (KeyError, ValueError, TypeError):
        result['state'] = 'unknown'
    return result


def decisions(report):
    identity = report['identity']['state']
    entitlement = report['entitlement']['state']
    interfaces = report['interfaces']
    core_ok = all(interfaces[n]['state'] == 'ok' for n in ('nav', 'view', 'player'))
    optional_ok = interfaces['playurl']['state'] in ('ok', 'missing')
    allowed = (report['target']['state'] == 'matched' and core_ok and optional_ok
               and identity in ('authenticated', 'anonymous')
               and entitlement in ('free', 'entitled')
               and (entitlement != 'entitled' or identity == 'authenticated')
               and positive(report['media']['expected_duration_s'])
               and report['source_span']['state'] in ('unverified', 'complete'))
    report['download_allowed'] = bool(allowed)
    report['asr_allowed'] = bool(allowed and report['media']['state'] == 'complete'
                                 and report['media']['has_audio'] is True)
    return report


def evaluate(captures, bvid, cid, page=1, expected_mid=None):
    interfaces = {}
    data = {}
    for name in ('nav', 'view', 'player', 'playurl'):
        data[name], interfaces[name] = unwrap(captures.get(name))
        if name == 'nav' and isinstance(captures.get(name), dict):
            body = captures[name].get('body', captures[name])
            if (isinstance(body, dict) and body.get('code') == -101
                    and isinstance(body.get('data'), dict)
                    and body['data'].get('isLogin') is False
                    and captures[name].get('http', 200) == 200
                    and captures[name].get('error') is None):
                data[name] = body['data']
                interfaces[name]['state'] = 'ok'
    nav, view, player = data['nav'], data['view'], data['player']
    view = view.get('View', view)
    if not isinstance(view, dict):
        view = {}
    identity = {'state': 'unknown', 'mid': nav.get('mid'), 'expected_mid': expected_mid}
    if nav.get('isLogin') is False:
        identity['state'] = 'anonymous'
    elif nav.get('isLogin') is True and identifier(nav.get('mid')):
        identity['state'] = 'authenticated'
    mid = nav.get('mid') if identity['state'] == 'authenticated' else 0
    if identity['state'] != 'unknown':
        if 'login_mid' not in player or player['login_mid'] is None:
            identity['state'] = 'unknown'
        elif type(player['login_mid']) is not int or player['login_mid'] != mid or (expected_mid is not None and mid != expected_mid):
            identity['state'] = 'mismatch'
    pages = view.get('pages')
    selected = [p for p in pages if isinstance(p, dict) and p.get('cid') == cid and p.get('page') == page] if isinstance(pages, list) else []
    matched = (len(selected) == 1 and identifier(cid) and identifier(page)
               and type(player.get('cid')) is int and type(player.get('page_no')) is int
               and view.get('bvid') == bvid
               and player.get('bvid') == bvid and player.get('cid') == cid
               and player.get('page_no') == page)
    mismatch = (any(v is not None and v != want for v, want in (
        (view.get('bvid'), bvid), (player.get('bvid'), bvid),
        (player.get('cid'), cid), (player.get('page_no'), page)))
        or (isinstance(pages, list) and len(selected) != 1))
    target = {'bvid': bvid, 'cid': cid, 'page': page,
              'state': 'matched' if matched else 'mismatch' if mismatch else 'unknown'}
    fields = {key: field(player, key) for key in FLAGS}
    state = 'unknown'
    vals = [player.get(k) for k in FLAGS]
    if player.get('is_ugc_pay_preview') is True:
        state = 'paid_preview'
    elif all(type(v) is bool for v in vals):
        exclusive, can_play, preview = vals
        state = 'entitled' if exclusive and can_play else 'denied' if exclusive else 'free'
        if not exclusive and can_play:
            state = 'unknown'  # contradictory rather than silently free
    subtitle = {'state': 'unknown', 'count': None, 'need_login': field(player, 'need_login_subtitle')}
    if interfaces['player']['state'] == 'ok':
        if 'subtitle' not in player:
            subtitle['state'] = 'missing'
        elif player['subtitle'] is None:
            subtitle['state'] = 'null'
        elif not isinstance(player['subtitle'], dict):
            subtitle['state'] = 'invalid'
        else:
            sub = player['subtitle']
            if 'subtitles' not in sub:
                subtitle['state'] = 'missing'
            elif sub['subtitles'] is None:
                subtitle['state'] = 'null'
            elif isinstance(sub['subtitles'], list):
                subtitle.update(state='available' if sub['subtitles'] else 'empty', count=len(sub['subtitles']))
            else:
                subtitle['state'] = 'invalid'
    expected = selected[0].get('duration') if len(selected) == 1 else None
    expected = expected if positive(expected) else None
    report = {'schema_version': SCHEMA_VERSION, 'target': target, 'identity': identity,
              'entitlement': {'state': state, 'fields': fields}, 'subtitle': subtitle,
              'source_span': source_check(expected, data['playurl'], interfaces['playurl']),
              'media': media_check(expected, captures.get('ffprobe')), 'interfaces': interfaces,
              'reasons': []}
    for name, status in interfaces.items():
        if status['state'] not in ('ok', 'missing'):
            report['reasons'].append(f'{name}:interface_failed')
    for name in ('target', 'identity', 'entitlement'):
        if report[name]['state'] not in ('matched', 'authenticated', 'anonymous', 'free', 'entitled'):
            report['reasons'].append(f'{name}:{report[name]["state"]}')
    if expected is None:
        report['reasons'].append('media:missing_part_duration')
    if report['source_span']['state'] not in ('complete', 'unverified'):
        report['reasons'].append('source_span:' + report['source_span']['state'])
    if report['media']['state'] != 'complete':
        report['reasons'].append(f'media:{report["media"]["state"]}')
    return decisions(report)


def evaluate_report(report, bvid, cid, page=1, ffprobe=None):
    """Validate a saved diagnostic, recompute decisions and optional fresh media."""
    if not isinstance(report, dict) or (type(report.get('schema_version')) is not int or report.get('schema_version') != SCHEMA_VERSION):
        raise ValueError('unsupported or missing schema_version')
    required = {'target': ('bvid', 'cid', 'page', 'state'),
                'identity': ('state', 'mid', 'expected_mid'),
                'entitlement': ('state', 'fields'), 'subtitle': ('state', 'count', 'need_login'),
                'source_span': ('state', 'expected_duration_s', 'actual_duration_s', 'tolerance_s'),
                'media': ('state', 'expected_duration_s', 'actual_duration_s', 'tolerance_s', 'has_audio'),
                'interfaces': ('nav', 'view', 'player', 'playurl')}
    for name, keys in required.items():
        if not isinstance(report.get(name), dict) or any(k not in report[name] for k in keys):
            raise ValueError(f'incomplete {name}')
    if not isinstance(report.get('reasons'), list):
        raise ValueError('missing reasons')
    for name in ('nav', 'view', 'player', 'playurl'):
        if not isinstance(report['interfaces'][name], dict) or any(k not in report['interfaces'][name] for k in ('state', 'code')):
            raise ValueError('incomplete interface')
    fields = report['entitlement']['fields']
    if not isinstance(fields, dict) or any(k not in fields for k in FLAGS):
        raise ValueError('missing entitlement fields')
    # Reconstruct entitlement from field evidence, not a saved allow boolean.
    player = {}
    for key in FLAGS:
        entry = fields[key]
        if not isinstance(entry, dict) or 'state' not in entry or 'value' not in entry:
            raise ValueError('incomplete entitlement field')
        if entry['state'] == 'present':
            player[key] = entry['value']
    values = [player.get(k) for k in FLAGS]
    derived = ('paid_preview' if player.get(FLAGS[2]) is True else
               ('entitled' if values[0] and values[1] else 'denied' if values[0] else
                'unknown' if values[1] else 'free') if all(type(v) is bool for v in values) else 'unknown')
    if derived != report['entitlement']['state']:
        raise ValueError('entitlement state inconsistent with evidence')
    span = report['source_span']
    if span['expected_duration_s'] != report['media']['expected_duration_s']:
        raise ValueError('source/media duration mismatch')
    if span['state'] == 'complete':
        if not positive(span['actual_duration_s']) or not positive(span['expected_duration_s']):
            raise ValueError('incomplete source span')
        tolerance = 1.05 if float(span['expected_duration_s']).is_integer() else 0.05
        if span['tolerance_s'] != tolerance or abs(span['actual_duration_s'] - span['expected_duration_s']) > tolerance:
            raise ValueError('inconsistent source span')
    if span['state'] == 'unverified' and (span['actual_duration_s'] is not None or span['tolerance_s'] is not None):
        raise ValueError('inconsistent unverified source span')
    result = copy.deepcopy(report)
    if any(result['target'][key] != value for key, value in (('bvid', bvid), ('cid', cid), ('page', page))):
        result['target']['state'] = 'mismatch'
        result['reasons'].append('target:mismatch')
    identity = result['identity']
    if identity['state'] == 'authenticated' and (not identifier(identity['mid']) or
            (identity['expected_mid'] is not None and identity['mid'] != identity['expected_mid'])):
        identity['state'] = 'mismatch'
    if ffprobe is not None:
        result['media'] = media_check(result['media']['expected_duration_s'], ffprobe)
        result['reasons'] = [r for r in result['reasons'] if not str(r).startswith('media:')]
        if result['media']['state'] != 'complete':
            result['reasons'].append('media:' + result['media']['state'])
    else:
        # ASR always requires a fresh ffprobe of the actual ASR input.
        result = decisions(result)
        result['asr_allowed'] = False
        return result
    return decisions(result)


def probe(bvid, cid, page, cookie_file=None):
    handlers = [urllib.request.ProxyHandler({})]
    if cookie_file:
        jar = http.cookiejar.MozillaCookieJar(cookie_file)
        jar.load(ignore_discard=True, ignore_expires=False)
        handlers.append(urllib.request.HTTPCookieProcessor(jar))
    opener = urllib.request.build_opener(*handlers)
    paths = {'nav': 'x/web-interface/nav', 'view': 'x/web-interface/view',
             'player': 'x/player/wbi/v2', 'playurl': 'x/player/playurl'}
    captures = {}
    for name, path in paths.items():
        if name == 'player' and cid is None:
            view, _ = unwrap(captures.get('view'))
            pages = view.get('pages', [])
            selected = [p for p in pages if isinstance(p, dict) and p.get('page') == page] if isinstance(pages, list) else []
            cid = selected[0].get('cid') if len(selected) == 1 else None
            if not identifier(cid):
                break
        params = {} if name == 'nav' else {'bvid': bvid}
        if name in ('player', 'playurl'):
            params.update(cid=cid)
        if name == 'playurl':
            params.update(fnval=16, qn=64)
        url = 'https://api.bilibili.com/' + path + '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://www.bilibili.com'})
        status = 0
        try:
            with opener.open(request, timeout=20) as response:
                status = response.status
                captures[name] = {'http': status, 'body': json.load(response)}
        except urllib.error.HTTPError as exc:
            captures[name] = {'http': exc.code, 'body': {'code': None}, 'error': 'http_error'}
        except urllib.error.URLError as exc:
            category = 'timeout' if isinstance(exc.reason, TimeoutError) else 'network_error'
            captures[name] = {'http': status, 'body': {'code': None}, 'error': category}
        except TimeoutError:
            captures[name] = {'http': status, 'body': {'code': None}, 'error': 'timeout'}
        except (json.JSONDecodeError, UnicodeDecodeError):
            captures[name] = {'http': status, 'body': {'code': None}, 'error': 'invalid_json'}
        except Exception:
            # Do not expose cookies, signed URLs, or server bodies in errors.
            captures[name] = {'http': status, 'body': {'code': None}, 'error': 'unexpected_error'}
    return captures


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('replay', 'probe', 'verify-report'):
        p = subs.add_parser(name)
        p.add_argument('--bvid', required=True)
        p.add_argument('--cid', required=name != 'probe', type=int)
        p.add_argument('--page', type=int, default=1)
        if name == 'replay':
            for source in ('nav', 'view', 'player', 'playurl', 'ffprobe'):
                p.add_argument('--' + source)
            p.add_argument('--expected-mid', type=int)
        elif name == 'probe':
            p.add_argument('--cookie-file', help='explicit authorized Netscape cookie jar; never reads browser cookies')
            p.add_argument('--expected-mid', type=int)
        else:
            p.add_argument('report')
            p.add_argument('--ffprobe')
            p.add_argument('--require', choices=('download', 'asr'), required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r'BV[0-9A-Za-z]{10}', args.bvid) or (args.cid is not None and args.cid <= 0) or args.page <= 0:
            raise ValueError('invalid target')
        if args.command == 'verify-report':
            result = evaluate_report(load(args.report), args.bvid, args.cid, args.page,
                                     load(args.ffprobe) if args.ffprobe else None)
        else:
            captures = (probe(args.bvid, args.cid, args.page, args.cookie_file) if args.command == 'probe'
                        else {name: load(getattr(args, name)) for name in ('nav', 'view', 'player', 'playurl', 'ffprobe') if getattr(args, name)})
            cid = args.cid
            if args.command == 'probe' and cid is None:
                player, _ = unwrap(captures.get('player'))
                cid = player.get('cid')
            result = evaluate(captures, args.bvid, cid, args.page, args.expected_mid)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        if args.command == 'verify-report':
            return 0 if result[args.require + '_allowed'] else 1
        return 0 if result['download_allowed'] else 1
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({'schema_version': SCHEMA_VERSION, 'download_allowed': False,
                          'asr_allowed': False, 'error': type(error).__name__}), file=sys.stdout)
        return 2


if __name__ == '__main__':
    sys.exit(main())

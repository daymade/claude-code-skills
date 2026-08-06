#!/usr/bin/env python3
"""Tests for scripts/extract_user_messages.py — synthetic fixture homes only."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import extract_user_messages as ex  # noqa: E402
from _core.sources import discover_claude_sources  # noqa: E402

NOW = datetime.now(timezone.utc)
TS = (NOW - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
TS_LATER = (NOW - timedelta(minutes=59)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
TS_EARLIER = (NOW - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')


def user(uuid, content, ts=TS, **extra):
    rec = {
        'type': 'user', 'uuid': uuid, 'sessionId': 's1', 'timestamp': ts,
        'message': {'role': 'user', 'content': content},
    }
    rec.update(extra)
    return rec


def assistant(uuid, text, ts=TS_EARLIER):
    return {
        'type': 'assistant', 'uuid': uuid, 'sessionId': 's1', 'timestamp': ts,
        'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]},
    }


def queued(uuid, prompt, kind='human', ts=TS):
    att = {'type': 'queued_command', 'prompt': prompt, 'commandMode': 'prompt'}
    if kind is not None:
        att['origin'] = {'kind': kind}
    return {'type': 'attachment', 'uuid': uuid, 'sessionId': 's1', 'timestamp': ts, 'attachment': att}


def run_extract(home: Path, records: list) -> ex.Extraction:
    write_jsonl(home / 'projects' / '-tmp-proj' / 's1.jsonl', records)
    sources, _ = discover_claude_sources(explicit_homes=[str(home)])
    cutoff = NOW - timedelta(days=1)
    return ex.extract(sources, cutoff)


class ExtractUserMessagesTest(unittest.TestCase):
    def test_typed_message_is_kept(self):
        ext = run_extract(self.home, [user('u1', '今天把这个修一下')])
        self.assertEqual([e.text for e in ext.entries], ['今天把这个修一下'])

    def test_structural_noise_is_dropped(self):
        ext = run_extract(self.home, [
            user('u1', 'real words'),
            user('u2', '<task-notification> <task-id>x</task-id> </task-notification>', promptSource='system'),
            user('u3', 'sdk template text', promptSource='sdk'),
            user('u4', 'meta text', isMeta=True),
            user('u5', [{'type': 'tool_result', 'tool_use_id': 't', 'content': 'res'}]),
            user('u6', '[Request interrupted by user]'),
            user('u7', 'This session is being continued from a previous conversation that ran out of context. Summary: ...'),
        ])
        self.assertEqual([e.text for e in ext.entries], ['real words'])

    def test_command_envelopes_go_to_appendix_with_args(self):
        ext = run_extract(self.home, [
            user('u1', '<command-message>foo</command-message>\n<command-name>/transcript-fixer</command-name>\n<command-args>修一下这个词</command-args>'),
            user('u2', '/compact'),
            user('u3', '/opt/data/x.md 这个文件看下'),  # path text is NOT a command
        ])
        self.assertEqual([c.text for c in ext.commands], ['/transcript-fixer 修一下这个词', '/compact'])
        self.assertEqual([e.text for e in ext.entries], ['/opt/data/x.md 这个文件看下'])

    def test_queued_command_human_is_recovered(self):
        ext = run_extract(self.home, [
            user('u1', 'normal'),
            queued('q1', '打断一下，先别跑'),
        ])
        texts = [e.text for e in ext.entries]
        self.assertIn('打断一下，先别跑', texts)

    def test_queued_list_variant_and_peer_origin(self):
        ext = run_extract(self.home, [
            queued('q1', [{'type': 'text', 'text': '第一句'}, {'type': 'text', 'text': '第二句'}]),
            queued('q2', 'agent 投递', kind='peer'),
            queued('q3', 'harness 通知', kind=None),
        ])
        texts = [e.text for e in ext.entries]
        self.assertEqual(texts, ['第一句\n第二句'])

    def test_queued_dedupes_against_delivered_record(self):
        ext = run_extract(self.home, [
            queued('q1', '同一句话', ts=TS),
            user('u1', '同一句话', ts=TS_LATER),
        ])
        self.assertEqual(len(ext.entries), 1)

    def test_boilerplate_frequency_detection_and_tail_strip(self):
        boiler = '固定注入块 ' + '这是一个很长的注入提示词块。' * 40  # >400 normalized chars
        records = [user(f'b{i}', boiler) for i in range(5)]
        records.append(user('u1', '我自己的话。' + boiler))
        ext = run_extract(self.home, records)
        self.assertEqual(len(ext.injected), 5)
        self.assertEqual([e.text for e in ext.entries], ['我自己的话。'])

    def test_long_ascii_paste_goes_to_appendix(self):
        paste = 'x' * 2100
        ext = run_extract(self.home, [user('u1', paste), user('u2', '正常中文消息')])
        self.assertEqual([e.text for e in ext.entries], ['正常中文消息'])
        self.assertEqual(len(ext.pastes), 1)

    def test_agent_voiced_reinjection_is_subtracted_only_when_earlier(self):
        agent_text = '这是一段 agent 产出的分析结论，足够长，超过三十个字符的阈值限制。'
        ext = run_extract(self.home, [
            assistant('a1', agent_text, ts=TS_EARLIER),
            user('u1', agent_text, ts=TS),  # agent said it first -> dropped
        ])
        self.assertEqual(ext.subtracted, 1)
        self.assertEqual(len(ext.entries), 0)

        ext2 = run_extract(self.home2, [
            user('u1', agent_text, ts=TS_EARLIER),  # user said it first -> kept
            assistant('a1', agent_text, ts=TS),
        ])
        self.assertEqual(ext2.subtracted, 0)
        self.assertEqual(len(ext2.entries), 1)

    def test_filler_flag(self):
        ext = run_extract(self.home, [user('u1', '继续'), user('u2', '把这个方案展开讲讲')])
        by_text = {e.text: e for e in ext.entries}
        self.assertTrue(by_text['继续'].filler)
        self.assertFalse(by_text['把这个方案展开讲讲'].filler)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp2 = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.home2 = Path(self._tmp2.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._tmp2.cleanup()


if __name__ == '__main__':
    unittest.main()

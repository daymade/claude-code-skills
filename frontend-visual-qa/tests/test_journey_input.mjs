import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
import { runJsonlJourney } from '../scripts/journey_input.mjs';

test('preserves long UTF-8 JSON and blank lines through chunked non-TTY input', async () => {
  const command = { eval: '正文与焦点'.repeat(6000), arg: { text: 'a\nb', value: 0 } };
  const bytes = Buffer.from('\n' + JSON.stringify(command) + '\r\n' + JSON.stringify({ method: 'Page.captureScreenshot' }) + '\n');
  const chunks = [];
  for (let i = 0; i < bytes.length; i += 19) chunks.push(bytes.subarray(i, i + 19));
  const seen = [], records = [];
  const result = await runJsonlJourney(Readable.from(chunks), async value => { seen.push(value); return 'observed'; }, async value => records.push(value));
  assert.deepEqual(seen[0], command);
  assert.deepEqual(result, { steps: 2, lines: 3 });
  assert.deepEqual(records.map(r => [r.step, r.line]), [[1, 2], [2, 3]]);
});

test('malformed or non-object input stops before any later action', async () => {
  for (const invalid of ['{"broken":', 'null', '[]', '"text"']) {
    const seen = [];
    await assert.rejects(runJsonlJourney(Readable.from([invalid + '\n{"later":true}\n']), async value => seen.push(value)));
    assert.deepEqual(seen, []);
  }
});

test('an executor failure stops downstream dispatch while retaining earlier evidence', async () => {
  const seen = [], records = [];
  await assert.rejects(runJsonlJourney(Readable.from(['{"step":1}\n{"step":2}\n{"step":3}\n']), async value => {
    seen.push(value.step);
    if (value.step === 2) throw new Error('required observation failed');
    return { confirmed: true };
  }, async value => records.push(value)), /required observation failed/);
  assert.deepEqual(seen, [1, 2]);
  assert.equal(records.length, 1);
});

test('recording failure also stops downstream dispatch', async () => {
  const seen = [];
  await assert.rejects(runJsonlJourney(Readable.from(['{"step":1}\n{"step":2}\n']), async value => seen.push(value.step), async () => { throw new Error('evidence unavailable'); }), /evidence unavailable/);
  assert.deepEqual(seen, [1]);
});

test('TTY input is refused before reading or dispatching; empty pipe is explicit', async () => {
  await assert.rejects(runJsonlJourney({ isTTY: true }, () => assert.fail('dispatched')), /non-TTY/);
  assert.deepEqual(await runJsonlJourney(Readable.from([]), async () => assert.fail('dispatched')), { steps: 0, lines: 0 });
});

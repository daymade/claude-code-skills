import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import test from 'node:test';

test('same long input needs readable content, exact source and ordinary return', async () => {
  const require = createRequire(join(process.cwd(), 'package.json'));
  let chromium;
  for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
    try { chromium = require(name).chromium; if (chromium) break; } catch { /* existing project dependency */ }
  }
  assert.ok(chromium, 'Run from an existing Playwright project; a missing browser is not a pass.');
  const supplied = process.env.NESTED_SOURCE_EVIDENCE_DIR;
  const evidence = supplied || await mkdtemp(join(tmpdir(), 'nested-source-'));
  await mkdir(evidence, { recursive: true });
  const html = await readFile(new URL('../evals/files/nested-source-return-fixture.html', import.meta.url));
  const server = createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  const measurements = { viewport: { width: 800, height: 440 }, cases: [], examined: 0 };
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: measurements.viewport });
    const url = `http://127.0.0.1:${server.address().port}/`;
    const geometry = () => page.evaluate(() => {
      const box = document.querySelector('#reader');
      const style = getComputedStyle(box);
      return { client: box.clientHeight, padding: parseFloat(style.paddingTop) + parseFloat(style.paddingBottom),
        scroll: box.scrollTop, scrollHeight: box.scrollHeight };
    });
    const fullyReadable = selector => page.locator(selector).evaluate(element => {
      const reader = document.querySelector('#reader');
      const bounds = reader.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(reader);
      const top = bounds.top + parseFloat(style.paddingTop);
      const bottom = bounds.bottom - parseFloat(style.paddingBottom);
      return rect.top >= top - 0.5 && rect.bottom <= bottom + 0.5 && rect.bottom <= innerHeight;
    });
    async function settledScroll() {
      let previous = null;
      for (let attempt = 0; attempt < 60; attempt++) {
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const now = (await geometry()).scroll;
        if (previous !== null && Math.abs(now - previous) < 0.25) return now;
        previous = now;
      }
      assert.fail('Actual reader scrolling did not settle.');
    }
    async function ordinaryJourney(layout) {
      await page.goto(`${url}?layout=${layout}&input=long`);
      assert.equal(await fullyReadable('#target-source'), false, 'Source must begin below the fold.');
      const readerBox = await page.locator('#reader').boundingBox();
      await page.mouse.move(readerBox.x + readerBox.width / 2, readerBox.y + readerBox.height / 2);
      for (let attempt = 0; attempt < 10; attempt++) {
        if (await fullyReadable('#target-source') && await fullyReadable('#target-body')) break;
        await page.mouse.wheel(0, 65);
        await settledScroll();
      }
      assert.ok(await fullyReadable('#target-source') && await fullyReadable('#target-body'),
        'Ordinary scrolling must reveal the source button and a complete body line.');
      const before = await geometry();
      assert.ok(before.scroll > 0);
      await page.screenshot({ path: join(evidence, 'long-repaired-readable.png') });
      await page.locator('#target-source').click();
      assert.equal(await page.locator('#original').getAttribute('data-child'), 'child-cedar');
      assert.equal(await page.locator('#original').getAttribute('data-record'), 'record-29');
      await assert.doesNotReject(() => page.locator('#original-body').waitFor({ state: 'visible' }));
      assert.match(await page.locator('#original-body').innerText(), /Second record body: the amber draft/);
      assert.ok(await page.locator('#original-body').evaluate(element => {
        const rect = element.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= innerHeight && rect.left >= 0 && rect.right <= innerWidth;
      }), 'The bound original body must be readable in the normal viewport.');
      await page.screenshot({ path: join(evidence, 'exact-original.png') });
      await page.locator('#return').click();
      const after = await settledScroll();
      const state = await page.locator('#context').evaluate(element => ({ ...element.dataset }));
      assert.deepEqual(state, { parent: 'parent-copper', group: 'group-amber', page: '3', selected: 'child-cedar/record-29' });
      assert.ok(Math.abs(after - before.scroll) <= 1, 'Return must preserve the real scroll owner.');
      assert.ok(await fullyReadable('#target-source') && await fullyReadable('#target-body'));
      await page.screenshot({ path: join(evidence, 'long-repaired-return.png') });
      return { before, after, state };
    }

    await page.goto(`${url}?layout=faulty&input=long`);
    const bad = await geometry();
    assert.equal(bad.client, bad.padding, 'Long faulty input collapses the content area to padding.');
    assert.equal(await fullyReadable('#target-body'), false);
    await page.screenshot({ path: join(evidence, 'long-faulty.png') });
    measurements.cases.push({ name: 'long-faulty', geometry: bad, readable: false });
    measurements.examined++;
    const good = await ordinaryJourney('repaired');
    measurements.cases.push({ name: 'long-repaired', ...good });
    measurements.examined++;
    await page.goto(`${url}?layout=faulty&input=short`);
    const short = await geometry();
    assert.ok(short.client - short.padding >= 24);
    assert.ok(await fullyReadable('#reader > p:first-child'));
    measurements.cases.push({ name: 'short-faulty-healthy-control', geometry: short });
    measurements.examined++;
    // Remove the layout repair without changing the long input or journey assertion.
    await assert.rejects(ordinaryJourney('faulty'), /Ordinary scrolling must reveal/);
    measurements.mutation = 'repaired-to-faulty rejected by the same ordinary journey';
    assert.equal(measurements.examined, 3);
    await writeFile(join(evidence, 'measurements.json'), `${JSON.stringify(measurements, null, 2)}\n`);
  } finally {
    await browser?.close();
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    if (!supplied) await rm(evidence, { recursive: true, force: true });
  }
});

test('requirement meaning, source binding and runtime recovery have distinct controls', async () => {
  const require = createRequire(join(process.cwd(), 'package.json'));
  let chromium;
  for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
    try { chromium = require(name).chromium; if (chromium) break; } catch { /* existing project dependency */ }
  }
  assert.ok(chromium, 'Run from an existing Playwright project; a missing browser is not a pass.');
  const supplied = process.env.NESTED_SOURCE_EVIDENCE_DIR;
  const evidence = supplied || await mkdtemp(join(tmpdir(), 'semantic-source-'));
  await mkdir(evidence, { recursive: true });
  const html = await readFile(new URL('../evals/files/nested-source-return-fixture.html', import.meta.url));
  const server = createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const result = { scope: 'synthetic calibration, not application acceptance', judgments: [] };
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1150, height: 800 } });
    const url = `http://127.0.0.1:${server.address().port}/?journey=semantic`;
    async function start(fault) {
      const response = await page.goto(`${url}&fault=${fault}`);
      assert.equal(response.status(), 200, 'Every failing control intentionally loads successfully.');
      // The long requirement must not hide the current reply or original-reading action.
      assert.ok(await page.locator('#latest-reply').evaluate(element => {
        const rect = element.getBoundingClientRect(); return rect.top >= 0 && rect.bottom <= innerHeight;
      }));
      const list = await page.locator('#work-list').boundingBox();
      await page.mouse.move(list.x + list.width / 2, list.y + list.height / 2);
      await page.mouse.wheel(0, 210);
      await page.waitForFunction(() => document.querySelector('#work-list').scrollTop > 0);
      return page.locator('#workbench').evaluate(element => ({ ...element.dataset,
        scroll: document.querySelector('#work-list').scrollTop }));
    }
    async function openRequirement() {
      await page.getByRole('button', { name: 'Read full requirement', exact: true }).click();
      const identity = await page.locator('#semantic-original-view').evaluate(element => ({ ...element.dataset }));
      assert.equal(identity.workspace, 'workspace-cedar', 'Original must belong to the selected source.');
      assert.equal(identity.runtime, 'run-copper');
      assert.equal(identity.record, 'record-b', 'Requirement must not open Goal A or latest reply C.');
      assert.match(await page.locator('#semantic-original-body').innerText(), /^Review the illustration captions before publishing\./);
      const reader = await page.locator('#semantic-original').boundingBox();
      await page.mouse.move(reader.x + reader.width / 2, reader.y + reader.height / 2);
      await page.mouse.wheel(0, 4000);
      await page.waitForFunction(() => {
        const element = document.querySelector('#semantic-original');
        return element.scrollTop + element.clientHeight >= element.scrollHeight - 1;
      });
      assert.match(await page.locator('#semantic-original-body').innerText(), /retain the turquoise envelope in illustration seven\.$/);
      assert.ok(await page.locator('#semantic-original-body').evaluate(element => {
        const range = document.createRange(); range.selectNodeContents(element);
        const last = [...range.getClientRects()].at(-1);
        const bounds = document.querySelector('#semantic-original').getBoundingClientRect();
        return last.top >= bounds.top && last.bottom <= bounds.bottom && last.bottom <= innerHeight;
      }), 'The final requirement line must actually be readable, not merely in the DOM.');
    }
    async function ordinary(fault) {
      const before = await start(fault);
      await openRequirement();
      await page.screenshot({ path: join(evidence, `semantic-${fault}-original.png`) });
      await page.getByRole('button', { name: 'Return to workbench', exact: true }).click();
      const after = await page.locator('#workbench').evaluate(element => ({ ...element.dataset,
        scroll: document.querySelector('#work-list').scrollTop }));
      assert.deepEqual(after, before, 'Return must preserve source, runtime, page, selection and actual scroll.');
      await page.screenshot({ path: join(evidence, `semantic-${fault}-return.png`) });
      return { before, after };
    }
    result.judgments.push({ name: 'healthy-meaning-source-return', accepted: true, ...await ordinary('none') });
    for (const [fault, reason] of [['goal-as-request', /Requirement must not open/], ['reply-as-request', /Requirement must not open/],
      ['wrong-source', /Original must belong/], ['false-return', /Return must preserve/]]) {
      await assert.rejects(ordinary(fault), reason);
      await page.screenshot({ path: join(evidence, `semantic-${fault}-rejected.png`) });
      result.judgments.push({ name: fault, accepted: false });
    }
    async function runtime(fault) {
      await start(fault); await openRequirement();
      await page.getByRole('button', { name: 'Simulate runtime replacement', exact: true }).click();
      await page.getByRole('button', { name: 'Return to workbench', exact: true }).click();
      assert.match(await page.locator('#runtime-status').innerText(), /Previous workspace instance is unavailable/,
        'A replaced instance must not be reported as a recovered old selection.');
      assert.equal(await page.locator('#workbench').getAttribute('data-selected'), '');
      assert.equal(await page.locator('#read-requirement').isDisabled(), true);
      await page.screenshot({ path: join(evidence, `runtime-${fault}-refusal.png`) });
      await page.getByRole('button', { name: 'Choose current native workspace', exact: true }).click();
      assert.equal(await page.locator('#workbench').getAttribute('data-runtime'), 'run-amber');
      assert.equal(await page.locator('#workbench').getAttribute('data-selected'), 'record-b');
      await page.getByRole('button', { name: 'Read full requirement', exact: true }).click();
      assert.equal(await page.locator('#semantic-original-view').getAttribute('data-runtime'), 'run-amber');
      assert.equal(await page.locator('#semantic-original-view').getAttribute('data-record'), 'record-b');
      assert.match(await page.locator('#semantic-original-body').innerText(), /turquoise envelope/);
      await page.screenshot({ path: join(evidence, `runtime-${fault}-current.png`) });
    }
    await runtime('none'); result.judgments.push({ name: 'runtime-refusal-and-explicit-current-recovery', accepted: true });
    await assert.rejects(runtime('stale-return'), /recovered old selection/);
    result.judgments.push({ name: 'stale-runtime-return', accepted: false });
    assert.equal(result.judgments.length, 7);
    await writeFile(join(evidence, 'semantic-measurements.json'), `${JSON.stringify(result, null, 2)}\n`);
  } finally {
    await browser?.close();
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    if (!supplied) await rm(evidence, { recursive: true, force: true });
  }
});

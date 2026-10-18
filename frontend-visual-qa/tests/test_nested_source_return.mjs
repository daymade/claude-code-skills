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

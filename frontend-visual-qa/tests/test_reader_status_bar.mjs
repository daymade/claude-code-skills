import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import test from 'node:test';

// Fixture-specific known-answer controls, not a generic Reader/semantic detector.
test('retained Reader must also expose its last prose and footnote under a status bar', async () => {
  const require = createRequire(join(process.cwd(), 'package.json'));
  let chromium;
  for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
    try { chromium = require(name).chromium; if (chromium) break; } catch { /* existing harness */ }
  }
  assert.ok(chromium, 'Run from an existing Playwright project; missing browser coverage is not a pass.');
  const evidence = process.env.READER_STATUS_EVIDENCE_DIR || await mkdtemp(join(tmpdir(), 'reader-status-'));
  await mkdir(evidence, { recursive: true });
  const html = await readFile(new URL('../evals/files/reader-status-bar-fixture.html', import.meta.url));
  const server = createServer((_req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const measurements = { cases: [], examined: 0 };
  let browser;
  try {
    browser = await chromium.launch({ headless: true, args: ['--disable-features=MacAppCodeSignClone'] });
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1100, height: 700 }]) {
      const page = await browser.newPage({ viewport });
      const url = `http://127.0.0.1:${server.address().port}/`;
      for (const layout of ['overflowing', 'bounded']) {
        await page.goto(`${url}?layout=${layout}`);
        const frame = page.frameLocator('#reader');
        await frame.locator('#last-note').waitFor();
        const nativeFrame = page.frames().find(value => value.parentFrame());
        const originalDocument = await nativeFrame.evaluateHandle(() => document);
        await frame.locator('#find').fill('needle');
        await frame.locator('#next').click();
        assert.equal(await frame.locator('#matches').innerText(), '1/33');
        const initialBox = await page.locator('#reader').boundingBox();
        await page.mouse.move(initialBox.x + initialBox.width / 2, initialBox.y + 150);
        await page.mouse.wheel(0, 320);
        await page.waitForFunction(() => document.querySelector('#reader').contentDocument.querySelector('#body').scrollTop >= 300);
        const state = () => nativeFrame.evaluate(() => ({ query: document.querySelector('#find').value,
          range: { ...document.querySelector('#body').dataset }, scroll: document.querySelector('#body').scrollTop }));
        const before = await state();
        assert.ok(before.scroll > 0);
        await page.locator('#fail').click();
        assert.equal(await nativeFrame.evaluate(saved => document === saved, originalDocument), true);
        assert.deepEqual(await state(), before, 'Showing failure must retain actual document, Find, range and scroll.');
        await page.locator('#retry').click();
        assert.deepEqual(await state(), before, 'Recovery must retain the same reading state.');
        assert.equal(await nativeFrame.evaluate(saved => document === saved, originalDocument), true);
        await page.locator('#fail').click();

        // Ordinary wheel input at the actual body, rather than scrollIntoView on the tail.
        const box = await page.locator('#reader').boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + 150);
        await page.mouse.wheel(0, 100000);
        await page.waitForFunction(() => {
          const body = document.querySelector('#reader').contentDocument.querySelector('#body');
          return Math.abs(body.scrollHeight - body.clientHeight - body.scrollTop) <= 1;
        });
        const observed = await page.evaluate(() => {
          const frame = document.querySelector('#reader');
          const clip = document.querySelector('#clip').getBoundingClientRect();
          const bounds = frame.getBoundingClientRect();
          const doc = frame.contentDocument;
          const scroll = doc.querySelector('#body');
          const scrollBounds = scroll.getBoundingClientRect();
          const items = ['last-prose', 'last-note'].map(id => {
            const rect = doc.getElementById(id).getBoundingClientRect();
            const bottom = bounds.top + rect.bottom;
            return { id, top: bounds.top + rect.top, bottom,
              readable: rect.top >= scrollBounds.top && rect.bottom <= scrollBounds.bottom &&
                bottom <= clip.bottom && bottom <= innerHeight };
          });
          return { clipBottom: clip.bottom, frameBottom: bounds.bottom, frameHeight: bounds.height,
            scroll: scroll.scrollTop, maxScroll: scroll.scrollHeight - scroll.clientHeight, items,
            records: doc.querySelectorAll('article').length };
        });
        assert.equal(observed.records, 34, 'Nonvacuous complete loaded window.');
        assert.equal(observed.items.length, 2);
        const accept = result => assert.ok(result.items.every(item => item.readable),
          'Last record prose and footnote must be readable through the real parent clip.');
        if (layout === 'overflowing') {
          assert.ok(observed.frameBottom - observed.clipBottom >= 51);
          assert.equal(observed.items.find(item => item.id === 'last-note').readable, false);
          assert.throws(() => accept(observed), /Last record prose and footnote/);
        } else {
          assert.ok(observed.frameBottom <= observed.clipBottom + 0.5);
          accept(observed);
        }
        await page.screenshot({ path: join(evidence, `${viewport.width}-${layout}-tail.png`) });
        // Healthy source text is not product-authored missing-field narration.
        assert.equal(await frame.locator('#last-note').innerText(), 'Original author wrote: “No responsibility declared.”');
        assert.equal(await page.getByRole('heading', { name: 'Responsibility', exact: true }).count(), 0);
        assert.match(await page.locator('h1').innerText(), /Execution unknown/);
        await page.locator('#recover').click();
        assert.equal(await nativeFrame.evaluate(saved => document === saved, originalDocument), true);
        assert.equal((await state()).query, before.query);
        assert.deepEqual((await state()).range, before.range);
        await frame.locator('#next').click();
        assert.equal(await frame.locator('#matches').innerText(), '2/33', 'Find remains usable after recovery.');
        measurements.cases.push({ viewport, layout, before, observed });
        measurements.examined++;
        await originalDocument.dispose();
      }
      await page.close();
    }
    assert.equal(measurements.examined, 4);
    measurements.mutation = 'Removing bounded sizing selects overflowing; the identical tail acceptance rejects it.';
    await writeFile(join(evidence, 'measurements.json'), `${JSON.stringify(measurements, null, 2)}\n`);
    console.log(`Reader status evidence: ${evidence}`);
  } finally {
    await browser?.close();
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

// Only the declared synthetic fixture's task answers; not a generic semantic validator.
const target = {
  record: 'cedar-7', report: 'report-cedar-7',
  body: 'Cedar original 7: shipment is 46 units; the prior plan is 50 units.',
  draftA: 'Compare cedar shipments', draftB: 'Check amber inspection'
};

test('visible task answers and context, with calibrated faulty and healthy journeys', async t => {
  const require = createRequire(join(process.cwd(), 'package.json'));
  let chromium;
  for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
    try { chromium = require(name).chromium; if (chromium) break; } catch { /* existing project dependency */ }
  }
  assert.ok(chromium, 'Run from an existing Playwright project; a missing renderer is not a pass.');
  const supplied = process.env.COLLECTION_CONTEXT_EVIDENCE_DIR;
  const evidence = supplied || await mkdtemp(join(tmpdir(), 'collection-context-'));
  await mkdir(evidence, { recursive: true });
  const html = await readFile(new URL('../evals/files/collection-context-fixture.html', import.meta.url));
  const server = createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  const observations = { scope: 'Synthetic calibration only, not application acceptance', cases: [] };
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(3000);
    const base = `http://127.0.0.1:${server.address().port}/`;
    async function visit(fault = '') {
      await page.goto(`${base}${fault ? `?fault=${fault}` : ''}`);
      await page.locator('#filter').selectOption('tracked');
      await page.locator('#summary-phase').filter({ hasText: 'Summary requests settled' }).waitFor();
    }
    async function summariesReadable() {
      const rows = page.locator('#collection:visible #rows li');
      assert.equal(await rows.count(), 10, 'The contracted collection must contain all ten tracked records.');
      const summaries = await rows.locator('.summary').allInnerTexts();
      assert.deepEqual(summaries, Array.from({ length: 10 }, (_, i) =>
        `Cedar record ${i + 1}: compare the current shipment with the prior plan.`),
      'Rows and settled requests do not prove the promised summaries are readable.');
    }
    async function enterTarget() {
      const list = page.locator('#list');
      const box = await list.boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.wheel(0, 620);
      const open = page.getByRole('button', { name: `Read ${target.record}: Quarterly review`, exact: true });
      await open.scrollIntoViewIfNeeded();
      const before = await list.evaluate(element => element.scrollTop);
      assert.ok(before > 0, 'The return control needs a genuinely displaced list.');
      await open.click();
      return before;
    }
    async function correctOriginal() {
      assert.equal(await page.locator('#reader:visible #report-key').innerText(), `Original: ${target.report}`,
        'The visible reader must identify the requested original, despite repeated titles.');
      assert.equal(await page.locator('#reader:visible #report-body').innerText(), target.body,
        'The reader must expose the exact original body.');
      assert.equal(new URL(page.url()).searchParams.get('report'), target.report);
      assert.ok(await page.locator('#report-body').evaluate(element => {
        const rect = element.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= innerHeight && rect.left >= 0 && rect.right <= innerWidth;
      }), 'The original body must fit the ordinary reading viewport.');
    }
    async function returnedContext(before) {
      assert.equal(await page.locator('#filter').inputValue(), 'tracked', 'Return must preserve the contracted filter.');
      assert.equal(await page.locator('#selection').innerText(), `Selected: ${target.record}`);
      assert.equal(await page.locator('#rows li[aria-current=true]').count(), 1);
      assert.ok(Math.abs(await page.locator('#list').evaluate(element => element.scrollTop) - before) <= 1,
        'Return must preserve the actual list scroll owner.');
      assert.equal(await page.locator(':focus').innerText(), `Read ${target.record}: Quarterly review`);
      assert.equal(new URL(page.url()).searchParams.has('report'), false);
    }

    await t.test('collection ready, exact original and ordinary return are separate endpoints', async () => {
      await visit('summaries');
      assert.equal(await page.locator('#rows li').count(), 10); // Deliberately insufficient shell-only check.
      await assert.rejects(summariesReadable(), /promised summaries are readable/);
      await page.screenshot({ path: join(evidence, 'summary-failure-despite-rows.png') });
      observations.cases.push({ fault: 'summaries', rows: 10, verdict: 'summary assertion rejects' });
      await visit('identity');
      await summariesReadable();
      await enterTarget();
      await assert.rejects(correctOriginal(), /requested original/);
      observations.cases.push({ fault: 'identity', verdict: 'exact original assertion rejects' });
      await visit('return');
      await summariesReadable();
      const lost = await enterTarget();
      await correctOriginal();
      await page.locator('#return').click();
      await assert.rejects(returnedContext(lost), /contracted filter/);
      observations.cases.push({ fault: 'return', verdict: 'return context assertion rejects' });
      await visit();
      await summariesReadable();
      const before = await enterTarget();
      await correctOriginal();
      await page.screenshot({ path: join(evidence, 'exact-original-readable.png') });
      await page.locator('#return').click();
      await returnedContext(before);
      await page.screenshot({ path: join(evidence, 'collection-context-returned.png') });
      observations.cases.push({ fault: null, verdict: 'ten summaries, exact body and return pass', scroll: before });
    });

    async function openEditor() { await page.locator('#edit').click(); }
    async function closePreservesDraft() {
      await openEditor();
      await page.locator('#draft').fill(target.draftA);
      await page.locator('#close').click();
      await openEditor();
      assert.equal(await page.locator('#draft').inputValue(), target.draftA, 'Close must keep this scope draft.');
    }
    async function scopeIsolatesDrafts() {
      await page.locator('#close').click();
      await page.locator('#scope-amber').click();
      await openEditor();
      assert.equal(await page.locator('#draft').inputValue(), '', 'A new scope must not inherit another scope draft.');
      await page.locator('#draft').fill(target.draftB);
      await page.locator('#close').click();
      await page.locator('#scope-cedar').click();
      await openEditor();
      assert.equal(await page.locator('#draft').inputValue(), target.draftA, 'Returning to Cedar must recover its own draft.');
    }
    async function explicitDiscard() {
      await page.locator('#discard').click();
      await openEditor();
      assert.equal(await page.locator('#draft').inputValue(), '', 'Explicit discard must clear the current scope draft.');
    }
    await t.test('close, scope changes and explicit discard have declared distinct boundaries', async () => {
      await visit('close-draft');
      await assert.rejects(closePreservesDraft(), /Close must keep/);
      observations.cases.push({ fault: 'close-draft', verdict: 'close preservation assertion rejects' });
      await visit('scope-draft');
      await closePreservesDraft();
      await assert.rejects(scopeIsolatesDrafts(), /must not inherit/);
      observations.cases.push({ fault: 'scope-draft', verdict: 'scope isolation assertion rejects' });
      await visit('discard');
      await closePreservesDraft();
      await assert.rejects(explicitDiscard(), /Explicit discard must clear/);
      observations.cases.push({ fault: 'discard', verdict: 'explicit discard assertion rejects' });
      await visit();
      await closePreservesDraft();
      await scopeIsolatesDrafts();
      await explicitDiscard();
      await page.locator('#close').click();
      await page.locator('#scope-amber').click();
      await openEditor();
      assert.equal(await page.locator('#draft').inputValue(), target.draftB, 'Discard must not erase another scope draft.');
      observations.cases.push({ fault: null, verdict: 'close keeps, scopes isolate, discard clears only current' });
    });

    async function escapeReturns() {
      const before = await enterTarget();
      await correctOriginal();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#reader').isVisible(), false, 'Actual Escape must close the active reader.');
      await returnedContext(before);
    }
    await t.test('hidden retained DOM is neither visible content nor an active modal', async () => {
      for (const fault of ['hidden-escape', '']) {
        await visit(fault);
        assert.equal(await page.locator('[role=dialog]').count(), 2, 'Both hidden dialog nodes must exist in this control.');
        assert.equal(await page.getByRole('dialog').count(), 0, 'No dialog is currently visible or exposed.');
        assert.match(await page.locator('body').textContent(), /Cached report sentinel/);
        assert.doesNotMatch(await page.locator('body').innerText(), /Cached report sentinel/,
          'A hidden retained report must not contaminate current visible content assertions.');
        if (fault) await assert.rejects(escapeReturns(), /Actual Escape must close/);
        else {
          await escapeReturns();
          await openEditor();
          await page.locator('#draft').fill(target.draftA);
          await page.keyboard.press('Escape');
          assert.equal(await page.getByRole('dialog').count(), 0);
          await openEditor();
          assert.equal(await page.locator('#draft').inputValue(), target.draftA, 'Editor Escape follows close, not discard.');
          await page.screenshot({ path: join(evidence, 'active-editor-with-hidden-cache.png') });
        }
        observations.cases.push({ fault: fault || null, verdict: fault ? 'Escape assertion rejects' : 'real Escape and visible-content assertions pass' });
      }
    });
    assert.equal(observations.cases.length, 10, 'All seven faulty controls and three healthy journeys must be examined.');
    await writeFile(join(evidence, 'observations.json'), `${JSON.stringify(observations, null, 2)}\n`);
  } finally {
    await browser?.close();
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    if (!supplied) await rm(evidence, { recursive: true, force: true });
  }
});

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import test from 'node:test';
import { collectPaintedText } from '../scripts/painted_text_probe.mjs';

test('Chromium catches partial glyphs without condemning clamp, ellipsis or scroll', async () => {
  const require = createRequire(join(process.cwd(), 'package.json'));
  let chromium;
  for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
    try { chromium = require(name).chromium; if (chromium) break; } catch { /* existing dependency */ }
  }
  assert.ok(chromium, 'Run from an existing Playwright project; missing renderer is not a pass.');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    // Synthetic replay of measured fixed-card + inverse-scale clipping, not a live app verdict.
    await page.setContent(`<style>body{font:14px Arial;margin:20px}
      .card{display:flex;flex-direction:column;width:276px;height:140px;overflow:hidden;transform:scale(.116284);transform-origin:top left}
      strong{display:block;font-size:120.398px;line-height:150.499px;overflow:hidden;width:205px;height:69.22px;flex-shrink:1}
      </style><div class="card"><strong id="half">Agent example</strong></div>`);
    const bad = await page.evaluate(collectPaintedText);
    assert.equal(bad.examined, 1);
    assert.ok(bad.issues.some(x => x.selector === '#half' && x.type === 'partially-painted-text-line'));
    await page.evaluate(() => { document.querySelector('strong').style.height = '150.499px'; document.querySelector('.card').style.height = '180px'; });
    assert.equal((await page.evaluate(collectPaintedText)).issues.length, 0);
    await page.setContent(`<style>body{font:14px/18px Arial}p{margin:20px;width:120px}
      #clamp{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
      #ellipsis{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #scroll{height:27px;overflow:auto}#hidden{display:none}#presence{height:8px;width:8px}
      #sr{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden}
      </style><p id="clamp">Whole lines then intentional omitted detail on another line.</p>
      <p id="ellipsis">Deliberately abbreviated horizontal label.</p>
      <div id="scroll"><p>Scroll window with several normal lines.</p></div>
      <p id="hidden">Hidden detail</p><button id="presence" title="Full name" aria-label="Full name"></button>
      <p id="sr">Accessible text</p>`);
    const good = await page.evaluate(collectPaintedText);
    assert.equal(good.issues.length, 0); assert.equal(good.status, 'partial');
    assert.ok(good.omissions.some(x => x.reason.includes('scroll')));
    assert.ok(good.omissions.some(x => x.reason.includes('clip-path')));
    await page.setContent('<p>Visible healthy control</p>');
    const healthy = await page.evaluate(collectPaintedText);
    assert.equal(healthy.status, 'mechanical-pass'); assert.equal(healthy.examined, 1);
    assert.equal((await page.evaluate(collectPaintedText, { limit: 0 })).status, 'unobserved');
    await page.setContent('<div></div>');
    assert.equal((await page.evaluate(collectPaintedText)).status, 'unobserved');
    await page.setContent('<div style="height:8px;overflow:hidden"><p style="margin:0;font:14px/18px Arial">Ancestor clipped label</p></div>');
    assert.equal((await page.evaluate(collectPaintedText)).issues.length, 1);
  } finally { await browser.close(); }
});

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join } from "node:path";
import test from "node:test";
import { collectAttentionInventory, inspectNecessityCoverage } from "../scripts/attention_inventory.mjs";

const inventory = { truncated: false, opaqueSurfaces: [], items: [{ id: "a" }, { id: "b" }] };
const decisions = ["a", "b"].map((id) => ({ id, disposition: "retain", taskLossWithoutIt: "A claimed task loss, not independently established." }));

test("coverage never certifies necessity, even when every item is retained", () => {
  assert.deepEqual(inspectNecessityCoverage(inventory, decisions), { complete: true, missingIds: [], necessityVerdict: "not_evaluated" });
  assert.equal(inspectNecessityCoverage(inventory, decisions.slice(0, 1)).complete, false);
  assert.equal(inspectNecessityCoverage(inventory, [decisions[0], decisions[0]]).reason, "unknown_or_duplicate_id");
  assert.equal(inspectNecessityCoverage(inventory, [{ ...decisions[0], disposition: "not_supported" }]).reason, "decision_incomplete");
  assert.equal(inspectNecessityCoverage({ ...inventory, truncated: true }, decisions).complete, false);
  assert.equal(inspectNecessityCoverage({ ...inventory, opaqueSurfaces: ["iframe"] }, decisions).complete, false);
});

test("real renderer inventories unmentioned repetition without treating essential context as a defect", async (t) => {
  const require = createRequire(join(process.cwd(), "package.json"));
  let chromium;
  for (const name of ["playwright", "@playwright/test", "playwright-core"]) {
    try { chromium = require(name).chromium; if (chromium) break; } catch { /* try the next installed layout */ }
  }
  if (!chromium) return t.skip("Run from the audited project that supplies Playwright; browser behavior is unverified here.");
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
    await page.setContent(`<style>body{font:16px sans-serif}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.hidden{display:none}.scroll{height:36px;overflow:auto}.row{height:36px}</style>
      <h1 class="sr">Accessible page name</h1><nav><button><span>System diagnostics</span><small>diagnostics</small></button></nav>
      <main><svg width="400" height="60"><text x="10" y="30">26·02</text></svg><div class="axis">26·02</div>
      <p>Amount <strong>USD</strong></p><label>Transfer amount<input value="INPUT_VALUE_NOT_FOR_EXPORT"></label>
      <p role="alert">This action cannot be reversed.</p><div class="hidden">Hidden variant</div>
      <div class="scroll"><div class="row">Visible source</div><div class="row">Offscreen source</div></div></main>`);
    const result = await page.evaluate(collectAttentionInventory);
    assert.equal(result.truncated, false);
    assert.equal(result.necessityVerdict, "not_evaluated");
    const texts = result.items.map((item) => item.text);
    for (const value of ["Accessible page name", "Hidden variant", "Offscreen source", "INPUT_VALUE_NOT_FOR_EXPORT"]) assert.ok(!texts.includes(value), value);
    for (const value of ["USD", "Transfer amount", "This action cannot be reversed."]) assert.ok(texts.includes(value), value);
    assert.ok(result.repeats.some((ids) => ids.length === 2 && ids.every((id) => result.items.find((item) => item.id === id).text === "26·02")));
    assert.ok(result.labelEchoes.some((ids) => ids.map((id) => result.items.find((item) => item.id === id).text).join(" / ") === "System diagnostics / diagnostics"));
    assert.ok(result.items.every((item) => item.rect.height > 1 && item.selector.startsWith("body > ")));
    const limited = await page.evaluate(collectAttentionInventory, { limit: 1 });
    assert.equal(limited.items.length, 1);
    assert.equal(limited.truncated, true);
    await page.setContent('<iframe srcdoc="<p>Frame task</p>"></iframe><div id="host"></div>');
    await page.evaluate(() => { document.querySelector("#host").attachShadow({ mode: "open" }).innerHTML = "<p>Shadow task</p>"; });
    const opaque = await page.evaluate(collectAttentionInventory);
    assert.equal(opaque.opaqueSurfaces.length, 2);
  } finally { await browser.close(); }
});

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = resolve(TEST_DIR, "../../scripts/visual_layout_audit.mjs");

function projectHasPlaywright() {
  const require = createRequire(join(process.cwd(), "package.json"));
  for (const name of ["playwright", "@playwright/test", "playwright-core"]) {
    try {
      if (require(name)?.chromium) return true;
    } catch { /* try the next installed layout */ }
  }
  return false;
}

function runScript(args) {
  return new Promise((resolveRun) => {
    const child = spawn(process.execPath, [SCRIPT, ...args], { cwd: process.cwd() });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("close", (code) => resolveRun({ code, stdout, stderr }));
  });
}

test("wrapped-control ignores same-baseline icon/text and non-control semantic containers", async (t) => {
  if (!projectHasPlaywright()) {
    return t.skip("Run from the audited project that supplies Playwright; browser behavior is unverified here.");
  }
  const root = await mkdtemp(join(os.tmpdir(), "visual-layout-lines-"));
  const artifact = join(root, "fixture.html");
  const out = join(root, "evidence");
  await writeFile(artifact, `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Line grouping calibration</title><style>
body{margin:0;font:16px/1.3 Arial,sans-serif}main{padding:20px}
.control{display:inline-block;padding:8px 12px;font:16px/24px Arial,sans-serif;white-space:nowrap}
.arrow{margin-right:6px;font-size:12px;vertical-align:text-top}
.topic-nav{width:120px;margin-top:12px}#wrapped{width:52px;white-space:normal;margin-top:12px}
</style></head><body><main><h1>Line grouping calibration</h1>
<button id="same-baseline" class="control"><span class="arrow">→</span><span>Continue</span></button>
<div id="semantic" class="topic-nav">Related navigation context</div>
<button id="wrapped">Continue now</button></main></body></html>`);
  try {
    const result = await runScript([
      "--file", artifact,
      "--viewport", "1200x400",
      "--settle-ms", "0",
      "--out", out,
    ]);
    assert.equal(result.code, 1, result.stdout + result.stderr);
    const report = JSON.parse(await readFile(join(out, "frontend-visual-qa-report.json"), "utf8"));
    const wrapped = report.issues.filter((issue) => issue.type === "wrapped-control");
    assert.deepEqual(wrapped.map((issue) => issue.selector), ["button#wrapped"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

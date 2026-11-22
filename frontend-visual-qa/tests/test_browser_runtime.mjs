import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { isCloningBrowserPath, resolveBrowserPath } from "../scripts/browser_runtime.mjs";

const regular = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const testing = "test-home/Applications/Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";

function options(overrides = {}) {
  const paths = new Set([testing]);
  return {
    platform: "darwin",
    env: {},
    home: "test-home",
    exists: candidate => paths.has(candidate),
    realpath: candidate => candidate,
    ...overrides,
  };
}

test("macOS defaults to Chrome for Testing", () => {
  assert.equal(resolveBrowserPath(options()), testing);
});

test("missing Chrome for Testing falls back to Playwright bundled Chromium, never regular Chrome", () => {
  const result = resolveBrowserPath(options({ exists: candidate => candidate === regular }));
  assert.equal(result, null);
});

test("explicit regular Chrome is rejected", () => {
  assert.throws(
    () => resolveBrowserPath(options({ env: { CHROME_PATH: regular }, exists: () => true })),
    /Regular Chrome is disabled/u,
  );
});

test("case aliases and symlinks cannot bypass the regular Chrome guard", () => {
  const alias = "/applications/google chrome.app/contents/macos/google chrome";
  assert.equal(isCloningBrowserPath(alias, { realpath: () => regular }), true);
  assert.throws(
    () => resolveBrowserPath(options({
      env: { CHROME_PATH: alias },
      exists: () => true,
      realpath: () => regular,
    })),
    /Regular Chrome is disabled/u,
  );
});

test("default Chrome for Testing symlink to regular Chrome is rejected", () => {
  assert.throws(
    () => resolveBrowserPath(options({ exists: candidate => candidate === testing, realpath: () => regular })),
    /resolves to regular Chrome/u,
  );
});

test("explicit regular Chrome requires the documented double override", () => {
  assert.equal(resolveBrowserPath(options({
    env: { CHROME_PATH: regular, FRONTEND_VISUAL_QA_ALLOW_CLONING_CHROME: "1" },
    exists: () => true,
  })), regular);
});

test("explicit Chrome for Testing is accepted", () => {
  assert.equal(resolveBrowserPath(options({ env: { CHROME_PATH: testing } })), testing);
});

test("non-macOS preserves system browser discovery and bundled fallback", () => {
  assert.equal(resolveBrowserPath(options({ platform: "linux" })), null);
  assert.equal(resolveBrowserPath(options({
    platform: "linux",
    exists: candidate => candidate === "/usr/bin/google-chrome",
  })), "/usr/bin/google-chrome");
});

test("bundled launchers do not hardcode regular Chrome", async () => {
  const directory = fileURLToPath(new URL("../scripts/", import.meta.url));
  const files = (await readdir(directory)).filter(name => name.endsWith(".mjs"));
  assert.ok(files.length >= 5, "static guard must examine the bundled script surface");
  for (const file of files) {
    const source = await readFile(new URL(`../scripts/${file}`, import.meta.url), "utf8");
    assert.doesNotMatch(source, /\/Applications\/Google Chrome\.app/u, file);
  }
});

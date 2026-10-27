import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const require = createRequire(import.meta.url);
const resolver = fileURLToPath(new URL('../scripts/resolve-playwright.cjs', import.meta.url));
const loadPlaywright = require(resolver);

test('browser entry invokes the resolver instead of destructuring the loader', () => {
  const source = readFileSync(new URL('../scripts/read-usage-profile.cjs', import.meta.url), 'utf8');
  assert.match(source, /const \{ chromium \} = require\('\.\/resolve-playwright\.cjs'\)\(\);/);
});

test('navigation failures stay unknown instead of becoming a logged-out account', () => {
  const {parseUsage} = require('../scripts/read-usage-profile.cjs');
  const failed = parseUsage('', 'chrome-error://chromewebdata/');
  assert.equal(failed.unavailable, true);
  assert.equal(failed.loggedOut, false);
  const loggedOut = parseUsage('Log in or sign up', 'https://chatgpt.com/');
  assert.equal(loggedOut.unavailable, false);
  assert.equal(loggedOut.loggedOut, true);
});

test('rejected usage navigation cannot reuse a retained HTTPS page', async () => {
  const {readUsagePage} = require('../scripts/read-usage-profile.cjs');
  const retainedPages = [
    'Log in or sign up',
    'account@example.com\nWeekly usage limit\n50% remaining',
  ];
  for (const retainedText of retainedPages) {
    const page = {
      goto: async () => { throw new Error('Timeout 20000ms exceeded'); },
      innerText: async () => retainedText,
      url: () => 'https://chatgpt.com/',
    };
    const result = await readUsagePage(page, 0);
    assert.equal(result.unavailable, true);
    assert.equal(result.loggedOut, false);
  }
});

test('successful usage navigation preserves fresh body text for normal output', async () => {
  const {readUsagePage} = require('../scripts/read-usage-profile.cjs');
  const text = 'account@example.com\nWeekly usage limit\n50% remaining';
  const page = {
    goto: async () => {},
    innerText: async () => text,
    url: () => 'https://chatgpt.com/codex/settings/usage',
  };
  const result = await readUsagePage(page, 0);
  assert.equal(result.unavailable, false);
  assert.equal(result.loggedOut, false);
  assert.equal(result.text, text);
});

test('existing local Playwright resolves without NODE_PATH', () => {
  const env = {...process.env};
  delete env.NODE_PATH;
  const result = spawnSync(process.execPath, ['-e', `const load=require(${JSON.stringify(resolver)}); console.log(typeof load().chromium)`], {
    encoding: 'utf8', env, timeout: 10000,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), 'object');
});

test('explicit dependency path supports spaces and missing paths fail usefully', () => {
  const root = mkdtempSync(join(tmpdir(), 'quota dependency '));
  try {
    const packageDir = join(root, 'playwright with spaces');
    mkdirSync(packageDir);
    writeFileSync(join(packageDir, 'package.json'), JSON.stringify({name: 'playwright', main: 'index.js'}));
    writeFileSync(join(packageDir, 'index.js'), 'module.exports={chromium:{fixture:true}};\n');
    envWithPath(packageDir, resolver, (result) => {
      assert.equal(result.status, 0, result.stderr);
      assert.equal(result.stdout.trim(), 'object');
    });
    envWithPath(join(root, 'missing'), resolver, (result) => {
      assert.equal(result.status, 1);
      assert.match(result.stderr, /TIBO_PLAYWRIGHT_PATH/);
      assert.doesNotMatch(result.stderr, /NODE_PATH/);
    });
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

function envWithPath(dependencyPath, source, check) {
  const env = {...process.env, TIBO_PLAYWRIGHT_PATH: dependencyPath};
  delete env.NODE_PATH;
  const result = spawnSync(process.execPath, ['-e', `const load=require(${JSON.stringify(source)}); console.log(typeof load().chromium)`], {
    encoding: 'utf8', env, timeout: 10000,
  });
  check(result);
}

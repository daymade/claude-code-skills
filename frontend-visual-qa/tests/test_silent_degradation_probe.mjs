#!/usr/bin/env node
"use strict";

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = resolve(TEST_DIR, '../scripts/silent_degradation_probe.mjs');

function runProbe(args) {
  return new Promise((resolveRun) => {
    const child = spawn(process.execPath, [SCRIPT, ...args], { cwd: process.cwd() });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('close', (code) => resolveRun({ code, stdout, stderr }));
  });
}

function projectHasPlaywright() {
  return [
    join(process.cwd(), 'node_modules/playwright/index.js'),
    join(process.cwd(), '.ds-sync/node_modules/playwright/index.js'),
    join(process.cwd(), '../node_modules/playwright/index.js'),
  ].some(existsSync);
}

function listen(server) {
  return new Promise((resolveListen) => {
    server.listen(0, '127.0.0.1', resolveListen);
  });
}

test('class mode ignores project and library CSS comments', async () => {
  const root = await mkdtemp(join(os.tmpdir(), 'silent-degradation-css-'));
  try {
    const projectComment = join(root, 'project-comment.css');
    const liveProject = join(root, 'live-project.css');
    const library = join(root, 'library.css');
    const libraryComment = join(root, 'library-comment.css');
    await writeFile(projectComment, '/* old .ant-removed selector */\n.bridge { color: red; }\n');
    await writeFile(liveProject, '.ant-removed { color: red; }\n');
    await writeFile(library, '.ant-current { color: blue; }\n');
    await writeFile(libraryComment, '/* .ant-removed no longer exists */\n');

    const falseFailure = await runProbe([
      'class', '--css', projectComment, '--library-css', library,
    ]);
    assert.equal(falseFailure.code, 0, falseFailure.stdout + falseFailure.stderr);
    assert.equal(JSON.parse(falseFailure.stdout).referenced, 0);

    const falseClear = await runProbe([
      'class', '--css', liveProject, '--library-css', libraryComment,
    ]);
    assert.equal(falseClear.code, 1, falseClear.stdout + falseClear.stderr);
    assert.deepEqual(JSON.parse(falseClear.stdout).dead, ['ant-removed']);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('font mode treats system-ui as a platform generic', async (t) => {
  if (!projectHasPlaywright()) return t.skip('Playwright is not available in the audited project');
  const result = await runProbe([
    'font',
    '--url', 'data:text/html,<p>probe</p>',
    '--family', 'system-ui',
    '--wait', '0',
  ]);
  assert.equal(result.code, 0, result.stdout + result.stderr);
  assert.deepEqual(JSON.parse(result.stdout).platformGeneric, ['system-ui']);
});

test('invalid header syntax is rejected as input before browser startup', async () => {
  const result = await runProbe([
    'font',
    '--url', 'http://127.0.0.1/',
    '--family', 'system-ui',
    '--header',
  ]);
  assert.equal(result.code, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /invalid --header/);
  assert.doesNotMatch(result.stderr, /playwright not resolvable/);
});

test('headers stay on the requested origin across redirects', async (t) => {
  if (!projectHasPlaywright()) return t.skip('Playwright is not available in the audited project');
  let initialAuthorization = '';
  let redirectedAuthorization = '';
  const destination = http.createServer((request, response) => {
    redirectedAuthorization = request.headers.authorization || '';
    response.end('<p>destination</p>');
  });
  await listen(destination);
  const redirector = http.createServer((request, response) => {
    initialAuthorization = request.headers.authorization || '';
    response.writeHead(302, {
      Location: `http://127.0.0.1:${destination.address().port}/destination`,
    });
    response.end();
  });
  await listen(redirector);

  try {
    const result = await runProbe([
      'font',
      '--url', `http://127.0.0.1:${redirector.address().port}/start`,
      '--family', 'system-ui',
      '--header', 'Authorization: Bearer PROBE_SECRET',
      '--wait', '0',
    ]);
    assert.equal(result.code, 0, result.stdout + result.stderr);
    assert.equal(initialAuthorization, 'Bearer PROBE_SECRET');
    assert.equal(redirectedAuthorization, '');
  } finally {
    redirector.close();
    destination.close();
  }
});

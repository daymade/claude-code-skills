#!/usr/bin/env node
"use strict";

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = resolve(TEST_DIR, '../scripts/silent_degradation_probe.mjs');
const LAYOUT_SCRIPT = resolve(TEST_DIR, '../scripts/visual_layout_audit.mjs');

function runScript(script, args, options = {}) {
  return new Promise((resolveRun) => {
    const child = spawn(process.execPath, [script, ...args], {
      cwd: process.cwd(),
      env: { ...process.env, ...options.env },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('close', (code) => resolveRun({ code, stdout, stderr }));
  });
}

function runProbe(args, options) {
  return runScript(SCRIPT, args, options);
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

test('raw headers are rejected before browser startup', async () => {
  const result = await runProbe([
    'font',
    '--url', 'http://127.0.0.1/',
    '--family', 'system-ui',
    '--header',
  ]);
  assert.equal(result.code, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /--header is disabled/);
  assert.doesNotMatch(result.stderr, /playwright not resolvable/);
});

test('arbitrary token-like raw headers cannot bypass environment indirection', async () => {
  const result = await runProbe([
    'font',
    '--url', 'http://127.0.0.1/',
    '--family', 'system-ui',
    '--header', 'X-Access-Token: PLACEHOLDER_ONLY',
  ]);
  assert.equal(result.code, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /--header is disabled/);
  assert.doesNotMatch(result.stderr, /playwright not resolvable/);
});

test('equals-form raw headers cannot bypass environment indirection', async () => {
  const result = await runProbe([
    'font',
    '--url', 'http://127.0.0.1/',
    '--family', 'system-ui',
    '--header=X-Access-Token:HEADER_VALUE_SENTINEL',
  ]);
  assert.equal(result.code, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /--header is disabled/);
  assert.doesNotMatch(result.stderr, /HEADER_VALUE_SENTINEL|playwright not resolvable/);
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
      '--header-env', 'Authorization: FVQA_TEST_AUTH',
      '--wait', '0',
    ], { env: { FVQA_TEST_AUTH: 'Bearer PROBE_SECRET' } });
    assert.equal(result.code, 0, result.stdout + result.stderr);
    assert.equal(initialAuthorization, 'Bearer PROBE_SECRET');
    assert.equal(redirectedAuthorization, '');
  } finally {
    redirector.close();
    destination.close();
  }
});

test('navigation failures redact the exact URL and use the documented runtime exit', async (t) => {
  if (!projectHasPlaywright()) return t.skip('Playwright is not available in the audited project');
  const closedServer = http.createServer();
  await listen(closedServer);
  const port = closedServer.address().port;
  await new Promise((resolveClose) => closedServer.close(resolveClose));
  const result = await runProbe([
    'font',
    '--url', `http://127.0.0.1:${port}/NET_PATH_SENTINEL?token=NET_QUERY_SENTINEL#/NET_FRAGMENT_SENTINEL`,
    '--family', 'system-ui',
    '--wait', '0',
  ]);
  assert.equal(result.code, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /probe navigation failed/);
  assert.doesNotMatch(result.stderr, /NET_PATH_SENTINEL|NET_QUERY_SENTINEL|NET_FRAGMENT_SENTINEL/);
  assert.match(result.stderr, /<redacted-path>/);
  assert.match(result.stderr, /<redacted-fragment>/);
});

test('layout report hashes the exact target without persisting secret URL values', async (t) => {
  if (!projectHasPlaywright()) return t.skip('Playwright is not available in the audited project');
  const root = await mkdtemp(join(os.tmpdir(), 'visual-layout-redaction-'));
  const output = join(root, 'evidence');
  const server = http.createServer((_request, response) => {
    response.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}h1{overflow-wrap:anywhere}</style><title>Safe fixture</title><main><h1>Ready</h1></main><script>document.title=location.pathname.split("/").filter(Boolean).at(-1)||"root";document.querySelector("h1").textContent=new URL(location.href).searchParams.get("tenant")+"|"+location.hash;</script>');
  });
  await listen(server);
  try {
    const target = `http://127.0.0.1:${server.address().port}/reset/PATH_SECRET?code=OAUTH_SECRET&tenant=PRIVATE_ACCOUNT#/password/FRAGMENT_SECRET?token=HASH_QUERY_SECRET`;
    const result = await runScript(LAYOUT_SCRIPT, [
      '--url', target,
      '--viewport', '390x844',
      '--settle-ms', '0',
      '--out', output,
    ]);
    assert.equal(result.code, 0, result.stdout + result.stderr);
    const report = JSON.parse(await readFile(join(output, 'frontend-visual-qa-report.json'), 'utf8'));
    const serialized = JSON.stringify(report);
    assert.doesNotMatch(result.stdout + result.stderr, /PATH_SECRET|OAUTH_SECRET|PRIVATE_ACCOUNT|FRAGMENT_SECRET|HASH_QUERY_SECRET/);
    assert.doesNotMatch(serialized, /PATH_SECRET|OAUTH_SECRET|PRIVATE_ACCOUNT|FRAGMENT_SECRET|HASH_QUERY_SECRET/);
    assert.equal(report.target.kind, 'web');
    assert.match(report.target.redacted, /\/<redacted-path>/);
    assert.match(report.target.redacted, /code=<redacted>/);
    assert.match(report.target.redacted, /tenant=<redacted>/);
    assert.match(report.viewports[0].finalTarget.redacted, /#<redacted-fragment>/);
    assert.match(report.target.targetStringSha256, /^[a-f0-9]{64}$/);
    assert.equal(report.target.targetStringSha256, report.viewports[0].requestedTarget.targetStringSha256);
    assert.match(report.viewports[0].titleEvidence.sha256, /^[a-f0-9]{64}$/);
    assert.match(report.viewports[0].h1Evidence.sha256, /^[a-f0-9]{64}$/);
    assert.equal('title' in report.viewports[0], false);
    assert.equal('h1' in report.viewports[0], false);
  } finally {
    server.close();
    await rm(root, { recursive: true, force: true });
  }
});

test('layout navigation errors redact path and fragment secrets from stderr and report', async (t) => {
  if (!projectHasPlaywright()) return t.skip('Playwright is not available in the audited project');
  const root = await mkdtemp(join(os.tmpdir(), 'visual-layout-error-redaction-'));
  const output = join(root, 'evidence');
  const server = http.createServer((_request, response) => {
    response.writeHead(404);
    response.end('missing');
  });
  await listen(server);
  try {
    const target = `http://127.0.0.1:${server.address().port}/reset/ERROR_PATH_SECRET?code=ERROR_QUERY_SECRET#/route/ERROR_FRAGMENT_SECRET`;
    const result = await runScript(LAYOUT_SCRIPT, [
      '--url', target,
      '--viewport', '390x844',
      '--settle-ms', '0',
      '--out', output,
    ]);
    assert.equal(result.code, 2, result.stdout + result.stderr);
    assert.doesNotMatch(result.stderr, /ERROR_PATH_SECRET|ERROR_QUERY_SECRET|ERROR_FRAGMENT_SECRET/);
    const serialized = await readFile(join(output, 'frontend-visual-qa-report.json'), 'utf8');
    assert.doesNotMatch(serialized, /ERROR_PATH_SECRET|ERROR_QUERY_SECRET|ERROR_FRAGMENT_SECRET/);
    assert.match(serialized, /<redacted-path>/);
    assert.match(serialized, /<redacted-fragment>/);
  } finally {
    server.close();
    await rm(root, { recursive: true, force: true });
  }
});

test('single-file layout evidence hashes file bytes and redacts the canonical path', async (t) => {
  if (!projectHasPlaywright()) return t.skip('Playwright is not available in the audited project');
  const root = await mkdtemp(join(os.tmpdir(), 'visual-layout-file-identity-'));
  const artifact = join(root, 'artifact.html');
  const output = join(root, 'evidence');
  const content = '<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>File fixture</title><main>Ready</main>';
  await writeFile(artifact, content);
  try {
    const result = await runScript(LAYOUT_SCRIPT, [
      '--file', artifact,
      '--viewport', '390x844',
      '--settle-ms', '0',
      '--out', output,
    ]);
    assert.equal(result.code, 0, result.stdout + result.stderr);
    const report = JSON.parse(await readFile(join(output, 'frontend-visual-qa-report.json'), 'utf8'));
    assert.equal(report.target.kind, 'single-file');
    assert.equal(report.target.redactedCanonicalPath, 'file:///<redacted-path>');
    assert.equal(report.target.rendererScheme, 'file:');
    assert.equal(
      report.target.contentSha256,
      createHash('sha256').update(content).digest('hex'),
    );
    assert.doesNotMatch(JSON.stringify(report.target), new RegExp(root.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

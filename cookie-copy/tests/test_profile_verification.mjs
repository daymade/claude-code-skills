import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync, symlinkSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {verified} from '../scripts/verify-chatgpt-profile.mjs';

test('identity verification is independent of quota availability', () => {
  assert.equal(verified({state:'authenticated', email:'test@example.com'}, 'test@example.com'), true);
  assert.equal(verified({state:'authenticated', email:'test@example.com', usage:{status:403}}, 'test@example.com'), true);
  for (const r of [null, {}, {state:'anonymous'}, {state:'authenticated',email:'other@example.com'}]) {
    assert.equal(verified(r,'test@example.com'),false);
  }
});

test('CLI help executes through an installed symlink, including paths with spaces', () => {
  const root = mkdtempSync(join(tmpdir(), 'profile-entry-'));
  try {
    const entry = join(root, 'linked verifier.mjs');
    const source = fileURLToPath(new URL('../scripts/verify-chatgpt-profile.mjs', import.meta.url));
    symlinkSync(source, entry);
    for (const script of [source, entry]) {
      const result = spawnSync(process.execPath, [script, '--help'], {encoding:'utf8', timeout:10000});
      assert.equal(result.status, 0, result.stderr);
      assert.match(result.stdout, /--profile-dir/);
      assert.match(result.stdout, /--expected-email/);
    }
  } finally {rmSync(root, {recursive:true, force:true});}
});

test('authenticated identity can be checked without a quota request', async () => {
  const {verifyIdentity} = await import('../scripts/verify-chatgpt-profile.mjs');
  const methods = [];
  const cmd = async (method, params) => {
    methods.push(method);
    if (method === 'Runtime.evaluate') {
      assert.doesNotMatch(params.expression, /wham|accessToken|Authorization/);
      return {result:{value:{state:'authenticated',email:'test@example.com'}}};
    }
    return {};
  };
  const result = await verifyIdentity(cmd, {'expected-email':'test@example.com'});
  assert.equal(result.status,'verified');
  assert.equal(result.login_verified,true);
  assert.equal(result.usage,undefined);
  assert.ok(methods.includes('Page.navigate'));
});

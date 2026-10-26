import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync, symlinkSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {verified} from '../scripts/verify-chatgpt-profile.mjs';

test('only the expected authenticated account with readable identity-bound usage passes', () => {
  const good = {state:'authenticated',email:'test@example.com',usage:{status:200,identity_matches:true,window_count:1}};
  assert.equal(verified(good, 'TEST@example.com'), true);
  for (const result of [null, {}, {...good,state:'anonymous'}, {...good,email:'other@example.com'},
    {...good,usage:null}, {...good,usage:{...good.usage,status:403}},
    {...good,usage:{...good.usage,identity_matches:false}}, {...good,usage:{...good.usage,window_count:0}},
    {...good,usage:{status:200}}, {...good,usage:{...good.usage,window_count:null}}]) {
    assert.equal(verified(result, 'test@example.com'), false);
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

test('independently installed cookie-copy dependency must resolve before browser work', () => {
  const root = mkdtempSync(join(tmpdir(),'quota dependency '));
  try {
    const source=fileURLToPath(new URL('../scripts/verify-chatgpt-profile.mjs',import.meta.url));
    for (const dependency of ['', join(root,'missing')]) {
      const result=spawnSync(process.execPath,[source,'--profile-dir',join(root,'target'),'--expected-email','test@example.com'], {
        encoding:'utf8', env:{...process.env,COOKIE_COPY_SKILL_DIR:dependency},timeout:10000
      });
      assert.equal(result.status,1);
      assert.match(result.stderr,/cookie-copy|COOKIE_COPY_SKILL_DIR/);
      assert.doesNotMatch(result.stderr,/test@example.com/);
    }
  } finally {rmSync(root,{recursive:true,force:true});}
});

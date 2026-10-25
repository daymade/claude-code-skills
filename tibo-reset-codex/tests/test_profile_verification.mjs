import assert from 'node:assert/strict';
import {test} from 'node:test';
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

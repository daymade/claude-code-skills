#!/usr/bin/env node
// Quota-workflow adapter: cookie-copy owns Chrome and login verification.
import {realpath} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

export function verified(result, expected) {
  return result?.state === 'authenticated' && typeof result.email === 'string'
    && result.email.toLowerCase() === expected.toLowerCase()
    && result.usage?.status === 200 && result.usage.identity_matches === true
    && Number.isInteger(result.usage.window_count) && result.usage.window_count > 0;
}

async function cookieCopy() {
  if ('COOKIE_COPY_SKILL_DIR' in process.env && !process.env.COOKIE_COPY_SKILL_DIR.trim()) {
    throw Error('COOKIE_COPY_SKILL_DIR must be a nonempty resolved Skill directory');
  }
  const root = process.env.COOKIE_COPY_SKILL_DIR
    ? resolve(process.env.COOKIE_COPY_SKILL_DIR)
    : fileURLToPath(new URL('../../cookie-copy/', import.meta.url));
  try {return await import(pathToFileURL(resolve(root, 'scripts/verify-chatgpt-profile.mjs')).href);}
  catch (cause) {throw Error('Load/install cookie-copy and set COOKIE_COPY_SKILL_DIR to its resolved Skill directory', {cause});}
}

export async function run(argv) {
  const owner = await cookieCopy();
  return owner.run(argv, async (cmd, opt) => {
    const result = await owner.verifyIdentity(cmd, opt);
    if (result.state === 'authenticated' && result.email?.toLowerCase() === opt['expected-email'].toLowerCase()) {
      const reply = await cmd('Runtime.evaluate', {returnByValue: true, awaitPromise: true, expression: `(async () => {
        if(location.origin !== 'https://chatgpt.com') return {status:null,identity_matches:false,window_count:0};
        try {
          const s=JSON.parse(document.body.innerText), token=s.accessToken;
          if(typeof token!=='string') return {status:null,identity_matches:false,window_count:0};
          const claims=JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
          const account=claims['https://api.openai.com/auth']?.chatgpt_account_id;
          if(!account) return {status:null,identity_matches:false,window_count:0};
          const response=await fetch('/backend-api/wham/usage',{credentials:'include',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:'Bearer '+token,'ChatGPT-Account-Id':account}});
          if(!response.ok) return {status:response.status,identity_matches:false,window_count:0};
          const usage=await response.json();
          const windows=[usage.rate_limit?.primary_window,usage.rate_limit?.secondary_window].filter(w=>w&&[18000,604800].includes(w.limit_window_seconds)&&Number.isFinite(w.used_percent)&&w.used_percent>=0&&w.used_percent<=100);
          return {status:response.status,identity_matches:usage.account_id===account&&typeof usage.email==='string'&&usage.email.toLowerCase()===${JSON.stringify(opt['expected-email'].toLowerCase())},window_count:windows.length};
        } catch {return {status:null,identity_matches:false,window_count:0};}
      })()`});
      result.usage = reply.result?.value;
    }
    return {...result, status: verified(result, opt['expected-email']) ? 'verified' : 'unconfirmed'};
  });
}

if (process.argv[1] && await realpath(fileURLToPath(import.meta.url)) === await realpath(resolve(process.argv[1]))) {
  if (process.argv.includes('--help')) {
    console.log('node verify-chatgpt-profile.mjs --profile-dir <isolated-root> [--initialize | --expected-email <email>] [--chrome <executable>] [--proxy <url>] [--headless]');
  } else {
    try {const result = await run(process.argv.slice(2)); console.log(JSON.stringify(result)); process.exitCode = ['verified','initialized'].includes(result.status) ? 0 : 2;}
    catch (error) {console.error(JSON.stringify({status: 'error', reason: error.message})); process.exitCode = 1;}
  }
}

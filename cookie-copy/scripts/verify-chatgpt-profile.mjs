#!/usr/bin/env node
// Verify the expected ChatGPT identity in this invocation's isolated Chrome.
import {spawn, execFileSync} from 'node:child_process';
import {access, mkdir, readFile, unlink, realpath} from 'node:fs/promises';
import {homedir} from 'node:os';
import {resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';

export function verified(result, expected) {
  return result?.state === 'authenticated' && typeof result.email === 'string'
    && result.email.toLowerCase() === expected.toLowerCase();
}

export async function verifyIdentity(cmd, opt) {
    await cmd('Page.enable');
    await cmd('Page.navigate', {url: 'https://chatgpt.com/api/auth/session'});
    let result = {state: 'unconfirmed'};
    for (let n = 0; n < 60; n++) {
      const reply = await cmd('Runtime.evaluate', {returnByValue: true, expression: `(() => {
        if(location.origin !== 'https://chatgpt.com') return {state:'unconfirmed'};
        try {const session=JSON.parse(document.body.innerText); return {state:session.user?.email?'authenticated':'anonymous',email:session.user?.email||null};}
        catch {return {state:document.title.includes('Just a moment')?'challenge':'loading'};}
      })()`});
      result = reply.result?.value || {state: 'unconfirmed'};
      if (['authenticated', 'anonymous'].includes(result.state)) break;
      await delay(500);
    }
    return {...result, login_verified: verified(result, opt['expected-email']),
      status: verified(result, opt['expected-email']) ? 'verified' : 'unconfirmed'};
}

function options(argv) {
  const out = {initialize: false, headless: false};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--initialize') out.initialize = true;
    else if (arg === '--headless') out.headless = true;
    else if (['--profile-dir', '--expected-email', '--chrome', '--proxy'].includes(arg)) {
      if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw Error('missing value for ' + arg);
      out[arg.slice(2)] = argv[++i];
    } else throw Error('unknown argument');
  }
  if (!out['profile-dir']) throw Error('--profile-dir is required');
  if (!out.initialize && !out['expected-email']) throw Error('--expected-email is required');
  return out;
}

function systemProxy() {
  const text = execFileSync('/usr/sbin/scutil', ['--proxy'], {encoding: 'utf8'});
  if (!/HTTPSEnable\s*:\s*1/.test(text)) return null;
  const host = text.match(/HTTPSProxy\s*:\s*(\S+)/)?.[1];
  const port = text.match(/HTTPSPort\s*:\s*(\d+)/)?.[1];
  if (!host || !port) throw Error('system HTTPS proxy configuration is incomplete');
  return `http://${host}:${port}`;
}

export async function run(argv, verifySession = verifyIdentity) {
  const opt = options(argv);
  if (process.platform !== 'darwin') throw Error('this verifier supports macOS Chrome only');
  const requestedRoot = resolve(opt['profile-dir']);
  let root;
  try {root = await realpath(requestedRoot);}
  catch (error) {if (error.code !== 'ENOENT') throw error; root = requestedRoot;}
  const daily = await realpath(resolve(homedir(), 'Library/Application Support/Google/Chrome'));
  if (root === daily || root.startsWith(daily + '/')) {
    throw Error('daily Chrome profile is not an isolated verification target');
  }
  const chrome = opt.chrome || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  await access(chrome);
  if (opt.initialize) await mkdir(root, {mode: 0o700}); // Existing roots are never initialized again.
  else await access(root);
  // Chrome's lock may be a dangling symlink; access() would miss that case.
  const {lstat} = await import('node:fs/promises');
  try {await lstat(root + '/SingletonLock'); throw Error('target browser is active or its lock is unresolved');}
  catch (error) {if (error.code !== 'ENOENT') throw error;}
  try {await unlink(root + '/DevToolsActivePort');}
  catch (error) {if (error.code !== 'ENOENT') throw error;}
  const proxy = opt.proxy || systemProxy();
  const child = spawn(chrome, [
    `--user-data-dir=${root}`, '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check',
    ...(opt.headless ? ['--headless=new'] : []), ...(proxy ? [`--proxy-server=${proxy}`] : []), 'about:blank',
  ], {stdio: ['ignore', 'ignore', 'ignore']});
  let spawnError;
  child.on('error', () => {spawnError = true;});
  let ws, seq = 0;
  const pending = new Map();
  async function send(method, params = {}, sessionId) {
    return new Promise((resolveCall, reject) => {
      const id = ++seq;
      const timer = setTimeout(() => {pending.delete(id); reject(Error('CDP request timed out: ' + method));}, 20000);
      pending.set(id, {resolve: resolveCall, reject, timer});
      ws.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  try {
    let endpoint;
    for (let n = 0; n < 100; n++) {
      if (spawnError || child.exitCode !== null) throw Error('owned Chrome failed to start');
      try {endpoint = await readFile(root + '/DevToolsActivePort', 'utf8'); break;}
      catch (error) {if (error.code !== 'ENOENT') throw error;}
      await delay(100);
    }
    if (!endpoint) throw Error('owned Chrome did not publish its debugging endpoint');
    const [port, path] = endpoint.trim().split('\n');
    if (!/^\d+$/.test(port) || !path?.startsWith('/devtools/browser/')) throw Error('invalid owned Chrome endpoint');
    ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
    await new Promise((connected, reject) => {
      const timer = setTimeout(() => reject(Error('owned Chrome connection timed out')), 10000);
      ws.onopen = () => {clearTimeout(timer); connected();};
      ws.onerror = () => {clearTimeout(timer); reject(Error('owned Chrome connection failed'));};
    });
    ws.onmessage = event => {
      const data = JSON.parse(event.data), entry = pending.get(data.id);
      if (!entry) return;
      pending.delete(data.id); clearTimeout(entry.timer);
      data.error ? entry.reject(Error('CDP command failed')) : entry.resolve(data.result);
    };
    const {targetId} = await send('Target.createTarget', {url: 'about:blank'});
    const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
    const cmd = (method, params = {}) => send(method, params, sessionId);
    if (opt.initialize) {
      await cmd('Network.getAllCookies');
      for (let n = 0; n < 50; n++) {
        try {await access(root + '/Default/Cookies'); return {status: 'initialized', login_verified: false};}
        catch (error) {if (error.code !== 'ENOENT') throw error;}
        await delay(100);
      }
      throw Error('Chrome did not initialize its cookie database');
    }
    return await verifySession(cmd, opt);
  } finally {
    if (ws?.readyState === WebSocket.OPEN) {
      try {await send('Browser.close');} catch {} // The owned child is still reaped below.
      ws.close();
    }
    if (child.exitCode === null && !spawnError) {
      await Promise.race([new Promise(done => child.once('exit', done)), delay(5000)]);
      if (child.exitCode === null) child.kill('SIGTERM'); // Only this invocation's own child.
    }
    for (const entry of pending.values()) {clearTimeout(entry.timer); entry.reject(Error('owned browser closed'));}
  }
}

if (process.argv[1] && await realpath(fileURLToPath(import.meta.url)) === await realpath(resolve(process.argv[1]))) {
  if (process.argv.includes('--help')) {
    console.log('node verify-chatgpt-profile.mjs --profile-dir <isolated-root> [--initialize | --expected-email <email>] [--chrome <executable>] [--proxy <url>] [--headless]');
  } else {
    try {const result = await run(process.argv.slice(2)); console.log(JSON.stringify(result)); process.exitCode = ['verified','initialized'].includes(result.status) ? 0 : 2;}
    catch {console.error(JSON.stringify({status: 'error', reason: 'browser verification failed; preserve the target and inspect prerequisites'})); process.exitCode = 1;}
  }
}

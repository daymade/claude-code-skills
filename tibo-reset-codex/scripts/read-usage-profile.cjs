#!/usr/bin/env node
// 隔离 profile 第二/多账号 ChatGPT/Codex 用量查询的自动化"手"。
//
// 用法：
//   node read_usage_auto.cjs                    # 读模式：读当前登录账号的 usage（默认 profile a）
//   node read_usage_auto.cjs --drive-login      # 未登录时驱动到 Google 账号选择器（交人工输密码）
//   TIBO_PROFILE=b node read_usage_auto.cjs     # 换 profile b
//   TIBO_PROXY=... node read_usage_auto.cjs     # 自定义代理（默认 127.0.0.1:1082）
//
// 边界（重要，勿越界）：
//   - 只驱动到 Google「选择账号」页为止。密码/验证码/授权确认一律交人工，绝不自动化输入。
//   - 首次人工登录一次后，会话 cookie 存进隔离 profile，之后本脚本读模式全自动。
//   - 点击走 CDP Input.dispatchMouseEvent（真实 isTrusted 事件）——登录页 SSO 按钮点得动，
//     但 chatgpt.com 首页那个「Log in」实测点不动（事件挂载不同），所以登录一律走 /auth/login。
//
// 通道事实（2026-09-16 实测）：
//   - open -na 不继承系统代理，必须显式 --proxy-server=...，否则 chatgpt.com 直连挂起/403。
//   - CDP Network.getAllCookies 拿到的 Google cookie 是 Google 侧编码值，读不出明文邮箱；
//     账号身份只能从页面 DOM 读（账号选择器 / myaccount 页）。
const { chromium } = require('playwright');
const { execFile } = require('child_process');
const http = require('http');

const PORT = 9222;
const PROFILE = process.env.TIBO_PROFILE || 'a';
const UDD = `${process.env.HOME}/.chrome-profiles/tibo-codex-${PROFILE}`;
const PROXY = process.env.TIBO_PROXY || 'http://127.0.0.1:1082';
const USAGE = 'https://chatgpt.com/codex/settings/usage';
const LOGIN = 'https://chatgpt.com/auth/login';
const DRIVE = process.argv.includes('--drive-login');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function cdpReady() {
  return new Promise((res) => {
    const req = http.get({ host: '127.0.0.1', port: PORT, path: '/json/version', timeout: 1000 }, (r) => {
      let b = ''; r.on('data', (c) => (b += c)); r.on('end', () => res(b.length > 0));
    });
    req.on('error', () => res(false)); req.on('timeout', () => { req.destroy(); res(false); });
  });
}

async function ensureChrome() {
  if (await cdpReady()) return true;
  console.log(`[chrome] 拉起隔离 Chrome profile=${PROFILE} proxy=${PROXY}`);
  execFile('open', ['-na', 'Google Chrome', '--args',
    `--user-data-dir=${UDD}`, `--remote-debugging-port=${PORT}`,
    `--proxy-server=${PROXY}`, 'about:blank'], () => {});
  for (let i = 0; i < 25; i++) { if (await cdpReady()) { await sleep(2500); return true; } await sleep(700); }
  return false;
}

// 真实点击：CDP Input.dispatchMouseEvent，isTrusted=true
async function realClick(cdp, x, y) {
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await sleep(180);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await sleep(90);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
}

function parseUsage(text, url) {
  const email = (text.match(/[\w.+-]+@[\w-]+\.[\w.-]+/) || [null])[0];
  const weekly = (text.match(/Weekly usage limit[^\n]{0,70}/i) || [null])[0];
  const pcts = [...text.matchAll(/(\d+)\s*%\s*(remaining|left)/gi)].map((m) => `${m[1]}% ${m[2]}`);
  const resets = [...text.matchAll(/(No usage limit resets available|Full reset[^\n]{0,40})/gi)].map((m) => m[0]);
  const fiveH = (text.match(/5[- ]hour[^\n]{0,60}/i) || [null])[0];
  // 登录态以正面证据为准：解析到邮箱 或 出现 weekly 用量文本 = 已登录。
  // 不猜 URL——登出时 usage 页可能留在 / 首页、也可能重定向到 /auth/login，两种都要覆盖。
  const hasUsage = !!email || /weekly usage limit/i.test(text);
  const loggedOut = !hasUsage;
  return { email, weekly, pcts, resets, fiveH, loggedOut };
}

(async () => {
  if (!(await ensureChrome())) { console.error('隔离 Chrome CDP 未就绪'); process.exit(2); }
  // connectOverCDP 会间歇 handshake 卡顿（ws 连上但 browse 端点没稳定）——带重试
  let browser = null;
  for (let i = 0; i < 4; i++) {
    try { browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`, { timeout: 30000 }); break; }
    catch (e) { console.log(`[cdp] 连接 attempt ${i + 1} 失败: ${e.message.split('\n')[0]}，重试`); await sleep(4000); }
  }
  if (!browser) { console.error('connectOverCDP 多次重试仍失败'); process.exit(3); }
  const ctx = browser.contexts()[0];
  let page = ctx.pages().find((p) => p.url().startsWith('https://chatgpt.com'));
  if (!page) page = await ctx.newPage();

  console.log(`[nav] → ${USAGE}`);
  await page.goto(USAGE, { waitUntil: 'commit', timeout: 20000 }).catch((e) => console.log('goto warn:', e.message.split('\n')[0]));
  await sleep(12000); // SPA 渲染 + 可能重定向到 analytics#usage 或首页/auth/login

  const text = await page.innerText('body').catch(() => '');
  const u = parseUsage(text, page.url());

  if (u.loggedOut) {
    console.log('[登录] usage 页是登出态');
    if (!DRIVE) {
      console.log('未登录。加 --drive-login 可自动驱动到 Google 账号选择器（密码交人工）。');
      console.log('当前 URL:', page.url());
      await browser.close(); return;
    }
    // 驱动登录：走 /auth/login 点 Continue with Google（首页 Log in 点不动）
    console.log('[drive] → /auth/login 点 Continue with Google');
    const lp = await ctx.newPage();
    await lp.goto(LOGIN, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch((e) => console.log('login goto warn:', e.message.split('\n')[0]));
    await sleep(5000);
    const lcdp = await ctx.newCDPSession(lp);
    const loc = lp.getByRole('button', { name: /continue with google/i }).first();
    await loc.scrollIntoViewIfNeeded().catch(() => {});
    await sleep(500);
    const bb = await loc.boundingBox();
    if (!bb) { console.log('未找到 Continue with Google 按钮'); await browser.close(); return; }
    await realClick(lcdp, bb.x + bb.width / 2, bb.y + bb.height / 2);
    console.log('[drive] 已点击，等 Google OAuth 页…');
    // 轮询等 accounts.google.com 出现（OAuth 重定向 + SPA 渲染约需 8-10s，固定 sleep 会漏）
    let gp = null;
    for (let i = 0; i < 15; i++) {
      await sleep(1000);
      gp = ctx.pages().find((p) => p.url().includes('accounts.google.com'));
      if (gp) break;
    }
    if (gp) {
      await sleep(2500);
      const gt = await gp.innerText('body').catch(() => '');
      const accounts = [...gt.matchAll(/[\w.+-]+@[\w-]+\.[\w.-]+/g)].map((m) => m[0]);
      const uniq = [...new Set(accounts)];
      console.log('=== Google 账号选择器（人工在此完成登录，密码/验证码交你）===');
      console.log('可选账号:', uniq.join(' , ') || '(未解析到)');
      console.log('请在弹出的隔离 Chrome 窗口手动点目标账号并完成登录；');
      console.log('登录成功后重跑本脚本（去掉 --drive-login）即自动读取。');
    } else {
      console.log('未到达 Google 账号选择器，当前 tab:');
      ctx.pages().forEach((p) => console.log('  ', p.url().slice(0, 100)));
    }
    await browser.close(); return;
  }

  // 已登录：输出用量
  console.log('--- URL ---\n' + page.url());
  console.log('--- 用量解析 ---');
  console.log('当前邮箱 :', u.email || '(未解析)');
  console.log('登录态   :', '✅ 已登录');
  console.log('Weekly   :', u.weekly || '(未解析)');
  console.log('5h 窗口  :', u.fiveH || '(未解析/无)');
  console.log('百分比   :', u.pcts.join(' | ') || '(未解析)');
  console.log('Resets   :', u.resets.join(' | ') || '(未解析/无)');
  console.log('--- innerText 前 1400 字（人工核对）---');
  console.log(text.slice(0, 1400));
  await browser.close(); // connectOverCDP：不断底层 Chrome
})().catch((e) => { console.error('ERR:', e.message); process.exit(1); });

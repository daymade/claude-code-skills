#!/usr/bin/env node
/**
 * Silent-degradation probe.
 *
 * Static checks (lint, typecheck, geometry assertions) cannot see three whole
 * classes of visual defect, because in each of them **nothing errors**:
 *
 *   font    A font family is declared but never shipped. computed fontFamily
 *           returns the declared name and document.fonts.check() returns true
 *           even when no @font-face exists, so both report success while every
 *           glyph renders in a fallback. Only measuring text width against a
 *           deliberately nonexistent family tells the truth — and the probe
 *           string must contain Latin characters, since CJK glyphs are
 *           full-width in every font and cannot reveal a substitution.
 *           Measuring also has to happen AFTER document.fonts.load(): a webfont
 *           is fetched only when used, so a healthy bundled fallback that this
 *           page happens not to use measures exactly like one that was never
 *           shipped. Reports five outcomes rather than pass/fail, because
 *           "bundled and working" and "never shipped" must not be conflated —
 *           acting on that confusion means deleting a fallback that works.
 *
 *   class   A component library renames its internal DOM classes on a major
 *           version. Every stylesheet rule targeting the old names silently
 *           matches nothing; components fall back to the library's stock look
 *           while the design system's own vocabulary disappears. A CSS rule
 *           that matches no element is not an error in CSS.
 *
 *   shot    A claim that something "looks wrong" is unverifiable without the
 *           pixels. This mode crops the exact element (with a little context)
 *           so a report can carry its own evidence.
 *
 * Usage:
 *   node silent_degradation_probe.mjs font  --url <url> --family "Brand Sans" [--family ...]
 *   node silent_degradation_probe.mjs class --css <file.css> --library-css <node_modules/lib/dist/lib.css>
 *   node silent_degradation_probe.mjs shot  --url <url> --select "<css>" --out <dir> [--name x] [--pad 12] [--dpr 3]
 *
 * Common flags: --browser <chrome-executable>  --viewport WxH  --wait <ms>
 *   --header-env "k: ENV_NAME" (repeatable, target origin only)
 *   --storage <playwright-storage-state.json>  --ignore-https-errors
 *
 * Exit: 0 clean · 1 degradation found · 2 invalid input / runtime failure.
 */
import { readFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import process from 'node:process';

const argv = process.argv.slice(2);
const mode = argv[0];
const flag = (n, d = null) => { const i = argv.indexOf(`--${n}`); return i > -1 ? argv[i + 1] : d; };
const flags = (n) => argv.reduce((a, v, i) => (v === `--${n}` ? [...a, argv[i + 1]] : a), []);
const has = (n) => argv.includes(`--${n}`);

process.on('uncaughtException', failRuntime);
process.on('unhandledRejection', failRuntime);

const CSS_GENERIC_FAMILIES = new Set([
  'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui',
  'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded', 'math', 'emoji',
  'fangsong',
]);
function normalizedFamily(family) {
  return family.trim().replace(/^['"]|['"]$/g, '').toLowerCase();
}

function stripCssComments(css) {
  let output = '';
  let quote = null;
  for (let index = 0; index < css.length; index += 1) {
    const char = css[index];
    const next = css[index + 1];
    if (quote) {
      output += char;
      if (char === '\\' && index + 1 < css.length) {
        output += css[index + 1];
        index += 1;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      output += char;
      continue;
    }
    if (char === '/' && next === '*') {
      index += 2;
      while (index < css.length && !(css[index] === '*' && css[index + 1] === '/')) {
        if (css[index] === '\n' || css[index] === '\r') output += css[index];
        index += 1;
      }
      continue;
    }
    output += char;
  }
  return output;
}

if (!mode || has('help') || !['font', 'class', 'shot'].includes(mode)) {
  process.stdout.write(readFileSync(new URL(import.meta.url)).toString().split('*/')[0].replace(/^\/\*\*?/, '') + '\n');
  process.exit(mode ? 2 : 0);
}

/** Resolve playwright from the audited project, never from this skill. */
async function loadPlaywright() {
  for (const base of [process.cwd(), join(process.cwd(), '..'), join(process.cwd(), '../..')]) {
    for (const p of ['node_modules/playwright/index.js', '.ds-sync/node_modules/playwright/index.js']) {
      const full = join(base, p);
      if (existsSync(full)) {
        const mod = await import(`file://${full}`);
        return mod.default ?? mod;
      }
    }
  }
  try { return (await import('playwright')).default ?? (await import('playwright')); } catch {}
  process.stderr.write('playwright not resolvable from the audited project. Run from the project root, or skip this probe and report it as omitted.\n');
  process.exit(2);
}

async function openPage() {
  const url = flag('url');
  if (!url) { process.stderr.write('--url is required\n'); process.exit(2); }
  let targetOrigin;
  try { targetOrigin = new URL(url).origin; }
  catch { process.stderr.write('invalid --url\n'); process.exit(2); }
  const extraHeaders = {};
  if (argv.some((value) => value === '--header' || value.startsWith('--header='))) {
    process.stderr.write('--header is disabled; use --header-env for every header value\n');
    process.exit(2);
  }
  if (argv.some((value) => value.startsWith('--header-env='))) {
    process.stderr.write('invalid --header-env; pass "name: ENV_NAME" as the next argument\n');
    process.exit(2);
  }
  for (const spec of flags('header-env')) {
    const separator = typeof spec === 'string' ? spec.indexOf(':') : -1;
    const name = separator > 0 ? spec.slice(0, separator).trim().toLowerCase() : '';
    const envName = separator > 0 ? spec.slice(separator + 1).trim() : '';
    if (
      !/^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/.test(name)
      || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(envName)
    ) {
      process.stderr.write('invalid --header-env (expected "name: ENV_NAME")\n');
      process.exit(2);
    }
    if (!(envName in process.env)) {
      process.stderr.write(`missing environment variable for --header-env: ${envName}\n`);
      process.exit(2);
    }
    extraHeaders[name] = process.env[envName];
  }
  const [w, h] = (flag('viewport', '1440x900')).split('x').map(Number);
  const dpr = Number(flag('dpr', '2'));
  if (![w, h, dpr].every(Number.isFinite) || w <= 0 || h <= 0 || dpr <= 0) {
    process.stderr.write('--viewport must be positive WxH and --dpr must be positive\n');
    process.exit(2);
  }
  const pw = await loadPlaywright();
  const browser = await pw.chromium.launch({ executablePath: flag('browser') || undefined });
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: has('ignore-https-errors'),
    viewport: { width: w, height: h },
    deviceScaleFactor: dpr,
    storageState: flag('storage') || undefined,
  });
  if (Object.keys(extraHeaders).length) {
    await ctx.route('**/*', async (route) => {
      const requestHeaders = { ...route.request().headers() };
      for (const name of Object.keys(extraHeaders)) delete requestHeaders[name];
      let requestOrigin = null;
      try { requestOrigin = new URL(route.request().url()).origin; } catch {}
      if (requestOrigin === targetOrigin) {
        Object.assign(requestHeaders, extraHeaders);
        // route.continue() applies header overrides to automatic redirects too,
        // which can forward a target-origin credential to another origin before
        // interception runs again. Fetch exactly one hop, then fulfill it so the
        // browser issues any redirect as a fresh, independently filtered request.
        const response = await route.fetch({ headers: requestHeaders, maxRedirects: 0 });
        await route.fulfill({ response });
      } else {
        await route.continue({ headers: requestHeaders });
      }
    });
  }
  const page = await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle' });
  } catch (error) {
    await browser.close().catch(() => {});
    process.stderr.write(`probe navigation failed: ${redactUrlsInText(error?.message || String(error))}\n`);
    process.exit(2);
  }
  await page.waitForTimeout(Number(flag('wait', '1200')));
  return { browser, page };
}

function failRuntime(error) {
  process.stderr.write(`probe runtime failed: ${redactUrlsInText(error?.stack || error?.message || String(error))}\n`);
  process.exit(2);
}

function redactUrlsInText(value) {
  return String(value).replace(/\b(?:https?|file|data):[^\s"'<>]+/gi, redactUrlForEvidence);
}

function redactUrlForEvidence(value) {
  try {
    const parsed = new URL(String(value));
    if (parsed.protocol === 'data:') return 'data:<redacted>';
    if (parsed.protocol === 'file:') return 'file:///<redacted-path>';
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return '<redacted-target>';
    const pathLabel = parsed.pathname === '/' ? '/' : '/<redacted-path>';
    const queryKeys = [...new Set(parsed.searchParams.keys())];
    const query = queryKeys.length
      ? `?${queryKeys.map((key) => `${encodeURIComponent(key)}=<redacted>`).join('&')}`
      : '';
    return `${parsed.origin}${pathLabel}${query}${parsed.hash ? '#<redacted-fragment>' : ''}`;
  } catch {
    return '<redacted-target>';
  }
}

// ---------------------------------------------------------------- font
if (mode === 'font') {
  const families = flags('family');
  if (!families.length) { process.stderr.write('at least one --family is required\n'); process.exit(2); }
  const weight = flag('weight', '400');
  const { browser, page } = await openPage();
  const result = await page.evaluate(async ({ fams, weight: wt }) => {
    // Latin characters are mandatory: CJK is full-width in every font, so an
    // all-CJK probe measures identical widths whatever font actually renders.
    const PROBE = 'Handgloves 0123456789 幅';
    const measure = (family) => {
      const c = document.createElement('canvas').getContext('2d');
      c.font = `${wt} 16px ${family}`;
      return c.measureText(PROBE).width;
    };

    // A webfont is fetched only when something on the page uses it. Measuring a
    // bundled-but-not-yet-used @font-face therefore returns the fallback width
    // and looks exactly like a font that was never shipped. Ask for each family
    // explicitly and wait, or this probe condemns healthy fallbacks.
    const loadErrors = {};
    await Promise.all(fams.map(async (f) => {
      try { await document.fonts.load(`${wt} 16px "${f}"`, PROBE); }
      catch (e) { loadErrors[f] = String(e).slice(0, 120); }
    }));
    await document.fonts.ready;

    const sentinel = measure('"NoSuchFamily__PROBE__"');
    return {
      fontFaceRules: Array.from(document.styleSheets).flatMap((s) => {
        try { return Array.from(s.cssRules || []); } catch { return []; }
      }).filter((r) => r.constructor.name === 'CSSFontFaceRule').length,
      documentFonts: document.fonts.size,
      sentinelWidth: sentinel,
      weightProbed: wt,
      families: fams.map((f) => {
        const w = measure(`"${f}"`);
        // Does the page itself ship this family, or is it merely present on
        // this machine? A face that renders only because the auditor's OS has
        // it will fall back on every machine that does not — the classic
        // "works for the team, broken for the customer" case.
        const faces = Array.from(document.fonts)
          .filter((ff) => ff.family.replace(/^["']|["']$/g, '') === f);
        return {
          family: f,
          width: w,
          // check() is reported for contrast only — it returns true with no
          // @font-face at all, which is exactly the false positive to expose.
          checkSaysAvailable: document.fonts.check(`${wt} 16px "${f}"`),
          actuallyRenders: Math.abs(w - sentinel) > 0.5,
          shippedByPage: faces.length > 0,
          faceStatus: faces.map((ff) => `${ff.weight}:${ff.status}`).join(' ') || null,
          loadError: loadErrors[f] || null,
        };
      }),
    };
  }, { fams: families, weight });
  await browser.close();
  // Five distinct outcomes. Only two of them are defects, and conflating the
  // healthy-bundled case with the never-shipped case is worse than not checking
  // at all: it tells the reader to delete a fallback that works.
  const platformGeneric = result.families.filter((f) => CSS_GENERIC_FAMILIES.has(normalizedFamily(f.family)));
  const custom = result.families.filter((f) => !CSS_GENERIC_FAMILIES.has(normalizedFamily(f.family)));
  const healthy = custom.filter((f) => f.actuallyRenders && f.shippedByPage);
  const hostOnly = custom.filter((f) => f.actuallyRenders && !f.shippedByPage);
  const brokenAsset = custom.filter((f) => !f.actuallyRenders && f.shippedByPage);
  const absent = custom.filter((f) => !f.actuallyRenders && !f.shippedByPage);
  process.stdout.write(JSON.stringify({ mode: 'font', ...result,
    platformGeneric: platformGeneric.map((f) => f.family),
    healthy: healthy.map((f) => f.family),
    hostProvidedOnly: hostOnly.map((f) => f.family),
    declaredButUnusable: brokenAsset.map((f) => f.family),
    absentStackEntries: absent.map((f) => f.family) }, null, 2) + '\n');
  if (hostOnly.length) {
    process.stderr.write(`\n${hostOnly.length} family/families render here but are NOT shipped by the page:\n`
      + hostOnly.map((f) => `  - ${f.family}`).join('\n')
      + `\nThey resolve only because this machine happens to have them installed. Any user without\n`
      + `them gets a fallback, and no probe run on a developer machine will ever reveal it.\n`
      + `Ship the face with the app, or drop it from the stack.\n`);
  }
  if (brokenAsset.length) {
    process.stderr.write(`\n${brokenAsset.length} family/families are declared by the page but still do not render:\n`
      + brokenAsset.map((f) => `  - ${f.family} (faces ${f.faceStatus}`
        + `${f.loadError ? `; load error ${f.loadError}` : ''})`).join('\n')
      + `\nThe @font-face exists, so this is a broken asset — a 404, a bad path, a format the\n`
      + `browser rejected, or a weight that was never built. Check the network panel.\n`);
  }
  if (absent.length) {
    process.stderr.write(`\n${absent.length} stack entry/entries neither ship nor resolve on this host:\n`
      + absent.map((f) => `  - ${f.family} (width ${f.width} === sentinel ${result.sentinelWidth}`
        + `${f.checkSaysAvailable ? '; document.fonts.check() reported true — a false positive' : ''})`).join('\n')
      + `\nThese contribute nothing on this machine. They may still be intentional (a platform face\n`
      + `for an OS you are not testing on) — confirm before deleting, and note which OS you ran on.\n`);
  }
  process.exit(hostOnly.length || brokenAsset.length ? 1 : 0);
}

// --------------------------------------------------------------- class
if (mode === 'class') {
  const cssPath = flag('css'), libPath = flag('library-css');
  if (!cssPath || !libPath) { process.stderr.write('--css and --library-css are required\n'); process.exit(2); }
  const own = stripCssComments(readFileSync(resolve(cssPath), 'utf8'));
  const lib = stripCssComments(readFileSync(resolve(libPath), 'utf8'));
  const prefix = flag('prefix', 'ant');
  const referenced = [...new Set([...own.matchAll(new RegExp(`\\.(${prefix}-[a-z0-9-]+)`, 'g'))].map((m) => m[1]))].sort();
  const rows = referenced.map((name) => {
    const inLib = (lib.match(new RegExp(`\\.${name}(?![a-z0-9-])`, 'g')) || []).length;
    return { name, occurrencesInLibrary: inLib, dead: inLib === 0 };
  });
  const dead = rows.filter((r) => r.dead);
  process.stdout.write(JSON.stringify({ mode: 'class', referenced: rows.length, dead: dead.map((d) => d.name), rows }, null, 2) + '\n');
  if (dead.length) {
    process.stderr.write(`\n${dead.length} of ${rows.length} referenced class name(s) do not exist in the installed library:\n`
      + dead.map((d) => `  - .${d.name}`).join('\n')
      + `\nRules targeting them match nothing and fail silently — the component keeps the library's stock look.\n`
      + `Check the library's changelog for renames, then re-anchor each rule.\n`
      + `Note: a dead name inside a selector GROUP whose other branch still matches costs nothing; confirm before editing.\n`);
    process.exit(1);
  }
  process.exit(0);
}

// ---------------------------------------------------------------- shot
if (mode === 'shot') {
  const sel = flag('select'), outDir = flag('out');
  if (!sel || !outDir) { process.stderr.write('--select and --out are required\n'); process.exit(2); }
  mkdirSync(resolve(outDir), { recursive: true });
  const pad = Number(flag('pad', '12'));
  const name = flag('name', 'evidence');
  const { browser, page } = await openPage();
  const box = await page.locator(sel).first().boundingBox({ timeout: 5000 }).catch(() => null);
  if (!box) { await browser.close(); process.stderr.write(`selector matched nothing: ${sel}\n`); process.exit(2); }
  const vp = page.viewportSize();
  const clip = {
    x: Math.max(0, box.x - pad), y: Math.max(0, box.y - pad),
    width: Math.min(vp.width - Math.max(0, box.x - pad), box.width + pad * 2),
    height: box.height + pad * 2,
  };
  const file = join(resolve(outDir), `${name}.png`);
  await page.screenshot({ path: file, clip });
  await browser.close();
  // Report CSS px, not device px: a DPR-2 capture is twice the pixel count and
  // reporting that number as page height has produced false "20 screens long"
  // findings. The image file is larger; the layout is not.
  process.stdout.write(JSON.stringify({
    mode: 'shot', file, cssPx: { w: Math.round(clip.width), h: Math.round(clip.height) },
    note: 'dimensions are CSS px; the PNG is deviceScaleFactor times larger',
  }, null, 2) + '\n');
  process.exit(0);
}

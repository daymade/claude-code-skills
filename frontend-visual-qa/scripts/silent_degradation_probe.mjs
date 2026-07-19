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
 *   --header "k: v" (repeatable)  --storage <playwright-storage-state.json>
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
  const pw = await loadPlaywright();
  const [w, h] = (flag('viewport', '1440x900')).split('x').map(Number);
  const browser = await pw.chromium.launch({ executablePath: flag('browser') || undefined });
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: w, height: h },
    deviceScaleFactor: Number(flag('dpr', '2')),
    storageState: flag('storage') || undefined,
    extraHTTPHeaders: Object.fromEntries(flags('header').map((s) => {
      const i = s.indexOf(':'); return [s.slice(0, i).trim(), s.slice(i + 1).trim()];
    })),
  });
  const page = await ctx.newPage();
  const url = flag('url');
  if (!url) { process.stderr.write('--url is required\n'); process.exit(2); }
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(Number(flag('wait', '1200')));
  return { browser, page };
}

// ---------------------------------------------------------------- font
if (mode === 'font') {
  const families = flags('family');
  if (!families.length) { process.stderr.write('at least one --family is required\n'); process.exit(2); }
  const { browser, page } = await openPage();
  const result = await page.evaluate((fams) => {
    // Latin characters are mandatory: CJK is full-width in every font, so an
    // all-CJK probe measures identical widths whatever font actually renders.
    const PROBE = 'Handgloves 0123456789 幅';
    const measure = (family) => {
      const c = document.createElement('canvas').getContext('2d');
      c.font = `16px ${family}`;
      return c.measureText(PROBE).width;
    };
    const sentinel = measure('"NoSuchFamily__PROBE__"');
    return {
      fontFaceRules: Array.from(document.styleSheets).flatMap((s) => {
        try { return Array.from(s.cssRules || []); } catch { return []; }
      }).filter((r) => r.constructor.name === 'CSSFontFaceRule').length,
      documentFonts: document.fonts.size,
      sentinelWidth: sentinel,
      families: fams.map((f) => {
        const w = measure(`"${f}"`);
        // Does the page itself ship this family, or is it merely present on
        // this machine? A face that renders only because the auditor's OS has
        // it will fall back on every machine that does not — the classic
        // "works for the team, broken for the customer" case.
        const shipped = Array.from(document.fonts).some((ff) => ff.family.replace(/^["']|["']$/g, '') === f);
        return {
          family: f,
          width: w,
          // check() is reported for contrast only — it returns true with no
          // @font-face at all, which is exactly the false positive to expose.
          checkSaysAvailable: document.fonts.check(`16px "${f}"`),
          actuallyRenders: Math.abs(w - sentinel) > 0.5,
          shippedByPage: shipped,
        };
      }),
    };
  }, families);
  await browser.close();
  const dead = result.families.filter((f) => !f.actuallyRenders);
  const hostOnly = result.families.filter((f) => f.actuallyRenders && !f.shippedByPage);
  process.stdout.write(JSON.stringify({ mode: 'font', ...result,
    degraded: dead.map((f) => f.family),
    hostProvidedOnly: hostOnly.map((f) => f.family) }, null, 2) + '\n');
  if (hostOnly.length) {
    process.stderr.write(`\n${hostOnly.length} family/families render here but are NOT shipped by the page:\n`
      + hostOnly.map((f) => `  - ${f.family}`).join('\n')
      + `\nThey resolve only because this machine happens to have them installed. Any user without\n`
      + `them gets a fallback, and no probe run on a developer machine will ever reveal it.\n`
      + `Ship the face with the app, or drop it from the stack.\n`);
  }
  if (dead.length) {
    process.stderr.write(`\n${dead.length} declared family/families never render; every glyph falls back:\n`
      + dead.map((f) => `  - ${f.family} (width ${f.width} === sentinel ${result.sentinelWidth}`
        + `${f.checkSaysAvailable ? '; document.fonts.check() reported true — a false positive' : ''})`).join('\n')
      + `\nShip the font with the app, or reduce the stack to families the host actually has.\n`);
    process.exit(1);
  }
  process.exit(0);
}

// --------------------------------------------------------------- class
if (mode === 'class') {
  const cssPath = flag('css'), libPath = flag('library-css');
  if (!cssPath || !libPath) { process.stderr.write('--css and --library-css are required\n'); process.exit(2); }
  const own = readFileSync(resolve(cssPath), 'utf8');
  const lib = readFileSync(resolve(libPath), 'utf8');
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

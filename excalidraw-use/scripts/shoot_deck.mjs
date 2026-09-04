#!/usr/bin/env node
/**
 * Screenshot every slide of a Vite/React slide deck to PNG, with presenter-only
 * chrome hidden and staged reveals fully expanded.
 *
 * Thin glue over puppeteer; the deck-specific parts are the slide-id extraction,
 * the two fragment-advance strategies, and the chrome hiding.
 *
 * Usage:
 *   node shoot_deck.mjs --index <src/slides/index.ts> --url <base-url> --out <dir>
 *                       [--advance pdf|keys] [--width 1920] [--height 1080]
 *
 * --advance pdf   the deck's Deck component honours a ?pdf=1 query that jumps each
 *                 slide to its final fragment.
 * --advance keys  (default) no such mode: press ArrowRight fragmentCount times.
 *                 The deck's own next() advances the fragment while
 *                 fragmentIndex < fragmentCount and only then moves to the next
 *                 slide, so exactly fragmentCount presses land on the last
 *                 fragment without overshooting.
 *
 * Never mix the two: under ?pdf=1 the fragment index is already at its maximum,
 * so an extra ArrowRight moves to the next slide and you silently shoot the
 * wrong content.
 *
 * Serve the deck's built output over http (`python3 -m http.server`, or the
 * project's own preview command). Do not point this at a dev server: see
 * references/deck_screenshot_pitfalls.md for why a stale build is the failure
 * that costs the most time here.
 */
import puppeteer from 'puppeteer'
import { readFileSync, mkdirSync } from 'fs'

const args = process.argv.slice(2)
const arg = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 ? args[i + 1] : fallback
}
const INDEX = arg('--index')
const BASE = arg('--url')
const OUT = arg('--out')
const ADVANCE = arg('--advance', 'keys')
const WIDTH = Number(arg('--width', '1920'))
const HEIGHT = Number(arg('--height', '1080'))
// Unrevealed fragments are loud but non-fatal by default: a deck may legitimately
// keep a .fragment hidden, and a check that fails on healthy input teaches people
// to bypass it. Pass --strict when this runs inside a pipeline that must stop.
const STRICT = args.includes('--strict')

if (!INDEX || !BASE || !OUT) {
  console.error('usage: shoot_deck.mjs --index <index.ts> --url <base> --out <dir> [--advance pdf|keys]')
  process.exit(2)
}
if (!['pdf', 'keys'].includes(ADVANCE)) {
  console.error(`--advance must be "pdf" or "keys", got ${ADVANCE}`)
  process.exit(2)
}

// Slide registries in these decks look like:
//   { id: 'intro', component: S01_Intro, fragmentCount: 3 },
const source = readFileSync(INDEX, 'utf-8')
const slides = []
for (const m of source.matchAll(/\{\s*id:\s*'([^']+)'([^}]*)\}/g)) {
  const frag = /fragmentCount:\s*(\d+)/.exec(m[2])
  slides.push({ id: m[1], frags: frag ? Number(frag[1]) : 0 })
}
if (slides.length === 0) {
  console.error(`no slides found in ${INDEX} — expected entries shaped like { id: '...' }`)
  process.exit(2)
}
mkdirSync(OUT, { recursive: true })
console.log(`${slides.length} slides (${slides.filter(s => s.frags).length} with fragments), advance=${ADVANCE}`)

// Presenter-only furniture, hidden before each shot. The class names cover the
// common cases; the geometry pass below catches the ones built with inline
// styles and no class at all, which is why both halves are needed.
const CHROME_CSS = `.presenter-note,.slide-number,.deck-progress,ul.keystrokes{display:none !important}`

function hideInlineChrome() {
  const vw = window.innerWidth
  const vh = window.innerHeight
  let hidden = 0
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el)
    if (cs.display === 'none') continue
    const r = el.getBoundingClientRect()
    // A full-width bar pinned to the bottom edge: agenda/timeline strips.
    if (cs.position === 'fixed' && r.width >= vw * 0.9 && r.height <= 90 && r.bottom >= vh - 2) {
      el.style.setProperty('display', 'none', 'important')
      hidden++
      continue
    }
    // A small "3 / 14" badge, wherever it sits.
    const text = (el.innerText || '').trim()
    if (r.width < 220 && r.height < 60 && el.children.length <= 2 && /^\d+\s*[/／]\s*\d+$/.test(text)) {
      el.style.setProperty('display', 'none', 'important')
      hidden++
    }
  }
  return hidden
}

const browser = await puppeteer.launch({ headless: true })
const page = await browser.newPage()
await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 })

const failures = []
const unrevealed = []
let hiddenTotal = 0

for (let i = 0; i < slides.length; i++) {
  const { id, frags } = slides[i]
  const n = String(i + 1).padStart(2, '0')
  try {
    // Full navigation per slide, not a hash change: a hash change re-renders the
    // slide but leaves the fragment index where it was, so fragment-bearing
    // slides shoot in their pre-reveal state.
    const query = ADVANCE === 'pdf' ? '?pdf=1' : ''
    await page.goto(`${BASE}${query}#${id}`, { waitUntil: 'networkidle0', timeout: 60000 })
    await new Promise(r => setTimeout(r, 700))

    if (ADVANCE === 'keys') {
      for (let f = 0; f < frags; f++) {
        await page.keyboard.press('ArrowRight')
        await new Promise(r => setTimeout(r, 320))
      }
      // Decks often show an on-screen badge for each keypress; the common
      // configuration lingers ~2s then fades ~0.6s. Wait it out or the badges
      // land in the screenshot.
      await new Promise(r => setTimeout(r, frags ? 2900 : 400))
    } else {
      await new Promise(r => setTimeout(r, 400))
    }

    await page.addStyleTag({ content: CHROME_CSS })
    hiddenTotal += await page.evaluate(hideInlineChrome)
    await new Promise(r => setTimeout(r, 250))
    await page.evaluate(() => document.fonts.ready)

    // Fragments that never revealed stay in the DOM at opacity 0, so any check
    // based on text content reports them as present while the picture is blank.
    // Measure what actually renders.
    const invisible = await page.evaluate(() =>
      [...document.querySelectorAll('.fragment')]
        .filter(e => parseFloat(getComputedStyle(e).opacity) < 0.9)
        .map(e => (e.innerText || '').replace(/\s+/g, ' ').slice(0, 40))
    )
    if (invisible.length) {
      unrevealed.push(`${n}-${id}: ${invisible.length} still hidden -> ${invisible.join(' | ')}`)
    }

    await page.screenshot({ path: `${OUT}/${n}-${id}.png`, type: 'png' })
    process.stdout.write(`\r  ${invisible.length ? '!' : 'ok'} ${i + 1}/${slides.length} #${id}          `)
  } catch (e) {
    failures.push(`${n}-${id}: ${e.message}`)
    process.stdout.write(`\r  FAIL ${i + 1}/${slides.length} #${id}          \n`)
  }
}
await browser.close()

console.log(`\n${slides.length - failures.length}/${slides.length} captured, ${hiddenTotal} inline chrome element(s) hidden -> ${OUT}`)
if (failures.length) {
  console.log('failed:')
  for (const f of failures) console.log('   ' + f)
}
if (unrevealed.length) {
  console.log(`WARNING: ${unrevealed.length} slide(s) have fragments that never revealed.`)
  console.log('Those screenshots are missing content. Most often the served build predates')
  console.log('the ?pdf=1 support in the source — rebuild and serve the fresh output.')
  for (const u of unrevealed) console.log('   ' + u)
  if (STRICT) console.log('(--strict: exiting non-zero)')
} else {
  console.log('all .fragment elements rendered visible (opacity check)')
}
process.exit(failures.length || (STRICT && unrevealed.length) ? 1 : 0)

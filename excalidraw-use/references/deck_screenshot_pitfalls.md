# Screenshotting a slide deck without silently losing content

Every failure below produces a *plausible-looking* screenshot. That is what makes
them expensive: nothing errors, the file is written, and the missing content is
only visible if you open the picture and know what should be there.

## 1. A stale build makes a source feature disappear

The most expensive one, because the evidence points at your script.

A deck's `dist/` is a build artifact. If it was produced before a feature landed
in `src/`, the served page does not have that feature — but the *source* you are
reading does. So you read `Deck.tsx`, see it handles `?pdf=1`, pass `--advance pdf`,
and the fragments never advance. Everything you can see says the code is there.

Compare the timestamps:

```bash
ls -la <deck>/dist/assets/*.js <deck>/src/components/Deck.tsx
```

If the source is newer, rebuild. Build to a directory **outside** the project so
you do not overwrite an artifact someone else may be relying on:

```bash
npx vite build --outDir /tmp/deck-dist --emptyOutDir
```

Observed instance: a `dist/` built at 05:21 and a `Deck.tsx` modified at 10:10 the
same day. The five-hour gap was the whole bug. Six slides captured with their
reveals collapsed, and the first two rounds of debugging went into the
screenshot script, which was fine.

## 2. `innerText` is not a proxy for what renders

The instrument that made the above take twice as long as it should have.

Animation libraries commonly mount every fragment and animate `opacity`. So an
unrevealed fragment **is in the DOM with its full text**, and:

```js
document.body.innerText   // shows all four years — looks correct
```

while the screenshot shows one. A check built on text content confirms exactly
the thing that is broken.

Measure what renders:

```js
[...document.querySelectorAll('.fragment')]
  .map(e => getComputedStyle(e).opacity)   // "1" vs "0" — this one is honest
```

`shoot_deck.mjs` runs this after every slide and reports anything still at
opacity 0. The general form of the lesson: when checking whether something is
*visible*, a check that reads the DOM's text answers a different question and
answers it confidently.

## 3. Hash navigation leaves the fragment index behind

Navigating between slides with `window.location.hash = id` re-renders the slide
but does not reset or advance the fragment state the way a fresh load does, so
fragment-bearing slides capture in their pre-reveal state.

Do a full `page.goto()` per slide. It is slower and it is correct.

## 4. The two advance modes are mutually exclusive

- `?pdf=1`, where supported, sets the fragment index to its maximum on slide change.
- Key presses advance it one at a time; the deck's own `next()` moves to the next
  slide once the index is already at `fragmentCount`.

So pressing keys *while* in pdf mode overshoots into the next slide — and the
screenshot is of a real slide, just the wrong one. Grep the deck's `Deck`
component for `pdf` and pick one mode.

## 5. Key-press indicators land in the picture

Presentation decks often visualise keystrokes on screen. A common configuration
lingers ~2000 ms then fades ~600 ms, so a screenshot taken 500 ms after the last
`ArrowRight` catches the badges.

`shoot_deck.mjs` waits ~2900 ms after the last press on fragment-bearing slides.
If a deck configures a longer linger, raise it — check the deck's own
`KeystrokeVisualizer.enable({...})` call or equivalent.

## 6. Presenter-only furniture

What belongs to the presenter, not the audience, and should not reach a canvas:

- speaker-note strips (often `.presenter-note`, with badge/copy sub-elements)
- slide numbers (`.slide-number`, or an inline-styled `N / M` badge anywhere)
- progress bars (`.deck-progress`)
- agenda/timeline strips pinned to the bottom edge — frequently **inline-styled
  with no class at all**

The last one is why class selectors alone are not enough. `shoot_deck.mjs` uses
both: a stylesheet for the known classes, plus a geometry pass that hides any
`position: fixed` full-width bar sitting on the bottom edge and any small element
whose entire text matches `N / M`.

When adapting to a new deck, find the selectors instead of guessing — dump
candidates and read their `outerHTML`:

```js
[...document.querySelectorAll('body *')]
  .filter(el => {
    const r = el.getBoundingClientRect()
    return r.bottom > innerHeight - 60 && r.width > 1500 && r.height < 90
  })
  .map(el => el.outerHTML.slice(0, 200))
```

## 7. Deduplication can hide a fragment bug

If two adjacent slides differ only by a reveal, and the reveals never happened,
the two screenshots are **byte-identical**. Content-hash dedupe then silently
drops one, and the count comes out one short.

Treat an unexpected dedupe between adjacent slides as a symptom of §1, not as a
tidy result. Observed: a 30-slide deck produced 29 unique images; after the
rebuild it produced 30.

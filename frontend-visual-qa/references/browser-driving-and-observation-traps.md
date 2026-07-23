# Browser-Driving And Observation Traps

Failure modes that belong to *the auditor*, not to the page. Each one makes a
healthy page look broken or a broken page look healthy, and every one of them has
produced a wrong verdict: at best a wasted round, at worst an "fix" applied to
code that was already correct.

Read this before driving a real browser, and again whenever an observation
surprises you.

## Contents

- [1. "Clicked, nothing happened" is not evidence of a broken feature](#1-clicked-nothing-happened-is-not-evidence-of-a-broken-feature)
- [2. The page you are looking at may not be the page you just changed](#2-the-page-you-are-looking-at-may-not-be-the-page-you-just-changed)
- [3. `file://` is not drivable by browser-extension tooling](#3-file-is-not-drivable-by-browser-extension-tooling)
- [4. A headless screenshot is a viewport, not the page](#4-a-headless-screenshot-is-a-viewport-not-the-page)
- [5. Resizing a headless window is not device emulation](#5-resizing-a-headless-window-is-not-device-emulation)
- [6. Default state hides whole categories of defect](#6-default-state-hides-whole-categories-of-defect)
- [7. Mid-run state is not final state](#7-mid-run-state-is-not-final-state)
- [8. A hidden tab defers media loads — the request is never sent](#8-a-hidden-tab-defers-media-loads--the-request-is-never-sent)
- [9. Virtual time fast-forwards timers, not I/O](#9-virtual-time-fast-forwards-timers-not-io)
- [10. `--dump-dom` captures at load, not after your injected test](#10---dump-dom-captures-at-load-not-after-your-injected-test)
- [11. A media stall may be the test server: Range support × moov position](#11-a-media-stall-may-be-the-test-server-range-support--moov-position)
- [12. Calibrate capture and inspect the minimum surface](#12-calibrate-capture-and-inspect-the-minimum-surface)

---

## 1. "Clicked, nothing happened" is not evidence of a broken feature

The most expensive mistake in this list. A click that produces no visible change
has at least four causes, and only one of them is "the feature is broken":

1. **The click missed.** Inline targets (a `<span>` inside a paragraph, an icon,
   a short link) are a few pixels tall. A coordinate derived from a screenshot is
   often just outside them, and the click silently lands on the parent.
2. **The handler threw.** Visible only in the console.
3. **The element was replaced** between the screenshot and the click (re-render,
   HMR reload, async data arrival), so the coordinate now points at nothing.
4. The feature really is broken.

**Order of investigation — cheapest and most-likely first:**

```
1. Read the console for errors      → rules out cause 2
2. Re-target by element reference   → rules out causes 1 and 3
   (resolve the element by role/text/accessible name, click that reference,
    not an x/y pair)
3. Only now suspect the code
```

Skipping to step 3 leads to editing code that was already correct. Prefer
reference-based clicking over coordinates for anything smaller than a large
button — coordinates are for canvas, maps, and drag paths, where no element
reference exists.

## 2. The page you are looking at may not be the page you just changed

For a source-change or deployment claim, visual verification is a chain:

    source edit → built artifact → deployed runtime → exact URL → inspected pixels

Each arrow can be stale while the previous step is correct. A passing test or
correct dev server proves neither the deployed runtime nor the user-supplied
URL. Preserve its full query and fragment in browser memory, but persist only
URLs with path/query values/the entire fragment redacted, plus stable
target-string fingerprints and query-key lists for the requested URL, redirects,
and final URL. Hash rendered labels and scrub target-derived values from errors
or metadata before persistence. Another port or local server changes the target.

Other targets use other identities:

- single file/image: canonical path + content hash + actual renderer;
- multi-resource HTML/deck: canonical entry + authoritative resource manifest
  or dependency-closure digest + renderer;
- native app: installed artifact fingerprint/code signature + build/version +
  running process/window + renderer route.

These identities prove what was inspected. They do not require a deployment
chain when the claim is only “this exact target currently renders this way.”
The bundled layout sweep computes the web target-string fingerprint and
single-file byte hash only; it cannot infer a resource-closure or native identity.

For authorized target mutation, collect identity before and after. Prefer two
independent signals where the project exposes them:

- **runtime identity** from the canonical status/lifecycle command: source
  revision or working-tree fingerprint, release/image/container identity, and
  whether it reports stale;
- **data-plane identity** from the exact target: assets mapped to an expected
  manifest, a release header/version endpoint, or a visible build stamp.

If they do not match the expected source, the **source-fix closure** is **partial
— source fixed, verification target stale** and delivery is mismatched. The
older target's current-render verdict remains independently scoped to what was
actually inspected. Source-edit permission does not authorize target mutation.
Only separately authorized target mutation may run the named canonical
lifecycle; if ownership is unresolved, the mutation path is blocked. If no
identity mapping exists, report delivery identity unprovable while keeping the
current-render visual verdict scoped to what was actually observed.

Browsers cache aggressively, and **`file://` is cached too** — reloading the tab
after editing the file frequently re-renders the *old* build. This produces the
worst class of QA error: "I fixed it, but the screenshot still shows the bug",
which sends you chasing a phantom.

Two habits remove it:

- **Prefer a cache-disabled reload or fresh context.** Append a changing query
  only when the project declares it semantically inert; preserve the original
  query/fragment and make the final evidence pass on the original exact URL.
- **Use a visible freshness anchor as a cue, never identity proof.** Check the
  version/build/generation stamp before judging content, then corroborate it
  against the release contract and runtime/manifest mapping.

The anchor has to be one you actually keep current. A stamp that is updated in
one place (say, an on-page badge) but not another (the `<title>`) creates a
second-order trap: the reader checks the *stale* one, concludes "this is the old
version", and dismisses a change that did ship. If an artifact carries a version
in more than one place, they must be written together.

Record this state from the rendered page:

```js
() => ({
  href: location.href,
  title: document.title,
  h1: document.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim() || null,
  inner: [innerWidth, innerHeight],
  outer: [outerWidth, outerHeight],
  clientWidth: document.documentElement.clientWidth,
  scrollWidth: document.documentElement.scrollWidth,
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  visualViewport: visualViewport
    ? [visualViewport.width, visualViewport.height, visualViewport.scale]
    : null,
  dpr: devicePixelRatio,
  metaViewport: document.querySelector('meta[name="viewport"]')?.content || null,
})
```

Compare outerWidth, innerWidth, visualViewport, and clientWidth before blaming
CSS for blank space or mobile layout. Reset stale zoom/device emulation and
re-capture after display or scale changes. Restore the user's expected viewport
when finished.

## 3. `file://` is not drivable by browser-extension tooling

Extension-based browser automation generally cannot navigate to `file://` URLs
(the extension has no host permission for the scheme). Headless CLI browsers
*can* open `file://`, so a local artifact is inspectable but not necessarily
*interactive* through the same channel.

When an audit needs real interaction on a local file, serve it only under
explicit isolated-diagnostic authority:

```bash
# from the artifact's directory
python3 -m http.server <port> --bind 127.0.0.1
# then drive http://127.0.0.1:<port>/<artifact>.html
```

One caveat: this server is fine for pages, scripts, and images, but it does **not**
support HTTP Range requests — a page containing `<video>` can stall on it while
everything else loads (see trap 11 before concluding the player is broken).

Serving over HTTP also removes a second class of confusion: `file://` has
distinct CORS behavior, so a page that fetches anything at runtime behaves
differently under the two schemes. State which scheme the evidence came from.

## 4. A headless screenshot is a viewport, not the page

`--window-size=W,H` sets the **viewport**; the screenshot is that rectangle.
Content below `H` is not captured — it is not "the full page scaled down". A tall
page screenshotted at a normal height silently drops everything past the fold,
and a section audited that way was never audited at all.

Three ways out, in order of preference:

1. **Isolate the region** — render a copy of the artifact with the other
   sections hidden, then screenshot at a normal viewport. This preserves
   realistic `vh` units and scroll containers, so what you see matches what a
   user sees.
2. **Segment** — screenshot at a normal height, scroll, repeat, and inspect the
   segments.
3. **One tall viewport** — simplest, but distorts anything sized in `vh` or any
   internal `max-height` scroll container: a panel that scrolls in reality will
   appear fully expanded, so scroll-dependent defects become invisible.

Also note anchors: navigating to `#section` does not scroll a headless capture
into view the way it does interactively. Don't assume the anchor took.

## 5. Resizing a headless window is not device emulation

A narrow `--window-size` triggers width-based media queries, which is enough to
check that a breakpoint's layout rules fire. It is **not** mobile emulation: no
device pixel ratio, no touch flags, and — critically — no check of whether the
document declares a viewport meta tag at all.

Consequence: a page can look perfect at a 390px-wide headless window and still be
unusable on a real phone, because without `<meta name="viewport">` the device
renders it at desktop width and scales it down. Width-resize testing cannot
detect that class of defect; a real emulation profile (or the bundled sweep,
which asserts the meta tag and effective-viewport agreement) can.

State which one produced your evidence. "Checked at 560px" and "checked on a
mobile profile" are different claims.

## 6. Default state hides whole categories of defect

A screenshot captures one state: loaded, idle, mouse-driven, default user
preferences. Defects living in the *other* states survive every visual pass:

| State | Defect it hides | How to surface it |
|---|---|---|
| Keyboard focus | Focus ring suppressed (`outline:none`) with no replacement — element is focusable but the user cannot see where they are | Tab through and screenshot; or audit stylesheets for `outline:none` with zero `:focus`/`:focus-visible` rules |
| Reduced-motion preference | Animation with no degraded path | Check for an `@media (prefers-reduced-motion: reduce)` block; emulate the preference |
| Narrow viewport, selected item | Only the *selected* item carries a border/background, so in a wrapped horizontal layout it becomes a raised outlier and rows stop aligning | Screenshot the narrow breakpoint *with a selection active* — the default screenshot has selection on the first item, which often hides the misalignment |
| Long-content scroll containers | Scrollbar styling that clashes with the surface; scroll affordance invisible | View at a height that forces the container to scroll |
| Hover | Hover-only affordances unreachable by keyboard/touch | Inspect the rule, not just the rendering |

The bundled sweep automates the first two (`focus-indicator-suppressed`,
`focus-indicator-default-only`, `motion-without-reduced-motion-fallback`). The
rest still need a deliberately constructed state — the point is to *know that
default-state evidence is partial* and say so, rather than reporting "audited"
after one screenshot.

**A note on what should not become an automated check:** a custom scrollbar, a
missing hover style, an unusual focus color — these are design choices, and
flagging them mechanically produces false positives on healthy pages. A check
earns automation only when its failure state is unambiguous (suppressed focus
with no replacement is; "uses the default scrollbar" is not). Misfiring on healthy
input trains people to ignore the whole gate, which is worse than not having it.

## 7. Mid-run state is not final state

When a multi-step process is running (a batch sweep, a sync, a queued render),
reading its state file or its output directory *while it runs* shows whichever
items it has reached so far. Items not yet processed look identical to items that
were processed and found empty.

Before concluding "these were skipped / found nothing", wait for the process to
exit and check its exit status. "Not reached yet" and "no result" are
indistinguishable from the outside, and reporting the former as the latter is a
fabricated negative.

## 8. A hidden tab defers media loads — the request is never sent

Driving a tab through extension tooling usually means the tab is **not visible**
(`document.visibilityState === "hidden"`): the window is behind others, minimized,
or belongs to a browser instance that is not frontmost. Chrome defers `<video>` /
`<audio>` loading in hidden tabs — the media request is **never issued at all**.

The signature is distinctive, and reads exactly like a broken player if you don't
know it: `video.networkState = 2` (LOADING) forever, `readyState = 0`,
`video.error = null`, the request **absent from the network log** — while a
page-context `fetch()` of the same URL succeeds instantly. Every component of the
stack is healthy; the scheduler simply hasn't started the load.

Order of investigation: check `document.visibilityState` **first**, before any
server-side or codec theory. If it is `hidden`, verify media in a context that is
visible — a headless run (headless pages count as visible to the scheduler) or a
tab actually brought to the foreground. Two sub-traps while escaping: OS-level
scripting (e.g. AppleScript's application object) may not see the automation
window at all when it belongs to another profile/instance — don't burn rounds
trying to raise it; and per trap 9, don't verify the escape under virtual time.

## 9. Virtual time fast-forwards timers, not I/O

`--virtual-time-budget=N` makes `setTimeout`-based test scripts complete
instantly — and starves everything that needs **wall-clock** time: network
transfers, disk reads, media buffering. An injected probe that waits 3 virtual
seconds and then reads `video.readyState` gets `0` on a perfectly healthy video,
because zero real milliseconds of buffering have happened. That is a fabricated
negative, produced by the harness (one real session shipped exactly this wrong
verdict before catching it interactively).

Rule of thumb: **virtual time for DOM-and-interaction assertions** (clicks,
dialog open/close, class toggles, counters, `src` swaps — all synchronous or
timer-driven); **real time and a visible context for anything that loads**
(media readiness, lazy images, network-dependent states).

## 10. `--dump-dom` captures at load, not after your injected test

Headless `--dump-dom` serializes the DOM when the page finishes loading. An
injected async test that runs after a delay and writes its verdict later (a
common pattern: `document.title = "RESULT:" + JSON.stringify(state)`) finishes
*after* the dump — so the dump contains the test's **source code**, and a grep
for the marker happily matches the marker inside your own `<script>` text. The
output looks like a result and is nothing of the sort.

Two mechanics fix it, chosen by trap 9's rule: a virtual-time budget (DOM-only
tests), or arranging the test to finish inside the load window (real-time tests —
lazy-loading assets conveniently extend it). And make the grep match something
only the **executed** result can contain — `RESULT:{"` with the opening brace —
never the bare marker that the source also contains.

Used correctly this title-encoding pattern is the cheapest interaction probe
available without a debugging protocol: inject script → perform interactions →
assert on **state** (`dialog.open`, counter text, `src` changed — a dispatched
click alone proves nothing, per trap 1) → encode the assertion results into
`document.title` → dump and grep the marker-plus-brace.

## 11. A media stall may be the test server: Range support × moov position

MP4s whose `moov` atom sits at the **tail** (common for phone recordings and
editor exports) require byte-range access before metadata can be read. Browser
media stacks fetch them with Range requests; `python3 -m http.server` — the very
server trap 3 recommends — **ignores Range and returns 200 with the whole
body**, and the media element stalls at `readyState 0` indefinitely. Meanwhile
`fetch()` with a bounded Range header "succeeds" (the server just ignores the
header), and a full GET downloads fine — every probe short of the media stack
itself says the server is healthy. The page gets blamed; nothing on the page is
wrong.

Diagnose in two commands: `curl -sI -H "Range: bytes=0-100" <url>` — a `200`
with full `Content-Length` instead of `206` means no Range support; and locate
`moov` vs `mdat` byte offsets in the file (tail-moov + no-Range = guaranteed
stall). Escapes: a range-capable static server (many exist; verify with the same
curl — expect `206` and a `Content-Range`), or `file://` for pure rendering
checks (native random access, no server), or serving faststart-remuxed copies.
Keep the original files untouched; remux copies are a serving concern, not an
asset edit.

## 12. Calibrate capture and inspect the minimum surface

Capture the whole visible composition before zooming into a local defect. Then
inspect the affected component and at least one relevant responsive width.
Include lower sections for long pages; a clean hero does not validate the rest.

Open every screenshot with an image viewer and record what you saw. Use DOM
geometry to explain a visible problem, not to replace visual judgment.

**Calibrate the instrument before you trust it — a capture can both invent a
defect and hide one.** A screenshot is not a neutral window onto the page: pixel
evidence is notoriously noisy from anti-aliasing, sub-pixel positioning and font
smoothing, and a frame captured at a different device scale factor than the
viewport it claims to represent will crop or letterbox what you see.

- **Before filing "content is clipped / overflowing", falsify it against DOM
  geometry.** If `document.documentElement.scrollWidth === clientWidth` and the
  suspect element's `getBoundingClientRect().right` sits inside `clientWidth`,
  the page fits and the clipping lives in your capture, not in the product. This
  is the one direction where DOM geometry *overrides* the visual impression
  instead of explaining it — report the reverse and you send someone to "fix"
  CSS that was already correct.
- **Pin the scale factor** (`--force-device-scale-factor=1`) so the captured
  frame and the CSS viewport agree, and capture only after fonts have loaded and
  animation/network have settled; those are the standard sources of diff noise.
- **A false pass is the worse failure, so the engine you capture with must be the
  engine the reader will view in.** Headless rendering follows standardized
  software paths while headed rendering uses host GPU and OS font hinting, so
  subtle layout shift, font substitution, z-index and animation defects are
  exactly the class headless most reliably *hides*. Never accept a thumbnailer or
  preview renderer whose layout engine differs from the target application as
  evidence — a green check on the wrong engine manufactures confidence, which is
  worse than having run no check at all.

Check at minimum:

- macro hierarchy, balance, density, repeated context, and page-type fit;
- type family, size, weight, line height, tracking, column width, and semantic
  line breaks;
- computed body/key-heading typography, relevant control/text-column/rail
  widths, and the smallest important text when DOM evidence is available;
- wrapped controls, clipped content, unexpected overflow, competing scroll
  owners, sticky overlap, dense data-driven collisions, and same-row alignment;
- image load, crop, natural/display ratio, focal point, and overlay collisions;
- mobile preservation of identity, status, decision fields, and primary action;
- status-semantic density on list/queue pages: alarm-toned chips repeated across
  rows, one global fact re-rendered per row, and unlabeled numeric/graphic cells
  (contract details in the journey/page-contract reference);
- keyboard focus visibility, focus obstruction, and target size/spacing when
  accessibility is in scope. A default screenshot cannot show this: an element
  can pass "is it focusable" and still leave the user lost, because a global
  `outline:none` suppressed the ring and nothing replaced it. The sweep reports
  `focus-indicator-suppressed` (error) and `focus-indicator-default-only`
  (warning); confirm visually that the focus state is also distinguishable from
  the *selected* and *hover* states, which a stylesheet audit cannot judge;
- motion that ignores user preference — the sweep reports
  `motion-without-reduced-motion-fallback` when the page animates but declares no
  `@media (prefers-reduced-motion: reduce)`. Degrading means keeping the end
  state and dropping the travel (keep the highlight, drop the flash), not
  removing the feedback;
- states that only exist off the default path: a wrapped narrow-viewport row
  screenshotted *with a selection active*, a scroll container at a height that
  actually scrolls, an expanded/error/empty variant. Default-state evidence is
  partial evidence — say which states the report covers;
- parity with the named reference and the project's tokens/assets before
  applying generic taste rules.

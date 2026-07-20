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

Browsers cache aggressively, and **`file://` is cached too** — reloading the tab
after editing the file frequently re-renders the *old* build. This produces the
worst class of QA error: "I fixed it, but the screenshot still shows the bug",
which sends you chasing a phantom.

Two habits remove it:

- **Cache-bust the URL** when re-opening after an edit: append a changing query
  (`?v=<timestamp>`) so the browser treats it as a new resource.
- **Give the artifact a visible freshness anchor** and check it *before*
  judging any content: a version stamp, a build time, a generation timestamp
  rendered on the page. Then "is this stale?" is answerable in one glance rather
  than by inference.

The anchor has to be one you actually keep current. A stamp that is updated in
one place (say, an on-page badge) but not another (the `<title>`) creates a
second-order trap: the reader checks the *stale* one, concludes "this is the old
version", and dismisses a change that did ship. If an artifact carries a version
in more than one place, they must be written together.

## 3. `file://` is not drivable by browser-extension tooling

Extension-based browser automation generally cannot navigate to `file://` URLs
(the extension has no host permission for the scheme). Headless CLI browsers
*can* open `file://`, so a local artifact is inspectable but not necessarily
*interactive* through the same channel.

When an audit needs real interaction on a local file, serve it:

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

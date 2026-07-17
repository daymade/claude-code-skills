# Authenticated-SPA Driving And Environment Hijack Traps

Load this reference when the audit must sign in to a SPA (Supabase/OAuth/token
auth), when scripted login fails or bounces, or when the target runs on
localhost behind a developer machine with shell proxies. Every trap below burned
a real audit; each one masquerades as either "the login is broken" or "the
product is broken" when the defect is in the driving harness or the
environment.

## Contents

- Login Driving Traps
- Post-Login Navigation Contract Drift
- Environment Hijack Diagnostics
- Fixed-Overlay Screenshot Collapse

## Login Driving Traps

### 1. Rendered button text may not equal source text

Component libraries restyle short CJK labels: antd inserts a space between the
two characters of a two-character button, so the rendered text of a 登录 button
is 登 录 and a locator like `getByRole('button', { name: /登录/ })` times out.
Prefer partial or whitespace-tolerant matching for short CJK controls:

    page.locator('button:has-text("登")')          // partial
    page.getByRole('button', { name: /登\s*录/ })   // whitespace-tolerant

The same applies to any library that letter-spaces, uppercases, or otherwise
transforms label text at render time. When a locator times out on a control you
can see in the screenshot, diff the rendered text against the source text
before blaming the page.

### 2. waitForURL substring matches lie on auth redirects

A guarded route bounces to `/auth?redirect=%2Faccounts%3Fpage%3D1...`. That URL
*contains* the target path as a query parameter, so a substring or regex match
like `waitForURL(/accounts/)` reports success while the browser is still
sitting on the login page — the audit then screenshots the login form and
labels it the accounts page. Assert on the pathname, never the full URL:

    await page.waitForURL((u) => !u.pathname.startsWith('/auth'), { timeout: 25000 });

### 3. Hard navigation races the freshly written session

After a scripted login succeeds, `page.goto(...)` loads a brand-new document,
which re-runs the SPA's session-restore flow from storage. If the auth
provider's token write or the restore round-trip has not settled, the route
guard sees "no session" and bounces to login — the audit concludes "login does
not persist" when the product is fine. Prefer in-app navigation (click the nav
link) to move between pages; it keeps the live session and mirrors real usage.
When a hard reload is itself the thing under test, wait for the restore to
converge before judging:

    await page.waitForURL((u) => !u.pathname.startsWith('/auth'), { timeout: 15000 });

### 4. The session-restore interstitial is not evidence

SPAs commonly render a "restoring session…" splash for a second or two after
load. A screenshot taken during it proves nothing about the page. Wait for a
required state marker (H1, table, workspace rail) or for the interstitial text
to disappear before capturing. Fresh headless profiles have no stored session
at all, so an unauthenticated headless hit on a guarded route always shows
either the interstitial or the login page — that is the guard working, not a
defect.

## Post-Login Navigation Contract Drift

A successful login does not prove that a remembered sidebar item exists on the
landing page. Products add home cards, rename entries, or mount navigation only
after entering a workspace. A hard-coded label can therefore time out while the
product is healthy.

Before filing a missing-navigation finding, capture the post-login contract:

    () => ({
      href: location.href,
      visibleText: document.body.innerText.replace(/\s+/g, " ").trim().slice(0, 600),
      entries: [...document.querySelectorAll('a[href],button')]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return rect.width > 0 && rect.height > 0
            && style.display !== 'none' && style.visibility !== 'hidden';
        })
        .map((element) => element.textContent?.replace(/\s+/g, " ").trim())
        .filter(Boolean)
        .slice(0, 40),
    })

Follow the visible canonical entry path, then prove the target with its pathname
and a state marker. If the expected locator is absent but another visible entry
reaches the target, the harness was stale. If no visible entry or direct route
can reach the promised workspace, then the product has a navigation defect.

## Environment Hijack Diagnostics

Environment problems impersonate product bugs. The tell: the failure message
blames the network or the product while the same request succeeds from a
different client. Run these checks before filing any "login/network broken"
finding from a scripted browser.

### 1. Shell proxy inheritance eats localhost

A Playwright/Puppeteer-launched Chromium inherits `http_proxy`/`https_proxy`
from the shell. On a developer machine with a system proxy, the browser then
routes `http://127.0.0.1:<port>` API calls through the proxy, which cannot
reach them — the frontend surfaces a generic "network error" toast that looks
exactly like a product defect. Discriminator: the same URL answers `curl`
directly but fails inside the scripted browser. Fix at launch time:

    chromium.launch({ args: ['--no-proxy-server'] })
    // or: env NO_PROXY=localhost,127.0.0.1 with the proxy vars preserved

### 2. The build's entry point is a contract — audit through it

A production SPA build bakes in its API/auth base URL and ships a CSP whose
`connect-src` matches that origin. Serving the same static bundle from a
different port or host (a replica server, a copied dist/) renders fine — until
the first auth call, which the CSP blocks. Login then fails on an otherwise
healthy stack. Read the console error: a CSP violation names the blocked URL
and the allowed list, which tells you the entry point the build expects.
Audit through the gateway/origin the build was configured for; any other entry
is a fresh-session diagnostic at best.

### 3. Triangulate browser events against server logs

Wire the three listeners before reproducing a login/network failure:

    page.on('console',        m => m.type() === 'error' && console.log('CONSOLE:', m.text()));
    page.on('requestfailed',  r => console.log('FAILED:', r.failure()?.errorText, r.url()));
    page.on('request',        r => console.log('REQ:', r.method(), r.url()));

Then check the backend/gateway access log for the same window. The decisive
signal is an *absence*: if the server log shows zero auth requests arriving
while the browser fired one, the request went somewhere else entirely (proxy,
wrong origin, CSP kill) — the product's auth code never ran, so no product
finding can be filed from that run.

## Fixed-Overlay Screenshot Collapse

Element-scoped screenshots of `position: fixed` overlays (drawers, modals,
full-viewport scrims) can collapse to a sliver: inside a transformed ancestor —
which screenshot harnesses commonly introduce — `fixed` resolves against that
ancestor, whose height is content-sized. If an overlay renders correctly live
but captures collapsed, wrap the capture target in an explicit-height container
that deliberately becomes the containing block:

    <div style="height: 560px; position: relative; transform: translateZ(0); overflow: hidden">

Whole-page screenshots are unaffected; this only bites per-element captures.

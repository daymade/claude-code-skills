# Replacement backends

The menu this skill picks from. One default, the rest kept as real options
rather than footnotes, because the right answer changes with who the user is.

Each entry says how it was checked. **Live-tested** means a query actually ran
through it and returned real, current URLs, on 2026-09-14 or 2026-09-15.
**Documented** means a vendor page said so and nobody exercised it. The difference
matters: one keyless option that looked fine on paper failed outright in testing.

A third state turned up often enough to name: **reached but gated** — the endpoint
answered, the credential authenticated far enough to produce a product-specific
error, and something on the account was missing. That is worth more than either of
the other two labels, because it confirms the URL and hands you the exact next
step, which a vendor page rarely does.

**A third distinction runs underneath those two, and it decides how far a failure
generalises.** When an endpoint refuses with a named policy — Firecrawl's
`KEYLESS_ACCESS_NOT_AVAILABLE` is the example here — it is stating a rule, and a
handful of calls in one sitting is ample evidence of that rule. When it refuses
with a challenge, a throttle or an anti-bot message, it is reporting a condition
that moves with time, address and reputation. Several failures in one window are
then **one observation repeated**, not several, and they cannot support a claim
about the product. Re-sample across days and across egress before turning that kind
of failure into a verdict. The same arithmetic error is easy to make in the other
direction, by reading a run of successes inside one window as proof of a ceiling
that was never approached.

Quotas and prices are the volatile part. Treat them as what the vendor said that
day and read the current page before quoting a number to anyone. Endpoints and
auth shapes move far more slowly.

## Contents

- [How to choose](#how-to-choose)
- [Default — Exa](#default--exa)
- [Other options worth keeping](#other-options-worth-keeping)
- [Documented but untested](#documented-but-untested)
- [Ruled out](#ruled-out)
- [After installing, check nothing else answers first](#after-installing-check-nothing-else-answers-first)
- [The mainland-China question](#the-mainland-china-question)
- [Registering it](#registering-it)

## How to choose

In order. A later criterion never overrules an earlier one.

1. **Does it need an account?** Not needing one removes the only step you cannot
   do for the user.
2. **Does it need anything installed?** A hosted endpoint needs nothing. A local
   server needs Node or a Python with an SDK, and a stock macOS has neither — its
   `/usr/bin/python3` is a stub that opens an Xcode installer dialog on first use.
3. **Does it replace everything that broke?** If `web_fetch` died alongside
   `web_search`, a search-only backend leaves the user able to find pages and
   unable to open them.
4. **Is it reachable from where the user is?**
5. **Does it answer in the language the user asks in?** A Chinese-speaking user
   handed English sources reads that as the tool still being broken.
6. Result quality, last. A working search beats a better one that will not run.

**A keyless tier is a vendor decision, not a property.** One candidate here shipped
an anonymous tier, documented it, and was refusing every anonymous call by the time
it was tested — the server said so explicitly, in an HTTP 200. So when the default
stops answering, do not debug it as if something on this machine broke. Re-run the
five criteria above against the current menu and pick again. The same reasoning
applies to the entry that is default today.

**So carry an order, not a single choice.** Three shipping systems were looked at
and all three chain their backends rather than betting on one: an open-source
finance agent falls through Exa to Perplexity to Tavily depending on which key
exists, another pulls several news sources in parallel, and a third falls through
three free engines in turn. Three is not a survey, but none of them bet on one. This file keeps one default because
a non-technical user should be told what to install, not handed a menu — but the
order behind it is: **Exa, then Tavily once anonymous Exa starts refusing requests
or when a key is already in hand, then a local gateway when the work is mainly
Chinese.**
Moving down that list is a normal event, not a failure.

**Check which half of a stack the word "free" is attached to.** In the one case
examined closely, a widely starred project advertising zero-cost operation meant
that its scheduled runner was free while every search source behind it billed per
call. One case is not a pattern, but it costs nothing to ask the question before
repeating a free claim to a user.

## Default — Exa

`https://mcp.exa.ai/mcp` — **live-tested**.

One command, no key, nothing installed:

```
claude mcp add --scope user --transport http exa https://mcp.exa.ai/mcp
```

Then grant it, in `~/.claude/settings.json`, or the model will register the tool
and be refused when it calls it:

```json
{ "permissions": { "allow": ["mcp__exa__web_search_exa", "mcp__exa__web_fetch_exa"] } }
```

Merge that into the file; do not replace it. **Both lines have to be at the user
level.** Putting the grant in a project's `.claude/settings.json` looks identical
and does not work — see *Registering it* at the end of this file for what the
client does instead and how it tells you.

Of the candidates in this file, it is the only one that took first place on every
criterion at once. The anonymous tier needs no account at all, and adding a key
later raises whatever ceiling exists without changing anything else.

**Be precise about the allowance, because it is the one thing nobody here knows.**
The vendor's current page says only that the free plan "covers casual use" and
publishes no rate or daily figure, so do not quote one. Testing did not find the
ceiling either: anonymous requests across separate isolated sessions all succeeded,
with no key, no error and nothing that looked like throttling — at a handful of
requests, which is far too few to have found a limit even if one is there. So the
honest state is that a ceiling probably exists and its size is unknown. The signal
to act on is therefore an observed one: when requests start failing or being
throttled, that is the moment to add a key or move down the order, not a number
somebody predicted in advance.

**Say that out loud to a non-technical user before you leave, because they will hit
it alone.** From their chair a ceiling looks exactly like the bug you just fixed:
the agent stops finding things. Give them the one sentence that separates the two —
*if searching stops working again, it is the free allowance, not the same fault
coming back* — and tell them the fix is to ask their agent to run this procedure
again and pick the next backend down.

**Resist writing that fallback down as a single command they can paste.** Swapping
backends is not one command: the new server has to be registered *and* its tools
granted by name in `permissions.allow`, and those names differ per backend. A
paste-able `claude mcp add` line with no grant beside it reproduces exactly the
failure the main workflow exists to prevent — registered, refused, and the model
reporting that it is waiting for permission — this time with no agent present to
notice. Tavily in particular cannot be pre-written even by someone willing to:
its endpoint rejects an unauthenticated MCP handshake outright (HTTP 401, empty
body, before `tools/list`), so the tool names needed for the grant are not
discoverable until an account exists.

What you can do before leaving is remove the account step from their path: get the
free Tavily key during the install while you are there, register it alongside the
default, and grant both. Then the fallback really is nothing for them to run.

Tools are `web_search_exa` and `web_fetch_exa`, so it replaces **both** halves
when fetch is dead too. Once registered they appear to the model as
`mcp__exa__web_search_exa` and `mcp__exa__web_fetch_exa` — prefixed, so neither
collides with the built-in name in logs or in the model's own reasoning.

Measured returning real articles with titles, URLs, publication dates and
authors, all checkable.

## Other options worth keeping

**Tavily** — `https://mcp.tavily.com/mcp/`, **live-tested**. Hosted, so still
nothing installed, but it needs a key (in the URL query or an `Authorization`
header; OAuth also exists). Vendor-documented free tier is 1,000 credits per
month, recurring, no card. Choose it over the default once anonymous Exa starts
throttling or erroring, or when its extract and crawl tools are wanted. It
handled a Chinese-language query correctly in testing.

**one-search-mcp with Bocha** — **search live-tested**, and the right answer for
Chinese-language work. It runs locally over npx, so it costs a Node install and a
first-run download, but it returned noticeably better mainland Chinese sources
than either hosted option. It is a local gateway over many providers, so the same
install can be pointed at Tavily, Bing or Google by changing one environment
variable. Needs a Bocha key. **Its fetch side is vendor-claimed, not tested here**
— `one_scrape` and `one_extract` appear in its own description, and nobody
exercised them. That gap matters, because this is the entry recommended below for
the case where `web_fetch` died too; confirm fetch on a real page before relying
on it for that case.

**UniFuncs** — `unifuncs.com`, **not tested here**. Hosted, one key, and it covers
both halves: a search API and a reader that also handles PDF, Word, Excel and
PowerPoint at a URL. It ships as skill bundles rather than an MCP server, and they
are the immune kind — their front matter restricts them to running a local Python
script through the shell, so nothing routes through the model's declared tools.
Worth checking before installing anything else, because a user who already has a
key here needs no new account at all.

**brave-search-skills** — **live-tested**. Not an MCP server; a skill bundle
whose instructions have the model build its own `curl` calls against Brave's API.
Works, and is the pick for someone already in the Brave ecosystem who wants
Goggles or Brave's structured data. Three install steps rather than one, more
turns at runtime, and its skill names (`web-search`, `news-search`) read
confusingly close to the built-in tool in logs. The Brave API requires a card
even on the free tier, as an anti-fraud check the vendor says is never charged.
**Search only**: nothing in the skills it exposes reads a given URL's body, and
Brave's API is not a fetch API — so it leaves a user who lost `web_fetch` able to
find pages and unable to open them.

**You.com keyless** — `https://api.you.com/mcp?profile=free`, **live-tested**.
Hosted, one command, no account, and it returned real results with real URLs and
dates. **Search only, and the exclusion is the vendor's own**: its documentation
lists `you-contents` — the tool that reads a page — among those excluded from the
free profile. So installing this alone moves a user from "cannot find it" to
"found it, cannot open it". Use it when only `web_search` is dead.

## Needs an account before it can be judged

**Linkup** — `https://mcp.linkup.so/mcp`. Its documented free allowance is the
largest of anything found here. **Its anonymous path was exercised and failed**: a
keyless connection was attempted directly at the protocol layer and the MCP
handshake itself failed before any tool was called, returning
`-32603 Invalid response format` — a message that names neither the key nor the
fix, so somebody debugging it has nothing to go on. That is a live observation of
the keyless path, not a vendor claim. What remains untested is the product itself,
which needs a real account; nothing here argues against registering for one.

## Ruled out

| Option | Why not |
|---|---|
| Firecrawl's **anonymous tier only** | **Live-tested and failed.** That tier is documented to cover search *and* scrape, which would have made it the one option replacing both dead tools with no account. Every anonymous call was refused by the server itself: HTTP 200 at the transport layer, `"isError": true` with `"code": "KEYLESS_ACCESS_NOT_AVAILABLE"` in the payload, four calls, zero results. The error text is unusually good — it names the cause and gives the fix — but the fix is "create an API key", so the keyless property is gone. **This rules out the anonymous tier, not the product.** Firecrawl also has a keyed free allowance and a self-hostable open-source edition; neither was exercised here, and either could be the right answer for somebody willing to register. |
| DuckDuckGo, via any wrapper | **Refused throughout one session, from one address.** Its anti-bot layer answered "DDG detected an anomaly in the request" to every attempt, and three retries including a deliberate wait changed nothing. Read that for exactly what it is: an anti-bot refusal is reputation- and time-dependent, so several failures inside one window are one observation repeated, not several. Enough to stop recommending it; not enough to call it dead. Re-test from a different address on a different day before either restoring or ruling it out. |
| Brave's own hosted MCP | **Looked for and not found.** Brave's documentation describes a server that runs locally, whose HTTP mode is for self-hosting on a network you trust; no vendor-operated endpoint turned up in that documentation or its repository. That is the extent of the search — it is not a claim that none exists anywhere. |
| Query-template bundles (for example the "search N engines at once" skills) | Instructive rather than bad. They cost nothing and need no key, because they are just a list of search-engine URL templates the model fills in and then **reads with its own fetch tool**. On the endpoint this skill exists for, that fetch tool is one of the dead ones, so the whole bundle resolves to the failure being fixed. Usable only once a working fetch is already in place. |
| Serper | **Looked for and not found.** Searching the vendor's site and repositories turned up only third-party wrappers, no server the vendor itself publishes. Third-party wrappers may work; nobody exercised one here. |
| Perplexity | Hosted endpoint exists; **no free tier was found** on the vendor's current pricing page, so the organization has to be funded before the first call. Priced tiers change; check before ruling it out for a user who is willing to pay. |
| Kagi | Hosted endpoint exists; no free allowance found, and API billing is separate from the consumer subscription. |
| Zhipu 智谱 (`api.z.ai`) | Hosted and reachable inside China, but the vendor's FAQ restricts it to GLM Coding Plan subscribers with no pay-as-you-go path, and a paying subscriber has reported billing failures against it. |

## After installing, check nothing else answers first

A registered MCP server is not the same as a used one, and two separate things
can intercept the request before it ever reaches your new tool.

The built-in tool is the first, and it is covered in the main workflow: leave
`WebSearch` enabled and the model keeps choosing it, measured at 21 calls to 0.

The second is easy to miss: **another installed skill can claim the query.** In
testing, an unrelated skill on the machine matched a plain "search for this
week's news" prompt and took over before any MCP tool was considered, spending a
dollar of tokens on the wrong path. If the model still is not calling the new
tool after the built-ins are gone, look at what else is installed rather than
reinstalling the backend.

## For a user inside mainland China

None of the options above is confirmed reachable from there, and none was
measured from there — no machine involved in this work was on that side of it.
Every reachability claim in this file, in both directions, is an inference from
where a vendor operates.

Domestic hosted endpoints do exist, and they are **not** found on the search
vendors' own sites or GitHub repositories. They live on the cloud platforms'
MCP marketplaces, which is why an earlier pass that only checked vendor
repositories wrongly concluded there were none. Three such marketplaces are
confirmed to carry them: Aliyun's Bailian, Tencent Cloud's, and Tencent's
WorkBuddy connector panel — that last one was found only because an unrelated
vertical search service announced listing there, which is a fair description of
how discoverable any of this is. Two entries take an ordinary pay-as-you-go key
with no subscription:

| Option | Endpoint | Billing |
|---|---|---|
| Aliyun Bailian web search | `https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp` | first 2,000 calls free, then per-thousand |
| Tencent Cloud WSA | `https://api.wsa.cloud.tencent.com/Mcp` | per-thousand, no enterprise tier required for the entry plan |

**Aliyun's endpoint was exercised with a real DashScope key, and the result is the
useful part: the URL is right and the account is not enough.** The MCP handshake
came back HTTP 404 carrying a specific business error —
`未开通该MCP或非可用开通状态`, "this MCP is not activated" — rather than a generic
not-found, which is what tells you the route exists and the gate is provisioning
rather than a typo. So budget a console visit before the first call: an ordinary
DashScope key that already works for model inference does **not** carry this. The
free allowance and the endpoint shape were not contradicted by anything observed;
they were also not reached.

The console is `https://bailian.console.aliyun.com/`. **The clicks inside it are not
recorded here and should not be guessed at** — which is a real problem for the agent
doing this, because its own web search is by definition broken at that moment, so it
cannot go and look them up either. Hand this step to the user with the URL and the
exact error string, rather than narrating a menu you cannot see.

Aliyun's is the better documented of the two and was corroborated across three
independent sources; Tencent's command shape was derived from its documentation
rather than copied from an official example, and its credential is the looser
claim of the two. What a Tencent Cloud account issues by default is a
SecretId/SecretKey pair meant for TC3 request signing, not a bearer token — checked
against a real account. Whether WSA mints a separate bearer key of its own was not
established, so treat the `Bearer` line as the thing to verify first rather than
the thing to build on.

Two further leads stop one step short of confirmed, and are worth finishing
before concluding anything: **Zhipu's mainland platform** publishes an MCP
endpoint that appears to bill per call on an ordinary key — note this is a
different endpoint from the international one listed under *Ruled out*, which is
subscription-gated, and the two are easy to confuse. **Baidu Qianfan** documents
MCP support with the lowest entry barrier of anything here (a free monthly
allowance, enabled by default), but its endpoint URL sits behind a console login
nobody opened.

**The narrow gap that is real**: neither Aliyun Bailian nor Tencent WSA — the two
in the table above — carries a fetch tool. They search and nothing more. Nothing is
claimed here about the fetch side of Zhipu's mainland endpoint or Baidu Qianfan,
since neither console was opened. So when the diagnosis says both `web_search` and
`web_fetch` are dead, either one only fixes half the problem.

Two candidates close that gap, and they trade against each other:

**`one-search-mcp` with Bocha** — its search side is live-tested and returned the
best Chinese-language sources of any candidate, and it is packaged as an MCP server
so registration is one command. It costs a local Node process, and its fetch tools
are the ones flagged above as claimed rather than measured.

**Metaso (秘塔)** — `metaso.cn`, **not tested here**. A plain HTTP API with two
routes, one for search and one for a reader that returns page text and is
documented to handle WeChat public-account articles, a format that is both widely
asked for and routinely hostile to plain fetching. It is hosted, so it needs no local runtime at
all, and registration reportedly needs no card. Against it: **there is no MCP
packaging**, so somebody has to wrap those two routes before an agent can call
them, which is real work the other entries do not require. The free allowance
quoted for it comes from a secondary write-up, not the vendor, and that write-up
had a commercial interest — read the current page before repeating any number.

By this file's own ordering a hosted API outranks a local runtime, so Metaso would
win if the wrapper existed. It does not, so the recommendation stays with
`one-search-mcp` until somebody builds one or confirms the fetch side of it.

## Registering it

Get the current syntax from the tool rather than from this file, because flags
move: `claude mcp add --help`, and for Codex `codex mcp add --help`. The shape is
a transport, a name, a URL, and an auth header or a key in the query string.

Three things worth knowing before running it:

- **Scope is not optional in practice.** `claude mcp add --scope` takes `local`,
  `user` or `project` and defaults to `local`, a name that sounds contained but
  writes into the user's real `~/.claude.json`. Pass `--scope` explicitly every
  time. You do not have to guess which file: both `add` and `remove` print the
  absolute path they modified, which is the line to show the user. `--scope user`
  was measured landing as a top-level `mcpServers` entry in that same
  `~/.claude.json`; `--scope project` writes a `.mcp.json` beside the cwd.
- **A new server starts unapproved, and that really does block its tools.** Every
  hosted server registered during this work showed as pending approval, and the
  refusal is explicit: `Claude requested permissions to use mcp__<server>__<tool>,
  but you haven't granted it yet`. One session appeared to ignore this and call the
  tool freely; it was running in a relaxed permission mode its account had, which a
  user on a relay token does not get. Grant the server — interactively, or by adding
  the prefixed tool name to `permissions.allow` — and do not read `claude mcp list`
  as a readiness check, because its status line said the same thing in the run that
  worked and the run that was refused.
- **Put the grant in `~/.claude/settings.json`; a project's `.claude/settings.json`
  is ignored unless that workspace has been trusted.** The client drops the entry
  and prints `Ignoring 1 permissions.allow entry from .claude/settings.json: this
  workspace has not been trusted` — on **stderr only**, so it is absent from
  `--output-format json` and an agent parsing that sees a bare denial. Measured with
  nothing changing but the grant's location: user settings works,
  `.claude/settings.local.json` works, the shared project file works only once the
  workspace carries `hasTrustDialogAccepted`. `permissions.deny` was honoured from
  the project file in every case, so the asymmetry is between restricting and
  granting, not between the files.
- **On Codex, `mcp add` against a hosted URL can hang instead of finishing.** It
  writes the `[mcp_servers.<name>]` block, then detects OAuth support, prints an
  authorize URL and waits with no timeout. Interrupt it and read the file — the
  entry is there, and the default backend answered anonymously afterwards without
  the flow ever being completed.
- **Claude Desktop's chat surface is not a target for any of this.** As observed in
  September 2026 it cannot take a remote endpoint from its config file; that path is
  a click-through connector
  flow in its own settings, and the menu names for it are not recorded here, so an
  agent attempting it is guessing at a UI. Say the procedure does not cover that
  surface and move to Claude Code on the same machine, where every step is a file
  edit.

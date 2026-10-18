---
name: floorplan-finder
description: >-
  Finds existing residential floor plans online and checks layout, entrance orientation,
  and source identity. Use for 找户型图、按楼栋房号找原图、核对同款或镜像户型.
  Not for designing, generating, or certifying architectural drawings.
---

# Floorplan Finder

Find an existing, inspectable plan that meets the user's actual acceptance criteria.
Deliver the image, its source, the match evidence, and any remaining identity gap.
Never substitute a generated or reconstructed drawing for a retrieved original.

## Start with the requested result

1. Recover every supplied constraint and later correction before searching.
   Separate confirmed facts, approximate recollections, source claims, and unknowns.
   Use [the working record](references/working-record.md) for a long or interrupted task;
   keep task data outside this installed Skill, in the authorized task directory.
2. Establish whether success requires **this exact unit's documented plan** or
   **the same physical layout**. Preserve an explicit exact-unit requirement until
   the user changes it. Do not impose property-record authentication on a request
   that only needs a matching layout.
3. Resolve only ambiguity that changes candidate selection: city/district,
   development/phase, approximate area, room arrangement, building height,
   elevator/household configuration, and **whose door faces which direction**.
   Ask whether “north-facing door” means the apartment entrance or building entrance.
   Reuse answers already given. Missing area does not prevent a first search.
4. Record acquisition boundaries, including online-only, public-only, and login
   authorization. Keep price, purchase year, and ownership as context; use them
   as search clues rather than proof of layout identity.

Restate the current constraints when asked and after a material scope correction.
Do not silently turn “about 95 m²” into an online listing's precise 94.86 m².

## Check available capabilities

Use the host's authorized search/fetch, browser, and image-viewing tools. Read the
current browser owner's instructions before operating it; use task-owned pages
and respect user takeover and other agents' resource ownership.

- Reuse installed retrieval/channel Skills when available. They own transport,
  authentication, and browser lifecycle; this Skill owns property identity and
  plan comparison. Optional helpers are not prerequisites for the public workflow.
- Without an interactive browser, continue accessible public pages and images.
  Keep a browser-dependent source pending rather than declare the whole task blocked.
- Without image viewing, gather original image URLs and source metadata, then
  request visual inspection or the missing capability. Text snippets cannot verify geometry.
- Request login or human verification only for a currently necessary source and
  only through the site's legitimate flow. After the person returns, inspect the
  current page/account state before continuing. Code submission alone proves no login.
- Establish the registered owner before proposing an owner-only archive route.
  Verify that the service actually offers the needed drawing; a login page proves
  neither eligibility nor availability. Never carry credentials into the task record.

Do not install tools, send brokers messages, purchase access, or bypass CAPTCHA,
login, paywalls, or host restrictions merely to advance a search.

## Retrieve originals before widening the search

Read [search routes](references/search-routes.md) when selecting sources or a route fails.

1. Bind the development's city, district, phase/alias, and public community ID.
   Search exact development names plus 户型图 / 两室 / building clues; search a
   documented alias separately. Inspect primary pages behind search results.
2. Open the community's plan gallery and individual plan/report pages. Obtain
   original images early. Also inspect relevant sale, rental, and renovation pages.
   Record a source-page → image association for each candidate, including stated
   area, room count and building details. An exterior-photo listing supplies no plan.
3. Inspect images with [plan verification](references/plan-verification.md).
   Keep plausible candidates when a feature is ambiguous or the source conflicts
   with the drawing. A wrong visual interpretation is grounds to reopen a rejection.
4. Show the strongest unresolved alternatives early, with the actual images and
   one discriminating question. For example, ask which side contains both bedrooms
   when the alternatives otherwise fit. Do not make the user choose from opaque IDs.
   Continue independent retrieval while awaiting their answer.
5. Expand only the missing evidence: standard-floor listings, same-layout units,
   developer materials, public official records, renovation drawings, or viewing
   videos. Treat nearby floors/buildings as leads; verify mirrors, end units,
   ground-floor gardens, top-floor duplexes, and alterations individually.

Use viewing-video evidence only when it can resolve a named gap. Bind the actual
playing item and timestamps; distinguish observed frames, spoken claims, and an
automatic transcript. A matching floor count does not identify a building or mirror.
Reuse the installed video/ASR owner instead of building another media pipeline.

## Recover with evidence

For a failure, record the source, attempted route, observed response, and next
distinct action in the existing working record. State what the failure establishes.

- After navigation/observation timeout, inspect the current URL and rendered state
  before navigating again; a page can load after the caller times out.
- After a stale selector, inspect the current page and target before another action.
  A dispatched click, empty receipt, or HTTP 200 is not evidence of the target content.
- For an app-only gallery placeholder, inspect accessible individual reports,
  related links, and ordinary image resources exposed by the public page. Do not
  invent report IDs, claim unseen pagination, or equate a gallery badge with coverage.
- For an access-control challenge, use an authorized human handoff or another public
  source. After a genuine network failure, use the host's existing network owner;
  do not change shared proxy/services as an incidental search step.
- Before another near-identical query, name the new evidence it could produce.
  When it cannot, change the source or unresolved feature. Reinspect strong rejected
  originals before concluding no matching plan exists.

Do not offload the task to property management or neighbors when the user requires
online retrieval. Do not mark all work blocked because one portal is unavailable.
If no authorized route can currently advance the result, report the exact missing
distinction/access and preserve candidates and completed work for continuation.

## Decide and deliver

Before asserting a match, check:

1. The delivered image is the inspected original and belongs to the cited page.
2. Every decisive layout constraint has image evidence or an explicit user decision.
3. Contradictions have been resolved or remain visible; no ambiguous label was
   silently counted as an extra bedroom/bathroom or an entrance direction.
4. The claim matches its authority:
   - **Candidate:** plausible, with the unresolved difference named.
   - **User-confirmed same layout:** the user explicitly selected this image as
     matching their home. This completes a same-layout request; stop searching.
   - **Documented exact unit:** an authoritative record explicitly binds the
     requested unit to the drawing. Do not infer this from user recognition alone.
5. The user can open the image and its source. Show the image inline when supported;
   retain an authorized local copy if remote access is fragile. Keep only requested
   result pages when finishing a task-owned browser workspace.

Lead the final reply with the result and image/source links. Explain the decisive
match or remaining gap briefly. Do not append more required questions after an
unambiguous same-layout confirmation, or upgrade it into an official unit certificate.

For ambiguous images or disputed exclusions, use the synthetic controls in
[comparison cases](references/comparison-cases.md). They test decisions, not portal availability.

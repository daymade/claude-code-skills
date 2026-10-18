---
name: search-routes
description: >-
  Choose online property-plan sources, bind page-to-image evidence, and recover from partial galleries and inaccessible listings.
---

# Search routes

Choose the next source by the evidence it can add. These are discovery methods,
not promises that a particular service has the requested unit or remains accessible.

## Resolve the property

Combine city/district with the development name before accepting a community page.
Compare phase/marketing aliases and building type. Similar names in another city,
a villa phase, or a different development are separate entities.

Use a few focused queries, adapting terms to known facts:

```text
"<development>" "户型图" <city>
"<development>" "两室" <city>
"<development>" "<building>" 户型
"<documented phase alias>" 户型图
```

Quoted queries still return fuzzy or unrelated results. Open the original result
and verify the entity. Treat cached snippets as locators; an absent listing does
not prove it was sold or removed for a particular reason.

## Obtain a page-bound original

| Source | Useful evidence | Follow-up |
|---|---|---|
| Community gallery / per-plan report | Multiple plan types and original images | Inspect plan-specific pages and related-plan links |
| Sale / rental listing | Area, floor count, room count, photographs and sometimes a plan | Open the actual image gallery; classify exteriors and interiors separately |
| Developer brochure / public project record | Phase, building series, standard-floor variants | Check whether the actual image and building/unit mapping are present |
| Renovation plan library | Drawings and topology | Check city, phase, duplicate plans, alterations and original versus design proposal |
| Viewing video | Connected-room walkthrough and spoken building details | Bind the playing item, timestamps and available visual/audio coverage |
| Public auction or historical record | Potential unit identifiers and attachments | Verify the attachment and unit association rather than rely on the title |

For Chinese community searches, 房天下's mobile community pages and individual
户型报告 are useful places to inspect alongside 安居客、贝壳/链家 and renovation
libraries. The public report route observed in a successful search had this shape:

```text
https://m.fang.com/xiaoqu/<city-code>/hxreport/<community-id>/<report-id>/
```

Discover current IDs and links from the actual community/report page. Do not guess
them or depend on this URL shape as a stable API. Follow each page's real image
reference to its ordinary original-image resource; preserve the association.

Inspect the full-resolution file and confirm it is an image, not a challenge or
HTML response saved with a .jpg suffix. Record the observed dimensions when possible.
Changing a thumbnail URL's size suffix may return the same low-resolution bytes;
inspect detail before claiming a higher-resolution original.

## Handle incomplete access

Distinguish an empty gallery, an app-download tile, a challenge page, an unavailable
listing, and a successful page containing only stock community photos. None proves
that every source lacks the floor plan.

When a mobile gallery exposes only a subset, inspect accessible desktop views,
individual report pages, and their public related links. Read the observed page's
DOM/embedded public data through the browser owner if needed; do not invent an
undocumented API or brute-force identifiers. Record advertised count, inspected
count, duplicates, and inaccessible remainder separately.

Try a different authorized transport only for a transport/content failure. Respect
site, account and host access limits. Record the exact failed source and continue
other public sources. Re-probe the current page after a manual handoff or timeout
instead of repeating the completed action.

## Bind corroboration narrowly

Keep these claims separate: community identity, building identity, exact unit,
source-reported area/counts, visible geometry, and user recognition. Three websites
copying one listing are not three independent observations.

For video, use the canonical item URL and actual active player. A preloaded media
element or an automatically advanced next item can belong to a different apartment.
Retain timestamps for inspected frames and identify automatic ASR as a draft.
Do not claim full visual coverage from a few frames or count floor/room narration
as proof of an unmentioned building number.

For an official archive, inspect the available fields/attachments before promising
success after login. Empty responses establish only that specific query's result;
do not generalize them into “the city has no drawings.”

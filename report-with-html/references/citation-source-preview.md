---
name: citation-source-preview
description: Read when a report needs numbered hover/focus source previews and in-place access to original text, images or PDF pages.
---

# Citation source preview

Use [source-preview.html](../assets/components/source-preview.html) as a
**candidate/pilot** recipe. It has runnable synthetic adapters, but has not passed
the interaction shelf's user-approval admission. Keep that status when reusing it;
the existing approved drawer and gallery retain their own contracts.

## Wire the page

Read the component's header and copy its complete `BEGIN…END` block before
`</body>`. Put a native button inside a sentence-end `sup`; its numeric label is
the visible citation and `data-source-id` binds it to the page's source record.
The component owns a noninteractive metadata tooltip and activation dispatch.
The page owns source identity, content loading and the full-content surface.

```html
<sup><button type="button" data-source-id="source-1">1</button></sup>
```

```js
const preview = SourcePreview.mount({
  root: document.querySelector('#reading'),
  sources: verifiedSources,
  openSource: pageAdapter.openSource,
  rollbackSource: pageAdapter.rollbackSource
});
```

Each source record has `id`, `kind`, `type`, `date`, `author`, `locator`,
`excerpt` and `original`. Use `null` for genuinely unknown metadata; do not infer
identities from similarity or renumber original images to match a filtered gallery.

| Kind | `original` | Page adapter acceptance before returning |
|---|---|---|
| `text` | `{text}` with the complete nonempty original | Exact cited wording and locator visible with surrounding context |
| `image` | `{url, group, index}`; original group/index may be unknown | Correct source bytes decoded, original identity retained and detail inspectable |
| `pdf` | `{url, page, previewUrl}` | Correct attachment and exact page rendered at readable size, with scroll or zoom when needed |

`openSource({source, trigger, closed})` may return a Promise. Return
`{surface, modal}` after verifying the displayed content. Call `closed()` once,
after the full source closes and its background locks are released. A modal needs
actual modal behavior, keyboard containment and a close path; a nonmodal surface
must not claim `aria-modal="true"`.

Register `rollbackSource({source, trigger, error})` before opening can run.
It must idempotently close partially opened page-owned surfaces and release their
inert state, scroll locks and listeners. The component awaits rollback before
restoring focus and reporting the opening failure. A failed rollback is a separate
unrecovered state: retain a working page-owned close path and do not claim recovery.
`preview.destroy()` is available after the full source is closed.

## Run the synthetic adapters

Serve [the examples directory](../assets/examples/source-preview/) with an existing
local static server, then open `demo-text.html`, `demo-image.html` and
`demo-pdf.html`. Keep their adjacent synthetic image, PDF and page-render files
at the exact relative paths. Text uses the shelf drawer; image uses the shelf
gallery; PDF uses a page-owned native dialog with a rendered original page.
These examples perform no business writes and contain no private source data.

Exercise hover and keyboard focus, movement into the tooltip, Escape dismissal,
fresh focus, activation, full-source reading and close. Focus and reading scroll
must return without immediately reopening the preview. Introduce an empty/wrong
source and a partial-open failure to prove content inspection and rollback can
reject and recover those cases. Load the available `frontend-visual-qa` Skill and
follow its Journey reference → **Cited Source Inspection**;
if unavailable, perform those same source-content and return checks directly.

A rendered PDF-page preview and a browser's native PDF viewer are separate axes.
Record untested viewer or assistive-technology behavior explicitly; working
tooltips and modal flags do not certify it.

## Pattern basis

[WCAG 2.2 SC 1.4.13](https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html)
explains dismissible, hoverable and persistent additional content.
[APG's tooltip pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/)
describes focus remaining on the trigger, Escape and `aria-describedby`; that
page explicitly remains work in progress without task-force consensus.
[APG's modal-dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
describes keyboard containment and focus return for actual modals.
[MediaWiki Reference Previews](https://www.mediawiki.org/wiki/Help:Reference_Previews)
provides a footnote-preview usage example. Its reference-list navigation and
interactive links inside the preview are not copied into this recipe.

Numbered markers, source metadata, in-place originals and suppression after Escape
or close are this report interaction contract. The component's delays are local
defaults; these details are not prescribed by WCAG.

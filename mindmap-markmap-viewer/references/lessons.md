# Real-world lessons & counter-review

This skill was hardened against a multi-agent adversarial review rather than just "looks right." The findings below are the battle-tested lessons baked into the current code; the regression suite ([`evals/test_render_markmap.py`](../evals/test_render_markmap.py)) locks each one down so they can't quietly come back.

## The bug that started it: white-on-white

A user opened the generated HTML standalone and got a **blank map**. Root cause: the renderer used a *transparent* background, which only works when embedded in an already-dark host (the original Streamlit dark-theme assumption). Standalone — or under a light theme — white font on a white surface is invisible.

Lesson: **white font and a dark background are one decision, not two.** `build_html` now paints its own dark backdrop by default; transparent is opt-in for hosts known to be dark.

## Counter-review: 23 agents, 12 confirmed, 7 rejected

After the visible fix, the renderer and text transforms were put through an adversarial pass: independent reviewers per dimension (escaping, frontmatter, filter hierarchy, docs), each finding re-verified by a second agent that tried to *refute* it by tracing concrete inputs through the code. 7 plausible-but-wrong findings were rejected (e.g. a claimed 4-space-indent bug that traces out correct; a "`&lt;` escape doesn't survive" claim that misread the HTML5 parse order). The 12 that survived:

| # | Area | Failure (concrete input) | Fix |
|---|------|--------------------------|-----|
| 9 | `build_html` | `</div>` in a node closes the div early → map truncated | HTML-escape the source |
| 10 | `build_html` | `List<String>` / `&` mangled in `textContent` | same escape, round-trips losslessly |
| 1 / 11 | `set_expand_level` | frontmatter with no `markmap:` key → **two stacked `---` blocks** | inject in place inside the fence |
| 2 | `set_expand_level` | inline `markmap: {colorFreezeLevel: 2}` not matched → double block, dropped setting | merge into the inline mapping |
| 3 | `set_expand_level` | `initialExpandLevel:` in *body prose* rewritten; expand-all silently lost | scope all edits to the frontmatter |
| 4 | `set_expand_level` | indented `markmap:` key not matched → double block | allow leading whitespace in the anchor |
| 7 | `filter_markmap` | hijacked pseudo-frontmatter feeds the double-block path | frontmatter-scoped injection removes the stack |
| 5 | `filter_markmap` | tab-indented child gets depth 0 (`1 // 2`) → reparented to root | `expandtabs(2)` before measuring |
| 6 | `filter_markmap` | `H4` after a bullet pulled in as the bullet's child | explicit kind-aware parent tree |
| 12 | `filter_markmap` | `*` / `+` / numbered bullets dropped on search → tree wiped | broaden the list-item regex |

(#8, a blank canvas on zero matches, was triaged as a documented contract — callers branch on the returned count — not a defect.)

## Process lessons worth keeping

- **Verify findings adversarially.** More than a third of the raw findings were plausible but wrong on a careful trace. A second agent tasked with *refuting* each one, with concrete inputs, is what separated the real bugs from the noise.
- **Two of the real bugs were introduced by an earlier "fix."** The first attempt at robust `initialExpandLevel` injection created the double-frontmatter family (#1/#2/#4). A counter-review pass before shipping caught them.
- **Edit text, not the rendering API.** Every transform is a text manipulation with a deterministic, dependency-free test — which is exactly why a regression suite could pin all 12 findings in seconds.

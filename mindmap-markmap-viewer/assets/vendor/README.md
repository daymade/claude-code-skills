# Vendored libraries (offline bundle)

`build_html()` references these files locally so a generated mind map opens
**offline** — no CDN, no network request. Versions are **pinned exactly**; bump
them deliberately and re-run `evals/test_render_markmap.py` after testing.

| File | Package | Version | License |
|---|---|---|---|
| `d3.min.js` | [d3](https://github.com/d3/d3) | 7.9.0 | ISC |
| `markmap-view.min.js` | [markmap-view](https://github.com/markmap/markmap) | 0.18.12 | MIT |
| `markmap-lib.min.js` | [markmap-lib](https://github.com/markmap/markmap) | 0.18.12 | MIT |
| `markmap-toolbar.min.js` | [markmap-toolbar](https://github.com/markmap/markmap) | 0.18.12 | MIT |
| `markmap-toolbar.min.css` | markmap-toolbar | 0.18.12 | MIT |

All three globals (`markmap-view`, `-lib`, `-toolbar`) attach to one
`window.markmap` namespace; `d3` is a global peer of `markmap-view`, so the load
order in `build_html` is d3 → view → lib → toolbar.

## Refreshing the bundle

Resolve the exact patch, then download the browser builds:

```bash
# exact versions: https://data.jsdelivr.com/v1/packages/npm/<pkg>/resolved?specifier=0.18
curl -sL https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js                          -o d3.min.js
curl -sL https://cdn.jsdelivr.net/npm/markmap-view@0.18.12/dist/browser/index.min.js   -o markmap-view.min.js
curl -sL https://cdn.jsdelivr.net/npm/markmap-lib@0.18.12/dist/browser/index.iife.min.js -o markmap-lib.min.js
curl -sL https://cdn.jsdelivr.net/npm/markmap-toolbar@0.18.12/dist/index.min.js         -o markmap-toolbar.min.js
curl -sL https://cdn.jsdelivr.net/npm/markmap-toolbar@0.18.12/dist/style.min.css        -o markmap-toolbar.min.css
```

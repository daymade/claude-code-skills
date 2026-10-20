# Scrapling Troubleshooting

## Installation Modes

Use the CLI path as the default:

```bash
uv tool install 'scrapling[shell]'
```

Do not assume `uv tool install scrapling` is enough for CLI usage. The base package may install the executable wrapper without the optional CLI dependencies.

## Verified Failure Modes

### 1. CLI installed without extras

Symptom:

- `scrapling --help` fails
- Output mentions missing `click`
- Output says Scrapling must be installed with extras

Recovery:

```bash
uv tool uninstall scrapling
uv tool install 'scrapling[shell]'
```

### 2. Browser-backed fetchers not ready

Symptom:

- `extract fetch` or `extract stealthy-fetch` fails because the Playwright runtime is not installed
- Scrapling has not downloaded Chromium or Chrome Headless Shell

Recovery:

```bash
scrapling install
```

Installation clues:

- `scrapling install` later reports `The dependencies are already installed`
- Browser caches contain both:
  - `chromium-*`
  - `chromium_headless_shell-*`

With no effective browser-path override, inspect only the current platform's root:

- On Linux, use `XDG_CACHE_HOME/ms-playwright` when `XDG_CACHE_HOME` is non-empty;
  otherwise use `~/.cache/ms-playwright`.
- On macOS, use `~/Library/Caches/ms-playwright`; ignore foreign platform settings.
- On Windows, use `LOCALAPPDATA/ms-playwright` when `LOCALAPPDATA` is non-empty;
  otherwise use `~/AppData/Local/ms-playwright`.

Read `XDG_CACHE_HOME` and `LOCALAPPDATA` directly, without npm-key fallbacks. Treat
their value `0` as an ordinary path. On other platforms, report `unknown` unless
an explicit browser-path override selects a root; do not borrow another
platform's populated cache.

Treat directory presence as a cache-location observation. Verify compatible
browser versions and a working launch by running the needed browser-backed fetch
and inspecting its saved content.

For an explicit `PLAYWRIGHT_BROWSERS_PATH`, inspect only that root. Read each
browser-path or `INIT_CWD` environment key
before `npm_config_<lowercase-key>` and `npm_package_config_<lowercase-key>`;
let a present empty value mask the lower-priority keys. With an empty or absent
effective browser-path value, select the platform default above.

After selecting either a default or overridden root, resolve a relative path
lexically against `INIT_CWD`, or the current directory when it is unset or empty.
Preserve literal `~` and whitespace; normalize `..` without following symlinks.

For the exact effective `PLAYWRIGHT_BROWSERS_PATH` value `0`, expect `unknown`
from the diagnostic. Locate the active
Playwright or Patchright provider's `.local-browsers` directory separately; this
helper does not discover hermetic provider locations. Do not infer a missing
runtime from `unknown` or substitute a populated default cache.

### 3. Static fetch TLS trust-store failure

Symptom:

- `extract get` fails with `curl: (60) SSL certificate problem`

Interpretation:

- Treat this as a local certificate verification problem first
- Do not assume the target URL or Scrapling itself is broken

Recovery:

Retry the same static command with:

```bash
--no-verify
```

Do not make `--no-verify` the default. Use it only after the failure matches this certificate-verification pattern.

## Static vs Dynamic Fetch Choice

Use this order:

1. `extract get`
2. `extract fetch`
3. `extract stealthy-fetch`

Use `extract get` when:

- The page is mostly server-rendered
- The content is likely already present in raw HTML
- The target is an article page with a stable content container

Use `extract fetch` when:

- Static HTML does not contain the real content
- The site depends on JavaScript rendering
- The page content appears only after runtime hydration

Use `extract stealthy-fetch` when:

- `fetch` still fails
- The target site shows challenge or anti-bot behavior

## WeChat Extraction Pattern

For `mp.weixin.qq.com` public article pages:

- Start with `extract get`
- Use the selector `#js_content`
- Validate the saved file immediately

Example:

```bash
scrapling extract get 'https://mp.weixin.qq.com/s/ARTICLE_ID?scene=1' article.md -s '#js_content'
```

Observed behavior:

- The static fetch can already contain the real article body
- Browser-backed fetch is often unnecessary for article extraction

## Smoke Test Commands

Resolve `SCRAPLING_SKILL_DIR` through the
[diagnostic entry](../SKILL.md#step-1-diagnose-the-install) before using these commands.

### Basic diagnosis

```bash
python3 "$SCRAPLING_SKILL_DIR/scripts/diagnose_scrapling.py"
```

### Static extraction smoke test

```bash
python3 "$SCRAPLING_SKILL_DIR/scripts/diagnose_scrapling.py" --url 'https://example.com'
```

### WeChat article smoke test

```bash
python3 "$SCRAPLING_SKILL_DIR/scripts/diagnose_scrapling.py" \
  --url 'https://mp.weixin.qq.com/s/ARTICLE_ID?scene=1' \
  --selector '#js_content'
```

### Dynamic extraction smoke test

```bash
python3 "$SCRAPLING_SKILL_DIR/scripts/diagnose_scrapling.py" \
  --url 'https://example.com' \
  --dynamic
```

### Validate saved output

Use the path printed under `Smoke Test Output` for the diagnostic's result.
Retain each invocation's separate temporary directory for inspection; later
smoke tests do not replace earlier results. Treat `failed`, `missing output file`
or `empty` as unsuccessful extraction even when another file from an earlier run
contains valid content.

```bash
SMOKE_OUTPUT='<absolute output path printed under Smoke Test Output>'
wc -c "$SMOKE_OUTPUT"
sed -n '1,40p' "$SMOKE_OUTPUT"
```

# Scrapling Troubleshooting

## Contents

- Installation modes
- Verified failure modes
- Static vs dynamic fetch choice
- WeChat extraction pattern
- Smoke test commands

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

Success signals:

- `scrapling install` later reports `The dependencies are already installed`
- Browser caches contain both:
  - `chromium-*`
  - `chromium_headless_shell-*`

Typical cache roots:

- `~/Library/Caches/ms-playwright/`
- `~/.cache/ms-playwright/`

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

### Basic diagnosis

```bash
python3 scripts/diagnose_scrapling.py
```

### Static extraction smoke test

```bash
python3 scripts/diagnose_scrapling.py --url 'https://example.com'
```

### WeChat article smoke test

```bash
python3 scripts/diagnose_scrapling.py \
  --url 'https://mp.weixin.qq.com/s/ARTICLE_ID?scene=1' \
  --selector '#js_content'
```

### Dynamic extraction smoke test

```bash
python3 scripts/diagnose_scrapling.py \
  --url 'https://example.com' \
  --dynamic
```

### Validate saved output

```bash
wc -c article.md
sed -n '1,40p' article.md
rg -n '<title>|js_content|main|rich_media_title' page.html
```

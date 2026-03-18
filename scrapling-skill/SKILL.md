---
name: scrapling-skill
description: Install, troubleshoot, and use Scrapling CLI to extract HTML, Markdown, or text from webpages. Use this skill whenever the user mentions Scrapling, `uv tool install scrapling`, `scrapling extract`, WeChat/mp.weixin articles, browser-backed page fetching, or needs help deciding between static and dynamic extraction.
---

# Scrapling Skill

## Overview

Use Scrapling through its CLI as the default path. Start with the smallest working command, validate the saved output, and only escalate to browser-backed fetching when the static fetch does not contain the real page content.

Do not assume the user's Scrapling install is healthy. Verify it first.

## Default Workflow

Copy this checklist and keep it updated while working:

```text
Scrapling Progress:
- [ ] Step 1: Diagnose the local Scrapling install
- [ ] Step 2: Fix CLI extras or browser runtime if needed
- [ ] Step 3: Choose static or dynamic fetch
- [ ] Step 4: Save output to a file
- [ ] Step 5: Validate file size and extracted content
- [ ] Step 6: Escalate only if the previous path failed
```

## Step 1: Diagnose the Install

Run the bundled diagnostic script first:

```bash
python3 scripts/diagnose_scrapling.py
```

Use the result as the source of truth for the next step.

## Step 2: Fix the Install

### If the CLI was installed without extras

If `scrapling --help` fails with missing `click` or a message about installing Scrapling with extras, reinstall it with the CLI extra:

```bash
uv tool uninstall scrapling
uv tool install 'scrapling[shell]'
```

Do not default to `scrapling[all]` unless the user explicitly needs the broader feature set.

### If browser-backed fetchers are needed

Install the Playwright runtime:

```bash
scrapling install
```

If the install looks slow or opaque, read `references/troubleshooting.md` before guessing. Do not claim success until either:
- `scrapling install` reports that dependencies are already installed, or
- the diagnostic script confirms both Chromium and Chrome Headless Shell are present.

## Step 3: Choose the Fetcher

Use this decision rule:

- Start with `extract get` for normal pages, article pages, and most WeChat public articles.
- Use `extract fetch` when the static HTML does not contain the real content or the page depends on JavaScript rendering.
- Use `extract stealthy-fetch` only after `fetch` still fails because of anti-bot or challenge behavior. Do not make it the default.

## Step 4: Run the Smallest Useful Command

Always quote URLs in shell commands. This is mandatory in `zsh` when the URL contains `?`, `&`, or other special characters.

### Full page to HTML

```bash
scrapling extract get 'https://example.com' page.html
```

### Main content to Markdown

```bash
scrapling extract get 'https://example.com' article.md -s 'main'
```

### JS-rendered page with browser automation

```bash
scrapling extract fetch 'https://example.com' page.html --timeout 20000
```

### WeChat public article body

Use `#js_content` first. This is the default selector for article body extraction on `mp.weixin.qq.com` pages.

```bash
scrapling extract get 'https://mp.weixin.qq.com/s/ARTICLE_ID?scene=1' article.md -s '#js_content'
```

## Step 5: Validate the Output

After every extraction, verify the file instead of assuming success:

```bash
wc -c article.md
sed -n '1,40p' article.md
```

For HTML output, check that the expected title, container, or selector target is actually present:

```bash
rg -n '<title>|js_content|rich_media_title|main' page.html
```

If the file is tiny, empty, or missing the expected container, the extraction did not succeed. Go back to Step 3 and switch fetchers or selectors.

## Step 6: Handle Known Failure Modes

### Local TLS trust store problem

If `extract get` fails with `curl: (60) SSL certificate problem`, treat it as a local trust-store problem first, not a Scrapling content failure.

Retry the same command with:

```bash
--no-verify
```

Only do this after confirming the failure matches the local certificate verification error pattern. Do not silently disable verification by default.

### WeChat article pages

For `mp.weixin.qq.com`:
- Try `extract get` before `extract fetch`
- Use `-s '#js_content'` for the article body
- Validate the saved Markdown or HTML immediately

### Browser-backed fetch failures

If `extract fetch` fails:
1. Re-check the install with `python3 scripts/diagnose_scrapling.py`
2. Confirm Chromium and Chrome Headless Shell are present
3. Retry with a slightly longer timeout
4. Escalate to `stealthy-fetch` only if the site behavior justifies it

## Command Patterns

### Diagnose and smoke test a URL

```bash
python3 scripts/diagnose_scrapling.py --url 'https://example.com'
```

### Diagnose and smoke test a WeChat article body

```bash
python3 scripts/diagnose_scrapling.py \
  --url 'https://mp.weixin.qq.com/s/ARTICLE_ID?scene=1' \
  --selector '#js_content' \
  --no-verify
```

### Diagnose and smoke test a browser-backed fetch

```bash
python3 scripts/diagnose_scrapling.py \
  --url 'https://example.com' \
  --dynamic
```

## Guardrails

- Do not tell the user to reinstall blindly. Verify first.
- Do not default to the Python library API when the user is clearly asking about the CLI.
- Do not jump to browser-backed fetching unless the static result is missing the real content.
- Do not claim success from exit code alone. Inspect the saved file.
- Do not hardcode user-specific absolute paths into outputs or docs.

## Resources

- Installation and smoke test helper: `scripts/diagnose_scrapling.py`
- Verified failure modes and recovery paths: `references/troubleshooting.md`

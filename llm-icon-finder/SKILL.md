---
name: llm-icon-finder
description: Finding and accessing AI/LLM model brand icons from lobe-icons library. Use when users need icon URLs, want to download brand logos for AI models/providers/applications (Claude, GPT, Gemini, etc.), or request icons in SVG/PNG/WEBP formats.
---

# Finding AI/LLM Brand Icons

Access AI/LLM model brand icons and logos from the [lobe-icons](https://github.com/lobehub/lobe-icons) library. The library contains 100+ icons for models (Claude, GPT, Gemini), providers (OpenAI, Anthropic, Google), and applications (ComfyUI, LobeChat).

## Icon Formats and Variants

**Available formats**: SVG (scalable), PNG (raster), WEBP (compressed)
**Theme variants**: light, dark, and color (some icons)

## CDN URL Patterns

Construct URLs using these patterns:

```
# SVG
https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-svg/{light|dark}/{icon-name}.svg

# PNG
https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/{light|dark}/{icon-name}.png

# WEBP
https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-webp/{light|dark}/{icon-name}.webp

# Color variant (append -color to icon-name)
https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/dark/{icon-name}-color.png
```

**Icon naming convention**: Lowercase, hyphenated (e.g., `claude`, `chatglm`, `openai`, `huggingface`)

## Workflow

When users request icons:

1. Identify icon name (usually lowercase company/model name, hyphenated if multi-word)
2. Determine format (default: PNG) and theme (default: dark)
3. Construct CDN URL using pattern above
4. Provide URL to user
5. If download requested, use Bash tool with curl
6. Include web viewer link: `https://lobehub.com/icons/{icon-name}`

## Finding Icon Names

**Common icons**: See `references/icons-list.md` for comprehensive list organized by category (Models, Providers, Applications, Chinese AI)

**Uncertain names**:
- Browse https://lobehub.com/icons
- Try variations (e.g., company name vs product name: `alibaba` vs `alibabacloud`)
- Check for `-color` variants if standard URL fails

**Chinese AI models**: Support Chinese queries (e.g., "智谱" → `chatglm`, "月之暗面" → `moonshot`)

## Examples

**Single icon request**:
```
User: "Claude icon"
→ Provide: https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/dark/claude.png
→ Also mention color variant and web viewer link
```

**Multiple icons download**:
```bash
curl -o openai.svg "https://raw.githubusercontent.com/lobehub/lobe-icons/.../dark/openai.svg"
curl -o anthropic.svg "https://raw.githubusercontent.com/lobehub/lobe-icons/.../dark/anthropic.svg"
```

**Chinese query**:
```
User: "找一下智谱的图标"
→ Identify: 智谱 = ChatGLM → icon name: chatglm
→ Provide URLs and mention related icons (zhipu, codegeex)
```

## Troubleshooting

If URL returns 404:
1. Try `-color` suffix variant
2. Check alternate naming (e.g., `chatgpt` vs `gpt`, `google` vs `gemini`)
3. Direct user to https://lobehub.com/icons to browse
4. Search repository: https://github.com/lobehub/lobe-icons

## Reference Files

- `references/icons-list.md` - Comprehensive list of 100+ available icons by category
- `references/developer-info.md` - npm installation and React usage examples

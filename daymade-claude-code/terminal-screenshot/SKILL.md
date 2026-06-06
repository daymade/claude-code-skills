---
name: terminal-screenshot
description: >
  Render a terminal CLI program's colored output to a PNG so Claude can actually
  SEE the real visual result — color contrast, alignment, background blocks,
  highlighting — instead of only reading plain text and raw ANSI escape codes.
  Use this whenever verifying or debugging how a CLI tool looks in the terminal:
  delta git diff colors, bat syntax highlighting, starship prompt, eza/ls colors,
  git diff, ripgrep matches, or any ANSI-colored output. ALWAYS use it right after
  changing any CLI color config (delta / bat / themes / lazygit pager) to visually
  confirm the result rather than guessing from hex values — reading a hex code is
  not the same as seeing the rendered contrast on the real terminal background.
  Trigger phrases: 看终端效果, 终端截图, 验证配色, 配色对比, 终端真实效果,
  terminal screenshot, render terminal output, ANSI to image, "does this color
  look right", "is the contrast enough", delta/bat color verification.
---

# Terminal Screenshot

Render the colored output of a terminal command into a PNG image, then read that
image to judge the result visually.

## Why this exists

When a command's output arrives as a tool result, Claude sees plain text plus raw
escape codes like `\x1b[48;2;92;30;34m` — not the rendered colors. That makes it
impossible to honestly answer "is the diff's add/remove contrast strong enough?"
or "did this theme come out too dark?". Reading hex values is guessing. This skill
turns the output into an image so the judgement is based on what a human would
actually see on screen.

## The method: capture, then render

Two separate steps. Keep them separate — that separation is the whole trick.

### Step 1 — Capture full-fidelity ANSI to a file

Most CLIs **drop or downgrade colors when they detect they're not writing to a
real terminal** (a pipe or a child process). Force full coloring and save to a
`.ansi` file. The exact flag depends on the tool — recipes below.

The single most important rule: **never let the renderer run the command for you.**
`freeze --execute "git diff | delta"` looks convenient but produces a *degraded*
result — delta (and lazygit, and anything that probes terminal capabilities) runs
inside freeze's child pty, detects a reduced environment, and silently drops its
background blocks, line-number column, and header box. Capture in a normal shell
first, render second.

### Step 2 — Render the ANSI file to PNG, then read it

Use the bundled wrapper, which prefers `freeze` and falls back to a stdlib
renderer + headless Chrome:

```bash
scripts/render_ansi.sh <input.ansi> <output.png> [background_hex]
```

Then read the PNG with the Read tool and judge the colors.

**Background color must match the real terminal**, or a dark theme verified on a
white page looks wrong. On macOS with Ghostty:

```bash
ghostty +show-config --default | grep '^background'   # e.g. 282c34 (the default)
```

Pass it as `#282c34`. If unknown, a dark terminal is usually near `#1d1f21`–`#282c34`.

## Capture recipes per tool

Pick a `--width` close to the real terminal (≈100–120) so wrapping matches.

| Tool | Capture command (writes full-color ANSI) |
|------|------------------------------------------|
| **delta** (git diff) | `git --no-pager diff \| delta --dark --line-numbers --width=110 > /tmp/x.ansi` |
| **git diff** (native) | `git -c color.ui=always --no-pager diff > /tmp/x.ansi` |
| **bat** | `bat --color=always --style=numbers <file> > /tmp/x.ansi` |
| **eza** | `eza -la --color=always --icons > /tmp/x.ansi` |
| **ls** (GNU) | `ls -la --color=always > /tmp/x.ansi` |
| **ls** (macOS/BSD) | `CLICOLOR_FORCE=1 ls -laG > /tmp/x.ansi` |
| **ripgrep** | `rg --color=always 'pattern' <path> > /tmp/x.ansi` |
| **anything else** | `CLICOLOR_FORCE=1 <cmd> > /tmp/x.ansi` or `<cmd> --color=always`, or wrap in a real pty: `script -q /dev/null <cmd>` |

Note `delta` always emits its configured colors even to a file, so the only trap
for delta is Step 1's rule (don't render it via `freeze --execute`).

### Full example: verify a delta color change

```bash
# after editing [delta] colors in gitconfig, in any repo with a diff:
git --no-pager diff | delta --dark --line-numbers --width=110 > /tmp/diff.ansi
scripts/render_ansi.sh /tmp/diff.ansi /tmp/diff.png "#282c34"
# then: Read /tmp/diff.png and judge whether add/remove contrast is clear
```

## TUI programs (lazygit, htop, top) — out of scope

Full-screen TUIs paint with cursor positioning, not a linear ANSI stream, so they
can't be captured this way. To check a TUI's *colors*, verify the underlying piece
in isolation — e.g. for lazygit's diff, render `git diff | delta` as above (lazygit
calls the same delta config). For a true TUI screenshot, run it in a real terminal
and capture the screen (a screencapture/computer-use task), not this skill.

## Installing freeze (the preferred renderer)

`freeze` is [charmbracelet/freeze](https://github.com/charmbracelet/freeze) — it
renders ANSI to PNG/SVG/WebP with faithful background blocks and nice chrome.

**Do not run `brew install freeze`** — that installs an unrelated GUI app of the
same name (a cask). The CLI lives in charmbracelet's tap or via `go install`:

```bash
# Option A — Homebrew tap (needs GitHub reachable)
brew install charmbracelet/tap/freeze

# Option B — go install (works behind a firewall via a Go module mirror)
GOPROXY=https://goproxy.cn,direct GOSUMDB=off \
  go install github.com/charmbracelet/freeze@latest
# binary lands in "$(go env GOPATH)/bin/freeze"
```

`GOSUMDB=off` is needed when the checksum database (`sum.golang.org`) is
unreachable and `go install` hangs on "verifying module ... 504".

If freeze can't be installed, the wrapper automatically falls back to the bundled
`scripts/ansi2html.py` (stdlib only) + headless Chrome — no extra dependency
beyond a Chrome install. The fallback uses a fixed window size; widen
`--window-size` in `render_ansi.sh` if output is clipped.

## Bundled scripts

- `scripts/render_ansi.sh` — render a captured `.ansi` file to PNG (freeze, else
  Chrome fallback). This is the entry point; call it after Step 1.
- `scripts/ansi2html.py` — stdlib ANSI→HTML converter used by the fallback path.
  Handles 24-bit truecolor, 256-color, bold, and resets, preserving background
  color blocks (the part naive renderers drop).

## Common pitfalls

- **Letting the renderer run the command** (`freeze --execute "delta …"`) →
  degraded output. Capture in a normal shell first, render the file second.
- **Non-TTY strips color** → force it (`--color=always` / `CLICOLOR_FORCE=1` /
  `script -q /dev/null`).
- **Wrong background color** → a dark CLI theme rendered on a white page misjudges
  contrast. Use the real terminal background.
- **Light/dark mismatch** → if the terminal is dark, the CLI's colors must be its
  dark variant. Verifying a `light=true` config against a dark terminal shows
  inverted, hard-to-read colors (and is itself the bug, not the renderer's fault).
- **`brew install freeze`** installs the wrong (GUI cask) tool — use the tap or
  `go install`.

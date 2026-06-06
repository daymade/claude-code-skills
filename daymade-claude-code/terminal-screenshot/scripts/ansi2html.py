#!/usr/bin/env python3
"""Render an ANSI-colored text file to a standalone HTML page (stdlib only).

Fallback renderer for when charmbracelet/freeze is unavailable. Parses the SGR
subset that real CLI tools emit: 24-bit truecolor (38;2;r;g;b / 48;2;r;g;b),
256-color (38;5;n / 48;5;n with xterm palette -> RGB), bold (1), and the resets
(0 / 39 / 49). Background color blocks (48;...) are preserved faithfully — that is
the whole point, since tools like delta encode add/remove as background blocks.

Usage: ansi2html.py <input.ansi> <background_hex> <output.html>
"""
import sys
import re
import html as H


def xterm256(n):
    """Map an xterm-256 palette index to an (r, g, b) tuple."""
    base = [
        (0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (0, 0, 238),
        (205, 0, 205), (0, 205, 205), (229, 229, 229), (127, 127, 127),
        (255, 0, 0), (0, 255, 0), (255, 255, 0), (92, 92, 255),
        (255, 0, 255), (0, 255, 255), (255, 255, 255),
    ]
    if n < 16:
        return base[n]
    if n >= 232:
        v = 8 + (n - 232) * 10
        return (v, v, v)
    n -= 16
    r, g, b = n // 36, (n % 36) // 6, n % 6
    conv = lambda x: 0 if x == 0 else 55 + x * 40
    return (conv(r), conv(g), conv(b))


def rgb(t):
    return f"rgb({t[0]},{t[1]},{t[2]})"


def main():
    if len(sys.argv) < 4:
        sys.exit("usage: ansi2html.py <input.ansi> <background_hex> <output.html>")
    ansi_file, bg, out_html = sys.argv[1], sys.argv[2], sys.argv[3]
    fg = "#c5c8c6"  # default foreground for unstyled text on a dark background

    text = open(ansi_file, encoding="utf-8", errors="replace").read()
    parts = re.split(r"(\x1b\[[0-9;]*m)", text)
    cur_fg = cur_bg = None
    bold = False
    out = []
    for p in parts:
        if p.startswith("\x1b["):
            codes = p[2:-1].split(";")
            if codes == [""]:
                codes = ["0"]
            i = 0
            while i < len(codes):
                c = codes[i]
                if c in ("0", ""):
                    cur_fg = cur_bg = None
                    bold = False
                elif c == "1":
                    bold = True
                elif c == "22":
                    bold = False
                elif c == "39":
                    cur_fg = None
                elif c == "49":
                    cur_bg = None
                elif c == "38" and i + 1 < len(codes):
                    if codes[i + 1] == "2":
                        cur_fg = rgb((int(codes[i + 2]), int(codes[i + 3]), int(codes[i + 4])))
                        i += 4
                    elif codes[i + 1] == "5":
                        cur_fg = rgb(xterm256(int(codes[i + 2])))
                        i += 2
                elif c == "48" and i + 1 < len(codes):
                    if codes[i + 1] == "2":
                        cur_bg = rgb((int(codes[i + 2]), int(codes[i + 3]), int(codes[i + 4])))
                        i += 4
                    elif codes[i + 1] == "5":
                        cur_bg = rgb(xterm256(int(codes[i + 2])))
                        i += 2
                i += 1
        elif p:
            style = []
            if cur_fg:
                style.append(f"color:{cur_fg}")
            if cur_bg:
                style.append(f"background:{cur_bg}")
            if bold:
                style.append("font-weight:bold")
            esc = H.escape(p)
            out.append(f'<span style="{";".join(style)}">{esc}</span>' if style else esc)

    doc = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>\n'
        f"body{{margin:0;padding:18px;background:{bg}}}\n"
        'pre{margin:0;font-family:"JetBrains Mono",Menlo,Consolas,monospace;'
        f"font-size:15px;line-height:1.55;color:{fg};white-space:pre}}\n"
        "</style></head><body><pre>" + "".join(out) + "</pre></body></html>"
    )
    open(out_html, "w", encoding="utf-8").write(doc)
    print(out_html)


if __name__ == "__main__":
    main()

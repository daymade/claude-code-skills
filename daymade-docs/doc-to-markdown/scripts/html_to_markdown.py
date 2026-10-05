#!/usr/bin/env python3
"""Local HTML conversion through Pandoc, with source-to-output link verification."""

from collections import Counter
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_OMIT = frozenset({"script", "style", "template"})


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)
    start: str = ""


class HTMLTree(HTMLParser):
    """Keep element boundaries without adding a parser dependency."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs), start=self.get_starttag_text())
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def elements(node):
    yield node
    for child in node.children:
        if isinstance(child, Element):
            yield from elements(child)


def select_content(tree, selector=None):
    """Select exactly one tag, #id or .class; default keeps the entire body."""
    if selector:
        if not re.fullmatch(r"(?:[a-zA-Z][\w-]*|[#.][\w-]+)", selector):
            raise ValueError("HTML selector supports one tag, #id or .class only")
        def matches(node):
            if selector.startswith("#"):
                return node.attrs.get("id") == selector[1:]
            if selector.startswith("."):
                return selector[1:] in (node.attrs.get("class") or "").split()
            return node.tag == selector.lower()
        found = [node for node in elements(tree) if matches(node)]
        if len(found) != 1:
            raise ValueError(f"HTML selector {selector!r} matched {len(found)} elements; expected exactly one")
        return found[0]
    bodies = [node for node in elements(tree) if node.tag == "body"]
    if len(bodies) > 1:
        raise ValueError("HTML has multiple bodies; choose content with --html-selector")
    return bodies[0] if bodies else tree


def prepare_html(source, selector=None):
    parser = HTMLTree()
    parser.feed(source)
    parser.close()
    content = select_content(parser.root, selector)
    expected = Counter()

    def render(node, in_svg=False):
        if isinstance(node, str):
            return escape(node, quote=False)
        if (node.tag in _OMIT and not (node.tag == "style" and in_svg)) or node.tag == "head":
            return ""
        if node.tag == "a" and node.attrs.get("href"):
            expected[node.attrs["href"]] += 1
        if node.tag == "figcaption":
            # A bold caption title and its following description are distinct blocks.
            groups = []
            current = []
            for child in node.children:
                if isinstance(child, str) and not child.strip() and not current:
                    continue
                if isinstance(child, Element) and child.tag in {"strong", "b"} and not current and not groups:
                    groups.append(f"<p>{render(child)}</p>")
                else:
                    current.append(render(child))
            if current:
                groups.append("<p>" + "".join(current) + "</p>")
            return "".join(groups)
        inner = "".join(render(child, in_svg or node.tag == "svg") for child in node.children)
        if node.tag in {"document", "html", "body"}:
            return inner
        # Pandoc's figure handling can duplicate captions as image alt text.
        # Preserve the caption as a separate block, including inline links.
        if node.tag == "figure":
            return inner
        if node.tag == "a" and not in_svg:
            # GFM has no styling attributes on links; Pandoc otherwise emits a raw
            # HTML anchor instead of a Markdown hyperlink for class-bearing cards.
            attrs = "".join(f' {key}="{escape(value, quote=True)}"'
                            for key, value in node.attrs.items()
                            if key in {"href", "title"} and value is not None)
            anchor_id = node.attrs.get("id")
            prefix = f'<a id="{escape(anchor_id, quote=True)}"></a>' if anchor_id else ""
            return prefix + f"<a{attrs}>{inner}</a>"
        start = node.start or f"<{node.tag}>"
        original_tag = re.match(r"<([\w:-]+)", start).group(1)
        rendered = start + inner + ("" if node.tag in _VOID or start.rstrip().endswith("/>")
                                    else f"</{original_tag}>")
        if node.tag == "svg" and not in_svg:
            # Pandoc's HTML reader lowercases SVG attributes (including viewBox).
            # Encode the untouched SVG markup first, without rasterizing it.
            if "xmlns" not in node.attrs:
                rendered = rendered.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
            encoded = base64.b64encode(rendered.encode("utf-8")).decode("ascii")
            return f'<img src="data:image/svg+xml;base64,{encoded}" />'
        return rendered

    return render(content), expected


def _pandoc(text, source_format, target_format, extra_args=()):
    result = subprocess.run(
        ["pandoc", "-f", source_format, "-t", target_format, "--wrap=none", *extra_args],
        input=text, capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise ValueError(f"Pandoc {source_format}→{target_format} failed: {result.stderr.strip()}")
    return result.stdout


def normalize_href(href):
    # Pandoc percent-encodes spaces/non-ASCII; keep encoded URI delimiters distinct.
    return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group().upper(),
                  quote(href, safe="/:@?#[]!$&'()*+,;=%"))


def markdown_links(markdown):
    """Read actual link nodes, so fenced text and broken Markdown cannot pass."""
    ast = json.loads(_pandoc(markdown, "gfm", "json"))
    links = Counter()
    def visit(value):
        if isinstance(value, dict):
            if value.get("t") == "Link":
                links[normalize_href(value["c"][-1][0])] += 1
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(ast)
    return links


def verify_links(expected, markdown):
    actual = markdown_links(markdown)
    normalized = Counter()
    for href, count in expected.items():
        normalized[normalize_href(href)] += count
    missing = normalized - actual
    if missing:
        detail = "; ".join(f"{href!r} ({count} missing)" for href, count in sorted(missing.items()))
        raise ValueError(f"HTML hyperlink verification failed: {detail}")
    return sum(normalized.values())


def convert_html(file_path: Path, selector=None, heading_offset=0):
    """Return verified GFM; keep asset targets unchanged and never fetch them."""
    source = file_path.read_text(encoding="utf-8-sig")
    prepared, expected = prepare_html(source, selector)
    if not 0 <= heading_offset <= 5:
        raise ValueError("HTML heading offset must be between 0 and 5")
    parser = HTMLTree()
    parser.feed(prepared)
    if any(re.fullmatch(r"h[1-6]", node.tag) and int(node.tag[1]) + heading_offset > 6
           for node in elements(parser.root)):
        raise ValueError("HTML heading offset would exceed heading level 6")
    markdown = _pandoc(prepared, "html", "gfm",
                       [f"--shift-heading-level-by={heading_offset}"])
    verify_links(expected, markdown)
    return markdown


def main():
    parser = argparse.ArgumentParser(description="Verify saved Markdown hyperlinks against local source HTML")
    parser.add_argument("source", type=Path)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--html-selector")
    args = parser.parse_args()
    try:
        _, expected = prepare_html(args.source.read_text(encoding="utf-8-sig"), args.html_selector)
        count = verify_links(expected, args.markdown.read_text(encoding="utf-8"))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"HTML links verified: {count} source hyperlinks present as Markdown links")


if __name__ == "__main__":
    main()

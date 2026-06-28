#!/usr/bin/env python3
"""Extract public WPS/KDocs ProcessOn mind maps into source JSON and Markdown."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)
PROCESSON_API_BASE = "https://wps.processon.com/wpsapi/diagrams/view/api"
KDOCS_LINK_RE = re.compile(r"https?://(?:www\.)?kdocs\.cn/(?:view/)?l/([^/?#]+)")


class ExtractionError(RuntimeError):
    pass


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.kdocs.cn/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise ExtractionError(f"HTTP {exc.code} while fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise ExtractionError(f"Network error while fetching {url}: {exc.reason}") from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionError(f"Non-UTF-8 response from {url}") from exc

    if "用户未登录" in text or "login" in text.lower() and "definition" not in text:
        raise ExtractionError(f"Response looks like a login wall: {url}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        snippet = text[:200].replace("\n", " ")
        raise ExtractionError(f"Response is not JSON from {url}: {snippet}") from exc

    if isinstance(data, dict):
        return data
    raise ExtractionError(f"JSON response is not an object: {url}")


def first_payload(obj: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "result"):
        value = obj.get(key)
        if isinstance(value, dict) and (
            "definition" in value or "fileinfo" in value or "fileId" in value
        ):
            return value
    return obj


def find_dict_with_any_key(obj: Any, keys: set[str]) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if any(key in obj for key in keys):
            return obj
        for value in obj.values():
            found = find_dict_with_any_key(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_dict_with_any_key(value, keys)
            if found is not None:
                return found
    return None


def one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def strip_known_extension(name: str | None) -> str | None:
    if not name:
        return None
    for suffix in (".pof", ".pos", ".processon"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def person_name(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("name", "userName", "username", "displayName", "id"):
            if value.get(key) is not None:
                return clean_text(value.get(key)) or None
        return None
    return clean_text(value) or None


def safe_filename(value: str, fallback: str = "wps-processon") -> str:
    value = clean_text(value).splitlines()[0] if value else ""
    value = re.sub(r'[\\/:*?"<>|]+', "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return (value or fallback)[:140]


def build_processon_api_url(query: dict[str, list[str]]) -> str:
    required = ["file_id", "group_id"]
    missing = [key for key in required if not one(query, key)]
    if missing:
        raise ExtractionError(f"ProcessOn URL is missing required query keys: {', '.join(missing)}")
    return PROCESSON_API_BASE + "?" + urllib.parse.urlencode(query, doseq=True)


def resolve_source(url: str, timeout: int) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    result: dict[str, Any] = {
        "source_url": url,
        "source_type": "unknown",
        "kdocs_share_id": None,
        "kdocs_link_api_url": None,
        "kdocs_link_json": None,
        "processon_api_url": None,
        "file_id": None,
        "group_id": None,
        "link_title": None,
        "creator": None,
    }

    if host.endswith("kdocs.cn"):
        match = KDOCS_LINK_RE.search(url)
        if not match:
            raise ExtractionError("KDocs URL does not match /view/l/<share_id> or /l/<share_id>")
        share_id = match.group(1)
        link_api_url = f"https://drive.kdocs.cn/api/v5/links/{share_id}?review=true"
        link_json = fetch_json(link_api_url, timeout)
        link_payload = first_payload(link_json)
        fileinfo = link_payload.get("fileinfo")
        if not isinstance(fileinfo, dict):
            fileinfo = find_dict_with_any_key(link_payload, {"groupid", "group_id", "fname", "id"})
        if not isinstance(fileinfo, dict):
            raise ExtractionError("KDocs link metadata did not include fileinfo")

        file_id = str(fileinfo.get("id") or fileinfo.get("file_id") or "").strip()
        group_id = str(fileinfo.get("groupid") or fileinfo.get("group_id") or "").strip()
        if not file_id or not group_id:
            raise ExtractionError("KDocs link metadata did not include file id and group id")

        query = {
            "file_id": [file_id],
            "group_id": [group_id],
            "is_recycle": ["false"],
            "user_id": ["0"],
            "product": ["kdocs_web"],
            "platform": [""],
            "lang": ["en-US"],
        }
        result.update(
            {
                "source_type": "kdocs_processon",
                "kdocs_share_id": share_id,
                "kdocs_link_api_url": link_api_url,
                "kdocs_link_json": link_json,
                "processon_api_url": build_processon_api_url(query),
                "file_id": file_id,
                "group_id": group_id,
                "link_title": strip_known_extension(fileinfo.get("fname")),
                "creator": person_name(
                    link_payload.get("creator")
                    or fileinfo.get("creator")
                    or fileinfo.get("creator_name")
                ),
            }
        )
        return result

    if "processon.com" in host:
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "/wpsapi/diagrams/view/api" in parsed.path:
            result.update(
                {
                    "source_type": "processon_api",
                    "processon_api_url": url,
                    "file_id": one(query, "file_id"),
                    "group_id": one(query, "group_id"),
                }
            )
            return result

        if "/diagrams/view" in parsed.path:
            result.update(
                {
                    "source_type": "processon_view",
                    "processon_api_url": build_processon_api_url(query),
                    "file_id": one(query, "file_id"),
                    "group_id": one(query, "group_id"),
                }
            )
            return result

    raise ExtractionError("Unsupported URL. Expected kdocs.cn public link or wps.processon.com view/API URL.")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def collect_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        out.append(node)
        children = node.get("children")
        if isinstance(children, list):
            out.extend(collect_nodes([child for child in children if isinstance(child, dict)]))
    return out


def index_comments(comments: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_node: dict[str, list[dict[str, Any]]] = {}
    unmapped: list[dict[str, Any]] = []
    for comment in comments:
        selection = str(comment.get("selectionId") or "")
        node_id = selection.split("_", 1)[0] if selection else ""
        if node_id:
            by_node.setdefault(node_id, []).append(comment)
        else:
            unmapped.append(comment)
    return by_node, unmapped


def format_comment(comment: dict[str, Any]) -> str:
    user = clean_text(comment.get("userName")) or "unknown"
    created = clean_text(comment.get("createTime"))
    text = clean_text(comment.get("text")) or "(empty)"
    meta = f"{user}"
    if created:
        meta += f", {created}"
    return f"{meta}: {text}"


def append_wrapped_lines(out: list[str], indent: str, prefix: str, text: str) -> None:
    lines = text.splitlines() or [""]
    out.append(f"{indent}{prefix}{lines[0]}")
    for line in lines[1:]:
        out.append(f"{indent}{' ' * len(prefix)}{line}")


def render_node(
    node: dict[str, Any],
    out: list[str],
    comments_by_node: dict[str, list[dict[str, Any]]],
    depth: int = 0,
) -> None:
    indent = "  " * depth
    title = clean_text(node.get("title")) or "(untitled)"
    append_wrapped_lines(out, indent, "- ", title)

    summaries = node.get("summaries")
    if isinstance(summaries, list):
        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            summary_text = clean_text(summary.get("title"))
            if summary_text:
                label = "摘要"
                if summary.get("range"):
                    label += f"（range {summary.get('range')}）"
                append_wrapped_lines(out, indent + "  ", f"- {label}: ", summary_text)

    for comment in comments_by_node.get(str(node.get("id")), []):
        append_wrapped_lines(out, indent + "  ", "- 评论: ", format_comment(comment))

    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                render_node(child, out, comments_by_node, depth + 1)


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    return json.dumps(str(value), ensure_ascii=False)


def payload_file_id(source: dict[str, Any], api_payload: dict[str, Any]) -> Any:
    request_params = api_payload.get("requestParamKS")
    if not isinstance(request_params, dict):
        request_params = {}
    return (
        source.get("file_id")
        or api_payload.get("fileId")
        or api_payload.get("file_id")
        or api_payload.get("wpsFileId")
        or request_params.get("fileId")
        or request_params.get("file_id")
    )


def payload_group_id(source: dict[str, Any], api_payload: dict[str, Any]) -> Any:
    request_params = api_payload.get("requestParamKS")
    if not isinstance(request_params, dict):
        request_params = {}
    return (
        source.get("group_id")
        or api_payload.get("groupId")
        or api_payload.get("group_id")
        or request_params.get("groupId")
        or request_params.get("group_id")
    )


def build_markdown(
    definition: dict[str, Any],
    source: dict[str, Any],
    api_payload: dict[str, Any],
    manifest_name: str,
    title_override: str | None = None,
) -> str:
    title = (
        clean_text(title_override)
        or clean_text(definition.get("title"))
        or clean_text(source.get("link_title"))
        or "WPS ProcessOn"
    )
    creator = person_name(source.get("creator") or api_payload.get("creatorName"))
    children = definition.get("children") if isinstance(definition.get("children"), list) else []
    comments = definition.get("comments") if isinstance(definition.get("comments"), list) else []
    comments_by_node, unmapped = index_comments([c for c in comments if isinstance(c, dict)])
    nodes = collect_nodes([node for node in children if isinstance(node, dict)])

    lines: list[str] = [
        "---",
        f"title: {yaml_scalar(title)}",
        f"source_url: {yaml_scalar(source.get('source_url'))}",
        f"source_type: {yaml_scalar(source.get('source_type'))}",
        f"file_id: {yaml_scalar(payload_file_id(source, api_payload))}",
        f"group_id: {yaml_scalar(payload_group_id(source, api_payload))}",
        f"creator: {yaml_scalar(creator)}",
        f"captured_at: {yaml_scalar(dt.datetime.now(dt.timezone.utc).isoformat())}",
        f"capture_manifest: {yaml_scalar(manifest_name)}",
        "---",
        "",
        f"# {title}",
        "",
        "## Source",
        "",
        f"- Source URL: {source.get('source_url')}",
        f"- ProcessOn API: {source.get('processon_api_url')}",
        f"- File ID: {payload_file_id(source, api_payload) or ''}",
        f"- Group ID: {payload_group_id(source, api_payload) or ''}",
    ]
    if source.get("kdocs_link_api_url"):
        lines.append(f"- KDocs link API: {source.get('kdocs_link_api_url')}")
    if creator:
        lines.append(f"- Creator: {creator}")
    lines.extend(
        [
            "",
            "## Mind Map",
            "",
        ]
    )

    if children:
        for child in children:
            if isinstance(child, dict):
                render_node(child, lines, comments_by_node, 0)
    else:
        lines.append("_No mind-map children were present in the ProcessOn definition._")

    if unmapped:
        lines.extend(["", "## Unmapped Comments", ""])
        for comment in unmapped:
            lines.append(f"- {format_comment(comment)}")

    mapped_count = sum(len(items) for items in comments_by_node.values())
    lines.extend(
        [
            "",
            "## Extraction Notes",
            "",
            "- Markdown was generated from the ProcessOn `definition` JSON without LLM rewriting.",
            f"- Parsed node count: {len(nodes)}",
            f"- Parsed comment count: {len(comments)} ({mapped_count} mapped to node ids, {len(unmapped)} unmapped).",
            "- Capture the rendered SVG/PNG separately when the original visual layout is required.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ExtractionError(f"JSON file is not an object: {path}")
    return value


def extract_definition(api_json: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = first_payload(api_json)
    definition_value = payload.get("definition")
    if isinstance(definition_value, str):
        try:
            definition = json.loads(definition_value)
        except json.JSONDecodeError as exc:
            raise ExtractionError("ProcessOn `definition` is not valid JSON") from exc
    elif isinstance(definition_value, dict):
        definition = definition_value
    else:
        raise ExtractionError("ProcessOn API payload did not include a `definition` object/string")
    if not isinstance(definition, dict):
        raise ExtractionError("ProcessOn definition is not a JSON object")
    return payload, definition


def validate_text_outputs(paths: list[Path]) -> None:
    bad = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if "\ufffd" in text:
            bad.append(str(path))
    if bad:
        raise ExtractionError("Unicode replacement character found in output: " + ", ".join(bad))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="KDocs public link, ProcessOn view URL, or ProcessOn API URL")
    parser.add_argument("--api-json", type=Path, help="Use an existing ProcessOn API JSON file")
    parser.add_argument("--link-json", type=Path, help="Optional existing KDocs link metadata JSON file")
    parser.add_argument("--output-dir", type=Path, required=True, help="Archive output directory")
    parser.add_argument("--title", help="Override output Markdown base name")
    parser.add_argument("--rendered-svg", help="Path or filename for a separately captured SVG")
    parser.add_argument("--rendered-png", help="Path or filename for a separately rendered PNG")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)

    if not args.url and not args.api_json:
        parser.error("Provide --url or --api-json")

    source: dict[str, Any]
    if args.url:
        source = resolve_source(args.url, args.timeout)
    else:
        source = {
            "source_url": None,
            "source_type": "local_processon_api_json",
            "kdocs_share_id": None,
            "kdocs_link_api_url": None,
            "kdocs_link_json": None,
            "processon_api_url": None,
            "file_id": None,
            "group_id": None,
            "link_title": None,
            "creator": None,
        }

    if args.link_json:
        source["kdocs_link_json"] = load_json(args.link_json)

    if args.api_json:
        api_json = load_json(args.api_json)
    else:
        api_url = source.get("processon_api_url")
        if not api_url:
            raise ExtractionError("Could not resolve ProcessOn API URL")
        api_json = fetch_json(str(api_url), args.timeout)

    api_payload, definition = extract_definition(api_json)
    title = args.title or clean_text(definition.get("title")) or clean_text(source.get("link_title")) or "WPS ProcessOn"
    base = safe_filename(title)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    api_path = args.output_dir / "processon-api.json"
    definition_path = args.output_dir / "processon-definition.json"
    manifest_path = args.output_dir / "capture-manifest.json"
    markdown_path = args.output_dir / f"{base}.md"

    write_json(api_path, api_json)
    write_json(definition_path, definition)
    if source.get("kdocs_link_json") is not None:
        write_json(args.output_dir / "kdocs-link-api.json", source["kdocs_link_json"])

    children = definition.get("children") if isinstance(definition.get("children"), list) else []
    comments = definition.get("comments") if isinstance(definition.get("comments"), list) else []
    node_count = len(collect_nodes([node for node in children if isinstance(node, dict)]))
    manifest = {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_url": source.get("source_url"),
        "source_type": source.get("source_type"),
        "kdocs_share_id": source.get("kdocs_share_id"),
        "kdocs_link_api_url": source.get("kdocs_link_api_url"),
        "processon_api_url": source.get("processon_api_url"),
        "file_id": payload_file_id(source, api_payload),
        "group_id": payload_group_id(source, api_payload),
        "title": title,
        "creator": person_name(source.get("creator") or api_payload.get("creatorName")),
        "counts": {
            "nodes": node_count,
            "comments": len(comments),
        },
        "outputs": {
            "processon_api_json": api_path.name,
            "processon_definition_json": definition_path.name,
            "markdown": markdown_path.name,
            "rendered_svg": args.rendered_svg,
            "rendered_png": args.rendered_png,
        },
        "notes": [
            "Markdown is a structural conversion of ProcessOn definition JSON, not an LLM rewrite.",
            "Capture the rendered SVG/PNG separately for the original visual layout.",
        ],
    }
    write_json(manifest_path, manifest)

    markdown = build_markdown(definition, source, api_payload, manifest_path.name, title)
    markdown_path.write_text(markdown, encoding="utf-8")
    validate_text_outputs([api_path, definition_path, manifest_path, markdown_path])

    print(
        json.dumps(
            {
                "ok": True,
                "title": title,
                "node_count": node_count,
                "comment_count": len(comments),
                "outputs": {
                    "api_json": str(api_path),
                    "definition_json": str(definition_path),
                    "manifest": str(manifest_path),
                    "markdown": str(markdown_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExtractionError as exc:
        print(f"wps_processon_extract.py: {exc}", file=sys.stderr)
        raise SystemExit(2)

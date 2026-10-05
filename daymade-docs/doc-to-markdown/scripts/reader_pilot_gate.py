#!/usr/bin/env python3
"""Check retained reader observations and current bytes; never certify UI truth."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from urllib.parse import unquote, urlsplit

import html_to_markdown as html_owner


SCHEMA = 1
LIMIT = ("Evidence completeness and current-byte identity verified; "
         "actual clicks, capture provenance and legibility remain observer claims.")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, name):
    need(isinstance(value, str) and bool(value.strip()), f"{name}: nonempty text required")
    return value


def object_value(value, name):
    need(isinstance(value, dict), f"{name}: object required")
    return value


def list_value(value, name):
    need(isinstance(value, list) and bool(value), f"{name}: nonempty list required")
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest_object(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8"))


def file_hash(path):
    with Path(path).open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def absolute_file(value, name):
    path = Path(text(value, name)).expanduser()
    need(path.is_absolute(), f"{name}: absolute file path required")
    # Resolve system aliases such as /tmp, but reject a final file symlink.
    need(not path.is_symlink(), f"{name}: file symlinks unsupported")
    path = path.resolve(strict=True)
    need(path.is_file(), f"{name}: regular file required")
    return path


def relative(value, name):
    value = text(value, name)
    need("\\" not in value and not value.startswith("/"), f"{name}: relative POSIX path required")
    need(all(part not in {"", ".", ".."} for part in value.split("/")),
         f"{name}: traversal or empty component")
    need(not re.match(r"^[A-Za-z]:", value), f"{name}: drive path unsupported")
    return PurePosixPath(value).as_posix()


def inside(root, value, name):
    rel = relative(value, name)
    path = root / rel
    current = root
    for part in PurePosixPath(rel).parts:
        current /= part
        need(not current.is_symlink(), f"{name}: symlink component unsupported")
    resolved = path.resolve(strict=True)
    need(resolved.is_relative_to(root) and resolved.is_file(), f"{name}: outside root or not a file")
    return resolved


def binding(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": file_hash(path)}


def verify_binding(value, name, nonempty=True):
    value = object_value(value, name)
    path = absolute_file(value.get("path"), f"{name}.path")
    expected = text(value.get("sha256"), f"{name}.sha256")
    need(re.fullmatch(r"[0-9a-f]{64}", expected), f"{name}: invalid sha256")
    need(file_hash(path) == expected, f"{name}: stale bytes")
    if nonempty:
        need(path.stat().st_size > 0, f"{name}: empty artifact")
    return path


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return object_value(json.loads(Path(path).read_text(encoding="utf-8"),
                                   object_pairs_hook=pairs), "JSON root")


def inventory(root):
    root = Path(root).resolve(strict=True)
    need(root.is_dir(), "input_root: directory required")
    files = {}
    for path in sorted(root.rglob("*")):
        need(not path.is_symlink(), f"input_root: symlink unsupported: {path.name}")
        if path.is_dir():
            continue
        need(path.is_file(), "input_root: special file unsupported")
        files[path.relative_to(root).as_posix()] = file_hash(path)
    need(bool(files), "input_root: no files")
    return files


def recipe_identity():
    directory = Path(__file__).resolve().parent
    executable = shutil.which("pandoc")
    need(executable is not None, "Pandoc is required")
    executable = Path(executable).resolve(strict=True)
    version = subprocess.run([str(executable), "--version"], capture_output=True,
                             text=True, check=True, timeout=20).stdout
    return {"name": "existing-html-pandoc-gfm-v1", "manual_postprocessing": False,
            "files": {name: file_hash(directory / name) for name in
                      ("reader_pilot_gate.py", "batch_html.py", "html_to_markdown.py", "convert.py")},
            "pandoc": {"path": str(executable), "sha256": file_hash(executable),
                       "version": version},
            "arguments": ["-f", "html", "-t", "gfm", "--wrap=none"]}


def reader_state(path):
    state = load_json(path)
    for key in ("reader", "version", "mode", "theme", "capture_context"):
        text(state.get(key), f"reader_settings.{key}")
    need(state["mode"] == "reading", "reader_settings.mode must be reading")
    for key in ("body_width_css_px", "device_scale"):
        value = state.get(key)
        need(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0,
             f"reader_settings.{key}: positive number required")
    return state


def local_target(raw, base, root, outputs, navigation=False):
    """Resolve a prepared local dependency; external navigation is permitted."""
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        if navigation and parsed.scheme in {"https", "http", "mailto", "tel"}:
            return
        if not navigation and re.match(r"^data:image/(?:png|jpeg|gif|webp);base64,", raw):
            return
        raise ValueError(f"external dependency unsupported: {raw!r}; materialize it first")
    if not parsed.path:
        return
    target = unquote(parsed.path)
    need("\\" not in target and not target.startswith("/"), f"absolute dependency: {raw!r}")
    resolved = (base / target).resolve()
    need(resolved.is_relative_to(root), f"dependency escapes input_root: {raw!r}")
    if navigation and resolved.relative_to(root).as_posix() in outputs:
        return
    need(resolved.is_file(), f"missing dependency: {raw!r}")
    # Prepared page links must already target the declared final Markdown path.
    need(not (navigation and resolved.suffix.lower() in {".html", ".htm"}),
         f"page link still targets HTML: {raw!r}; prepare the reader target explicitly")
    inside(root, resolved.relative_to(root).as_posix(), "dependency")


def validate_closure(root, pages, files):
    outputs = {p["output"] for p in pages}
    for page in pages:
        need(PurePosixPath(page["source"]).parent == PurePosixPath(page["output"]).parent,
             "source and output directories must match to retain relative targets")
    for rel in files:
        path = root / rel
        if path.suffix.lower() in {".html", ".htm", ".svg"}:
            parser = html_owner.HTMLTree()
            parser.feed(path.read_text(encoding="utf-8-sig"))
            for node in html_owner.elements(parser.root):
                need(node.tag != "base", "HTML base unsupported; resolve prepared targets first")
                need(node.tag != "script", "dynamic scripts unsupported in prepared HTML; retain raw sources separately")
                need(not any(key.startswith("on") for key in node.attrs),
                     "dynamic event handlers unsupported in prepared HTML")
                for attr in ("src", "href", "poster", "xlink:href"):
                    if node.attrs.get(attr):
                        local_target(node.attrs[attr], path.parent, root, outputs,
                                     navigation=node.tag == "a" and attr == "href")
                need(not node.attrs.get("srcset"), "srcset unsupported; prepare one local asset")
                if node.tag == "object" and node.attrs.get("data"):
                    local_target(node.attrs["data"], path.parent, root, outputs)
            source = path.read_text(encoding="utf-8-sig")
        elif path.suffix.lower() == ".css":
            source = path.read_text(encoding="utf-8-sig")
        else:
            continue
        for url in re.findall(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", source):
            local_target(url.strip(), path.parent, root, outputs)
        for url in re.findall(r"@import\s+['\"]([^'\"]+)['\"]", source):
            local_target(url, path.parent, root, outputs)


def validate_pages(value, root):
    pages = list_value(value, "pages")
    seen_sources, seen_outputs = set(), set()
    result = []
    for index, raw in enumerate(pages):
        raw = object_value(raw, f"pages[{index}]")
        source = relative(raw.get("source"), "page.source")
        output = relative(raw.get("output"), "page.output")
        need(Path(source).suffix.lower() in {".html", ".htm"}, "page.source must be HTML/HTM")
        need(Path(output).suffix.lower() == ".md", "page.output must be Markdown")
        inside(root, source, "page.source")
        need(source not in seen_sources and output not in seen_outputs, "duplicate source/output")
        need(not (root / output).exists(), "output collides with an input file")
        selector = raw.get("selector")
        need(selector is None or isinstance(selector, str) and bool(selector.strip()),
             "selector: omit/use null for whole body; blank is invalid")
        offset = raw.get("heading_offset", 0)
        need(type(offset) is int and 0 <= offset <= 5, "heading_offset: integer 0..5 required")
        seen_sources.add(source)
        seen_outputs.add(output)
        result.append({"source": source, "output": output,
                       "selector": selector, "heading_offset": offset})
    return result


def asset_inventory(files):
    # Preserve all non-HTML dependencies under their actual relative directory names.
    return {rel: digest for rel, digest in files.items()
            if Path(rel).suffix.lower() not in {".html", ".htm"}}


def provenance_records(value, root, pages):
    """Bind retained raw sources and explicit mappings for caller-prepared inputs."""
    if value is None:
        return [{"prepared_source": page["source"], "raw_source": binding(root / page["source"]),
                 "target_mapping": [], "asset_mapping": []} for page in pages]
    records = list_value(value, "provenance")
    need(len(records) == len(pages), "provenance must have one record per ordered page")
    for record, page in zip(records, pages):
        record = object_value(record, "provenance record")
        need(record.get("prepared_source") == page["source"], "provenance page order mismatch")
        verify_binding(record.get("raw_source"), "raw_source")
        for category in ("target_mapping", "asset_mapping"):
            need(isinstance(record.get(category), list), f"{category}: explicit list required (may be empty)")
            for item in record[category]:
                item = object_value(item, category)
                text(item.get("from"), f"{category}.from")
                text(item.get("to"), f"{category}.to")
                if category == "target_mapping":
                    raw_links, _ = source_observables(Path(record["raw_source"]["path"]).read_text(encoding="utf-8-sig"), None)
                    prepared_links, _ = source_observables((root / page["source"]).read_text(encoding="utf-8-sig"), page["selector"])
                    old = html_owner.normalize_href(item["from"])
                    new = html_owner.normalize_href(item["to"])
                    old_labels = [label for label, href in raw_links if href == old]
                    new_labels = [label for label, href in prepared_links if href == new]
                    need(old_labels and new_labels and all(label in new_labels for label in old_labels),
                         "declared target mapping missing or source labels changed")
                else:
                    inside(root, item["to"], "asset_mapping.to")
    return records


def validate_manifest(manifest):
    need(manifest.get("schema_version") == SCHEMA, "unsupported manifest schema")
    root = Path(text(manifest.get("input_root"), "input_root"))
    need(root.is_absolute(), "input_root must be absolute")
    root = root.resolve(strict=True)
    pages = validate_pages(manifest.get("pages"), root)
    need(pages == manifest["pages"], "noncanonical page options")
    files = inventory(root)
    need(files == manifest.get("inputs"), "stale source/dependency inventory")
    validate_closure(root, pages, files)
    need(provenance_records(manifest.get("provenance"), root, pages) == manifest.get("provenance"),
         "manifest requires canonical raw-source provenance")
    need(manifest.get("recipe") == recipe_identity(), "stale or unsupported conversion recipe")
    settings_path = verify_binding(manifest.get("reader_settings"), "reader_settings")
    state = reader_state(settings_path)
    need(state == manifest.get("reader_state"), "stale reader settings")
    pilot = object_value(manifest.get("pilot"), "pilot")
    pilot_root = Path(text(pilot.get("directory"), "pilot.directory")).resolve(strict=True)
    note = inside(pilot_root, pages[0]["output"], "pilot.note")
    need(pilot.get("note") == binding(note), "stale pilot note identity")
    reproduced = html_owner.convert_html(root / pages[0]["source"], pages[0]["selector"],
                                         pages[0]["heading_offset"])
    need(note.read_bytes() == reproduced.encode("utf-8"),
         "pilot note is not reproducible; manual postprocessing recipes cannot authorize this batch")
    assets = asset_inventory(files)
    need(pilot.get("assets") == assets, "pilot asset manifest differs from frozen dependencies")
    expected_files = {pages[0]["output"]: pilot["note"]["sha256"], **assets}
    need(inventory(pilot_root) == expected_files, "stale/unlisted pilot notes or assets")
    return root, pages, files, state, reproduced


def inline_text(value):
    if isinstance(value, list):
        return "".join(inline_text(child) for child in value)
    if not isinstance(value, dict):
        return ""
    tag = value.get("t")
    if tag == "Str":
        return value["c"]
    if tag in {"Space", "SoftBreak", "LineBreak"}:
        return " "
    if tag in {"Code", "Math"}:
        return value["c"][-1]
    if tag in {"Link", "Image"}:
        return inline_text(value["c"][1])
    if tag == "RawInline":
        return value["c"][-1]
    return inline_text(value.get("c", []))


def markdown_observables(markdown):
    ast = json.loads(html_owner._pandoc(markdown, "gfm", "json"))
    links, blocks = [], []
    def walk(value):
        if isinstance(value, dict):
            if value.get("t") == "Link":
                links.append((inline_text(value["c"][1]), html_owner.normalize_href(value["c"][-1][0])))
            if value.get("t") in {"Para", "Plain", "Header"}:
                blocks.append(inline_text(value["c"][-1] if value["t"] == "Header" else value["c"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(ast)
    return links, " ".join(blocks)


def source_observables(source, selector):
    prepared, _ = html_owner.prepare_html(source, selector)
    parser = html_owner.HTMLTree()
    parser.feed(prepared)
    def plain(node):
        if isinstance(node, str):
            return node
        return " ".join([node.attrs.get("alt") or "", *(plain(c) for c in node.children)])
    links = [(" ".join(plain(n).split()), html_owner.normalize_href(n.attrs["href"]))
             for n in html_owner.elements(parser.root) if n.tag == "a" and n.attrs.get("href")]
    return links, " ".join(plain(parser.root).split())


def validate_evidence(manifest_path, evidence_path):
    manifest_path = absolute_file(str(Path(manifest_path).absolute()), "manifest")
    evidence_path = absolute_file(str(Path(evidence_path).absolute()), "evidence")
    initial_manifest_hash = file_hash(manifest_path)
    initial_evidence_hash = file_hash(evidence_path)
    manifest = load_json(manifest_path)
    root, pages, files, state, note = validate_manifest(manifest)
    evidence = load_json(evidence_path)
    need(evidence.get("schema_version") == SCHEMA, "unsupported evidence schema")
    need(evidence.get("manifest_sha256") == file_hash(manifest_path), "stale manifest evidence binding")
    observer = object_value(evidence.get("observer"), "observer")
    for key in ("identity", "method", "observed_at"):
        text(observer.get(key), f"observer.{key}")
    artifact = verify_binding(evidence.get("observation_artifact"), "observation_artifact")
    need(artifact not in {manifest_path, evidence_path, Path(manifest["pilot"]["note"]["path"])},
         "observation artifact must be a separately retained record")
    need(evidence.get("reader_state") == state, "evidence reader state differs from frozen settings")
    captures = {}
    for item in list_value(evidence.get("captures"), "captures"):
        item = object_value(item, "capture")
        capture_id = text(item.get("id"), "capture.id")
        need(capture_id not in captures, "duplicate capture identity")
        verify_binding(item.get("artifact"), f"capture {capture_id}")
        need(item.get("kind") in {"source", "recipient"}, "capture.kind must be source or recipient")
        need(item.get("source_role") in {"raw", "prepared"}, "capture.source_role must be raw or prepared")
        expected_source = (manifest["provenance"][0]["raw_source"]["sha256"]
                           if item["source_role"] == "raw" else files[pages[0]["source"]])
        need(item.get("source_sha256") == expected_source, "stale capture source binding")
        if item["kind"] == "recipient":
            need(item["source_role"] == "prepared", "recipient capture must bind the prepared conversion input")
            need(item.get("note_sha256") == manifest["pilot"]["note"]["sha256"], "stale capture note binding")
            need(item.get("assets_sha256") == digest_object(manifest["pilot"]["assets"]), "stale capture asset binding")
            need(item.get("reader_settings_sha256") == manifest["reader_settings"]["sha256"],
                 "stale capture settings binding")
        captures[capture_id] = item
    need({c["kind"] for c in captures.values()} == {"source", "recipient"}, "both capture kinds required")
    source_links, source_text = source_observables((root / pages[0]["source"]).read_text(encoding="utf-8-sig"),
                                                 pages[0]["selector"])
    note_links, note_text = markdown_observables(note)
    observations = object_value(evidence.get("observations"), "observations")
    counts = {}
    def capture(value, kind):
        text(value, f"{kind} capture identity")
        need(value in captures and captures[value]["kind"] == kind, f"{kind} capture identity missing")
    for category in ("navigation", "citations"):
        items = list_value(observations.get(category), f"observations.{category}")
        for item in items:
            item = object_value(item, category)
            for key in ("source_href", "label", "observed_label", "intended_destination",
                        "observed_destination", "intended_landing_text", "observed_landing_text", "capture_id"):
                text(item.get(key), f"{category}.{key}")
            capture(item["capture_id"], "recipient")
            destination = html_owner.normalize_href(item["intended_destination"])
            need(html_owner.normalize_href(item["source_href"]) == destination,
                 "link adaptation must be prepared in HTML; manual reader remap unsupported")
            need(item["label"] == item["observed_label"], f"{category}: stripped/changed visible label")
            need((item["label"], destination) in source_links and (item["label"], destination) in note_links,
                 f"{category}: exact source/Markdown link label and destination not found")
            need(item["observed_destination"] == item["intended_destination"], f"{category}: wrong landing destination")
            need(item["observed_landing_text"] == item["intended_landing_text"], f"{category}: wrong landing text")
            need(item["intended_landing_text"] in note_text, f"{category}: landing text missing from note")
        counts[category] = len(items)
    figures = list_value(observations.get("figures"), "observations.figures")
    for figure in figures:
        figure = object_value(figure, "figure")
        capture(figure.get("source_capture_id"), "source")
        capture(figure.get("recipient_capture_id"), "recipient")
        figure_source_text = source_text
        if captures[figure["source_capture_id"]]["source_role"] == "raw":
            _, figure_source_text = source_observables(
                Path(manifest["provenance"][0]["raw_source"]["path"]).read_text(encoding="utf-8-sig"), None)
        for category in ("labels", "relations"):
            expected = list_value(figure.get(f"source_{category}"), f"figure.source_{category}")
            observed = list_value(figure.get(f"observed_{category}"), f"figure.observed_{category}")
            for value in expected + observed:
                text(value, f"figure.{category}")
            need(expected == observed, f"figure: missing/changed whole-figure {category}")
        for label in figure["source_labels"]:
            need(label in figure_source_text, f"figure: source label absent: {label!r}")
        source_caption = text(figure.get("source_caption"), "figure.source_caption")
        observed_caption = text(figure.get("observed_caption"), "figure.observed_caption")
        need(source_caption == observed_caption, "figure: caption mismatch")
        need(source_caption in figure_source_text and observed_caption in note_text, "figure: caption missing from source/note")
    counts["figures"] = len(figures)
    # Recheck inputs, pilot, recipe and the observation files after parsing/conversion.
    validate_manifest(manifest)
    verify_binding(evidence["observation_artifact"], "observation_artifact")
    for item in captures.values():
        verify_binding(item["artifact"], "capture")
    need(file_hash(manifest_path) == initial_manifest_hash and file_hash(evidence_path) == initial_evidence_hash,
         "manifest/evidence changed during validation")
    return manifest, evidence, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        _, _, counts = validate_evidence(args.manifest, args.evidence)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Reader pilot rejected: {exc}\n")
    print(f"Reader pilot evidence accepted: {json.dumps(counts, sort_keys=True)}")
    print(LIMIT)


if __name__ == "__main__":
    main()

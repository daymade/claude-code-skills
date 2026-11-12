#!/usr/bin/env python3
"""Read DOCX list ordinals independently of Pandoc; prepare a disposable input.

The compatibility repair changes only missing ilvl=0 on unambiguous single-level
definitions. The source checker separately resolves paragraph/style properties,
numbering instances, level overrides and counter restarts from the original ZIP.
"""

from contextlib import contextmanager
from pathlib import Path
import re
import tempfile
import zipfile
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def val(element, default=None):
    return element.get(f"{{{W}}}val", default) if element is not None else default


def levels(parent):
    """Resolve a lone implicit level; never guess multiple omitted levels."""
    children = parent.findall("w:lvl", NS)
    result = {}
    for child in children:
        index = child.get(f"{{{W}}}ilvl")
        if index is None:
            if len(children) != 1:
                raise ValueError("Ambiguous DOCX numbering: multiple levels omit ilvl")
            index = "0"
        index = int(index)
        if index in result or not 0 <= index <= 8:
            raise ValueError("Invalid or duplicate DOCX numbering level")
        result[index] = child
    return result


def normalize_numbering_xml(data):
    """Add only unambiguous missing level attributes, preserving XML prefixes."""
    root = ET.fromstring(data)
    indices = {}
    for parent in root.findall("w:abstractNum", NS):
        indices.update({id(node): index for index, node in levels(parent).items()})
    for override in root.findall("w:num/w:lvlOverride", NS):
        indices.update({id(node): int(override.get(f"{{{W}}}ilvl"))
                        for node in override.findall("w:lvl", NS)})
    expected = [indices[id(node)] if node.get(f"{{{W}}}ilvl") is None else None
                for node in root.iter(f"{{{W}}}lvl")]
    if not any(index is not None for index in expected):
        return data
    text = data.decode("utf-8")
    prefixes = re.findall(r'xmlns:([\w.-]+)\s*=\s*[\'"]' + re.escape(W) + r'[\'"]', text)
    if len(prefixes) != 1:
        raise ValueError("Cannot safely normalize DOCX numbering namespace")
    prefix = prefixes[0]
    pattern = re.compile(r"<" + re.escape(prefix) + r":lvl(?=[\s/>])[^>]*>")
    position = 0

    def insert(match):
        nonlocal position
        tag = match.group()
        index = expected[position]
        position += 1
        if index is None:
            return tag
        return tag.replace(":lvl", f':lvl {prefix}:ilvl="{index}"', 1)

    result = pattern.sub(insert, text).encode("utf-8")
    if position != len(expected):
        raise ValueError("DOCX numbering repair count mismatch")
    ET.fromstring(result)
    return result


@contextmanager
def pandoc_input(source):
    """Yield the source or a temporary reading copy; never write the original."""
    source = Path(source)
    if source.suffix.lower() != ".docx":
        yield source
        return
    with zipfile.ZipFile(source) as archive:
        if "word/numbering.xml" not in archive.namelist():
            yield source
            return
        original = archive.read("word/numbering.xml")
        normalized = normalize_numbering_xml(original)
        if normalized == original:
            yield source
            return
        with tempfile.TemporaryDirectory(prefix="docx-numbering-") as directory:
            copy = Path(directory) / source.name
            with zipfile.ZipFile(copy, "w") as target:
                for entry in archive.infolist():
                    target.writestr(entry, normalized if entry.filename == "word/numbering.xml"
                                    else archive.read(entry.filename))
            yield copy


def source_numbering(source):
    """Return decimal ordinal/depth records from original OOXML, without Pandoc.

    Unsupported list formats/indirections fail explicitly instead of reporting
    zero numbered items. Bullet levels are traversed but have no decimal record.
    """
    with zipfile.ZipFile(source) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        numbering = (ET.fromstring(archive.read("word/numbering.xml"))
                     if "word/numbering.xml" in archive.namelist() else ET.Element("numbering"))
        styles_root = (ET.fromstring(archive.read("word/styles.xml"))
                       if "word/styles.xml" in archive.namelist() else ET.Element("styles"))
    styles = {s.get(f"{{{W}}}styleId"): s for s in styles_root.findall("w:style", NS)}
    default = next((key for key, s in styles.items() if s.get(f"{{{W}}}default") == "1"
                    and s.get(f"{{{W}}}type") == "paragraph"), None)
    abstracts = {n.get(f"{{{W}}}abstractNumId"): n for n in numbering.findall("w:abstractNum", NS)}
    nums = {n.get(f"{{{W}}}numId"): n for n in numbering.findall("w:num", NS)}

    def properties(style_id, seen=()):
        if style_id is None:
            return {}
        if style_id in seen or style_id not in styles:
            raise ValueError("Unresolved or cyclic DOCX paragraph style")
        style = styles[style_id]
        result = properties(val(style.find("w:basedOn", NS)), seen + (style_id,))
        result.update(num_properties(style.find("w:pPr", NS)))
        return result

    def num_properties(ppr):
        if ppr is None:
            return {}
        numpr = ppr.find("w:numPr", NS)
        if numpr is None:
            return {}
        return {name: val(numpr.find("w:" + name, NS)) for name in ("numId", "ilvl")
                if numpr.find("w:" + name, NS) is not None}

    definitions, counters, records = {}, {}, []
    for paragraph in document.findall(".//w:body//w:p", NS):
        ppr = paragraph.find("w:pPr", NS)
        style = val(ppr.find("w:pStyle", NS), default) if ppr is not None else default
        props = properties(style)
        props.update(num_properties(ppr))
        num_id = props.get("numId")
        if num_id in (None, "0"):
            continue
        level = int(props.get("ilvl", "0"))
        if num_id not in definitions:
            num = nums.get(num_id)
            abstract = abstracts.get(val(num.find("w:abstractNumId", NS))) if num is not None else None
            if abstract is None or abstract.find("w:numStyleLink", NS) is not None:
                raise ValueError("Unresolved DOCX numbering instance or linked numbering style")
            defs = {index: {c.tag.split("}")[-1]: val(c) for c in node}
                    for index, node in levels(abstract).items()}
            for override in num.findall("w:lvlOverride", NS):
                index = int(override.get(f"{{{W}}}ilvl"))
                # An override level uses the enclosing override's level index.
                for node in override.findall("w:lvl", NS):
                    defs.setdefault(index, {}).update({c.tag.split("}")[-1]: val(c) for c in node})
                start = val(override.find("w:startOverride", NS))
                if start is not None:
                    defs.setdefault(index, {})["start"] = start
            definitions[num_id] = defs
        defs = definitions[num_id]
        if level not in defs:
            raise ValueError(f"Undefined DOCX numbering level {level}")
        definition = defs[level]
        fmt = definition.get("numFmt", "decimal")
        if fmt not in ("decimal", "bullet", "none"):
            raise ValueError(f"Numbering format {fmt!r} needs a scoped/native check")
        state = counters.setdefault(num_id, {})
        state[level] = state[level] + 1 if level in state else int(definition.get("start", "0"))
        for deeper, settings in defs.items():
            restart = int(settings.get("lvlRestart", str(deeper)))
            if deeper > level and restart != 0 and level == restart - 1:
                state.pop(deeper, None)
        if fmt == "decimal":
            text = ''.join(node.text or '' for node in paragraph.iter(f"{{{W}}}t"))
            records.append({"level": level, "value": state[level],
                            "text": re.sub(r"\s+", "", text)})
    return records


def markdown_numbering(blocks, text_of):
    """Read Markdown list ordinals/hierarchy from its AST, not the DOCX parser."""
    records = []

    def visit(node, depth=0):
        if isinstance(node, list):
            for child in node:
                visit(child, depth)
        elif isinstance(node, dict):
            kind, children = node.get("t"), node.get("c")
            if kind == "OrderedList":
                for value, item in enumerate(children[1], start=children[0][0]):
                    # One generated OOXML paragraph owns the label. Later
                    # continuation paragraphs belong to body-text comparison.
                    first = next((block for block in item
                                  if block.get("t") not in ("OrderedList", "BulletList")), None)
                    text = text_of(first)
                    records.append({"level": depth, "value": value,
                                    "text": re.sub(r"\s+", "", text)})
                    visit(item, depth + 1)
            elif kind == "BulletList":
                for item in children:
                    visit(item, depth + 1)
            else:
                visit(children, depth)

    visit(blocks)
    return records

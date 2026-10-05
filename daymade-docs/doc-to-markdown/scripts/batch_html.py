#!/usr/bin/env python3
"""Freeze a local HTML pilot, then expand only after retained reader evidence."""

import argparse
import json
import os
from pathlib import Path
import subprocess

import html_to_markdown as html_owner
import reader_pilot_gate as gate


RECEIPT = "batch-result.json"


def write_new(path, data, root=None):
    """Exclusive writes, rejecting symlink directory components via dir descriptors."""
    path = Path(path)
    root = Path(root) if root is not None else path.parent
    rel = gate.relative(path.relative_to(root).as_posix(), "write destination")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, directory_flags)
    try:
        parts = rel.split("/")
        for part in parts[:-1]:
            try:
                os.mkdir(part, dir_fd=descriptor)
            except FileExistsError:
                pass
            following = os.open(part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        file_descriptor = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                  0o644, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(data)
        file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "rb") as handle:
            gate.need(handle.read() == data, f"write readback failed: {path}")
    finally:
        os.close(descriptor)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def new_directory(value, forbidden):
    path = Path(value).expanduser().absolute()
    gate.need(not path.exists() and not path.is_symlink(), "output directory already exists")
    gate.need(path.parent.is_dir(), "output parent must already exist")
    resolved = path.parent.resolve(strict=True) / path.name
    for item in forbidden:
        item = Path(item).resolve()
        gate.need(resolved != item and not resolved.is_relative_to(item)
                  and not item.is_relative_to(resolved), "output overlaps source/evidence/pilot path")
    return resolved


def destinations(pages, assets):
    names = [page["output"] for page in pages] + list(assets) + [RECEIPT]
    gate.need(len(names) == len(set(names)), "duplicate output destination")
    for name in names:
        gate.relative(name, "output destination")
        for other in names:
            gate.need(name == other or not other.startswith(name + "/"),
                      "output file/directory collision")


def prepare(plan_path, manifest_path, pilot_dir):
    plan_path = gate.absolute_file(str(Path(plan_path).absolute()), "plan")
    plan = gate.load_json(plan_path)
    root = Path(gate.text(plan.get("input_root"), "input_root"))
    gate.need(root.is_absolute(), "input_root must be absolute")
    root = root.resolve(strict=True)
    files = gate.inventory(root)
    pages = gate.validate_pages(plan.get("pages"), root)
    gate.validate_closure(root, pages, files)
    provenance = gate.provenance_records(plan.get("provenance"), root, pages)
    settings = gate.absolute_file(plan.get("reader_settings_path"), "reader_settings_path")
    state = gate.reader_state(settings)
    gate.need(not settings.is_relative_to(root), "reader settings must be outside input_root")
    assets = gate.asset_inventory(files)
    destinations(pages, assets)
    manifest_path = Path(manifest_path).absolute()
    gate.need(not manifest_path.exists() and not manifest_path.is_symlink(), "manifest already exists")
    gate.need(manifest_path.parent.is_dir(), "manifest parent must already exist")
    manifest_path = manifest_path.parent.resolve() / manifest_path.name
    raw_paths = [record["raw_source"]["path"] for record in provenance]
    pilot_root = new_directory(pilot_dir, [root, plan_path, settings, manifest_path, *raw_paths])
    gate.need(not manifest_path.is_relative_to(root), "manifest cannot be inside input_root")
    recipe = gate.recipe_identity()
    pilot_page = pages[0]
    note = html_owner.convert_html(root / pilot_page["source"], pilot_page["selector"],
                                  pilot_page["heading_offset"]).encode("utf-8")
    gate.need(gate.inventory(root) == files and gate.recipe_identity() == recipe,
              "inputs/recipe changed during pilot preparation")
    settings_binding = gate.binding(settings)
    pilot_root.mkdir(exist_ok=False)
    try:
        write_new(pilot_root / pilot_page["output"], note, pilot_root)
        for rel, digest in assets.items():
            data = gate.inside(root, rel, "asset").read_bytes()
            gate.need(gate.sha(data) == digest, "asset changed during pilot preparation")
            write_new(pilot_root / rel, data, pilot_root)
        manifest = {"schema_version": gate.SCHEMA, "input_root": str(root),
                    "inputs": files, "pages": pages, "recipe": recipe,
                    "provenance": provenance,
                    "reader_settings": settings_binding, "reader_state": state,
                    "pilot": {"directory": str(pilot_root),
                              "note": gate.binding(pilot_root / pilot_page["output"]),
                              "assets": assets}}
        gate.validate_manifest(manifest)
        # No mutable status or observations are written into the frozen manifest.
        write_new(manifest_path, json_bytes(manifest))
    except Exception:
        # Retain owned partial files for diagnosis; never overwrite/delete inputs.
        raise
    return manifest


def run_batch(manifest_path, evidence_path, output_dir):
    # This completes before creating a batch directory or converting other pages.
    manifest, evidence, counts = gate.validate_evidence(manifest_path, evidence_path)
    root = Path(manifest["input_root"])
    pages, files = manifest["pages"], manifest["inputs"]
    assets = gate.asset_inventory(files)
    destinations(pages, assets)
    frozen_manifest = gate.binding(manifest_path)
    frozen_evidence = gate.binding(evidence_path)
    evidence_files = [Path(evidence["observation_artifact"]["path"]),
                      *(Path(item["artifact"]["path"]) for item in evidence["captures"])]
    output = new_directory(output_dir, [root, Path(manifest["pilot"]["directory"]),
                                        manifest_path, evidence_path, manifest["reader_settings"]["path"],
                                        *(record["raw_source"]["path"] for record in manifest["provenance"]),
                                        *evidence_files])
    output.mkdir(exist_ok=False)
    written = {}
    try:
        link_counts = {}
        for page in pages:
            gate.need(gate.inventory(root) == files, "inputs changed during batch")
            gate.need(gate.recipe_identity() == manifest["recipe"], "recipe changed during batch")
            note = html_owner.convert_html(root / page["source"], page["selector"], page["heading_offset"])
            gate.need(gate.inventory(root) == files, "inputs changed during conversion")
            write_new(output / page["output"], note.encode("utf-8"), output)
            written[page["output"]] = gate.file_hash(output / page["output"])
            _, expected = html_owner.prepare_html((root / page["source"]).read_text(encoding="utf-8-sig"),
                                                  page["selector"])
            link_counts[page["output"]] = html_owner.verify_links(expected, (output / page["output"]).read_text())
        for rel, digest in assets.items():
            data = gate.inside(root, rel, "asset").read_bytes()
            gate.need(gate.sha(data) == digest, "asset changed during batch")
            write_new(output / rel, data, output)
            written[rel] = gate.file_hash(output / rel)
        gate.need(gate.inventory(output) == written, "final output hash readback failed")
        gate.verify_binding(frozen_manifest, "manifest")
        gate.verify_binding(frozen_evidence, "evidence")
        gate.validate_evidence(manifest_path, evidence_path)
        result = {"schema_version": gate.SCHEMA, "status": "complete", "manifest": frozen_manifest,
                  "evidence": frozen_evidence, "outputs": written, "page_order": [p["output"] for p in pages],
                  "source_hyperlinks_retained": link_counts, "pilot_observation_counts": counts,
                  "reader_limit": gate.LIMIT}
        write_new(output / RECEIPT, json_bytes(result))
        gate.need(gate.load_json(output / RECEIPT) == result, "receipt readback failed")
        gate.need(gate.inventory(output) == {**written, RECEIPT: gate.file_hash(output / RECEIPT)},
                  "output changed after receipt write")
    except Exception as exc:
        # A failed/partial directory is retained, never advertised as complete.
        if not (output / RECEIPT).exists():
            write_new(output / RECEIPT, json_bytes({"schema_version": gate.SCHEMA, "status": "failed",
                                                  "error": str(exc), "outputs_written": written}))
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="create one reproducible pilot and a new frozen manifest")
    prepare_parser.add_argument("plan", type=Path)
    prepare_parser.add_argument("--manifest", type=Path, required=True)
    prepare_parser.add_argument("--pilot-dir", type=Path, required=True)
    run_parser = commands.add_parser("run", help="check reader evidence before expanding the frozen page order")
    run_parser.add_argument("manifest", type=Path)
    run_parser.add_argument("evidence", type=Path)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            manifest = prepare(args.plan, args.manifest, args.pilot_dir)
            print(f"Pilot prepared: {manifest['pilot']['note']['path']}")
            print(f"Manifest: {args.manifest}; sha256={gate.file_hash(args.manifest)}")
            print("Reader evidence required: navigation, citations, whole figures, observer and retained captures.")
        else:
            result = run_batch(args.manifest, args.evidence, args.output_dir)
            print(f"Batch complete: {len(result['page_order'])} notes; {args.output_dir / RECEIPT}")
            print(gate.LIMIT)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"HTML batch rejected: {exc}\n")


if __name__ == "__main__":
    main()

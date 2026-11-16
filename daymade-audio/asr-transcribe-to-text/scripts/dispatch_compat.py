"""Exact dispatch-only producer transitions; original provenance stays immutable.

The adjacent manifest pins reviewed old/new entry bytes, not a generic policy to
ignore source changes. New artifacts always carry actual current producer hashes.
"""
import copy
import hashlib
import json
import re
from pathlib import Path


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def old_hash(path):
    path = Path(path)
    try:
        manifest = json.loads(path.with_name("dispatch_compatibility.json").read_text())
        transition = manifest["transitions"][path.name]
        if (manifest["schema"] == "audio-dispatch-compatibility-v1"
                and re.fullmatch(r"[0-9a-f]{64}", transition["previous_sha256"])
                and transition["current_sha256"] == file_sha256(path)):
            return transition["previous_sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def producer_matches(recorded, current, path):
    if recorded == current:
        return True
    previous = old_hash(path)
    return bool(previous and recorded == {**current, "sha256": previous})


def pipeline_matches(recorded, current, scripts):
    return (isinstance(recorded, dict) and recorded.keys() == current.keys()
            and all(recorded[name] == digest or (old_hash(Path(scripts) / name) is not None
                        and recorded[name] == old_hash(Path(scripts) / name))
                    for name, digest in current.items()))


def previous_checkpoint(root, stem, identity, digest, script):
    previous = old_hash(script)
    if (not previous or identity.get("producer", {}).get("sha256") != file_sha256(script)):
        return None
    old = copy.deepcopy(identity)
    old["producer"]["sha256"] = previous
    path = Path(root) / f"{stem}-{digest(old)[:16]}" / "manifest.json"
    try:
        manifest = json.loads(path.read_text())
        if isinstance(manifest, dict) and manifest.get("status") == "complete" and all(manifest.get(k) == v for k, v in old.items()):
            return path, old
    except (OSError, ValueError, TypeError):
        pass
    return None


def write_reuse_record(origin, entrypoints):
    """Keep actual executing hashes separately; never edit a producer receipt."""
    origin = Path(origin)
    target = origin.with_name(origin.name + ".dispatch-reuse.json")
    payload = json.dumps({"schema": "audio-dispatch-reuse-v1",
                          "origin": str(origin.resolve()),
                          "origin_sha256": file_sha256(origin),
                          "entrypoints": {Path(p).name: file_sha256(p) for p in entrypoints}},
                         sort_keys=True, indent=2) + "\n"
    from transcribe_local_mlx import atomic_write_text
    atomic_write_text(target, payload)

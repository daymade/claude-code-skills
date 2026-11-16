"""Stage-1 history through daudio; native files change only after a three-way CAS.

The optional history_projection binding is literal argv. Its interpreter must
provide the installed daudio SDK; ordinary standalone correction needs no SDK.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import difflib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return base64.b64encode(value).decode("ascii")


def decoded(value):
    return base64.b64decode(value, validate=True)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".history-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _state(config_dir):
    return Path(config_dir) / "history-projections.json"


@contextmanager
def state_lock(path):
    # Same lock owner as the native Skill; its dependency is already declared.
    from filelock import FileLock
    with FileLock(str(path) + ".lock", timeout=10):
        state = json.loads(path.read_text()) if path.exists() else {"pending": {}, "receipts": {}}
        yield state
        atomic_json(path, state)


def _binding():
    from shared_evidence import _argv, _profile
    profile = _profile()
    return _argv(profile, "history_projection") if "history_projection" in profile else None


def capture_success(*, args, original_bytes, original_text, output_path, output_text, recipe, evidence_refs):
    """Preserve the bytes already read by this successful native invocation."""
    try:
        binding = _binding()
        if binding is None:
            return
        from utils.config import get_config
        config_dir = get_config().paths.config_dir
        output_path = Path(output_path).resolve()
        output_bytes = output_path.read_bytes()
        if output_bytes != output_text.replace("\n", os.linesep).encode("utf-8"):
            raise ValueError("native output changed before its success receipt")
        identity = uuid.uuid4().hex
        payload = {"execution_id": identity, "source_path": str(Path(args.input).resolve()),
            "output_path": str(output_path), "input_bytes_base64": encoded(original_bytes),
            "input_sha256": digest(original_bytes), "input_text": original_text,
            "output_bytes_base64": encoded(output_bytes), "output_sha256": digest(output_bytes),
            "parent_job_uri": os.environ.get("DAUDIO_PARENT_JOB_URI"),
            "script": str(Path(__file__).with_name("fix_transcription.py").resolve()),
            "recipe": recipe, "evidence_refs": evidence_refs, "status": "native_completed"}
        path = _state(config_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with state_lock(path) as state:
            state["pending"][identity] = payload
        # Native success is already durable; registry trouble cannot reverse it.
        subprocess.run([*binding, "flush", "--state", str(path)], check=True,
                       stdout=subprocess.DEVNULL, timeout=60)
    except Exception as error:
        print("Stage-1 history pending: " + type(error).__name__, file=sys.stderr)


def flush_native(config_dir):
    try:
        binding = _binding()
        if binding is not None and _state(config_dir).exists():
            subprocess.run([*binding, "flush", "--state", str(_state(config_dir))],
                           check=True, stdout=subprocess.DEVNULL, timeout=60)
    except Exception as error:
        print("Stage-1 projection pending: " + type(error).__name__, file=sys.stderr)


def exact_ref(resource, relation):
    return {"uri": resource["uri"], "version": resource["version"], "relation": relation}


def _parent_source(client, payload):
    parent = client.get(payload["parent_job_uri"])
    metadata = parent["metadata"]
    request = metadata.get("dispatch_request", {})
    if (parent["kind"] != "job" or metadata.get("provider") != "transcript.correct"
            or request.get("script") != payload["script"]
            or metadata.get("status") not in {"running", "completed"}):
        raise ValueError("history requires its original correction dispatch")
    references = [ref for ref in metadata.get("source_refs", []) if ref.get("relation") == "source_transcript"]
    if len(references) != 1:
        raise ValueError("history requires one exact original source")
    source = client.get(references[0]["uri"], version=references[0]["version"])
    original = decoded(payload["input_bytes_base64"])
    if (source["kind"] != "transcript" or digest(original) != payload["input_sha256"]
            or decoded(source["metadata"]["original_bytes_base64"]) != original):
        raise ValueError("read bytes do not match the pinned dispatch source")
    scope = client.config.get("device", {}).get("id")
    location = Path(payload["source_path"]).as_uri()
    if not scope or not any(item.get("uri") == location and item.get("locator_scope") == scope for item in source["locations"]):
        raise ValueError("source device/path is unknown or foreign")
    return parent, source, scope


def _capture(client, payload, save):
    parent, source, scope = _parent_source(client, payload)
    payload["parent_job_uri"] = parent["version_uri"]
    save()
    output = decoded(payload["output_bytes_base64"])
    if digest(output) != payload["output_sha256"]:
        raise ValueError("native output receipt bytes changed")
    refs = [exact_ref(parent, "native_call")]
    if sum(item.get("role") == "transcript-fixer.dictionary" for item in payload["evidence_refs"]) != 1:
        raise ValueError("historical correction needs a pinned shared dictionary")
    for item in payload["evidence_refs"]:
        evidence = client.get(item["source_ref"])
        if evidence["version_uri"] != item["source_ref"]:
            raise ValueError("history evidence must be pinned")
        refs.append(exact_ref(evidence, item["role"]))
    from shared_evidence import _profile
    profile = _profile()
    provider = profile.get("history_projection_provider")
    if not isinstance(provider, str) or not provider:
        raise ValueError("history_projection_provider must name its configured deterministic adapter")
    metadata = {"text": output.decode("utf-8"), "native_output_bytes_base64": encoded(output),
        "native_projection": {"path": payload["output_path"], "locator_scope": scope},
        "daudio": {"recompute": {"operation": "correct-stage1", "provider": provider,
            "source_uri": source["version_uri"], "options": {"recipe": payload["recipe"],
                "original_source_ref": source["version_uri"]}}}}
    result = client.record_result(producer="transcript-fixer.stage1", producer_revision=payload["recipe"]["revision"],
        native_execution_id=payload["execution_id"], operation="correct-stage1", source_uri=source["version_uri"],
        native_status="completed", raw={"native_status": "completed", "parent_job_ref": exact_ref(parent, "native_call"),
            "input_sha256": payload["input_sha256"], "output_sha256": payload["output_sha256"]},
        outputs=[{"kind": "transcript", "metadata": metadata, "refs": refs}])
    if result["metadata"].get("registration_status") != "completed":
        raise RuntimeError("native history registration remains pending")
    target = result["metadata"]["outputs"][0]
    resource = client.get(target["uri"], version=target["version"])
    return {"target_uri": resource["uri"], "baseline_ref": resource["version_uri"],
        "source_ref": source["version_uri"], "output_path": payload["output_path"],
        "locator_scope": scope, "status": "current"}


def three_way(base, native, derived):
    """Merge non-overlapping UTF-8 edits without rewriting newline bytes."""
    base, native, derived = (value.decode("utf-8") for value in (base, native, derived))
    def edits(value):
        return [(i, j, value[a:b]) for tag, i, j, a, b in difflib.SequenceMatcher(None, base, value, autojunk=False).get_opcodes() if tag != "equal"]
    native_edits, derived_edits = edits(native), edits(derived)
    combined = list(native_edits)
    for edit in derived_edits:
        if edit in combined:
            continue
        start, end, _ = edit
        for left, right, _ in native_edits:
            if (max(start, left) < min(end, right)
                    or start == end and left <= start <= right
                    or left == right and start <= left <= end):
                raise ValueError("manual and derived edits conflict")
        combined.append(edit)
    result = base
    for start, end, value in sorted(combined, key=lambda item: (item[0], item[1]), reverse=True):
        result = result[:start] + value + result[end:]
    return result.encode("utf-8")


def _evidence_copy(client, raw, key, refs):
    evidence_key = key + ":" + digest(json.dumps(refs, sort_keys=True).encode())
    return client.register("context", source_key=evidence_key, metadata={"original_bytes_base64": encoded(raw),
        "sha256": digest(raw), "role": "native_projection_observation"}, refs=refs)


def _project(client, receipt):
    scope = client.config.get("device", {}).get("id")
    if not scope or scope != receipt["locator_scope"]:
        raise ValueError("native projection belongs to another or unknown device")
    target = client.get(receipt["target_uri"])
    baseline = client.get(receipt["baseline_ref"])
    if target["version_uri"] == baseline["version_uri"]:
        return
    path = Path(receipt["output_path"])
    current = path.read_bytes()
    derived = target["metadata"]["text"].encode("utf-8")
    base = baseline["metadata"]["text"].encode("utf-8")
    refs = [exact_ref(baseline, "previous_projection"), exact_ref(target, "new_projection")]
    observed = _evidence_copy(client, current, "fixer-native-observed:" + digest(str(path).encode() + current), refs)
    receipt["observed_ref"] = observed["version_uri"]
    merged = three_way(base, current, derived)
    # Preserve the complete candidate before a native write; restart can verify it.
    candidate = _evidence_copy(client, merged, "fixer-native-candidate:" + digest(str(path).encode() + merged), refs)
    receipt["candidate_ref"] = candidate["version_uri"]
    receipt["expected_native_sha256"] = digest(current)
    receipt["projecting_ref"] = target["version_uri"]
    receipt["status"] = "prepared"
    return path, current, merged, target


def _replace_projection(client, prepared):
    path, current, merged, target = prepared
    if client.get(target["uri"])["version"] != target["version"] or path.read_bytes() != current:
        raise ValueError("projection compare-and-swap failed")
    fd, temporary = tempfile.mkstemp(prefix=".stage1-projection-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(merged)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        if path.read_bytes() != current or client.get(target["uri"])["version"] != target["version"]:
            raise ValueError("projection changed before native replacement")
        os.replace(temporary, path)
        if path.read_bytes() != merged:
            raise ValueError("native projection readback differs; retain evidence")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def flush(path):
    from daudio.client import Daudio
    client = Daudio()
    with state_lock(path) as state:
        for identity, payload in list(state["pending"].items()):
            try:
                receipt = _capture(client, payload, lambda: atomic_json(path, state))
                for prior in state["receipts"].values():
                    if (prior["output_path"], prior["locator_scope"]) == (receipt["output_path"], receipt["locator_scope"]):
                        prior["status"] = "superseded"
                state["receipts"][identity] = receipt
                del state["pending"][identity]
                atomic_json(path, state)
            except Exception as error:
                payload["error_type"] = type(error).__name__
        for receipt in state["receipts"].values():
            if receipt.get("status") == "superseded":
                continue
            try:
                if receipt.get("status") == "prepared":
                    candidate = client.get(receipt["candidate_ref"])
                    current = Path(receipt["output_path"]).read_bytes()
                    if digest(current) == candidate["metadata"]["sha256"]:
                        receipt.update(baseline_ref=receipt["projecting_ref"], status="current")
                prepared = _project(client, receipt)
                if prepared is not None:
                    atomic_json(path, state)
                    _replace_projection(client, prepared)
                    receipt.update(baseline_ref=prepared[3]["version_uri"], status="current")
                    receipt.pop("error_type", None)
            except Exception as error:
                receipt.update(status="pending", error_type=type(error).__name__)
                try:
                    if client.config.get("device", {}).get("id") == receipt["locator_scope"]:
                        actual = Path(receipt["output_path"]).read_bytes()
                        observed = _evidence_copy(client, actual, "fixer-native-readback:" + digest(str(receipt["output_path"]).encode() + actual), [])
                        receipt["readback_ref"] = observed["version_uri"]
                except Exception:
                    pass
    print(json.dumps({"status": "processed"}))


def recompute(options):
    from daudio.client import Daudio
    from core.correction_repository import CorrectionRepository
    from core.correction_service import CorrectionService
    from core.dictionary_processor import DictionaryProcessor
    client = Daudio()
    recipe = options["recipe"]
    dictionaries = [client.get(ref["uri"], version=ref["version"]) for ref in options["evidence_refs"]
        if ref.get("relation") == "transcript-fixer.dictionary"]
    if len(dictionaries) != 1:
        raise ValueError("Stage-1 history requires one exact dictionary snapshot")
    image = dictionaries[0]["metadata"]["sqlite_snapshot"]
    raw = decoded(image["bytes_base64"])
    if digest(raw) != image["sha256"]:
        raise ValueError("dictionary snapshot digest differs")
    with tempfile.TemporaryDirectory(prefix="fixer-history-rules-") as directory:
        database = Path(directory) / "rules.sqlite3"
        database.write_bytes(raw)
        repository = CorrectionRepository(database)
        try:
            service = CorrectionService(repository)
            corrections, metadata = service.get_corrections_with_metadata(recipe["domains"])
            rules = service.load_context_rules(recipe["domains"])
            if recipe["apply_domain"] and recipe["domains"]:
                for value in metadata.values():
                    value["trusted_domain"] = True
            demote = set(recipe["trap_froms"]) | set(recipe["trap_keep"])
            if recipe["shared_contexts"]:
                from core.trap_scanner import extract_demotion_sets
                demote = set()
                for ref in options["evidence_refs"]:
                    if ref.get("relation") == "transcript-fixer.contexts":
                        context = client.get(ref["uri"], version=ref["version"])
                        traps = extract_demotion_sets(context["metadata"]["text"])
                        demote.update(traps.banned_froms | traps.keep_tokens)
            for key in demote:
                if key in metadata:
                    metadata[key]["demoted_by_trap"] = True
            disabled = service.get_disabled_pairs(recipe["domains"])
            for key, value in recipe["fallback_corrections"].items():
                if key not in corrections and (key, value) not in disabled:
                    corrections[key] = value
                    metadata[key] = recipe["fallback_metadata"][key]
            processor = DictionaryProcessor(corrections, rules, metadata, speaker_labels=set(recipe["speaker_labels"]))
            source = client.get(options["original_source_ref"])
            import io
            text = io.TextIOWrapper(io.BytesIO(decoded(source["metadata"]["original_bytes_base64"])), encoding="utf-8").read()
            result, changes = processor.process(text,
                review_mode=not recipe["apply_all"], boundary_check=not recipe["apply_all"])
        finally:
            repository.close()
    print(json.dumps({"text": result, "stage": 1, "deferred": sum(item.risk != "low" for item in changes)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("flush")
    command.add_argument("--state", type=Path, required=True)
    command = commands.add_parser("recompute")
    command.add_argument("--options", required=True)
    command = commands.add_parser("publish")
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--publisher-json", required=True)
    command.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "flush":
        flush(args.state)
    elif args.command == "recompute":
        recompute(json.loads(args.options))
    else:
        argv = json.loads(args.publisher_json)
        if not isinstance(argv, list) or not argv or any(not isinstance(value, str) or not value for value in argv):
            raise ValueError("publisher must be explicit literal argv")
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        completed = subprocess.run([*argv, *arguments], check=False)
        if completed.returncode == 0 and args.state.exists():
            try:
                # Preserve the original publisher's stdout JSON exactly.
                from contextlib import redirect_stdout
                with redirect_stdout(sys.stderr):
                    flush(args.state)
            except Exception as error:
                print("Stage-1 projection pending: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()

"""Stage-1 history through daudio; native files change only after a three-way CAS.

The optional history_projection binding is literal argv. Resource access defaults
to the independent daudio thin SDK; standalone correction needs no audio SDK.
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


def _resource_client():
    from shared_evidence import _profile
    mode = _profile().get("history_resource_mode", "service")
    if mode == "service":
        from daudio_client import DaudioClient
        return DaudioClient()
    if mode == "local-worker":
        from daudio.client import Daudio
        client = Daudio()
        client.device_id = client.config.get("device", {}).get("id")
        return client
    raise ValueError("history_resource_mode must be service or explicit local-worker")


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


def _needs_native_flush(state_path: Path) -> bool:
    """Return True only when local projection state actually has work to recover.

    Read-only commands and idle CLI exits must not pay a synchronous full-history
    projection sweep across already-settled, conflict-parked (`ValueError`), or
    still-missing (`FileNotFoundError`) historical receipts. Pending Stage-1
    captures, interrupted `prepared` installs, active preimage recovery files,
    transient-error `pending` receipts, restored `FileNotFoundError` targets,
    and corrupt state files still trigger flush.
    """
    if not state_path.is_file():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    if not isinstance(state, dict):
        return True
    if state.get("pending"):
        return True
    receipts = state.get("receipts")
    if not isinstance(receipts, dict):
        return True
    for receipt in receipts.values():
        if not isinstance(receipt, dict):
            return True
        status = receipt.get("status")
        if status == "prepared":
            return True
        recovery = receipt.get("recovery_path")
        if isinstance(recovery, str) and recovery and Path(recovery).exists():
            return True
        if status == "pending":
            error_type = receipt.get("error_type")
            if error_type == "FileNotFoundError":
                output_path = receipt.get("output_path")
                if isinstance(output_path, str) and output_path and Path(output_path).exists():
                    return True
                continue
            if error_type == "ValueError":
                continue
            return True
    return False


def flush_native(config_dir):
    try:
        binding = _binding()
        state_path = _state(config_dir)
        if binding is not None and _needs_native_flush(state_path):
            subprocess.run([*binding, "flush", "--state", str(state_path)],
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
    scope = client.device_id
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


def _require_device(client, receipt):
    scope = client.device_id
    if not scope or scope != receipt["locator_scope"]:
        raise ValueError("native projection belongs to another or unknown device")


def _project(client, receipt):
    _require_device(client, receipt)
    target = client.get(receipt["target_uri"])
    if target["version_uri"] == receipt["baseline_ref"]:
        return
    path = Path(receipt["output_path"])
    current = path.read_bytes()
    baseline = client.get(receipt["baseline_ref"])
    if target["version_uri"] == baseline["version_uri"]:
        return
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
    receipt["recovery_path"] = str(path.parent / (".stage1-preimage-" + uuid.uuid4().hex))
    receipt["status"] = "prepared"
    return path, current, merged, target, receipt


def _preserve_preimage(client, receipt):
    _require_device(client, receipt)
    path = Path(receipt["recovery_path"])
    raw = path.read_bytes()
    resource = _evidence_copy(client, raw, "fixer-replaced-preimage:" + digest(str(path).encode() + raw),
        [{"uri": client.get(receipt["projecting_ref"])["uri"],
          "version": client.get(receipt["projecting_ref"])["version"], "relation": "proposed_projection"}])
    receipt["preimage_ref"] = resource["version_uri"]
    return raw


def _replace_projection(client, prepared):
    path, current, merged, target, receipt = prepared
    _require_device(client, receipt)
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
        recovery = Path(receipt["recovery_path"])
        if recovery.exists():
            raise ValueError("projection preimage destination is already occupied")
        # Capture the actual directory entry at the write boundary. A final
        # read/check alone cannot preserve a last-window external replacement.
        os.rename(path, recovery)
        preimage = _preserve_preimage(client, receipt)
        if preimage != current:
            if not path.exists():
                os.link(recovery, path)  # No overwrite if an editor recreated it.
            raise ValueError("native preimage changed at the replacement boundary")
        # Publish only to an empty destination; an editor's recreated file wins.
        # Unsupported hardlink filesystems retain the preimage and stay pending.
        try:
            os.link(temporary, path)
        except Exception:
            if not path.exists():
                try:
                    os.link(recovery, path)
                except OSError:
                    pass  # The durable preimage still names the native bytes.
            raise
        if _preserve_preimage(client, receipt) != current:
            raise ValueError("native preimage changed during projection")
        if path.read_bytes() != merged:
            raise ValueError("native projection readback differs; retain evidence")
        if client.get(target["uri"])["version"] != target["version"]:
            raise ValueError("derived version changed during native projection")
        recovery.unlink()  # Exact preimage bytes are already in the registry.
        receipt.pop("recovery_path", None)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def flush(path):
    client = _resource_client()
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
                _require_device(client, receipt)
                recovery_path = receipt.get("recovery_path")
                has_recovery = bool(recovery_path and Path(recovery_path).exists())
                if has_recovery:
                    preimage = _preserve_preimage(client, receipt)
                    native = Path(receipt["output_path"])
                    if not native.exists():
                        os.link(recovery_path, native)
                    if native.read_bytes() == preimage:
                        Path(recovery_path).unlink()
                        receipt.pop("recovery_path", None)
                    elif digest(preimage) != receipt["expected_native_sha256"]:
                        raise ValueError("retained native preimage requires conflict resolution")
                    else:
                        Path(recovery_path).unlink()
                        receipt.pop("recovery_path", None)
                if (receipt.get("status") == "pending"
                        and receipt.get("error_type") == "FileNotFoundError"
                        and not has_recovery
                        and not Path(receipt["output_path"]).exists()):
                    continue
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
                else:
                    receipt["status"] = "current"
                    receipt.pop("error_type", None)
            except Exception as error:
                receipt.update(status="pending", error_type=type(error).__name__)
                try:
                    if client.device_id == receipt["locator_scope"]:
                        actual = Path(receipt["output_path"]).read_bytes()
                        observed = _evidence_copy(client, actual, "fixer-native-readback:" + digest(str(receipt["output_path"]).encode() + actual), [])
                        receipt["readback_ref"] = observed["version_uri"]
                except Exception:
                    pass
    print(json.dumps({"status": "processed"}))


def recompute(options):
    from core.correction_repository import CorrectionRepository
    from core.correction_service import CorrectionService
    from core.dictionary_processor import DictionaryProcessor
    client = _resource_client()
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

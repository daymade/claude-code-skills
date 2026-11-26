"""Optional source-bound evidence reads; native correction state stays writable locally.

The profile is shared with external_dispatch. Only transcript-fixer's three
bindings are consumed. No binding means no subprocess, snapshot or rule change.
"""
from __future__ import annotations

import base64
import contextvars
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger(__name__)
_current = contextvars.ContextVar("transcript_shared_evidence", default=None)
_KEYS = {"transcript-fixer.dictionary": "dictionary", "transcript-fixer.roster": "people_roster",
         "transcript-fixer.contexts": "context"}
_URI = re.compile(r"^(daudio://(dictionary|context)/[A-Za-z0-9_-]+)(?:/versions/([1-9][0-9]*))?$")


class EvidenceError(ValueError):
    """Configured evidence cannot be verified; do not silently use another source."""


def _profile():
    explicit = os.getenv("DAYMADE_AUDIO_CONFIG")
    path = Path(explicit).expanduser() if explicit is not None else Path(
        os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "daymade-audio/config.json"
    if not path.is_file():
        if explicit is not None:
            raise EvidenceError("DAYMADE_AUDIO_CONFIG must name a readable profile")
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceError("invalid audio source profile") from exc
    if not isinstance(result, dict):
        raise EvidenceError("audio source profile must be an object")
    return result


def _argv(profile, key):
    value = profile.get(key)
    if (not isinstance(value, dict) or type(value.get("protocol")) is not int
            or value["protocol"] != 1 or not isinstance(value.get("argv"), list)
            or not value["argv"] or any(not isinstance(v, str) or not v or "\0" in v for v in value["argv"])):
        raise EvidenceError(key + " requires protocol=1 and literal nonempty argv")
    return value["argv"]


def _invoke(argv):
    try:
        result = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60)
        value = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Captured output can contain the complete private dictionary. Never log it.
        raise EvidenceError("configured source command failed or returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceError("source command must return one resource object")
    return value


def _bytes(value, digest, size=None):
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise EvidenceError("source bytes must be valid base64") from exc
    if (not isinstance(digest, str) or hashlib.sha256(decoded).hexdigest() != digest
            or (size is not None and (type(size) is not int or size != len(decoded)))):
        raise EvidenceError("source bytes do not match the declared SHA256/size")
    return decoded


def _binding(value, label):
    if not isinstance(value, dict) or not isinstance(value.get("uri"), str) or "domain" not in value:
        raise EvidenceError(label + " needs an explicit uri and domain (null for unscoped)")
    match = _URI.fullmatch(value["uri"])
    if not match:
        raise EvidenceError("binding requires a stable or pinned daudio resource URI")
    domain = value["domain"]
    if domain is not None:
        from core.correction_repository import normalize_domains
        if not isinstance(domain, str) or normalize_domains(domain) != [domain] or not re.fullmatch(r"[\w-]+", domain):
            raise EvidenceError("binding domain must be one explicit domain")
    if label == "context" and domain is None:
        raise EvidenceError("context binding must name its actual domain")
    if match[2] != ("dictionary" if label == "dictionary" else "context"):
        raise EvidenceError("binding kind mismatch")
    return value


class OverlayRepository:
    """Read-only supplementation using the producer's existing SQL selectors."""

    def __init__(self, native, shared, source_ref):
        self.native, self.shared, self.source_ref = native, shared, source_ref

    def get_all_corrections(self, domain=None, active_only=True):
        native = self.native.get_all_corrections(domain, active_only=False)
        shared = self.shared.get_all_corrections(domain, active_only=False)
        active_keys = {(c.domain, c.from_text) for c in native if c.is_active}
        active_pairs = {(c.domain, c.from_text, c.to_text) for c in native if c.is_active}
        decisions = self.native.get_shared_vetoes()
        vetoes = {(c.domain, c.from_text, c.to_text) for c in native if not c.is_active}
        vetoes.update((d["domain"], d["from_text"], d["to_text"]) for d in decisions)
        result = list(native)
        for row in shared:
            pair = (row.domain, row.from_text, row.to_text)
            suppressed = pair in vetoes and pair not in active_pairs
            if (row.domain, row.from_text) in active_keys and not suppressed:
                continue
            value = replace(row, id=None, is_active=False if suppressed else row.is_active)
            value.source_ref = self.source_ref
            value.source_native_id = row.id
            result.append(value)
        if active_only:
            result = [c for c in result if c.is_active]
        # Match the original repository ordering; stable sorting retains native
        # precedence without inventing a new cross-domain priority policy.
        return sorted(result, key=lambda c: ((c.domain,) if not domain else ()) + (-len(c.from_text), c.from_text))

    def get_correction(self, from_text, domain="general"):
        return next((c for c in self.get_all_corrections(domain) if c.from_text == from_text), None)

    def get_context_rule_rows(self, domains=None, active_only=True):
        native = self.native.get_context_rule_rows(domains, active_only=False)
        shared = self.shared.get_context_rule_rows(domains, active_only=False)
        keys = {(r.get("domain"), r["pattern"]) for r in native}
        rows = native + [{**r, "id": None, "source_ref": self.source_ref, "source_native_id": r["id"]}
                         for r in shared if (r.get("domain"), r["pattern"]) not in keys]
        return sorted((r for r in rows if not active_only or r["is_active"]), key=lambda r: -r["priority"])


class SharedEvidence:
    def __init__(self, profile=None):
        self.profile = _profile() if profile is None else profile
        configured = self.profile.get("evidence_bindings", {})
        if not isinstance(configured, dict):
            raise EvidenceError("evidence_bindings must be an object")
        self.bindings = {}
        for key, label in _KEYS.items():
            if key not in configured:
                continue
            values = configured[key] if label == "context" else [configured[key]]
            if not isinstance(values, list) or not values:
                raise EvidenceError("contexts binding must be a nonempty array")
            self.bindings[key] = [_binding(value, label) for value in values]
            if label == "context" and len({v["domain"] for v in values}) != len(values):
                raise EvidenceError("each context domain needs one unambiguous binding")
        self.reader = _argv(self.profile, "source_reader") if self.bindings else None
        self.publisher = _argv(self.profile, "source_publisher") if self.bindings and "source_publisher" in self.profile else None
        self._temp = None
        self._resources, self._paths, self._repos, self._native = {}, {}, [], {}
        self._dictionary_repos = {}
        self._validated = set()

    def _directory(self):
        if self._temp is None:
            self._temp = tempfile.TemporaryDirectory(prefix="transcript-evidence-")
        return Path(self._temp.name)

    def resource(self, binding, label):
        requested = binding["uri"]
        validation = (requested, label, binding["domain"])
        if validation in self._validated:
            return self._resources[requested]
        resource = self._resources.get(requested)
        if resource is None:
            resource = _invoke([*self.reader, requested])
        self._validate_resource(resource, binding, label)
        self._resources[requested] = resource
        self._validated.add(validation)
        return resource

    def _validate_resource(self, resource, binding, label):
        match = _URI.fullmatch(binding["uri"])
        version = resource.get("version")
        if (resource.get("uri") != match[1] or type(version) is not int or version < 1
                or resource.get("kind") != match[2] or (match[3] and int(match[3]) != version)):
            raise EvidenceError("source command returned a foreign resource or version")
        exact = match[1] + "/versions/" + str(version)
        if resource.get("version_uri") != exact:
            raise EvidenceError("source resource lacks its exact version URI")
        metadata = resource.get("metadata")
        if not isinstance(metadata, dict) or "domain" not in metadata or metadata["domain"] != binding["domain"]:
            raise EvidenceError("source domain differs from explicit binding")
        if metadata.get("import_kind") != ("transcript_fixer_sqlite" if label == "dictionary" else "text"):
            raise EvidenceError("unsupported source import_kind")
        identity = metadata.get("source")
        if not isinstance(identity, dict) or "size_bytes" not in identity:
            raise EvidenceError("source identity is incomplete")
        origin = identity.get("uri")
        if (not isinstance(origin, str) or not origin or any(c.isspace() or ord(c) < 32 for c in origin)
                or not urlsplit(origin).scheme):
            raise EvidenceError("source identity needs its explicit original URI")
        payload = _bytes(metadata.get("original_bytes_base64"), identity.get("sha256"), identity["size_bytes"])
        if label != "dictionary":
            if metadata.get("text_kind") != label or identity.get("encoding") != "utf-8":
                raise EvidenceError("text source kind/encoding mismatch")
            try:
                text = payload.decode("utf-8")
            except UnicodeError as exc:
                raise EvidenceError("source text must be UTF-8") from exc
            if text != metadata.get("text"):
                raise EvidenceError("source text and original bytes disagree")
        # Validate publisher ownership before a native writer can be opened.
        if self.publisher and label == "dictionary":
            key = resource.get("source_key")
            if not isinstance(key, str) or not key.startswith("source-import:dictionary:") or not key[len("source-import:dictionary:"):]:
                raise EvidenceError("dictionary publisher requires an owned SourceImporter source key")

    @staticmethod
    def _dictionary_image(metadata):
        snapshot = metadata.get("sqlite_snapshot", {})
        if not isinstance(snapshot, dict) or snapshot.get("format") != "sqlite_backup":
            raise EvidenceError("dictionary needs a consistent SQLite backup")
        return _bytes(snapshot.get("bytes_base64"), snapshot.get("sha256"))

    def _snapshot_cursor(self, metadata):
        image = self._dictionary_image(metadata)
        path = self._directory() / ("cursor-" + hashlib.sha256(image).hexdigest() + ".db")
        if not path.exists():
            path.write_bytes(image)
            path.chmod(0o600)
        return self._audit_cursor(path)

    def path(self, binding, label):
        resource = self.resource(binding, label)
        exact = resource["version_uri"]
        if exact not in self._paths:
            metadata = resource["metadata"]
            if label == "dictionary":
                data = self._dictionary_image(metadata)
            else:
                data = base64.b64decode(metadata["original_bytes_base64"], validate=True)
            path = self._directory() / (hashlib.sha256(exact.encode()).hexdigest() + (".db" if label == "dictionary" else ".md"))
            path.write_bytes(data)
            path.chmod(0o600)
            self._paths[exact] = path
        return self._paths[exact]

    def preflight(self):
        # Fence every configured source, including foreign context/roster, before
        # native repository initialization can create/migrate its local DB.
        for key, bindings in self.bindings.items():
            for binding in bindings:
                self.path(binding, _KEYS[key])
                if _KEYS[key] == "dictionary":
                    from core.correction_repository import CorrectionRepository
                    shared = CorrectionRepository(self.path(binding, "dictionary"), initialize_schema=False, readonly=True)
                    try:
                        rows = shared.get_all_corrections(active_only=False)
                        shared.get_context_rule_rows(active_only=False)
                        if binding["domain"] is not None and any(c.domain != binding["domain"] for c in rows):
                            raise EvidenceError("dictionary contains rows outside its bound domain")
                    except Exception:
                        shared.close()
                        raise
                    self._repos.append(shared)
                    self._dictionary_repos[binding["uri"]] = shared

    def attach(self, native):
        self.observe_native(native)
        bindings = self.bindings.get("transcript-fixer.dictionary")
        if not bindings:
            return native
        binding = bindings[0]
        shared = self._dictionary_repos[binding["uri"]]
        return OverlayRepository(native, shared, self.resource(binding, "dictionary")["version_uri"])

    def roster_path(self, native_path=None):
        if native_path and Path(native_path).expanduser().is_file():
            return native_path
        values = self.bindings.get("transcript-fixer.roster")
        return self.path(values[0], "people_roster") if values else native_path

    def people(self, native_path, *, names=False):
        from core.people_roster import load_people_roster, load_roster_names
        parser = load_roster_names if names else load_people_roster
        values = self.bindings.get("transcript-fixer.roster")
        if not values:
            return parser(native_path)
        shared = parser(self.path(values[0], "people_roster"))
        native = parser(native_path) if native_path and Path(native_path).is_file() else ({} if names else ({}, {}))
        if names:
            return {**shared, **native}
        return ({**shared[0], **native[0]}, {**shared[1], **native[1]})

    def contexts(self, domains, config_dir):
        if not domains:
            return []
        texts = []
        by_domain = {b["domain"]: b for b in self.bindings.get("transcript-fixer.contexts", [])}
        for domain in domains:
            binding = by_domain.get(domain)
            shared = self.resource(binding, "context")["metadata"]["text"] if binding else None
            native_path = Path(config_dir) / "contexts" / (domain + ".md")
            native = native_path.read_text(encoding="utf-8") if native_path.is_file() else None
            # Local context and its traps remain authoritative. Retain shared
            # supplementary context while preserving local vetoes with a union.
            if shared is not None:
                texts.append((domain, self.resource(binding, "context")["version_uri"], shared))
            if native is not None and native != shared:
                texts.append((domain, "local", native))
        return texts

    def stage2_context(self, domains, config_dir):
        if "transcript-fixer.contexts" not in self.bindings:
            return None
        return "\n\n".join(f"## Domain {domain}; source {ref}\n{text}" for domain, ref, text in self.contexts(domains, config_dir))

    def references(self, domains):
        """Compact pinned evidence, without original text or physical locations."""
        refs = []
        for key, bindings in self.bindings.items():
            for binding in bindings:
                if key == "transcript-fixer.contexts" and binding["domain"] not in (domains or []):
                    continue
                resource = self.resource(binding, _KEYS[key])
                refs.append({"role": key, "source_ref": resource["version_uri"],
                             "domain": binding["domain"], "source_sha256": resource["metadata"]["source"]["sha256"]})
        return refs

    @staticmethod
    def _audit_cursor(path):
        with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            cursor = conn.execute("SELECT coalesce(max(id),0) FROM audit_log").fetchone()[0]
            if type(cursor) is not int or cursor < 0:
                raise EvidenceError("snapshot audit cursor is invalid")
            return cursor

    def observe_native(self, native):
        if self.publisher and "transcript-fixer.dictionary" in self.bindings:
            path = str(native.db_path.resolve())
            binding = self.bindings["transcript-fixer.dictionary"][0]
            source = self.resource(binding, "dictionary")
            if Path(path).as_uri() != source["metadata"]["source"].get("uri"):
                raise EvidenceError("native dictionary path differs from configured publisher owner")
            baseline = self._audit_cursor(self.path(binding, "dictionary"))
            self._native.setdefault(path, baseline)

    def _publication_devices(self, binding):
        def configured_id(value):
            return value if isinstance(value, str) and value and not any(c.isspace() or ord(c) < 32 for c in value) else None
        device = self.profile.get("device")
        current = configured_id(device.get("id")) if isinstance(device, dict) else None
        return current, configured_id(binding.get("owner_device_id"))

    def publish(self, config_dir, *, invoke_publisher: bool = True):
        if not self.publisher or "transcript-fixer.dictionary" not in self.bindings:
            return
        from filelock import FileLock
        path = Path(config_dir) / "shared-publications.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=5):
            state = json.loads(path.read_text()) if path.is_file() else {"pending": {}, "receipts": {}}
            binding = self.bindings["transcript-fixer.dictionary"][0]
            resource = self.resource(binding, "dictionary")
            key = resource["source_key"][len("source-import:dictionary:"):]
            current_device, owner_device = self._publication_devices(binding)
            for native, before in self._native.items():
                cursor = self._audit_cursor(native)
                old_receipt = state["receipts"].get(native, {})
                recorded = old_receipt.get("captured_through_audit_cursor", 0) if (
                    old_receipt.get("device_id") == current_device and old_receipt.get("owner_device_id") == owner_device) else 0
                if type(recorded) is not int or recorded < 0:
                    raise EvidenceError("publication receipt cursor is invalid")
                before = max(before, recorded)
                if cursor > before:
                    prior = state["pending"].get(native)
                    if prior is not None and (not prior.get("device_id") or not prior.get("owner_device_id")
                            or prior.get("device_id") != current_device
                            or prior.get("owner_device_id") != owner_device):
                        continue  # Preserve another configured identity's pending work.
                    state["pending"][native] = {"audit_cursor": cursor, "source_key": key,
                        "uri": resource["uri"], "domain": binding["domain"],
                        "device_id": current_device, "owner_device_id": owner_device}
            def save():
                data = json.dumps(state, ensure_ascii=False)
                fd, temporary = tempfile.mkstemp(prefix=".shared-publications-", dir=path.parent)
                try:
                    with os.fdopen(fd, "w") as target:
                        target.write(data)
                        target.flush()
                        os.fsync(target.fileno())
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            if not state["pending"]:
                return
            save()  # Durable pending precedes any external publication attempt.
            if not invoke_publisher:
                return
            for native, pending in list(state["pending"].items()):
                # A changed owner binding cannot publish a previous owner's file.
                if (pending["uri"] != resource["uri"] or pending["source_key"] != key
                        or pending["domain"] != binding["domain"]):
                    continue
                if (not current_device or not owner_device or current_device != owner_device
                        or pending.get("device_id") != current_device
                        or pending.get("owner_device_id") != owner_device):
                    log.warning("Shared publication retained: configured device is missing or not the source owner")
                    continue
                if Path(native).resolve().as_uri() != resource["metadata"]["source"].get("uri"):
                    log.warning("Shared publication retained: pending path differs from configured owner")
                    continue
                argv = [*self.publisher, "dictionary", native, "--source-key", key]
                if pending["domain"] is not None:
                    argv += ["--domain", pending["domain"]]
                try:
                    receipt = _invoke(argv)
                    self._validate_resource(receipt, {"uri": pending["uri"], "domain": pending["domain"]}, "dictionary")
                    if receipt.get("source_key") != resource["source_key"] or receipt["metadata"]["source"]["uri"] != Path(native).resolve().as_uri():
                        raise EvidenceError("publisher returned a foreign owner receipt")
                    metadata = receipt["metadata"]
                    captured = self._snapshot_cursor(metadata)
                    if captured < pending["audit_cursor"]:
                        raise EvidenceError("published snapshot precedes committed audit cursor")
                    state["receipts"][native] = {"version_uri": receipt["version_uri"], "captured_through_audit_cursor": captured,
                        "device_id": current_device, "owner_device_id": owner_device,
                        "source_sha256": metadata["source"]["sha256"], "sqlite_snapshot_sha256": metadata["sqlite_snapshot"]["sha256"]}
                    del state["pending"][native]
                except (EvidenceError, KeyError, TypeError, ValueError, sqlite3.Error):
                    log.warning("Shared dictionary publication pending; native commit remains successful")
                save()

    def close(self):
        for repo in self._repos:
            repo.close()
        if self._temp is not None:
            self._temp.cleanup()


def current():
    return _current.get()


@contextmanager
def evidence_operation():
    evidence = SharedEvidence()
    try:
        evidence.preflight()
        if evidence.publisher and "transcript-fixer.dictionary" in evidence.bindings:
            from utils.config import get_config
            binding = evidence.bindings["transcript-fixer.dictionary"][0]
            source = evidence.resource(binding, "dictionary")
            if Path(get_config().database.path).resolve().as_uri() != source["metadata"]["source"].get("uri"):
                raise EvidenceError("native dictionary path differs from configured publisher owner")
    except Exception:
        evidence.close()
        raise
    token = _current.set(evidence)
    try:
        yield evidence
    finally:
        try:
            if evidence.publisher:
                from utils.config import get_config
                evidence.publish(
                    get_config().paths.config_dir,
                    invoke_publisher=not getattr(evidence, "defer_publish", False),
                )
        except Exception:
            # Native writes are already committed. Preserve their success; the
            # pending state/audit cursor supplies the next ordinary-call replay.
            log.warning("Shared publication could not finish; native state is retained")
        finally:
            if "history_projection" in evidence.profile:
                from history_projection import flush_native
                from utils.config import get_config
                flush_native(get_config().paths.config_dir)
            _current.reset(token)
            evidence.close()

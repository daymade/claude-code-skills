#!/usr/bin/env python3
"""Project-local research source records and cross-study discovery.

The catalog is an explicit list of studies, never a recursive history scan.
Provider outputs remain governed by provider_runs.py.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import provider_runs


SOURCE_STATES = {"candidate", "approved", "rejected", "unavailable"}
CLAIM_STATES = {"supported", "contested", "unknown"}
URL_RE = re.compile(r"https?://[^\s<>\]\[\"'()，、。；]+")
CLAIM_RE = re.compile(r"\[(C[0-9]+)\]")
TEXT_SUFFIXES = {".md", ".txt", ".html", ".htm", ".json", ".jsonl"}
DISCOVERABLE_SOURCE_STATES = {"approved", "legacy_unverified_for_reuse"}


class AnchorLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()
        self.visible_text = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_depth += 1
            return
        if tag != "a":
            return
        url = dict(attrs).get("href", "")
        if url.startswith(("https://", "http://")):
            self.urls.add(normalize_url(url))

    def handle_data(self, data):
        if self.hidden_depth == 0:
            self.visible_text.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def prior_catalog_path(directory, prior):
    value = prior.get("catalog")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("prior research catalog is missing")
    recorded = Path(value)
    return (recorded if recorded.is_absolute() else directory / recorded).resolve()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temp = Path(stream.name)
    os.replace(temp, path)


def append_jsonl(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank line")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_url(url):
    if re.fullmatch(r"urn:sha256:[0-9a-f]{64}", url):
        return url
    if not url.startswith(("https://", "http://")):
        raise ValueError("source reference must be HTTP(S) or a SHA-256 URN for a local original")
    return url.split("#", 1)[0].rstrip(".,;")


def source_id(url):
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:20]


def urls_in_text(text):
    return {normalize_url(match.group(0).rstrip(").,;")) for match in URL_RE.finditer(text)}


def row_sha256(row):
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def catalog_rows(catalog):
    latest = {}
    order = []
    for row in read_jsonl(catalog):
        study_id = row.get("study_id")
        if not study_id or not row.get("path"):
            raise ValueError(f"{catalog}: invalid catalog study")
        previous = latest.get(study_id)
        if previous is None:
            if row.get("revision", 1) != 1 or row.get("supersedes_sha256"):
                raise ValueError(f"{catalog}: first catalog revision must be 1")
            order.append(study_id)
        elif (row["path"] != previous["path"]
              or row.get("revision") != previous.get("revision", 1) + 1
              or row.get("supersedes_sha256") != row_sha256(previous)):
            raise ValueError(f"{catalog}: invalid catalog revision for {study_id}")
        latest[study_id] = row
    return [latest[study_id] for study_id in order]


def find_prior(catalog, query, include_leads=False):
    terms = [part.casefold() for part in query.split() if part]
    if not terms:
        raise ValueError("prior query must contain a specific entity or subject")
    matches = []
    for row in catalog_rows(catalog):
        source_index = [source for source in row.get("source_index", [])
                        if include_leads or source.get("status") in DISCOVERABLE_SOURCE_STATES]
        claim_index = row.get("claim_index", [])
        study_text = " ".join([row.get("study_id", ""), row.get("business_outcome", ""),
                               *row.get("terms", []),
                               *(source.get("title", "") + " " + source.get("url", "") for source in source_index),
                               *(claim.get("text", "") for claim in claim_index)]).casefold()
        source_matches = [
            source for source in source_index
            if any(term in (source.get("title", "") + " " + source.get("url", "")).casefold()
                   for term in terms)
        ]
        claim_matches = [
            claim for claim in claim_index
            if any(term in claim.get("text", "").casefold() for term in terms)
        ]
        if all(term in study_text for term in terms):
            matches.append({"study_id": row["study_id"], "path": row["path"],
                            "coverage": row.get("coverage", "unknown"),
                            "source_matches": source_matches[:10],
                            "claim_matches": claim_matches[:10],
                            "match_truncated": len(source_matches) > 10 or len(claim_matches) > 10})
    return matches


def cmd_start(args):
    directory = args.study.resolve()
    catalog = args.catalog.resolve()
    if directory.exists():
        raise ValueError(f"study directory already exists: {directory}")
    spec = read_json(args.spec)
    if not isinstance(spec, dict):
        raise ValueError("study spec must be a JSON object")
    context = spec.get("dispatch_context")
    if not isinstance(context, str) or not context.strip():
        raise ValueError("dispatch_context required: include the exact seed URL, named targets, and identifiers available at dispatch")
    for lane in spec.get("lanes", []):
        if not isinstance(lane, dict) or context not in lane.get("prompt", ""):
            raise ValueError(f"lane {lane.get('lane_id', '?') if isinstance(lane, dict) else '?'} prompt omits dispatch_context")
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.touch(exist_ok=True)
    matches = find_prior(catalog, args.query)
    directory.mkdir(parents=True)
    (directory / "sources" / "originals").mkdir(parents=True)
    (directory / "study.json").write_bytes(args.spec.read_bytes())
    try:
        provider_runs.load_study(directory)
    except Exception:
        shutil.rmtree(directory)
        raise
    receipt = {
        "catalog": os.path.relpath(catalog, directory),
        "catalog_sha256": sha256(catalog) if catalog.exists() else None,
        "searched_at": now(),
        "query": args.query,
        "matches": [{**match, "decision": "pending", "reason": ""} for match in matches],
    }
    write_json(directory / "prior-research.json", receipt)
    print(json.dumps({"study": str(directory), "prior_matches": matches}, ensure_ascii=False, indent=2))


def cmd_decide(args):
    path = args.study / "prior-research.json"
    receipt = read_json(path)
    if not args.reason.strip():
        raise ValueError("prior decision needs a concrete reason")
    matches = [row for row in receipt.get("matches", []) if row.get("study_id") == args.study_id]
    if len(matches) != 1:
        raise ValueError(f"prior study not in this search: {args.study_id}")
    matches[0]["decision"] = args.decision
    matches[0]["reason"] = args.reason
    write_json(path, receipt)
    print(f"{args.study_id}: {args.decision}")


def cmd_source(args):
    directory = args.study.resolve()
    _, lanes = provider_runs.load_study(directory)
    if args.lane_id and args.lane_id not in lanes:
        raise ValueError(f"unknown source lane: {args.lane_id}")
    if not args.url and not args.file:
        raise ValueError("source needs an HTTP(S) URL or a local original file")
    url = normalize_url(args.url) if args.url else "urn:sha256:" + sha256(args.file)
    for field in ("title", "source_type", "accessibility", "family"):
        if not getattr(args, field).strip():
            raise ValueError(f"source {field} is required")
    if args.status not in SOURCE_STATES:
        raise ValueError(f"invalid source status: {args.status}")
    if args.status in {"rejected", "unavailable"} and not args.reason.strip():
        raise ValueError(f"{args.status} source requires a reason")
    if args.status == "approved" and not (args.file or args.no_snapshot_reason.strip()):
        raise ValueError("approved source needs original file or no-snapshot reason")
    if args.status == "approved" and not args.locator.strip():
        raise ValueError("approved source needs a page, section, or exact locator")
    if args.file and not args.file.is_file():
        raise ValueError(f"source file missing: {args.file}")
    if args.published_at:
        datetime.strptime(args.published_at, "%Y-%m-%d")
    artifact = None
    if args.file:
        digest = sha256(args.file)
        suffix = args.file.suffix.lower() or ".bin"
        if len(suffix) > 12:
            suffix = ".bin"
        destination = directory / "sources" / "originals" / f"{source_id(url)}-{digest[:12]}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(args.file, destination)
        if sha256(destination) != digest:
            raise ValueError("copied original does not match input")
        artifact = {"path": str(destination.relative_to(directory)), "sha256": digest,
                    "bytes": destination.stat().st_size}
    previous = latest_sources(directory).get(source_id(url))
    surfaced_by = set(previous.get("surfaced_by", [])) if previous else set()
    if args.lane_id:
        surfaced_by.add(args.lane_id)
    row = {
        "at": now(), "source_id": source_id(url), "url": url, "title": args.title,
        "status": args.status, "source_type": args.source_type,
        "accessibility": args.accessibility, "evidence_family": args.family,
        "published_at": args.published_at, "locator": args.locator,
        "lane_id": args.lane_id, "surfaced_by": sorted(surfaced_by), "reason": args.reason,
        "no_snapshot_reason": args.no_snapshot_reason, "artifact": artifact,
    }
    append_jsonl(directory / "source-ledger.jsonl", row)
    print(json.dumps({"source_id": row["source_id"], "artifact": artifact}, ensure_ascii=False))


def latest_sources(directory):
    latest = {}
    for row in read_jsonl(directory / "source-ledger.jsonl"):
        url = normalize_url(row.get("url", ""))
        if row.get("source_id") != source_id(url):
            raise ValueError(f"source ID mismatch: {url}")
        if row.get("status") not in SOURCE_STATES:
            raise ValueError(f"invalid source status: {url}")
        for field in ("title", "source_type", "accessibility", "evidence_family"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"source missing {field}: {url}")
        latest[row["source_id"]] = row
    return latest


def provider_links(directory, events):
    links = {}
    for event in events:
        if event.get("state") != "collected":
            continue
        path = provider_runs.artifact_path(directory, event["artifact"])
        if path.suffix.lower() in TEXT_SUFFIXES:
            contents = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() in {".html", ".htm"}:
                parser = AnchorLinks()
                parser.feed(contents)
                urls = parser.urls | urls_in_text(" ".join(parser.visible_text))
            else:
                urls = urls_in_text(contents)
            for url in urls:
                links.setdefault(url, set()).add(event["lane_id"])
    return links


def cmd_harvest(args):
    directory = args.study.resolve()
    _, lanes = provider_runs.load_study(directory)
    events, _, _ = provider_runs.load_events(directory, lanes)
    known = {row["url"]: row for row in latest_sources(directory).values()}
    added = 0
    for url, lane_ids in sorted(provider_links(directory, events).items()):
        if url in known:
            previous = known[url]
            surfaced_by = sorted(set(previous.get("surfaced_by", [])) | lane_ids)
            if surfaced_by != previous.get("surfaced_by", []):
                append_jsonl(directory / "source-ledger.jsonl", {
                    **previous, "at": now(), "surfaced_by": surfaced_by,
                })
            continue
        append_jsonl(directory / "source-ledger.jsonl", {
            "at": now(), "source_id": source_id(url), "url": url, "title": url,
            "status": "candidate", "source_type": "other", "accessibility": "public",
            "evidence_family": "unknown", "published_at": None, "locator": "",
            "lane_id": "", "surfaced_by": sorted(lane_ids),
            "reason": "URL surfaced in collected provider text; not verified",
            "no_snapshot_reason": "", "artifact": None,
        })
        added += 1
    print(f"harvested {added} provider URLs")


def cmd_claim(args):
    directory = args.study.resolve()
    provider_runs.load_study(directory)
    if not re.fullmatch(r"C[0-9]+", args.claim_id):
        raise ValueError("claim ID must look like C1 or C01")
    if not args.text.strip() or not args.boundary.strip():
        raise ValueError("claim needs text and evidence boundary")
    if args.status != "unknown" and not args.locator.strip():
        raise ValueError("supported or contested claim needs an exact locator")
    if args.status != "unknown" and not args.source_id:
        raise ValueError(f"{args.status} claim needs source IDs")
    sources = latest_sources(directory)
    for source in args.source_id:
        if source not in sources or sources[source]["status"] != "approved":
            raise ValueError(f"claim source is not approved: {source}")
    existing = {row.get("claim_id") for row in read_jsonl(directory / "claims.jsonl")}
    if args.claim_id in existing:
        raise ValueError(f"duplicate claim ID: {args.claim_id}")
    append_jsonl(directory / "claims.jsonl", {
        "claim_id": args.claim_id, "text": args.text, "status": args.status,
        "source_ids": args.source_id, "locator": args.locator,
        "boundary": args.boundary, "recorded_at": now(),
    })
    print(args.claim_id)


def load_claims(directory, sources):
    claims = {}
    for row in read_jsonl(directory / "claims.jsonl"):
        claim_id = row.get("claim_id")
        if not re.fullmatch(r"C[0-9]+", claim_id or "") or claim_id in claims:
            raise ValueError(f"invalid or duplicate claim ID: {claim_id}")
        if row.get("status") not in CLAIM_STATES or not row.get("text") or not row.get("boundary"):
            raise ValueError(f"claim lacks status, text, or boundary: {claim_id}")
        source_ids = row.get("source_ids")
        if not isinstance(source_ids, list):
            raise ValueError(f"claim source_ids must be a list: {claim_id}")
        if row["status"] != "unknown" and not source_ids:
            raise ValueError(f"claim needs sources: {claim_id}")
        for source in source_ids:
            if source not in sources or sources[source]["status"] != "approved":
                raise ValueError(f"claim source is not approved: {claim_id}/{source}")
        claims[claim_id] = row
    return claims


def check(directory, report):
    directory = directory.resolve()
    report = report.resolve()
    if not report.is_relative_to(directory):
        raise ValueError("final report must be inside the durable study directory")
    study, lanes = provider_runs.load_study(directory)
    events, states, _ = provider_runs.load_events(directory, lanes)
    unfinished = [lane for lane in lanes if states.get(lane) not in {"collected", "deferred", "failed_unknown"}]
    if unfinished:
        raise ValueError(f"nonterminal lanes: {', '.join(unfinished)}")
    prior = read_json(directory / "prior-research.json")
    if not prior.get("query") or not prior.get("searched_at") or not prior.get("catalog"):
        raise ValueError("prior research query, time, and catalog are required")
    if not prior_catalog_path(directory, prior).is_file():
        raise ValueError("prior research catalog is missing")
    for row in prior.get("matches", []):
        if row.get("decision") not in {"reuse", "adapt", "reject"} or not row.get("reason"):
            raise ValueError(f"undecided prior study: {row.get('study_id')}")
    sources = latest_sources(directory)
    if not sources or not any(row["status"] == "approved" for row in sources.values()):
        raise ValueError("at least one approved original source is required")
    for row in sources.values():
        artifact = row.get("artifact")
        if artifact:
            path = provider_runs.artifact_path(directory, artifact)
            if not path.is_file() or sha256(path) != artifact["sha256"]:
                raise ValueError(f"source artifact missing or changed: {row['url']}")
        if row["status"] == "approved" and not (artifact or row.get("no_snapshot_reason")):
            raise ValueError(f"approved source has no original or access reason: {row['url']}")
    known = {row["url"]: row for row in sources.values()}
    missing_provider = set(provider_links(directory, events)) - set(known)
    if missing_provider:
        raise ValueError(f"{len(missing_provider)} provider URLs unrecorded; run harvest: "
                         + ", ".join(sorted(missing_provider)[:3]))
    if not report.is_file() or report.stat().st_size == 0:
        raise ValueError(f"report missing or empty: {report}")
    report_text = report.read_text(encoding="utf-8", errors="replace")
    cited = urls_in_text(report_text)
    missing_report = {url for url in cited if url not in known or known[url]["status"] != "approved"}
    if missing_report:
        raise ValueError(f"{len(missing_report)} report URLs lack approved source records: "
                         + ", ".join(sorted(missing_report)[:3]))
    claims = load_claims(directory, sources)
    if not claims:
        raise ValueError("claim registry is empty")
    cited_claims = set(CLAIM_RE.findall(report_text))
    if not cited_claims:
        raise ValueError("report has no claim IDs")
    unknown_claims = cited_claims - set(claims)
    if unknown_claims:
        raise ValueError("report cites unknown claims: " + ", ".join(sorted(unknown_claims)))
    for paragraph in re.split(r"\n\s*\n", report_text):
        units = [line for line in paragraph.splitlines() if CLAIM_RE.search(line)] if paragraph.lstrip().startswith("|") else [paragraph]
        for unit in units:
            for claim_id in set(CLAIM_RE.findall(unit)):
                refs = urls_in_text(unit)
                refs.update(re.findall(r"\]\((sources/originals/[^)]+)\)", unit))
                expected = set()
                for sid in claims[claim_id]["source_ids"]:
                    source = sources[sid]
                    expected.add(source["url"] if source["url"].startswith(("http://", "https://"))
                                 else source["artifact"]["path"])
                if not expected.issubset(refs):
                    raise ValueError(f"report {claim_id} lacks its bound original link(s): "
                                     + ", ".join(sorted(expected - refs)))
    return study, len(sources), len(cited)


def cmd_check(args):
    study, source_count, citation_count = check(args.study, args.report)
    print(json.dumps({"study_id": study["study_id"], "source_count": source_count,
                      "report_url_count": citation_count, "status": "valid"}, ensure_ascii=False))


def cmd_register(args):
    study, _, _ = check(args.study, args.report)
    prior = read_json(args.study.resolve() / "prior-research.json")
    if prior_catalog_path(args.study.resolve(), prior) != args.catalog.resolve():
        raise ValueError("registration catalog differs from the one searched at start")
    sources = latest_sources(args.study.resolve())
    claims = load_claims(args.study.resolve(), sources)
    catalog = args.catalog.resolve()
    rows = catalog_rows(catalog)
    path = os.path.relpath(args.study.resolve(), catalog.parent)
    existing = next((row for row in rows if row["study_id"] == study["study_id"]), None)
    if existing and existing["path"] != path:
        raise ValueError("study ID already registered at another path")
    terms = list(dict.fromkeys([*(existing.get("terms", []) if existing else []), *args.term]))
    indexed = {
        "study_id": study["study_id"], "path": path, "as_of": study["as_of"],
        "business_outcome": study["business_outcome"],
        "terms": terms, "coverage": "finalized",
        "source_index": [{"source_id": row["source_id"], "title": row["title"],
                          "url": row["url"], "status": row["status"]}
                         for row in sources.values()],
        "claim_index": [{"claim_id": row["claim_id"], "text": row["text"],
                         "status": row["status"]}
                        for row in claims.values()],
    }
    if existing:
        comparable = {key: existing.get(key) for key in indexed}
        if comparable == indexed:
            print(f"already registered: {study['study_id']}")
            return
        indexed["revision"] = existing.get("revision", 1) + 1
        indexed["supersedes_sha256"] = row_sha256(existing)
    indexed["registered_at"] = now()
    append_jsonl(catalog, indexed)
    print(f"registered: {study['study_id']} revision {indexed.get('revision', 1)}")


def cmd_relink_catalog(args):
    directory = args.study.resolve()
    study, _ = provider_runs.load_study(directory)
    prior_path = directory / "prior-research.json"
    prior = read_json(prior_path)
    catalog = args.catalog.resolve()
    if not args.reason.strip() or not catalog.is_file():
        raise ValueError("catalog relink needs an existing catalog and a reason")
    registered = next((row for row in catalog_rows(catalog) if row["study_id"] == study["study_id"]), None)
    if not registered or registered["path"] != os.path.relpath(directory, catalog.parent):
        raise ValueError("target catalog does not register this exact study path")
    old = prior.get("catalog")
    relative = os.path.relpath(catalog, directory)
    if old == relative:
        print("catalog already portable")
        return
    prior["catalog"] = relative
    prior["catalog_relinked_from"] = old
    prior["catalog_relinked_at"] = now()
    prior["catalog_relink_reason"] = args.reason
    write_json(prior_path, prior)
    print(f"relinked: {study['study_id']} -> {relative}")


def cmd_import_legacy(args):
    """Index a completed older study without claiming it meets this contract."""
    if not args.reason.strip():
        raise ValueError("legacy import needs an explicit coverage reason")
    directory = args.study.resolve()
    study, lanes = provider_runs.load_study(directory)
    _, states, _ = provider_runs.load_events(directory, lanes)
    if not any(state == "collected" for state in states.values()):
        raise ValueError("legacy study has no collected provider output")
    catalog = args.catalog.resolve()
    rows = catalog_rows(catalog)
    path = os.path.relpath(directory, catalog.parent)
    if any(row["study_id"] == study["study_id"] for row in rows):
        existing = next(row for row in rows if row["study_id"] == study["study_id"])
        if existing["path"] != path:
            raise ValueError("study ID already registered at another path")
        print(f"already registered: {study['study_id']}")
        return
    evidence = directory / "evidence.jsonl"
    source_index = {}
    claim_index = []
    if evidence.exists():
        for row in read_jsonl(evidence):
            url = row.get("source")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                source_index[source_id(url)] = {
                    "source_id": source_id(url), "title": row.get("source_type", "source"),
                    "url": normalize_url(url), "status": "legacy_unverified_for_reuse",
                }
            if row.get("claim"):
                claim_index.append({"claim_id": row.get("id", ""), "text": row["claim"],
                                    "status": row.get("status", "unknown")})
    append_jsonl(catalog, {
        "study_id": study["study_id"], "path": path, "as_of": study["as_of"],
        "business_outcome": study["business_outcome"], "terms": args.term,
        "coverage": "legacy_selected_sources", "coverage_reason": args.reason,
        "registered_at": now(), "source_index": list(source_index.values()),
        "claim_index": claim_index,
    })
    print(f"registered legacy study: {study['study_id']}")


def cmd_search(args):
    print(json.dumps(find_prior(args.catalog.resolve(), args.query, args.include_leads), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="create a study and inspect an explicit prior-study catalog")
    start.add_argument("study", type=Path)
    start.add_argument("--spec", required=True, type=Path)
    start.add_argument("--catalog", required=True, type=Path)
    start.add_argument("--query", required=True)
    decide = commands.add_parser("decide", help="record a decision on a discovered prior study")
    decide.add_argument("study", type=Path)
    decide.add_argument("study_id")
    decide.add_argument("decision", choices=["reuse", "adapt", "reject"])
    decide.add_argument("--reason", required=True)
    source = commands.add_parser("source", help="append a source record and optional original bytes")
    source.add_argument("study", type=Path)
    source.add_argument("--url", help="HTTP(S) original; omit with --file for a local original")
    source.add_argument("--title", required=True)
    source.add_argument("--status", choices=sorted(SOURCE_STATES), required=True)
    source.add_argument("--source-type", required=True)
    source.add_argument("--accessibility", required=True)
    source.add_argument("--family", required=True)
    source.add_argument("--published-at")
    source.add_argument("--locator", default="")
    source.add_argument("--lane-id", default="")
    source.add_argument("--reason", default="")
    source.add_argument("--file", type=Path)
    source.add_argument("--no-snapshot-reason", default="")
    claim = commands.add_parser("claim", help="append a source-bound claim")
    claim.add_argument("study", type=Path)
    claim.add_argument("--claim-id", required=True)
    claim.add_argument("--text", required=True)
    claim.add_argument("--status", choices=sorted(CLAIM_STATES), required=True)
    claim.add_argument("--source-id", action="append", default=[])
    claim.add_argument("--locator", default="")
    claim.add_argument("--boundary", required=True)
    harvest = commands.add_parser("harvest", help="record every URL in collected text reports as a lead")
    harvest.add_argument("study", type=Path)
    check_parser = commands.add_parser("check", help="check final source and provider coverage")
    check_parser.add_argument("study", type=Path)
    check_parser.add_argument("--report", required=True, type=Path)
    register = commands.add_parser("register", help="add a valid study to the searchable catalog")
    register.add_argument("study", type=Path)
    register.add_argument("--catalog", required=True, type=Path)
    register.add_argument("--report", required=True, type=Path)
    register.add_argument("--term", action="append", default=[])
    relink = commands.add_parser("relink-catalog", help="migrate an older absolute catalog path after checking the target study entry")
    relink.add_argument("study", type=Path)
    relink.add_argument("--catalog", required=True, type=Path)
    relink.add_argument("--reason", required=True)
    legacy = commands.add_parser("import-legacy", help="index an older provider study with explicit partial coverage")
    legacy.add_argument("study", type=Path)
    legacy.add_argument("--catalog", required=True, type=Path)
    legacy.add_argument("--reason", required=True)
    legacy.add_argument("--term", action="append", default=[])
    search = commands.add_parser("search", help="search the explicit catalog")
    search.add_argument("--catalog", required=True, type=Path)
    search.add_argument("--query", required=True)
    search.add_argument("--include-leads", action="store_true", help="include unverified and rejected source URLs")
    args = parser.parse_args()
    try:
        {"start": cmd_start, "decide": cmd_decide, "source": cmd_source,
         "claim": cmd_claim,
         "harvest": cmd_harvest, "check": cmd_check, "register": cmd_register,
         "relink-catalog": cmd_relink_catalog,
         "import-legacy": cmd_import_legacy, "search": cmd_search}[args.command](args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

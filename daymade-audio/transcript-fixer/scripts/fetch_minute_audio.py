#!/usr/bin/env python3
"""Fetch a Feishu/Lark minute's audio and verify it pairs with a transcript.

Why this exists: the dashboard's audio playback (`Q`) needs the recording that
matches the transcript's timeline, and getting it involves three steps that are
each easy to get subtly wrong — a download the CLI refuses on its own SSRF
guard, a signed URL that must be JSON-parsed rather than pattern-matched, and a
timeline check nobody remembers to run. Doing it by hand once per transcript
re-pays all three costs; this script pays them once.

Usage:
    fetch_minute_audio.py --token <minute-token> --profile <lark-cli-profile> \
        --output <path/to/audio.m4a> [--transcript <path/to/transcript.md>]

With --transcript it also compares the audio duration against the transcript's
last speaker timestamp and prints the exact `audio:` frontmatter line to add.

Exit codes (the frontmatter line goes to stdout, diagnostics to stderr, so the
status is what tells you whether anything was actually verified):
    0  verified — audio and transcript share a timeline
    1  timeline mismatch — a file WAS downloaded, but do NOT wire it
    2  downloaded, pairing unverified — ffprobe absent or its output unusable,
       no --transcript, the transcript has no `<speaker> HH:MM:SS.mmm` lines, or
       every one of those timestamps is 00:00:00 (no timeline to compare with).
       argparse also exits 2 for a malformed invocation — its message says so.
    3  operational failure, nothing usable produced (bad --transcript path or an
       unreadable one, an un-writable --output directory, lark-cli failed, curl
       failed, the download was too small, or the profile cannot read this
       minute — that last one is the most common and is not a bad token).

Requires: lark-cli (authenticated for the profile that OWNS the minute), curl,
and optionally ffprobe for the duration check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import typing
from pathlib import Path

# Mirrors `_TS_LINE` in scripts/review-dashboard/server.py — deliberately the
# SAME shape, because this check exists to predict what the dashboard will be
# able to play. A looser pattern does not just risk drift, it actively misfires:
# a permissive `HH:MM:SS` scan also matches wall-clock times sitting in YAML
# frontmatter (an upload timestamp like `...T12:26:17` reads as 12.4 hours),
# which made an early version of this script reject a perfectly healthy pairing.
SPEAKER_TS_LINE = re.compile(r"^\S.*?\s(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*$")


def run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def fail(message: str) -> "typing.NoReturn":
    """Operational failure — nothing usable was produced.

    Exits 3 so a caller can tell it apart from exit 1 (a real file downloaded,
    but its timeline does not match the transcript). Conflating the two sends
    the operator hunting for a different recording when the actual problem was
    a wrong --profile.
    """
    print(f"✗ {message}", file=sys.stderr)
    raise SystemExit(3)


def fetch_signed_url(token: str, profile: str) -> str:
    """Ask lark-cli for the signed download URL.

    Two things this gets right that a hand-rolled version usually doesn't:
    the envelope is real JSON, so it is parsed rather than regex-scraped (a
    regex leaves `\\u0026` and other escapes literal, producing a URL that 404s
    or truncates at the first parameter); and the Feishu API is a domestic
    service, so any HTTP proxy in the environment is disabled for the call —
    a proxy both breaks the request and would carry credentials outbound.
    """
    env = dict(os.environ)
    env["LARK_CLI_NO_PROXY"] = "1"
    proc = run(
        [
            "lark-cli", "minutes", "+download",
            "--minute-tokens", token,
            "--profile", profile,
            "--url-only",
        ],
        env=env,
    )
    if proc.returncode != 0:
        fail(f"lark-cli failed (exit {proc.returncode}):\n{proc.stderr.strip()[:800]}")

    # The CLI may prepend/append human-readable lines; isolate the JSON object.
    raw = proc.stdout
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        fail(f"No JSON object in lark-cli output:\n{raw[:800]}")
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        fail(f"Could not parse lark-cli JSON: {exc}\n{raw[:800]}")

    url = (payload.get("data") or {}).get("download_url")
    if not url:
        # A permission failure surfaces here, and the cause is almost always the
        # profile rather than the token: a minute is a per-tenant, per-user
        # resource, so a profile from another tenant (or one the minute was
        # never shared with) authenticates fine and still cannot read it.
        fail(
            "No data.download_url in the response — the profile likely cannot "
            f"read this minute. Envelope:\n{json.dumps(payload, ensure_ascii=False)[:800]}"
        )
    return url


def download(url: str, output: Path) -> None:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail(f"cannot create output directory {output.parent}: {exc}")
    # --noproxy '*': same domestic-service reason as above. -L: the signed URL
    # redirects, and without it you save a ~100-byte redirect body that looks
    # like a successful download until playback fails.
    proc = run(["curl", "-sSL", "--noproxy", "*", "-o", str(output), url])
    if proc.returncode != 0:
        fail(f"curl failed (exit {proc.returncode}): {proc.stderr.strip()[:400]}")
    if not output.exists() or output.stat().st_size < 10_000:
        size = output.stat().st_size if output.exists() else 0
        fail(f"Downloaded file is {size} bytes — too small to be audio; the URL may have expired.")


def audio_duration_seconds(path: Path) -> tuple[float | None, str]:
    """(duration, reason). reason is "" on success, else why it is unknown.

    The two failure causes need different words: telling an operator to install
    ffprobe when ffprobe just ran and emitted something unparseable sends them
    after the wrong thing.
    """
    if not shutil.which("ffprobe"):
        return None, "ffprobe not installed"
    proc = run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
    ])
    try:
        return float(proc.stdout.strip()), ""
    except (ValueError, AttributeError):
        return None, f"ffprobe ran but returned no usable duration ({proc.stdout.strip()[:60]!r})"


def last_timestamp_seconds(transcript: Path) -> float | None:
    """End of the transcript's timeline: the largest SPEAKER timestamp.

    Only speaker-timestamp lines count — the same ones the dashboard turns into
    clips. Any other `HH:MM:SS` in the file (frontmatter, prose, a quoted time)
    belongs to a different clock and would corrupt the comparison.
    """
    best: float | None = None
    try:
        content = transcript.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        # is_file() is true for an unreadable file, so the pre-flight check does
        # not cover this. Uncaught it would exit 1 — "timeline mismatch".
        fail(f"cannot read --transcript {transcript}: {exc}")
    for line in content.splitlines():
        match = SPEAKER_TS_LINE.match(line)
        if not match:
            continue
        h, m, s, ms = match.groups()
        total = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
        if best is None or total > best:
            best = total
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--token", required=True, help="Minute token (from the transcript's frontmatter)")
    ap.add_argument("--profile", required=True, help="lark-cli profile that OWNS the minute")
    ap.add_argument("--output", required=True, type=Path, help="Where to save the audio")
    ap.add_argument("--transcript", type=Path, help="Transcript to verify the timeline against")
    args = ap.parse_args()

    # Validate inputs BEFORE any network work: exit 3 means "nothing usable was
    # produced", so it must not be reachable after a good file is already on disk.
    if args.transcript is not None and not args.transcript.is_file():
        fail(f"--transcript path does not exist: {args.transcript}")

    print(f"→ Requesting signed URL for {args.token} …", file=sys.stderr)
    url = fetch_signed_url(args.token, args.profile)
    print(f"→ Downloading to {args.output} …", file=sys.stderr)
    download(url, args.output)
    size_mb = args.output.stat().st_size / 1_048_576
    print(f"✓ Saved {size_mb:.1f} MB", file=sys.stderr)

    # Exit codes carry the verification result because the diagnostics go to
    # stderr while the frontmatter line goes to stdout — a caller capturing
    # stdout would otherwise see a clean-looking success for an unverified file.
    #   0 = verified   1 = timeline mismatch   2 = unverified   3 = op failure
    unverified = False

    duration, why = audio_duration_seconds(args.output)
    if duration is None:
        print(f"⚠ {why} — timeline pairing NOT verified.", file=sys.stderr)
        unverified = True
    else:
        print(f"  audio duration: {duration:.0f}s", file=sys.stderr)

    if args.transcript is None:
        print("⚠ No --transcript given — timeline pairing NOT verified.", file=sys.stderr)
        unverified = True

    if args.transcript and duration is not None:
        last = last_timestamp_seconds(args.transcript)
        if last is None:
            print(
                "⚠ No '<speaker> HH:MM:SS.mmm' lines in the transcript — pairing NOT "
                "verified. The dashboard derives clip windows from those same lines, "
                "so audio wired to this transcript would have nothing to play.",
                file=sys.stderr,
            )
            unverified = True
        elif last <= 0:
            # Every speaker line reads 00:00:00.000 — there is no timeline to
            # compare against. Falling through to the shared ending (rather than
            # returning here) keeps the frontmatter line and its bare-value
            # warning identical across every outcome.
            print(
                "⚠ All speaker timestamps are 00:00:00 — no usable timeline; "
                "pairing NOT verified.",
                file=sys.stderr,
            )
            unverified = True
        else:
            drift = duration - last
            print(f"  transcript ends at: {last:.0f}s   (audio − transcript = {drift:+.0f}s)", file=sys.stderr)
            # A speed-rate mismatch (e.g. a transcript produced from a 1.3x
            # ASR input) shows up as a large proportional gap, which would make
            # every clip play the wrong seconds.
            if abs(drift) > max(60.0, last * 0.05):
                print(
                    "✗ TIMELINE MISMATCH — the audio and transcript are probably on "
                    "different timelines (speed-rate or wrong recording). Do NOT wire "
                    "this file: every clip would play the wrong seconds.",
                    file=sys.stderr,
                )
                return 1
            print("✓ Timeline pairing looks correct.", file=sys.stderr)

    print(f"audio: {args.output.resolve()}")
    print(
        "  ^ add this line to the transcript's YAML frontmatter, bare — a trailing "
        "'#' comment becomes part of the path and silently disables playback",
        file=sys.stderr,
    )
    return 2 if unverified else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fetch a Feishu/Lark minute's audio and verify it pairs with a transcript.

Use the source workflow's authorized profile and identity to fetch its recording.
This helper owns signed-URL parsing, HTTP download errors and duration comparison.

Usage:
    fetch_minute_audio.py --token <minute-token> --profile <lark-cli-profile> --as user \
        --output <path/to/audio.m4a> [--transcript <path/to/transcript.md>]

With --transcript it also compares the audio duration against the transcript's
last speaker timestamp and prints the exact `audio:` frontmatter line to add.

Exit codes (the frontmatter line goes to stdout, diagnostics to stderr, so the
status is what tells you whether anything was actually verified):
    0  duration comparison passed; confirm source identity and a spoken anchor
    1  timeline mismatch — a file WAS downloaded, but do NOT wire it
    2  downloaded, pairing unverified — ffprobe absent or its output unusable,
       no --transcript, the transcript has no `<speaker> HH:MM:SS.mmm` lines, or
       every one of those timestamps is 00:00:00 (no timeline to compare with).
       argparse also exits 2 for a malformed invocation — its message says so.
    3  operational failure, nothing usable produced (bad --transcript path or an
       unreadable one, an un-writable --output directory, lark-cli failed, curl
       failed, the download was too small, or the API refused export).

Requires: lark-cli (authenticated for the authorized source profile), curl,
and optionally ffprobe for the duration check.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import typing
from pathlib import Path

# Count only speaker-timestamp lines; wall-clock times in YAML frontmatter do
# not identify playback positions.
SPEAKER_TS_LINE = re.compile(r"^\S.*?\s(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*$")


def run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def fail(message: str) -> "typing.NoReturn":
    """Report the actual operational failure without inferring its cause."""
    print(f"✗ {message}", file=sys.stderr)
    raise SystemExit(3)


def fetch_signed_url(token: str, profile: str, identity: str = "user") -> str:
    """Ask lark-cli for the signed download URL.

    Parse the CLI envelope as JSON so URL escapes are decoded. Keep this
    source workflow's request independent of environment HTTP proxies.
    """
    if identity not in ("user", "bot"):
        fail("--as must be user or bot; preserve the source identity")
    env = dict(os.environ)
    env["LARK_CLI_NO_PROXY"] = "1"
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    proc = run(
        [
            "lark-cli", "minutes", "+download",
            "--minute-tokens", token,
            "--profile", profile,
            "--as", identity,
            "--url-only",
        ],
        env=env,
    )
    # The CLI may prepend/append human-readable lines; isolate the JSON object.
    raw = proc.stdout
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        if proc.returncode != 0:
            fail(f"lark-cli failed (exit {proc.returncode}):\n{proc.stderr.strip()[:800]}")
        fail(f"No JSON object in lark-cli output:\n{raw[:800]}")
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        fail(f"Could not parse lark-cli JSON: {exc}\n{raw[:800]}")

    if not isinstance(payload, dict):
        fail("lark-cli result is not an object; export status is unknown")
    error = payload.get("error")
    if proc.returncode != 0 or error or ("ok" in payload and payload["ok"] is not True):
        detail = json.dumps(error, ensure_ascii=False) if error else proc.stderr.strip()
        # Preserve the actual refusal/error; never infer missing permissions from
        # an absent URL or echo a signed success payload into a diagnostic.
        fail(f"lark-cli export failed (exit {proc.returncode}): {detail[:800] or 'invalid success status'}")
    data = payload.get("data")
    if not isinstance(data, dict):
        fail("lark-cli result has no data object; export status is unknown")
    url = data.get("download_url")
    if not isinstance(url, str) or not url.strip():
        fail("lark-cli result has no nonblank data.download_url; export status is unknown")
    return url


def download(url: str, output: Path) -> None:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail(f"cannot create output directory {output.parent}: {exc}")
    # --noproxy '*': same domestic-service reason as above. -L: the signed URL
    # redirects, and without it you save a ~100-byte redirect body that looks
    # like a successful download until playback fails.
    proc = run(["curl", "--fail", "-sSL", "--noproxy", "*", "-o", str(output), url])
    if proc.returncode != 0:
        fail(f"curl failed (exit {proc.returncode}): {proc.stderr.strip()[:400]}")
    if not output.exists() or output.stat().st_size < 10_000:
        size = output.stat().st_size if output.exists() else 0
        fail(f"Downloaded file is {size} bytes — too small to be audio; the URL may have expired.")


def audio_duration_seconds(path: Path) -> tuple[float | None, str]:
    """(duration, reason). reason is "" on success, else why it is unknown.

    Distinguish an unavailable probe from an unusable result in diagnostics.
    """
    if not shutil.which("ffprobe"):
        return None, "ffprobe not installed"
    proc = run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
    ])
    try:
        duration = float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return None, f"ffprobe ran but returned no usable duration ({proc.stdout.strip()[:60]!r})"
    if proc.returncode != 0 or not math.isfinite(duration) or duration <= 0:
        return None, f"ffprobe duration is unverified (exit {proc.returncode}, value {duration!r})"
    return duration, ""


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
    ap.add_argument("--profile", required=True, help="source workflow's authorized lark-cli profile")
    ap.add_argument("--as", dest="identity", choices=("user", "bot"), default="user",
                    help="source identity; defaults to user, pass bot only for a bot-sourced workflow")
    ap.add_argument("--output", required=True, type=Path, help="Where to save the audio")
    ap.add_argument("--transcript", type=Path, help="Transcript to verify the timeline against")
    args = ap.parse_args()

    # Validate inputs BEFORE any network work: exit 3 means "nothing usable was
    # produced", so it must not be reachable after a good file is already on disk.
    if args.transcript is not None and not args.transcript.is_file():
        fail(f"--transcript path does not exist: {args.transcript}")

    print(f"→ Requesting signed URL for {args.token} …", file=sys.stderr)
    url = fetch_signed_url(args.token, args.profile, args.identity)
    print(f"→ Downloading to {args.output} …", file=sys.stderr)
    download(url, args.output)
    size_mb = args.output.stat().st_size / 1_048_576
    print(f"✓ Saved {size_mb:.1f} MB", file=sys.stderr)

    # Exit codes carry the verification result because the diagnostics go to
    # stderr while the frontmatter line goes to stdout — a caller capturing
    # stdout would otherwise see a clean-looking success for an unverified file.
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

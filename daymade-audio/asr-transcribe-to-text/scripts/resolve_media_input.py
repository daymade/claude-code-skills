# /// script
# requires-python = ">=3.10"
# ///
"""Resolve local files, direct media URLs, and podcast/web pages to media files.

The script keeps network/media handling deterministic so the ASR step only sees
validated local paths.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html.parser
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


MEDIA_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".ape",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}

CONTENT_TYPE_EXTENSIONS = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclasses.dataclass
class ResolvedMedia:
    input: str
    kind: str
    path: str
    media_url: str | None = None
    page_url: str | None = None
    title: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    bytes_written: int | None = None
    sha256: str | None = None
    duration_seconds: float | None = None
    skipped_existing: bool = False


@dataclasses.dataclass
class RemoteInfo:
    final_url: str
    content_length: int | None
    content_type: str | None
    content_disposition: str | None


class MediaHTMLParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.sources: list[str] = []
        self.json_scripts: list[str] = []
        self.title_text_parts: list[str] = []
        self._in_title = False
        self._in_json_script = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {k.lower(): v or "" for k, v in attrs}
        tag = tag.lower()

        if tag == "meta":
            key = attrs_map.get("property") or attrs_map.get("name")
            content = attrs_map.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()
        elif tag == "link":
            self.links.append(attrs_map)
        elif tag in {"audio", "video", "source"}:
            src = attrs_map.get("src")
            if src:
                self.sources.append(src.strip())
        elif tag == "script" and attrs_map.get("type", "").lower() == "application/ld+json":
            self._in_json_script = True
            self._json_parts = []
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._in_json_script:
            self.json_scripts.append("".join(self._json_parts).strip())
            self._in_json_script = False
            self._json_parts = []
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_json_script:
            self._json_parts.append(data)
        elif self._in_title:
            self.title_text_parts.append(data)

    @property
    def title(self) -> str | None:
        for key in ("og:title", "twitter:title"):
            if self.meta.get(key):
                return self.meta[key]
        title = " ".join(part.strip() for part in self.title_text_parts if part.strip())
        return title or None


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})


def open_url(url: str, method: str = "GET", timeout: int = 30):
    return urllib.request.urlopen(request(url, method), timeout=timeout)


def normalize_content_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[0].strip().lower() or None


def parse_content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def head(url: str, timeout: int) -> RemoteInfo:
    with open_url(url, "HEAD", timeout) as resp:
        return RemoteInfo(
            final_url=resp.geturl(),
            content_type=normalize_content_type(resp.headers.get("content-type")),
            content_length=parse_content_length(resp.headers.get("content-length")),
            content_disposition=resp.headers.get("content-disposition"),
        )


def is_media_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type.startswith("audio/") or content_type.startswith("video/")


def extension_from_url(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path
    ext = Path(path).suffix.lower()
    return ext if ext in MEDIA_EXTENSIONS else None


def extension_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return CONTENT_TYPE_EXTENSIONS.get(content_type)


def filename_from_content_disposition(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"filename\*=utf-8''([^;]+)", value, re.IGNORECASE)
    if match:
        return urllib.parse.unquote(match.group(1).strip().strip('"'))
    match = re.search(r'filename="?([^";]+)"?', value, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extension_from_content_disposition(value: str | None) -> str | None:
    filename = filename_from_content_disposition(value)
    if not filename:
        return None
    ext = Path(filename).suffix.lower()
    return ext if ext in MEDIA_EXTENSIONS else None


def sanitize_filename(name: str, limit: int = 140) -> str:
    name = urllib.parse.unquote(name)
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "media"
    return name[:limit].rstrip(" .") or "media"


def infer_filename(
    source_url: str,
    media_url: str,
    title: str | None,
    content_type: str | None,
    content_disposition: str | None,
) -> str:
    ext = (
        extension_from_url(media_url)
        or extension_from_content_type(content_type)
        or extension_from_content_disposition(content_disposition)
        or extension_from_url(source_url)
    )
    if not ext:
        fail(f"cannot infer media extension for {media_url}")

    disposition_name = filename_from_content_disposition(content_disposition)
    if title:
        base = sanitize_filename(title)
    elif disposition_name:
        base = sanitize_filename(Path(disposition_name).stem)
    else:
        path_base = posixpath.basename(urllib.parse.urlparse(media_url).path)
        base = sanitize_filename(Path(path_base).stem) if path_base else hashlib.sha256(media_url.encode()).hexdigest()[:16]

    return f"{base}{ext}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe_duration(path: Path) -> float:
    if not shutil.which("ffprobe"):
        fail("ffprobe is required but was not found in PATH")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"ffprobe failed for {path}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        fail(f"ffprobe did not return a numeric duration for {path}: {result.stdout!r}")
    raise AssertionError("unreachable")


def ffmpeg_decode_check(path: Path) -> None:
    if not shutil.which("ffmpeg"):
        fail("ffmpeg is required for --decode-check but was not found in PATH")
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"ffmpeg decode check failed for {path}: {result.stderr.strip()}")


def find_json_media_urls(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"contentUrl", "embedUrl", "url"} and isinstance(nested, str) and is_url(nested):
                if extension_from_url(nested):
                    found.append(nested)
            else:
                found.extend(find_json_media_urls(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_json_media_urls(item))
    return found


def absolutize(base_url: str, candidate: str) -> str:
    return urllib.parse.urljoin(base_url, candidate.strip())


def extract_media_from_page(page_url: str, timeout: int) -> tuple[str, str | None, str]:
    with open_url(page_url, "GET", timeout) as resp:
        final_url = resp.geturl()
        content_type = normalize_content_type(resp.headers.get("content-type"))
        if content_type and not content_type.startswith("text/html"):
            fail(f"expected HTML page but got content-type {content_type} for {page_url}")
        html_bytes = resp.read()

    parser = MediaHTMLParser()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))

    candidates: list[str] = []
    for key in ("og:audio", "og:audio:url", "og:video", "twitter:player:stream"):
        if parser.meta.get(key):
            candidates.append(parser.meta[key])

    for link in parser.links:
        rel = link.get("rel", "").lower()
        link_type = normalize_content_type(link.get("type"))
        href = link.get("href")
        if href and ("enclosure" in rel or is_media_content_type(link_type)):
            candidates.append(href)

    candidates.extend(parser.sources)

    for raw_json in parser.json_scripts:
        try:
            candidates.extend(find_json_media_urls(json.loads(raw_json)))
        except json.JSONDecodeError:
            continue

    for candidate in candidates:
        media_url = absolutize(final_url, candidate)
        if extension_from_url(media_url):
            return media_url, parser.title, final_url
        try:
            remote = head(media_url, timeout)
            if is_media_content_type(remote.content_type) or extension_from_content_disposition(remote.content_disposition):
                return remote.final_url, parser.title, final_url
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue

    fail(f"could not find an audio/video URL in page: {page_url}")
    raise AssertionError("unreachable")


def classify_url(url: str, timeout: int) -> tuple[str, RemoteInfo]:
    if extension_from_url(url):
        try:
            return "direct-url", head(url, timeout)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            return "direct-url", RemoteInfo(url, None, None, None)

    remote = head(url, timeout)
    if is_media_content_type(remote.content_type) or extension_from_content_disposition(remote.content_disposition):
        return "direct-url", remote
    return "page-url", remote


def download_media(
    source_input: str,
    kind: str,
    media_url: str,
    output_dir: Path,
    timeout: int,
    title: str | None,
    page_url: str | None,
    decode_check: bool,
    force: bool,
) -> ResolvedMedia:
    try:
        remote = head(media_url, timeout)
    except urllib.error.HTTPError as exc:
        fail(f"HEAD failed for {media_url}: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f"HEAD failed for {media_url}: {exc}")

    filename = infer_filename(source_input, remote.final_url, title, remote.content_type, remote.content_disposition)
    output_path = output_dir / filename

    if output_path.exists() and not force:
        local_size = output_path.stat().st_size
        if remote.content_length is None or local_size == remote.content_length:
            duration = ffprobe_duration(output_path)
            if decode_check:
                ffmpeg_decode_check(output_path)
            return ResolvedMedia(
                input=source_input,
                kind=kind,
                path=str(output_path),
                media_url=remote.final_url,
                page_url=page_url,
                title=title,
                content_type=remote.content_type,
                content_length=remote.content_length,
                bytes_written=local_size,
                sha256=sha256_file(output_path),
                duration_seconds=duration,
                skipped_existing=True,
            )
        print(
            f"Existing file size {local_size} differs from remote size {remote.content_length}; re-downloading {output_path}",
            file=sys.stderr,
        )

    part_path = output_path.with_name(f"{output_path.name}.part")
    if part_path.exists():
        part_path.unlink()

    digest = hashlib.sha256()
    bytes_written = 0
    start = time.time()
    try:
        with open_url(remote.final_url, "GET", timeout) as resp, part_path.open("wb") as out:
            response_length = parse_content_length(resp.headers.get("content-length"))
            expected_size = remote.content_length if remote.content_length is not None else response_length
            for chunk in iter(lambda: resp.read(1024 * 1024), b""):
                out.write(chunk)
                digest.update(chunk)
                bytes_written += len(chunk)
        if expected_size is not None and bytes_written != expected_size:
            raise RuntimeError(f"downloaded {bytes_written} bytes, expected {expected_size}")
        os.replace(part_path, output_path)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise

    duration = ffprobe_duration(output_path)
    if decode_check:
        ffmpeg_decode_check(output_path)

    elapsed = time.time() - start
    print(
        f"Downloaded {bytes_written} bytes in {elapsed:.1f}s -> {output_path}",
        file=sys.stderr,
    )

    return ResolvedMedia(
        input=source_input,
        kind=kind,
        path=str(output_path),
        media_url=remote.final_url,
        page_url=page_url,
        title=title,
        content_type=remote.content_type,
        content_length=remote.content_length,
        bytes_written=bytes_written,
        sha256=digest.hexdigest(),
        duration_seconds=duration,
        skipped_existing=False,
    )


def resolve_input(value: str, output_dir: Path, timeout: int, decode_check: bool, force: bool) -> ResolvedMedia:
    if not is_url(value):
        path = Path(value).expanduser()
        if not path.exists():
            fail(f"local input does not exist: {value}")
        if not path.is_file():
            fail(f"local input is not a file: {value}")
        duration = ffprobe_duration(path)
        if decode_check:
            ffmpeg_decode_check(path)
        return ResolvedMedia(
            input=value,
            kind="local-file",
            path=str(path.resolve()),
            bytes_written=path.stat().st_size,
            sha256=sha256_file(path),
            duration_seconds=duration,
        )

    kind, remote = classify_url(value, timeout)
    title = None
    page_url = None
    media_url = remote.final_url

    if kind == "page-url":
        media_url, title, page_url = extract_media_from_page(remote.final_url, timeout)
        kind = "webpage"

    return download_media(
        source_input=value,
        kind=kind,
        media_url=media_url,
        output_dir=output_dir,
        timeout=timeout,
        title=title,
        page_url=page_url,
        decode_check=decode_check,
        force=force,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve ASR inputs to validated local media files")
    parser.add_argument("inputs", nargs="+", help="Local paths, direct media URLs, or podcast/web page URLs")
    parser.add_argument("--output-dir", required=True, help="Directory for downloaded media")
    parser.add_argument("--manifest", help="Write JSON manifest to this path")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    parser.add_argument("--decode-check", action="store_true", help="Run ffmpeg full decode validation after ffprobe")
    parser.add_argument("--force", action="store_true", help="Re-download even if a same-size file already exists")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    resolved: list[ResolvedMedia] = []
    for input_value in args.inputs:
        item = resolve_input(input_value, output_dir, args.timeout, args.decode_check, args.force)
        resolved.append(item)
        print(item.path)

    manifest = {
        "generated_at_unix": int(time.time()),
        "items": [dataclasses.asdict(item) for item in resolved],
    }
    if args.manifest:
        manifest_path = Path(args.manifest).expanduser()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = manifest_path.with_name(f"{manifest_path.name}.tmp")
        tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, manifest_path)


if __name__ == "__main__":
    main()

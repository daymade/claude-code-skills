#!/usr/bin/env python3
"""
YouTube video downloader using yt-dlp with robust error handling.

This script handles common issues like nsig extraction failures and network problems,
especially useful for users behind proxies or in regions with YouTube access issues.

Requirements:
    - yt-dlp: Install via `brew install yt-dlp` (macOS) or `pip install yt-dlp` (cross-platform)
    - A supported JavaScript runtime and EJS components for current YouTube extraction
    - Optional PO token provider: see ../references/po-token-setup.md

Usage:
    scripts/download_video.py "https://youtu.be/VIDEO_ID"
    scripts/download_video.py "https://youtu.be/VIDEO_ID" --audio-only
    scripts/download_video.py "https://youtu.be/VIDEO_ID" --quality 1080p
    scripts/download_video.py "https://youtu.be/VIDEO_ID" -o ~/Downloads

Note:
    Start with yt-dlp's default clients. --auto-po-token authorizes provider setup
    only after a failed download with an explicit missing-token diagnostic.
    Browser cookies and alternate clients require explicit options.
"""

import argparse
import json
import subprocess
import sys
import shutil
import time
import os
import re
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import urlopen
from urllib.error import URLError


PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

QUALITY_PRESETS = {
    "best": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best",
    "720p": "bestvideo[height<=720]+bestaudio/best",
    "480p": "bestvideo[height<=480]+bestaudio/best",
    "360p": "bestvideo[height<=360]+bestaudio/best",
    "worst": "worstvideo+worstaudio/worst",
}


def build_output_template(output_dir: str, template: Optional[str]) -> str:
    if template:
        template_path = Path(template)
        if template_path.is_absolute():
            return template
        return str(Path(output_dir).expanduser().resolve() / template)

    return str(Path(output_dir).expanduser().resolve() / "%(title)s.%(ext)s")


def list_files(root: Path) -> set:
    return {path for path in root.rglob("*") if path.is_file()}


def human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        num_bytes /= 1024.0
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
    return f"{num_bytes:.1f} PB"


def pick_primary_file(files: Iterable[Path], audio_only: bool) -> Optional[Path]:
    video_exts = {".mp4", ".webm", ".mkv", ".mov", ".m4v"}
    audio_exts = {".mp3", ".m4a", ".opus", ".aac", ".flac", ".wav"}
    candidates = []
    for path in files:
        if path.suffix.lower() in {".part", ".ytdl", ".tmp"}:
            continue
        if audio_only:
            if path.suffix.lower() in audio_exts:
                candidates.append(path)
        else:
            if path.suffix.lower() in video_exts:
                candidates.append(path)

    if not candidates:
        candidates = [path for path in files if path.suffix.lower() not in {".part", ".ytdl", ".tmp"}]

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_size)


def get_video_resolution(path: Path) -> Optional[str]:
    check = subprocess.run(["which", "ffprobe"], capture_output=True, text=True)
    if check.returncode != 0:
        return None

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def filter_cookie_lines(text: str) -> str:
    if not text:
        return ""
    filtered = []
    for line in text.splitlines():
        lowered = line.lower()
        if "extracting cookies" in lowered:
            continue
        if "extracted" in lowered and "cookies" in lowered:
            continue
        filtered.append(line)
    return "\n".join(filtered)


def run_yt_dlp(cmd: list, hide_cookie_logs: bool = False) -> subprocess.CompletedProcess:
    # Retain diagnostics even without cookies, while keeping progress visible.
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    ) as process:
        lines = []
        for line in process.stdout:
            lines.append(line)
            visible = filter_cookie_lines(line) if hide_cookie_logs else line.rstrip("\n")
            if visible:
                print(visible, flush=True)
        return subprocess.CompletedProcess(cmd, process.wait(), "".join(lines), "")


def final_error(result: subprocess.CompletedProcess) -> str:
    """Use the terminal failure, not explanatory words in an unused-format warning."""
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    errors = [line.strip() for line in text.splitlines() if re.match(
        r"^(?:error:\s*\S|\[download\].*error:|http error [45])", line.strip())]
    return errors[-1] if errors else ""


def has_403_error(result: subprocess.CompletedProcess) -> bool:
    text = final_error(result)
    return any(marker in text for marker in (
        "http error 403", "403: forbidden", "fragment 1 not found",
    ))


def has_pot_error(result: subprocess.CompletedProcess) -> bool:
    """Identify an explicit missing-token diagnostic, not a generic download error."""
    if result.returncode == 0:
        return False
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    # A provider timeout or a warning for an unused client does not explain a
    # failed network request. Leave these failures on the network/recovery path.
    if any(word in text for word in ("timed out", "timeout", "ssl", "connection reset", "network is unreachable")):
        return False
    token_lines = [
        line for line in text.splitlines()
        if
        re.search(r"\bpo[ _-]?tokens?\b", line)
        and re.search(r"\b(require[ds]?|required|missing|not provided|not supplied|must provide)\b", line)
    ]
    failure = final_error(result)
    return bool(token_lines) and (
        failure in token_lines
        or any(marker in failure for marker in (
            "only images are available", "requested format is not available",
            "http error 403", "403: forbidden",
        ))
    )


def has_wpc_error(result: subprocess.CompletedProcess) -> bool:
    text = ""
    if hasattr(result, "stdout") and result.stdout:
        text += result.stdout
    if hasattr(result, "stderr") and result.stderr:
        text += result.stderr
    text = text.lower()
    return "pot:wpc" in text or "webpoclient" in text


def with_player_client(cmd: list, client: str) -> list:
    """Replace only the YouTube player_client, retaining provider arguments."""
    rebuilt = []
    youtube_args = []
    index = 0
    while index < len(cmd):
        token = cmd[index]
        if token == "--extractor-args" and index + 1 < len(cmd):
            value = cmd[index + 1]
            if value.startswith("youtube:"):
                youtube_args.extend(
                    part for part in value[len("youtube:"):].split(";")
                    if part and not part.startswith("player_client="))
            else:
                rebuilt.extend([token, value])
            index += 2
            continue
        rebuilt.append(token)
        index += 1
    youtube_args.append(f"player_client={client}")
    # yt-dlp replaces repeated dictionaries for the same extractor. Keep all
    # YouTube settings together so its real parser retains them.
    rebuilt.extend(["--extractor-args", "youtube:" + ";".join(youtube_args)])
    return rebuilt


def get_proxy_settings(proxy_arg: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if proxy_arg:
        proxy = proxy_arg
    else:
        proxy = (
            os.environ.get("ALL_PROXY")
            or os.environ.get("all_proxy")
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
        )
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    return proxy, no_proxy


def normalize_proxy_for_docker(proxy_url: str) -> str:
    parsed = urlparse(proxy_url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        host = "host.docker.internal"
        netloc = ""
        if parsed.username or parsed.password:
            userinfo = parsed.username or ""
            if parsed.password:
                userinfo += f":{parsed.password}"
            netloc = f"{userinfo}@"
        if parsed.port:
            netloc += f"{host}:{parsed.port}"
        else:
            netloc += host
        parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    return proxy_url


def is_localhost_proxy(proxy_url: str) -> bool:
    parsed = urlparse(proxy_url)
    return parsed.hostname in {"127.0.0.1", "localhost"}


def find_chrome_path() -> Optional[str]:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def with_wpc_browser(cmd: list, browser_path: Optional[str]) -> list:
    if not browser_path:
        return cmd
    return cmd + ["--extractor-args", f"youtubepot-wpc:browser_path={browser_path}"]


def provider_ping(url: str = "http://127.0.0.1:4416/ping") -> bool:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status == 200
    except (URLError, ConnectionResetError, TimeoutError):
        return False


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
    return result.returncode == 0


def docker_daemon_ready() -> bool:
    result = subprocess.run(["docker", "info"], capture_output=True, text=True)
    return result.returncode == 0


def wait_for_provider(timeout: int = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if provider_ping():
            return True
        time.sleep(1)
    return False


def container_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and name in result.stdout.split()


def parse_yt_dlp_version() -> Optional[str]:
    result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def version_at_least(version: str, minimum: str) -> bool:
    def parse(value: str) -> list:
        return [int(part) for part in value.split(".") if part.isdigit()]

    current = parse(version)
    required = parse(minimum)
    if not current or not required:
        return False
    while len(current) < len(required):
        current.append(0)
    while len(required) < len(current):
        required.append(0)
    return current >= required


def yt_dlp_python() -> Optional[str]:
    yt_dlp_path = shutil.which("yt-dlp")
    if not yt_dlp_path:
        return None
    try:
        with open(yt_dlp_path, "r", encoding="utf-8") as handle:
            first = handle.readline().strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    shebang = first[2:].strip()
    if shebang.endswith("env python3") or shebang.endswith("env python"):
        return "python3"
    return shebang


def ensure_pot_plugin_installed(proxy_url: Optional[str]) -> bool:
    version = parse_yt_dlp_version()
    if not version or not version_at_least(version, "2025.05.22"):
        print("⚠️  yt-dlp needs to be updated before enabling PO Token provider.")
        return False

    python_bin = yt_dlp_python()
    if not python_bin:
        print("⚠️  Unable to locate yt-dlp's Python interpreter for plugin install.")
        return False

    check = subprocess.run(
        [python_bin, "-m", "pip", "show", "bgutil-ytdlp-pot-provider"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        return True

    print("⚠️  Installing PO Token provider plugin (one-time setup)...")
    install_cmd = [python_bin, "-m", "pip", "install", "bgutil-ytdlp-pot-provider", "-i", PYPI_MIRROR]
    if proxy_url:
        install_cmd.extend(["--proxy", proxy_url])
    install = subprocess.run(install_cmd, capture_output=True, text=True)
    return install.returncode == 0


def ensure_wpc_provider(proxy_url: Optional[str]) -> bool:
    version = parse_yt_dlp_version()
    if not version or not version_at_least(version, "2025.09.26"):
        print("⚠️  yt-dlp needs to be updated before enabling the WPC PO Token provider.")
        return False

    python_bin = yt_dlp_python()
    if not python_bin:
        print("⚠️  Unable to locate yt-dlp's Python interpreter for WPC provider install.")
        return False

    check = subprocess.run(
        [python_bin, "-m", "pip", "show", "yt-dlp-getpot-wpc"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        return True

    print("⚠️  Installing WPC PO Token provider (one-time setup)...")
    install_cmd = [python_bin, "-m", "pip", "install", "-U", "yt-dlp-getpot-wpc", "-i", PYPI_MIRROR]
    if proxy_url:
        install_cmd.extend(["--proxy", proxy_url])
    install = subprocess.run(install_cmd, capture_output=True, text=True)
    return install.returncode == 0


def ensure_po_token_provider(proxy_url: Optional[str], no_proxy: Optional[str]) -> Optional[str]:
    if not ensure_pot_plugin_installed(proxy_url):
        return "wpc" if ensure_wpc_provider(proxy_url) else None

    if provider_ping():
        return "bgutil"

    if not docker_available():
        print("⚠️  Docker is not available. Switching to browser-based PO Token provider...")
        return "wpc" if ensure_wpc_provider(proxy_url) else None

    if not docker_daemon_ready():
        print("⚠️  Docker daemon is not running. Switching to browser-based PO Token provider...")
        return "wpc" if ensure_wpc_provider(proxy_url) else None

    name = "bgutil-pot-provider"
    if container_exists(name):
        start = subprocess.run(["docker", "start", name], capture_output=True, text=True)
        if start.returncode != 0:
            print("⚠️  Docker container failed to start. Switching to browser-based PO Token provider...")
            return "wpc" if ensure_wpc_provider(proxy_url) else None
    else:
        env_args = []
        use_host_network = False
        docker_proxy = None
        if proxy_url:
            use_host_network = is_localhost_proxy(proxy_url)
            docker_proxy = proxy_url if use_host_network else normalize_proxy_for_docker(proxy_url)
            env_args.extend(
                [
                    "-e",
                    f"HTTP_PROXY={docker_proxy}",
                    "-e",
                    f"HTTPS_PROXY={docker_proxy}",
                    "-e",
                    f"ALL_PROXY={docker_proxy}",
                    "-e",
                    f"http_proxy={docker_proxy}",
                    "-e",
                    f"https_proxy={docker_proxy}",
                    "-e",
                    f"all_proxy={docker_proxy}",
                ]
            )
        if no_proxy:
            env_args.extend(
                [
                    "-e",
                    f"NO_PROXY={no_proxy}",
                    "-e",
                    f"no_proxy={no_proxy}",
                ]
            )
        run_cmd = ["docker", "run", "-d", "--name", name]
        if use_host_network:
            run_cmd.extend(["--network", "host"])
        run_cmd.extend(
            [
                "-p",
                "4416:4416",
                *env_args,
                "--init",
                "brainicism/bgutil-ytdlp-pot-provider",
            ]
        )

        run = subprocess.run(run_cmd, capture_output=True, text=True)
        if run.returncode != 0:
            if use_host_network and proxy_url:
                # Retry without host network using host.docker.internal proxy
                docker_proxy = normalize_proxy_for_docker(proxy_url)
                env_args = [
                    "-e",
                    f"HTTP_PROXY={docker_proxy}",
                    "-e",
                    f"HTTPS_PROXY={docker_proxy}",
                    "-e",
                    f"ALL_PROXY={docker_proxy}",
                    "-e",
                    f"http_proxy={docker_proxy}",
                    "-e",
                    f"https_proxy={docker_proxy}",
                    "-e",
                    f"all_proxy={docker_proxy}",
                ]
                if no_proxy:
                    env_args.extend(
                        [
                            "-e",
                            f"NO_PROXY={no_proxy}",
                            "-e",
                            f"no_proxy={no_proxy}",
                        ]
                    )
                retry = subprocess.run(
                    [
                        "docker",
                        "run",
                        "-d",
                        "--name",
                        name,
                        "-p",
                        "4416:4416",
                        *env_args,
                        "--init",
                        "brainicism/bgutil-ytdlp-pot-provider",
                    ],
                    capture_output=True,
                    text=True,
                )
                if retry.returncode == 0:
                    run = retry
                else:
                    print("⚠️  Docker provider failed to start. Switching to browser-based PO Token provider...")
                    return "wpc" if ensure_wpc_provider(proxy_url) else None
            else:
                print("⚠️  Docker provider failed to start. Switching to browser-based PO Token provider...")
                return "wpc" if ensure_wpc_provider(proxy_url) else None

    if wait_for_provider():
        print("✓ PO Token provider is running.")
        return "bgutil"

    # Do not remove/restart a shared container just because its health probe failed.
    print("⚠️  Docker provider did not respond; preserving it and trying the browser provider...")
    return "wpc" if ensure_wpc_provider(proxy_url) else None


def restart_po_token_provider(proxy_url: Optional[str], no_proxy: Optional[str]) -> bool:
    name = "bgutil-pot-provider"
    if not docker_available() or not docker_daemon_ready():
        return False
    if container_exists(name):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
    env_args = []
    use_host_network = False
    docker_proxy = None
    if proxy_url:
        use_host_network = is_localhost_proxy(proxy_url)
        docker_proxy = proxy_url if use_host_network else normalize_proxy_for_docker(proxy_url)
        env_args.extend(
            [
                "-e",
                f"HTTP_PROXY={docker_proxy}",
                "-e",
                f"HTTPS_PROXY={docker_proxy}",
                "-e",
                f"ALL_PROXY={docker_proxy}",
                "-e",
                f"http_proxy={docker_proxy}",
                "-e",
                f"https_proxy={docker_proxy}",
                "-e",
                f"all_proxy={docker_proxy}",
            ]
        )
    if no_proxy:
        env_args.extend(
            [
                "-e",
                f"NO_PROXY={no_proxy}",
                "-e",
                f"no_proxy={no_proxy}",
            ]
        )
    run_cmd = ["docker", "run", "-d", "--name", name]
    if use_host_network:
        run_cmd.extend(["--network", "host"])
    run_cmd.extend(
        [
            "-p",
            "4416:4416",
            *env_args,
            "--init",
            "brainicism/bgutil-ytdlp-pot-provider",
        ]
    )

    run = subprocess.run(run_cmd, capture_output=True, text=True)
    if run.returncode != 0 and use_host_network:
        docker_proxy = normalize_proxy_for_docker(proxy_url)
        env_args = [
            "-e",
            f"HTTP_PROXY={docker_proxy}",
            "-e",
            f"HTTPS_PROXY={docker_proxy}",
            "-e",
            f"ALL_PROXY={docker_proxy}",
            "-e",
            f"http_proxy={docker_proxy}",
            "-e",
            f"https_proxy={docker_proxy}",
            "-e",
            f"all_proxy={docker_proxy}",
        ]
        if no_proxy:
            env_args.extend(
                [
                    "-e",
                    f"NO_PROXY={no_proxy}",
                    "-e",
                    f"no_proxy={no_proxy}",
                ]
            )
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-p",
                "4416:4416",
                *env_args,
                "--init",
                "brainicism/bgutil-ytdlp-pot-provider",
            ],
            capture_output=True,
            text=True,
        )
    return wait_for_provider()


def fallback_format_for_quality(quality: Optional[str]) -> str:
    if not quality or quality == "best":
        return "best[protocol!*=m3u8][ext=mp4]/best[protocol!*=m3u8]/best"
    if quality.endswith("p") and quality[:-1].isdigit():
        height = quality[:-1]
        return (
            f"best[height<={height}][protocol!*=m3u8][ext=mp4]/"
            f"best[height<={height}][protocol!*=m3u8]/best[protocol!*=m3u8]"
        )
    return "best[protocol!*=m3u8][ext=mp4]/best[protocol!*=m3u8]/best"


def print_video_info(cmd_base: list, url: str, hide_cookie_logs: bool = False) -> int:
    info_cmd = cmd_base + ["--skip-download", "--dump-json", "--no-playlist", url]
    result = subprocess.run(info_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("✗ Failed to fetch video metadata")
        if result.stderr:
            print(filter_cookie_lines(result.stderr).strip())
        fallback = fetch_oembed_info(url)
        if fallback:
            print("\n✓ Retrieved metadata via YouTube oEmbed (limited fields).")
            render_oembed_info(fallback)
            return 0
        return result.returncode

    first_line = result.stdout.strip().splitlines()[0] if result.stdout else ""
    if not first_line:
        print("✗ No metadata returned")
        return 1

    try:
        info = json.loads(first_line)
        title = info.get("title", "Unknown title")
        uploader = info.get("uploader") or info.get("channel") or "Unknown uploader"
        duration = info.get("duration")
        duration_text = f"{duration}s" if isinstance(duration, int) else "Unknown"
        thumbnail = info.get("thumbnail")
        print(f"Title: {title}")
        print(f"Uploader: {uploader}")
        print(f"Duration: {duration_text}")
        if thumbnail:
            print(f"Thumbnail: {thumbnail}")
    except json.JSONDecodeError:
        print(first_line)

    return 0


def fetch_oembed_info(url: str) -> Optional[dict]:
    oembed_url = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
    try:
        with urlopen(oembed_url, timeout=15) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)
    except Exception:
        return None


def render_oembed_info(info: dict) -> None:
    title = info.get("title", "Unknown title")
    uploader = info.get("author_name", "Unknown uploader")
    thumbnail = info.get("thumbnail_url")
    print(f"Title: {title}")
    print(f"Uploader: {uploader}")
    print("Duration: Unknown")
    if thumbnail:
        print(f"Thumbnail: {thumbnail}")


def download_video(
    url: str,
    output_dir: str = ".",
    format_spec: str = None,
    quality: str = None,
    output_template: str = None,
    merge_format: str = "mp4",
    subtitles: bool = False,
    subtitle_lang: str = "en",
    cookies_from_browser: str = None,
    cookies_file: str = None,
    player_client: str = None,
    auto_po_token: bool = False,
    proxy: str = None,
    wpc_browser_path: str = None,
    allow_playlist: bool = False,
    use_android_client: bool = False,
    audio_only: bool = False,
    list_formats: bool = False,
    info_only: bool = False,
    js_runtimes: str = None,
) -> int:
    """
    Download a YouTube video using yt-dlp.

    Args:
        url: YouTube video URL
        output_dir: Directory to save the downloaded file
        format_spec: Format specification (e.g., "bestvideo+bestaudio/best")
        quality: Quality preset (best, 1080p, 720p, 480p, 360p, worst)
        output_template: Output filename template (yt-dlp template syntax)
        merge_format: Merge output container format (e.g., mp4, mkv)
        subtitles: Download subtitles if available
        subtitle_lang: Subtitle languages (comma-separated)
        cookies_from_browser: Load cookies from browser (e.g., chrome, firefox)
        cookies_file: Load cookies from a cookies.txt file
        player_client: Use a specific YouTube player client (e.g., web_safari)
        auto_po_token: Authorize provider setup after a failed explicit PO-token diagnostic
        proxy: Proxy URL for yt-dlp and PO Token provider
        wpc_browser_path: Browser path for WPC PO Token provider
        allow_playlist: Allow playlist downloads (default: False)
        use_android_client: Explicit legacy Android client request (default: False)
        audio_only: Download audio only
        list_formats: List available formats instead of downloading
        info_only: Print video info before exiting
        js_runtimes: Explicit yt-dlp JavaScript runtime configuration (e.g., node)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Check if yt-dlp is installed
    check_result = subprocess.run(
        ["which", "yt-dlp"], capture_output=True, text=True
    )
    if check_result.returncode != 0:
        print("✗ Error: yt-dlp is not installed")
        print("  Install via: brew install yt-dlp  # or: pip install yt-dlp")
        return 1

    # Build yt-dlp command
    cmd = ["yt-dlp"]

    if cookies_from_browser and cookies_file:
        print("✗ Error: Use either --cookies-from-browser or --cookies-file, not both.")
        return 2

    proxy_value, no_proxy = get_proxy_settings(proxy)

    has_cookies = bool(cookies_from_browser or cookies_file)
    if has_cookies and player_client:
        clients = set(player_client.split(","))
        if clients & {"android", "android_vr", "ios", "tv_simply"}:
            print("✗ Error: The selected player client does not support account cookies.")
            return 2
    # Never make an alternate client the consequence of disabling PO tokens.
    use_android = use_android_client and not (has_cookies or player_client)
    if use_android:
        cmd.extend(["--extractor-args", "youtube:player_client=android"])

    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    elif cookies_file:
        cmd.extend(["--cookies", cookies_file])

    if proxy_value:
        cmd.extend(["--proxy", proxy_value])
    if js_runtimes:
        cmd.extend(["--js-runtimes", js_runtimes])

    if player_client:
        cmd.extend(["--extractor-args", f"youtube:player_client={player_client}"])

    if not allow_playlist:
        cmd.append("--no-playlist")

    # List formats if requested
    if list_formats:
        cmd.extend(["-F", url])
        result = run_yt_dlp(cmd, hide_cookie_logs=bool(cookies_from_browser))

        return result.returncode

    if info_only:
        return print_video_info(cmd, url, hide_cookie_logs=bool(cookies_from_browser))

    if format_spec and quality:
        print("✗ Error: Use either --format or --quality, not both.")
        return 2

    if not format_spec and not quality and not audio_only:
        quality = "best"

    format_from_quality = False
    if quality:
        format_spec = QUALITY_PRESETS.get(quality)
        if not format_spec:
            print(f"✗ Error: Unsupported quality preset: {quality}")
            return 2
        format_from_quality = True

    # Set output directory
    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    output_template_final = build_output_template(str(output_root), output_template)
    cmd.extend(["-o", output_template_final])

    # Handle audio-only downloads
    if audio_only:
        cmd.extend(["-x", "--audio-format", "mp3"])
    if format_spec:
        cmd.extend(["-f", format_spec])

    if subtitles:
        cmd.extend(["--write-subs", "--write-auto-subs", "--sub-lang", subtitle_lang])

    if merge_format:
        cmd.extend(["--merge-output-format", merge_format])

    # Add URL
    cmd.append(url)

    def finalize_download(before_snapshot: set) -> None:
        after_files = list_files(output_root)
        new_files = sorted(after_files - before_snapshot)
        primary = pick_primary_file(new_files, audio_only=audio_only)
        if primary:
            size = human_size(primary.stat().st_size)
            print(f"\n✓ Download completed successfully!")
            print(f"  File: {primary}")
            print(f"  Size: {size}")
            if audio_only:
                print("  Resolution: N/A (audio-only)")
            else:
                resolution = get_video_resolution(primary)
                if resolution:
                    print(f"  Resolution: {resolution}")
                else:
                    print("  Resolution: Not available")
        else:
            print(f"\n✓ Download completed successfully!")
            print(f"  Location: {output_root}")

    before_files = list_files(output_root)
    print(f"Executing: {' '.join(cmd)}")
    result = run_yt_dlp(cmd, hide_cookie_logs=bool(cookies_from_browser))
    if result.returncode == 0:
        finalize_download(before_files)
        return 0

    if has_pot_error(result):
        if auto_po_token:
            token_client = player_client or ("web_safari" if has_cookies else "mweb")
            if use_android or token_client not in {"mweb", "web", "web_safari", "web_music", "web_creator"}:
                print("✗ Select a compatible web player client before using the web PO Token provider.")
                return 2
            print("\n⚠️  Explicit PO Token requirement detected. Preparing the authorized provider...")
            provider_type = ensure_po_token_provider(proxy_value, no_proxy)
            if provider_type:
                cmd = with_player_client(cmd, token_client)
                if provider_type == "wpc":
                    browser = wpc_browser_path or find_chrome_path()
                    cmd = with_wpc_browser(cmd, browser)
                print(f"Executing: {' '.join(cmd)}")
                result = run_yt_dlp(cmd, hide_cookie_logs=bool(cookies_from_browser))
                if result.returncode == 0:
                    finalize_download(before_files)
                    return 0
                diagnostics = ((result.stdout or "") + (result.stderr or "")).lower()
                if provider_type == "bgutil" and "[pot:bgutil" in diagnostics and "error" in diagnostics:
                    print("\n⚠️  The authorized provider failed. Trying WPC without restarting the shared service...")
                    if ensure_wpc_provider(proxy_value):
                        provider_type = "wpc"
                        cmd = with_wpc_browser(cmd, wpc_browser_path or find_chrome_path())
                        result = run_yt_dlp(cmd, hide_cookie_logs=bool(cookies_from_browser))
                        if result.returncode == 0:
                            finalize_download(before_files)
                            return 0
                if provider_type == "wpc" and has_wpc_error(result):
                    print("\n⚠️  Browser verification not ready. Retrying once; keep its window open...")
                    time.sleep(3)
                    result = run_yt_dlp(cmd, hide_cookie_logs=bool(cookies_from_browser))
                    if result.returncode == 0:
                        finalize_download(before_files)
                        return 0
            else:
                print("✗ Authorized PO Token setup failed; the original download was already attempted.")
                return result.returncode
        else:
            print("\nPO Token requirement detected. If provider setup is authorized, retry with --auto-po-token.")

    # A 403 alone never authorizes installing a provider or extracting cookies.
    # Retain explicitly supplied cookies on the one compatible-client retry.
    if has_cookies and not player_client and has_403_error(result):
        print("\n⚠️  Retrying the authorized cookie session with web_safari...")
        cmd = with_player_client(cmd, "web_safari")
        result = run_yt_dlp(cmd, hide_cookie_logs=bool(cookies_from_browser))
        if result.returncode == 0:
            finalize_download(before_files)
            return 0

    if not audio_only and format_from_quality and has_403_error(result):
        print("\n⚠️  403/fragment failure. Retrying once with progressive formats; quality may be lower...")
        retry_cmd = cmd[:]
        retry_format = fallback_format_for_quality(quality)
        retry_cmd[retry_cmd.index("-f") + 1] = retry_format
        result = run_yt_dlp(retry_cmd, hide_cookie_logs=bool(cookies_from_browser))
        if result.returncode == 0:
            finalize_download(before_files)
            return 0

    print(f"\n✗ Download failed with exit code {result.returncode}")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube videos using yt-dlp with robust error handling"
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--output-template",
        help="Output template (e.g., '%%(title)s.%%(ext)s')",
    )
    parser.add_argument(
        "-f", "--format", help="Format specification (e.g., 'bestvideo+bestaudio/best')"
    )
    parser.add_argument(
        "-q",
        "--quality",
        choices=sorted(QUALITY_PRESETS.keys()),
        help="Quality preset (best, 1080p, 720p, 480p, 360p, worst)",
    )
    parser.add_argument(
        "--merge-format",
        default="mp4",
        help="Merge output container format (default: mp4)",
    )
    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Download subtitles if available",
    )
    parser.add_argument(
        "--sub-lang",
        default="en",
        help="Subtitle languages (comma-separated, default: en)",
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="Load cookies from browser (e.g., chrome, firefox)",
    )
    parser.add_argument(
        "--cookies-file",
        help="Load cookies from a cookies.txt file",
    )
    parser.add_argument(
        "--player-client",
        help="Use a specific YouTube player client (e.g., web_safari)",
    )
    parser.add_argument(
        "--proxy",
        help="Proxy URL for yt-dlp and PO Token provider (e.g., http://127.0.0.1:1082)",
    )
    parser.add_argument(
        "--wpc-browser-path",
        help="Browser executable path for WPC PO Token provider",
    )
    parser.add_argument(
        "--js-runtimes",
        help="Enable an installed yt-dlp JavaScript runtime (e.g., node or node:/path/to/node)",
    )
    auto_group = parser.add_mutually_exclusive_group()
    auto_group.add_argument(
        "--auto-po-token",
        action="store_true",
        help="Authorize provider installation/start after a failed explicit PO Token diagnostic",
    )
    auto_group.add_argument(
        "--no-auto-po-token",
        action="store_true",
        help="Do not install/start a PO Token provider (default)",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Allow playlist downloads (default: single video only)",
    )
    parser.add_argument(
        "--no-android-client",
        action="store_true",
        help="Compatibility option: default clients are already used; select Android explicitly with --player-client",
    )
    parser.add_argument(
        "-a", "--audio-only", action="store_true", help="Download audio only (as MP3)"
    )
    parser.add_argument(
        "-F", "--list-formats", action="store_true", help="List available formats"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Print video metadata (title/uploader/duration) and exit",
    )

    args = parser.parse_args()

    exit_code = download_video(
        url=args.url,
        output_dir=args.output_dir,
        format_spec=args.format,
        quality=args.quality,
        output_template=args.output_template,
        merge_format=args.merge_format,
        subtitles=args.subtitles,
        subtitle_lang=args.sub_lang,
        cookies_from_browser=args.cookies_from_browser,
        cookies_file=args.cookies_file,
        player_client=args.player_client,
        auto_po_token=args.auto_po_token,
        proxy=args.proxy,
        wpc_browser_path=args.wpc_browser_path,
        allow_playlist=args.playlist,
        use_android_client=False,
        audio_only=args.audio_only,
        list_formats=args.list_formats,
        info_only=args.info,
        js_runtimes=args.js_runtimes,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

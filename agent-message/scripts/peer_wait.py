#!/usr/bin/env python3
"""Event-driven local filesystem wait primitives for peer-message.

Stdlib-only helper used by `peer.py wait` and `peer.py send --wait-reply`.
On macOS/BSD (`select.kqueue`), watches existing target files and their nearest
existing parent directories with `KQ_FILTER_VNODE` (zero busy-loop, sub-ms
wakeup latency). Falls back cleanly to bounded sleeping polls on platforms
without `kqueue` or if `kqueue` fails with `OSError`.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import select
import time
from typing import Any, Callable, Iterable

MIN_TIMEOUT_SECONDS = 0.0
MAX_TIMEOUT_SECONDS = 3600.0
DEFAULT_POLL_INTERVAL = 0.25
_DIRECT_KQUEUE_SLICE_SECONDS = 2.0


def clamp_timeout(timeout_sec: float) -> float:
    """Validate finite timeout and clamp to [0.0, 3600.0] seconds."""
    try:
        value = float(timeout_sec)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"timeout_sec must be a finite number, got {timeout_sec!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"timeout_sec must be finite, got {timeout_sec!r}")
    if value < MIN_TIMEOUT_SECONDS:
        return MIN_TIMEOUT_SECONDS
    if value > MAX_TIMEOUT_SECONDS:
        return MAX_TIMEOUT_SECONDS
    return value


def _normalize_paths(raw_paths: Iterable[Path | str] | None) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    if not raw_paths:
        return out
    for item in raw_paths:
        if item is None:
            continue
        p = Path(item).expanduser()
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def watch_paths_for_target(
    target: str,
    *,
    claude_home: Path | None = None,
    codex_home: Path | None = None,
    antigravity_home: Path | None = None,
    state_dir: Path | None = None,
    extra_paths: Iterable[Path | str] = (),
) -> list[Path]:
    """Return candidate local files/directories to watch for inbound updates to `target`."""
    candidates: list[Path] = []

    if state_dir is not None:
        sd = Path(state_dir).expanduser()
        candidates.append(sd / "coordination.sqlite3")
        candidates.append(sd / "coordination.sqlite3-wal")

    if isinstance(target, str) and target.startswith(("antigravity:", "agy:")):
        raw_id = (
            target.removeprefix("antigravity:")
            if target.startswith("antigravity:")
            else target.removeprefix("agy:")
        ).strip().lower()
        if raw_id:
            if state_dir is not None:
                sd = Path(state_dir).expanduser()
                candidates.append(sd / "antigravity-inbox" / f"{raw_id}.jsonl")
            if antigravity_home is not None:
                ah = Path(antigravity_home).expanduser()
                logs_dir = ah / "brain" / raw_id / ".system_generated" / "logs"
                candidates.append(logs_dir / "transcript.jsonl")
                candidates.append(logs_dir / "transcript_full.jsonl")
    elif isinstance(target, str) and target.startswith("codex:"):
        if codex_home is not None:
            ch = Path(codex_home).expanduser()
            candidates.append(ch)
            if ch.is_dir():
                for pattern in ("queue_*.sqlite", "thread_history_*.sqlite"):
                    for db_path in sorted(ch.glob(pattern)):
                        candidates.append(db_path)
                        candidates.append(Path(f"{db_path}-wal"))
    elif isinstance(target, str) and target.startswith(("claude-session:", "claude-pid:", "claude:")):
        session_id = (
            target.removeprefix("claude-session:").strip()
            if target.startswith("claude-session:")
            else ""
        )
        if claude_home is not None:
            cl = Path(claude_home).expanduser()
            projects = cl / "projects"
            candidates.append(projects)
            if session_id and projects.is_dir():
                for transcript in sorted(projects.glob(f"*/{session_id}.jsonl")):
                    candidates.append(transcript)
            sessions_dir = cl / "sessions"
            if sessions_dir.is_dir():
                candidates.append(sessions_dir)

    for extra in extra_paths:
        candidates.append(Path(extra).expanduser())

    return _normalize_paths(candidates)


def _nearest_existing_dir(path: Path) -> tuple[Path | None, bool]:
    """Return (nearest_existing_dir, is_direct_parent) for `path`."""
    direct_parent = path.parent
    current = direct_parent
    while True:
        try:
            if current.is_dir():
                return current, (current == direct_parent)
        except OSError:
            pass
        if current.parent == current:
            return None, False
        current = current.parent


def _kqueue_available() -> bool:
    return (
        hasattr(select, "kqueue")
        and hasattr(select, "kevent")
        and hasattr(select, "KQ_FILTER_VNODE")
    )


def _open_event_fd(path: Path) -> int | None:
    open_flags = getattr(os, "O_EVTONLY", os.O_RDONLY)
    try:
        return os.open(path, open_flags)
    except OSError:
        return None


def _arm_kqueue_watches(
    kq: Any, paths: list[Path]
) -> tuple[list[int], dict[int, bool], bool]:
    """Register VNODE kevents for existing files + nearest existing parent dirs.

    Returns (opened_fds, fd_is_file, has_indirect_ancestor).
    """
    file_fflags = (
        select.KQ_NOTE_WRITE
        | select.KQ_NOTE_EXTEND
        | select.KQ_NOTE_DELETE
        | select.KQ_NOTE_RENAME
        | select.KQ_NOTE_ATTRIB
    )
    dir_fflags = (
        select.KQ_NOTE_WRITE
        | select.KQ_NOTE_EXTEND
        | select.KQ_NOTE_RENAME
    )
    ev_flags = select.KQ_EV_ADD | select.KQ_EV_CLEAR

    opened_fds: list[int] = []
    fd_is_file: dict[int, bool] = {}
    armed_targets: set[str] = set()
    kevents: list[Any] = []
    has_indirect_ancestor = False

    def _add_watch(target_path: Path, *, is_file: bool) -> None:
        key = str(target_path)
        if key in armed_targets:
            return
        fd = _open_event_fd(target_path)
        if fd is None:
            return
        armed_targets.add(key)
        opened_fds.append(fd)
        fd_is_file[fd] = is_file
        kevents.append(
            select.kevent(
                fd,
                filter=select.KQ_FILTER_VNODE,
                flags=ev_flags,
                fflags=file_fflags if is_file else dir_fflags,
            )
        )

    try:
        for path in paths:
            try:
                is_dir = path.is_dir()
                is_file = path.is_file()
            except OSError:
                is_dir = False
                is_file = False

            if is_dir:
                _add_watch(path, is_file=False)
                parent_dir, _ = _nearest_existing_dir(path)
                if parent_dir is not None and parent_dir != path:
                    _add_watch(parent_dir, is_file=False)
            elif is_file:
                _add_watch(path, is_file=True)
                parent_dir, _ = _nearest_existing_dir(path)
                if parent_dir is not None:
                    _add_watch(parent_dir, is_file=False)
            else:
                ancestor, is_direct = _nearest_existing_dir(path)
                if ancestor is not None:
                    _add_watch(ancestor, is_file=False)
                    if not is_direct:
                        has_indirect_ancestor = True
                else:
                    has_indirect_ancestor = True

        if kevents:
            kq.control(kevents, 0, 0)
    except Exception:
        for fd in opened_fds:
            try:
                os.close(fd)
            except OSError:
                pass
        raise

    return opened_fds, fd_is_file, has_indirect_ancestor


def _close_fds(fds: list[int]) -> None:
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass


def _wait_poll(
    paths_fn: Callable[[], Iterable[Path | str]],
    check_fn: Callable[[], Any],
    *,
    start: float,
    deadline: float,
    poll_interval: float,
) -> dict[str, Any]:
    while True:
        watched = [str(p) for p in _normalize_paths(paths_fn())]
        result = check_fn()
        if result is not None:
            return {
                "status": "ready",
                "waited_seconds": round(max(0.0, time.monotonic() - start), 6),
                "result": result,
                "watched_paths": watched,
                "backend": "poll",
            }
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "status": "timeout",
                "waited_seconds": round(max(0.0, time.monotonic() - start), 6),
                "result": None,
                "checked_sources": watched,
                "backend": "poll",
            }
        time.sleep(min(poll_interval, remaining))


def watch_until(
    paths_fn: Callable[[], Iterable[Path | str]],
    check_fn: Callable[[], Any],
    *,
    timeout_sec: float,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    backend: str = "auto",
) -> dict[str, Any]:
    """Block until `check_fn()` returns a non-None value or `timeout_sec` expires.

    Always evaluates `check_fn()` before arming/blocking and again immediately
    after arming `kqueue` watches to eliminate lost-wakeup races.
    """
    clamped_timeout = clamp_timeout(timeout_sec)
    effective_poll = max(0.01, float(poll_interval))
    if backend not in ("auto", "kqueue", "poll"):
        raise ValueError(f"backend must be 'auto', 'kqueue', or 'poll', got {backend!r}")

    start = time.monotonic()
    deadline = start + clamped_timeout
    use_kqueue = (backend == "kqueue") or (backend == "auto" and _kqueue_available())
    if backend == "kqueue" and not _kqueue_available():
        use_kqueue = False
    reported_backend = "kqueue" if use_kqueue else "poll"

    # Fast check-before-block: zero syscall overhead when already ready or timeout == 0.
    initial_paths = _normalize_paths(paths_fn())
    initial_watched = [str(p) for p in initial_paths]
    initial_result = check_fn()
    if initial_result is not None:
        return {
            "status": "ready",
            "waited_seconds": round(max(0.0, time.monotonic() - start), 6),
            "result": initial_result,
            "watched_paths": initial_watched,
            "backend": reported_backend,
        }
    if clamped_timeout <= 0.0:
        return {
            "status": "timeout",
            "waited_seconds": round(max(0.0, time.monotonic() - start), 6),
            "result": None,
            "checked_sources": initial_watched,
            "backend": reported_backend,
        }

    if not use_kqueue:
        return _wait_poll(
            paths_fn,
            check_fn,
            start=start,
            deadline=deadline,
            poll_interval=effective_poll,
        )

    kq = None
    try:
        kq = select.kqueue()
    except OSError:
        return _wait_poll(
            paths_fn,
            check_fn,
            start=start,
            deadline=deadline,
            poll_interval=effective_poll,
        )

    try:
        while True:
            paths = _normalize_paths(paths_fn())
            watched_strs = [str(p) for p in paths]
            fds: list[int] = []
            try:
                fds, _, has_indirect = _arm_kqueue_watches(kq, paths)
                # Re-check AFTER arming kqueue watches so writes occurring
                # between the previous check and fd open are never missed.
                result = check_fn()
                if result is not None:
                    return {
                        "status": "ready",
                        "waited_seconds": round(max(0.0, time.monotonic() - start), 6),
                        "result": result,
                        "watched_paths": watched_strs,
                        "backend": "kqueue",
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {
                        "status": "timeout",
                        "waited_seconds": round(max(0.0, time.monotonic() - start), 6),
                        "result": None,
                        "checked_sources": watched_strs,
                        "backend": "kqueue",
                    }
                if not fds:
                    time.sleep(min(effective_poll, remaining))
                else:
                    slice_cap = effective_poll if has_indirect else _DIRECT_KQUEUE_SLICE_SECONDS
                    wait_slice = min(remaining, slice_cap)
                    kq.control(None, max(1, len(fds)), wait_slice)
            except OSError:
                _close_fds(fds)
                fds = []
                return _wait_poll(
                    paths_fn,
                    check_fn,
                    start=start,
                    deadline=deadline,
                    poll_interval=effective_poll,
                )
            finally:
                _close_fds(fds)
    finally:
        if kq is not None:
            try:
                kq.close()
            except OSError:
                pass

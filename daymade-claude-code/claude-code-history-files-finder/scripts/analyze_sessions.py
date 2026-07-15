#!/usr/bin/env python3
"""
Analyze Claude Code session files to find relevant sessions and statistics.

This script helps locate sessions containing specific keywords, analyze
session activity, and generate reports about session content.

History is searched across EVERY Claude config home, not just ~/.claude:
users who run third-party models through per-model profiles keep parallel
history under ~/.claude-profiles/<name>/ (each profile is its own
CLAUDE_CONFIG_DIR). Searching only ~/.claude silently misses those sessions —
the #1 way a real conversation is wrongly judged "not found".
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict


def discover_claude_homes(explicit=None) -> List[Path]:
    """Discover every Claude config home that holds a ``projects/`` history dir.

    Claude Code stores session history under ``<home>/projects/``. The default
    home is ``~/.claude``, but a user who runs third-party models through
    per-model *profiles* — each profile is its own ``CLAUDE_CONFIG_DIR`` — keeps
    a parallel history under ``~/.claude-profiles/<name>/`` and sometimes a
    sibling ``~/.claude-<name>/``. A tool that only looks at ``~/.claude``
    silently misses every conversation held under a profile, which is the #1
    reason a real session is wrongly reported as "not found".

    Discovery is dynamic (glob), never a hardcoded profile list, so it adapts to
    whatever profiles happen to exist on the machine.

    Args:
        explicit: Optional single path or list of paths. When given, ONLY those
            homes are used (each must contain a ``projects/`` subdir) and
            auto-discovery is skipped — this backs the ``--home`` / ``--main-only``
            flags.

    Returns:
        De-duplicated, existence-checked list of home ``Path`` objects, each
        with a ``projects/`` subdirectory.
    """
    homes: List[Path] = []
    seen = set()

    def add(candidate) -> None:
        try:
            home = Path(candidate).expanduser()
        except Exception:
            return
        if not (home / "projects").is_dir():
            return
        try:
            key = str(home.resolve())
        except Exception:
            key = str(home)
        if key in seen:
            return
        seen.add(key)
        homes.append(home)

    # An explicit override (single path or list) short-circuits discovery.
    if explicit:
        for candidate in (explicit if isinstance(explicit, (list, tuple)) else [explicit]):
            add(candidate)
        return homes

    # CLAUDE_CONFIG_DIR wins first when set, then the default home.
    env_home = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_home:
        add(env_home)
    add(Path.home() / ".claude")

    # Per-model profile homes: ~/.claude-profiles/*/
    profiles_root = Path.home() / ".claude-profiles"
    if profiles_root.is_dir():
        for child in sorted(profiles_root.iterdir()):
            add(child)

    # Sibling homes: ~/.claude-<name>/ that carry their own projects/
    for child in sorted(Path.home().glob(".claude-*")):
        if child.name != ".claude-profiles":
            add(child)

    return homes


def home_label(home) -> str:
    """Short, human-readable provenance label for a home path.

    ``~/.claude`` -> ``main``; ``~/.claude-profiles/kimi`` -> ``kimi``;
    ``~/.claude-deepseek`` -> ``claude-deepseek``. Used so search/list output
    shows which profile a session came from instead of an opaque absolute path.
    A sibling ``~/.claude-<name>`` home keeps its ``claude-`` prefix so it never
    collides with a same-named ``~/.claude-profiles/<name>`` profile.
    """
    home = Path(home)
    if home.name == ".claude":
        return "main"
    if home.parent.name == ".claude-profiles":
        return home.name
    if home.name.startswith(".claude-"):
        return home.name[len("."):]
    return home.name


class SessionAnalyzer:
    """Analyze Claude Code session history files across all config homes."""

    def __init__(self, homes: Optional[List[Path]] = None):
        """
        Initialize analyzer.

        Args:
            homes: List of Claude config home directories to search (each must
                contain a ``projects/`` subdir). Pass ``None`` (the default) to
                auto-discover all homes (``~/.claude`` plus every
                ``~/.claude-profiles/*`` and ``~/.claude-*`` profile home). Pass
                an explicit list to restrict the search — an EMPTY list means
                "search nothing", it must NOT silently fall back to full
                discovery (that would turn a scope-narrowing flag into the
                widest possible scope).
        """
        self.homes = discover_claude_homes() if homes is None else list(homes)

    def find_project_sessions(self, project_path: str) -> List[Dict[str, Any]]:
        """
        Find all session files for a project ACROSS every discovered home.

        Sessions are de-duplicated by session id (the ``.jsonl`` filename), so a
        conversation shared across profiles (profile dirs link back to one
        physical file) is reported once, attributed to every home it appears in.
        Agent side-files (``agent-*.jsonl``) are excluded.

        Args:
            project_path: The project's working directory. An absolute path, a
                ``~`` path, or a relative path are all expanded and resolved to
                an absolute path before encoding. A bare directory name
                (basename) is also accepted and matched via reverse lookup.

        Returns:
            List of dicts ``{"path", "homes", "mtime"}`` sorted by mtime (newest
            first). ``homes`` is the list of home Paths the session was found in
            — its provenance. Empty if the project has no history anywhere.
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        for home, project_dir in self._resolve_project_dirs(project_path):
            for file in project_dir.glob("*.jsonl"):
                if file.name.startswith("agent-"):
                    continue
                try:
                    mtime = file.stat().st_mtime
                except OSError:
                    continue
                sid = file.name
                entry = by_id.get(sid)
                if entry is None:
                    by_id[sid] = {"path": file, "homes": [home], "mtime": mtime}
                else:
                    if home not in entry["homes"]:
                        entry["homes"].append(home)
                    # Keep the copy with the latest mtime (usually the same file).
                    if mtime > entry["mtime"]:
                        entry["path"] = file
                        entry["mtime"] = mtime

        return sorted(by_id.values(), key=lambda e: e["mtime"], reverse=True)

    def _resolve_project_dirs(self, project_path: str) -> List[tuple]:
        """
        Resolve a project path to its encoded dir under EACH home's projects/.

        Claude Code encodes the project's ABSOLUTE working-directory path by
        replacing every ``/`` with ``-`` (e.g. ``/Users/<name>/app`` ->
        ``-Users-<name>-app``). The directory name is NOT the basename, so a
        bare name or an unexpanded ``~`` path never matches directly — the #1
        reason a real history is mistaken for "no sessions". The same project
        has a same-named encoded dir under every home that holds history for it.

        Strategy (the exact-vs-fallback decision is GLOBAL, not per-home):
        1. Try the exact encoded dir in every home. If it matches in ANY home,
           the project identity is known precisely — return those exact matches
           only. A home lacking the exact dir contributes nothing; it is NOT
           fuzzy-matched, so a different project that merely shares the basename
           in another profile home can never be conflated in.
        2. Only if NO home has the exact dir, treat the input as a bare basename
           and reverse-look-up ``-<basename>`` across all homes. Require a SINGLE
           distinct encoded name; if the basename maps to two different projects
           (within OR across homes), that is ambiguous — warn and return nothing
           rather than guess.

        Returns:
            List of ``(home, encoded_dir)`` pairs — one per home where the
            resolved project dir exists.
        """
        # Encode the resolved absolute path once (for exact matching).
        exact_name: Optional[str] = None
        try:
            abs_path = Path(project_path).expanduser().resolve()
            exact_name = str(abs_path).replace("/", "-")
        except (OSError, RuntimeError):
            exact_name = None
        base = Path(project_path).name

        # Pass 1 — exact encoded-dir match across ALL homes. A single exact hit
        # anywhere fixes the project identity, so we never fuzzy-fall-back.
        if exact_name is not None:
            exact_hits = [
                (home, home / "projects" / exact_name)
                for home in self.homes
                if (home / "projects" / exact_name).is_dir()
            ]
            if exact_hits:
                return exact_hits

        # Pass 2 — no exact match anywhere: reverse-look-up the bare basename,
        # but bind only ONE distinct project so same-basename projects living in
        # different homes are never conflated together.
        if not base:
            return []
        by_name: Dict[str, List[tuple]] = {}
        for home in self.homes:
            projects_dir = home / "projects"
            if not projects_dir.is_dir():
                continue
            for d in projects_dir.iterdir():
                if d.is_dir() and d.name.endswith("-" + base):
                    by_name.setdefault(d.name, []).append((home, d))

        if not by_name:
            return []
        if len(by_name) > 1:
            print(
                f"Ambiguous project name '{base}' — {len(by_name)} distinct "
                "projects match across homes; re-run with the full absolute path:",
                file=sys.stderr,
            )
            for name in sorted(by_name):
                homes_str = ", ".join(home_label(h) for h, _ in by_name[name])
                print(f"  {name}  [{homes_str}]", file=sys.stderr)
            return []
        # Exactly one distinct project — use it wherever it exists.
        return next(iter(by_name.values()))

    def search_sessions(
        self,
        session_refs: List[Dict[str, Any]],
        keywords: List[str],
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search sessions for keywords.

        Args:
            session_refs: Session refs from ``find_project_sessions`` (each a
                dict with ``path`` and ``homes``).
            keywords: Keywords to search for.
            case_sensitive: Whether to perform case-sensitive search.

        Returns:
            List of match dicts (session ref + match counts), most mentions
            first.
        """
        matches: List[Dict[str, Any]] = []

        for ref in session_refs:
            session_file = ref["path"]
            keyword_counts = defaultdict(int)
            total_mentions = 0

            try:
                with open(session_file, "r") as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                        except json.JSONDecodeError:
                            continue

                        # Extract text content from message
                        text_content = self._extract_text_content(data)

                        # Search for keywords
                        search_text = (
                            text_content if case_sensitive else text_content.lower()
                        )
                        for keyword in keywords:
                            search_keyword = (
                                keyword if case_sensitive else keyword.lower()
                            )
                            count = search_text.count(search_keyword)
                            if count > 0:
                                keyword_counts[keyword] += count
                                total_mentions += count

            except Exception as e:
                print(
                    f"Warning: Error processing {session_file}: {e}", file=sys.stderr
                )
                continue

            if total_mentions > 0:
                matches.append(
                    {
                        "path": session_file,
                        "homes": ref["homes"],
                        "total_mentions": total_mentions,
                        "keyword_counts": dict(keyword_counts),
                        "modified_time": ref["mtime"],
                        "size": session_file.stat().st_size,
                    }
                )

        matches.sort(key=lambda m: m["total_mentions"], reverse=True)
        return matches

    def get_session_stats(self, session_file: Path) -> Dict[str, Any]:
        """
        Get detailed statistics for a session file.

        Args:
            session_file: Path to session JSONL file

        Returns:
            Dictionary of session statistics
        """
        stats = {
            "total_lines": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_uses": defaultdict(int),
            "write_calls": 0,
            "edit_calls": 0,
            "read_calls": 0,
            "bash_calls": 0,
            "file_operations": [],
        }

        try:
            with open(session_file, "r") as f:
                for line in f:
                    stats["total_lines"] += 1

                    try:
                        data = json.loads(line.strip())

                        # Count message types
                        role = data.get("role") or data.get("message", {}).get("role")
                        if role == "user":
                            stats["user_messages"] += 1
                        elif role == "assistant":
                            stats["assistant_messages"] += 1

                        # Analyze tool uses
                        content = data.get("content") or data.get("message", {}).get(
                            "content", []
                        )
                        for item in content:
                            if not isinstance(item, dict):
                                continue

                            if item.get("type") == "tool_use":
                                tool_name = item.get("name", "unknown")
                                stats["tool_uses"][tool_name] += 1

                                # Track file operations
                                if tool_name == "Write":
                                    stats["write_calls"] += 1
                                    file_path = item.get("input", {}).get(
                                        "file_path", ""
                                    )
                                    if file_path:
                                        stats["file_operations"].append(
                                            ("write", file_path)
                                        )
                                elif tool_name == "Edit":
                                    stats["edit_calls"] += 1
                                    file_path = item.get("input", {}).get(
                                        "file_path", ""
                                    )
                                    if file_path:
                                        stats["file_operations"].append(
                                            ("edit", file_path)
                                        )
                                elif tool_name == "Read":
                                    stats["read_calls"] += 1
                                elif tool_name == "Bash":
                                    stats["bash_calls"] += 1

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"Error analyzing {session_file}: {e}", file=sys.stderr)

        # Convert defaultdict to regular dict
        stats["tool_uses"] = dict(stats["tool_uses"])

        return stats

    def _extract_text_content(self, data: Dict[str, Any]) -> str:
        """Extract all text content from a message."""
        text_parts = []

        # Get content from either location
        content = data.get("content") or data.get("message", {}).get("content", [])

        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    # Also check tool inputs for file paths etc
                    elif item.get("type") == "tool_use":
                        tool_input = item.get("input", {})
                        if isinstance(tool_input, dict):
                            # Add file paths from tool inputs
                            if "file_path" in tool_input:
                                text_parts.append(tool_input["file_path"])
                            # Add content from Write calls
                            if "content" in tool_input:
                                text_parts.append(tool_input["content"])

        return " ".join(text_parts)


def _add_home_flags(subparser) -> None:
    """Attach the shared home-scoping flags to a subparser (list / search)."""
    subparser.add_argument(
        "--home",
        action="append",
        metavar="DIR",
        help="Restrict to a specific Claude home dir (repeatable). Default: "
        "search ~/.claude PLUS every ~/.claude-profiles/* profile home.",
    )
    subparser.add_argument(
        "--main-only",
        action="store_true",
        help="Search only ~/.claude, skipping all profile homes.",
    )


def _homes_for(args) -> tuple:
    """Resolve the home list from CLI flags (used by list / search).

    Returns ``(homes, narrowed)``. ``narrowed`` is True when the user passed
    ``--home`` / ``--main-only``, so the caller can treat an empty result as a
    real "your selection matched no home with history" error instead of
    silently widening back to searching every home.
    """
    if getattr(args, "main_only", False):
        return discover_claude_homes([Path.home() / ".claude"]), True
    explicit = getattr(args, "home", None)
    if explicit:
        return discover_claude_homes(explicit), True
    return discover_claude_homes(), False


def _analyzer_or_exit(args) -> "SessionAnalyzer":
    """Build a SessionAnalyzer, erroring out if a narrowing flag matched no home.

    Without this, an explicit ``--home``/``--main-only`` that resolves to no
    home-with-history would (via an empty list) either search nothing or, worse,
    reintroduce full discovery — turning a scope-narrowing flag into the widest
    possible scope. We fail loudly instead.
    """
    homes, narrowed = _homes_for(args)
    if narrowed and not homes:
        print(
            "No Claude home with a projects/ dir matched your --home/--main-only "
            "selection (a --home value must be a config home such as ~/.claude "
            "or ~/.claude-profiles/<name>, not its projects/ subdir).",
            file=sys.stderr,
        )
        sys.exit(1)
    return SessionAnalyzer(homes)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze Claude Code session history files"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List sessions command
    list_parser = subparsers.add_parser("list", help="List all sessions for a project")
    list_parser.add_argument("project_path", help="Project path")
    list_parser.add_argument(
        "--limit", type=int, default=10, help="Max sessions to show (default: 10)"
    )
    _add_home_flags(list_parser)

    # Search command
    search_parser = subparsers.add_parser("search", help="Search sessions for keywords")
    search_parser.add_argument("project_path", help="Project path")
    search_parser.add_argument(
        "keywords", nargs="+", help="Keywords to search for"
    )
    search_parser.add_argument(
        "--case-sensitive", action="store_true", help="Case-sensitive search"
    )
    _add_home_flags(search_parser)

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Get session statistics")
    stats_parser.add_argument("session_file", type=Path, help="Session file path")
    stats_parser.add_argument(
        "--show-files", action="store_true", help="Show file operations"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        analyzer = _analyzer_or_exit(args)
        home_summary = ", ".join(home_label(h) for h in analyzer.homes)
        sessions = analyzer.find_project_sessions(args.project_path)
        if not sessions:
            print(f"No sessions found for project: {args.project_path}")
            print(
                f"(searched {len(analyzer.homes)} home(s): {home_summary})",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Found {len(sessions)} session(s) for {args.project_path}")
        print(f"Searched {len(analyzer.homes)} home(s): {home_summary}\n")
        print(f"Showing {min(args.limit, len(sessions))} most recent:\n")

        for i, ref in enumerate(sessions[: args.limit], 1):
            session = ref["path"]
            mtime = datetime.fromtimestamp(ref["mtime"])
            size_kb = session.stat().st_size / 1024
            labels = ", ".join(home_label(h) for h in ref["homes"])
            print(f"{i}. {session.name}")
            print(f"   Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Size: {size_kb:.1f} KB")
            print(f"   Profile: {labels}")
            print(f"   Path: {session}")
            print()

    elif args.command == "search":
        analyzer = _analyzer_or_exit(args)
        home_summary = ", ".join(home_label(h) for h in analyzer.homes)
        sessions = analyzer.find_project_sessions(args.project_path)
        if not sessions:
            print(f"No sessions found for project: {args.project_path}")
            print(
                f"(searched {len(analyzer.homes)} home(s): {home_summary})",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"Searching {len(sessions)} session(s) across {len(analyzer.homes)} "
            f"home(s) [{home_summary}] for: {', '.join(args.keywords)}\n"
        )

        matches = analyzer.search_sessions(
            sessions, args.keywords, args.case_sensitive
        )

        if not matches:
            print("No matches found.")
            sys.exit(0)

        print(f"Found {len(matches)} session(s) with matches:\n")

        for info in matches:
            session = info["path"]
            mtime = datetime.fromtimestamp(info["modified_time"])
            labels = ", ".join(home_label(h) for h in info["homes"])
            print(f"📄 {session.name}")
            print(f"   Date: {mtime.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Profile: {labels}")
            print(f"   Total mentions: {info['total_mentions']}")
            print(
                f"   Keywords: {', '.join(f'{k}({v})' for k, v in info['keyword_counts'].items())}"
            )
            print(f"   Path: {session}")
            print()

    elif args.command == "stats":
        if not args.session_file.exists():
            print(f"Error: Session file not found: {args.session_file}")
            sys.exit(1)

        print(f"Analyzing session: {args.session_file}\n")

        analyzer = SessionAnalyzer()
        stats = analyzer.get_session_stats(args.session_file)

        print("=" * 60)
        print("Session Statistics")
        print("=" * 60)
        print(f"\nMessages:")
        print(f"  Total lines: {stats['total_lines']:,}")
        print(f"  User messages: {stats['user_messages']}")
        print(f"  Assistant messages: {stats['assistant_messages']}")

        print(f"\nTool Usage:")
        print(f"  Write calls: {stats['write_calls']}")
        print(f"  Edit calls: {stats['edit_calls']}")
        print(f"  Read calls: {stats['read_calls']}")
        print(f"  Bash calls: {stats['bash_calls']}")

        if stats["tool_uses"]:
            print(f"\n  All tools:")
            for tool, count in sorted(
                stats["tool_uses"].items(), key=lambda x: x[1], reverse=True
            ):
                print(f"    {tool}: {count}")

        if args.show_files and stats["file_operations"]:
            print(f"\nFile Operations ({len(stats['file_operations'])}):")
            # Group by file
            files = defaultdict(list)
            for op, path in stats["file_operations"]:
                files[path].append(op)

            # Limit to 20 files to prevent terminal flooding on large sessions
            for file_path, ops in list(files.items())[:20]:
                filename = Path(file_path).name
                op_summary = ", ".join(
                    f"{op}({ops.count(op)})" for op in set(ops)
                )
                print(f"  {filename}")
                print(f"    Operations: {op_summary}")
                print(f"    Path: {file_path}")

        print()


if __name__ == "__main__":
    main()

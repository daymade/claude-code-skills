"""Ghostty window/tab structure capture via the Ghostty scripting dictionary.

Captures the app's window -> tab -> terminal-surface tree with each surface's
TTY device, PID, working directory and auto/override titles, then joins tab
TTYs to snapshot sessions by TTY basename. Read-only and best-effort: any
failure returns {"captured": False, "reason": ...} so the snapshot path
never breaks on hosts without Ghostty AppleScript support.
"""

import os
import subprocess

OSASCRIPT = "osascript"

_WINDOW_STRUCTURE_APPLESCRIPT = """
on run
  set tabCh to (ASCII character 9)
  set nl to linefeed
  set out to ""
  tell application "Ghostty"
    repeat with w in windows
      set out to out & "WINDOW" & tabCh & (id of w) & tabCh & (name of w) & nl
      repeat with t in tabs of w
        set selF to "false"
        try
          if selected of t then set selF to "true"
        end try
        set ovr to ""
        try
          set ovr to (name override of t)
        end try
        set out to out & "TAB" & tabCh & (id of w) & tabCh & (id of t) & tabCh & (index of t) & tabCh & selF & tabCh & ovr & tabCh & (name of t) & nl
        repeat with tm in terminals of t
          set tovr to ""
          try
            set tovr to (name override of tm)
          end try
          set tcwd to ""
          try
            set tcwd to (working directory of tm)
          end try
          set tp to ""
          try
            set tp to ((pid of tm) as text)
          end try
          set tt to ""
          try
            set tt to (tty of tm)
          end try
          set out to out & "TERM" & tabCh & (id of t) & tabCh & (id of tm) & tabCh & tt & tabCh & tp & tabCh & tcwd & tabCh & tovr & tabCh & (name of tm) & nl
        end repeat
      end repeat
    end repeat
  end tell
  return out
end run
"""

def _to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def parse_window_structure(text):
    """Parse WINDOW/TAB/TERM tab-separated lines into the manifest windows block."""
    windows, tabs, terms = [], {}, {}
    for line in text.splitlines():
        parts = line.split("\t")
        kind = parts[0] if parts else ""
        if kind == "WINDOW" and len(parts) >= 3:
            windows.append({"id": parts[1], "name": parts[2]})
        elif kind == "TAB" and len(parts) >= 7:
            tabs[parts[2]] = {"window": parts[1], "tab_id": parts[2],
                              "index": _to_int(parts[3], 0),
                              "selected": parts[4] == "true",
                              "title_override": parts[5], "title": parts[6]}
        elif kind == "TERM" and len(parts) >= 8:
            terms.setdefault(parts[1], []).append(
                {"terminal_id": parts[2], "tty": parts[3], "pid": parts[4],
                 "cwd": parts[5], "title_override": parts[6], "title": parts[7]})
    by_window = {}
    for tid in sorted(tabs, key=lambda k: tabs[k]["index"]):
        by_window.setdefault(tabs[tid]["window"], []).append(dict(tabs[tid], terminals=terms.get(tid, [])))
    return {"windows": [dict(w, tabs=by_window.get(w["id"], [])) for w in windows],
            "coverage": {"tabs": len(tabs), "terminals": sum(len(v) for v in terms.values())}}

def capture_window_structure():
    """Run the capture AppleScript; degrade to captured=False on any failure."""
    try:
        result = subprocess.run([OSASCRIPT, "-e", _WINDOW_STRUCTURE_APPLESCRIPT],
                                capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"captured": False, "reason": f"osascript failed: {error}"}
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        reason = lines[-1][:200] if lines else "no output"
        return {"captured": False, "reason": f"osascript rc={result.returncode}: {reason}"}
    try:
        block = parse_window_structure(result.stdout)
    except Exception as error:  # defensive: capture must never break snapshot
        return {"captured": False, "reason": f"parse failed: {error}"}
    block["captured"] = True
    block["capture_channel"] = "ghostty-applescript-dictionary"
    return block

def join_windows_to_sessions(windows, sessions):
    """Attach session anchors to captured terminals by TTY basename.

    unmapped_tab_ttys: tab TTYs with no snapshot session (plain shells).
    sessions_without_tab: snapshot sessions with no tab (headless or closed).
    """
    tty_to_session = {}
    for entry in sessions:
        tty = os.path.basename(str(entry.get("tty") or ""))
        if tty:
            tty_to_session[tty] = entry
    matched, unmapped = 0, []
    tab_ttys = set()
    for window in windows["windows"]:
        for tab in window["tabs"]:
            for term in tab["terminals"]:
                tty = os.path.basename(term.get("tty") or "")
                tab_ttys.add(tty)
                entry = tty_to_session.get(tty)
                term["session"] = ({"sid": entry.get("sid"), "tool": entry.get("tool"),
                                    "profile": entry.get("profile"), "status": entry.get("status")}
                                   if entry else None)
                if entry:
                    matched += 1
                else:
                    unmapped.append(term.get("tty") or "(no-tty terminal)")
    windows["coverage"].update({
        "sessions_matched": matched,
        "unmapped_tab_ttys": unmapped,
        "sessions_without_tab": sorted(tty for tty in set(tty_to_session) - tab_ttys),
    })
    return windows

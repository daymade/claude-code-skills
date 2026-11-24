"""Ghostty window/tab structure and native actions via the scripting dictionary.

Captures the app's window -> tab -> terminal-surface tree with each surface's
TTY device, PID, working directory and auto/override titles, then joins tab
TTYs to snapshot sessions by TTY basename. Read-only and best-effort: any
failure returns {"captured": False, "reason": ...} so the snapshot path
never breaks on hosts without Ghostty AppleScript support.
"""

import math
import os
import subprocess

OSASCRIPT = "osascript"

_WINDOW_STRUCTURE_APPLESCRIPT = """
on run
  set tabCh to character id 9
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

_TERMINAL_COMMAND_APPLESCRIPT = """
on run argv
  set targetID to item 1 of argv
  set expectedTTY to item 6 of argv
  set expectedPID to item 7 of argv
  set submitPresses to (item 3 of argv) as integer
  set preDelay to ((item 4 of argv) as integer) / 1000
  set postDelay to ((item 5 of argv) as integer) / 1000
  set separator to character id 30
  if application "Ghostty" is not running then error "Ghostty is not running"
  tell application "Ghostty"
    set matchingTerminals to every terminal whose id is targetID
    if (count of matchingTerminals) is not 1 then error "Terminal ID is missing or ambiguous"
    set t to item 1 of matchingTerminals
    set beforeTitle to name of t
    set beforeTTY to tty of t
    set beforePID to (pid of t) as text
    if (expectedTTY is not "" and beforeTTY is not expectedTTY) or ¬
      (expectedPID is not "" and beforePID is not expectedPID) then error "Terminal binding changed"
    input text (item 2 of argv) to t
    delay preDelay
    repeat submitPresses times
      if (tty of t) is not beforeTTY or ((pid of t) as text) is not beforePID then error "Terminal binding changed during submission"
      send key "enter" to t
      delay postDelay
    end repeat
    set afterTitle to ""
    set afterTTY to ""
    set afterPID to ""
    try
      set afterTitle to name of t
      set afterTTY to tty of t
      set afterPID to (pid of t) as text
    end try
  end tell
  return targetID & separator & beforeTTY & separator & beforePID & separator & beforeTitle & separator & afterTTY & separator & afterPID & separator & afterTitle
end run
"""


def send_terminal_command(terminal_id, text, *, submit_presses=2, pre_submit_delay=0.25,
                          post_submit_delay=0.35, timeout=15, expected_tty=None,
                          expected_pid=None):
    """Send one line to an exact native surface and return its input receipt."""
    for name, value in (("terminal_id", terminal_id), ("text", text)):
        if not value.strip() or any(char in value for char in "\x00\r\n"):
            raise ValueError(f"{name} must be a nonempty single line")
    if type(submit_presses) is not int or submit_presses < 1:
        raise ValueError("submit_presses must be a positive integer")
    if not all(math.isfinite(delay) and delay >= 0 for delay in (pre_submit_delay, post_submit_delay)):
        raise ValueError("submit delays must be nonnegative and finite")
    argv = [OSASCRIPT, "-e", _TERMINAL_COMMAND_APPLESCRIPT, "--", terminal_id, text,
            str(submit_presses), str(round(pre_submit_delay * 1000)), str(round(post_submit_delay * 1000)),
            expected_tty or "", str(expected_pid) if expected_pid is not None else ""]
    receipt = {"terminal_id": terminal_id, "returncode": None, "reason": None,
               "before": None, "after": None}
    try:
        completed = subprocess.run(argv, capture_output=True, encoding="utf-8",
                                   errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        receipt["reason"] = "osascript timed out; input may have been partially delivered"
        return receipt
    except OSError as error:
        receipt["reason"] = f"osascript failed: {error}"
        return receipt
    receipt["returncode"] = completed.returncode
    if completed.returncode:
        receipt["reason"] = _applescript_error(completed, "native terminal input failed")
        return receipt

    fields = completed.stdout.removesuffix("\n").split("\x1e")
    if len(fields) != 7 or fields[0] != terminal_id:
        receipt["reason"] = "native input returned no usable surface metadata"
        return receipt
    _, before_tty, before_pid, before_title, after_tty, after_pid, after_title = fields
    receipt["before"] = {"tty": before_tty, "pid": _to_int(before_pid), "title": before_title}
    if after_tty:
        receipt["after"] = {"tty": after_tty, "pid": _to_int(after_pid), "title": after_title}
    return receipt


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

def capture_window_structure(timeout=15, *, running_only=False):
    """Run the capture AppleScript; degrade to captured=False on any failure.

    ``timeout`` bounds the osascript call; supervised callers pass their
    remaining observation budget so a slow capture degrades instead of
    exceeding the supervisor kill window.
    """
    script = _WINDOW_STRUCTURE_APPLESCRIPT
    if running_only:
        script = script.replace("on run\n", 'on run\n  if application "Ghostty" is not running then error "Ghostty is not running"\n', 1)
    try:
        result = subprocess.run([OSASCRIPT, "-e", script],
                                capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as error:
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

    Mutates ``windows`` in place and is not idempotent (repeat calls grow
    ``unmapped_tab_ttys``); call once per parsed capture.

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


def canonical_layout(windows):
    """Return the change-only layout projection, or None when capture is unknown.

    Window/tab IDs, TTYs, PIDs, automatic titles and selection are deliberately
    excluded. Only mapped session order, native indexes and tab-level custom
    titles affect the automatic-backup change predicate.
    """
    if not isinstance(windows, dict) or not windows.get("captured"):
        return None
    rows = []
    try:
        for window_index, window in enumerate(windows["windows"], 1):
            for tab in window["tabs"]:
                sids = [(term.get("session") or {}).get("sid") for term in tab["terminals"]]
                sids = [sid for sid in sids if isinstance(sid, str) and sid]
                if not sids:
                    continue
                title = tab.get("title_override") or ""
                if not isinstance(title, str):
                    raise ValueError("tab title override must be text")
                rows.append({"window": window_index, "tab": int(tab["index"]),
                             "sessions": sids, "title_override": title})
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid captured window layout") from error
    return rows


def recorded_single_window_layout(windows):
    """Return restorable order/titles for one tab per session, else None."""
    if not isinstance(windows, dict) or not windows.get("captured"):
        return None
    try:
        if len(windows["windows"]) != 1:
            return None
        order, titles = [], {}
        for tab in sorted(windows["windows"][0]["tabs"], key=lambda row: row["index"]):
            terminals = tab["terminals"]
            sids = [(term.get("session") or {}).get("sid") for term in terminals]
            sids = [sid for sid in sids if isinstance(sid, str) and sid]
            if not sids:
                continue
            if len(terminals) != 1 or len(sids) != 1 or sids[0] in order:
                return None
            sid = sids[0]
            order.append(sid)
            title = tab.get("title_override") or ""
            if not isinstance(title, str):
                return None
            if title:
                titles[sid] = title
        return {"order": order, "titles": titles}
    except (KeyError, TypeError, AttributeError):
        return None


def _applescript_quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'


def _applescript_error(result, fallback):
    lines = (result.stderr or result.stdout or "").strip().splitlines()
    return lines[-1][:300] if lines else fallback


def apply_tab_title_overrides(windows, titles, timeout=15):
    """Write custom titles to current tabs selected by joined SID, never by index."""
    assignments, seen, ambiguous = [], set(), set()
    for window in windows.get("windows", []):
        for tab in window.get("tabs", []):
            sids = [(term.get("session") or {}).get("sid") for term in tab.get("terminals", [])]
            sids = [sid for sid in sids if sid in titles]
            if len(sids) > 1 or (sids and sids[0] in seen):
                ambiguous.update(sids)
                continue
            if sids:
                seen.add(sids[0])
                assignments.append((tab["tab_id"], sids[0], titles[sids[0]]))
    result = {"applied": 0, "missing": sorted(set(titles) - seen - ambiguous),
              "ambiguous": sorted(ambiguous), "error": None}
    if ambiguous:
        result["error"] = "ambiguous current tab/session mapping"
        return result
    if not assignments:
        return result
    lines = ['tell application "Ghostty"', "  repeat with w in windows",
             "    repeat with t in tabs of w", "      set tid to id of t"]
    for tab_id, _, title in assignments:
        lines.append(f"      if tid is {_applescript_quote(tab_id)} then set name override of t to {_applescript_quote(title)}")
    lines += ["    end repeat", "  end repeat", "end tell"]
    try:
        completed = subprocess.run([OSASCRIPT, "-e", "\n".join(lines)],
                                   capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as error:
        result["error"] = f"osascript failed: {error}"
        return result
    if completed.returncode:
        result["error"] = _applescript_error(completed, "title override failed")
        return result
    result["applied"] = len(assignments)
    return result


def apply_recorded_tab_order(windows, order, timeout=15):
    """Move selected existing tabs into recorded order without moving other tabs."""
    result = {"applied": 0, "missing": [], "error": None}
    try:
        if len(windows.get("windows", [])) != 1:
            result["error"] = "current order restore requires one window"
            return result
        tabs = sorted(windows["windows"][0]["tabs"], key=lambda row: row["index"])
        if len(set(order)) != len(order):
            result["error"] = "recorded order contains duplicate session IDs"
            return result
        selected = set(order)
        by_sid, sid_rows = {}, []
        for tab in tabs:
            sids = [(term.get("session") or {}).get("sid") for term in tab.get("terminals", [])]
            sids = [sid for sid in sids if isinstance(sid, str) and sid]
            if len(sids) > 1:
                result["error"] = "ambiguous current tab/session mapping"
                return result
            sid = sids[0] if sids else None
            sid_rows.append(sid)
            if sid in selected:
                if sid in by_sid:
                    result["error"] = "duplicate current tab/session mapping"
                    return result
                by_sid[sid] = tab
        missing = sorted(selected - set(by_sid))
        if missing:
            result["missing"] = missing
            result["error"] = "current order targets are missing"
            return result
        slots = [index for index, sid in enumerate(sid_rows) if sid in selected]
        if len(slots) != len(order):
            result["error"] = "current order mapping is not unambiguous"
            return result
        desired = list(tabs)
        for slot, sid in zip(slots, order):
            desired[slot] = by_sid[sid]
        current, operations = list(tabs), []
        for index, target in enumerate(desired):
            if current[index]["tab_id"] == target["tab_id"]:
                continue
            source = next((j for j in range(index + 1, len(current))
                           if current[j]["tab_id"] == target["tab_id"]), None)
            if source is None:
                result["error"] = "could not plan native tab movement"
                return result
            operations.append((target["tab_id"], index - source))
            current.insert(index, current.pop(source))
    except (KeyError, TypeError, AttributeError) as error:
        result["error"] = f"invalid current window layout: {error}"
        return result
    if not operations:
        return result
    lines = ['tell application "Ghostty"']
    for tab_id, delta in operations:
        lines += ["  repeat with w in windows", "    repeat with t in tabs of w",
                  f"      if id of t is {_applescript_quote(tab_id)} then",
                  f"        set action_result to perform action {_applescript_quote('move_tab:' + str(delta))} on (focused terminal of t)",
                  '        if action_result is false then error "move_tab rejected"',
                  "      end if", "    end repeat", "  end repeat"]
    lines.append("end tell")
    try:
        completed = subprocess.run([OSASCRIPT, "-e", "\n".join(lines)],
                                   capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as error:
        result["error"] = f"osascript failed: {error}"
        return result
    if completed.returncode:
        result["error"] = _applescript_error(completed, "native tab movement failed")
        return result
    result["applied"] = len(operations)
    return result


def select_tab(tab_id, timeout=15):
    """Select an existing native tab ID without synthesizing keyboard input."""
    script = ("tell application \"Ghostty\"\n"
              "  repeat with w in windows\n"
              "    repeat with t in tabs of w\n"
              f"      if id of t is {_applescript_quote(tab_id)} then\n"
              "        select tab t\n"
              "        return true\n"
              "      end if\n"
              "    end repeat\n"
              "  end repeat\n"
              "end tell\n"
              "return false")
    try:
        completed = subprocess.run([OSASCRIPT, "-e", script], capture_output=True,
                                   text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as error:
        return {"selected": False, "reason": f"osascript failed: {error}"}
    if completed.returncode:
        return {"selected": False, "reason": _applescript_error(completed, "select tab failed")}
    return {"selected": completed.stdout.strip().lower() == "true",
            "reason": None if completed.stdout.strip().lower() == "true" else "tab id not found"}

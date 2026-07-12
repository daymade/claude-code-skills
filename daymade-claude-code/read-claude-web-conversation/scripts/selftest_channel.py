#!/usr/bin/env python3
"""Regression suite for automation-Chrome detection. Run after any change to cdp_channel.py.

    uv run --with websockets python scripts/selftest_channel.py

This detector decides whether AppleScript can be trusted, and it has now been wrong
in BOTH directions:

  * Missing a real harness  -> the agent thinks AppleScript is safe, Apple Events land
    on the automation Chrome, and the user gets told to enable a menu toggle they have
    had on for years.
  * Flagging the real browser -> the agent avoids AppleScript for no reason, and
    slanders the user's daily browser while doing it.

Both failures flip the routing decision; neither announces itself. Hence fixtures.
The path cases are not hypothetical — Chrome for Testing (what puppeteer and
chrome-devtools-mcp actually run) and macOS's own temp root both contain spaces or
live outside the obvious markers, which is precisely how the first version managed to
miss every real instance while looking correct.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cdp_channel', HERE / 'cdp_channel.py')
cdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp)

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
CFT = ('/Applications/Google Chrome for Testing.app/Contents/MacOS/'
       'Google Chrome for Testing')

# (is_automation, command line, what it is)
CASES = [
    (True,  f'{CFT} --user-data-dir=/Users/u/Library/Caches/Google/Chrome for Testing/'
            f'chrome-profile --enable-automation',
     'Chrome for Testing — spaces in the path; what puppeteer/devtools-mcp actually run'),
    (True,  f'{CHROME} --user-data-dir=/private/var/folders/q9/xx/T/.org.chromium.Chromium.AbC',
     "macOS temp profile — /var/folders is where throwaway profiles really live"),
    (True,  f'{CHROME} --user-data-dir=/Users/u/Library/Application Support/puppeteer/profile',
     'puppeteer — "Application Support" has a space in it'),
    (True,  f'{CHROME} --user-data-dir=/Users/u/.cache/chrome-devtools-mcp/chrome-profile',
     'chrome-devtools-mcp'),
    (True,  f'{CHROME} --headless=new --user-data-dir=/Users/u/whatever',
     'headless — nobody browses like this'),
    (False, f'{CHROME} --disk-cache-dir=/Users/u/.cache/chrome-disk',
     "normal browser whose DISK CACHE happens to sit in .cache/ (was flagged)"),
    (False, f'{CHROME} --crash-dumps-dir=/tmp/chrome-crashes',
     'normal browser whose crash dumps happen to sit in /tmp/ (was flagged)'),
    (False, CHROME,
     'the plain, default, signed-in browser this skill exists to read'),
]


def main():
    failed = 0
    for expect, cmd, what in CASES:
        got = cdp._is_automation(cmd)
        if got != expect:
            failed += 1
            print(f'  FAIL  called it {"AUTOMATION" if got else "REAL"}, expected '
                  f'{"AUTOMATION" if expect else "REAL"}\n        {what}')
        else:
            print(f'  ok    {"AUTOMATION" if got else "REAL      "}  {what}')

    # The extractor must survive spaces; whitespace-splitting the command line is what
    # silently truncated every real profile path.
    udd = cdp._user_data_dir(f'{CHROME} --user-data-dir=/a b/c d --enable-automation')
    if udd != '/a b/c d':
        failed += 1
        print(f'  FAIL  --user-data-dir with spaces parsed as {udd!r}, expected "/a b/c d"')
    else:
        print('  ok    --user-data-dir survives spaces in the path')

    print()
    if failed:
        print(f'{failed} failed — the AppleScript routing decision cannot be trusted.')
        return 1
    print(f'all {len(CASES) + 1} passed — detector catches real harnesses and leaves the '
          f'user\'s browser alone.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

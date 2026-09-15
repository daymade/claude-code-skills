#!/usr/bin/env python3
"""Copy .google.com-family cookies from the daily Chrome profile into one
of the isolated tibo-codex-{a,b} profiles created by launch-usage-profile.sh.

Why this is safe to do as a raw SQLite copy (verified 2026-09-15, this machine):
  - macOS Chrome's cookie-encryption key lives ONLY in the Keychain item
    "Chrome Safe Storage" (svce="Chrome Safe Storage", acct="Chrome") —
    `Local State`'s own `os_crypt` section is empty on macOS, confirmed by
    reading it directly on this machine.
  - That Keychain item's identity is scoped to the app (acct="Chrome"), not
    to any --user-data-dir. Every profile launched by the same
    /Applications/Google Chrome.app binary decrypts with the SAME key.
  - So `encrypted_value` BLOBs can be copied verbatim between profiles of
    the same Chrome.app install with no decrypt/re-encrypt step — this
    script never touches Keychain and never sees a plaintext cookie value.

Run this yourself (not via an agent's shell) so the OS-level consent for
reading Chrome's live profile stays entirely on your side:

    python3 scripts/import-google-cookies.py --profile a
    python3 scripts/import-google-cookies.py --profile b

Only .google.com and its subdomains are copied — enough for Google SSO
into a third-party site, nothing from the other ~1160 unrelated domains
in your daily profile.
"""
import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_COOKIES = (
    Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
)
DEST_ROOT = Path.home() / ".chrome-profiles"
GOOGLE_DOMAIN_WHERE = "(host_key = 'google.com' OR host_key LIKE '%.google.com')"


def dest_cookies_path(profile: str) -> Path:
    return DEST_ROOT / f"tibo-codex-{profile}" / "Default" / "Cookies"


def chrome_running_on(user_data_dir: Path) -> bool:
    out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True)
    needle = f"--user-data-dir={user_data_dir}"
    return any(needle in line for line in out.stdout.splitlines())


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", choices=["a", "b"], required=True)
    ap.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )
    args = ap.parse_args()

    dest_path = dest_cookies_path(args.profile)
    dest_user_data_dir = DEST_ROOT / f"tibo-codex-{args.profile}"

    if not SOURCE_COOKIES.exists():
        print(f"source not found: {SOURCE_COOKIES}", file=sys.stderr)
        return 1
    if not dest_path.exists():
        print(
            f"destination not found: {dest_path}\n"
            "run launch-usage-profile.sh once for this profile first "
            "so Chrome can create its own Default/Cookies schema.",
            file=sys.stderr,
        )
        return 1
    if chrome_running_on(dest_user_data_dir):
        print(
            f"Chrome is currently running on {dest_user_data_dir} — quit that "
            "window first, otherwise Chrome may overwrite this write when it "
            "next flushes its own state.",
            file=sys.stderr,
        )
        return 1

    # Read the LIVE source through a snapshot copy, never the live file
    # directly — Chrome keeps it open and a live read can race a write.
    with tempfile.TemporaryDirectory() as tmp:
        src_snapshot = Path(tmp) / "Cookies.src"
        shutil.copy2(SOURCE_COOKIES, src_snapshot)

        src = sqlite3.connect(f"file:{src_snapshot}?mode=ro", uri=True)
        dst = sqlite3.connect(dest_path)

        src_cols = table_columns(src, "cookies")
        dst_cols = table_columns(dst, "cookies")
        cols = [c for c in dst_cols if c in src_cols]  # intersection, dest order
        if not cols:
            print("no common 'cookies' columns between source and destination — "
                  "Chrome schema mismatch, aborting.", file=sys.stderr)
            return 1

        col_list = ", ".join(cols)
        rows = src.execute(
            f"SELECT {col_list} FROM cookies WHERE {GOOGLE_DOMAIN_WHERE}"
        ).fetchall()
        domains = sorted(
            {r[cols.index("host_key")] for r in rows} if "host_key" in cols else set()
        )

        print(f"source:      {SOURCE_COOKIES}")
        print(f"destination: {dest_path}")
        print(f"columns copied: {len(cols)} (intersection of source/dest schema)")
        print(f"cookies found: {len(rows)} across {len(domains)} google.com domains:")
        for d in domains:
            print(f"  - {d}")

        if not rows:
            print("nothing to copy.")
            return 0

        if not args.yes:
            ans = input(f"\nWrite {len(rows)} cookies into profile {args.profile}? [y/N] ")
            if ans.strip().lower() != "y":
                print("aborted, nothing written.")
                return 1

        placeholders = ", ".join("?" for _ in cols)
        dst.executemany(
            f"INSERT OR REPLACE INTO cookies ({col_list}) VALUES ({placeholders})",
            rows,
        )
        dst.commit()
        print(f"done: wrote {len(rows)} cookies into profile {args.profile}.")
        print("Launch it with ./scripts/launch-usage-profile.sh "
              f"{args.profile} and check chatgpt.com's Google sign-in.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

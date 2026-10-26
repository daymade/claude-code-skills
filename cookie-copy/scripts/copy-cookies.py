#!/usr/bin/env python3
"""Copy selected-site cookies between local profiles of the SAME macOS Chrome.

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

Read the source and write the destination only within the user's authorization:

    python3 scripts/copy-cookies.py --site chatgpt --destination /path/to/isolated-profile

The default remains Google-only. --site chatgpt transfers every session-token
chunk. Verify the expected account after reopening the destination. Cookie copy
alone does not establish login. Cross-browser/cross-machine conversion is unsupported.
"""
import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_COOKIES = (
    Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
)
SITE_DOMAINS = {"google": ("google.com",), "chatgpt": ("chatgpt.com", "openai.com")}


def chrome_running_on(user_data_dir: Path) -> bool:
    out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True)
    needle = f"--user-data-dir={user_data_dir}"
    if out.returncode:
        raise RuntimeError("cannot inspect running browsers")
    return any("Google Chrome" in line and needle in line for line in out.stdout.splitlines())


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def locate_cookies(profile_root: Path) -> Path:
    candidates = [profile_root / "Default/Cookies", profile_root / "Default/Network/Cookies"]
    found = [path for path in candidates if path.is_file()]
    if len(found) != 1:
        raise ValueError("destination must contain exactly one initialized Default cookie database")
    return found[0]


def save_backup(conn: sqlite3.Connection, destination: Path) -> str:
    fd, name = tempfile.mkstemp(prefix="Cookies.before-migration-", suffix=".sqlite", dir=destination.parent)
    os.close(fd)
    saved = sqlite3.connect(name)
    try:
        conn.backup(saved)
    finally:
        saved.close()
    return name


def restore(destination: Path, backup: Path) -> dict:
    destination, backup = destination.resolve(strict=True), backup.resolve(strict=True)
    if (backup.parent != destination.parent or not backup.name.startswith("Cookies.before-migration-")
            or backup.samefile(destination)):
        raise ValueError("restore requires a migration backup beside the exact destination database")
    saved = sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(destination.as_uri() + "?mode=rw", uri=True)
    try:
        if not table_columns(saved, "cookies") or table_columns(saved, "cookies") != table_columns(dst, "cookies"):
            raise ValueError("backup and destination schemas differ")
        retained = save_backup(dst, destination)
        saved.backup(dst)
        return {"restored": True, "backup": retained, "login_verified": False}
    finally:
        saved.close()
        dst.close()


def transfer(source: Path, destination: Path, *, site: str, approve) -> dict:
    """Read one SQLite snapshot, back up the target, then commit one transaction.

    Never modify the source, log cookie values, or silently drop schema fields.
    The caller owns the stopped-destination-browser preflight.
    """
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=True)
    if source.samefile(destination):
        raise ValueError("source and destination must be different databases")
    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(destination.as_uri() + "?mode=rw", uri=True)
    try:
        src.execute("BEGIN")
        columns = table_columns(src, "cookies")
        if not columns or columns != table_columns(dst, "cookies"):
            raise ValueError("cookie schemas differ; no fields may be silently discarded")
        for required in ("host_key", "name", "encrypted_value", "expires_utc"):
            if required not in columns:
                raise ValueError(f"cookie schema lacks {required}")
        domains = SITE_DOMAINS[site]
        where = " OR ".join("(host_key = ? OR host_key LIKE ?)" for _ in domains)
        parameters = [value for domain in domains for value in (domain, "%." + domain)]
        col_list = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
        rows = src.execute(f"SELECT {col_list} FROM cookies WHERE {where}", parameters).fetchall()
        # The selected snapshot is now in memory. Do not keep a source read lock
        # while a person decides whether to approve the destination write.
        src.rollback()
        names = {row[columns.index("name")] for row in rows}
        if site == "chatgpt" and not any(
            name == "__Secure-next-auth.session-token" or name.startswith("__Secure-next-auth.session-token.")
            for name in names
        ):
            raise ValueError("source has no ChatGPT session cookie; nothing written")
        summary = {"site": site, "rows": len(rows), "domains": sorted(
            {row[columns.index("host_key")] for row in rows}
        ), "login_verified": False}
        if not rows:
            return summary
        if not approve(summary):
            raise ValueError("aborted; nothing written")

        backup_name = save_backup(dst, destination)
        try:
            dst.execute("BEGIN IMMEDIATE")
            # Replace the selected site's old snapshot as a set: stale session
            # token chunks from an earlier login must not survive a shorter token.
            if site == "chatgpt":
                dst.execute("DELETE FROM cookies WHERE " + where, parameters)
            dst.executemany(
                f"INSERT OR REPLACE INTO cookies ({col_list}) VALUES ({','.join('?' for _ in columns)})", rows
            )
            dst.commit()
        except BaseException:
            dst.rollback()
            raise
        summary["backup"] = backup_name
        return summary
    finally:
        src.close()
        dst.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--destination", type=Path, required=True, help="initialized isolated Chrome user-data-dir")
    ap.add_argument("--source-cookie-db", type=Path, default=SOURCE_COOKIES)
    ap.add_argument("--site", choices=SITE_DOMAINS, default="google")
    ap.add_argument("--restore-backup", type=Path, help="restore a backup for this stopped destination")
    ap.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )
    args = ap.parse_args()

    dest_user_data_dir = args.destination.expanduser().resolve()

    if not args.restore_backup and not args.source_cookie_db.expanduser().is_file():
        print(f"source not found: {args.source_cookie_db}", file=sys.stderr)
        return 1
    try:
        dest_path = locate_cookies(dest_user_data_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if chrome_running_on(dest_user_data_dir) or os.path.lexists(dest_user_data_dir / "SingletonLock"):
        print(
            f"Chrome is currently running on {dest_user_data_dir} — quit that "
            "window first, otherwise Chrome may overwrite this write when it "
            "next flushes its own state.",
            file=sys.stderr,
        )
        return 1

    def approve(summary):
        print(f"source: {args.source_cookie_db}; destination: {dest_path}")
        print(f"selected {summary['rows']} {args.site} cookies across {len(summary['domains'])} domains")
        return args.yes or input("Replace these site cookies in the stopped destination? [y/N] ").strip().lower() == "y"
    try:
        if args.restore_backup:
            if not args.yes and input("Restore this destination's migration backup? [y/N] ").strip().lower() != "y":
                raise ValueError("aborted; nothing written")
            summary = restore(dest_path, args.restore_backup.expanduser())
        else:
            summary = transfer(args.source_cookie_db.expanduser(), dest_path, site=args.site, approve=approve)
    except (ValueError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    print("destination restored; login not yet verified" if summary.get("restored") else
          f"transfer complete: {summary['rows']} cookies; login not yet verified")
    if summary.get("backup"):
        print(f"destination backup: {summary['backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

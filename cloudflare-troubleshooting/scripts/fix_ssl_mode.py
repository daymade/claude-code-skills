#!/usr/bin/env python3
"""
Preview or change Cloudflare SSL/TLS mode to resolve redirect loops.

The script is dry-run by default. It fetches the zone and current SSL mode,
prints the current -> target transition, and exits without changing live
settings unless --apply is provided.

Common scenarios:
- GitHub Pages + Flexible mode -> Change to Full
- Netlify/Vercel + Flexible mode -> Change to Full
- Any HTTPS-enforcing origin + Flexible mode -> Change to Full

Requires:
- requests library
- Cloudflare API credentials
"""

import sys
from typing import Optional


VALID_MODES = ["flexible", "full", "strict", "off"]


def cloudflare_headers(email: str, api_key: str) -> dict:
    """Return Cloudflare API headers."""
    return {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json",
    }


def get_requests():
    """Import requests with a user-friendly error."""
    try:
        import requests
    except ImportError:
        print("Error: 'requests' library not installed")
        print("Install with: pip install requests")
        return None
    return requests


def find_zone_id(domain: str, email: str, api_key: str) -> Optional[str]:
    """Return the Cloudflare zone ID for a domain."""
    requests = get_requests()
    if requests is None:
        return None

    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones?name={domain}",
            headers=cloudflare_headers(email, api_key),
            timeout=30,
        )

        if not response.ok:
            print(f"API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return None

        data = response.json()
        if not data.get("success") or not data.get("result"):
            print(f"Domain '{domain}' not found in your Cloudflare account")
            return None

        return data["result"][0]["id"]

    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        return None


def get_ssl_mode(zone_id: str, email: str, api_key: str) -> Optional[str]:
    """Return the current SSL mode for a zone."""
    requests = get_requests()
    if requests is None:
        return None

    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl",
            headers=cloudflare_headers(email, api_key),
            timeout=30,
        )

        if not response.ok:
            print(f"API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return None

        data = response.json()
        if not data.get("success"):
            print("Failed to fetch current SSL mode")
            print(f"Errors: {data.get('errors', 'Unknown error')}")
            return None

        return data["result"]["value"]

    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        return None


def fix_ssl_mode(
    zone_id: str,
    target_mode: str,
    email: str,
    api_key: str,
    apply: bool = False,
) -> bool:
    """
    Preview or change SSL mode for a zone.

    Args:
        zone_id: Cloudflare zone ID
        target_mode: Target SSL mode ('flexible', 'full', 'strict', 'off')
        email: Cloudflare account email
        api_key: Cloudflare Global API Key
        apply: Change live settings when True; otherwise run dry-run preview

    Returns:
        True if preview/update succeeds, False otherwise
    """
    if target_mode not in VALID_MODES:
        print(f"Error: Invalid SSL mode '{target_mode}'")
        print(f"Valid modes: {', '.join(VALID_MODES)}")
        return False

    current_mode = get_ssl_mode(zone_id, email, api_key)
    if current_mode is None:
        return False

    print(f"Current SSL mode: {current_mode}")
    print(f"Target SSL mode:  {target_mode}")

    if not apply:
        print("\nDry run only. No Cloudflare settings were changed.")
        print("Re-run with --apply to update the SSL mode.")
        return True

    requests = get_requests()
    if requests is None:
        return False

    print("\nApplying SSL mode change...")

    try:
        response = requests.patch(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl",
            headers=cloudflare_headers(email, api_key),
            json={"value": target_mode},
            timeout=30,
        )

        if not response.ok:
            print(f"API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        data = response.json()
        if not data.get("success"):
            print("Failed to update SSL mode")
            print(f"Errors: {data.get('errors', 'Unknown error')}")
            return False

        new_mode = data["result"]["value"]
        print(f"SSL mode successfully changed: {current_mode} -> {new_mode}")
        print("\nCloudflare is updating edge servers (typically takes 10-30 seconds)")
        print("Recommendation: Clear your browser cache or use incognito mode to test")
        return True

    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        return False


def purge_cache(zone_id: str, email: str, api_key: str, apply: bool = False) -> bool:
    """Preview or purge all Cloudflare cache for the zone."""
    if not apply:
        print("\nDry run: cache purge requested, but no cache was purged.")
        print("Re-run with --apply to purge the cache.")
        return True

    requests = get_requests()
    if requests is None:
        return False

    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache",
            headers=cloudflare_headers(email, api_key),
            json={"purge_everything": True},
            timeout=30,
        )

        if response.ok and response.json().get("success"):
            print("Cache purged successfully")
            return True

        print(f"Failed to purge cache: {response.status_code}")
        print(f"Response: {response.text}")
        return False

    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        return False


def print_usage() -> None:
    """Print CLI usage."""
    print(
        "Usage: python fix_ssl_mode.py <domain> <email> <api_key> <mode> "
        "[--apply] [--purge-cache]"
    )
    print(
        "\nBy default this script runs in dry-run mode and does not change "
        "live settings."
    )
    print("Add --apply to update SSL mode. --purge-cache also requires --apply.")
    print("\nSSL Modes:")
    print(
        "  flexible - Cloudflare -> Origin uses HTTP "
        "(can cause loops with HTTPS origins)"
    )
    print("  full     - Cloudflare -> Origin uses HTTPS (recommended for most origins)")
    print("  strict   - Full + validates origin certificate (most secure)")
    print("  off      - No encryption (not recommended)")
    print("\nExamples:")
    print("  # Preview the change without writing")
    print("  python fix_ssl_mode.py example.com user@example.com abc123... full")
    print("\n  # Fix redirect loop for GitHub Pages")
    print(
        "  python fix_ssl_mode.py example.com user@example.com abc123... "
        "full --apply --purge-cache"
    )
    print("\n  # Switch to strict mode")
    print(
        "  python fix_ssl_mode.py example.com user@example.com abc123... "
        "strict --apply"
    )


def main() -> None:
    """Main function."""
    if len(sys.argv) < 5:
        print_usage()
        sys.exit(1)

    domain = sys.argv[1]
    email = sys.argv[2]
    api_key = sys.argv[3]
    target_mode = sys.argv[4]
    should_apply = "--apply" in sys.argv
    should_purge = "--purge-cache" in sys.argv

    mode_label = "APPLY" if should_apply else "DRY RUN"
    print(f"\n{mode_label}: SSL configuration for {domain}")
    print("=" * 60)

    zone_id = find_zone_id(domain, email, api_key)
    if zone_id is None:
        sys.exit(1)

    print(f"Found zone: {domain}\n")

    if not fix_ssl_mode(zone_id, target_mode, email, api_key, should_apply):
        sys.exit(1)

    if should_purge:
        print("\nCache purge requested...")
        if not purge_cache(zone_id, email, api_key, should_apply):
            sys.exit(1)

    if should_apply:
        print("\nDone. Test your site after 30 seconds.")
    else:
        print("\nDone. This was a dry run; no live Cloudflare settings were changed.")
    sys.exit(0)


if __name__ == "__main__":
    main()

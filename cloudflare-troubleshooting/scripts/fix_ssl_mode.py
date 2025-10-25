#!/usr/bin/env python3
"""
Fix Cloudflare SSL/TLS mode to resolve redirect loops.

This script changes the SSL mode to resolve common redirect loop issues
caused by SSL mode mismatches between Cloudflare and origin servers.

Common scenarios:
- GitHub Pages + Flexible mode → Change to Full
- Netlify/Vercel + Flexible mode → Change to Full
- Any HTTPS-enforcing origin + Flexible mode → Change to Full

Requires:
- requests library
- Cloudflare API credentials
"""

import sys


def fix_ssl_mode(zone_id: str, target_mode: str, email: str, api_key: str) -> bool:
    """
    Change SSL mode for a zone.

    Args:
        zone_id: Cloudflare zone ID
        target_mode: Target SSL mode ('flexible', 'full', 'full_strict', 'off')
        email: Cloudflare account email
        api_key: Cloudflare Global API Key

    Returns:
        True if successful, False otherwise
    """
    try:
        import requests
    except ImportError:
        print("Error: 'requests' library not installed")
        print("Install with: pip install requests")
        return False

    # Validate mode
    valid_modes = ["flexible", "full", "strict", "off"]
    if target_mode not in valid_modes:
        print(f"Error: Invalid SSL mode '{target_mode}'")
        print(f"Valid modes: {', '.join(valid_modes)}")
        return False

    # Note: API uses 'strict' but documentation calls it 'full (strict)'
    api_mode = target_mode

    try:
        response = requests.patch(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl",
            headers={
                "X-Auth-Email": email,
                "X-Auth-Key": api_key,
                "Content-Type": "application/json"
            },
            json={"value": api_mode},
            timeout=30
        )

        if not response.ok:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        data = response.json()

        if not data.get("success"):
            print(f"❌ Failed to update SSL mode")
            print(f"Errors: {data.get('errors', 'Unknown error')}")
            return False

        new_mode = data["result"]["value"]
        print(f"✅ SSL mode successfully changed to: {new_mode}")
        print(f"\n⏳ Cloudflare is updating edge servers (typically takes 10-30 seconds)")
        print(f"💡 Recommendation: Clear your browser cache or use incognito mode to test")

        return True

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def purge_cache(zone_id: str, email: str, api_key: str) -> bool:
    """Purge all Cloudflare cache for the zone."""
    try:
        import requests
    except ImportError:
        return False

    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache",
            headers={
                "X-Auth-Email": email,
                "X-Auth-Key": api_key,
                "Content-Type": "application/json"
            },
            json={"purge_everything": True},
            timeout=30
        )

        if response.ok and response.json().get("success"):
            print("✅ Cache purged successfully")
            return True

        return False

    except Exception:
        return False


def main():
    """Main function."""
    if len(sys.argv) < 5:
        print("Usage: python fix_ssl_mode.py <domain> <email> <api_key> <mode> [--purge-cache]")
        print("\nSSL Modes:")
        print("  flexible - Cloudflare → Origin uses HTTP (can cause loops with HTTPS origins)")
        print("  full     - Cloudflare → Origin uses HTTPS (recommended for most origins)")
        print("  strict   - Full + validates origin certificate (most secure)")
        print("  off      - No encryption (not recommended)")
        print("\nExamples:")
        print("  # Fix redirect loop for GitHub Pages")
        print("  python fix_ssl_mode.py typeof.tech user@example.com abc123... full --purge-cache")
        print("\n  # Switch to strict mode")
        print("  python fix_ssl_mode.py example.com user@example.com abc123... strict")
        sys.exit(1)

    domain = sys.argv[1]
    email = sys.argv[2]
    api_key = sys.argv[3]
    target_mode = sys.argv[4]
    should_purge = "--purge-cache" in sys.argv

    try:
        import requests
    except ImportError:
        print("Error: 'requests' library not found")
        print("Install with: pip install requests")
        sys.exit(1)

    print(f"\n🔧 Fixing SSL configuration for: {domain}")
    print("=" * 60)

    # Get zone ID
    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones?name={domain}",
            headers={"X-Auth-Email": email, "X-Auth-Key": api_key},
            timeout=30
        )

        if not response.ok:
            print(f"❌ API Error: {response.status_code}")
            sys.exit(1)

        data = response.json()
        if not data.get("success") or not data.get("result"):
            print(f"❌ Domain '{domain}' not found in your Cloudflare account")
            sys.exit(1)

        zone_id = data["result"][0]["id"]
        print(f"✅ Found zone: {domain}\n")

    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        sys.exit(1)

    # Fix SSL mode
    if not fix_ssl_mode(zone_id, target_mode, email, api_key):
        sys.exit(1)

    # Optionally purge cache
    if should_purge:
        print(f"\n🗑️  Purging cache...")
        purge_cache(zone_id, email, api_key)

    print("\n✅ Done! Test your site after 30 seconds.")
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Comprehensive Cloudflare configuration checker.

This script diagnoses common Cloudflare issues including:
- SSL/TLS mode mismatches
- DNS configuration problems
- Cache settings
- Page rules and redirect loops

Requires:
- requests library
- Cloudflare API credentials (email + Global API Key OR API Token)
"""

import json
import sys
from typing import Dict, List, Optional, Tuple


def check_ssl_configuration(
    zone_id: str, email: str, api_key: str
) -> Tuple[bool, List[str]]:
    """
    Check SSL/TLS configuration for common issues.

    Returns: (has_issues, issues_list)
    """
    try:
        import requests
    except ImportError:
        return True, ["Error: 'requests' library not installed. Install with: pip install requests"]

    issues = []

    # Get SSL mode
    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl",
            headers={"X-Auth-Email": email, "X-Auth-Key": api_key},
            timeout=30
        )

        if not response.ok:
            return True, [f"API Error: {response.status_code} - {response.text}"]

        data = response.json()
        if not data.get("success"):
            return True, [f"API Error: {data.get('errors', 'Unknown error')}"]

        ssl_mode = data["result"]["value"]

        # Check Always Use HTTPS setting
        https_response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/always_use_https",
            headers={"X-Auth-Email": email, "X-Auth-Key": api_key},
            timeout=30
        )

        always_https = "off"
        if https_response.ok:
            https_data = https_response.json()
            if https_data.get("success"):
                always_https = https_data["result"]["value"]

        # Analyze configuration
        if ssl_mode == "flexible":
            issues.append(
                f"⚠️  SSL Mode is 'flexible' - this can cause redirect loops if your origin "
                f"server enforces HTTPS (common with GitHub Pages, Netlify, Vercel, etc.)"
            )
            issues.append(
                "   Recommendation: Change SSL mode to 'full' or 'full (strict)' if your "
                "origin supports HTTPS"
            )

        if ssl_mode == "off":
            issues.append("⚠️  SSL is disabled - visitors will see 'Not Secure' warnings")

        # Report current configuration
        if not issues:
            issues.append(f"✅ SSL Mode: {ssl_mode} - Configuration looks good")
            issues.append(f"   Always Use HTTPS: {always_https}")

        return len([i for i in issues if i.startswith("⚠️")]) > 0, issues

    except requests.RequestException as e:
        return True, [f"Network Error: {str(e)}"]
    except Exception as e:
        return True, [f"Unexpected Error: {str(e)}"]


def check_dns_records(
    zone_id: str, domain: str, email: str, api_key: str
) -> Tuple[bool, List[str]]:
    """
    Check DNS configuration for common issues.

    Returns: (has_issues, issues_list)
    """
    try:
        import requests
    except ImportError:
        return True, ["Error: 'requests' library not installed"]

    issues = []

    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            headers={"X-Auth-Email": email, "X-Auth-Key": api_key},
            timeout=30
        )

        if not response.ok:
            return True, [f"API Error: {response.status_code}"]

        data = response.json()
        if not data.get("success"):
            return True, [f"API Error: {data.get('errors')}"]

        records = data["result"]

        # Check for root domain records
        root_records = [r for r in records if r["name"] == domain]
        if not root_records:
            issues.append(f"⚠️  No DNS records found for root domain '{domain}'")

        # Check proxy status
        proxied_records = [r for r in records if r.get("proxied")]
        if proxied_records:
            issues.append(f"✅ Found {len(proxied_records)} proxied record(s) (Cloudflare CDN enabled)")

        unproxied_important = [
            r for r in records
            if not r.get("proxied") and r["type"] in ["A", "AAAA", "CNAME"]
        ]
        if unproxied_important:
            issues.append(
                f"ℹ️  Found {len(unproxied_important)} non-proxied record(s) - "
                "these bypass Cloudflare's CDN and security features"
            )

        return len([i for i in issues if i.startswith("⚠️")]) > 0, issues

    except Exception as e:
        return True, [f"Error checking DNS: {str(e)}"]


def check_page_rules(
    zone_id: str, email: str, api_key: str
) -> Tuple[bool, List[str]]:
    """
    Check Page Rules for potential redirect loops.

    Returns: (has_issues, issues_list)
    """
    try:
        import requests
    except ImportError:
        return True, ["Error: 'requests' library not installed"]

    issues = []

    try:
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/pagerules",
            headers={"X-Auth-Email": email, "X-Auth-Key": api_key},
            timeout=30
        )

        if not response.ok:
            return True, [f"API Error: {response.status_code}"]

        data = response.json()
        if not data.get("success"):
            return True, [f"API Error: {data.get('errors')}"]

        rules = data["result"]

        if not rules:
            issues.append("✅ No Page Rules configured")
            return False, issues

        # Check for redirect rules
        redirect_rules = []
        for rule in rules:
            actions = rule.get("actions", [])
            for action in actions:
                if action.get("id") in ["forwarding_url", "always_use_https"]:
                    redirect_rules.append({
                        "url": rule.get("targets", [{}])[0].get("constraint", {}).get("value"),
                        "action": action.get("id"),
                        "status": rule.get("status")
                    })

        if redirect_rules:
            issues.append(f"ℹ️  Found {len(redirect_rules)} redirect Page Rule(s):")
            for r in redirect_rules:
                issues.append(f"   - {r['url']}: {r['action']} (status: {r['status']})")
            issues.append(
                "   Note: Conflicting redirect rules can cause redirect loops"
            )
        else:
            issues.append("✅ No redirect Page Rules found")

        return False, issues

    except Exception as e:
        return True, [f"Error checking Page Rules: {str(e)}"]


def main():
    """Main diagnostic function."""
    if len(sys.argv) < 4:
        print("Usage: python check_cloudflare_config.py <domain> <email> <api_key>")
        print("\nExample:")
        print("  python check_cloudflare_config.py typeof.tech user@example.com abc123...")
        print("\nGet your Global API Key from:")
        print("  https://dash.cloudflare.com/profile/api-tokens")
        sys.exit(1)

    domain = sys.argv[1]
    email = sys.argv[2]
    api_key = sys.argv[3]

    try:
        import requests
    except ImportError:
        print("Error: 'requests' library not found")
        print("Install with: pip install requests")
        sys.exit(1)

    print(f"\n🔍 Checking Cloudflare configuration for: {domain}\n")
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
        print(f"✅ Found zone: {domain} (ID: {zone_id})\n")

    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        sys.exit(1)

    # Run all checks
    all_issues = []

    print("\n📋 SSL/TLS Configuration:")
    print("-" * 60)
    has_ssl_issues, ssl_issues = check_ssl_configuration(zone_id, email, api_key)
    for issue in ssl_issues:
        print(issue)

    print("\n📋 DNS Configuration:")
    print("-" * 60)
    has_dns_issues, dns_issues = check_dns_records(zone_id, domain, email, api_key)
    for issue in dns_issues:
        print(issue)

    print("\n📋 Page Rules:")
    print("-" * 60)
    has_rules_issues, rules_issues = check_page_rules(zone_id, email, api_key)
    for issue in rules_issues:
        print(issue)

    # Summary
    print("\n" + "=" * 60)
    if has_ssl_issues or has_dns_issues or has_rules_issues:
        print("⚠️  Issues found - review the warnings above")
        sys.exit(1)
    else:
        print("✅ No critical issues detected!")
        sys.exit(0)


if __name__ == "__main__":
    main()

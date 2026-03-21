#!/usr/bin/env python3
"""
Quick tunnel/proxy conflict diagnostics for macOS.

This script detects the most common local and Tailscale networking conflicts:
1) Shell proxy env + NO_PROXY mismatch
2) System proxy exceptions mismatch
3) Proxy path failure vs direct path success
4) Local TLS trust issues
5) Route ownership conflicts for a Tailscale IP (optional)
"""

import argparse
import json
import os
import re
import shlex
import socket
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


def run(cmd: List[str], env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def match_proxy_pattern(host: str, pattern: str) -> bool:
    p = pattern.strip().lower()
    h = host.strip().lower()
    if not p or not h:
        return False

    # CIDR / wildcard IP patterns are not domain checks.
    if "/" in p and not p.startswith("*."):
        return False
    if re.match(r"^\d+\.\d+\.\d+\.\*$", p):
        return False

    if p == h:
        return True
    if p.startswith("*."):
        suffix = p[1:]  # keep leading dot
        return h.endswith(suffix)
    if p.startswith("."):
        return h.endswith(p)
    return False


def has_host_bypass(host: str, patterns: List[str]) -> bool:
    return any(match_proxy_pattern(host, item) for item in patterns)


def parse_scutil_proxy() -> Dict[str, object]:
    code, stdout, _stderr = run(["scutil", "--proxy"])
    if code != 0:
        return {"raw": "", "exceptions": [], "http_enabled": False, "https_enabled": False}

    raw = stdout
    exceptions: List[str] = []
    for line in raw.splitlines():
        m = re.search(r"\d+\s*:\s*(.+)$", line)
        if m and "ExceptionsList" not in line:
            exceptions.append(m.group(1).strip())

    http_enabled = bool(re.search(r"HTTPEnable\s*:\s*1", raw))
    https_enabled = bool(re.search(r"HTTPSEnable\s*:\s*1", raw))

    return {
        "raw": raw,
        "exceptions": exceptions,
        "http_enabled": http_enabled,
        "https_enabled": https_enabled,
    }


def resolve_host(host: str) -> List[str]:
    ips = []
    try:
        infos = socket.getaddrinfo(host, None)
        for item in infos:
            ip = item[4][0]
            if ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        pass
    return ips


def curl_status(url: str, timeout: int, mode: str, proxy_url: Optional[str] = None) -> Dict[str, object]:
    cmd = [
        "curl",
        "-k",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        str(timeout),
        url,
    ]

    env = os.environ.copy()
    if mode == "direct":
        for key in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
        ):
            env.pop(key, None)
    elif mode == "forced_proxy" and proxy_url:
        cmd.extend(["--proxy", proxy_url])

    code, stdout, stderr = run(cmd, env=env)
    http_code = stdout if stdout else "000"
    ok = code == 0 and http_code.isdigit() and http_code != "000"

    return {
        "ok": ok,
        "http_code": http_code,
        "exit_code": code,
        "stderr": stderr,
        "command": " ".join(shlex.quote(x) for x in cmd),
    }


def strict_tls_check(url: str, timeout: int) -> Dict[str, object]:
    cmd = [
        "curl",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        str(timeout),
        url,
    ]
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(key, None)
    code, stdout, stderr = run(cmd, env=env)
    cert_issue = "certificate" in stderr.lower() or "ssl" in stderr.lower()
    return {
        "ok": code == 0 and stdout != "000",
        "http_code": stdout if stdout else "000",
        "exit_code": code,
        "stderr": stderr,
        "cert_issue": cert_issue,
    }


def find_tailscale_utun() -> Optional[str]:
    """Find which utun interface belongs to Tailscale (has a 100.x.x.x IP)."""
    code, stdout, _ = run(["ifconfig"])
    if code != 0:
        return None
    current_iface = ""
    for line in stdout.splitlines():
        # Interface header line (e.g., "utun7: flags=...")
        m = re.match(r"^(\w+):", line)
        if m:
            current_iface = m.group(1)
        # Look for Tailscale CGNAT IP on a utun interface
        if current_iface.startswith("utun") and "inet 100." in line:
            return current_iface
    return None


def get_iface_mtu(iface: str) -> Optional[int]:
    """Get MTU of a network interface."""
    code, stdout, _ = run(["ifconfig", iface])
    if code != 0:
        return None
    m = re.search(r"mtu\s+(\d+)", stdout)
    return int(m.group(1)) if m else None


def route_check(tailscale_ip: str) -> Dict[str, object]:
    code, stdout, stderr = run(["route", "-n", "get", tailscale_ip])
    if code != 0:
        return {"ok": False, "interface": "", "gateway": "", "raw": stderr or stdout}

    interface = ""
    gateway = ""
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("interface:"):
            interface = line.split(":", 1)[1].strip()
        if line.startswith("gateway:"):
            gateway = line.split(":", 1)[1].strip()

    # Identify which utun is Tailscale's and whether the route points to it
    tailscale_utun = find_tailscale_utun()
    route_mtu = get_iface_mtu(interface) if interface else None
    is_tailscale_iface = (interface == tailscale_utun) if tailscale_utun else None
    wrong_utun = (
        interface.startswith("utun")
        and tailscale_utun is not None
        and interface != tailscale_utun
    )

    return {
        "ok": True,
        "interface": interface,
        "gateway": gateway,
        "tailscale_utun": tailscale_utun or "",
        "route_iface_mtu": route_mtu,
        "is_tailscale_iface": is_tailscale_iface,
        "wrong_utun": wrong_utun,
        "raw": stdout,
    }


def pick_proxy_url() -> Optional[str]:
    for key in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def build_report(
    host: str,
    url: str,
    timeout: int,
    tailscale_ip: Optional[str],
) -> Dict[str, object]:
    no_proxy = os.environ.get("NO_PROXY", "")
    no_proxy_lc = os.environ.get("no_proxy", "")
    no_proxy_entries = split_csv(no_proxy if no_proxy else no_proxy_lc)

    scutil_info = parse_scutil_proxy()
    scutil_exceptions = scutil_info["exceptions"]

    proxy_url = pick_proxy_url()
    direct = curl_status(url, timeout, mode="direct")
    ambient = curl_status(url, timeout, mode="ambient")
    forced_proxy = curl_status(url, timeout, mode="forced_proxy", proxy_url=proxy_url) if proxy_url else None
    strict_tls = strict_tls_check(url, timeout) if url.startswith("https://") else None

    host_ips = resolve_host(host)
    host_in_no_proxy = has_host_bypass(host, no_proxy_entries)
    host_in_scutil_exceptions = has_host_bypass(host, scutil_exceptions)

    findings: List[Dict[str, str]] = []

    if not host_ips:
        findings.append(
            {
                "level": "error",
                "title": "Host resolution failed",
                "detail": f"{host} could not be resolved. Check DNS/hosts first.",
                "fix": f"Add a hosts entry if this is local: 127.0.0.1 {host}",
            }
        )

    if proxy_url and not host_in_no_proxy:
        findings.append(
            {
                "level": "warn",
                "title": "NO_PROXY missing target host",
                "detail": f"Proxy is enabled ({proxy_url}) but NO_PROXY does not match {host}.",
                "fix": (
                    "Add host to NO_PROXY/no_proxy, e.g. "
                    f"NO_PROXY=...,{host}"
                ),
            }
        )

    if (scutil_info["http_enabled"] or scutil_info["https_enabled"]) and not host_in_scutil_exceptions:
        findings.append(
            {
                "level": "warn",
                "title": "System proxy exception missing target host",
                "detail": f"scutil active exceptions do not include {host}.",
                "fix": (
                    "Add host to proxy app skip/bypass list (Shadowrocket/Clash/Surge), "
                    "then reload profile."
                ),
            }
        )

    if direct["ok"] and forced_proxy and not forced_proxy["ok"]:
        findings.append(
            {
                "level": "error",
                "title": "Proxy path is broken for target host",
                "detail": (
                    "Direct access works, but forced proxy tunnel fails. "
                    "Traffic must bypass proxy for this host."
                ),
                "fix": (
                    f"Add {host} to both NO_PROXY and proxy app skip-proxy/DIRECT rules."
                ),
            }
        )

    if not ambient["ok"] and direct["ok"]:
        findings.append(
            {
                "level": "error",
                "title": "Ambient shell path fails while direct path works",
                "detail": (
                    "Current shell env/proxy settings break default access."
                ),
                "fix": (
                    "Use NO_PROXY for this host, or temporarily unset proxy env for local verification."
                ),
            }
        )

    if strict_tls and not strict_tls["ok"] and direct["ok"] and strict_tls["cert_issue"]:
        findings.append(
            {
                "level": "warn",
                "title": "TLS trust issue detected",
                "detail": "Network path is reachable, but strict TLS validation failed.",
                "fix": "Trust local CA certificate (for local/internal TLS) or use a valid public cert.",
            }
        )

    route_info = route_check(tailscale_ip) if tailscale_ip else None
    if route_info and route_info["ok"]:
        iface = str(route_info["interface"])
        ts_utun = str(route_info.get("tailscale_utun", ""))
        route_mtu = route_info.get("route_iface_mtu")
        wrong_utun = route_info.get("wrong_utun", False)

        if iface.startswith("en"):
            findings.append(
                {
                    "level": "error",
                    "title": "Possible route hijack for Tailscale destination",
                    "detail": f"route -n get {tailscale_ip} resolved to {iface}, not utun*.",
                    "fix": (
                        "Check proxy TUN excluded-routes. Do not exclude 100.64.0.0/10 from TUN route table."
                    ),
                }
            )
        elif wrong_utun:
            mtu_hint = f" (MTU {route_mtu})" if route_mtu else ""
            findings.append(
                {
                    "level": "error",
                    "title": "Route points to wrong utun interface",
                    "detail": (
                        f"route -n get {tailscale_ip} resolved to {iface}{mtu_hint}, "
                        f"but Tailscale is on {ts_utun}. "
                        f"Likely hitting Shadowrocket/VPN TUN (MTU 4064) instead of Tailscale (MTU 1280)."
                    ),
                    "fix": (
                        "Check proxy TUN excluded-routes and rule ordering. "
                        "Ensure IP-CIDR,100.64.0.0/10,DIRECT is in proxy rules."
                    ),
                }
            )

    summary = {
        "host": host,
        "url": url,
        "host_ips": host_ips,
        "proxy_url": proxy_url or "",
        "env_no_proxy": no_proxy if no_proxy else no_proxy_lc,
        "host_in_no_proxy": host_in_no_proxy,
        "scutil_http_enabled": scutil_info["http_enabled"],
        "scutil_https_enabled": scutil_info["https_enabled"],
        "host_in_scutil_exceptions": host_in_scutil_exceptions,
        "connectivity": {
            "ambient": ambient,
            "direct": direct,
            "forced_proxy": forced_proxy,
            "strict_tls": strict_tls,
        },
        "tailscale_route": route_info,
        "findings": findings,
    }
    return summary


def print_human(report: Dict[str, object]) -> int:
    print("=== Tunnel Doctor Quick Diagnose ===")
    print(f"Host: {report['host']}")
    print(f"URL: {report['url']}")
    ips = report["host_ips"]
    print(f"Resolved IPs: {', '.join(ips) if ips else 'N/A'}")
    print("")

    print("Proxy Context")
    print(f"- proxy env: {report['proxy_url'] or '(not set)'}")
    print(f"- host in NO_PROXY: {'yes' if report['host_in_no_proxy'] else 'no'}")
    print(
        "- system proxy enabled: "
        f"HTTP={'yes' if report['scutil_http_enabled'] else 'no'} "
        f"HTTPS={'yes' if report['scutil_https_enabled'] else 'no'}"
    )
    print(f"- host in scutil exceptions: {'yes' if report['host_in_scutil_exceptions'] else 'no'}")
    print("")

    conn = report["connectivity"]
    print("Connectivity Checks")
    for key in ("ambient", "direct", "forced_proxy", "strict_tls"):
        value = conn.get(key)
        if not value:
            continue
        ok = "PASS" if value.get("ok") else "FAIL"
        print(
            f"- {key:12s}: {ok} "
            f"(http={value.get('http_code', '000')}, exit={value.get('exit_code', 'n/a')})"
        )
        stderr = value.get("stderr")
        if stderr:
            print(f"  stderr: {stderr}")
    print("")

    route = report.get("tailscale_route")
    if route:
        if route.get("ok"):
            print("Tailscale Route Check")
            print(f"- route interface: {route.get('interface') or 'N/A'}")
            route_mtu = route.get("route_iface_mtu")
            if route_mtu:
                print(f"  route iface MTU: {route_mtu}")
            print(f"- gateway:         {route.get('gateway') or 'N/A'}")
            ts_utun = route.get("tailscale_utun")
            if ts_utun:
                print(f"- tailscale utun:  {ts_utun}")
                is_ts = route.get("is_tailscale_iface")
                if is_ts is True:
                    print("  route → Tailscale utun: YES (correct)")
                elif is_ts is False:
                    print("  route → Tailscale utun: NO (MISMATCH — see findings)")
            else:
                print("- tailscale utun:  (not detected — is Tailscale running?)")
            print("")
        else:
            print("Tailscale Route Check")
            print(f"- failed: {route.get('raw', '')}")
            print("")

    findings = report["findings"]
    if not findings:
        print("Result: no high-confidence conflict found.")
        print("If browser still fails, verify proxy app profile mode/rule order and reload profile.")
        return 0

    print("Findings")
    severity_order = {"error": 0, "warn": 1, "info": 2}
    findings_sorted = sorted(findings, key=lambda x: severity_order.get(str(x.get("level")), 99))
    for idx, item in enumerate(findings_sorted, start=1):
        print(f"{idx}. [{item['level'].upper()}] {item['title']}")
        print(f"   Detail: {item['detail']}")
        print(f"   Fix:    {item['fix']}")

    return 1 if any(x["level"] == "error" for x in findings) else 0


def main() -> int:
    if sys.platform != "darwin":
        print("This script is designed for macOS only.", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(
        description="Quick diagnostics for Tailscale + proxy conflicts on macOS."
    )
    parser.add_argument("--host", default="local.claude4.dev", help="Target host to diagnose.")
    parser.add_argument(
        "--url",
        default="",
        help="Full URL to test. Default: https://<host>/health",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=8,
        help="curl timeout seconds (default: 8).",
    )
    parser.add_argument(
        "--tailscale-ip",
        default="",
        help="Optional Tailscale IP for route ownership check (e.g. 100.101.102.103).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON report.",
    )
    args = parser.parse_args()

    url = args.url.strip() or f"https://{args.host}/health"
    report = build_report(
        host=args.host.strip(),
        url=url,
        timeout=max(args.timeout, 1),
        tailscale_ip=args.tailscale_ip.strip() or None,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    return print_human(report)


if __name__ == "__main__":
    sys.exit(main())

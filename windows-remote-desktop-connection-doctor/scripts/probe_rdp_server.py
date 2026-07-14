#!/usr/bin/env python3
"""Standalone RDP protocol probe for Windows App diagnostics.

Sends an X.224 Connection Request with RDP_NEG_REQ to TCP 3389 and parses the
RDP_NEG_RSP to confirm the server speaks the RDP protocol stack. Then upgrades
the same socket to TLS to verify the transport layer works without requiring
credentials or the Windows App client.

Use this to falsify "the server is down" when Windows App is stuck at a
progress dialog. A successful probe means the server-side RDP stack is healthy
and the problem is almost certainly client-side (auth, identity, local proxy,
app state).

Usage:
    python3 scripts/probe_rdp_server.py <host> [port]
    python3 scripts/probe_rdp_server.py 192.168.1.10
    python3 scripts/probe_rdp_server.py my-pc.example.com 13389

Exit codes:
    0  RDP protocol responded and TLS handshake succeeded
    1  Usage / argument error
    2  TCP connection refused / timeout / network unreachable
    3  RDP protocol response malformed or rejected
    4  TLS handshake failed
"""

import socket
import ssl
import struct
import sys
from typing import Optional

# TPKT (4) + X.224 CR (7) + RDP_NEG_REQ (8) = 19 bytes
# X.224: 0x03 0x00 0x00 0x13 (len=19) 0x0e (CR) 0xe0 (DST) 0x00 0x00 0x00 0x00 0x00 (src)
# RDP_NEG_REQ: 0x01 0x00 0x08 0x00 0x03 0x00 0x00 0x00 (TLS+Hybrid)
RDP_NEG_REQ_PACKET = bytes.fromhex("030000130ee000000000000100080003000000")


def probe_rdp_server(host: str, port: int = 3389, timeout: float = 8.0) -> None:
    sock: Optional[socket.socket] = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        print(f"TCP connect to {host}:{port} failed: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        sock.sendall(RDP_NEG_REQ_PACKET)
        resp = sock.recv(256)
    except OSError as exc:
        print(f"Failed to send/receive RDP negotiation packet: {exc}", file=sys.stderr)
        sys.exit(2)

    if len(resp) < 19:
        print(f"RDP response too short ({len(resp)} bytes): {resp.hex()}", file=sys.stderr)
        sys.exit(3)

    # TPKT header: resp[0] == 0x03, resp[1] == 0x00, resp[2:4] = length
    # X.224 CC: resp[4] == 0x0e (CC), resp[5] == 0xd0 (DST), resp[6:11] = variable
    # RDP_NEG type: resp[11] (0x02 = RDP_NEG_RSP, 0x03 = RDP_NEG_FAILURE)
    # RDP_NEG flags: resp[12]
    # RDP_NEG length: resp[13:15]
    # Selected protocol: resp[15:19] LE
    tpkt_length = struct.unpack(">H", resp[2:4])[0]
    x224_type = resp[4]
    neg_type = resp[11]
    selected = struct.unpack("<I", resp[15:19])[0]

    print(f"TPKT length: {tpkt_length}, X.224 type: 0x{x224_type:02x}, RDP_NEG type: 0x{neg_type:02x}")
    print(f"Selected protocol: {selected} (0x{selected:08x})")

    if neg_type != 0x02:
        # 0x03 = RDP_NEG_FAILURE; failureCode is at resp[15:19]
        failure_code = struct.unpack("<I", resp[15:19])[0]
        print(f"RDP_NEG_FAILURE: 0x{failure_code:08x}", file=sys.stderr)
        sys.exit(3)

    protocol_names = {
        0x00000000: "Standard RDP (no TLS/NLA)",
        0x00000001: "TLS",
        0x00000002: "CredSSP/NLA (Hybrid)",
        0x00000003: "TLS + CredSSP/NLA",
        0x00000008: "RDSTLS",
    }
    print(f"Negotiated security: {protocol_names.get(selected, 'Unknown')}")

    # Upgrade to TLS to prove the transport is healthy. We intentionally disable
    # verification because the diagnostic goal is to confirm the RDP stack
    # accepts TLS, not to validate the certificate chain.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        tls_sock = ctx.wrap_socket(sock, server_hostname=host)
        cipher = tls_sock.cipher()
        version = tls_sock.version()
        print(f"TLS handshake OK: {version}, cipher={cipher[0]}")
    except ssl.SSLError as exc:
        print(f"TLS handshake failed: {exc}", file=sys.stderr)
        sys.exit(4)
    finally:
        try:
            tls_sock.close()
        except Exception:
            pass

    print(f"RDP server {host}:{port} is reachable and healthy (RDP + TLS).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <host> [port]", file=sys.stderr)
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 3389
    probe_rdp_server(host, port)

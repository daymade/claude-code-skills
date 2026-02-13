# Windows App Log Analysis Guide

Detailed patterns for parsing Windows App (Microsoft Remote Desktop) diagnostic logs on macOS.

## Contents

- Log file locations
- Log file naming and rotation
- Startup health check block
- Transport negotiation entries
- Error signatures and their meaning
- Comparing working vs broken sessions
- Filtering noise from logs

## Log File Locations

### macOS

```
~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows App/
```

Files follow the pattern:
```
com.microsoft.rdc.macos_v<version>_<YYYY-MM-DD>_<HH-mm-ss>.log
```

A new log file is created each day or when the app restarts. Multiple files may exist — sort by modification time to find the most recent:

```bash
ls -lt ~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows\ App/
```

## Startup Health Check Block

When the Windows App launches, it runs a health check sequence. A healthy startup produces entries in this order:

```
Passed: InternetConnectivity
0: 1
4: 3
AvcDecodingCheck: 0
HardwarePresenterCheck: 0
AvcHwDecodingCheck: 1
4: 4
TCP/IP Traffic Routed Through VPN: No
STUN/TURN Traffic Routed Through VPN: Yes
```

Followed by gateway reachability tests:

```
Passed URL: https://afdfp-rdgateway-r1.wvd.microsoft.com/ Attempts Made: 1 Used Ipv4: 1 HTTP Status Code: 200 Response Time: 480
Passed URL: https://rdweb.wvd.microsoft.com/ Attempts Made: 1 Used Ipv4: 1 HTTP Status Code: 200 Response Time: 613
```

### What Each Entry Means

| Entry | Description |
|-------|-------------|
| `Passed: InternetConnectivity` | General internet reachability confirmed |
| `AvcDecodingCheck` / `AvcHwDecodingCheck` | Hardware video decoding capability (0=unavailable, 1=available) |
| `HardwarePresenterCheck` | Hardware presentation capability |
| `TCP/IP Traffic Routed Through VPN` | Whether the client detects a VPN intercepting TCP traffic |
| `STUN/TURN Traffic Routed Through VPN` | Whether the client detects a VPN intercepting STUN/TURN (UDP) traffic |
| `Passed URL: ...` | Gateway reachability test with response time in ms |

### When Health Check Fails

If the startup health check block is **completely absent** from a log, the diagnostic subsystem itself failed. Check for certificate validation errors near the log start:

```
DIAGNOSTICS(ERR): Failed to validate X509CertificateChain, certificate is not trusted.
BASIX_DCT(ERR): OSSLClosingException thrown, msg=Certificate validation failed
```

This indicates TLS interception (common with ISP HTTPS proxies in China) or DNS poisoning affecting Microsoft diagnostic endpoints.

## Transport Negotiation Entries

### FetchClientOptions

This is the critical function that retrieves transport capabilities from the gateway:

```
GATEWAY(ERR): CWVDTransport::FetchClientOptions exception when attempting to fetch client options: Request timed out
    wvd_transport.cpp(521): FetchClientOptions()
```

When this times out, the client cannot discover available transport options (including Shortpath). The connection will fall back to WebSocket.

### ClientOptions Controller

A separate mechanism that refreshes client properties:

```
ClientOptions_Controller(ERR): ClientOptionsController RefreshProperties attempt 1 failed: Request timed out. Retrying in 30s...
    client_options.cpp(214): RefreshProperties()
```

This is less critical than `FetchClientOptions` but indicates general connectivity issues to Microsoft configuration services.

### WebRTC Session

```
A3CORE(ERR): OnRDWebRTCRedirectorRpc rtcSession not handled
```

This appears when the server sends a WebRTC session setup but the client does not process it. This may indicate incomplete Shortpath support in the client version, or a session setup that arrives after fallback.

Note: `OnRDWebRTCRedirectorRpc notifyClipRectChanged not handled` is a benign clipboard-related message, not transport-related.

## Error Signatures

### Certificate Validation Failure

```
DIAGNOSTICS(ERR): Failed to validate X509CertificateChain, certificate is not trusted.
A3CORE(ERR): ITrustDelegateAdaptorPtr is empty.
BASIX_DCT(ERR): OSSLClosingException thrown, msg=Certificate validation failed, ossl error string="error:00000000:lib(0)::reason(0)", closing error code=1002
```

**Cause**: TLS certificate for Microsoft diagnostic endpoints is not trusted. Common with ISP HTTPS proxies/MITM, DNS poisoning, or corporate proxy servers.

**Impact**: Prevents the diagnostic health check from completing, which may block transport capability discovery.

### Channel Write Failures

```
"-legacy-"(ERR): Channel::StartWrite failed
```

Multiple consecutive `StartWrite failed` errors indicate a connection disruption — the WebSocket or TCP connection to the gateway was interrupted. This is typically followed by a reconnection attempt.

### Diagnostics Flush Errors

```
DIAGNOSTICS(ERR): FlushTracesInternal() is called before BeginUpload(). we don't have a claims token yet
```

This is a benign telemetry error — the diagnostics system tried to upload traces before authentication completed. Does NOT affect connection quality.

## Comparing Working vs Broken Sessions

The most effective diagnostic approach: compare a log from when the connection was healthy (UDP transport) with the current broken log.

### Quick Comparison Script

```bash
LOG_DIR=~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows\ App

echo "=== Health check and transport entries per log file ==="
for f in "$LOG_DIR"/*.log; do
  echo ""
  echo "--- $(basename "$f") ---"
  grep -c "InternetConnectivity" "$f" 2>/dev/null | xargs -I{} echo "  InternetConnectivity checks: {}"
  grep "Routed Through VPN" "$f" 2>/dev/null | head -2 | sed 's/^/  /'
  grep "Passed URL:" "$f" 2>/dev/null | head -2 | sed 's/^/  /'
  grep "FetchClientOptions" "$f" 2>/dev/null | head -1 | sed 's/^/  /'
  grep "Certificate validation failed" "$f" 2>/dev/null | head -1 | sed 's/^/  /'
done
```

### What to Compare

| Aspect | Working (UDP) | Broken (WebSocket) |
|--------|--------------|-------------------|
| Health check block | Present, complete | Missing or incomplete |
| `TCP/IP Routed Through VPN` | Present | Missing |
| `STUN/TURN Routed Through VPN` | Present | Missing |
| `Passed URL:` | Present with response times | Missing |
| `FetchClientOptions` | No error | Timeout error |
| Certificate errors | None at startup | Present at startup |

## Filtering Noise

Windows App logs contain many repetitive entries that obscure useful information. Filter these out:

```bash
grep -v -E "BasicStateManagement|DynVC.*SendChannelClose|dynvcstat.*SerializeToJson|asynctransport\.cpp|FlushTracesInternal"
```

### Common Noise Patterns

| Pattern | What It Is | Safe to Filter |
|---------|-----------|----------------|
| `~BasicStateManagement()` | Transport object destructor | Yes |
| `SendChannelClose()` | Dynamic virtual channel cleanup | Yes |
| `SerializeToJson()` | Channel stats serialization | Yes |
| `FlushTracesInternal()` | Telemetry upload attempt | Yes |
| `Stateful object ... destructed while in state Opened` | Abrupt connection close | Context-dependent |

The last pattern (`Stateful object destructed in Opened state`) may be significant during active troubleshooting — it indicates connections being torn down unexpectedly. Keep it when investigating disconnection events.

## Activity ID Tracking

Each RDP session gets a unique activity ID (GUID). Track a specific session through the log:

```bash
# Find activity IDs from connection events
grep -E "\{[0-9a-f]{8}-" "$LOG_FILE" | grep -v "00000000-0000-0000-0000-000000000000" | head -5

# Trace a specific session
grep "<activity-id>" "$LOG_FILE" | grep -v "BasicStateManagement\|FlushTraces"
```

The null GUID `{00000000-0000-0000-0000-000000000000}` indicates background/system events, not specific RDP sessions.

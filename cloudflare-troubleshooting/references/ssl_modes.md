# Cloudflare SSL/TLS Modes Explained

## Overview

Cloudflare offers four SSL/TLS encryption modes that determine how traffic is encrypted between visitors, Cloudflare, and your origin server.

```
Visitor ←→ Cloudflare ←→ Origin Server
  [A]         [B]          [C]

[A] Visitor to Cloudflare: Always HTTPS (handled by Cloudflare Universal SSL)
[B] Cloudflare to Origin: Depends on SSL mode setting
```

## The Four SSL Modes

### 1. Off (Not Recommended)

**Encryption:**
- Visitor → Cloudflare: HTTP (unencrypted)
- Cloudflare → Origin: HTTP (unencrypted)

**When to use:** Never. This disables HTTPS entirely.

**Issues:**
- Browser shows "Not Secure" warning
- No encryption between visitor and Cloudflare
- Vulnerable to man-in-the-middle attacks

---

### 2. Flexible

**Encryption:**
- Visitor → Cloudflare: HTTPS (encrypted)
- Cloudflare → Origin: HTTP (unencrypted)

**When to use:**
- Origin server doesn't support HTTPS
- Legacy systems without SSL certificates
- Temporary solution during certificate setup

**Issues:**
- ⚠️ **CAUSES REDIRECT LOOPS** with origins that enforce HTTPS
- Traffic between Cloudflare and origin is unencrypted
- Not recommended for sensitive data

**Common redirect loop scenario:**
```
1. Browser requests https://example.com
2. Cloudflare receives HTTPS request
3. Cloudflare forwards HTTP request to origin (because mode is Flexible)
4. Origin server enforces HTTPS → redirects to https://example.com
5. Back to step 1 → INFINITE LOOP
```

**Affected platforms:**
- GitHub Pages
- Netlify
- Vercel
- Heroku
- Any platform that enforces HTTPS

---

### 3. Full (Recommended for Most Cases)

**Encryption:**
- Visitor → Cloudflare: HTTPS (encrypted)
- Cloudflare → Origin: HTTPS (encrypted)

**When to use:**
- Origin server supports HTTPS (most modern hosting)
- Self-signed certificates on origin
- Default choice for GitHub Pages, Netlify, Vercel, etc.

**Benefits:**
- End-to-end encryption
- No redirect loops with HTTPS-enforcing origins
- Compatible with self-signed certificates

**Important:**
- Cloudflare does NOT validate origin certificate
- Origin can use self-signed or expired certificates
- Still provides encryption, just doesn't verify origin identity

---

### 4. Full (Strict) (Most Secure)

**Encryption:**
- Visitor → Cloudflare: HTTPS (encrypted)
- Cloudflare → Origin: HTTPS (encrypted + validated)

**When to use:**
- Origin has valid SSL certificate from trusted CA
- Maximum security requirements
- Production environments with proper certificates

**Requirements:**
- Origin must have valid certificate from trusted CA
- Certificate must not be expired
- Certificate must match the domain

**Benefits:**
- Maximum security
- Validates origin server identity
- Prevents man-in-the-middle attacks between Cloudflare and origin

**Issues if misconfigured:**
- 526 error if origin certificate is invalid
- 525 error if SSL handshake fails

---

## Decision Matrix

| Origin Supports HTTPS? | Origin Certificate Valid? | Recommended Mode | Why |
|------------------------|---------------------------|------------------|-----|
| No | N/A | Flexible | Only option (but upgrade origin ASAP) |
| Yes | Self-signed/Invalid | Full | Encrypts traffic, doesn't validate cert |
| Yes | Valid from trusted CA | Full (Strict) | Maximum security |
| Yes (enforced) | Any | Full or Full (Strict) | Prevents redirect loops |

## Common Platforms and Recommended Modes

| Platform | Enforces HTTPS? | Recommended Mode | Notes |
|----------|-----------------|------------------|-------|
| GitHub Pages | Yes | Full or Full (Strict) | Full (Strict) preferred |
| Netlify | Yes | Full or Full (Strict) | Has valid certificates |
| Vercel | Yes | Full or Full (Strict) | Has valid certificates |
| Heroku | Yes | Full or Full (Strict) | Has valid certificates |
| Custom VPS | Depends | Full (Strict) if possible | Install Let's Encrypt cert |
| Shared Hosting | Varies | Check with host | Usually Full |
| AWS CloudFront | Configurable | Full (Strict) | Use ACM certificates |

## Troubleshooting SSL Mode Issues

### Redirect Loop (ERR_TOO_MANY_REDIRECTS)

**Cause:** SSL mode is "Flexible" but origin enforces HTTPS

**Solution:**
```bash
# Check current mode
curl -X GET "https://api.cloudflare.com/client/v4/zones/ZONE_ID/settings/ssl" \
  -H "X-Auth-Email: email" \
  -H "X-Auth-Key: key"

# Change to Full
python scripts/fix_ssl_mode.py domain.com email API_KEY full --purge-cache
```

### Error 526 (Invalid SSL Certificate)

**Cause:** Mode is "Full (Strict)" but origin certificate is invalid

**Solutions:**
1. Install valid certificate on origin (recommended)
2. Switch to "Full" mode temporarily:
   ```bash
   python scripts/fix_ssl_mode.py domain.com email API_KEY full
   ```
3. Use Cloudflare Origin Certificate (free, only trusted by Cloudflare)

### Error 525 (SSL Handshake Failed)

**Cause:** Origin server SSL/TLS configuration issue

**Solutions:**
1. Check origin server SSL logs
2. Verify origin supports TLS 1.2 or higher
3. Ensure origin port 443 is open
4. Check cipher suite compatibility

## Best Practices

### 1. Start with Full Mode
When in doubt, use "Full" mode for origins that support HTTPS

### 2. Upgrade to Full (Strict) When Possible
Install proper certificates and use Full (Strict) for production

### 3. Never Use Flexible for New Sites
Flexible should only be used for legacy systems during migration

### 4. Use Cloudflare Origin Certificates
For custom origin servers, install Cloudflare Origin Certificates:
- Free
- Valid for 15 years
- Trusted by Cloudflare (enables Full Strict mode)
- Generate at: SSL/TLS → Origin Server → Create Certificate

### 5. Monitor SSL Errors
Set up alerts for SSL-related errors (525, 526) in Cloudflare Analytics

### 6. Test After Changes
- Clear browser cache
- Test in incognito mode
- Purge Cloudflare cache
- Wait 30-60 seconds for edge server updates

## Additional Security Settings

### Always Use HTTPS
- Redirects all HTTP requests to HTTPS
- Located: SSL/TLS → Edge Certificates
- Usually enabled by default
- Can cause loops if misconfigured with Page Rules

### HTTP Strict Transport Security (HSTS)
- Forces browsers to always use HTTPS
- Can't easily revert (browsers cache for months)
- Enable only when HTTPS is stable
- Located: SSL/TLS → Edge Certificates

### Minimum TLS Version
- Set to TLS 1.2 minimum (recommended)
- TLS 1.3 for maximum security
- Located: SSL/TLS → Edge Certificates

### Opportunistic Encryption
- Encrypts traffic when possible
- Good for mixed content
- Located: SSL/TLS → Edge Certificates

## API Reference

### Get SSL Mode
```bash
curl -X GET "https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl" \
  -H "X-Auth-Email: user@example.com" \
  -H "X-Auth-Key: api_key" \
  -H "Content-Type: application/json"
```

### Change SSL Mode
```bash
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/{zone_id}/settings/ssl" \
  -H "X-Auth-Email: user@example.com" \
  -H "X-Auth-Key: api_key" \
  -H "Content-Type: application/json" \
  --data '{"value":"full"}'
```

Valid values: `off`, `flexible`, `full`, `strict`

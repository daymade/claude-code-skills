# Common Cloudflare Issues and Solutions

## Redirect Loop Errors (ERR_TOO_MANY_REDIRECTS)

### Symptom
Browser displays "This page isn't working" or "ERR_TOO_MANY_REDIRECTS"

### Common Causes

#### 1. SSL Mode Mismatch (Most Common)
**Scenario:** Origin server enforces HTTPS, but Cloudflare SSL mode is "Flexible"

**Explanation:**
- Browser → HTTPS → Cloudflare
- Cloudflare → HTTP → Origin Server (because of Flexible mode)
- Origin Server → Redirects to HTTPS (because it enforces HTTPS)
- Infinite loop

**Affected Platforms:**
- GitHub Pages
- Netlify
- Vercel
- Heroku
- Most modern hosting platforms

**Solution:**
Change SSL mode from "Flexible" to "Full" or "Full (strict)"

```bash
# Diagnose
python scripts/check_cloudflare_config.py example.com user@example.com API_KEY

# Fix
python scripts/fix_ssl_mode.py example.com user@example.com API_KEY full --purge-cache
```

#### 2. Conflicting Page Rules
**Scenario:** Multiple redirect rules that conflict with each other

**Solution:**
- Review Page Rules in Cloudflare Dashboard
- Remove conflicting "Always Use HTTPS" or "Forwarding URL" rules
- Ensure redirect rules don't create loops

#### 3. Origin Server Misconfiguration
**Scenario:** Origin server has incorrect redirect rules in .htaccess or nginx config

**Solution:**
- Check origin server configuration
- Verify redirects don't conflict with Cloudflare settings
- Test direct origin access (bypass Cloudflare)

### Resolution Steps

1. **Check SSL mode:**
   ```bash
   curl -X GET "https://api.cloudflare.com/client/v4/zones/ZONE_ID/settings/ssl" \
     -H "X-Auth-Email: email" \
     -H "X-Auth-Key: key"
   ```

2. **Fix SSL mode if needed:**
   ```bash
   python scripts/fix_ssl_mode.py domain.com email API_KEY full
   ```

3. **Purge cache:**
   ```bash
   curl -X POST "https://api.cloudflare.com/client/v4/zones/ZONE_ID/purge_cache" \
     -H "X-Auth-Email: email" \
     -H "X-Auth-Key: key" \
     -d '{"purge_everything":true}'
   ```

4. **Clear browser cache or use incognito mode**

---

## DNS Resolution Issues

### Symptom
Website not accessible or showing old content

### Common Causes

#### 1. DNS Not Propagated
**Solution:** Wait 24-48 hours for full DNS propagation

Check propagation:
```bash
dig domain.com
nslookup domain.com
```

#### 2. Incorrect DNS Records
**Solution:**
- Verify A/AAAA/CNAME records point to correct IPs
- For GitHub Pages: Use A records to GitHub IPs or CNAME to username.github.io
- Ensure "Proxied" status matches requirements

#### 3. DNSSEC Issues
**Solution:**
- Check DNSSEC status in Cloudflare Dashboard
- Verify DS records at registrar match Cloudflare's DNSSEC settings

---

## SSL/TLS Certificate Errors

### Symptom
"Your connection is not private" or "NET::ERR_CERT_COMMON_NAME_INVALID"

### Common Causes

#### 1. Universal SSL Certificate Provisioning Delay
**Solution:** Wait 15-30 minutes for Cloudflare to provision certificate

#### 2. CAA Records Blocking Certificate Issuance
**Solution:**
- Check CAA records
- Ensure CAA allows Let's Encrypt: `letsencrypt.org` or Cloudflare CAs

#### 3. Full (Strict) Mode with Invalid Origin Certificate
**Solution:**
- Use "Full" mode instead of "Full (strict)" if origin cert is self-signed
- Or install valid certificate on origin server

---

## Performance Issues

### Symptom
Slow page load times despite using Cloudflare

### Common Causes

#### 1. Cache Not Configured
**Solution:**
- Enable Auto Minify (JS, CSS, HTML)
- Set up Page Rules for cache levels
- Configure Browser Cache TTL

#### 2. Large Assets Not Optimized
**Solution:**
- Enable Cloudflare Image Optimization
- Use WebP format
- Implement lazy loading

#### 3. Too Many Uncached Requests
**Solution:**
- Review cache analytics
- Add cache rules for static assets
- Use Cloudflare Workers for dynamic caching

---

## Access Denied / 403 Errors

### Symptom
"Error 1020: Access Denied" or generic 403

### Common Causes

#### 1. Firewall Rules Blocking Traffic
**Solution:**
- Review Firewall Rules in Security → WAF
- Check IP Access Rules
- Verify Managed Rulesets aren't too strict

#### 2. Rate Limiting
**Solution:**
- Check Rate Limiting rules
- Adjust thresholds if legitimate traffic is blocked

#### 3. Browser Integrity Check
**Solution:**
- Disable "Browser Integrity Check" if needed
- Found in: Security → Settings

---

## Origin Server Errors (502/503/504)

### Symptom
"502 Bad Gateway" or "504 Gateway Timeout"

### Common Causes

#### 1. Origin Server Down
**Solution:**
- Verify origin server is running
- Check origin server logs
- Test direct IP access

#### 2. Origin SSL Certificate Invalid (Full Strict mode)
**Solution:**
- Switch to "Full" mode temporarily
- Fix origin certificate
- Or use Cloudflare Origin Certificate

#### 3. Timeout Issues
**Solution:**
- Increase origin server timeout settings
- Optimize slow queries/code
- Consider using Cloudflare Workers for timeouts

---

## Page Rules Not Working

### Symptom
Page Rules don't seem to apply

### Common Causes

#### 1. Rule Order
**Solution:** Page Rules are executed top-to-bottom; reorder if needed

#### 2. Pattern Matching Issues
**Solution:**
- Use `*` for wildcards correctly
- Test patterns: `example.com/*` vs `*example.com/*`

#### 3. Cache Already Set
**Solution:** Purge cache after creating/modifying Page Rules

---

## Troubleshooting Workflow

### Step 1: Identify the Issue
- Collect error messages and codes
- Note when issue started
- Check if issue is intermittent or consistent

### Step 2: Check Cloudflare Status
- Visit https://www.cloudflarestatus.com
- Verify no ongoing incidents

### Step 3: Run Diagnostics
```bash
python scripts/check_cloudflare_config.py domain.com email API_KEY
```

### Step 4: Review Recent Changes
- Check Cloudflare Audit Log
- Review recent DNS/SSL/Page Rule changes

### Step 5: Test Bypass
- Temporarily set DNS to "DNS Only" (grey cloud)
- Test if issue persists without Cloudflare

### Step 6: Apply Fixes
- Implement specific solutions based on diagnosis
- Purge cache after changes
- Test in incognito/private mode

### Step 7: Monitor
- Verify fix works consistently
- Check analytics for any anomalies
- Document solution for future reference

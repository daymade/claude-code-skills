# Cloudflare API Overview

## Authentication

### Global API Key (used in examples)
```bash
curl -X GET "https://api.cloudflare.com/client/v4/..." \
  -H "X-Auth-Email: user@example.com" \
  -H "X-Auth-Key: abc123..."
```

### API Token (recommended for production)
```bash
curl -X GET "https://api.cloudflare.com/client/v4/..." \
  -H "Authorization: Bearer <token>"
```

## Response Format

All API responses follow this structure:
```json
{
  "success": true/false,
  "errors": [],
  "messages": [],
  "result": { ... },
  "result_info": { ... }
}
```

Always check `success` field before processing `result`.

## Core Endpoints by Category

### Zone Management

**List zones:**
```bash
GET /zones?name=<domain>
```
Returns zone information including `id`, `name`, `status`, `name_servers`

**Get zone details:**
```bash
GET /zones/{zone_id}
```

**Get all zone settings:**
```bash
GET /zones/{zone_id}/settings
```
Returns all configurable settings for the zone

### SSL/TLS

**Get SSL mode:**
```bash
GET /zones/{zone_id}/settings/ssl
```
Result: `{"value": "flexible"|"full"|"strict"|"off"}`

**Update SSL mode:**
```bash
PATCH /zones/{zone_id}/settings/ssl
Content-Type: application/json
{"value": "full"}
```

**Get Always Use HTTPS:**
```bash
GET /zones/{zone_id}/settings/always_use_https
```

**Update Always Use HTTPS:**
```bash
PATCH /zones/{zone_id}/settings/always_use_https
{"value": "on"|"off"}
```

**List SSL certificates:**
```bash
GET /zones/{zone_id}/ssl/certificate_packs
```

**Get SSL verification details:**
```bash
GET /zones/{zone_id}/ssl/verification
```

**Get SSL settings (universal, dedicated, etc):**
```bash
GET /zones/{zone_id}/ssl/analyze
```

**TLS 1.3 setting:**
```bash
GET /zones/{zone_id}/settings/tls_1_3
PATCH /zones/{zone_id}/settings/tls_1_3
{"value": "on"|"off"|"zrt"}
```

**Minimum TLS version:**
```bash
GET /zones/{zone_id}/settings/min_tls_version
PATCH /zones/{zone_id}/settings/min_tls_version
{"value": "1.0"|"1.1"|"1.2"|"1.3"}
```

### DNS Records

**List DNS records:**
```bash
GET /zones/{zone_id}/dns_records
```
Returns array of DNS records with type, name, content, proxied status, TTL

**Filter by type:**
```bash
GET /zones/{zone_id}/dns_records?type=A
GET /zones/{zone_id}/dns_records?type=CNAME
```

**Get specific record:**
```bash
GET /zones/{zone_id}/dns_records/{record_id}
```

**Create DNS record:**
```bash
POST /zones/{zone_id}/dns_records
{
  "type": "A",
  "name": "example.com",
  "content": "192.0.2.1",
  "ttl": 3600,
  "proxied": true
}
```

**Update DNS record:**
```bash
PATCH /zones/{zone_id}/dns_records/{record_id}
{"proxied": true}
```

**Delete DNS record:**
```bash
DELETE /zones/{zone_id}/dns_records/{record_id}
```

**DNSSEC status:**
```bash
GET /zones/{zone_id}/dnssec
```

### Page Rules

**List page rules:**
```bash
GET /zones/{zone_id}/pagerules
```

**Get specific page rule:**
```bash
GET /zones/{zone_id}/pagerules/{rule_id}
```

**Create page rule:**
```bash
POST /zones/{zone_id}/pagerules
{
  "targets": [{"target": "url", "constraint": {"operator": "matches", "value": "*example.com/*"}}],
  "actions": [{"id": "always_use_https"}],
  "priority": 1,
  "status": "active"
}
```

**Update page rule:**
```bash
PATCH /zones/{zone_id}/pagerules/{rule_id}
```

**Delete page rule:**
```bash
DELETE /zones/{zone_id}/pagerules/{rule_id}
```

### Cache

**Purge everything:**
```bash
POST /zones/{zone_id}/purge_cache
{"purge_everything": true}
```

**Purge by URL:**
```bash
POST /zones/{zone_id}/purge_cache
{"files": ["https://example.com/style.css", "https://example.com/script.js"]}
```

**Purge by tag:**
```bash
POST /zones/{zone_id}/purge_cache
{"tags": ["tag1", "tag2"]}
```

**Purge by host:**
```bash
POST /zones/{zone_id}/purge_cache
{"hosts": ["example.com", "www.example.com"]}
```

**Cache settings:**
```bash
GET /zones/{zone_id}/settings/cache_level
GET /zones/{zone_id}/settings/browser_cache_ttl
GET /zones/{zone_id}/settings/development_mode
```

### Firewall

**List firewall rules:**
```bash
GET /zones/{zone_id}/firewall/rules
```

**List WAF rules:**
```bash
GET /zones/{zone_id}/firewall/waf/packages
GET /zones/{zone_id}/firewall/waf/packages/{package_id}/rules
```

**IP Access Rules:**
```bash
GET /zones/{zone_id}/firewall/access_rules/rules
POST /zones/{zone_id}/firewall/access_rules/rules
{
  "mode": "block"|"challenge"|"whitelist",
  "configuration": {"target": "ip", "value": "192.0.2.1"},
  "notes": "Blocked malicious IP"
}
```

**Rate limiting:**
```bash
GET /zones/{zone_id}/rate_limits
POST /zones/{zone_id}/rate_limits
```

### Analytics

**Get analytics:**
```bash
GET /zones/{zone_id}/analytics/dashboard
```

**Traffic analytics:**
```bash
GET /zones/{zone_id}/analytics/colos
```

**DNS analytics:**
```bash
GET /zones/{zone_id}/dns_analytics/report
```

### Load Balancers

**List load balancers:**
```bash
GET /zones/{zone_id}/load_balancers
```

**Get load balancer details:**
```bash
GET /zones/{zone_id}/load_balancers/{lb_id}
```

**List pools:**
```bash
GET /accounts/{account_id}/load_balancers/pools
```

**List monitors:**
```bash
GET /accounts/{account_id}/load_balancers/monitors
```

### Workers & Routes

**List worker routes:**
```bash
GET /zones/{zone_id}/workers/routes
```

**List worker scripts:**
```bash
GET /accounts/{account_id}/workers/scripts
```

### Settings (Other Common)

**Development mode:**
```bash
GET /zones/{zone_id}/settings/development_mode
PATCH /zones/{zone_id}/settings/development_mode
{"value": "on"|"off"}
```

**Security level:**
```bash
GET /zones/{zone_id}/settings/security_level
PATCH /zones/{zone_id}/settings/security_level
{"value": "off"|"essentially_off"|"low"|"medium"|"high"|"under_attack"}
```

**Rocket Loader:**
```bash
GET /zones/{zone_id}/settings/rocket_loader
PATCH /zones/{zone_id}/settings/rocket_loader
{"value": "on"|"off"}
```

**Auto minify:**
```bash
GET /zones/{zone_id}/settings/minify
PATCH /zones/{zone_id}/settings/minify
{"value": {"css": "on", "html": "on", "js": "on"}}
```

**Brotli compression:**
```bash
GET /zones/{zone_id}/settings/brotli
```

**HTTP/2:**
```bash
GET /zones/{zone_id}/settings/http2
```

**HTTP/3 (QUIC):**
```bash
GET /zones/{zone_id}/settings/http3
```

**IPv6:**
```bash
GET /zones/{zone_id}/settings/ipv6
```

**Opportunistic Encryption:**
```bash
GET /zones/{zone_id}/settings/opportunistic_encryption
```

**Automatic HTTPS Rewrites:**
```bash
GET /zones/{zone_id}/settings/automatic_https_rewrites
PATCH /zones/{zone_id}/settings/automatic_https_rewrites
{"value": "on"|"off"}
```

## Learning New Endpoints

### Method 1: List All Settings
```bash
curl -s -X GET "https://api.cloudflare.com/client/v4/zones/{zone_id}/settings" \
  -H "X-Auth-Email: email" \
  -H "X-Auth-Key: key" | jq '.result[] | {id, value}'
```

This returns all available settings with current values. Use setting `id` to construct endpoint:
`/zones/{zone_id}/settings/{id}`

### Method 2: Cloudflare API Docs

Browse official API reference: https://developers.cloudflare.com/api/

**Structure:**
- Operations organized by product/feature
- Each operation shows:
  - HTTP method and endpoint
  - Required/optional parameters
  - Request body schema
  - Response schema
  - Example requests

**Search strategy:**
1. Identify feature/product (SSL, DNS, Cache, etc.)
2. Find relevant operations (List, Get, Create, Update, Delete)
3. Check request schema for required fields
4. Test with GET before making changes

### Method 3: Explore API Interactively

**Pattern:**
1. Start with zone info to understand structure
2. List resources: `GET /zones/{zone_id}/{resource_type}`
3. Get specific item: `GET /zones/{zone_id}/{resource_type}/{id}`
4. Check available operations in docs
5. Make changes: `PATCH/POST/DELETE`

**Example exploration for unknown feature:**
```bash
# 1. Check if endpoint exists
curl -I "https://api.cloudflare.com/client/v4/zones/{zone_id}/feature_name"

# 2. Try listing (if collection)
curl -X GET "https://api.cloudflare.com/client/v4/zones/{zone_id}/feature_name" \
  -H "X-Auth-Email: email" \
  -H "X-Auth-Key: key"

# 3. Examine response structure
# 4. Consult docs for modification operations
```

## Error Handling

Common error codes:
- 400: Bad request (check request format)
- 401: Unauthorized (check API credentials)
- 403: Forbidden (insufficient permissions)
- 404: Not found (check zone_id or resource_id)
- 429: Rate limit exceeded (wait before retrying)
- 500: Server error (Cloudflare issue, retry later)

**Error response structure:**
```json
{
  "success": false,
  "errors": [
    {
      "code": 1234,
      "message": "Error description"
    }
  ],
  "messages": [],
  "result": null
}
```

## Rate Limits

- Free tier: ~1200 requests per 5 minutes
- Paid tiers: Higher limits based on plan
- If rate limited (429), back off exponentially

## Best Practices

1. **Use jq for readability:**
   ```bash
   curl ... | jq '.result'
   ```

2. **Extract specific fields:**
   ```bash
   curl ... | jq '.result.value'
   curl ... | jq '.result[] | {id, name, value}'
   ```

3. **Check success before processing:**
   ```bash
   response=$(curl ...)
   success=$(echo "$response" | jq -r '.success')
   if [ "$success" = "true" ]; then
     echo "$response" | jq '.result'
   else
     echo "$response" | jq '.errors'
   fi
   ```

4. **Store zone_id for reuse:**
   ```bash
   zone_id=$(curl ... | jq -r '.result[0].id')
   ```

5. **Test with GET first:**
   Before modifying configuration, always GET to see current state

## Common Investigation Patterns

### Pattern 1: Settings Investigation
```bash
# Get all settings
curl -X GET "/zones/{zone_id}/settings" | jq '.result[]'

# Filter specific settings
curl -X GET "/zones/{zone_id}/settings" | jq '.result[] | select(.id | contains("ssl"))'
```

### Pattern 2: Resource Listing + Details
```bash
# List resources
curl -X GET "/zones/{zone_id}/dns_records" | jq '.result[] | {id, name, type}'

# Get specific resource
record_id="..."
curl -X GET "/zones/{zone_id}/dns_records/$record_id" | jq '.'
```

### Pattern 3: Multi-Setting Check
```bash
# Check related settings in parallel
curl ... /settings/ssl &
curl ... /settings/always_use_https &
curl ... /pagerules &
wait
```

### Pattern 4: Change + Verify
```bash
# Make change
curl -X PATCH "/zones/{zone_id}/settings/ssl" -d '{"value":"full"}'

# Verify change applied
curl -X GET "/zones/{zone_id}/settings/ssl" | jq '.result.value'
```

## Account-Level vs Zone-Level

Some resources are account-level, not zone-level:

**Account-level:**
- Load balancer pools/monitors: `/accounts/{account_id}/load_balancers/...`
- Workers scripts: `/accounts/{account_id}/workers/...`
- Access policies: `/accounts/{account_id}/access/...`

**Zone-level:**
- DNS records: `/zones/{zone_id}/dns_records`
- SSL settings: `/zones/{zone_id}/settings/ssl`
- Page rules: `/zones/{zone_id}/pagerules`

Get account_id from zone info:
```bash
curl -X GET "/zones?name=example.com" | jq '.result[0].account.id'
```

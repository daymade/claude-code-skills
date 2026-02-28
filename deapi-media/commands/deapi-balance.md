---
name: deapi-balance
description: Check deAPI account balance
---

# deAPI Account Balance

## Step 1: Check balance

```bash
curl -s "https://api.deapi.ai/api/v1/client/balance" \
  -H "Authorization: Bearer $DEAPI_API_KEY"
```

## Step 2: Present result

Response: `{ "data": { "balance": 4.25 } }`

Display: **deAPI balance: {balance} credits**

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 403 Forbidden | API key may be revoked, get a new one at deapi.ai |
| Network error | Check internet connection |

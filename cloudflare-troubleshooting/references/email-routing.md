# Email Routing inspection and delivery verification

Use this workflow when an address should forward incoming mail to an existing mailbox. Reuse the authorized Cloudflare connection selected by SKILL.md. A configured forwarding address alone does not establish an outbound sender identity; evaluate sending separately against the current sending product/API when requested.

## Read the existing route

1. Query `GET /zones?name=<domain>` and select the exact zone for the intended account. Read its `id` and `account.id`; do not borrow an account ID from another domain.
2. Query the endpoints below. Check HTTP status, `success` and `errors` before using `result`. Follow each list endpoint’s pagination metadata until the relevant complete list is available.
3. Match the requested full address against enabled literal `to` matchers and their forwarding actions. Inspect the catch-all separately; an explicit rule and a catch-all are different routes.
4. Match the forwarding destination to the account’s destination-address record and its verification state. Read routing settings such as enabled/status and any readiness/synchronization fields the current response exposes; do not assume one field proves every layer ready.
5. Compare Cloudflare DNS with public MX resolution and the provider’s required records. Preserve existing website records, other aliases and catch-all behavior. If the zone is absent from this account, inspect the actual DNS/mail provider; absence here does not establish a broken mailbox or require a nameserver migration.

All paths below are relative to `https://api.cloudflare.com/client/v4`:

| Evidence | GET endpoint |
|---|---|
| Routing settings | `/zones/{zone_id}/email/routing` |
| Explicit rules | `/zones/{zone_id}/email/routing/rules` |
| Catch-all rule | `/zones/{zone_id}/email/routing/rules/catch_all` |
| Destination addresses | `/accounts/{account_id}/email/routing/addresses` |
| DNS records | `/zones/{zone_id}/dns_records` |

For example, with the project’s existing Global API Key configuration:

```bash
curl --fail-with-body -sS \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/email/routing/rules" \
  -H "X-Auth-Email: ${CF_EMAIL}" \
  -H "X-Auth-Key: ${CF_API_KEY}" | jq .
```

`CF_ZONE_ID` is the selected zone ID; `CF_EMAIL` and `CF_API_KEY` stand for values from the existing authorized connection. If that connection uses an API Token, use its existing `Authorization: Bearer` header instead. This example reads one page; inspect pagination before treating it as the whole list.

## Repair and prove the requested result

If the requested rule already works, retain it. For a missing or incorrect rule, use the current rule API/schema to change that precise alias within the user’s authorized task, then independently query it again. Complete destination verification if required and re-read its state. Do not replace the entire rule set to repair one address.

Distinguish these outcomes:

- **Rule saved:** readback shows the requested matcher, enabled rule and forwarding action.
- **Destination activated:** the destination record is verified and the provider reports routing ready with the required DNS in place.
- **Mail arrived:** a uniquely identifiable test is present in the final destination Inbox, or the user supplies matching receipt evidence.

Use a different configured source mailbox for a forwarding test: forwarding a message back to the same source mailbox can behave differently and is a poor isolated test. Match recipient, subject and body. The sender’s Sent folder proves submission, not arrival. Do not infer delivery failure from an inaccessible mail client, or repeat an uncertain send without resolving its original outcome. Reuse the mail client’s existing send/read workflow.

If local DNS uses fake-IP answers, verify MX through the project’s established independent resolver or DNS-over-HTTPS route. Diagnose records or routing only from actual provider and DNS evidence.

## Reference contract

See the official [Email Routing API](https://developers.cloudflare.com/api/resources/email_routing/) and [Email Routing documentation](https://developers.cloudflare.com/email-routing/). The endpoint sequence above was exercised against a configured forwarding domain in September 2026; an enabled explicit alias, verified destination and unchanged catch-all were read through the API, then actual destination Inbox arrival was checked. That observation supports this readback workflow, not a claim that every account uses the same mail product.

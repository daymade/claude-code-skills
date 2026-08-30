---
name: terraform-skill
description: >-
  Diagnoses and designs safe Terraform releases, provisioners, multi-environment
  isolation, and fresh-host bootstrap. Use when writing or reviewing plan/apply
  wrappers, null_resource, remote-exec, local-exec, file provisioners, cloud-init,
  Docker Compose or Caddy deployment; when staging and production configuration may
  differ; when an IaC rollout can mutate a shared gateway; or when debugging drift,
  saved-plan, provenance, TLS, Restarting/unhealthy containers, DNS duplication,
  snapshot contamination, and post-apply failures. It emphasizes exact reviewed
  artifacts, pre-mutation validation, explicit production authorization, and
  independent live readback.
---

# Terraform Release and Provisioner Safety

Prevent a valid-looking Terraform workflow from publishing unvalidated bytes or widening a change's
blast radius. Keep the user's business outcome and the actual mutation surface ahead of plan counts,
green wrappers, or process completeness.

## Route the task

- Release, shared gateway, saved plan, staging receipt, or production promotion: read
  [release-safety-and-environment-parity.md](references/release-safety-and-environment-parity.md).
- A second environment, DNS ownership, state, or snapshots: read
  [multi-env-isolation.md](references/multi-env-isolation.md).
- Pre-deploy checks or a validator: read
  [pre-deploy-validation.md](references/pre-deploy-validation.md).
- Fresh instance or empty data disk: read
  [zero-to-deploy-checklist.md](references/zero-to-deploy-checklist.md).
- One known provisioner symptom: use the matching pattern below.

## Operating contract

1. Use the repository's canonical wrapper when it has one. Do not bypass it with a raw Terraform,
   SSH, SCP, helper-script, or console path because a gate rejects the planned release.
2. Prefer provider resources, image baking, cloud-init, or configuration management. HashiCorp
   recommends exhausting purpose-built alternatives because Terraform cannot model provisioner side
   effects predictably. When a provisioner remains necessary, make its artifact, target, lock,
   validation, and readback explicit.
3. Inventory every resource or recovery tool that can write the target runtime. A validator attached
   to only one writer does not protect another writer of the same shared service.
4. Give staging and production one required-key schema. Let values differ; never let a key be required
   in one environment and optional, defaulted, absent, or allowed-empty in another.
5. Validate the exact candidate bytes, Compose-rendered environment, and immutable runtime image
   before the first live write or restart. Keep post-deploy checks too: they detect damage but cannot
   prevent the first bad mutation.
6. Treat a saved plan as an executable artifact. Bind it to reviewed source/artifact identity and apply
   that exact file. A successful apply is not a staging receipt; record promotion evidence only after
   every required live verifier succeeds.
7. Require an explicit production decision at the last reversible point. A deadline, `PLAN_DIGEST`,
   `CONFIRM_*`, or agent inference is not production authorization.
8. Stop after the requested result is verified. Do not turn a single-service fix into full-stack drift
   reconciliation, recovery redesign, or unrelated hardening.

## Provisioner traps (symptom → fix)

Use these incident-derived symptom patterns to choose the next falsifying check. Confirm the current
source and runtime before promoting a historical cause into the present diagnosis.

### `docker: not found` in remote-exec

cloud-init still installing Docker when provisioner SSHs in.

```hcl
provisioner "remote-exec" {
  inline = [
    "cloud-init status --wait",
    "command -v docker >/dev/null || { echo 'FATAL: Docker not ready'; exit 1; }",
  ]
}
```

### `rsync: connection unexpectedly closed` in local-exec

Do not infer a universal Terraform limitation from this symptom. A second SSH client can lose to the
target's connection budget, SSH policy, or a competing deploy. Keep `local-exec` local: package an
immutable artifact there, then use a Terraform-managed upload or a purpose-built deploy system. Give
every apply a unique remote staging path; never share `/tmp/src.tar.gz` across concurrent applies.

```hcl
provisioner "local-exec" {
  command = "tar czf /tmp/src-${self.id}.tar.gz --exclude=node_modules --exclude=.git -C ${path.module}/../../.. myproject"
}
provisioner "file" {
  source      = "/tmp/src-${self.id}.tar.gz"
  destination = "/tmp/src-${self.id}.tar.gz"
}
provisioner "remote-exec" {
  inline = ["tar xzf /tmp/src-${self.id}.tar.gz -C /data/ && rm -f /tmp/src-${self.id}.tar.gz"]
}
```

macOS BSD tar: `--exclude` must come BEFORE the source argument.

### `cloud-init status` shows "running" forever

`apt-get -y` does not suppress debconf dialogs. Packages like `iptables-persistent` block on TTY prompts.

```yaml
- |
    echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
    echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
    DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
```

Known offenders: `iptables-persistent`, `postfix`, `mysql-server`, `wireshark-common`.

### `EACCES: permission denied` in container logs, container Restarting

Host volume dirs are root-owned; container runs as non-root (uid 1001). Fix before `docker compose up`:

```bash
mkdir -p /data/myapp/data /data/myapp/logs
chown -R 1001:1001 /data/myapp/data /data/myapp/logs
```

Find UID: grep `adduser.*-u` or `USER` in Dockerfile.

### Provisioner fails but no diagnostic output

Keep fail-fast behavior; attach diagnostics to failure instead of disabling `set -e`. Otherwise an
early failed command can be overwritten by a later green health check.

```hcl
provisioner "remote-exec" {
  inline = [
    "set -eu",
    "trap 'rc=$?; if [ $rc -ne 0 ]; then docker logs myapp --tail 20 2>&1 || true; docker ps --format \\\"table {{.Names}}\\\\t{{.Status}}\\\" || true; fi; exit $rc' EXIT",
    "docker compose up -d",
    "sleep 15",
    "docker ps --filter name=myapp --format '{{.Status}}' | grep -q healthy || exit 1",
  ]
}
```

### Container `Restarting` — database tables missing

DB migrations not in provisioner. PostgreSQL `docker-entrypoint-initdb.d` only runs on empty data dir. Explicitly create DB + run migrations:

```bash
# After postgres healthy:
docker exec pg psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='mydb'" | grep -q 1 \
  || docker exec pg psql -U postgres -c "CREATE DATABASE mydb;"

# Idempotent migrations:
for f in migrations/*.sql; do
  VER=$(basename $f)
  APPLIED=$($PSQL -tAc "SELECT 1 FROM schema_migrations WHERE version='$VER'" | tr -d ' ')
  [ "$APPLIED" = "1" ] && continue
  { echo 'BEGIN;'; cat $f; echo 'COMMIT;'; } | $PSQL
  $PSQL -tAc "INSERT INTO schema_migrations(version) VALUES ('$VER') ON CONFLICT DO NOTHING"
done
```

### Compose uses an unexpected value despite `.env`

Compose interpolation gives the invoking shell higher precedence than `--env-file` or project `.env`.
An old exported value can therefore override the reviewed environment silently. Inspect what Compose
actually used; unset ambient overrides when the env file is meant to be authoritative.

```bash
# Inspect interpolation inputs and the rendered model.
docker compose --env-file .env config --environment
docker compose --env-file .env config --format json > compose.rendered.json

# Make the reviewed env file authoritative for this key.
env -u DOCKER_WITH_PROXY_MODE docker compose --env-file .env build
```

### TLS handshake fails: `Invalid format for Authorization header`

Caddy's Cloudflare DNS module expects a scoped API Token through Bearer authentication. Do not infer
credential type, validity, or permissions from length/prefix alone. Verify the token with Cloudflare's
official endpoint, then exercise the exact zone operation or provider path required by the release.

```bash
curl -fsS https://api.cloudflare.com/client/v4/user/tokens/verify \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -e '.success == true and .result.status == "active"' >/dev/null
```

If the credential is absent or wrong, create a least-privilege API Token through Cloudflare's current
dashboard/API flow and grant only the zones/operations the provider needs. Follow the official creation
contract rather than copying permission-group IDs that may drift:
<https://developers.cloudflare.com/fundamentals/api/get-started/create-token/>.

### TLS fails on staging but works on production — hardcoded domains

Caddyfile or compose has literal domain names. Staging Caddy loads production config, tries to get certs for domains it doesn't own → ACME fails.

**Caddyfile**: Use `{$VAR}` — Caddy evaluates env vars at startup.
```caddy
# WRONG
example.com { tls { dns cloudflare {env.CLOUDFLARE_API_TOKEN} } }

# RIGHT
{$LOBEHUB_DOMAIN} { tls { dns cloudflare {env.CLOUDFLARE_API_TOKEN} } }
```

**Compose**: Use `${VAR:?required}` — fail-fast if unset or empty.
```yaml
# WRONG
- APP_URL=https://example.com

# RIGHT
- APP_URL=${APP_URL:?APP_URL is required}
```

Pass the env var to the gateway container so Caddy can read it:
```yaml
environment:
  - LOBEHUB_DOMAIN=${LOBEHUB_DOMAIN:?LOBEHUB_DOMAIN is required}
  - CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN:?required for DNS-01 TLS}
```

Do not stop at this local assertion. Put all runtime-required keys in one schema, require the same set
from every environment file, render the exact Compose service environment, and run the exact deployed
Caddy image with that full environment before mutating live files. Caddy `{$VAR}` expansion can become
an empty token before parsing; a Caddyfile default is not an environment-completeness check.

### OAuth login fails: `Social sign in failed`

Casdoor `init_data.json` contains hardcoded redirect URIs. `--createDatabase=true` only applies init_data on first-ever DB creation — not on restarts. Fix via SQL in provisioner:

```bash
# Replace production domain with staging in existing Casdoor DB
$PSQL -c "UPDATE application SET redirect_uris = REPLACE(redirect_uris,
  'example.com', 'staging.example.com')
  WHERE name='lobechat'
  AND redirect_uris LIKE '%example.com%'
  AND redirect_uris NOT LIKE '%staging.example.com%';"
```

Also check `AUTH_CASDOOR_ISSUER` — it must match the Casdoor subdomain (`auth.staging.example.com`), not the app root domain.

## Multi-environment isolation

Before creating a second environment, grep `.tf` files for hardcoded names. See [references/multi-env-isolation.md](references/multi-env-isolation.md) for the complete matrix.

Environment isolation does not mean configuration-contract drift. Keep one required-key manifest and
the same validation path for every environment. Staging and production may use different domains,
credentials, instance sizes, and feature values; they must not disagree about whether a runtime key is
required, optional, allowed-empty, or silently defaulted.

**Will fail on apply** (globally unique):

| Resource | Scope | Fix |
|---|---|---|
| SSH key pair | Region | `"${env}-deploy"` |
| SLS log project | Account | `"${env}-logs"` |
| CloudMonitor contact | Account | `"${env}-ops"` |

**DNS duplication trap**: Two environments creating A records for the same name in the same Cloudflare zone → two independent record IDs → DNS round-robin → ~50% traffic to wrong instance. Fix: use subdomain isolation (`staging.example.com`) or separate zones. Remember to create DNS records for ALL subdomains Caddy serves (e.g., `auth.staging`, `minio.staging`).

**Snapshot cross-contamination**: Unfiltered `data "alicloud_ecs_snapshots"` returns ALL account snapshots. New env inherits old 100GB snapshot, fails creating 40GB disk. Gate with variable:

```hcl
locals {
  latest_snapshot_id = var.enable_snapshot_recovery && length(local.available_snapshots) > 0
    ? local.available_snapshots[0].snapshot_id : null
}
```

Do NOT add `count` to the data source — changes its state address, causes drift.

## Pre-deploy validation

Run the cheapest checks first, but do not let a syntax check certify runtime behavior. HashiCorp's
`terraform validate` checks syntax and internal consistency without remote state or provider APIs.
Preconditions can block before their resource action; postconditions run after change and do not undo
what already happened; `check` assertions warn and continue. Choose the mechanism by when damage must
be prevented.

Key checks (see [references/pre-deploy-validation.md](references/pre-deploy-validation.md)):
1. Format, initialize without backend where appropriate, and run `terraform validate`.
2. Compare every environment against one required-key schema; reject missing, duplicate, and empty values.
3. Render the exact Compose model from the candidate files and controlled interpolation environment.
4. Run the production validator from the exact immutable image/module set against dangerous and healthy fixtures.
5. Generate a saved plan; review resource addresses, actions, target scope, artifact identity, and digest.
6. Apply that exact plan only after the required environment-specific authorization.
7. Verify deployed identity and the real user path independently; only then issue a staging/promotion receipt.

## Zero-to-deployment

Fresh disks expose every implicit dependency. See [references/zero-to-deploy-checklist.md](references/zero-to-deploy-checklist.md).

Key items that break provisioners on fresh instances:
1. **Directories**: `mkdir -p /data/{svc1,svc2}` in cloud-init — `file` provisioner fails if target dir missing
2. **Databases**: Explicit `CREATE DATABASE` — PG init scripts only run on empty data dir
3. **Migrations**: Tracked in `schema_migrations` table, applied idempotently
4. **Provisioner ordering**: `depends_on` between resources sharing Docker networks
5. **Memory**: Stop non-critical containers during Docker build on small instances (≤8GB)
6. **Environment contract**: Every runtime-required value uses the same required-key schema in every environment
7. **Credential capability**: Verify current status and the exact required operation; do not trust shape alone

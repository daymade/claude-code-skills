# Multi-Environment Isolation Checklist

Use when creating, changing or retiring an environment alongside production. Verify both state isolation and physical data ownership; separate Terraform addresses do not prove separate cloud backends.

## Configuration contract parity

Keep one machine-readable list of runtime-required keys. Every environment must contain each key
exactly once with a non-empty value. Only values differ by environment; requiredness does not.

Do not use these as environment isolation mechanisms:

- A production-only default that lets a missing key render as empty or as a guessed hostname
- A staging-only assertion that production never runs
- A hand-maintained list of variables inside one deploy writer
- A validator that reads the operator shell instead of the candidate environment artifact

Render each environment through the same production parser and compare the resulting key set before
planning. For Compose, remember that shell variables outrank `--env-file` and project `.env`; sanitize
ambient overrides or print `docker compose config --environment` as evidence.

## Terraform state isolation

Two environments MUST use different state paths. Different prefixes isolate state objects, not the cloud resources or service-side deletion effects:

```hcl
# production
backend "oss" {
  bucket = "myproject-terraform-state"
  prefix = "environments/production"
}

# staging
backend "oss" {
  bucket = "myproject-terraform-state"  # same bucket OK
  prefix = "environments/staging"       # different prefix = isolated state
}
```

**Verification**: Compare physical resource IDs and consumer bindings across the relevant states and live APIs. Different addresses or names in state lists do not prove separation.

## Resource naming collision matrix

Grep every `.tf` file for hardcoded names. Every globally-unique resource will collide.

### Must rename (apply will fail)

| Resource | Uniqueness scope | Fix pattern |
|---|---|---|
| SSH key pair (`key_pair_name`) | Region | `"${env}-deploy"` |
| SLS log project (`project_name`) | Account | `"${env}-logs"` |
| CloudMonitor contact (`alarm_contact_name`) | Account | `"${env}-ops"` |
| CloudMonitor contact group | Account | `"${env}-ops"` |

### Should rename (won't fail but causes confusion)

| Resource | Issue if same name |
|---|---|
| Security group name | Two SGs with same name in same VPC, can't tell apart in console |
| ECS instance name/hostname | Two instances named `myapp-spot` in console |
| Data disk name | Same in disk list |
| Auto snapshot policy name | Same in policy list |
| SLS machine group name | Logs from both instances land in same group |

### Pattern: Use a module name variable

```hcl
# production main.tf
module "app" {
  source = "../../modules/spot-with-data-disk"
  name   = "production-spot"  # flows to instance_name, disk_name, snapshot_policy_name
}

# staging main.tf
module "app" {
  source = "../../modules/spot-with-data-disk"
  name   = "staging-spot"     # all child resource names auto-isolated
}
```

## DNS record isolation

### The duplication trap

Two Terraform environments creating A records for `@` (root) in the same Cloudflare zone:
- Each gets its own Cloudflare record ID (independent)
- Cloudflare now has TWO A records for the same domain
- DNS round-robins between the two IPs
- ~50% of traffic goes to the wrong instance

### Correct patterns

**Pattern A: Subdomain isolation** (recommended for staging/lab):
```hcl
# Production: root domain records
resource "cloudflare_dns_record" "prod" {
  name = "@"  # example.com
}

# Staging: subdomain records only
resource "cloudflare_dns_record" "staging" {
  name = "staging"  # staging.example.com
}
```

**Pattern B: Separate zones** (for fully independent deployments):
Each environment gets its own domain/zone. No shared Cloudflare zone IDs.

**Pattern C: One environment owns DNS** (production):
Only production has DNS resources. Other environments access via IP only.

### Destroy safety

When one environment is destroyed:
- Its DNS records are deleted (by their specific Cloudflare record IDs)
- Other environments' DNS records are NOT affected
- **Verify before destroy**: Compare DNS record IDs between environments:
  ```bash
  terraform state show 'cloudflare_dns_record.app["root"]' | grep "^id"
  ```
  IDs must be different.

## Backend deletion and data lifecycle

Before a destroy, replacement, integration uninstall or environment retirement:

1. Map the exact account/region/physical backend IDs to every active consumer.
   Separate the environment owning compute/configuration from the owner of durable
   metrics, logs, databases and object storage. Reused VPCs can share integrations.
2. Inspect the selected provider version's delete implementation and current cloud
   API semantics, including cascade/delete-data flags. An environment-only plan can
   still delete a shared backend through one provider API call. Unknown cascade
   behavior is an unresolved destructive boundary, not evidence of safety.
3. If durable data is shared, remove the teardown's ownership of it through the
   project's reviewed lifecycle/state-migration process. Do not solve this by
   ad-hoc state removal, disabling guards or restoring over current data.
4. Bind the destructive plan to the authorized physical IDs and documented effects.
   Use provider lifecycle protection and cloud-side delete denial where available;
   Terraform `prevent_destroy` alone cannot guard console/API or parent cascades.
5. Verify the last successful independent backup and a real scratch restore of
   pre-incident data. A snapshot policy, timer, recreated ID or new ingestion is
   not historical recovery evidence. Query an old known-nonempty time window and
   current consumer continuity after the authorized change.

Stop before mutation if a surviving consumer or unknown data-deletion effect
remains. Execute only the resolved, authorized plan; do not expand a routine
read-only audit into a destructive recovery exercise.

## Shared resources (verify ownership before sharing)

These may be referenced without being managed by the second environment. Verify that deleting its child integrations cannot cascade into them; a reference alone is not protection.

| Resource | Required isolation |
|---|---|
| VPC / VSwitch | Referenced by ID, not created |
| Cloudflare zone ID | Referenced, records are independent |
| OSS state bucket | Different prefix = different state |
| SSH public key content | Same key, different key pair resource |
| Cloud provider credentials | Same account, different resources |

## Makefile pattern for multi-environment

```makefile
ENV ?= production
ENV_DIR := environments/$(ENV)

init: ; cd $(ENV_DIR) && terraform init
plan: pre-deploy ; cd $(ENV_DIR) && terraform plan -out=tfplan
apply: ; cd $(ENV_DIR) && terraform apply tfplan
drift: ; cd $(ENV_DIR) && terraform plan -detailed-exitcode
```

Usage: `make plan ENV=staging`

In a real repository, keep Terraform behind its existing canonical Make/CI wrapper rather than
copying this minimal example over stronger saved-plan, digest, authorization, or provenance gates.

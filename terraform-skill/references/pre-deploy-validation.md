# Pre-Deploy Validation Ladder

Run validation at the earliest phase that can still prevent the failure. Do not collapse syntax,
candidate behavior, plan scope, deployed state, and user-visible outcome into one green check.

## 1. Static configuration

Run the repository's canonical formatter and wrapper. If no wrapper exists:

```bash
terraform fmt -check -recursive
terraform init -backend=false -input=false
terraform validate
```

`terraform validate` checks syntax and internal consistency. It does not consult remote state or
provider APIs and cannot prove environment values, runtime modules, network access, or user behavior.

Use variable validation and resource preconditions for values Terraform knows before mutation.
Postconditions run after a resource operation and do not roll back earlier effects. Terraform `check`
blocks report warnings and continue, so they are observability rather than a destructive-change gate.

## 2. One environment schema

Define runtime-required keys once in a machine-readable manifest or derive them from the canonical
configuration. Apply the same rules to staging and production:

- Every required key appears exactly once.
- Missing and empty are both failures.
- Any unresolved `${IDENTIFIER}` token in a required effective value is a failure, including a
  placeholder that references a different missing key.
- Optional keys are explicitly classified; they do not share the required list.
- Environment files may change values, never requiredness.
- Caddy/Compose defaults are product defaults only, not a way to hide incomplete deployment input.

Calibrate the checker with one known-good environment and known-bad fixtures for missing, duplicate,
explicit-empty, self-placeholder, and foreign-placeholder values. A validator without a dangerous-input
test has not proved it can fail.

## 3. Render the effective runtime model

Docker Compose interpolation precedence is shell, then `--env-file`, then project `.env`. Prevent an
operator's ambient export from changing a reviewed release. Render the candidate with explicit project,
Compose, and env paths, then inspect the canonical model:

```bash
docker compose \
  --project-directory "$CANDIDATE_ROOT" \
  --env-file "$CANDIDATE_ROOT/environment.env" \
  -f "$CANDIDATE_ROOT/compose.yaml" \
  config --format json > "$CANDIDATE_ROOT/compose.rendered.json"
```

Run this command from a sanitized environment or explicitly reject ambient keys that can override the
candidate. Confirm the rendered service contains the exact immutable image and the complete environment
map. Do not rebuild a hand-selected env list in each deploy writer.

## 4. Run the production validator before live mutation

Use the same parser/module set that production will run. For Caddy, run the exact image digest with the
candidate directory and its full Compose-derived environment:

```bash
set -euo pipefail

GATEWAY_SERVICE=claude4dev-gateway
: "${CANDIDATE_ROOT:?candidate root is required}"
: "${EXPECTED_CADDY_IMAGE_DIGEST:?reviewed Caddy image digest is required}"
GATEWAY_ENV_FILE="$CANDIDATE_ROOT/gateway.effective.env"
REQUIRED_ENV_FILE="$CANDIDATE_ROOT/gateway/required-env.keys"
[ -s "$REQUIRED_ENV_FILE" ] \
  || { echo "FATAL: required-key manifest is missing or empty" >&2; exit 1; }

RENDERED_GATEWAY_IMAGE="$(jq -er --arg service "$GATEWAY_SERVICE" '
  .services[$service].image
  | select(type == "string" and length > 0)
' "$CANDIDATE_ROOT/compose.rendered.json")"

printf '%s\n' "$EXPECTED_CADDY_IMAGE_DIGEST" \
  | grep -Eq '@sha256:[0-9a-f]{64}$' \
  || { echo "FATAL: expected Caddy image is not an immutable digest" >&2; exit 1; }

[ "$RENDERED_GATEWAY_IMAGE" = "$EXPECTED_CADDY_IMAGE_DIGEST" ] \
  || { echo "FATAL: rendered gateway image differs from the reviewed digest" >&2; exit 1; }

jq -e --arg service "$GATEWAY_SERVICE" '
  .services[$service].environment
  | type == "object"
    and all(to_entries[];
      (.key | test("^[A-Za-z_][A-Za-z0-9_]*$"))
      and (.value | type == "string")
      and ((.value | contains("\n")) | not)
      and ((.value | test("\\$\\{[A-Za-z_][A-Za-z0-9_]*\\}")) | not)
    )
' "$CANDIDATE_ROOT/compose.rendered.json" >/dev/null \
  || { echo "FATAL: rendered gateway environment contains an invalid key, value, or unresolved placeholder" >&2; exit 1; }

required_count=0
seen_required=' '
while IFS= read -r required_key || [ -n "$required_key" ]; do
  case "$required_key" in
    ''|'#'*) continue ;;
    [A-Za-z_]*)
      case "$required_key" in
        *[!A-Za-z0-9_]*) echo "FATAL: invalid required key: $required_key" >&2; exit 1 ;;
      esac
      ;;
    *) echo "FATAL: invalid required key: $required_key" >&2; exit 1 ;;
  esac
  case "$seen_required" in
    *" $required_key "*) echo "FATAL: duplicate required key: $required_key" >&2; exit 1 ;;
  esac
  seen_required="$seen_required$required_key "
  required_count=$((required_count + 1))

  if ! required_value="$(jq -er --arg service "$GATEWAY_SERVICE" --arg key "$required_key" '
    .services[$service].environment[$key] | select(type == "string")
  ' "$CANDIDATE_ROOT/compose.rendered.json")"; then
    echo "FATAL: required gateway environment key is missing: $required_key" >&2
    exit 1
  fi
  [ -n "$required_value" ] \
    || { echo "FATAL: required gateway environment key is empty: $required_key" >&2; exit 1; }
  if printf '%s\n' "$required_value" | grep -Eq '\$\{[A-Za-z_][A-Za-z0-9_]*\}'; then
    echo "FATAL: required gateway environment key is unresolved: $required_key" >&2
    exit 1
  fi
done < "$REQUIRED_ENV_FILE"
[ "$required_count" -gt 0 ] \
  || { echo "FATAL: required-key manifest contains no keys" >&2; exit 1; }

jq -r --arg service "$GATEWAY_SERVICE" '
  .services[$service].environment
  | to_entries | sort_by(.key)[] | "\(.key)=\(.value)"
' "$CANDIDATE_ROOT/compose.rendered.json" > "$GATEWAY_ENV_FILE"
chmod 600 "$GATEWAY_ENV_FILE"

docker run --rm --pull=never --network none \
  --env-file "$GATEWAY_ENV_FILE" \
  -v "$CANDIDATE_ROOT/gateway:/etc/caddy:ro" \
  "$EXPECTED_CADDY_IMAGE_DIGEST" \
  caddy adapt --config /etc/caddy/Caddyfile --validate
```

`caddy adapt` alone is weaker: `--validate` also loads and provisions the adapted configuration. Keep
network disabled unless validation genuinely requires network access, and document that exception.

Validate before writing the live env/config tree or restarting the service. Promote the same bytes that
passed; avoid overlay extraction that leaves deleted stale files behind. Enumerate every normal and
recovery writer and route all of them through the shared validator.

## 5. Review one executable plan

Generate a saved plan, inspect it with `terraform show`, and bind it to:

- the exact environment and backend/workspace;
- source and release-artifact identities;
- resource addresses and action scope;
- immutable helper/validator bytes;
- a digest shown to the human reviewer.

Apply that exact plan file. In saved-plan mode, Terraform treats passing the plan as approval and does
not prompt; if production requires a fresh explicit decision, implement it in the wrapper at the last
reversible point. Do not use target names or environment variables as proof of authorization.

## 6. Issue promotion evidence only after live verification

A zero exit from `terraform apply` proves only that Terraform completed its operation. Run required
environment-specific live verifiers next. Record the staging/promotion receipt only after they all pass,
and bind it to the saved-plan digest, exact source/artifact identities, verifier set, and timestamp.

Before production, freshly read the authoritative remote branch and prove the candidate commit belongs
to it; cached tracking refs are not provenance. After apply, independently read back deployed identity,
service health, and the real user path. Post-deploy checks remain necessary, but they are detection and
recovery evidence, not a substitute for the pre-mutation gate.

## 7. Validate external dependencies at their authority

Keep these checks in the project's canonical pre-deploy wrapper instead of trusting string shape:

- Resolve every hostname the candidate gateway serves and compare it with the environment's intended
  target. When DNS is Terraform-managed, inspect the planned/current provider record IDs too.
- Verify OAuth/OIDC issuer and callback identities against the authoritative application configuration,
  including already-initialized databases that no longer replay first-boot seed files.
- Verify the selected SSH key exists, has suitable permissions, and reaches the attested host identity;
  a path existing locally does not prove it is the key for that host.
- Verify credentials through the provider's read-only identity/status endpoint, then exercise the exact
  permission needed by the plan when that can be done without mutation.

Fail with the concrete mismatch and next action. Do not continue to apply merely to collect a more
expensive version of the same error.

## Primary contracts

- HashiCorp: provisioners are a last resort because their behavior is not predictably modeled:
  <https://developer.hashicorp.com/terraform/language/provisioners>
- HashiCorp: saved-plan apply executes the reviewed plan without another approval prompt:
  <https://developer.hashicorp.com/terraform/cli/commands/apply>
- HashiCorp: validation, preconditions, postconditions, and non-blocking checks run at different phases:
  <https://developer.hashicorp.com/terraform/language/validate>
- Docker: Compose interpolation precedence and effective environment:
  <https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/>
- Docker: `docker compose config` renders the actual engine model:
  <https://docs.docker.com/reference/cli/docker/compose/config/>
- Caddy: `caddy adapt --validate` is stronger than adaptation alone:
  <https://caddyserver.com/docs/command-line#caddy-adapt>

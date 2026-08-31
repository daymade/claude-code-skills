#!/usr/bin/env bash
set -euo pipefail

skill_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checklist="$skill_root/references/zero-to-deploy-checklist.md"
release_contract="$skill_root/references/release-safety-and-environment-parity.md"
predeploy="$skill_root/references/pre-deploy-validation.md"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

stale_claim='Command-line env vars do NOT override `.env` values for compose interpolation.'
if grep -RFn --include='*.md' -- "$stale_claim" "$skill_root"; then
  echo "ERROR: stale Docker Compose interpolation precedence claim remains" >&2
  exit 1
fi

grep -Fq 'Docker Compose interpolation gives the invoking shell higher precedence' "$checklist"
grep -Fq 'DOCKER_WITH_PROXY_MODE=disabled docker compose build myapp' "$checklist"
grep -Fq 'env -u DOCKER_WITH_PROXY_MODE' "$checklist"

if grep -Eq 'Production apply .*headless|GUI|interactive (apply|approval)|TTY.*approval' "$release_contract"; then
  echo "ERROR: release contract requires a host-specific interactive apply gate" >&2
  exit 1
fi
grep -Fq 'plan-bound production authorization/audit' "$release_contract"
grep -Fq 'the apply runner remains non-interactive and headless-compatible.' "$release_contract"

grep -Fq 'compose.rendered.json" > "$GATEWAY_ENV_FILE"' "$predeploy"
grep -Fq -- '--env-file "$GATEWAY_ENV_FILE"' "$predeploy"
grep -Fq '(.value | type == "string")' "$predeploy"
grep -Fq '.services[$service].image' "$predeploy"
grep -Fq '[ "$RENDERED_GATEWAY_IMAGE" = "$EXPECTED_CADDY_IMAGE_DIGEST" ]' "$predeploy"
grep -Fq 'test("\\$\\{[A-Za-z_][A-Za-z0-9_]*\\}")' "$predeploy"
grep -Fq 'REQUIRED_ENV_FILE="$CANDIDATE_ROOT/gateway/required-env.keys"' "$predeploy"
grep -Fq '[ -n "$required_value" ]' "$predeploy"
grep -Fq 'placeholder that references a different missing key' "$predeploy"
grep -Fq 'unresolved self- or foreign-key placeholder' "$release_contract"

# Execute the exact documented validator block. Static prose checks previously
# stayed green while the block omitted image parity and placeholder rejection.
awk '
  /^```bash$/ { in_bash = 1; next }
  in_bash && /^set -euo pipefail$/ { capture = 1 }
  capture && /^```$/ { exit }
  capture { print }
' "$predeploy" > "$tmp/documented-validator.sh"
test -s "$tmp/documented-validator.sh"

mkdir -p "$tmp/bin"
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "${DOCKER_CALL_LOG:?}"
EOF
chmod +x "$tmp/bin/docker"

image_a="ghcr.io/example/gateway@sha256:$(printf 'a%.0s' {1..64})"
image_b="ghcr.io/example/gateway@sha256:$(printf 'b%.0s' {1..64})"

write_fixture() {
  local root=$1 value=$2 image=$3
  mkdir -p "$root/gateway"
  printf '%s\n' MB_SITE_ADDRESS MB_COOKIE_TOKEN > "$root/gateway/required-env.keys"
  jq -n --arg value "$value" --arg image "$image" '{
    services: {
      "claude4dev-gateway": {
        image: $image,
        environment: {
          MB_SITE_ADDRESS: "example.invalid",
          MB_COOKIE_TOKEN: $value,
          OPTIONAL_NOTE: ""
        }
      }
    }
  }' > "$root/compose.rendered.json"
}

run_documented_validator() {
  local root=$1 expected_image=$2 log=$3
  CANDIDATE_ROOT="$root" \
  EXPECTED_CADDY_IMAGE_DIGEST="$expected_image" \
  DOCKER_CALL_LOG="$log" \
  PATH="$tmp/bin:$PATH" \
    bash "$tmp/documented-validator.sh"
}

write_fixture "$tmp/healthy" token-value "$image_a"
run_documented_validator "$tmp/healthy" "$image_a" "$tmp/healthy.docker"
grep -Fq -- '--env-file' "$tmp/healthy.docker"
grep -Fq -- "$image_a" "$tmp/healthy.docker"

write_fixture "$tmp/image-drift" token-value "$image_a"
if run_documented_validator "$tmp/image-drift" "$image_b" "$tmp/image-drift.docker" 2>/dev/null; then
  echo "ERROR: documented validator accepted a rendered image mismatch" >&2
  exit 1
fi
test ! -e "$tmp/image-drift.docker"

write_fixture "$tmp/foreign-placeholder" '${MISSING_OTHER}' "$image_a"
if run_documented_validator "$tmp/foreign-placeholder" "$image_a" "$tmp/foreign-placeholder.docker" 2>/dev/null; then
  echo "ERROR: documented validator accepted a foreign unresolved placeholder" >&2
  exit 1
fi
test ! -e "$tmp/foreign-placeholder.docker"

write_fixture "$tmp/required-empty" '' "$image_a"
if run_documented_validator "$tmp/required-empty" "$image_a" "$tmp/required-empty.docker" 2>/dev/null; then
  echo "ERROR: documented validator accepted an explicit-empty required value" >&2
  exit 1
fi
test ! -e "$tmp/required-empty.docker"

write_fixture "$tmp/required-missing" token-value "$image_a"
jq 'del(.services["claude4dev-gateway"].environment.MB_COOKIE_TOKEN)' \
  "$tmp/required-missing/compose.rendered.json" > "$tmp/required-missing/compose.rendered.next.json"
mv "$tmp/required-missing/compose.rendered.next.json" "$tmp/required-missing/compose.rendered.json"
if run_documented_validator "$tmp/required-missing" "$image_a" "$tmp/required-missing.docker" 2>/dev/null; then
  echo "ERROR: documented validator accepted a missing required value" >&2
  exit 1
fi
test ! -e "$tmp/required-missing.docker"

write_fixture "$tmp/required-duplicate" token-value "$image_a"
printf '%s\n' MB_COOKIE_TOKEN >> "$tmp/required-duplicate/gateway/required-env.keys"
if run_documented_validator "$tmp/required-duplicate" "$image_a" "$tmp/required-duplicate.docker" 2>/dev/null; then
  echo "ERROR: documented validator accepted a duplicate required key" >&2
  exit 1
fi
test ! -e "$tmp/required-duplicate.docker"

echo "Compose precedence and headless release documentation are internally consistent."

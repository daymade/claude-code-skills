#!/usr/bin/env bash
set -euo pipefail

skill_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checklist="$skill_root/references/zero-to-deploy-checklist.md"
release_contract="$skill_root/references/release-safety-and-environment-parity.md"
predeploy="$skill_root/references/pre-deploy-validation.md"

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
grep -Fq 'placeholder that references a different missing key' "$predeploy"
grep -Fq 'unresolved self- or foreign-key placeholder' "$release_contract"

echo "Compose precedence and headless release documentation are internally consistent."

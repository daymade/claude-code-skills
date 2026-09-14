# GHCR publishing

Use this reference only when the requested hosted state is a new tag or digest on an **existing**
Docker or OCI image package at `ghcr.io/NAMESPACE/PACKAGE:TAG`. The image namespace and package
are separate facts from a local image name and from the repository that builds it. GitHub
Container Registry can inherit repository permissions for a linked package or use
package-specific permissions; check the actual package before assuming either relationship.

This procedure implements the universal mutation contract in [`../SKILL.md`](../SKILL.md).
It adds GHCR-specific preflight and readback, without another approval gate for an already
authorized exact image write.

## Preflight before a long build

Freeze the exact image reference, expected source repository, target tag, expected package
visibility, and expected package/repository association. Then identify the active actor without
printing its token:

```bash
host='github.com'
repo='OWNER/REPO'
image='ghcr.io/NAMESPACE/PACKAGE:TAG'

gh auth status --active --hostname "$host"
GHCR_ACTOR=$(gh api --hostname "$host" user --jq '.login')
test -n "$GHCR_ACTOR"
gh repo view "$repo" --json nameWithOwner,visibility,isPrivate,viewerPermission,url
```

The resolved actor must have the repository permission required by its workflow. `write:packages`
is an account-level scope, not a package-path-scoped grant. The operation, credential source,
image reference, and post-write readback must enforce the narrower authorized target. Do not add
repository, organization, or delete scope to make a package failure disappear. Use the
authenticated account that owns the target namespace or has delegated package access. If a
separate GitHub CLI operation truly needs an interactive scope refresh, follow the browser/device
flow rule in [`../SKILL.md`](../SKILL.md); registry publication itself uses the protected
registry credential below.

GitHub documents a classic personal access token for GitHub Packages registry login. Obtain that
separate, already-authorized write credential through the operator's protected secret mechanism,
then prove its identity and its access to this target *before* the build. `GH_TOKEN` here only
passes the credential to `gh` for the command; it is neither printed nor persisted:

```bash
write_login=$(GH_TOKEN="$GHCR_WRITE_TOKEN" gh api --hostname "$host" user --jq '.login')
test "$write_login" = "$GHCR_ACTOR" || {
  printf 'GHCR write credential identity does not match the authorized actor\n' >&2
  exit 1
}

GH_TOKEN="$GHCR_WRITE_TOKEN" gh repo view "$repo" \
  --json nameWithOwner,visibility,isPrivate,viewerPermission,url
```

The `viewerPermission` readback must satisfy the requested repository workflow. Continue only
when the write credential resolves to the authorized actor and this exact repository is the
intended source.

For an existing package, read its real scope and repository association. Select the endpoint
that matches the namespace owner; a `404` can mean either a new package or no access, so it
does not prove creation is allowed:

```bash
# Personal namespace
GH_TOKEN="$GHCR_WRITE_TOKEN" gh api "user/packages/container/PACKAGE" \
  --jq '{name,package_type,visibility,repository:(.repository.full_name // null)}'

# Organization namespace
GH_TOKEN="$GHCR_WRITE_TOKEN" gh api "orgs/NAMESPACE/packages/container/PACKAGE" \
  --jq '{name,package_type,visibility,repository:(.repository.full_name // null)}'
```

The package must already exist. A `404` or a private personal package not exposed by this REST
endpoint is not evidence that creation is allowed: inspect the authenticated Package settings UI
to establish its visibility, linked repository, and package access, or stop. A package whose
repository association or visibility differs from the frozen target is a target/access mismatch,
not a build failure.

Package metadata does not expose an effective package-write permission for the current actor.
For a package with granular access, use its authenticated Package settings UI to verify that the
same `GHCR_ACTOR` has Write or Admin package access before the build. For a package inheriting
repository permissions, record that inheritance and use the same credential's `viewerPermission`
readback above. If neither route proves package write access, stop before the build; a registry
push is not a harmless permission probe.

GitHub's current documentation says Container Registry publication uses GitHub Packages
authentication and documents `write:packages` for upload; a linked package can inherit the
linked repository's access. Treat those as platform rules, then verify the live package and
repository above before a write. Sources: [GitHub Container Registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) and [GitHub CLI auth refresh manual](https://cli.github.com/manual/gh_auth_refresh).
The package API endpoints and their user/organization access limits are documented in
[GitHub's REST package endpoints](https://docs.github.com/en/rest/packages/packages).

## Authenticate and publish with an ephemeral Docker config

Use a separate, already-authorized write credential delivered through the operator's protected
secret mechanism. GitHub documents a classic personal access token for GitHub Packages; do not
copy a value from `gh auth token`, a remote deployment host, shell history, or another user's
credential store. The variable names below are placeholders and the commands never echo them.

```bash
docker_config=$(mktemp -d)
metadata_file=$(mktemp)
cleanup_ghcr() {
  docker --config "$docker_config" logout ghcr.io >/dev/null 2>&1 || true
  rm -rf "$docker_config"
  rm -f "$metadata_file"
}
trap cleanup_ghcr EXIT HUP INT TERM

printf '%s' "$GHCR_WRITE_TOKEN" \
  | docker --config "$docker_config" login ghcr.io \
      --username "$GHCR_ACTOR" --password-stdin

docker buildx build --platform linux/amd64 \
  --metadata-file "$metadata_file" \
  --tag "$image" --push .
```

Set `--platform`, build context, tags, and build arguments only from the authorized image plan;
they are examples, not defaults. Do not write a credential into the project Docker config,
Dockerfile, image layer, build argument, or CI log. The trap removes the temporary Docker
configuration on success, failure, and interruption.

## Verify the published digest independently

The push receipt and local tag do not prove that GHCR now serves the intended image. Capture the
immutable digest emitted by the build, fetch the remote manifest using the exact digest through
the same temporary Docker configuration, and compare it with the tag resolution:

```bash
image_repo='ghcr.io/NAMESPACE/PACKAGE'
published_digest=$(jq -er '."containerimage.digest"' "$metadata_file")
digest_readback=$(docker --config "$docker_config" buildx imagetools inspect \
  --format '{{.Digest}}' "${image_repo}@${published_digest}")
tag_readback=$(docker --config "$docker_config" buildx imagetools inspect \
  --format '{{.Digest}}' "$image")
test "$digest_readback" = "$published_digest"
test "$tag_readback" = "$published_digest"
```

Finally, read package metadata through the matching GitHub API endpoint above. Report the exact
image reference and observed digest, package/repository association, and whether temporary
Docker credentials were cleaned up. If a tag moves between the build result and readback, report
the mismatch as a concurrent target change; do not retag or repush automatically.

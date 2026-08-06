# Docker Deep Analysis

Detailed Docker analysis workflow referenced from `SKILL.md` Step 2. Use this when development-environment cleanup involves Docker images, containers, volumes, or build cache.

## Step 2A: Docker Deep Analysis

Use agent team to analyze Docker resources in parallel for comprehensive coverage:

**Agent 1 — Images**:
```bash
# List all images sorted by size
docker images --format "table {{.ID}}\t{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" | sort -k3 -h -r

# Identify dangling images (no tag)
docker images -f "dangling=true" --format "{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"

# For each image, check if any container references it
docker ps -a --filter "ancestor=<IMAGE_ID>" --format "{{.Names}}\t{{.Status}}"
```

**Agent 2 — Containers and Volumes**:
```bash
# All containers with status
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}"

# All volumes with size
docker system df -v | grep -A 1000 "VOLUME NAME"

# Identify dangling volumes
docker volume ls -f dangling=true

# For each volume, check which container uses it
docker ps -a --filter "volume=<VOLUME_NAME>" --format "{{.Names}}"
```

**Agent 3 — System Level**:
```bash
# Docker disk usage summary
docker system df

# Build cache
docker builder du

# Container logs size
for c in $(docker ps -a --format "{{.Names}}"); do
  echo "$c: $(docker inspect --format='{{.LogPath}}' $c | xargs ls -lh 2>/dev/null | awk '{print $5}')"
done
```

**Version Management Awareness**: Identify version-managed images (e.g., Supabase managed by CLI). When newer versions are confirmed running, older versions are safe to remove. Pay attention to Docker Compose naming conventions (dash vs underscore).

## Step 2B: OrbStack-Specific Analysis

OrbStack users have additional considerations.

**data.img.raw is a Sparse File**:
```bash
# Logical size (can show 8TB+, meaningless)
ls -lh ~/Library/OrbStack/data/data.img.raw

# Actual disk usage (this is what matters)
du -h ~/Library/OrbStack/data/data.img.raw
```

The logical vs actual size difference is normal. Only actual usage counts.

**Post-Cleanup: Reclaim Disk Space**: After cleaning Docker objects inside OrbStack, `data.img.raw` does NOT shrink automatically. Instruct user: Open OrbStack Settings → "Reclaim disk space" to compact the sparse file.

**OrbStack Logs**: Typically 1-2 MB total (`~/Library/OrbStack/log/`). Not worth cleaning.

**Verifying which subdirectory drives real VM disk usage**: `du -h data.img.raw` on the macOS side gives an accurate top-level number. To see *which subdirectory inside the VM* is driving it (overlay2 vs volumes vs containers), a read-only bind mount reaches the real VM filesystem directly — no elevated privileges needed:

```bash
docker run --rm -v /var/lib/docker:/x:ro alpine sh -c "df -h /x; du -d 1 -h /x"
```

`/var/lib/docker` is inside the Docker Engine's own Linux VM (where `dockerd` runs on OrbStack), so this stays entirely within the VM — no macOS↔VM boundary to cross. It reports the real block device (typically `/dev/vdb1`) and real per-subdirectory sizes; verified to match a `--privileged --pid=host nsenter` approach byte-for-byte in testing, so prefer this unprivileged form. There's no verified reason to reach for `--privileged` for this check.

**BusyBox `du` uses `-d N`, not GNU's `--max-depth=N`** — the alpine image ships BusyBox coreutils, and the GNU-style flag errors with "unrecognized option: max-depth=1". `du -d 1`'s total will typically sum *higher* than `df`'s real "Used" figure (measured: `du` summed 170.6G against `df`'s 152.7G Used, same machine, same moment) because it double-counts `overlay2` layers shared across images. Trust `df`'s Used column for the true total; use `du -d 1` only for relative proportions between subdirectories, never as an absolute number.

## Step 2C: Double-Check Verification Protocol

Before deleting ANY Docker object, perform independent verification.

**On a machine with active development, the object list is live data.** `docker system df` and `docker images` can report different totals minutes apart if a build is running in the background (a CI job, another terminal's `docker compose build`, an IDE task). If time passed between the dry-run analysis and user confirmation, re-run the listing query fresh before executing — don't reuse the dry-run's cached list. A deletion plan built from a stale snapshot can delete an image that started being used since, or skip one that became safe to delete since. Re-pulling costs one command.

**For Images**:
```bash
# Verify no container (running or stopped) references the image
docker ps -a --filter "ancestor=<IMAGE_ID>" --format "{{.Names}}\t{{.Status}}"

# If empty → safe to delete with: docker rmi <IMAGE_ID>
```

**For Volumes**:
```bash
# Verify no container mounts the volume
docker ps -a --filter "volume=<VOLUME_NAME>" --format "{{.Names}}"

# If empty → check if database volume (see below)
# If not database → safe to delete with: docker volume rm <VOLUME_NAME>
```

**Database Volume Red Flag Rule**: If volume name contains mysql, postgres, redis, mongo, or mariadb, MANDATORY content inspection:
```bash
# Inspect database volume contents with temporary container
docker run --rm -v <VOLUME_NAME>:/data alpine ls -la /data
docker run --rm -v <VOLUME_NAME>:/data alpine du -sh /data/*
```

Only delete after user confirms the data is not needed.

**This rule also applies to anonymous volumes with no name to match against.** Heavy container churn (a service rerun often, an interactive dev loop) accumulates hundreds of anonymous volumes — 64-character hex names, no way to tell what's inside from the name alone. "Not referenced by any current container" is tempting to treat as sufficient evidence they're safe to remove. It isn't: a real inspection of 10 randomly sampled anonymous volumes found 5 of the 10 were live PostgreSQL data directories (`pg_wal`, `global/pg_control`, ~49MB each) — orphaned by containers whose lifecycle had ended, data still intact. "No container references it" and "the data is worthless" are unrelated facts; only content inspection tells you the second one.

Checking the whole population is cheap for Claude Code executing a loop, so script it rather than sampling and extrapolating:

```bash
for v in $(docker volume ls -qf dangling=true); do
  n=$(docker run --rm -v "$v":/data alpine find /data -type f 2>/dev/null | wc -l)
  [ "$n" -gt 0 ] && echo "$v: $n files"
done
```

Any volume the loop reports non-empty goes through the full Database Volume Red Flag inspection above before deletion — do not delete based on the sample-and-extrapolate shortcut this rule exists to warn against.

## Step 2D: Root-Cause Fix — Stop the Source, Not Just the Symptom

Everything above cleans up an existing backlog. When a Docker resource type keeps growing **across sessions** — not a one-time accumulation from unmanaged use, but the same category refilling every time you check — a cleanup pass alone is a symptom fix. It will be full again next week.

**The tell**: group images by repository (`docker images --format "{{.Repository}}" | sort | uniq -c | sort -rn`). A single repository with hundreds of tags and only one or two active containers is not organic accumulation — it's a build pipeline tagging a new image every run and never cleaning up the old ones. Common in CI/CD scripts, `docker compose build` steps in a dev-loop Makefile target, or any workflow baking a commit SHA or timestamp into the image tag.

**Diagnose the source:**
1. Confirm the pattern: does the tag naming look programmatic (commit hash, build ID, timestamp)? That's the signature of an automated build, not manual `docker build` runs.
2. Find what produces it: grep the project for the tag-naming pattern to locate the script, Makefile target, or CI config that builds that repository.
3. Check whether cleanup logic already exists nearby but was never wired in — a `down`/`stop` command that deliberately preserves images (e.g. to keep the last-known-good build) is correct by design; it just means retention belongs at the *build* step instead.
4. **Confirm this repository is only consumed locally** before proposing an automated fix. Step 2 tells you where images are *produced*, not where they're *consumed* — if the pipeline pushes to a registry that other machines or a CI/CD cluster pull from, a local `docker ps -a` check is blind to those remote consumers, and an image judged "safe to delete" locally may still be in active use elsewhere. This approach fits locally-built, locally-consumed repositories (a dev-loop `local-uat`-style target is the common case); a registry-backed multi-host pipeline needs registry-side retention, a different mechanism than what follows.

**Writing the fix needs the same user confirmation as every other deletion in this document — the difference is *when* you ask.** Every other deletion here is confirmed per-item, at the moment it happens, with a human present. Retention logic wired into a build script runs unattended *every future time the build succeeds*, so the confirmation has to move earlier: **get the user's explicit sign-off on adding this automated deletion logic before writing or committing it**, the same way you'd never `rm -rf` a directory without asking first. This isn't satisfied by avoiding prune-family commands — Core Principle 1 ("no shortcuts, no workarounds") and Principle 9 ("do NOT auto-execute cleanup") are both about *unattended* deletion, not which Docker subcommand runs. Recommend a dry-run/log-only mode for a few runs before enabling real deletion.

**Once approved, this is still precision deletion — just automated and scoped to one repository:**
- Add retention logic that runs **after** the new build succeeds and any health check passes — never before. A failed new build shouldn't cost the last-known-good image.
- Keep the N most recent images by **verified creation time** (`docker image inspect --format '{{.Created}}'`), not the human-readable `CreatedSince` string (imprecise, not sortable) or raw `docker image ls` ordering (not guaranteed time-sorted). **Caveat**: reproducible-build tooling (Bazel, Nix, some BuildKit configs) can pin `.Created` to a fixed value like `SOURCE_DATE_EPOCH` instead of the real build time, so a fresh image can sort as "older" than genuinely older ones. If the project's tooling does this, cross-check against the next bullet before trusting the sort.
- Before removing each candidate, verify no container — including stopped ones — references it (`docker ps -a --filter "ancestor=<IMAGE_ID>"`), the same Step 2C protocol running inside the application's automation. This also covers the reproducible-build caveat: exclude whatever image the just-started container is using, independent of its timestamp.
- Never call this with a prune-family command. Still one `docker rmi <ID>` per verified-safe image, scoped to one repository — automation just means unattended instead of a human typing the ID.
- Wrap the retention step so its own failure doesn't fail the surrounding build/deploy. Verify the exact failure signal your subprocess-execution mechanism actually returns rather than assuming a field name — a wrong assumption there silently turns the failure branch into a no-op.

**Then clean the existing backlog** using the Step 2C workflow — the backlog is one-time debt, the source fix stops new debt from accumulating. Fix the source first if practical, then clear the backlog.

## Bonus: Dockerfile Optimization Discoveries

During image analysis, if you discover oversized images, suggest multi-stage build optimization:

```dockerfile
# Before: 884 MB (full build environment in final image)
FROM node:20
COPY . .
RUN npm ci && npm run build
CMD ["node", "dist/index.js"]

# After: ~150 MB (only runtime in final image)
FROM node:20 AS builder
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
CMD ["node", "dist/index.js"]
```

Key techniques: multi-stage builds, slim/alpine base images, `.dockerignore`, layer ordering.

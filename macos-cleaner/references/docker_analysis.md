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

## Step 2C: Double-Check Verification Protocol

Before deleting ANY Docker object, perform independent verification.

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

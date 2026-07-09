#!/usr/bin/env bash
# Competitor repository management template.
# Copy this file into a product repo or ops directory, then set PRODUCT_NAME and
# optionally fill the COMPETITORS map below.

set -euo pipefail

# Durable competitor workspace. Override per run if needed:
#   COMPETITORS_BASE="$HOME/workspace/competitors" PRODUCT_NAME=my-product ./update-competitors.sh status
COMPETITORS_BASE="${COMPETITORS_BASE:-$HOME/workspace/competitors}"
PRODUCT_NAME="${PRODUCT_NAME:-your-product-name}"
COMPETITORS_DIR="$COMPETITORS_BASE/$PRODUCT_NAME"
PREFER_SSH="${PREFER_SSH:-1}"

# Persistent competitors for this product. Values can be SSH or HTTPS URLs.
declare -A COMPETITORS=(
    # ["owner-repo"]="<git-ssh-url-or-https-url>"
)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

require_product_name() {
    if [[ "$PRODUCT_NAME" == "your-product-name" || -z "$PRODUCT_NAME" ]]; then
        echo -e "${RED}Set PRODUCT_NAME first.${NC}" >&2
        echo "Example: PRODUCT_NAME=claude-flow-viewer $0 status" >&2
        exit 1
    fi
}

repo_name_from_url() {
    local repo_url="$1"
    local path_part
    local github_user="git"
    local github_host="github.com"
    local github_scp_prefix="${github_user}@${github_host}:"

    path_part="$repo_url"
    path_part="${path_part#$github_scp_prefix}"
    path_part="$(printf '%s\n' "$path_part" \
        | sed -E 's#^https://github.com/##; s#/$##; s#\.git$##')"

    if [[ "$path_part" == */* ]]; then
        printf '%s\n' "${path_part//\//-}"
    else
        basename "$path_part"
    fi
}

ssh_url_for_github() {
    local repo_url="$1"
    local path_part
    local github_user="git"
    local github_host="github.com"

    if [[ "$PREFER_SSH" != "1" ]]; then
        printf '%s\n' "$repo_url"
        return
    fi

    if [[ "$repo_url" == https://github.com/* ]]; then
        path_part="$(printf '%s\n' "$repo_url" \
            | sed -E 's#^https://github.com/##; s#/$##; s#\.git$##')"
        printf '%s@%s:%s.git\n' "$github_user" "$github_host" "$path_part"
    else
        printf '%s\n' "$repo_url"
    fi
}

clone_one() {
    local target_name="$1"
    local repo_url="$2"
    local clone_url
    local target_dir
    local attempt

    mkdir -p "$COMPETITORS_DIR"
    target_dir="$COMPETITORS_DIR/$target_name"
    clone_url="$(ssh_url_for_github "$repo_url")"

    if [[ -d "$target_dir/.git" ]]; then
        echo -e "${YELLOW}[exists] $target_name${NC}"
        git -C "$target_dir" remote -v | sed 's/^/  /'
        return
    fi

    echo -e "${GREEN}[clone] $target_name${NC}"
    for attempt in 1 2 3; do
        if git clone --depth 1 "$clone_url" "$target_dir"; then
            return
        fi

        echo "  retry $attempt/3..."
        sleep 2
    done

    if [[ "$clone_url" != "$repo_url" ]]; then
        echo -e "${YELLOW}  SSH failed; trying original URL${NC}"
        git clone --depth 1 "$repo_url" "$target_dir"
    fi
}

clone_known() {
    require_product_name

    if [[ "${#COMPETITORS[@]}" -eq 0 ]]; then
        echo -e "${YELLOW}No persistent competitors configured in COMPETITORS.${NC}"
        echo "Use: PRODUCT_NAME=$PRODUCT_NAME $0 clone-url https://github.com/owner/repo"
        return
    fi

    for target_name in "${!COMPETITORS[@]}"; do
        clone_one "$target_name" "${COMPETITORS[$target_name]}"
    done
}

clone_url() {
    require_product_name

    local repo_url="${1:-}"
    local target_name="${2:-}"

    if [[ -z "$repo_url" ]]; then
        echo -e "${RED}Usage: $0 clone-url <repo-url> [target-name]${NC}" >&2
        exit 1
    fi

    if [[ -z "$target_name" ]]; then
        target_name="$(repo_name_from_url "$repo_url")"
    fi

    clone_one "$target_name" "$repo_url"
}

discover_repos() {
    local query="${1:-}"
    local limit="${2:-30}"

    if [[ -z "$query" ]]; then
        echo -e "${RED}Usage: $0 discover <query> [limit]${NC}" >&2
        exit 1
    fi

    if ! command -v gh >/dev/null 2>&1; then
        echo -e "${RED}gh CLI is required for discover mode.${NC}" >&2
        exit 1
    fi

    gh search repos "$query" \
        --limit "$limit" \
        --archived=false \
        --json fullName,url,description,stargazersCount,forksCount,openIssuesCount,language,pushedAt,updatedAt,defaultBranch \
        --template '{{range .}}{{printf "%-45s  stars=%-6v forks=%-5v issues=%-5v lang=%-12v pushed=%s\n  %s\n  %s\n\n" .fullName .stargazersCount .forksCount .openIssuesCount .language .pushedAt .url .description}}{{end}}'
}

repo_dirs() {
    if [[ ! -d "$COMPETITORS_DIR" ]]; then
        return
    fi

    find "$COMPETITORS_DIR" -mindepth 1 -maxdepth 1 -type d -print | sort
}

pull_repos() {
    require_product_name

    local target_dir
    local repo_name

    while IFS= read -r target_dir; do
        [[ -d "$target_dir/.git" ]] || continue
        repo_name="$(basename "$target_dir")"
        echo -e "${GREEN}[update] $repo_name${NC}"
        git -C "$target_dir" fetch --all --prune
        git -C "$target_dir" pull --ff-only || echo -e "${YELLOW}  pull skipped: local divergence or no upstream${NC}"
    done < <(repo_dirs)
}

status_repos() {
    require_product_name

    local target_dir
    local repo_name
    local branch
    local upstream
    local behind
    local commit
    local remote

    if [[ ! -d "$COMPETITORS_DIR" ]]; then
        echo -e "${YELLOW}No directory yet: $COMPETITORS_DIR${NC}"
        return
    fi

    while IFS= read -r target_dir; do
        [[ -d "$target_dir/.git" ]] || continue
        repo_name="$(basename "$target_dir")"
        branch="$(git -C "$target_dir" branch --show-current 2>/dev/null || true)"
        upstream="$(git -C "$target_dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
        commit="$(git -C "$target_dir" log -1 --format='%h %cI %s' 2>/dev/null || true)"
        remote="$(git -C "$target_dir" remote get-url origin 2>/dev/null || true)"

        if [[ -n "$upstream" ]]; then
            behind="$(git -C "$target_dir" rev-list --count "HEAD..$upstream" 2>/dev/null || echo "?")"
        else
            behind="no-upstream"
        fi

        echo -e "${GREEN}$repo_name${NC}"
        echo "  path:   $target_dir"
        echo "  remote: $remote"
        echo "  branch: ${branch:-detached}"
        echo "  latest: $commit"
        echo "  behind: $behind"
        echo
    done < <(repo_dirs)
}

show_help() {
    cat <<EOF
Competitor repository manager - $PRODUCT_NAME

Usage:
  PRODUCT_NAME=<product> $0 discover <query> [limit]
  PRODUCT_NAME=<product> $0 clone-url <repo-url> [target-name]
  PRODUCT_NAME=<product> $0 clone
  PRODUCT_NAME=<product> $0 pull
  PRODUCT_NAME=<product> $0 status

Environment:
  COMPETITORS_BASE  Base directory (default: $HOME/workspace/competitors)
  PRODUCT_NAME      Product group directory under COMPETITORS_BASE
  PREFER_SSH        Convert GitHub HTTPS URLs to SSH clone URLs (default: 1)

Directory:
  $COMPETITORS_BASE/
  └── $PRODUCT_NAME/
      ├── owner-repo/
      └── ...
EOF
}

case "${1:-help}" in
    discover)
        shift
        discover_repos "$@"
        ;;
    clone-url)
        shift
        clone_url "$@"
        ;;
    clone)
        clone_known
        ;;
    pull)
        pull_repos
        ;;
    status)
        status_repos
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}" >&2
        show_help
        exit 1
        ;;
esac

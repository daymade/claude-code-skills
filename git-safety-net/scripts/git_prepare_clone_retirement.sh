#!/usr/bin/env bash
# git_prepare_clone_retirement.sh — freeze an independent clone before retirement.
#
# The script never moves or deletes a checkout and never changes repository refs.
# It refuses to certify a clone that still has working-tree bytes, ignored files,
# stashes, reflog-only commits, clone-only unreachable objects, linked worktrees,
# local submodule repositories, partial/promisor clones, known extension object
# stores, or tracked content filters. Repository fsmonitor commands are disabled.
# A successful run
# writes a private recovery directory containing:
#   all-refs.bundle       self-contained history for every current ref
#   refs.manifest         exact ref tips frozen before the bundle
#   symrefs.manifest      exact symbolic-ref name -> target topology
#   reflog-oids.manifest  every commit identity named by a reflog
#   metadata.manifest     types, modes, and hashes for config/hooks/info
#   repo-metadata.tar     exact config/hooks/info payload
#   receipt.txt           source/survivor identity and bundle digest
#
# Usage:
#   git_prepare_clone_retirement.sh \
#     --clone <independent-clone> --survivor <kept-checkout> --out <new-backup-dir>
#   git_prepare_clone_retirement.sh --verify-current <backup-dir>
#
# `--verify-current` is the final compare-and-swap gate. Freeze an absent no-clobber
# quarantine destination, run process occupancy by itself, then run this command.
# After success, the move must be the next operation with no intervening probe.

set -euo pipefail
umask 077
export GIT_OPTIONAL_LOCKS=0
export GIT_NO_LAZY_FETCH=1

safe_git() {
  command git --no-pager \
    -c core.fsmonitor=false \
    -c core.untrackedCache=false \
    -c status.submoduleSummary=false \
    "$@"
}

die() { echo "error: $*" >&2; exit 2; }
unsafe() { echo "$1${2:+: $2}" >&2; exit 1; }

usage() {
  sed -n '2,/^$/s/^# \{0,1\}//p' "$0"
}

canonical_dir() {
  (cd "$1" 2>/dev/null && pwd -P)
}

normalize_remote() {
  printf '%s' "${1:-}" | sed -E \
    's#^[a-z+]+://##; s#^[^@/]+@##; s#:#/#; s#\.git/?$##; s#/+$##'
}

absolute_git_dir() {
  safe_git -C "$1" rev-parse --absolute-git-dir 2>/dev/null
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "need sha256sum or shasum to fingerprint the recovery bundle"
  fi
}

file_mode() {
  local mode
  if mode="$(stat -f '%Lp' "$1" 2>/dev/null)"; then
    printf '%s' "$mode"
  elif mode="$(stat -c '%a' "$1" 2>/dev/null)"; then
    printf '%s' "$mode"
  else
    die "cannot read file mode: $1"
  fi
}

list_refs() {
  safe_git -C "$1" for-each-ref --format='%(objectname) %(refname)' | LC_ALL=C sort
}

list_symbolic_refs() {
  local checkout="$1"
  local head_target

  {
    head_target="$(safe_git -C "$checkout" symbolic-ref -q HEAD 2>/dev/null || true)"
    [ -z "$head_target" ] || printf 'HEAD %s\n' "$head_target"
    safe_git -C "$checkout" for-each-ref --format='%(refname) %(symref)' |
      awk 'NF == 2 { print $1, $2 }'
  } | LC_ALL=C sort -u
}

list_bundle_expected_heads() {
  local checkout="$1"
  {
    safe_git -C "$checkout" rev-parse HEAD | awk '{print $1 " HEAD"}'
    list_refs "$checkout"
  } | LC_ALL=C sort
}

list_reflog_oids() {
  safe_git -C "$1" reflog --all --format='%H' 2>/dev/null | LC_ALL=C sort -u
}

metadata_manifest() {
  local checkout="$1"
  local git_dir rel_path object_id link_target entry mode
  local escaped_path escaped_target

  git_dir="$(absolute_git_dir "$checkout")" || return 1
  emit_metadata_entry() {
    rel_path="${entry#"$git_dir"/}"
    printf -v escaped_path '%q' "$rel_path"
    mode="$(file_mode "$entry")"
    if [ -L "$entry" ]; then
      link_target="$(readlink "$entry")" || return 1
      printf -v escaped_target '%q' "$link_target"
      printf '%s|symlink|%s|%s\n' "$escaped_path" "$mode" "$escaped_target"
    elif [ -f "$entry" ]; then
      object_id="$(safe_git -C "$checkout" hash-object --no-filters -- "$entry")" || return 1
      printf '%s|file|%s|%s\n' "$escaped_path" "$mode" "$object_id"
    elif [ -d "$entry" ]; then
      printf '%s|directory|%s|-\n' "$escaped_path" "$mode"
    fi
  }

  {
    for entry in config config.worktree hooks info; do
      entry="$git_dir/$entry"
      if [ -e "$entry" ] || [ -L "$entry" ]; then
        emit_metadata_entry
        if [ -d "$entry" ] && [ ! -L "$entry" ]; then
          while IFS= read -r -d '' entry; do
            emit_metadata_entry
          done < <(find "$entry" -mindepth 1 \
            \( -type f -o -type d -o -type l \) -print0)
        fi
      fi
    done
  } | LC_ALL=C sort
}

check_metadata_scope() {
  local clone="$1"
  local git_dir config_file config_keys lowered_key symlink_path

  git_dir="$(absolute_git_dir "$clone")" || return 1
  for config_file in "$git_dir/config" "$git_dir/config.worktree"; do
    [ -e "$config_file" ] || continue
    config_keys="$(safe_git config --file "$config_file" --no-includes --name-only --list)" || \
      unsafe "LOCAL_CONFIG_UNREADABLE" "$config_file"
    while IFS= read -r lowered_key; do
      [ -n "$lowered_key" ] || continue
      case "$lowered_key" in
        include.path|includeif.*.path)
          unsafe "LOCAL_CONFIG_INCLUDE" \
            "$config_file contains $lowered_key; flatten or separately preserve its resolved config before retirement"
          ;;
        core.hookspath)
          unsafe "LOCAL_HOOKS_PATH" \
            "$config_file sets core.hooksPath; separately preserve and remove the local override before retirement"
          ;;
      esac
    done < <(printf '%s\n' "$config_keys" | LC_ALL=C tr '[:upper:]' '[:lower:]')
  done

  while IFS= read -r -d '' symlink_path; do
    unsafe "SYMLINKED_REPOSITORY_METADATA" \
      "$symlink_path may target bytes outside the recovery archive"
  done < <(find "$git_dir/config" "$git_dir/config.worktree" "$git_dir/hooks" "$git_dir/info" \
    -type l -print0 2>/dev/null)
}

check_no_linked_worktrees() {
  local clone="$1"
  local worktrees count

  worktrees="$(safe_git -C "$clone" worktree list --porcelain)" || \
    unsafe "WORKTREE_INVENTORY_UNREADABLE" "$clone"
  count="$(printf '%s\n' "$worktrees" | awk '$1 == "worktree" { count++ } END { print count + 0 }')"
  if [ "$count" -gt 1 ]; then
    printf '%s\n' "$worktrees" | awk '$1 == "worktree" { print $0 }' >&2
    unsafe "LINKED_WORKTREES_PRESENT" \
      "audit and retire every linked worktree before retiring its primary clone"
  fi
}

check_no_submodule_repositories() {
  local clone="$1"
  local git_dir submodules line

  git_dir="$(absolute_git_dir "$clone")" || return 1
  if [ -d "$git_dir/modules" ] && \
    find "$git_dir/modules" -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
    unsafe "SUBMODULE_REPOSITORIES_PRESENT" \
      "$git_dir/modules contains separate repositories; audit them independently before retirement"
  fi

  if ! submodules="$(safe_git -C "$clone" submodule status --recursive 2>&1)"; then
    unsafe "SUBMODULE_INVENTORY_UNREADABLE" "$submodules"
  fi
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    case "$line" in
      -*) ;;
      *)
        printf '%s\n' "$line" >&2
        unsafe "SUBMODULE_REPOSITORIES_PRESENT" \
          "audit every initialized submodule as an independent repository before retirement"
        ;;
    esac
  done < <(printf '%s\n' "$submodules")
}

check_no_promisor_clone() {
  local clone="$1"
  local git_dir promisor_config key value lowered_value

  git_dir="$(absolute_git_dir "$clone")" || return 1
  promisor_config="$(safe_git -C "$clone" config --local --no-includes --get-regexp \
    '^(extensions\.partialClone|remote\..*\.(promisor|partialclonefilter))$' 2>/dev/null || true)"
  while IFS=' ' read -r key value; do
    [ -n "$key" ] || continue
    case "$key" in
      extensions.partialClone|remote.*.partialclonefilter)
        unsafe "PROMISOR_CLONE" \
          "$key is configured; hydrate and convert the clone under a separate workflow"
        ;;
      remote.*.promisor)
        lowered_value="$(printf '%s' "$value" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
        case "$lowered_value" in
          true|yes|on|1)
            unsafe "PROMISOR_CLONE" \
              "$key=$value; lazy object hydration is outside this non-destructive helper"
            ;;
        esac
        ;;
    esac
  done < <(printf '%s\n' "$promisor_config")

  if [ -d "$git_dir/objects/pack" ] && \
    find "$git_dir/objects/pack" -type f -name '*.promisor' -print -quit |
      grep -q .; then
    unsafe "PROMISOR_CLONE" \
      "$git_dir/objects/pack contains promisor packs; lazy fetching is disabled"
  fi
}

check_no_extension_object_stores() {
  local clone="$1"
  local git_dir store

  git_dir="$(absolute_git_dir "$clone")" || return 1
  for store in "$git_dir/lfs/objects" "$git_dir/annex/objects"; do
    if [ -L "$store" ]; then
      unsafe "EXTENSION_OBJECT_STORE" \
        "$store is a symlink; audit the extension-managed object store separately"
    fi
    if [ -d "$store" ] && find "$store" -mindepth 1 -print -quit | grep -q .; then
      unsafe "EXTENSION_OBJECT_STORE" \
        "$store contains clone-private objects that a Git bundle does not preserve"
    fi
  done
}

check_no_tracked_content_filters() {
  local clone="$1"
  local path _attribute value

  safe_git -C "$clone" ls-files -z >/dev/null || \
    unsafe "TRACKED_PATH_INVENTORY_UNREADABLE" "$clone"
  safe_git -C "$clone" check-attr -z --stdin filter </dev/null >/dev/null || \
    unsafe "ATTRIBUTE_INVENTORY_UNREADABLE" "$clone"
  while IFS= read -r -d '' path && \
    IFS= read -r -d '' _attribute && \
    IFS= read -r -d '' value; do
    case "$value" in
      ''|unspecified|unset) ;;
      *)
        unsafe "TRACKED_CONTENT_FILTER" \
          "$path has filter=$value; audit that external content pipeline separately"
        ;;
    esac
  done < <(safe_git -C "$clone" ls-files -z | \
    safe_git -C "$clone" check-attr -z --stdin filter)
}

check_identity() {
  local clone="$1"
  local survivor="$2"
  local clone_remote survivor_remote clone_head survivor_head

  [ "$clone" != "$survivor" ] || die "clone and survivor resolve to the same checkout"
  [ -d "$clone/.git" ] || die "--clone must name an independent clone with a .git directory"
  safe_git -C "$clone" rev-parse --git-dir >/dev/null 2>&1 || die "clone is not a Git repository: $clone"
  safe_git -C "$survivor" rev-parse --git-dir >/dev/null 2>&1 || die "survivor is not a Git repository: $survivor"

  clone_remote="$(normalize_remote "$(safe_git -C "$clone" remote get-url origin 2>/dev/null | head -1 || true)")"
  survivor_remote="$(normalize_remote "$(safe_git -C "$survivor" remote get-url origin 2>/dev/null | head -1 || true)")"
  if [ -n "$clone_remote" ] && [ -n "$survivor_remote" ] && [ "$clone_remote" = "$survivor_remote" ]; then
    echo remote
    return 0
  fi

  clone_head="$(safe_git -C "$clone" rev-parse --verify HEAD 2>/dev/null || true)"
  survivor_head="$(safe_git -C "$survivor" rev-parse --verify HEAD 2>/dev/null || true)"
  if [ -n "$clone_head" ] && safe_git -C "$survivor" cat-file -e "${clone_head}^{commit}" 2>/dev/null; then
    echo shared-history
    return 0
  fi
  if [ -n "$survivor_head" ] && safe_git -C "$clone" cat-file -e "${survivor_head}^{commit}" 2>/dev/null; then
    echo shared-history
    return 0
  fi
  die "clone and survivor do not share a verified remote or commit history"
}

check_physical_state() {
  local clone="$1"
  local normal_state physical_state stash_state

  normal_state="$(safe_git -C "$clone" status --porcelain=v1 --untracked-files=all)" || \
    unsafe "STATUS_UNREADABLE" "$clone"
  [ -z "$normal_state" ] || {
    printf '%s\n' "$normal_state" >&2
    unsafe "UNTRACKED_OR_MODIFIED" "copy or commit every listed path before retirement"
  }

  physical_state="$(safe_git -C "$clone" status --porcelain=v1 --ignored --untracked-files=all)" || \
    unsafe "IGNORED_STATUS_UNREADABLE" "$clone"
  [ -z "$physical_state" ] || {
    printf '%s\n' "$physical_state" >&2
    unsafe "IGNORED_PHYSICAL_FILES" "classify and copy uncertain ignored bytes before retirement"
  }

  stash_state="$(safe_git -C "$clone" stash list --format='%gd|%H|%gs')" || \
    unsafe "STASH_STATUS_UNREADABLE" "$clone"
  [ -z "$stash_state" ] || {
    printf '%s\n' "$stash_state" >&2
    unsafe "STASHES_PRESENT" "export and classify every stash before retirement"
  }
}

check_reflog_coverage() {
  local clone="$1"
  local oid containing_ref

  while IFS= read -r oid; do
    [ -n "$oid" ] || continue
    safe_git -C "$clone" cat-file -e "${oid}^{commit}" 2>/dev/null || \
      unsafe "REFLOG_OBJECT_MISSING" "$oid"
    containing_ref="$(safe_git -C "$clone" for-each-ref --contains "$oid" --format='%(refname)' | head -1 || true)"
    [ -n "$containing_ref" ] || \
      unsafe "REFLOG_ONLY_COMMIT" "$oid has no current ref; pin it before bundling"
  done < <(list_reflog_oids "$clone")
}

check_clone_owned_unreachable_objects() {
  local clone="$1"
  local survivor="$2"
  local fsck_output object_type oid missing

  if ! fsck_output="$(safe_git -C "$clone" fsck --no-reflogs --unreachable --no-progress 2>&1)"; then
    unsafe "FSCK_FAILED" "$fsck_output"
  fi
  missing=""
  while IFS=' ' read -r object_type oid; do
    [ -n "$object_type" ] || continue
    [ -n "$oid" ] || continue
    if ! safe_git -C "$survivor" cat-file -e "$oid" 2>/dev/null; then
      missing="${missing}${object_type} ${oid}"$'\n'
    fi
  done < <(printf '%s\n' "$fsck_output" | awk \
    '($1 == "dangling" || $1 == "unreachable") && NF >= 3 {print $2, $3}' | LC_ALL=C sort -u)
  if [ -n "$missing" ]; then
    printf '%s' "$missing" >&2
    unsafe "CLONE_ONLY_UNREACHABLE_OBJECT" \
      "objects above are absent from the survivor; preserve them explicitly or keep the clone active"
  fi
}

copy_repository_metadata() {
  local clone="$1"
  local destination="$2"
  local git_dir entry
  local entries=()

  git_dir="$(absolute_git_dir "$clone")" || return 1
  for entry in config config.worktree hooks info; do
    if [ -e "$git_dir/$entry" ] || [ -L "$git_dir/$entry" ]; then
      entries+=("$entry")
    fi
  done
  [ ${#entries[@]} -gt 0 ] || return 0
  tar -cf "$destination" -C "$git_dir" "${entries[@]}"
}

verify_current() {
  local out="$1"
  local clone survivor expected_digest current_digest
  local expected_metadata_digest current_metadata_digest
  local current_refs current_symrefs current_reflog current_metadata bundle_heads

  [ -d "$out" ] || die "backup directory does not exist: $out"
  for required in clone.path survivor.path refs.manifest metadata.manifest \
    bundle-heads.manifest repo-metadata.tar metadata.sha256 all-refs.bundle \
    bundle.sha256 receipt.txt; do
    [ -s "$out/$required" ] || die "backup is incomplete: missing $out/$required"
  done
  [ -e "$out/reflog-oids.manifest" ] || \
    die "backup is incomplete: missing $out/reflog-oids.manifest"
  [ -e "$out/symrefs.manifest" ] || \
    die "backup is incomplete: missing $out/symrefs.manifest"

  IFS= read -r clone < "$out/clone.path"
  IFS= read -r survivor < "$out/survivor.path"
  [ -d "$clone/.git" ] || unsafe "CLONE_PATH_CHANGED" "$clone"
  [ -d "$survivor" ] || unsafe "SURVIVOR_PATH_CHANGED" "$survivor"
  check_no_promisor_clone "$clone"
  check_no_extension_object_stores "$clone"
  check_no_tracked_content_filters "$clone"
  check_identity "$clone" "$survivor" >/dev/null
  check_no_linked_worktrees "$clone"
  check_no_submodule_repositories "$clone"
  check_metadata_scope "$clone"
  check_physical_state "$clone"
  check_reflog_coverage "$clone"
  check_clone_owned_unreachable_objects "$clone" "$survivor"

  current_refs="$(list_refs "$clone")"
  [ "$current_refs" = "$(cat "$out/refs.manifest")" ] || \
    unsafe "REFSET_CHANGED" "rebuild the recovery directory before retirement"

  current_symrefs="$(list_symbolic_refs "$clone")"
  [ "$current_symrefs" = "$(cat "$out/symrefs.manifest")" ] || \
    unsafe "SYMREFS_CHANGED" "symbolic-ref topology changed after preparation"

  current_reflog="$(list_reflog_oids "$clone")"
  [ "$current_reflog" = "$(cat "$out/reflog-oids.manifest")" ] || \
    unsafe "REFLOG_CHANGED" "rebuild the recovery directory before retirement"

  current_metadata="$(metadata_manifest "$clone")"
  [ "$current_metadata" = "$(cat "$out/metadata.manifest")" ] || \
    unsafe "METADATA_CHANGED" "config/hooks/info changed after preparation"

  safe_git -C "$clone" bundle verify "$out/all-refs.bundle" >/dev/null || \
    unsafe "BUNDLE_INVALID" "$out/all-refs.bundle"
  bundle_heads="$(safe_git bundle list-heads "$out/all-refs.bundle" | LC_ALL=C sort)"
  [ "$bundle_heads" = "$(list_bundle_expected_heads "$clone")" ] || \
    unsafe "BUNDLE_REF_MISMATCH" "bundle heads no longer match the clone"

  expected_digest="$(awk 'NR == 1 {print $1}' "$out/bundle.sha256")"
  current_digest="$(sha256_file "$out/all-refs.bundle")"
  [ "$current_digest" = "$expected_digest" ] || \
    unsafe "BUNDLE_DIGEST_CHANGED" "expected=$expected_digest current=$current_digest"

  expected_metadata_digest="$(awk 'NR == 1 {print $1}' "$out/metadata.sha256")"
  current_metadata_digest="$(sha256_file "$out/repo-metadata.tar")"
  [ "$current_metadata_digest" = "$expected_metadata_digest" ] || \
    unsafe "METADATA_ARCHIVE_CHANGED" \
      "expected=$expected_metadata_digest current=$current_metadata_digest"

  echo "READY_TO_QUARANTINE clone=$clone backup=$out sha256=$current_digest"
}

CLONE=""
SURVIVOR=""
OUT=""
VERIFY_CURRENT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --clone) CLONE="${2:?--clone needs a path}"; shift 2 ;;
    --survivor) SURVIVOR="${2:?--survivor needs a path}"; shift 2 ;;
    --out) OUT="${2:?--out needs a directory}"; shift 2 ;;
    --verify-current)
      [ -z "$VERIFY_CURRENT" ] || die "--verify-current may be passed only once"
      VERIFY_CURRENT="${2:?--verify-current needs a backup directory}"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done

if [ -n "$VERIFY_CURRENT" ]; then
  [ -z "$CLONE" ] && [ -z "$SURVIVOR" ] && [ -z "$OUT" ] || \
    die "--verify-current is standalone; do not combine it with preparation options"
  verify_current "$VERIFY_CURRENT"
  exit 0
fi

[ -n "$CLONE" ] || die "--clone is required"
[ -n "$SURVIVOR" ] || die "--survivor is required"
[ -n "$OUT" ] || die "--out is required"
case "$CLONE" in /*) ;; *) die "--clone must be an absolute path" ;; esac
case "$SURVIVOR" in /*) ;; *) die "--survivor must be an absolute path" ;; esac
case "$OUT" in /*) ;; *) die "--out must be an absolute path" ;; esac

CLONE="$(canonical_dir "$CLONE")" || die "clone path does not exist: $CLONE"
SURVIVOR="$(canonical_dir "$SURVIVOR")" || die "survivor path does not exist: $SURVIVOR"
[ ! -e "$OUT" ] || die "backup directory already exists; use a fresh path: $OUT"
OUT_PARENT="$(canonical_dir "$(dirname "$OUT")")" || die "backup parent does not exist: $(dirname "$OUT")"
OUT="$OUT_PARENT/$(basename "$OUT")"
case "$OUT/" in
  "$CLONE/"*|"$SURVIVOR/"*) die "backup directory must be outside both repositories" ;;
esac

check_no_promisor_clone "$CLONE"
check_no_extension_object_stores "$CLONE"
check_no_tracked_content_filters "$CLONE"
IDENTITY_MODE="$(check_identity "$CLONE" "$SURVIVOR")"
SHALLOW_STATE="$(safe_git -C "$CLONE" rev-parse --is-shallow-repository)"
[ "$SHALLOW_STATE" = false ] || unsafe "SHALLOW_CLONE" "fetch complete history before retirement"
check_no_linked_worktrees "$CLONE"
check_no_submodule_repositories "$CLONE"
check_metadata_scope "$CLONE"
check_physical_state "$CLONE"
check_reflog_coverage "$CLONE"
check_clone_owned_unreachable_objects "$CLONE" "$SURVIVOR"

REFS="$(list_refs "$CLONE")"
[ -n "$REFS" ] || unsafe "NO_REFS" "the clone has no ref to bundle"
SYMREFS="$(list_symbolic_refs "$CLONE")"
REFLOG_OIDS="$(list_reflog_oids "$CLONE")"
METADATA="$(metadata_manifest "$CLONE")"
GIT_DIR="$(absolute_git_dir "$CLONE")"
if [ -s "$GIT_DIR/objects/info/alternates" ]; then
  BORROWED_OBJECTS=yes
else
  BORROWED_OBJECTS=no
fi

/bin/mkdir "$OUT"
printf '%s\n' "$CLONE" > "$OUT/clone.path"
printf '%s\n' "$SURVIVOR" > "$OUT/survivor.path"
printf '%s\n' "$REFS" > "$OUT/refs.manifest"
printf '%s\n' "$SYMREFS" > "$OUT/symrefs.manifest"
printf '%s\n' "$REFLOG_OIDS" > "$OUT/reflog-oids.manifest"
printf '%s\n' "$METADATA" > "$OUT/metadata.manifest"
safe_git -C "$CLONE" reflog --all --date=iso \
  --format='%H|%gD|%gs|%cd' > "$OUT/reflog.txt"
copy_repository_metadata "$CLONE" "$OUT/repo-metadata.tar"
METADATA_DIGEST="$(sha256_file "$OUT/repo-metadata.tar")"
printf '%s  %s\n' "$METADATA_DIGEST" "repo-metadata.tar" > "$OUT/metadata.sha256"

  safe_git -C "$CLONE" bundle create "$OUT/all-refs.bundle" --all
  safe_git -C "$CLONE" bundle verify "$OUT/all-refs.bundle" >/dev/null
  safe_git bundle list-heads "$OUT/all-refs.bundle" | LC_ALL=C sort > "$OUT/bundle-heads.manifest"
  if [ "$(cat "$OUT/bundle-heads.manifest")" != "$(list_bundle_expected_heads "$CLONE")" ]; then
    echo "FROZEN_REFS:" >&2
    list_bundle_expected_heads "$CLONE" >&2
    echo "BUNDLE_HEADS:" >&2
    cat "$OUT/bundle-heads.manifest" >&2
    unsafe "BUNDLE_REF_MISMATCH" "bundle heads do not match the frozen clone refs"
  fi

BUNDLE_DIGEST="$(sha256_file "$OUT/all-refs.bundle")"
printf '%s  %s\n' "$BUNDLE_DIGEST" "all-refs.bundle" > "$OUT/bundle.sha256"
printf '%s\n' \
  "prepared_at=$(date '+%F %T %Z')" \
  "clone=$CLONE" \
  "survivor=$SURVIVOR" \
  "identity_mode=$IDENTITY_MODE" \
  "head=$(safe_git -C "$CLONE" rev-parse HEAD)" \
  "branch=$(safe_git -C "$CLONE" branch --show-current)" \
  "borrowed_objects=$BORROWED_OBJECTS" \
  "bundle_sha256=$BUNDLE_DIGEST" \
  "metadata_sha256=$METADATA_DIGEST" > "$OUT/receipt.txt"

verify_current "$OUT"
echo "BORROWED_OBJECTS $BORROWED_OBJECTS"

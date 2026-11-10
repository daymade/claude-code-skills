# Resumable preparation for one linked worktree

Use this helper after the named target and its initialized module repositories have
preservation authority. It requires Python 3.10+, Git, empty tracked/untracked status
in the target and modules, and an external evidence directory. It does not fetch,
change refs, remove worktrees, establish business containment or grant deletion authority.
Keep the Mode E worktree procedure's ownership, scheduler, occupancy, containment,
normal-removal and post-removal gates.

```bash
SKILL_ROOT="<absolute-loaded-git-safety-net-directory>"
python3 "$SKILL_ROOT/scripts/git_prepare_worktree_retirement.py" prepare \
  --worktree "<exact-linked-worktree>" --base-ref refs/heads/main \
  --out "<new-external-evidence-directory>"
# After an interruption, use the same arguments and declarations:
python3 "$SKILL_ROOT/scripts/git_prepare_worktree_retirement.py" prepare \
  --worktree "<exact-linked-worktree>" --base-ref refs/heads/main \
  --out "<same-external-evidence-directory>" --resume
python3 "$SKILL_ROOT/scripts/git_prepare_worktree_retirement.py" verify-current \
  --out "<same-external-evidence-directory>"
```

Select a fully qualified retained base ref. When it reaches every root HEAD/reflog
commit being retired, the root uses that ref as its exact-object carrier; otherwise
the helper packs only the target HEAD/reflog history. Content containment after a
squash still needs the separate Mode E check. Neither a primary checkout nor its
unrelated WIP is a removal target.

Each initialized module must have its own Git/common directory inside this linked
worktree's admin directory. The helper inventories module HEAD, gitlink, refs and
symbolic targets, raw reflogs, metadata and physically owned loose/packed objects.
Recovery seeds are those identities and their dependency closure, including required
objects borrowed through alternates. It does not enumerate the alternate store's
unrelated objects. Metadata plus one self-contained recovery object pack replaces
repeated raw-store copies and bundles. Recovery Git configuration is newly generated;
the original configuration and reflogs remain in `metadata/` for explicit restoration.
Git's native `extensions.worktreeConfig` is supported: its missing, enabled or
disabled state is frozen, and per-worktree `config.worktree` bytes are preserved.
Changing either later blocks current verification; other extensions, includes and
promisor settings still require manual handling.

All ignored paths, entry types, modes, sizes, file hashes and symlink targets are
frozen. Byte-identical entries at the same relative primary path use that retained
carrier; other entries are copied with their relative paths. To exclude a known
rebuildable directory, add an exact target-relative declaration, repeated on resume:

```text
--rebuildable 'node_modules=pnpm install --frozen-lockfile from tracked package.json and pnpm-lock.yaml'
```

This is the operator's explicit reproduction claim, not a detector for caches.
Check that the named tool and tracked inputs really rebuild every covered entry;
unique environment files, evidence or uncertain bytes stay copied. Empty, unused
or overlapping declarations fail. Excluded entries remain in the frozen inventory
with their recipe, and later changes still fail the final comparison.

`state.json` is an atomic versioned checkpoint. A completed stage has its own scope
digest and file manifest before its directory is renamed into place. Resume verifies
and reuses that stage, including a stage completed before its checkpoint reply was
lost. It never overwrites a mismatched completed stage. A partial `.building-*`
directory is retained, and resume creates a new stage for that incomplete work only;
keep or retire those task-owned partial artifacts under the existing artifact gate.

Run `verify-current` before the final standalone occupancy check. It reads the checkpoint, verifies
recovery bytes and object closure, and compares current target, refs, module mapping,
metadata, physical object identities and ignored inventory with the frozen state.
Any change stops removal; preserve the new state and prepare a new evidence directory.
This is not a lock against writers. After its Git probes finish, run the standalone
occupancy check, reconfirm ownership, locks and scheduler use, then make the
already-authorized normal removal the next operation with no intervening command.
After removal, run `verify-recovery --out <same-directory>` and separately prove the
target is absent and the primary checkout is unchanged. That mode verifies carriers;
it does not claim removal occurred. Keep recovery-only evidence until authorized retirement.

Exit 0 is a positive preparation/verification result, 1 is an unsafe or changed
state, and 2 is invalid input or an execution failure. Missing/corrupt checkpoints
remain failures. Primary targets, dirty/locked worktrees, shared or unresolved module
stores, indirect Git/admin metadata, uninitialized modules with retained stores, partial/shallow Git
repositories or extensions other than native `worktreeConfig`,
content filters, extension object stores and special file types require
the manual Mode E path or resolution of that exact gap. Do not deinitialize modules
or force deletion to bypass an unsupported state.

# Worktree retirement helper reference

For retiring a linked worktree, follow the complete
[worktree retirement procedure](merge_verification.md#worktree-retirement--prove-the-checkout-is-disposable-before-removal).

Use this helper after the named target and its initialized module repositories have
preservation authority. It requires Python 3.10+, Git, empty tracked/untracked status
in the target and modules, and an external evidence directory. It does not fetch,
change refs, remove worktrees, establish business containment or grant deletion authority.
The same interface supports ordinary linked worktrees without submodules.

```bash
SKILL_ROOT="<absolute-loaded-git-safety-net-directory>"
python3 "$SKILL_ROOT/scripts/git_prepare_worktree_retirement.py" prepare \
  --worktree "<exact-linked-worktree>" --base-ref "<fully-qualified-retained-ref>" \
  --out "<new-external-evidence-directory>"
# After an interruption, use the same arguments and declarations:
python3 "$SKILL_ROOT/scripts/git_prepare_worktree_retirement.py" prepare \
  --worktree "<exact-linked-worktree>" --base-ref "<fully-qualified-retained-ref>" \
  --out "<same-external-evidence-directory>" --resume
python3 "$SKILL_ROOT/scripts/git_prepare_worktree_retirement.py" verify-current \
  --out "<same-external-evidence-directory>"
```

In an actively written shared repository, prefer a fixed task recovery ref over
a moving branch such as `refs/heads/main` as `--base-ref`. Create it only for
the exact authorized target after the content-containment check. The helper
freezes that ref's object ID, and later movement of the selected ref makes
`verify-current` fail closed. If a moving base changes, preserve the existing
evidence and prepare a new checkpoint against a newly verified fixed ref; do not
edit the old checkpoint.

Read `state.json`'s `snapshot.root_carrier`: `retained-ref` means the selected ref reaches
every root HEAD/reflog commit being retired and needs no root-history pack. A ref at HEAD
is insufficient when the reflog holds a unique commit outside HEAD's ancestry; the helper
then selects `pack` and preserves the target HEAD/reflog history. Do not discard that pack
or declare the unknown commit withdrawn to force the cheaper route.

For explicitly withdrawn rebase commits, pass repeated `--known-withdrawal OLD=RETAINED`
pairs with full commit IDs. The exact current tip must be in the retained base;
OLD must be an unretained commit from this root's reflog, and RETAINED must be in
the base. Both must be nonempty single-parent commits with matching stable and
verbatim patch IDs, so whitespace changes are not silently discarded. The checkpoint
freezes these declarations and keeps the original reflog metadata, but does not
promise recovery of the withdrawn commit's exact object identity. Frozen parent chains
must reach retained history; undeclared ancestors and other unretained history still
get the existing root pack. Supplied pairs with missing,
empty, mismatched or changed IDs fail before new evidence is written. Repeat the same pairs on
`prepare --resume`; verification reads only the frozen checkpoint.
Opt-in withdrawal checkpoints use version 2, which old helpers reject; ordinary
version 1 checkpoints keep their existing meaning and remain readable.

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

Sparse checkouts may omit tracked files with content filters: the helper accepts
only paths that Git marks `skip-worktree`, with sparse checkout enabled, no
physical file and no symlink along the omitted path. It does not fetch or smudge
these files. A materialized filtered file, a dangling link or an unproven omission
still requires manual preservation; `skip-worktree` alone is not permission to
discard a payload. `verify-current` repeats the same checks before retirement.

### Materialized files in the shared LFS store

If the checkpoint requires manual handling of a materialized LFS file, run
this read-only proof against the exact worktree and retained ref:

```bash
python3 "<skill-root>/scripts/git_prepare_worktree_retirement.py" verify-lfs-retention \
  --worktree "<exact-linked-worktree>" --base-ref "<fully-qualified-retained-ref>"
```

Require `status=lfs_retained` and a positive `examined` count. For each materialized
LFS path, the retained commit must have the same pointer. A full payload must
match the pointer's size and SHA-256 both in the worktree and in the Git common
directory's LFS store. Unsupported filters, indirect paths, missing objects
or differing bytes stop the proof. Preserve unique payloads before proceeding.
Use the result for the LFS portion of the manual
[worktree retirement procedure](merge_verification.md#worktree-retirement--prove-the-checkout-is-disposable-before-removal).
Recheck immediately before removal and complete the remaining retirement checks there.
For new sparse worktrees, materialize the required policy files and specific
edit and verification paths to limit LFS expansion.

An `lfs` directory in a retiring Git/admin directory is supported only when `lstat`
identifies a real, empty directory. Its presence and mode are frozen in metadata
and preserved for recovery. Missing and empty remain distinct; later creation,
removal, mode changes or contents block current verification and resume. Nonempty,
indirect (including dangling symlinks), special or unreadable LFS paths require
manual handling. This exception does not support an LFS object store or bypass
the tracked-content-filter gate.

All ignored paths, entry types, modes, sizes, file hashes and symlink targets are
frozen. A primary-path candidate with different type, mode or size cannot retain
a regular file. Read and hash its contents only if these checks match. Reuse a
byte-identical candidate and copy the source if it differs. A missing path,
non-directory ancestor or symlink loop also leaves the source to be copied.
An access error that pathlib reports is an error, not evidence of absence.
The preparation recheck and standalone `verify-current` read source bytes again.
To exclude a known rebuildable directory, add an exact target-relative
declaration, repeated on resume:

```text
--rebuildable 'node_modules=pnpm install --frozen-lockfile from tracked package.json and pnpm-lock.yaml'
```

This is the operator's explicit reproduction claim, not a detector for caches.
Check that the named tool and tracked inputs really rebuild every covered entry;
unique environment files, evidence or uncertain bytes stay copied. Declare only
paths present in this target; do not add an optional build directory that is absent.
Empty declarations fail. Nonexistent, unused or overlapping paths fail before
content scans or recovery output creation, with the offending path in the diagnostic. Git ignored
names are checked across initialized modules without hashing file contents; the
full ignored inventory is still frozen afterward. Excluded entries retain their
recipe, and later changes still fail the final comparison.

`state.json` is an atomic versioned checkpoint. A completed stage has its own scope
digest and file manifest before its directory is renamed into place. Resume verifies
and reuses that stage, including a stage completed before its checkpoint reply was
lost. It never overwrites a mismatched completed stage. A partial `.building-*`
directory is retained, and resume creates a new stage for that incomplete work only;
keep or retire those task-owned partial artifacts under the existing artifact gate.

`verify-current` reads the checkpoint, verifies
recovery bytes and object closure, and compares current target, refs, module mapping,
metadata, physical object identities and ignored inventory with the frozen state.
`verify-recovery --out <evidence-directory>` verifies the saved carriers without comparing the
live target. It does not prove removal or that the primary checkout is unchanged.

Exit 0 is a positive preparation/verification result, 1 is an unsafe or changed
state, and 2 is invalid input or an execution failure. Missing/corrupt checkpoints
remain failures. Primary targets, dirty/locked worktrees, shared or unresolved module
stores, indirect Git/admin metadata, uninitialized modules with retained stores, partial/shallow Git
repositories or extensions other than native `worktreeConfig`,
content filters, extension object stores (apart from the empty LFS scaffold above)
and special file types require
the manual Mode E path or resolution of that exact gap. Do not deinitialize modules
or force deletion to bypass an unsupported state.

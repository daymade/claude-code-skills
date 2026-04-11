# Installation Flow — Deep Dive

This document is a reference for the agent when walking a user through installing upstream ima-skill via `scripts/install_ima_skill.sh`. It is not part of the runtime hot path — read it when the install fails or when the user has questions about what's happening under the hood.

## Why a wrapper installer exists

The upstream Tencent IMA skill ships as a zip file at `https://app-dl.ima.qq.com/skills/ima-skills-<version>.zip`. The official documentation at `https://ima.qq.com/agent-interface` expects users to paste a prompt into a specific proprietary agent that handles the install for them. There is no cross-platform installer in the upstream distribution.

ima-copilot bridges that gap by using the open [vercel-labs/skills](https://github.com/vercel-labs/skills) CLI as a last-mile distributor. The flow is:

```
ima.qq.com/skills/ima-skills-X.Y.Z.zip
        ↓ curl
/tmp/ima-copilot-staging/<ts>/
        ↓ unzip
/tmp/ima-copilot-staging/<ts>/ima-skill/
        ↓ npx skills add <local-path> -a ... -g -y
~/.claude/skills/ima-skill/    (Claude Code — may be a symlink)
~/.agents/skills/ima-skill/    (Codex — may be a symlink)
~/.openclaw/skills/ima-skill/  (OpenClaw, if installed — may be a symlink)
```

The staging directory is deleted on exit. We rely on vercel skills' default symlink behavior: the first agent whose install succeeds becomes the canonical directory, and the remaining agents are symlinked to it. This is safe because vercel skills decouples the canonical location from the source path — once the install completes, nothing depends on the staging directory any more, so cleaning it up does not break any symlinks.

The key win of symlink mode is **propagation**: a Capability 3 repair applied to any one agent entry is immediately visible to the others through the symlink graph. When the user upgrades ima-skill, the new version replaces the canonical and all symlinks automatically point at the new content. `diagnose.sh` understands this graph via `realpath` and dedupes its issue reports so the user sees each underlying problem exactly once, not once per agent.

If you ever need the opposite behavior — fully independent agent copies, each with its own state and its own repair cycle — pass `--copy` to `npx skills add` manually by editing the install script. This is a rare requirement and the ima-copilot flow is not designed around it.

## Prerequisites

The installer needs three tools on `PATH`:

| Tool   | Why                                             | How to install                            |
|--------|-------------------------------------------------|-------------------------------------------|
| `curl` | Download the official zip                       | Preinstalled on macOS/Linux               |
| `unzip`| Extract the archive                             | Preinstalled on macOS/Linux               |
| `npx`  | Run `skills add` from the npm registry on demand | Install Node.js 18+ — `brew install node` |

The installer checks for each and aborts with a clear message if any is missing.

## Agent detection

The installer looks for well-known directory markers:

| Agent       | Detection rule              |
|-------------|-----------------------------|
| Claude Code | `~/.claude` exists           |
| Codex       | `~/.agents` exists           |
| OpenClaw    | `~/.openclaw` exists or `openclaw` is on `PATH` |

Only agents that are detected are passed to `npx skills add -a ...`. A missing agent produces no install — we never silently write to a path the user hasn't already chosen to use.

If zero agents are detected, the installer defaults to `claude-code` as the most common case and prints a notice explaining why.

## Version override

The installer hard-codes a known-good version for the default case. To pin a specific upstream release:

```bash
# via flag
bash scripts/install_ima_skill.sh --version 1.1.2

# via environment variable
IMA_VERSION=1.1.2 bash scripts/install_ima_skill.sh
```

If the upstream URL 404s (most commonly because the version hasn't been released yet or has been yanked), the installer exits with a hint to try the next known version. The upstream release pattern from observation is `ima-skills-<major>.<minor>.<patch>.zip` — check `https://ima.qq.com/agent-interface` for the current version when in doubt.

## What `npx skills add` actually does

`npx -y skills add <path> -a <agent> -g -y` breaks down as:

- `<path>` — a local directory containing a SKILL.md at the root. The vercel-labs CLI treats this as a single skill source.
- `-a <agent>` — target agent identifier. Passing multiple `-a` flags installs to multiple agents in one call.
- `-g` — global scope. Installs to the agent's home directory instead of a project-local `.claude/` or `.agents/` folder.
- `-y` — non-interactive. Skip all prompts. Required for use from a script.

Notice what is **not** passed: `--copy`. In vercel skills' default mode, the CLI picks one agent's directory (usually the first one whose install succeeds) as the canonical copy and creates symlinks from every other agent's skills directory back to it. For ima-copilot's use case this is strictly better than `--copy` would be — a repair or upgrade applied to any one agent propagates to all of them through the symlink graph, eliminating the need to loop over every agent during a fix.

The CLI auto-detects installed agents as well, but we pass `-a` explicitly to avoid accidentally installing to the other 38 supported agents the user hasn't opted into.

## File layout after install

After a successful install, the target directories contain the original upstream structure unchanged:

```
~/.claude/skills/ima-skill/
├── SKILL.md                         # root entry point
├── notes/
│   ├── SKILL.md                     # note operations (known ISSUE-001 in v1.1.2)
│   └── references/
│       └── api.md
└── knowledge-base/
    ├── SKILL.md                     # knowledge base operations (known ISSUE-001)
    ├── references/
    │   └── api.md
    └── scripts/
        ├── cos-upload.cjs
        └── preflight-check.cjs
```

No repair happens at install time. Any file modifications happen later, in Capability 3, with explicit user consent.

## Uninstall

vercel-labs/skills has a `remove` command:

```bash
npx -y skills remove ima-skill -a claude-code -a codex -a openclaw -g -y
```

This removes the skill from each named agent's skill directory. It does not remove credentials from `~/.config/ima/` — those are managed independently by Capability 2 and may still be wanted even without an install.

## Troubleshooting

### "curl returned HTTP 404"

The upstream package for the requested version doesn't exist. Try a different version via `--version`.

### "npx skills add failed"

Usually one of:
- No internet / npm registry unreachable — check network
- Node.js version too old — `node --version` should report ≥18
- Permissions on the target directory — some WSL / sandboxed environments restrict writes to `~/.claude/skills/`

### "extract archive but no SKILL.md found"

The upstream archive layout changed. Manually list the archive contents:

```bash
unzip -l /tmp/ima-copilot-staging/*/ima-skills.zip
```

If the SKILL.md moved, open an issue on this skill (ima-copilot) with the new archive layout so the installer can be updated.

### "Installed but diagnose.sh says not installed"

Most likely the agent detection logic put the install in a non-standard path for your agent. Check the known locations in `diagnose.sh` — if your agent uses a different path, the fix is to add it there as a new candidate.

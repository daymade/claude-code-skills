#!/usr/bin/env python3
"""一键初始化项目的 SessionStart hook。

用法:
    python init_session_start_hook.py --repo /path/to/project [--guide ONBOARDING.md] [--update-gitignore]

功能:
    1. 创建 .claude/settings.json（SessionStart hook 配置）
    2. 创建 .claude/hooks/session-start-check.sh（24h 缓存 + 环境自检提示）
    3. 可选更新 .gitignore（允许 .claude/settings.json 和 hooks/ 入 git）

要求:
    - 目标目录必须是 git 仓库（或 --force 跳过检查）
    - 不会覆盖已有配置（除非 --force-overwrite）
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path


SETTINGS_JSON = """\
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/session-start-check.sh"
          }
        ]
      }
    ]
  }
}
"""

HOOK_TEMPLATE = """#!/usr/bin/env bash
# SessionStart hook for {project_name}
# 24h cache + simplified nudge — agent reads {guide_file} for actual commands.

CACHE_DIR="$HOME/.claude/cache/env-check"
mkdir -p "$CACHE_DIR"

# Use repo absolute path hash as cache key
REPO_HASH=$(cd "$(dirname "$0")/../.." && pwd | sha256sum | cut -d' ' -f1)
CACHE_FILE="$CACHE_DIR/$REPO_HASH"

# Silent if checked within 24h
if [ -f "$CACHE_FILE" ] && [ "$(find "$CACHE_FILE" -mtime -1 2>/dev/null)" ]; then
    exit 0
fi

# Create cache + output concise nudge
touch "$CACHE_FILE"
echo "【环境自检】你刚刚进入 {project_name} 仓库。请在执行任何任务前，先阅读 {guide_file} 并按 Step 1-3 验证环境。任一失败则按 {guide_file} 修复。"
"""

GITIGNORE_RULES = """
# Allow project-level Claude Code settings + hooks to be shared
!.claude/settings.json
!.claude/hooks/
.claude/settings.local.json
.claude/cache/
.claude/debug/
"""


def detect_project_name(repo_path: Path) -> str:
    """从目录名或 git remote 推断项目名称。"""
    name = repo_path.name
    git_config = repo_path / ".git" / "config"
    if git_config.exists():
        try:
            text = git_config.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if "url =" in line:
                    url = line.split("=", 1)[1].strip()
                    # Extract repo name from git@host:owner/repo.git or https://host/owner/repo.git
                    if "/" in url:
                        part = url.rsplit("/", 1)[1]
                        if part.endswith(".git"):
                            part = part[:-4]
                        if part:
                            return part
        except Exception:
            pass
    return name


def init_hook(repo_path: Path, guide_file: str, update_gitignore: bool, force_overwrite: bool, force_non_git: bool) -> int:
    if not repo_path.exists():
        print(f"❌ 目录不存在: {repo_path}", file=sys.stderr)
        return 1

    if not (repo_path / ".git").exists() and not force_non_git:
        print(f"❌ {repo_path} 不是 git 仓库。如需继续，加 --force-non-git", file=sys.stderr)
        return 1

    project_name = detect_project_name(repo_path)
    claude_dir = repo_path / ".claude"
    hooks_dir = claude_dir / "hooks"
    settings_file = claude_dir / "settings.json"
    hook_file = hooks_dir / "session-start-check.sh"
    gitignore_file = repo_path / ".gitignore"

    # Create directories
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Write settings.json
    if settings_file.exists() and not force_overwrite:
        print(f"⚠️  已存在，跳过: {settings_file}")
    else:
        settings_file.write_text(SETTINGS_JSON, encoding="utf-8")
        print(f"✅ 创建: {settings_file}")

    # Write hook script
    if hook_file.exists() and not force_overwrite:
        print(f"⚠️  已存在，跳过: {hook_file}")
    else:
        hook_content = HOOK_TEMPLATE.format(project_name=project_name, guide_file=guide_file)
        hook_file.write_text(hook_content, encoding="utf-8")
        # Make executable
        hook_file.chmod(hook_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"✅ 创建: {hook_file}")

    # Update .gitignore
    if update_gitignore:
        if gitignore_file.exists():
            existing = gitignore_file.read_text(encoding="utf-8", errors="replace")
            # Check if rules already present
            if "!.claude/settings.json" in existing:
                print(f"ℹ️  .gitignore 已包含 Claude 规则，跳过")
            else:
                with open(gitignore_file, "a", encoding="utf-8") as f:
                    f.write(GITIGNORE_RULES)
                print(f"✅ 更新: {gitignore_file}")
        else:
            gitignore_file.write_text(GITIGNORE_RULES.lstrip("\n"), encoding="utf-8")
            print(f"✅ 创建: {gitignore_file}")

    print("\n📋 总结:")
    print(f"   项目: {project_name}")
    print(f"   路径: {repo_path}")
    print(f"   指南: {guide_file}")
    print(f"   Hook: {hook_file}")
    if update_gitignore:
        print(f"   Gitignore: 已更新")
    print("\n下次 Claude Code 进入此仓库时，SessionStart hook 会自动触发。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize SessionStart hook for a project")
    parser.add_argument("--repo", required=True, help="Target repository path")
    parser.add_argument("--guide", default="ONBOARDING.md", help="Guide file name to reference in hook (default: ONBOARDING.md)")
    parser.add_argument("--update-gitignore", action="store_true", help="Update .gitignore to allow .claude/ files")
    parser.add_argument("--force-overwrite", action="store_true", help="Overwrite existing files")
    parser.add_argument("--force-non-git", action="store_true", help="Allow running on non-git directory")
    args = parser.parse_args()

    return init_hook(
        repo_path=Path(args.repo).resolve(),
        guide_file=args.guide,
        update_gitignore=args.update_gitignore,
        force_overwrite=args.force_overwrite,
        force_non_git=args.force_non_git,
    )


if __name__ == "__main__":
    sys.exit(main())

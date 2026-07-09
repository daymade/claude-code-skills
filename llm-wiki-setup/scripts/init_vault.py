#!/usr/bin/env python3
"""init_vault — scaffold 一个空的 LLM Wiki vault（只建机制层）。

只建【通用工程结构】：三层目录 + lint 脚本 + hook 占位 + 空 index/log + CLAUDE 骨架。
**不写任何 schema / 投资偏好**——那是 CLAUDE.md 规则层的事，由访谈长出
（见 skill 的 SKILL.md + references/interview.md）。规则层照抄模板 = 背叛「每个人建自己的」。

用法：
  python init_vault.py <目标目录>
  python init_vault.py --refresh-tools <已有 vault>
"""
import filecmp
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / 'templates'

INDEX_TMPL = """# Index — <你的 vault 名>

> 全局目录：每页一行摘要。新建页必须在这里登记一行。
> 分节按【你自己的】分层来——下面只是占位，删改成你 CLAUDE.md 里定的层级。

## companies

## industries

## macro

## analysts

## themes

## synthesis
"""

LOG_TMPL = """# Log

> append-only 操作日志。每条 `## [YYYY-MM-DD] ingest|query|lint | 标题`（grep 友好）。
"""


def managed_tools(target):
    """Return canonical source and vault destination pairs for managed tooling."""
    return [
        (HERE / 'lint-vault.py', target / 'scripts' / 'lint-vault.py'),
        (TEMPLATES / 'pre-commit.snippet', target / '.githooks' / 'pre-commit'),
    ]


def refresh_tools(target):
    """Refresh copied tooling in an existing vault without touching user content."""
    required_files = [
        target / 'CLAUDE.md',
        target / 'wiki' / 'index.md',
        target / 'wiki' / 'log.md',
        *[destination for _, destination in managed_tools(target)],
    ]
    invalid = [
        path
        for path in required_files
        if path.is_symlink() or not path.is_file()
    ]
    if not target.is_dir() or invalid:
        print(f"❌ 不是可安全刷新的 LLM Wiki vault: {target}")
        for path in invalid:
            print(f"   缺失或不是普通文件: {path}")
        return 1

    pending = []
    for source, destination in managed_tools(target):
        content_matches = filecmp.cmp(source, destination, shallow=False)
        is_executable = (destination.stat().st_mode & 0o111) == 0o111
        if content_matches and is_executable:
            continue
        backup = destination.with_name(destination.name + '.before-refresh')
        if destination.exists() and (backup.exists() or backup.is_symlink()):
            print(f"❌ 备份已存在，未修改任何文件: {backup}")
            print("   请先审阅并移走该备份，再重新执行 refresh。")
            return 1
        pending.append((source, destination, backup))

    if not pending:
        print(f"✅ vault 工具已是最新: {target}")
        return 0

    for source, destination, backup in pending:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.copy2(destination, backup)
            print(f"   已备份: {backup}")
        shutil.copy2(source, destination)
        os.chmod(destination, 0o755)
        print(f"   已刷新: {destination}")

    print("✅ 只刷新了 scripts/lint-vault.py 与 .githooks/pre-commit；wiki/raw/CLAUDE.md 未改。")
    return 0


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--refresh-tools':
        return refresh_tools(Path(args[1]).resolve())
    if len(args) != 1 or args[0].startswith('-'):
        print("用法: python init_vault.py <目标目录>")
        print("      python init_vault.py --refresh-tools <已有 vault>")
        return 1
    target = Path(args[0]).resolve()
    if target.exists() and any(target.iterdir()):
        print(f"⚠️  目标非空: {target}\n   为安全不覆盖，请指定空目录。")
        return 1

    # 1. copy 骨架（wiki/<6层>/.gitkeep + raw/.gitkeep）
    shutil.copytree(TEMPLATES / 'vault', target, dirs_exist_ok=True)

    # 1b. lint 脚本：SSOT 在 skill/scripts/lint-vault.py，copy 进 vault/scripts/
    (target / 'scripts').mkdir(exist_ok=True)
    shutil.copy(HERE / 'lint-vault.py', target / 'scripts' / 'lint-vault.py')
    os.chmod(target / 'scripts' / 'lint-vault.py', 0o755)

    # 2. CLAUDE.md = 机制层骨架（规则层是空占位，待访谈填）
    shutil.copy(TEMPLATES / 'CLAUDE-skeleton.md', target / 'CLAUDE.md')

    # 3. 空 index / log
    (target / 'wiki' / 'index.md').write_text(INDEX_TMPL, encoding='utf-8')
    (target / 'wiki' / 'log.md').write_text(LOG_TMPL, encoding='utf-8')

    # 4. hook 占位（启用需 git config core.hooksPath .githooks）
    hooks = target / '.githooks'
    hooks.mkdir(exist_ok=True)
    shutil.copy(TEMPLATES / 'pre-commit.snippet', hooks / 'pre-commit')
    os.chmod(hooks / 'pre-commit', 0o755)

    print(f"✅ vault 骨架就绪: {target}")
    print("\n机制层已装好（三层目录 + lint + hook）。接下来：")
    print(f"  1. cd {target} && git init")
    print("  2. git config core.hooksPath .githooks   # 启用 lint hook（local 配置，换机/重 clone 要重设）")
    print("  3. 开始访谈共创【你自己的】CLAUDE.md —— 见 skill SKILL.md + references/interview.md")
    print("     规则层现在是空占位，禁止照抄模板，用你自己的话填。")
    return 0


if __name__ == '__main__':
    sys.exit(main())

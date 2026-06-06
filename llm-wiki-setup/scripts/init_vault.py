#!/usr/bin/env python3
"""init_vault — scaffold 一个空的 LLM Wiki vault（只建机制层）。

只建【通用工程结构】：三层目录 + lint 脚本 + hook 占位 + 空 index/log + CLAUDE 骨架。
**不写任何 schema / 投资偏好**——那是 CLAUDE.md 规则层的事，由访谈长出
（见 skill 的 SKILL.md + references/interview.md）。规则层照抄模板 = 背叛「每个人建自己的」。

用法：python init_vault.py <目标目录>
"""
import sys
import os
import shutil
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


def main():
    if len(sys.argv) < 2:
        print("用法: python init_vault.py <目标目录>")
        return 1
    target = Path(sys.argv[1]).resolve()
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

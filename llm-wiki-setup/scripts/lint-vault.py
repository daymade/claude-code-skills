#!/usr/bin/env python3
"""Vault lint — 自动检测投研 LLM Wiki vault 的结构性问题。

挂 git pre-commit hook（见 vault 安装时配的 hooksPath/pre-commit），commit 前自动跑；
硬 fail 项阻断 commit，不靠人记忆/自觉。软警告只提示、不阻断。

硬 fail（阻断 commit，三项均为结构性、零误报）：
  1. BROKEN_WIKILINK   [[X]] 指向 vault 内不存在的页（排除 raw/ 与 ../ 逻辑引用）
  2. INVALID_YAML      frontmatter pyyaml 解析失败（如值含未转义冒号）
  3. CROSS_LEVEL_LINK  companies/ 页无任何有效 industries/themes/macro 链接（孤立微观信息无价值）

软警告（advisory，打印但不阻断 commit）：
  4. ORPHAN_DOC        raw/ 下的源文件没有被任何 wiki 页 [[raw/...]] 引用
  5. OVERSIZED_PAGE    单个 wiki 页 > 200 行（建议拆分，对齐 Karpathy/Hermes 的 splitting 门槛）

不覆盖（语义类，lint 难精确、易误报，仍需人工 / LLM / counter-review）：
  - STALE_NUMBER（>90 天的孤立数字）、MISSING_ANALYST（观点无分析师链接）
  - 派生值过时副本（同一 PT/立场在多处复制后漂移）、观点冲突未归档

用法：python lint-vault.py [WIKI_DIR]   （默认脚本同级 ../wiki，raw 取其 sibling）
退出码：0 = 通过（可含软警告）；1 = 硬 fail；2 = 环境错误
"""
import sys
import os
import re
import glob


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    wiki = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(here, '..', 'wiki')
    if not os.path.isdir(wiki):
        print(f'lint-vault: wiki 目录不存在: {wiki}')
        return 2
    raw_dir = os.path.join(os.path.dirname(wiki), 'raw')

    md_files = sorted(glob.glob(os.path.join(wiki, '**', '*.md'), recursive=True))
    if not md_files:
        print(f'lint-vault: {wiki} 下无 .md')
        return 2

    # vault 实际存在的页（相对 wiki，去 .md 后缀）
    pages = {os.path.relpath(f, wiki)[:-3] for f in md_files}

    fails = []   # 硬错：阻断 commit
    warns = []   # 软警告：仅提示
    skipped = []

    # 收集所有页内容（一次读，多处用）
    contents = {f: open(f, encoding='utf-8').read() for f in md_files}
    link_re = re.compile(r'\[\[([^\]]+)\]\]')

    # ---- 硬 1. BROKEN_WIKILINK ----
    raw_refs = set()  # 顺便收集所有 raw 引用，给 ORPHAN_DOC 用
    for f in md_files:
        rel = os.path.relpath(f, wiki)
        for m in link_re.findall(contents[f]):
            target = m.split('|')[0].split('#')[0].strip()
            if target.startswith('raw/'):
                raw_refs.add(target)
                continue  # raw 逻辑引用不在 wiki/ 内，跳过断链检查
            if target.startswith('../'):
                continue  # 跨目录逻辑引用，不检查
            if target not in pages:
                fails.append(f'BROKEN_WIKILINK  {rel}: [[{target}]] → 不存在的页')

    # ---- 硬 2. INVALID_YAML（pyyaml 缺失则降级 skip，不误 fail）----
    try:
        import yaml
    except ImportError:
        skipped.append('YAML 检查需 pyyaml（hook 用 `uv run --with pyyaml` 注入；此次未装→跳过）')
        yaml = None
    if yaml is not None:
        for f in md_files:
            rel = os.path.relpath(f, wiki)
            txt = contents[f]
            if not txt.startswith('---'):
                continue
            end = txt.find('\n---', 3)
            if end < 0:
                fails.append(f'INVALID_YAML    {rel}: frontmatter 无闭合 ---')
                continue
            try:
                yaml.safe_load(txt[4:end])
            except Exception as e:
                fails.append(f'INVALID_YAML    {rel}: {str(e).splitlines()[0][:80]}')

    # ---- 硬 3. CROSS_LEVEL_LINK ----
    cl_re = re.compile(r'\[\[(industries|themes|macro)/([^\]|#]+)')
    for f in sorted(glob.glob(os.path.join(wiki, 'companies', '*.md'))):
        rel = os.path.relpath(f, wiki)
        has = any((lvl + '/' + name.strip()) in pages for lvl, name in cl_re.findall(contents[f]))
        if not has:
            fails.append(f'CROSS_LEVEL_LINK {rel}: 无有效 industries/themes/macro 链接')

    # ---- 软 4. ORPHAN_DOC（raw 源文件无 wiki 引用）----
    if os.path.isdir(raw_dir):
        raw_files = [p for p in glob.glob(os.path.join(raw_dir, '**', '*'), recursive=True)
                     if os.path.isfile(p) and not p.endswith('.gitkeep')]
        for p in raw_files:
            rel_raw = 'raw/' + os.path.relpath(p, raw_dir)
            stem = os.path.splitext(rel_raw)[0]  # 去扩展名，宽松匹配 #anchor / 带不带 .md
            # 任一 raw 引用以该文件 stem 为前缀即算被引用（宁漏报不误报）
            if not any(ref.startswith(stem) or ref.startswith(rel_raw) for ref in raw_refs):
                warns.append(f'ORPHAN_DOC      {rel_raw}: 无任何 wiki 页引用')

    # ---- 软 5. OVERSIZED_PAGE ----
    for f in md_files:
        n = contents[f].count('\n') + 1
        if n > 200:
            warns.append(f'OVERSIZED_PAGE  {os.path.relpath(f, wiki)}: {n} 行（>200，建议拆分）')

    # ---- 输出 ----
    for s in skipped:
        print(f'⚠️  {s}')
    if warns:
        print(f'\n🟡 软警告 {len(warns)} 条（不阻断 commit，建议处理）：')
        for x in warns:
            print('   ' + x)
    if fails:
        print(f'\n🔴 vault lint 失败 {len(fails)} 条（阻断 commit）：')
        for x in fails:
            print('   ' + x)
        print('\n修复后重新 commit。断链→改引用或去 wikilink；YAML→值含冒号加引号；CROSS_LEVEL→补 industries/macro 链接。')
        return 1

    tail = f'，{len(warns)} 条软警告' if warns else ''
    print(f'✅ vault lint 通过（{len(md_files)} 页：0 断链 / YAML 合法 / CROSS_LEVEL_LINK 达标{tail}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())

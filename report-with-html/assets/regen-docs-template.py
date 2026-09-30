#!/usr/bin/env python3
# ============================================================================
# 模板：嵌入源文档 + 条款引用抽屉的报告生成器（工作实现快照，非通用引擎）
#
# 来源：`_regen-docs.py` 的已验证工作实现。
# 用法：复制到你的报告目录改名（如 _regen-docs.py），按报告改「配置区」，机制区直接复用。
#       并把 citation-drawer.html（skill 的 assets/components/）复制到同目录——抽屉交互
#       是那个组件的活，本脚本只管「内容注入」，两层分工。
#
# ── 分层（2026-07 抽组件后）──────────────────────────────────────────────
#   本脚本 = 内容注入层：读源 markdown → 烤进 s9 的 .dpane、打条款锚点、生成 tab 按钮，
#            再把 citation-drawer 组件整块内嵌进页面。
#   citation-drawer.html = 交互外壳（SSOT）：tab 切换 / 正文「第 N 条」linkify / 侧滑抽屉
#            定位高亮 / 就地滚动 / ESC 关闭。改交互改那个组件文件、重跑本脚本即生效。
#   两层接缝 = DOM 契约：s9 里 .dtab[data-i]+.dt-t、.dpane[data-i]+.dsrc、
#            <h2 id="d{文档号}-c{条号}">，正文「第 N 条」纯文本。组件从 DOM 自读文档名，
#            本脚本无需再把文档名/文件名编进 JS。
#
# ── 配置区（每张报告必改）──────────────────────────────────────────────
#   DOCS_DIR / BOARD        —— 源文档目录与目标 HTML 路径
#   DOCS 清单               —— (文件名, 标题, 徽章, 副标题)：顺序/徽章/副标题的 SSOT 在这里，
#                              **改产物 HTML 里的这些字样会被下次 regen 覆盖**
#   INT_WARN                —— 标 kind="内" 的文档在页面上显示的警告文案
#   BADGE_LEGEND            —— 徽章图例（这几个徽章在你的报告里各是什么意思）
#   SECTION_TITLE           —— 源文档区的标题；**唯一不被哨兵拦的一项**，因为它的默认值
#                              是中性的（「源文档全文 · 直接读」），不改也只是不够贴切、
#                              不会印出别的项目的内容。改它能让页面更准。
#   ⚠️ 上面除 SECTION_TITLE 外的每一项都必须与 assert_configured() 检查的项一一对应——
#      那个函数是可执行的，本注释只是描述，不一致时以函数为准。本清单曾漏列
#      INT_WARN / BADGE_LEGEND，而哨兵一直在查它们。
#
# ── 机制区（直接复用，别改坏）─────────────────────────────────────────
#   put()                   —— 标记块整块替换（BEGIN/END 定界）。**禁改成"存在就跳过"**：
#                              那会让脚本常量的修改永远进不了产物（踩过两次）
#   条款锚点 ⚠️两处成对      —— <h2>第 N 条 → id="d{文档号}-c{条号}"；
#                              子条 <p><strong>N.M → id="d{文档号}-c{N}-{M}"。
#                              引用记号在**两个文件里各有一半**：本脚本这条正则负责给
#                              标题打锚点，citation-drawer.html 里名为 `RE` 的正则（搜 `var RE=`）
#                              负责把正文里的记号变成可点引用。源文档不用「第 N 条」体裁
#                              （改成 §7 / 「7. 标题」/ Article N）时**必须同时改两处**。
#                              只改一处的症状是本仓最难查的一类：锚点照打、id 齐全、
#                              静态检查全绿，而组件在正文里一个记号都匹配不到——引用交互
#                              整个是死的，浏览器控制台不报任何错。所以改完记号，判据不是
#                              「脚本跑通了」，是**在浏览器里点开一处引用看抽屉是否定位**。
#   组件内嵌                 —— citation-drawer.html 的 BEGIN…END 块整块烤进 </body> 前
#   同步检查                 —— `--check` 现算源文档与页面是否一致，不持久化派生鲜度值
#   清单外文件警告            —— 防源目录新增文件被静默漏收
#
# 配套纪律（regen 后双向验证 / 叙事反漂移 / 版本锚点 / 两层对接契约）：
#   references/long-lived-report-maintenance.md
#   交互契约 SSOT：references/interaction-components.md（citation-drawer 货架条目）
# ============================================================================

"""把源文档全文重新烤进报告页（s9 区块）+ 内嵌条款引用抽屉组件。

**什么时候要跑**：改完任一源 markdown、或改完 citation-drawer.html 组件之后。

**为什么必须手动跑**：看板是 `file://` 打开的，浏览器在该协议下不能 fetch 本地文件
（CORS），所以全文只能作为快照烤进 HTML。markdown 改了，看板**不会**自动跟着变——
不跑这个脚本就会漂移，而漂移的表现是"看板里的条款和实际要签的不一样"，很难靠肉眼发现。
用 `--check` 当次现算同步状态；不要把可由输入与产物比较得出的"最后生成于"持久化进页面。

**用法**（在本文件所在目录跑；citation-drawer.html 需在同目录）：
    uv run --python 3.12 --with markdown _regen-docs.py
    uv run --python 3.12 --with markdown _regen-docs.py --check

**幂等**：可重复跑。s9 由 <!-- DOCS:BEGIN/END --> 包裹、抽屉组件由
<!-- CITATION-DRAWER:BEGIN/END --> 包裹，每次各自整块替换。
"""
from __future__ import annotations

import argparse
import html
import os
import re
import stat
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("缺 markdown 库。用这条命令跑：\n  uv run --python 3.12 --with markdown _regen-docs.py")

HERE = Path(__file__).resolve().parent
# ⚠️ 下面三项是必填。它们曾经带着某个具体项目的真实值当默认——复制模板的人不改也能跑，
#    于是新报告静默继承了另一个项目的目录名、徽章语义和保密警告文案（含真人姓名）。
#    现在留哨兵值：不改就在启动时报错，而不是安静地做错事。
DOCS_DIR = HERE / "TODO-源文档目录名"          # 例：HERE / "签署稿" 或 HERE（与脚本同目录）
BOARD = HERE / "TODO-目标页面.html"

# 交互外壳组件（SSOT）——从 skill 的 assets/components/ 复制到本目录
COMPONENT_FILE = HERE / "citation-drawer.html"
COMP_BEGIN, COMP_END = "<!-- BEGIN citation-drawer -->", "<!-- END citation-drawer -->"

# 清单驱动：顺序 / 徽章 / 一句话描述都在这里定义。
# kind: 三种徽章的含义**由你的报告定义**，下面 BADGE_LEGEND 里写成一句给读者看的话。
#       别沿用示例语义——它来自一个特定项目（谁签、给谁看），换个报告就是错的。
DOCS: list[tuple[str, str, str, str]] = [
    # (文件名, 显示标题, 徽章 kind, 一句话副标题) —— 顺序即 tab 顺序，这里是 SSOT
    ("TODO-第一份.md", "TODO · 显示标题", "内", "TODO 副标题：这份是什么、给谁"),
]

BADGE = {"签": '<i class="dk dk-sign">签</i>', "读": '<i class="dk dk-read">读</i>', "内": '<i class="dk dk-int">内</i>'}
# 标 kind="内" 的文档在页面上显示的警告。**必须按本报告改写**——它讲的是"这份文件为什么
# 不能外发"，而那个理由每个项目都不同。旧版这里放的是某个项目的具体披露事项（含当事人
# 姓名），任何复制模板的项目只要标了一个"内"就会把它原样印出来。
INT_WARN = ('<div class="dwarn">⚠️ TODO：写清这份文件为什么不能外发'
            '（例如"含我方成本测算与让步储备，对外须另建剥离版"）。</div>')

# 徽章图例，显示在源文档区的 lead 里。含义由本报告定义，见上面 kind 的说明。
BADGE_LEGEND = "TODO：逐个说明徽章含义（例如「内＝内部工作稿，不外发」）"

# 源文档区的标题。默认中性，按你的报告改（"协议全文" / "规格全文" / "会议纪要"…）——
# 它印在读者看得见的地方，写死某一类文档的名字，换个报告就是错的。
SECTION_TITLE = "源文档全文 · 直接读"

BEGIN, END = "<!-- DOCS:BEGIN -->", "<!-- DOCS:END -->"
CD_BEGIN, CD_END = "<!-- CITATION-DRAWER:BEGIN -->", "<!-- CITATION-DRAWER:END -->"


class GenerationError(RuntimeError):
    """输入契约不成立；禁止在这种状态下继续写产物。"""


class IdInventoryParser(HTMLParser):
    """Count semantic HTML ids without matching comments, scripts, or quote style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.counts: dict[str, int] = {}

    def _record(self, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() == "id" and value:
                self.counts[value] = self.counts.get(value, 0) + 1

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def handle_startendtag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)


def semantic_id_counts(text: str) -> dict[str, int]:
    parser = IdInventoryParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        raise GenerationError(f"目标 HTML 无法解析 id：{exc}") from exc
    return parser.counts


def load_component() -> str:
    """读 citation-drawer.html，取 BEGIN…END 之间（含 marker）的整块——交互外壳的 SSOT。"""
    if not COMPONENT_FILE.exists():
        raise GenerationError(
            f"找不到交互组件：{COMPONENT_FILE}\n"
            f"   把 skill 的 assets/components/citation-drawer.html 复制到本目录（抽屉交互靠它）。"
        )
    text = COMPONENT_FILE.read_text(encoding="utf-8")
    if text.count(COMP_BEGIN) != 1 or text.count(COMP_END) != 1:
        raise GenerationError(
            f"组件文件必须且只能包含一组 {COMP_BEGIN} / {COMP_END} 标记。"
        )
    if text.index(COMP_BEGIN) > text.index(COMP_END):
        raise GenerationError("组件文件的 BEGIN 标记位于 END 之后。")
    block = text.split(COMP_BEGIN, 1)[1].split(COMP_END, 1)[0]
    return COMP_BEGIN + block + COMP_END


def assert_configured() -> None:
    """未改配置区就停下——这些值留着模板哨兵时跑出来的页面是错的，但不会报错。"""
    todos = []
    if "TODO" in DOCS_DIR.name: todos.append("DOCS_DIR")
    if "TODO" in BOARD.name: todos.append("BOARD")
    if any("TODO" in x for doc in DOCS for x in doc): todos.append("DOCS 清单")
    if "TODO" in INT_WARN: todos.append("INT_WARN")
    if "TODO" in BADGE_LEGEND: todos.append("BADGE_LEGEND")
    if todos:
        raise GenerationError(
            "配置区还是模板默认值：" + "、".join(todos) + "\n"
            "   这些值不改也能跑，但产出的页面会带着模板示例的目录名、徽章语义和保密警告。"
        )


def build_section() -> str:
    md = markdown.Markdown(extensions=["tables", "sane_lists"])
    tabs, panes = [], []
    for i, (fn, title, kind, sub) in enumerate(DOCS):
        path = DOCS_DIR / fn
        if not path.exists():
            raise GenerationError(f"缺文件：{path}\n   清单与磁盘不一致，先核对 DOCS 列表。")
        body = md.convert(path.read_text(encoding="utf-8"))
        md.reset()
        # 给「第 N 条」标题打锚点，供引用弹层定位（d<文档序号>-c<条号>）
        body = re.sub(r"<h2>第\s*(\d+)\s*条", lambda m: f'<h2 id="d{i}-c{m.group(1)}">第 {m.group(1)} 条', body)
        # 子条锚点。引用密集的审阅页里近半引用是子条（「第 8.3 条」），只有母节锚点时
        # 抽屉会定位到母节开头、把读者扔在目标上方一屏多，而状态栏照报「已定位并高亮该条」。
        # markdown 把 `**8.3 标题**` 渲染成 <p><strong>8.3 标题</strong></p>，据此打锚点。
        body = re.sub(r"<p><strong>(\d+)\.(\d+)([a-z]?)\s",
                      lambda m: f'<p id="d{i}-c{m.group(1)}-{m.group(2)}{m.group(3)}">'
                                f'<strong>{m.group(1)}.{m.group(2)}{m.group(3)} ', body)
        # 外部引用豁免：指向外部法条/外部文件的编号必须标 .nocite，否则会被 linkify 链到
        # 本文档的同号条款。踩过一个自我演示的例子：正文写着「这是架构 SSOT §3.1（不是本
        # 协议的 §3.1）」，两个 §3.1 都成了链接、点下去正好落到本协议 §3.1——链接在演示
        # 它旁边那句话警告的错误。组件侧配套：.nocite 已在 linkify 的 acceptNode 排除列表里。
        #   判据一 · 前缀：把本项目实际用到的外部来源名填进去（示例为香港法规与架构文档）
        EXT_PREFIXES = r"POBO|架构\s*SSOT|不是本协议的"
        body = re.sub(rf"((?:{EXT_PREFIXES})\s*[§第]\s*\d+(?:\.\d+[a-z]?)?(?:\(\d+\))?\s*条?)",
                      lambda m: f'<span class="nocite">{m.group(1)}</span>', body)
        #   判据二 · 形态：法条写作 §N(M)，而本类文档的子条写作 N.M——带圆括号子号的必是
        #   外部条文。加这条是因为只靠前缀会漏：「我方作为『提供利益方』在 §9(2) 下同罪」
        #   这句没有前缀，漏网后被链到了本文档 §9。启用前先确认本文档自身不用该形态。
        body = re.sub(r"(?<!>)(§\s*\d+\(\d+\))",
                      lambda m: f'<span class="nocite">{m.group(1)}</span>', body)
        act = " active" if i == 0 else ""
        tabs.append(
            f'<button type="button" class="dtab{act}" data-i="{i}" id="doc-tab-{i}" '
            f'role="tab" aria-selected="{"true" if i == 0 else "false"}" '
            f'aria-controls="doc-panel-{i}" tabindex="{0 if i == 0 else -1}">{BADGE[kind]}'
            f'<span class="dt-t">{html.escape(title)}</span>'
            f'<span class="dt-s">{html.escape(sub)}</span></button>'
        )
        warn = INT_WARN if kind == "内" else ""
        panes.append(
            f'<div class="dpane{act}" data-i="{i}" id="doc-panel-{i}" role="tabpanel" '
            f'aria-labelledby="doc-tab-{i}" aria-hidden="{"false" if i == 0 else "true"}">{warn}'
            f'<div class="dsrc">{html.escape(fn)}</div>'
            f'<article class="doc">{body}</article></div>'
        )
    return f"""{BEGIN}
  <section id="s9">
    <h2>{SECTION_TITLE}</h2>
    <p class="lead">下面是 <code>{html.escape(DOCS_DIR.name)}/</code> 的全部文本，与磁盘文件同源（改了源文件就重跑本脚本，否则页面与实际不一致）。{BADGE_LEGEND}</p>
    <div class="docwrap">
      <div class="dnav" role="tablist" aria-label="源文档">{''.join(tabs)}</div>
      <div class="dbody">{''.join(panes)}</div>
    </div>
    <p class="note">这里是 manifest 清单中源文档的生成快照；文件分类与读者范围以 manifest 的逐项声明为准，页面不持久化“已复核多少”“最后生成于”等汇总状态。改过源 markdown 或抽屉组件后重跑 <code>_regen-docs.py</code>；交付前运行 <code>_regen-docs.py --check</code> 现算同步状态。</p>
  </section>
{END}"""


def marker_state(text: str, begin: str, end: str, label: str) -> bool:
    """Return True for one valid marker pair, False for none; reject every ambiguous state."""
    begin_count, end_count = text.count(begin), text.count(end)
    if begin_count != end_count or begin_count > 1:
        raise GenerationError(
            f"{label} 标记不平衡或重复：BEGIN={begin_count}, END={end_count}。"
        )
    if begin_count == 1 and text.index(begin) > text.index(end):
        raise GenerationError(f"{label} 的 BEGIN 标记位于 END 之后。")
    return begin_count == 1


def put(text: str, begin: str, end: str, block: str, anchor: str) -> str:
    """标记块整块替换——存在则替换 BEGIN…END 之间，否则在 anchor 前首次注入。
    禁改成"存在就跳过"：那会让脚本/组件的修改永远进不了产物（踩过两次），脚本就不是 SSOT 了。"""
    payload = f"{begin}{block}{end}"
    if marker_state(text, begin, end, f"{begin}…{end}"):
        head, rest = text.split(begin, 1)
        _, tail = rest.split(end, 1)
        return head + payload + tail
    if text.count(anchor) != 1:
        raise GenerationError(
            f"首次注入要求唯一锚点 {anchor!r}，实际找到 {text.count(anchor)} 处。"
        )
    return text.replace(anchor, payload + anchor, 1)


def put_section(text: str, section: str) -> str:
    if marker_state(text, BEGIN, END, "DOCS 区块"):
        pre, rest = text.split(BEGIN, 1)
        _, post = rest.split(END, 1)
        return pre + section + post

    legacy_count = semantic_id_counts(text).get("s9", 0)
    if legacy_count:
        raise GenerationError(
            f"发现 {legacy_count} 个没有 DOCS marker 包裹的旧版 #s9。"
            "拒绝猜测嵌套 HTML 的结束边界；请先人工核对并给完整区块加 marker。"
        )

    footer_anchor = "  <footer>"
    if text.count(footer_anchor) != 1:
        raise GenerationError(
            f"新建 s9 要求唯一锚点 {footer_anchor!r}，实际找到 {text.count(footer_anchor)} 处。"
        )
    return text.replace(footer_anchor, section + "\n" + footer_anchor, 1)


def validate_output(text: str) -> None:
    required_pairs = (
        (CD_BEGIN, CD_END, "抽屉注入区"),
        (COMP_BEGIN, COMP_END, "抽屉组件"),
        (BEGIN, END, "DOCS 区块"),
    )
    for begin, end, label in required_pairs:
        if not marker_state(text, begin, end, label):
            raise GenerationError(f"产物缺少 {label} 标记。")
    id_counts = semantic_id_counts(text)
    # 条款锚点必须真的产出了。--check 是自洽比较（expected = render(current)），
    # 它能发现「产物过期」，但发现不了「生成器什么都没打」——因为零锚点会在比较的
    # 两侧同样出现。源文档一旦换了标题体裁（`## 第 N 条` 改成 `### `、粗体段落、
    # 「第一条」中文数字），锚点正则就静默失配，页面里所有引用变成死链，而 --check
    # 从下一次 regen 起永久绿。唯一的症状要点开一个引用才看得见。
    anchors = sum(1 for k in id_counts if re.fullmatch(r"d\d+-c\d+(-\d+[a-z]?)?", k))
    if DOCS and anchors == 0:
        raise GenerationError(
            "产物里一个条款锚点都没有（形如 d0-c1）。\n"
            "   多半是源文档的条标题体裁与 build_section 里的锚点正则对不上——\n"
            "   正则找的是 <h2>第 N 条 与 <p><strong>N.M，请核对源 markdown 的实际写法。\n"
            "   放着不管的后果：页面所有引用都是死链，而 --check 会一直报一致。"
        )
    duplicates = sorted(element_id for element_id, count in id_counts.items() if count > 1)
    if duplicates:
        raise GenerationError(f"产物包含重复 HTML id：{', '.join(duplicates)}。")
    s9_count = id_counts.get("s9", 0)
    drawer_count = id_counts.get("drawer", 0)
    if s9_count != 1:
        raise GenerationError(f"产物必须且只能有一个 #s9，实际找到 {s9_count} 处。")
    if drawer_count != 1:
        raise GenerationError(
            f"产物必须且只能有一个 #drawer，实际找到 {drawer_count} 处。"
        )


def atomic_write(path: Path, text: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def render(current: str) -> str:
    rendered = put(current, CD_BEGIN, CD_END, "\n" + load_component() + "\n", "</body>")
    rendered = put_section(rendered, build_section())
    validate_output(rendered)
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description="同步源文档与 citation-drawer 到报告 HTML。")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只现算并检查 BOARD 是否与源文档/组件一致；不写文件。",
    )
    args = parser.parse_args()

    # 配置哨兵必须在这里调用。加了函数却不接线，跟没加一样——这一条是刚踩过的：
    # 上面那个 assert_configured 定义完之后零调用，直到 grep 才发现。
    assert_configured()

    if not BOARD.exists():
        raise GenerationError(f"找不到看板：{BOARD}")

    # 清单外的 markdown 提醒（防新增文件被漏掉）
    listed = {fn for fn, *_ in DOCS}
    on_disk = {p.name for p in DOCS_DIR.glob("*.md")} - {"0-README.md"}
    if extra := on_disk - listed:
        print(f"⚠️  源文档目录有清单外的文件，未纳入页面：{sorted(extra)}\n   要收进去就编辑本脚本的 DOCS 列表。")

    current = BOARD.read_text(encoding="utf-8")
    expected = render(current)
    if args.check:
        if expected != current:
            raise GenerationError(
                f"{BOARD.name} 与源文档或组件不一致；运行不带 --check 的命令重新生成。"
            )
        print(f"✅ {BOARD.name} 与当前源文档、manifest 和抽屉组件一致。")
        return

    if expected == current:
        print(f"✅ {BOARD.name} 已同步，无需改写。")
        return
    atomic_write(BOARD, expected)
    print(f"✅ 已原子同步源文档 + 抽屉组件 → {BOARD.name}。")


if __name__ == "__main__":
    try:
        main()
    except GenerationError as exc:
        sys.exit(f"❌ {exc}")

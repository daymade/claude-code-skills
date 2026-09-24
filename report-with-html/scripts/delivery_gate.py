#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "html5lib"]
# ///
"""delivery_gate.py — 把「只有作者自己说做了才算做了」的三道判断步骤，改成机器可验的产物步骤。

用法:
    uv run scripts/delivery_gate.py init  page.html [--height 9600] [--force]
    uv run scripts/delivery_gate.py check page.html

为什么存在（2026-08-05 事故推导，请连同这段一起读）:
    一次交付里，这个 skill 工作流中**会留下外部产物**的步骤全部被执行了
    （render / crop / 逐段 Read / 独立审阅 agent / 窄屏实测），而**唯一裁判是作者自己**
    的步骤一条没做：先造量纲、遮字自测、data-visualization-discipline 的九条交付闸、
    阶段 1 的四项交接检查。九条编号连排的闸门刚读完就一条没跑——这不是忘，是
    「读到了」在作者那里结算成了「做过了」。产物是这一类失败唯一的解药：
    交不出 masked PNG，就没法声称遮字自测跑过。

    所以本脚本不判断"图好不好"（那是人和独立审阅的活），它只保证:
      ① 遮字副本被真的渲染出来了，且比页面新   → 遮字自测无法跳过
      ② 每个几何都声明了自己编码的量纲          → 「先造量纲」无法跳过
      ③ 九条闸 + 阶段 1 四问都被逐条写了答案     → 交付闸无法整体略过
      ④ 页面在填完闸门之后没有再被改过          → 「审后又改」无法蒙混

这不是本地发明，先说清它的出处（2026-08 检索）:
    ① 遮字自测 = **squint test**，UX 领域的既有方法（NN/g 有专门条目；做法是眯眼让细节消失、
       只剩明暗与块面，看主焦点还在不在）。**Polypane 已把它产品化**——`Placeholdifier`
       把文字与图片变成纯色块、只留版式层级，另有远视模拟做自动模糊。本脚本的遮字副本
       就是 Placeholdifier 的 headless 版：之所以不直接用 Polypane，是它是交互式 GUI 浏览器，
       产不出 agent 循环里能被 Read 的 PNG 产物。
       https://polypane.app/blog/debug-your-visual-hierarchy-with-the-squint-test/
       https://www.nngroup.com/videos/squint-test/
    ② 「清单没填完就不许合」这类闸，成熟工具是 **Danger**（danger.systems，口号正是
       "Stop Saying 'You Forgot To…'"）与 CodeRabbit pre-merge checks。**没有用它们**，
       因为那两者都绑在 merge 时机与 PR 对象上，而这道闸要在**交付前、按单个产物**跑，
       且要能被本地 agent 直接调用。若将来这套要变成仓库级 merge gate，Danger 是正解，
       别在这个脚本上加分支。
    ③ HTML 解析用 **html5lib**（WHATWG 算法，与浏览器同一套）而非 stdlib 的 html.parser——
       后者不做隐式闭合，<br>/<img>/省略的 </li></p> 都会让手工深度计数失衡，
       把无辜的兄弟几何误报成「嵌套」。三轮独立审阅里这类误杀换了五扇门进来，
       根因是解析器不是判据，所以换解析器而不是继续打补丁。
    本脚本自身因此只是胶水：渲染委托给同目录 render_report.sh，解析委托给 html5lib；
    它编码的是**本 skill 自己那九条闸与 data-geometry 契约**，换个项目不适用。

它抓不到什么——写在这里，因为一道你以为覆盖全了的闸最危险（2026-08 独立审阅实测）:
    ① **扫描器只读静态标记**。内联百分比只认一张属性表
       （width/height/left/top/right/bottom/inset/flex-basis）；CSS 类里的百分比宽
       （.w73{width:73%}）、CSS 变量、linear-gradient 的百分比色标、transform 百分比、
       以及**图表库在运行时注入 DOM 的图**（<div id=chart> + JS）——全部逃检。
       要真覆盖得读计算样式甚至跑 JS，那需要一个浏览器，而这道闸必须能在没有浏览器的环境里跑。
    ② **「一个标记罩住好几张独立图」只在 ≥2 张 svg/canvas 时能机械判定。** 罩住一堆
       CSS 条的情形分不开：刻度轴、堆叠条本来就是一个几何含几十个百分比部件，拿数量当
       判据会误杀合规页面。init 会把每个几何罩了多少部件打印出来，但不据此判红。
    ③ **填了什么它不看。** 把所有槽位机械替换成"已核对"就能绿——脚本能证明步骤发生过，
       证明不了答案是看着图写的。
    ①②③ 都由 SKILL.md 验收清单第 5 项接手：出示产物 → **gate 表行数 vs 遮字图里可见的
    几何数对账** → 随机抽一格答案回到遮字图核对。那一项是这道闸唯一的裁判，
    没有它，本脚本只对愿意跑它的人存在。

判定为什么不空转（这一点比上面四条更要紧）:
    最容易写坏的检查，是「没有标记就默认通过」——那样作者只要不加标记就永远绿。
    所以 ② 的实现是**先独立发现候选几何、再要求每个候选都被标记**：任何 <svg>/<canvas>、
    以及任何带内联百分比尺寸的元素（width/height/left/top/right/bottom/inset/flex-basis），
    都算候选。纯版面用的
    百分比盒子必须显式标 data-layout 才被排除——**排除是可见的，不是静默的**。

参数取值依据:
    --height 默认 9600  : 与 render_report.sh 同量级；页面更长时由调用方显式传。
    空洞阈值 120 CSS px : visualization-patterns.md「版面填充纪律」的可测化下限；
                          比一个标准卡片间距(42px)大得多，不会把正常留白判成空洞。
    墨密度 0.012        : 实测暖纸底页面，正文带 ≈0.09、纯背景带 <0.003；
                          0.012 落在两者之间且离两边都远，抗字体渲染差异。
    占位符 ‹待填›       : 单字符书名号包裹，正文几乎不会自然出现，grep 唯一。
"""
from __future__ import annotations

import argparse
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLACEHOLDER = "‹待填›"
VOID_MIN_CSS_PX = 120
INK_THRESHOLD = 0.012
BAND_CSS_PX = 40

MASK_CSS = """
  /* ===== delivery_gate.py 注入：遮字自测，只留几何 ===== */
  *{color:transparent !important;}
  text,tspan{fill:transparent !important;}
  nav{display:none !important;}
"""

# data-visualization-discipline 阶段 5 的九条交付闸。
#
# **这里曾经是一张手抄的常量表，注释还写着「标题为该 skill 原文」——而它已经漂了。**
# 独立审计对着原文抓出闸 3 丢了「每张图是否都遵守阶段 2 定下的那三个值」整个子项；
# 换成生成之后当场又暴露第二处：闸 6 丢了「若未分层，必须写…三样」整个子句，
# 闸 5 / 闸 8 的产物行则根本是另一段话。手抄两次、转述两次，两次都自认为在照抄。
#
# 所以现在**没有副本可以手改**：这张表由 `scripts/sync_delivery_gates.py` 从
# data-visualization-discipline/SKILL.md 生成进 assets/delivery-gates.json。
# 要改内容 → 改那边的 SSOT → 重跑 generator。
GATES_JSON = Path(__file__).resolve().parent.parent / "assets" / "delivery-gates.json"


def load_gates() -> list[tuple[str, str, str]]:
    """读生成好的九条闸。缺失 / 损坏一律 fail-fast，**不留任何硬编码兜底**。

    留兜底就等于把手抄的副本又请回来了，而且是一个只在出错时才生效、
    因此永远不会被人看见的副本——那比原来更糟。
    """
    if not GATES_JSON.is_file():
        sys.exit(f"❌ 找不到 {GATES_JSON.name}——它由仓级 scripts/sync_delivery_gates.py 生成，"
                 f"跑一次 `python3 scripts/sync_delivery_gates.py --write`")
    try:
        gates = json.loads(GATES_JSON.read_text(encoding="utf-8"))["gates"]
        return [(g["n"], g["title"], g["deliverable"]) for g in gates]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        sys.exit(f"❌ {GATES_JSON.name} 读不出九条闸（{type(e).__name__}: {e}）——重跑 generator")

# 下面这条的存在本身是一条教训：1.17.1 把「数值与坐标同一脚本产出」写进了 SKILL.md，
# 但**没给它任何机器消费者**——而 1.17.0 的全部论旨正是「唯一裁判是作者的步骤迟早被跳过」。
# 独立审计一眼看穿：这条新规则是下一个会被跳过的候选，它这次被执行纯粹因为作者刚被烫过。
# 更准确的判别变量也是审计给的：不是「有没有产物」（九条闸本来就要求产物，照样被跳），
# 是「这个产物有没有下游消费者或机器阻断」。所以这里给它装一个最小的消费者：
# 要一个路径，然后去 stat 它。挡不住填个假路径的人，但挡得住「忘了这回事」——
# 而后者才是它真正的失效模式。
COORD_SCRIPT_LABEL = "坐标产出脚本"

# 「读者已知清单」的消费者，见 references/audience-triage.md。这条和 COORD_SCRIPT_LABEL
# 同一个理由：写在 SKILL.md 里但没人 stat 的规则，是下一个被跳过的候选。这里的机器执法点
# 是「声明的词必须真的出现在页面里」——防止拿一堆没在页面里用过的词凑数糊弄这一栏。
AUDIENCE_LABEL = "读者已知清单"

STAGE1 = [
    ("受众×形态", "汇报（→静态结论图）还是操盘（→交互工具）？"),
    ("北极星指标", "哪个指标，凭什么是它（判据是受众做决策时直接依赖它，不是数最大）"),
    ("每图一句结论", "在下面的量纲表里逐个写"),
    ("对照清单", "每个要上屏的数，它的对照物是谁（vs 上周 / vs 标杆 / 同轴同行的另一个数）"),
    (COORD_SCRIPT_LABEL,
     "SKILL.md step 3 要求「数值与坐标出自同一个脚本」。写它的路径（相对页面或绝对），"
     "check 会验这个文件在不在。页面没有任何由计算值定位的几何 → 写「不适用：<为什么>」"),
    (AUDIENCE_LABEL,
     "只有当「受众×形态」声明的是内部/单一/已知情读者（不是陌生路人）才要填："
     "该读者已经知道、不需要本页解释的具体术语/脚本/系统，逐个用反引号标出，如 "
     "`verify_gate`、`rescue_rendered.py`。必须在 step 9 第一次派独立审阅之前写好——"
     "审阅回来再回填等于先射箭画靶，SKILL.md 的 audience triage 机制要求这份清单比"
     "第一轮审阅记录更早。check 会验每个反引号词是否真的出现在页面正文里。声明的受众"
     "就是陌生路人、不需要这份清单 → 写「不适用：<为什么>」"),
]


# ---------------------------------------------------------------- 几何发现
#
# 用 html5lib 而不是 stdlib 的 html.parser，原因是踩出来的：
#   html.parser 不实现 HTML5 的隐式闭合。空元素（<br>/<img>）不发 endtag、
#   可省略闭合标签（</li>/</p>）不会被自动补——手工维护的深度计数因此失衡，
#   于是**下一个兄弟几何被误报成「嵌在另一个几何里」**，报错还指向无辜的元素。
#   这类误杀在三轮独立审阅里连续出现五次，每次换一扇门进来；根因不是判据写错，
#   是解析器结构上就没法在真实 HTML 上跟踪嵌套。
#   html5lib 实现 WHATWG 解析算法（与浏览器同一套），拿到的是真实 DOM 形状。
#   慢 20 倍在这里无所谓：一次解析一个文件，旁边还跑着几秒的 Chrome 渲染。
#   https://html5lib.readthedocs.io/

PCT_RE = re.compile(
    r"(?:^|;)\s*(width|height|left|top|right|bottom|inset|flex-basis)\s*:\s*([\d.]+)%", re.I)
SKIP_TAGS = {"td", "th", "col", "colgroup", "table"}
PAGE_LEVEL = {"body", "html", "main", "article"}


def _local(tag: object) -> str:
    """html5lib 会给元素带命名空间（svg 尤其）；只要本地名。"""
    t = tag if isinstance(tag, str) else ""
    return t.rsplit("}", 1)[-1].lower()


def _is_decorative(attrs: dict) -> bool:
    """装饰性图元的正式声明是 aria-hidden="true"（WAI-ARIA），不是本脚本发明的逃生门。

    不给这个出口的话，页面上每个装饰图标都要被注解成"几何"，而给它标 data-layout
    语义又不通。一个会误杀合规输入的闸，代价是操作者学会反射性绕过整道闸。
    """
    return (attrs.get("aria-hidden") or "").strip().lower() == "true"


def _is_candidate(tag: str, attrs: dict) -> bool:
    if tag in ("svg", "canvas"):
        return not _is_decorative(attrs)
    if tag in SKIP_TAGS:
        return False
    for _prop, val in PCT_RE.findall(attrs.get("style") or ""):
        if abs(float(val) - 100.0) > 1e-9:      # 100% 是撑满父容器的布局惯例，不是量的编码
            return True
    return False


class GeometryScan:
    """先独立发现候选几何，再要求每个候选被标记——避免"没标记就默认通过"的空转。"""

    def __init__(self) -> None:
        self.marked: list[tuple[str, str]] = []
        self.unmarked: list[str] = []
        self.layout_optouts: list[str] = []
        self.page_level_marks: list[str] = []
        self.nested_marks: list[str] = []
        self.wrappers: list[str] = []
        self.volumes: list[tuple[str, int, int]] = []
        self.dup_names: list[str] = []


def _line_of(src_lines: list[str], tag: str, attrs: dict) -> int:
    """html5lib 的树不带行号；按标签名 + 一个尽量唯一的属性片段回原文找，纯诊断用。

    探针顺序是承重的：`data-geometry` 的值按定义在页内唯一（重名/嵌套标记本身会被判红），
    而 class **天然会撞**——两张图共用 `card scrollx` 是完全正常的写法。先探 class 就会
    把后一张图的行号报成前一张的行号。**诊断信息指错地方比没有诊断更糟**：它把人送去
    检查一个没问题的元素，而真正要看的那个从未被看。
    （实测：一页里第 2 个 `class="card scrollx"` 的几何，行号被报成第 1 个的。）
    """
    geo = (attrs.get("data-geometry") or "").strip()
    style = (attrs.get("style") or "")[:30]
    cls = (attrs.get("class") or "")[:30]
    # 单双引号都要探：html5lib 的树里引号已经归一化没了，我们是拿字面量回**源文本**去 grep，
    # 而 `data-geometry='X'` 是完全合法的 HTML。只探双引号会静默失配、回落到 class ——
    # 于是本函数刚修掉的那个「两张图共用 class 就指错行」原样复活。
    probes = [f'data-geometry="{geo}"', f"data-geometry='{geo}'"] if geo else []
    for probe in (*probes, style, cls):
        if not probe:
            continue
        for n, line in enumerate(src_lines, 1):
            if "<" + tag in line and probe in line:
                return n
    for n, line in enumerate(src_lines, 1):
        if "<" + tag in line:
            return n
    return 0


def _describe(tag: str, attrs: dict, line: int) -> str:
    loc = f"L{line} " if line else ""
    return f'{loc}<{tag} class="{attrs.get("class") or ""}" style="{(attrs.get("style") or "")[:60]}">'


def _count_media(node, top_only: bool = True) -> int:
    """数这个几何里有几张**独立**图。

    嵌套 <svg><svg> 是 SVG 规范允许的 viewport 裁剪、是同一张图的一部分，
    所以只数不在别的 svg 里面的那些；并列的两个内层 svg 同样属于外层那一张。
    """
    n = 0
    for child in node:
        t = _local(child.tag)
        if t in ("svg", "canvas") and not _is_decorative(child.attrib):
            n += 1
            continue          # 不进它内部
        n += _count_media(child)
    return n


def _count_pct(node) -> int:
    n = 0
    for child in node:
        if _is_candidate(_local(child.tag), child.attrib):
            n += 1
        n += _count_pct(child)
    return n


def scan_geometries(html_path: Path) -> GeometryScan:
    import html5lib  # noqa: PLC0415 — 只有静态扫描用得上

    src = html_path.read_text(encoding="utf-8")
    lines = src.splitlines()
    root = html5lib.parse(src, namespaceHTMLElements=False)
    out = GeometryScan()

    def walk(node, in_marked: bool) -> None:
        for el in node:
            tag = _local(el.tag)
            attrs = el.attrib
            if "data-geometry" in attrs:
                name = (attrs.get("data-geometry") or "").strip()
                line = _line_of(lines, tag, attrs)
                if tag in PAGE_LEVEL:
                    out.page_level_marks.append(f'L{line} <{tag} data-geometry="{name}">')
                if in_marked:
                    out.nested_marks.append(f'L{line} <{tag} data-geometry="{name}">')
                else:
                    # 名字必须页内唯一。两个理由都承重：① gate 表按名字与几何一一对应，
                    # 重名会让「9 个几何 = 9 行」这个对账变成假的（两行指同一个名字，
                    # 而某个几何根本没人写）；② _line_of 拿名字当探针回源文本定位，
                    # 重名时第二个几何的行号会指回第一个——正是它刚修掉的那个病。
                    # 这个不变量一度只写在注释和 commit message 里、**没有任何代码执法**，
                    # 由独立审计实测抓出（两个同名几何 exit 0 绿灯通过）。
                    if any(name == n for n, _ in out.marked):
                        out.dup_names.append(name)
                    out.marked.append((name, (attrs.get("data-derived-from") or "").strip()))
                    nsvg, npct = _count_media(el), _count_pct(el)
                    desc = f'L{line} data-geometry="{name}"'
                    out.volumes.append((desc, nsvg, npct))
                    # 只有「罩住 ≥2 张独立图」是零误杀的包裹信号。
                    # 「百分比后代很多」不是——刻度轴、堆叠条本来就是一个几何含几十个部件，
                    # 拿它当判据会把合规页面判红。那一类机械上分不开，
                    # 改由 SKILL.md 验收第 5(b) 项人工对账（gate 表行数 vs 遮字图可见几何数）。
                    if nsvg >= 2:
                        out.wrappers.append(
                            f"{desc} 罩住了 {nsvg} 张独立 svg/canvas —— 一个 data-geometry 应对应一张图")
                walk(el, True)
            elif not in_marked:
                if "data-layout" in attrs:
                    out.layout_optouts.append(f'<{tag} data-layout="{attrs.get("data-layout")}">')
                elif _is_candidate(tag, attrs):
                    out.unmarked.append(_describe(tag, attrs, _line_of(lines, tag, attrs)))
                    continue          # 图内部不再往下找候选
                walk(el, False)
            else:
                walk(el, True)

    walk(root, False)
    return out


_HIDDEN_TAGS = {"script", "style", "noscript", "template"}
_DISPLAY_NONE_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)


def _is_hidden_from_reader(tag: str, attrs: dict) -> bool:
    """内联可判的"读者看不见"信号。不是完整覆盖——见调用处的说明。"""
    if attrs.get("hidden") is not None:
        return True
    if _is_decorative(attrs):
        return True
    style = attrs.get("style") or ""
    return bool(_DISPLAY_NONE_RE.search(style))


def extract_visible_text(html_path: Path) -> str:
    """页面正文里"读者读到时会看见"的文字，供「读者已知清单」核对术语是否真的在读者面前用过。

    只排除内联可判的隐藏信号（<script>/<style>/<noscript>/<template>、hidden 属性、
    aria-hidden="true"、内联 style 里的 display:none/visibility:hidden）。**排不掉**
    通过 CSS 类名/外部样式表隐藏的内容——那需要跑浏览器算计算样式，这道闸和
    scan_geometries 一样刻意不依赖浏览器。这不是缺陷，是同一个已知边界：
    挡得住"顺手塞一个看不见的属性"，挡不住"专门写一条 CSS 规则来骗这道检查"，
    后者留给 SKILL.md 验收清单第 10 项的独立读者复核。
    """
    import html5lib  # noqa: PLC0415

    src = html_path.read_text(encoding="utf-8")
    root = html5lib.parse(src, namespaceHTMLElements=False)
    out: list[str] = []

    def walk(node) -> None:
        for el in node:
            # HTML 注释/处理指令的 .tag 不是字符串（html5lib 用 ElementTree.Comment 之类的
            # 可调用对象当 tag），_local() 会把它兜底成 ""——那会落进「未隐藏」分支，
            # 于是 <!-- 注释里的任何文字 --> 被当成读者能看到的正文。必须先单独排除。
            if not isinstance(el.tag, str):
                if el.tail:
                    out.append(el.tail)
                continue
            tag = _local(el.tag)
            # el 自己被隐藏只吞掉它的 .text 和子树；.tail 是它闭合标签之后的兄弟文字，
            # 就算 el 本身看不见，.tail 仍在读者能看到的流里，不能一起吞掉。
            if not (tag in _HIDDEN_TAGS or _is_hidden_from_reader(tag, el.attrib)):
                if el.text:
                    out.append(el.text)
                walk(el)
            if el.tail:
                out.append(el.tail)

    walk(root)
    return "".join(out)


# ---------------------------------------------------------------- 渲染
def _skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def render(src: Path, out_png: Path, height: int) -> None:
    renderer = _skill_dir() / "scripts" / "render_report.sh"
    if not renderer.is_file():
        sys.exit(f"❌ 找不到渲染器: {renderer}")
    res = subprocess.run(
        [str(renderer), str(src), str(out_png), "1300", str(height)],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not out_png.is_file():
        sys.stderr.write(res.stdout + res.stderr)
        sys.exit(f"❌ 渲染失败: {src}")


def inject_mask(src: str) -> str:
    """把遮字 CSS 注进页面。三种落点，按优先级——不能因为页面没有内联 <style> 就整个失败。"""
    if "</style>" in src:
        return src.replace("</style>", MASK_CSS + "</style>", 1)
    block = "<style>" + MASK_CSS + "</style>\n"
    if "</head>" in src:
        return src.replace("</head>", block + "</head>", 1)
    return block + src   # 无 head 的片段式页面：置顶即可，后续规则同样被 !important 压过


def render_masked(page: Path, out_png: Path, height: int) -> None:
    """把文字全部透明化后重渲一次——遮字自测的那份产物。"""
    masked = inject_mask(page.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / (page.stem + "__masked.html")
        tmp.write_text(masked, encoding="utf-8")
        render(tmp, out_png, height)


# ---------------------------------------------------------------- 空洞扫描
def scan_voids(png: Path) -> tuple[list[tuple[int, int]], float]:
    """返回 (空洞区间列表[CSS px], 墨密度中位数)。测量，不判断。"""
    from PIL import Image  # noqa: PLC0415  — 延迟导入，check 子命令不需要它

    im = Image.open(png).convert("L")
    w, h = im.size
    px = im.load()
    dpr = 2 if w >= 2000 else 1
    band = BAND_CSS_PX * dpr
    margin = 120

    densities: list[tuple[int, float]] = []
    for y0 in range(0, h, band):
        ink = total = 0
        for y in range(y0, min(y0 + band, h), 4 * dpr):
            for x in range(margin, w - margin, 6 * dpr):
                total += 1
                if px[x, y] < 235:
                    ink += 1
        if total:
            densities.append((y0 // dpr, ink / total))

    # 内容底部之后的纯背景不算空洞
    last_ink = max((cy for cy, d in densities if d >= INK_THRESHOLD), default=0)
    densities = [(cy, d) for cy, d in densities if cy <= last_ink]

    voids: list[tuple[int, int]] = []
    run: tuple[int, int] | None = None
    for cy, d in densities:
        if d < INK_THRESHOLD:
            run = (cy, cy) if run is None else (run[0], cy)
        else:
            if run and run[1] - run[0] + BAND_CSS_PX >= VOID_MIN_CSS_PX:
                voids.append(run)
            run = None
    if run and run[1] - run[0] + BAND_CSS_PX >= VOID_MIN_CSS_PX:
        voids.append(run)

    vals = sorted(d for _cy, d in densities)
    median = vals[len(vals) // 2] if vals else 0.0
    return voids, median


# ---------------------------------------------------------------- gate 文件
def gate_path(page: Path) -> Path:
    return page.with_suffix(page.suffix + ".gate.md")


_INLINE_CODE = re.compile(r"`[^`]*`")


def unfilled_lines(text: str) -> list[tuple[int, str]]:
    """找出真正的待填槽位。

    行内代码里的占位符**不算**——gate 文件的说明行本身要引用这个记号
    （"每一处 `‹待填›` 都必须换成实际内容"），若把它也数进去，这道闸从生成那一刻起
    就永远为红。一个永远红的闸门等于没装（而且更糟：它训练人反射性绕过）。
    判据因此是「裸露的占位符才是槽位，被反引号包起来的是在谈论它」。
    """
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER in _INLINE_CODE.sub("", line):
            out.append((i, line.strip()[:70]))
    return out


def _prev_carry_block(tail: str) -> str:
    """从「上一轮的答案」那一节里取回被 ``` 围起来的正文。

    只在当前 gate 文件本身是空模板时用得上——见 cmd_init 里的注释。
    """
    if "```" not in tail:
        return ""
    inner = tail.split("```", 1)[1]
    return inner.rsplit("```", 1)[0].strip() if "```" in inner else inner.strip()


def build_gate(page: Path, geo: GeometryScan, voids, median: float,
               png: Path, masked: Path) -> str:
    L: list[str] = []
    A = L.append
    A(f"# 交付闸 · {page.name}")
    A("")
    A("> 本文件由 `delivery_gate.py init` 生成，由 `delivery_gate.py check` 校验。")
    A(f"> **每一处 `{PLACEHOLDER}` 都必须换成实际内容**，否则 check 不过；")
    A("> 页面在填完之后又被修改，check 也会不过（防「审后又改」）。")
    A("")
    A("## 阶段 1 · 交接检查（动数据之前就该有的几样）")
    A("")
    for name, hint in STAGE1:
        A(f"- **{name}** — {hint}")
        A(f"  > {PLACEHOLDER}")
    A("")
    A("## 量纲声明 · 每个几何编码的是什么量")
    A("")
    A("> 「先造量纲」这一步的产物。每个几何在 HTML 里带 `data-geometry` 与 `data-derived-from`，")
    A("> 下表逐个写它遮字之后能读出什么、和它旁边那句结论对不对得上。")
    A("")
    A("| 几何 | data-derived-from（量纲） | 遮字后读出的关系 | 与结论句是否一致 |")
    A("|---|---|---|---|")
    if geo.marked:
        for name, derived in geo.marked:
            d = derived or f"**{PLACEHOLDER}（HTML 里缺 data-derived-from）**"
            A(f"| {name or PLACEHOLDER} | {d} | {PLACEHOLDER} | {PLACEHOLDER} |")
    else:
        A(f"| {PLACEHOLDER} | {PLACEHOLDER} | {PLACEHOLDER} | {PLACEHOLDER} |")
    A("")
    A("## 版面填充（本脚本实测，非人工填写）")
    A("")
    A(f"- 墨密度中位数：`{median:.3f}`")
    if voids:
        A(f"- **检出 {len(voids)} 处 ≥{VOID_MIN_CSS_PX} CSS px 的连续低墨区：**")
        for a, z in voids:
            A(f"  - CSS y `{a}`–`{z + BAND_CSS_PX}`（高 {z - a + BAND_CSS_PX} px）")
        A(f"- 这些空洞为什么可以留（或怎么填掉）：")
        A(f"  > {PLACEHOLDER}")
    else:
        A(f"- 无 ≥{VOID_MIN_CSS_PX} CSS px 的连续低墨区 ✅")
    A("")
    A("## 交付闸九条（data-visualization-discipline 阶段 5）")
    A("")
    A("> 不适用的条目写「不适用：<触发的是哪个豁免条件>」——只写「不适用」三个字等于跳过。")
    A("")
    for no, title, product in load_gates():
        A(f"### 闸 {no} · {title}")
        # 剥掉 SSOT 里的 **粗体**：这一行整体套在 *…* 斜体里，嵌进去会让强调标记错乱。
        # 剥的是**渲染**，JSON 里保持原文——两者分开，才不会为了排版去污染 SSOT 的副本。
        A(f"*要求的产物：{product.replace('**', '')}*")
        A("")
        A(f"> {PLACEHOLDER}")
        A("")
    A("## 产物")
    A("")
    A(f"- 正常渲染：`{png}`")
    A(f"- 遮字渲染：`{masked}`  ← 遮字自测的证据，必须逐段 Read 过")
    A("")
    return "\n".join(L) + "\n"


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- 子命令
def cmd_init(args: argparse.Namespace) -> int:
    page = Path(args.page).resolve()
    if not page.is_file():
        sys.exit(f"❌ 页面不存在: {page}")
    gate = gate_path(page)
    carried = ""
    prev_tail = ""
    _defer_carry_check = False
    if gate.exists():
        prev = gate.read_text(encoding="utf-8")
        head, _, prev_tail = prev.partition("\n---\n\n## 上一轮的答案")
        if args.force:
            # 判据是「这份 head 有没有被人动过」，**不是**「填完了没有」。
            #
            # 两个错法都真实发生过：
            #   · 无条件搬 head —— 连跑两次 --force 时，第二次把第一次刚吐出的空模板
            #     当成上一轮答案存下，真正填过的那份被静默顶掉。
            #   · 只在「全填完」时才搬 —— 填了 8 条、剩 1 条没填的人跑一次 --force，
            #     那 8 条无声蒸发。这个错更狠：它专杀**诚实留白**的人，
            #     而 carry-over 存在的全部意义正是防止重打。（独立审计实测抓出。）
            #
            # 所以用「动过没有」：head 与本轮新鲜模板逐字相同 = 没人动过 → 保留它
            # 已经带着的那一块；只要有任何差异（哪怕只填了一条）→ 搬走整个 head。
            # 方向上刻意宁可多搬：多搬一份陈旧模板只是噪音，少搬一次就是答案消失。
            carried = head.strip()   # 默认搬；下面拿新鲜模板比对后可能改判
            _defer_carry_check = True
        filled = not unfilled_lines(prev)
        if filled and not args.force:
            sys.exit(f"❌ {gate.name} 已填写完毕，不覆盖。确要重来加 --force"
                     f"（重来意味着此前填的答案作废——页面若已改，本就该重填）")

    png = page.with_suffix(".png")
    masked = page.with_name(page.stem + "--masked.png")

    # 永不把已存在的产物当成功：先删再渲
    for p in (png, masked):
        if p.exists():
            p.unlink()
    print("→ 渲染正常版…")
    render(page, png, args.height)
    print("→ 渲染遮字版（文字全透明，只留几何）…")
    render_masked(page, masked, args.height)

    geo = scan_geometries(page)
    voids, median = scan_voids(png)

    body = build_gate(page, geo, voids, median, png, masked)
    if _defer_carry_check and len(unfilled_lines(carried)) >= len(unfilled_lines(body)):
        # 上一份 head 的空槽位不比本轮新鲜模板少 = 没人往里填过任何东西
        # （典型：连跑两次 --force，第二次看到的是第一次刚吐的空模板）。
        # 搬它只会把真答案挤掉，改为原样保留它自己带着的那一块。
        #
        # 用「槽位数」而不是「逐字相等」：模板里嵌着本轮实测的墨密度、几何清单等
        # 会变的值，逐字比对会被这些噪音带偏、退回原 bug。槽位数只回答
        # 「有没有人填过东西」这一个问题，且方向安全——页面新增几何时新模板槽位更多，
        # 旧模板会被判成「填过」而多搬一份，多搬是噪音、少搬是答案消失。
        carried = _prev_carry_block(prev_tail)
    if carried:
        body += ("\n---\n\n## 上一轮的答案（页面已改，逐条复核后再搬上来）\n\n"
                 "> 保留它是为了不让「改一个错字就得全部重打一遍」把人训练成复制粘贴。\n"
                 "> 但**搬之前必须对着新的遮字图重看一遍**——页面变了，上一轮的观察可能已经不成立。\n\n"
                 "```\n" + carried + "\n```\n")
    write_atomic(gate, body)

    print()
    print(f"✅ {gate.name} 已生成")
    heavy = [v for v in geo.volumes if v[2] >= 8]
    if heavy:
        print("   ⚠️ 以下几何罩住了较多百分比部件——复合几何（刻度轴/堆叠条）是正常的，")
        print("      但「一个标记罩住好几张独立图」也长这样。请在 gate 表里确认它们确实各是一个几何：")
        for d, nsvg, npct in heavy[:6]:
            print(f"        {d} · {nsvg} 图 / {npct} 百分比元素")
    print(f"   已标记几何 {len(geo.marked)} 个"
          + (f" · 未标记候选 {len(geo.unmarked)} 个 ⚠️" if geo.unmarked else "")
          + (f" · 显式排除的版面盒 {len(geo.layout_optouts)} 个" if geo.layout_optouts else ""))
    for u in geo.unmarked[:10]:
        print(f"     未标记: {u}")
    print(f"   空洞 {len(voids)} 处 · 墨密度中位数 {median:.3f}")
    print()
    print("接下来（缺一不可）：")
    print(f"  1. 逐段 Read `{masked.name}` —— 只看几何，写下你能读出的关系")
    print(f"  2. 把 `{gate.name}` 里每处 {PLACEHOLDER} 换成实际内容")
    print(f"  3. `delivery_gate.py check {page.name}`")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    page = Path(args.page).resolve()
    if not page.is_file():
        sys.exit(f"❌ 页面不存在: {page}")
    gate = gate_path(page)
    png = page.with_suffix(".png")
    masked = page.with_name(page.stem + "--masked.png")

    fails: list[str] = []
    page_mtime = page.stat().st_mtime

    if not gate.is_file():
        fails.append(f"gate 文件不存在 —— 先跑 `delivery_gate.py init {page.name}`")
    if not png.is_file():
        fails.append(f"正常渲染不存在: {png.name}")
    elif png.stat().st_mtime < page_mtime:
        fails.append(f"正常渲染比页面旧（页面改过没重渲）: {png.name}")
    if not masked.is_file():
        fails.append(f"遮字渲染不存在: {masked.name} —— 遮字自测没跑过")
    elif masked.stat().st_mtime < page_mtime:
        fails.append(f"遮字渲染比页面旧（页面改过没重渲遮字版）: {masked.name}")

    if gate.is_file():
        if gate.stat().st_mtime < page_mtime:
            fails.append("gate 文件比页面旧 —— 填完闸门之后页面又被改过，答案已失效，重跑 init")
        text = gate.read_text(encoding="utf-8")
        slots = unfilled_lines(text)
        if slots:
            lines = [f"{i}: {t}" for i, t in slots]
            fails.append(f"gate 文件还有 {len(slots)} 处未填：\n      " + "\n      ".join(lines[:12]))
        # 「坐标产出脚本」那一栏的消费者：把路径拿出来 stat 一下。
        # 这是 SKILL.md step 3「数值与坐标同一脚本产出」唯一的机器执法点。
        for i, ln in enumerate(text.splitlines(), 1):
            if COORD_SCRIPT_LABEL not in ln or not ln.lstrip().startswith("-"):
                continue
            ans = next((a.lstrip("> ").strip()
                        for a in text.splitlines()[i:i + 3] if a.lstrip().startswith(">")), "")
            if ans.startswith("不适用") or ans.startswith("N/A"):
                break
            # 取路径：优先取第一个反引号里的内容——人写这一栏的自然形状是
            # `路径`（后面跟一句中文说明），裸 split()[0] 会把尾引号和中文一起切进来，
            # 于是一个真实存在的文件被判成不存在。这条检查第一次跑真数据就这么误杀了一次：
            # 标定时我用的是 `calc.py` 这种裸 token，而**标定样本不具代表性**。
            m = re.search(r"`([^`]+)`", ans)
            cand = (m.group(1) if m else (ans.split()[0] if ans.split() else "")).strip()
            if not cand:
                break   # 空的话上面的槽位扫描已经报过了，不重复报
            sp = Path(cand)
            if not sp.is_absolute():
                sp = page.parent / cand
            if not sp.is_file():
                fails.append(f"「{COORD_SCRIPT_LABEL}」写的是 {cand}，但这个文件不存在"
                             f"（找过 {sp}）——坐标必须能被重跑复现，写不出脚本说明它们是手抄的")
            break

        # 「读者已知清单」那一栏的消费者：反引号词必须真的出现在读者看得见的正文里，
        # 不是随便出现在 HTML 源码的任何角落——写进注释/alt/aria-hidden/display:none
        # 也能通过纯字符串匹配，但读者从没见过那个词，"读者已知"这个断言就是假的。
        # extract_visible_text 只挡得住内联可判的隐藏（见该函数注释里的边界说明），
        # 更刻意的规避（专门写一条 CSS 类名规则）留给 SKILL.md 验收清单第 10 项。
        lines_all = text.splitlines()
        for i, ln in enumerate(lines_all, 1):
            if AUDIENCE_LABEL not in ln or not ln.lstrip().startswith("-"):
                continue
            ans_lines: list[str] = []
            for a in lines_all[i:i + 20]:
                st = a.lstrip()
                if st.startswith(">"):
                    ans_lines.append(st.lstrip("> ").strip())
                elif ans_lines:
                    break
            ans = " ".join(ans_lines)
            if not ans or ans.startswith("不适用") or ans.startswith("N/A"):
                break
            terms = re.findall(r"`([^`]+)`", ans)
            if not terms:
                fails.append(f"「{AUDIENCE_LABEL}」写了内容但一个反引号词都没有——"
                              "术语要逐个用反引号标出才能被机器核对，裸文字没法验证是不是真的在页面里用过")
                break
            visible = extract_visible_text(page)
            missing = [t for t in terms if t not in visible]
            if missing:
                fails.append(f"「{AUDIENCE_LABEL}」声明读者已知 " +
                             "、".join(f"「{m}」" for m in missing) +
                             "，但这个词不在读者看得见的正文里——可能是页面根本没用过这个词、"
                             "词从页面删掉后清单没同步更新，也可能是词只出现在注释/隐藏元素里"
                             "（读者从没见过，不构成'已知'）")

            # 反回填检查：新词必须相对「上一轮的答案」附录里的旧清单可辨认，且
            # 就近标了「补记」。mtime 挡不住这个——init --force 每次都会重新渲染
            # png/masked.png，哪怕页面一个字没改，所以"渲染是不是新的"和"清单是不是
            # 看完审阅才偷偷塞进去的"是两件独立的事，第一个新鲜不能替第二个背书
            # （独立审阅 2026-09-13 第二轮实测抓出：靠 mtime 论证这里"会失败"是错的，
            # 这段之前就是靠这个错误论证蒙混过去）。
            _, _, prev_block = text.partition("\n---\n\n## 上一轮的答案")
            if prev_block:
                prev_text = _prev_carry_block(prev_block)
                prev_ans_lines: list[str] = []
                prev_lines_all = prev_text.splitlines()
                for pi, pln in enumerate(prev_lines_all, 1):
                    if AUDIENCE_LABEL not in pln or not pln.lstrip().startswith("-"):
                        continue
                    for pa in prev_lines_all[pi:pi + 20]:
                        pst = pa.lstrip()
                        if pst.startswith(">"):
                            prev_ans_lines.append(pst.lstrip("> ").strip())
                        elif prev_ans_lines:
                            break
                    break
                prev_terms = set(re.findall(r"`([^`]+)`", " ".join(prev_ans_lines)))
                new_terms = [t for t in terms if t not in prev_terms]
                unlabeled = [t for t in new_terms if "补记" not in ans]
                if unlabeled:
                    fails.append(f"「{AUDIENCE_LABEL}」比上一轮多出 " +
                                 "、".join(f"「{m}」" for m in unlabeled) +
                                 "，但答案里没有「补记于 cycle N 审阅之后」这类标记——"
                                 "上一轮审阅已经跑完才新增的词，必须就地标明是补记的，"
                                 "不能悄悄混进清单假装从一开始就在（SKILL.md step 9"
                                 "「Triage」一节的反回填要求）")
            break

        for tag in ("不适用", "N/A"):
            for i, ln in enumerate(text.splitlines(), 1):
                st = ln.lstrip("> ").strip()
                if not st.startswith(tag):
                    continue
                # 去掉 tag 和紧随其后的任何标点，看还剩不剩实质内容。
                # 早先的判据是 `st in (tag, tag+"。", tag+".")`——枚举标点，于是
                # 「不适用：」（空冒号，正是模板教人写的那个形状）直接放行。
                # 枚举永远漏下一个：改成「剥掉标点后是不是空的」。
                if not st[len(tag):].strip(" \t：:；;。.、，,——–-"):
                    fails.append(f"第 {i} 行只写了「{st}」——必须写出触发的是哪个豁免条件")

    geo = scan_geometries(page)
    if geo.page_level_marks:
        fails.append(
            "data-geometry 挂在了页面级容器上——那是「一页」不是「一个几何」，内部所有图表会一次性免检：\n      "
            + "\n      ".join(geo.page_level_marks[:5]))
    if geo.nested_marks:
        fails.append(
            "有 data-geometry 嵌在另一个 data-geometry 里（外层可能是「包一层」绕过）：\n      "
            + "\n      ".join(geo.nested_marks[:5]))
    if geo.dup_names:
        fails.append(
            "data-geometry 重名——名字必须页内唯一，否则 gate 表的「N 个几何 = N 行」是假的"
            "（两行指同一个名字，某个几何没人写），诊断行号也会指回第一个同名元素：\n      "
            + "\n      ".join(sorted(set(geo.dup_names))[:5]))
    if geo.wrappers:
        fails.append(
            "有 data-geometry 罩住了太多东西——「包一层」会让内部所有图一次性免检，"
            "请逐个几何分别标记：\n      " + "\n      ".join(geo.wrappers[:5]))
    if geo.unmarked:
        fails.append(
            f"{len(geo.unmarked)} 个几何候选没有 data-geometry 标记"
            "（纯版面盒标 data-layout；装饰性图标标 aria-hidden=\"true\"）：\n      "
            + "\n      ".join(geo.unmarked[:8]))
    for name, derived in geo.marked:
        if not name:
            fails.append("有 data-geometry 是空值")
        if not derived:
            fails.append(f"几何「{name}」缺 data-derived-from —— 「先造量纲」这一步没做")
    if gate.is_file():
        text = gate.read_text(encoding="utf-8")
        for name, _ in geo.marked:
            if name and name not in text:
                fails.append(f"几何「{name}」在 HTML 里有，但 gate 文件的量纲表里没有它")

    if fails:
        print("❌ 交付闸未过：")
        for f in fails:
            print(f"   · {f}")
        return 1

    print("✅ 交付闸通过")
    print(f"   几何 {len(geo.marked)} 个，全部声明了量纲并在 gate 表里有条目")
    print(f"   遮字渲染 {masked.name} 比页面新")
    print(f"   gate 文件无未填项，且比页面新")
    print("   ⚠️ 本脚本只保证这些步骤**被执行了**，不保证结论对——那仍需独立审阅（SKILL.md step 9 读者审阅 / step 10 验收）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="report-with-html 交付闸：把判断步骤变成产物步骤",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("参数取值依据")[0].split("为什么存在")[1][:400],
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="渲染正常版+遮字版，扫空洞，生成待填的 gate 文件")
    p_init.add_argument("page")
    p_init.add_argument("--height", type=int, default=9600)
    p_init.add_argument("--force", action="store_true", help="覆盖已填写的 gate 文件")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="确定性校验；未过则退出码 1")
    p_check.add_argument("page")
    p_check.set_defaults(func=cmd_check)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

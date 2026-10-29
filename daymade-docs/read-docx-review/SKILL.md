---
name: read-docx-review
disable-model-invocation: true
description: >-
  读取 Word/WPS 审阅后的 docx，把批注（comments）与修订（track changes）提取成可逐条裁决的
  markdown 对账表或 JSON。触发场景：对方批注完的合同/协议/书稿/报告回来了要读意见；「提取
  docx 批注」「审阅意见对账」「读一下修订」「谁批了什么、批在哪」；WPS 云文档/Word 在线协作
  导出的审阅稿；收到带修订模式改动的回稿要看对方改了什么；已有明确基线，要核对无批注、
  无修订稿的全文改动。修订感知——python-docx
  裸读会漏掉修订插入（w:ins）的内容、认不出整段删除（w:del），本 skill 走 OpenXML SDK 引擎
  读取已支持的批注、段落增删与文本视图；范围见正文。只读，不改对方文件。
  边界：生成/排版 docx → docx-creator 或 minimax-docx；PDF 批注不在范围。
---

# read-docx-review — docx 审阅与回稿对账

一条命令把审阅过的 docx 读成对账表：谁批的、批在哪段、批了什么、处理状态，外加修订模式的
逐段删改。产出表格自带空白「处置」列——它的用途就是拿去逐条裁决。

引擎提炼自作者一个真实图书出版项目的审阅工具链（2026-02 起生产验证：单文件 96 条编辑批注、
整书修订处理、输入含 WPS 云文档导出件），此处为通用化版本。书稿级的深度编辑工作流（版本链、
批注 resolve 状态机、审阅看板）留在原项目（私有），不在本 skill 范围。

## 快速开始

**本文全部命令都假设工作目录是本 skill 根目录**（`scripts/` 是相对路径）——先 `cd` 过来，
或把 `scripts/…` 换成绝对路径；docx 参数无所谓相对绝对。

```bash
uv run python scripts/extract_review.py <审阅稿.docx>
```

预期输出（有批注时）：

```
# 审阅对账 · 某某协议-审阅版.docx

批注 12 条（未处理 10 / 已处理 2，其中回复 1 条）；修订段落 3 个（删除元素 2、插入元素 4）。

## 批注

| # | 批注人 | 时间 | 锚定段落 | 批注内容 | 状态 | 处置 |
|---|---|---|---|---|---|---|
| 0 | 张三 | 2026-02-14 16:02 | 乙方应于收到通知后 15 个工作日内… | 15 天太短，建议 30 天 | 未处理 |  |
| ↳1 | 李四 | 2026-02-14 18:11 | （回复 #0） | 同意，30 天合理 | 未处理 |  |

## 修订（track changes）

| 段落 | 删除 | 插入 | 处置 |
|---|---|---|---|
| 47 | 百分之十五 | 百分之十 |  |
```

无批注无修订时输出明确提示。**零审阅痕迹不等于没有改动**：有明确已发基线时继续走下方
全文对比；缺基线时只报告痕迹为空，索取准确已发文件，不推断对方没改或没意见。

变体：

```bash
# 机器可读全量（锚定段落不截断、含全部字段）
uv run python scripts/extract_review.py <docx> --json

# 对账表包含已处理（resolved）的批注（默认只列未处理）
uv run python scripts/extract_review.py <docx> --include-resolved
```

要看某条批注前后更多上下文段落（Markdown 锚定列为缩略文本，`--json` 里是全文）：

```bash
uv run python -c "
import sys; sys.path.insert(0, 'scripts')   # 同样假设 cwd = skill 根目录
from bridge_lib.docx_bridge_client import extract_views
for v in extract_views('<docx>', paragraph_range=(40, 55)):  # 批注锚定段落 ±N
    print(v['index'], v['display'][:100])"
```

## 为什么必须走这套引擎（不要退回 python-docx 裸读）

python-docx 的 `paragraph.text` 走 `paragraph.runs`，runs 只取直接子 `<w:r>`、不递归
`<w:ins>` 包装——**对方用修订模式插入的所有内容都会被漏读**；裸 lxml 的 `.//w:t` 能读到
ins，但认不出「段落标记被 `<w:del>` 包装的整段」（接受修订后会整段消失的内容仍有 `<w:t>`）。
两个方向的漏读都在真实出版审阅稿上踩过。本 skill 的 csx 引擎基于 OpenXML SDK，旧读取
接口报告所支持的段落增删及文本视图，不保证覆盖所有修订类型。机制细节、段落索引语义（body 直接子段，
与 python-docx 对齐、不递归表格内段）及各 csx 的出参规格见
[references/csharp-tasks-spec.md](references/csharp-tasks-spec.md)。

`scripts/bridge_lib/docx_bridge_client.py` 是 Python 入口层：`list_comments()` /
`list_revisions()` / `extract_views()` / `paragraph_text()`；调用与缓存行为由该文件定义。
写自定义分析时 import 它，别绕过它手解 XML。

## 明确基线与对照稿的全文对比（含零审阅痕迹）

先固定准确基线和对照稿，保留原件。核对对方回稿时，基线必须有实际发送证据；用户明确
指定的双版本控制、生成件与人工编辑件也可比较，但不能据此称基线“已发送”。读取
[全文对比流程](references/full-comparison.md)，再运行：

```bash
uv run python scripts/compare_docx.py <基线.docx> <对照稿.docx>
uv run python scripts/compare_docx.py <基线.docx> <对照稿.docx> --json
# 按事项选择关键承诺；核对完整所在文本块及出现次数，不只查关键词仍在
uv run python scripts/compare_docx.py <基线.docx> <对照稿.docx> --unchanged '付款条件'
```

覆盖正文、页眉页脚、脚注尾注、表格文本和合并结构。脚本复用 SDK bridge，遇未决修订即
明确拒绝比较；先由已有修订感知流程在副本落实已确认视图，再比副本。此门只约束新比较入口，
旧 `extract_review.py` 与三视图 API 仍读取带修订稿。移位/改写对应是人工核对线索；正文、
图片及版式的覆盖边界和简洁交付格式见该流程。合成回归：
`python3 -m unittest discover -s tests -v`（SDK 用例需要下方依赖）。

## 依赖（首次使用装一次）

```bash
brew install dotnet                      # 或已有任意 .NET SDK
dotnet tool install -g dotnet-script    # csx 运行时
```

- 环境默认值、工具 PATH 补充与内存缓存由
  [`docx_bridge_client.py`](scripts/bridge_lib/docx_bridge_client.py) 定义。
- NuGet 依赖由 [`scripts/csharp/tasks/`](scripts/csharp/tasks/) 内各 `.csx` 的 `#r` 声明定义。
  首次 restore 或缺缓存时需要网络；失败读取真实错误，不用固定耗时判断是否正常。
- Python 侧纯 stdlib，零第三方依赖（解析全部在 C# 侧完成，Python 只做编排与渲染）——
  `uv run python` 或系统 `python3` 都能跑。

## Troubleshooting

| 症状 | 原因 | 处理 |
|---|---|---|
| `csx script failed … dotnet-script: command not found` | dotnet-script 未装 | 按依赖节准备工具 |
| 首次运行等待或失败 | 可能需要 NuGet restore | 检查实际输出和现有缓存；缺包的离线环境需在授权范围内完成 restore，不以等待时长判定正常 |
| 批注 0 条，但对方说改过 | 可能直接改了正文，也可能导出时丢了痕迹 | 有明确已发基线先走全文对比；对方确认有批注但本地未携带时，再取保留批注的 docx 导出件 |
| 批注在，但「按章节筛选」类需求做不了 | 文档没用 Word Heading 样式（很多生成器直排文本） | 用锚定段落号定位；对账表本身不受影响 |
| 修订表为空，但 Word 里能看到红字改动 | 那份文件的改动已被接受/拒绝过，红字是比较视图 | 修订只存在于未接受的 track changes；让对方发未接受修订的原稿 |

## 设计边界（防止未来重新纠结）

- Python 生态有 docx-revisions、docx-editor、docx2python 等批注/修订库（2026-08 核实存在）。
  未采用：本引擎已在真实出版审阅流程生产验证，且 OpenXML SDK 是官方实现、修订语义保真度
  上限更高；社区库对 python-docx 的补丁层未经我们验证，为已解决的问题重做验证是负收益。
- 本 skill 只读。它不提供「接受/拒绝修订」「回复批注」「改正文再导出」——对账后的改动应落在
  你自己的正稿源（合同草案 SSOT、书稿源文件）再重新生成，而不是在对方的审阅副本上改。
- PDF 批注、飞书/腾讯文档在线批注不在范围（各有专属工具链）。

## Next Step

对账表出来后的常见下游：逐条裁决由文档 owner 做（表格的「处置」列）；需要改合同/协议/书稿
正稿并重新生成对外件时，走你自己项目的起草与重新生成流程——本 skill 刻意不碰改稿。

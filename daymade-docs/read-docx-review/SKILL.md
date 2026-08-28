---
name: read-docx-review
description: >-
  读取 Word/WPS 审阅后的 docx，把批注（comments）与修订（track changes）提取成可逐条裁决的
  markdown 对账表或 JSON。触发场景：对方批注完的合同/协议/书稿/报告回来了要读意见；「提取
  docx 批注」「审阅意见对账」「读一下修订」「谁批了什么、批在哪」；WPS 云文档/Word 在线协作
  导出的审阅稿；收到带修订模式改动的回稿要看对方改了什么。核心保证：修订感知——python-docx
  裸读会漏掉修订插入（w:ins）的内容、认不出整段删除（w:del），本 skill 走 OpenXML SDK 引擎
  不漏。只读，不改对方文件。边界：生成/排版 docx → docx-creator 或 minimax-docx；PDF 批注不在范围。
---

# read-docx-review — docx 批注与修订对账

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

无批注无修订时输出一段明确提示（「这份 docx 没有携带任何审阅痕迹」＋两个常见原因），
不会静默输出空表——拿到丢了批注的副本还以为对方没意见，比读错内容更危险。

变体：

```bash
# 机器可读全量（锚定段落不截断、含全部字段）
uv run python scripts/extract_review.py <docx> --json

# 对账表包含已处理（resolved）的批注（默认只列未处理）
uv run python scripts/extract_review.py <docx> --include-resolved
```

要看某条批注前后更多上下文段落（对账表锚定列截断到 60 字，`--json` 里是全文）：

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
两个方向的漏读都在真实出版审阅稿上踩过。本 skill 的 csx 引擎基于 Word 工程团队
官方维护的 OpenXML SDK，ins/del/move 是一等公民。机制细节、段落索引语义（body 直接子段，
与 python-docx 对齐、不递归表格内段）与三个 csx 的出参规格见
[references/csharp-tasks-spec.md](references/csharp-tasks-spec.md)。

`scripts/bridge_lib/docx_bridge_client.py` 是 Python 入口层：`list_comments()` /
`list_revisions()` / `extract_views()` / `paragraph_text()`，全部无状态直读 docx，按
(路径+mtime) 做内存缓存。写自定义分析时 import 它，别绕过它手解 XML。

## 依赖（首次使用装一次）

```bash
brew install dotnet                      # 或已有任意 .NET SDK
dotnet tool install -g dotnet-script    # csx 运行时
```

- `DOTNET_ROLL_FORWARD=Major` 已由 client 内置设置（本机 .NET 版本高于 csx 目标版本时自动兼容）。
- `~/.dotnet/tools` 不在 PATH 时 client 会自动补，无需手动 export。
- NuGet 包（DocumentFormat.OpenXml 3.2.0，csx 内 `#r` 声明）首跑自动 restore，需要网络，
  首次运行慢约 10-30 秒属正常；之后走本地包缓存。
- Python 侧纯 stdlib，零第三方依赖（解析全部在 C# 侧完成，Python 只做编排与渲染）——
  `uv run python` 或系统 `python3` 都能跑。

## Troubleshooting

| 症状 | 原因 | 处理 |
|---|---|---|
| `csx script failed … dotnet-script: command not found` | dotnet-script 未装 | 上面依赖节两条安装命令 |
| 首次运行卡 10-30 秒 | NuGet 首次 restore | 正常，等它；离线环境会失败，需联网首跑一次 |
| 批注 0 条，但对方说批过 | 拿到的副本导出时丢了批注；或对方批在在线文档上没导出 | 让对方重新「下载/另存为 docx」。WPS 云文档的「下载为 docx」实测保留批注与 resolved 状态（2026-03 一份真实出版审阅稿的 96 条批注即此来源；本 skill 的空结果提示也会提醒这一条） |
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

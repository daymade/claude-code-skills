---
name: bilibili-content
description: "Extract Bilibili video subtitles (AI-generated → uploader-uploaded → local Whisper ASR fallback) and top comments. Output as study notes, summaries, threads, or blog posts. Use when the user shares a Bilibili link, wants a video summarized, or needs transcripts. 提取B站视频字幕（AI生成→投稿者上传→Whisper ASR兜底）和热门评论，输出学习笔记、摘要、博客等格式。用户发B站链接时使用。"
---

# Bilibili Content Tool · B站内容提取工具

提取 B站视频字幕和热门评论，输出为摘要、学习笔记、博客等格式。

Extract Bilibili video subtitles and top comments. Output as study notes, summaries, threads, or blog posts.

## 功能 / Features

- **三策略字幕获取** — AI 自动生成 (覆盖率 ~90%) → 投稿者上传 → 本地 Whisper ASR 兜底
- **热评提取** — 按赞数排序，包括 UP主置顶和观众高频讨论
- **多 P 支持** — 自动识别 URL 中的 `p=` 参数
- **多格式输出** — 教程笔记、章节摘要、博客、时间线

## 适用场景 / When to Use

用户发 B站链接、要总结视频、做学习笔记、提取字幕全文时使用。支持 `bilibili.com/video/`、`b23.tv` 短链、BV 号、AV 号。

## 安装 / Setup

```bash
# 核心依赖
pip install bilibili-api-python httpx

# 可选：本地 ASR 兜底
pip install faster-whisper
# macOS: brew install ffmpeg
```

### B站 AI 字幕（需 Cookie）

```bash
# 1. 浏览器登录 B站 → F12 → Application → Cookies → 复制 SESSDATA
# 2. 设置环境变量
export BILIBILI_SESSDATA="你的值"
```

不设 Cookie 时只能抓投稿者字幕（极少视频有），加 `--asr-fallback` 可启用本地 Whisper 兜底。

## 使用方法 / Usage

`SKILL_DIR` 为本 SKILL.md 所在目录。

```bash
# 完整提取（字幕 + 评论，JSON）
python3 SKILL_DIR/scripts/fetch_content.py "https://www.bilibili.com/video/BV1xx411c7m2"

# 只取字幕纯文本
python3 SKILL_DIR/scripts/fetch_content.py "BV1xx411c7m2" --subtitle-only

# 带时间戳
python3 SKILL_DIR/scripts/fetch_content.py "URL" --subtitle-only --timestamps

# 跳过评论（最快）
python3 SKILL_DIR/scripts/fetch_content.py "URL" --no-comments

# 指定分 P
python3 SKILL_DIR/scripts/fetch_content.py "URL" --page 17  # 0-based, P18

# ASR 兜底
python3 SKILL_DIR/scripts/fetch_content.py "URL" --asr-fallback
python3 SKILL_DIR/scripts/fetch_content.py "URL" --asr-fallback --asr-model small
```

## 输出格式 / Output Formats

根据视频类型和用户需求选择：

- **学习笔记**（教程类）— 分层知识点、代码块、⚠️ 注意事项、💡 小技巧
- **章节摘要** — 按内容变化分章
- **全文摘要** — 5-10 句概括
- **博客文章** — 标题、分段、核心要点
- **时间线** — 推文风格，每条 ≤280 字
- **评论精华** — UP主信息 + 高赞观点补充

教程/课程类默认输出 **学习笔记**，其他类型默认 **全文摘要**。

## 字幕策略 / Subtitle Strategy

```
1. player/wbi/v2  → AI 自动生成 (ai-zh)  覆盖率: ~90%  需: Cookie
2. get_subtitle() → 投稿者上传 (zh)      覆盖率: <5%   需: 无
3. Whisper ASR    → 本地转写              覆盖率: 100%  需: ffmpeg + faster-whisper
```

策略 3 仅在 `--asr-fallback` 时触发。

## JSON 结构

```json
{
  "video_id": "BV1xx411c7m2",
  "title": "视频标题",
  "duration": "12:34",
  "current_page": 1,
  "subtitle": {
    "source": "ai",
    "language": "ai-zh",
    "segment_count": 519,
    "full_text": "完整字幕...",
    "timestamped_text": "0:00 文本\n0:05 ..."
  },
  "comments": {
    "total_ac": 1234,
    "top_comments": [
      {"user": "UP主", "content": "...", "likes": 233}
    ]
  }
}
```

## 工作流 / Workflow

1. **抓取** — 运行 `fetch_content.py`
2. **验证** — 确认字幕非空。无字幕时注明
3. **分块** — 超 ~50K 字时分块处理
4. **转换** — 按视频类型格式化输出
5. **复查** — 检查时间戳和连贯性

## 错误处理

| 情况 | 处理 |
|------|------|
| 无字幕 | 告知用户，评论仍可用 |
| 无 Cookie | 建议设置 `BILIBILI_SESSDATA` 或加 `--asr-fallback` |
| 依赖缺失 | `pip install bilibili-api-python httpx` |
| 私有/已删除 | 转达 API 错误 |

## 文件结构

```
bilibili-content/
├── SKILL.md
├── scripts/
│   └── fetch_content.py
└── references/
    └── output-formats.md
```

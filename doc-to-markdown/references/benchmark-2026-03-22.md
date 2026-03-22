# DOCX→Markdown 转换方案基准测试

> **测试日期**：2026-03-22
>
> **测试文件**：`助教-【腾讯云🦞】小白实践 OpenClaw 保姆级教程.docx`（19MB，77 张图片，含 grid table 布局、JSON 代码块、多列图片并排、信息框）
>
> **测试方法**：5 个方案对同一文件转换，按 5 个维度各 10 分制打分

---

## 综合评分

| 维度 | Docling (IBM) | MarkItDown (MS) | Pandoc | Mammoth | **doc-to-markdown（我们）** |
|------|:---:|:---:|:---:|:---:|:---:|
| 表格质量 | 5 | 3 | 5 | 1~3 | **6** |
| 图片提取 | 4 | 2 | **10** | 5 | 7 |
| 文本完整性 | 8 | 7 | **9** | 7 | **9** |
| 格式清洁度 | 5 | 5 | 5 | 3 | **7** |
| 代码块 | 2 | 1 | N/A | 1 | **9** |
| **综合** | **4.8** | **3.6** | **7.3** | **3.4~3.6** | **7.6** |

---

## 各方案详细分析

### 1. IBM Docling（综合 4.8）

- **版本**：docling 2.x + Granite-Docling-258M
- **架构**：AI 驱动（VLM 视觉语言模型），DocTags 中间格式 → Markdown

**致命问题**：
- 图片引用全部是 `<!-- image -->` 占位符（77 张图 0 张可显示），`ImageRefMode` API 对 DOCX 不可用
- 标题层级全部丢失（0 个 `#`），所有标题退化为粗体文本
- 代码块为零，JSON 和命令全部输出为普通段落
- `api_key` 被错误转义为 `api\_key`

**优点**：
- 文本内容完整，中文/emoji/链接保留良好
- 无 grid table 或 HTML 残留
- 表格语法正确（pipe table），但内容是占位符

**结论**：Docling 的优势在 PDF（AAAI 2025 论文场景），DOCX 支持远未达到生产级别。

### 2. Microsoft MarkItDown（综合 3.6）

- **版本**：markitdown 0.1.5
- **架构**：底层调用 mammoth → HTML → markdownify → Markdown

**致命问题**：
- 77 张图片全部是截断的 base64 占位符（`data:image/png;base64,...`），默认 `keep_data_uris=False` 主动丢弃图片数据
- 标题全部变为粗体文本（mammoth 无法识别 WPS 自定义样式）
- 代码块为零，JSON 被塞入表格单元格
- 有序列表编号全部错误（输出为 `1. 1. 1.`）

**优点**：
- 无 HTML 标签残留
- 文本内容基本完整

**结论**：MarkItDown 的 markdownify 后处理反而引入破坏性截断。轻量场景可用，复杂 DOCX 不可靠。

### 3. Pandoc（综合 7.3）

- **版本**：pandoc 3.9
- **架构**：Haskell 原生 AST 解析，支持 60+ 格式

**测试了 3 种参数**：

| 参数 | 结果 |
|------|------|
| `-t gfm` | 最差：24 个 HTML `<table>` 嵌套，74 个 HTML `<img>` |
| `-t markdown` | 最佳：grid table（可后处理），无 HTML |
| `-t markdown-raw_html-...` | 与 markdown 完全相同，参数无效果 |

**问题**：
- Grid table 不可避免（原 docx 有多行单元格和嵌套表格，pipe table 无法表达）
- `{width="..." height="..."}` 68 处
- `{.underline}` 6 处
- 反斜杠过度转义 37 处

**优点**：
- 图片提取 10/10（77 张全部正确，路径结构一致）
- 文本完整性 9/10（内容、链接、emoji 全部保留）
- 最成熟稳定的底层引擎

**结论**：Pandoc 是最可靠的底层引擎，输出质量最高但需要后处理清洗 pandoc 私有语法。

### 4. Mammoth（综合 3.4~3.6）

- **版本**：mammoth 1.11.0
- **架构**：python-docx 解析 → HTML/Markdown（Markdown 支持已废弃）

**测试了 2 种方式**：

| 方式 | 综合 |
|------|------|
| 方式A：直接转 Markdown | 3.4（表格完全丢失） |
| 方式B：转 HTML → markdownify | 3.6（有表格但嵌套被压扁） |

**致命问题**：
- 标题全部丢失（WPS `styles.xml` 中样式定义为空，mammoth 无法映射 Heading）
- 代码块为零
- 图片全部 base64 内嵌，单文件 28MB
- 方式B 中 markdownify 丢失 14 张图片（63/77）

**结论**：Mammoth 的 Markdown 支持已废弃，对 WPS 导出的 docx 兼容性差。不推荐。

### 5. doc-to-markdown / 我们的方案（综合 7.6）

- **版本**：doc-to-markdown 1.0（基于 pandoc + 6 个后处理函数）
- **架构**：Pandoc 转换 → 自动后处理（grid table 清理、图片路径修复、属性清理、代码块修复、转义修复）

**后处理实际效果**：

| 后处理函数 | 修复数量 |
|-----------|---------|
| `_convert_grid_tables` | 11 处 grid table → pipe table / blockquote |
| `_clean_pandoc_attributes` | 3437 字符属性清理 |
| `_fix_code_blocks` | 22 处缩进虚线 → ``` 代码块 |
| `_fix_escaped_brackets` | 10 处 |
| `_fix_double_bracket_links` | 1 处 |
| `_fix_image_paths` | 77 张图片路径修复 |

**已知问题（待修复）**：
- 图片路径双层嵌套 bug：`--assets-dir` 指定目录内被 pandoc 再建一层 `media/`
- 2 处 grid table 残留（文末并排图片组未完全转换）

**优点**：
- 代码块识别 9/10（JSON 带语言标签，命令行正确包裹）
- 格式清洁度 7/10（attributes、转义、grid table 大部分清理干净）
- 文本完整性 9/10（关键内容全部保留）

**结论**：综合最优，核心价值在 pandoc 后处理层。剩余 2 个 bug 可修。

---

## 架构决策

```
最终方案：Pandoc（底层引擎）+ doc-to-markdown 后处理（增值层）

理由：
1. Pandoc 图片提取最可靠（10/10），文本最完整（9/10）
2. Pandoc 的问题（grid table、属性、转义）全部可后处理解决
3. Docling/MarkItDown/Mammoth 的致命问题（图片丢失、标题丢失）无法后处理修复
4. 后处理层是我们的核心竞争力，成本低、可迭代
```

---

## 测试文件特征

本次测试文件的难点在于：

| 特征 | 说明 | 影响 |
|------|------|------|
| WPS 导出 | 非标准 Word 样式（Style ID 2/3 而非 Heading 1/2） | mammoth/markitdown/docling 标题全丢 |
| 多列图片布局 | 2x2、1x4 图片网格用表格排版 | pandoc 输出 grid table |
| 信息框/提示框 | 单列表格包裹文字 | pandoc 输出 grid table |
| 嵌套表格 | 表格内套表格 | pipe table 无法表达 |
| JSON 代码块 | 非代码块样式，用文本框/缩进表示 | 多数工具无法识别为代码 |
| 19MB 文件 | 77 张截图嵌入 | base64 方案导致 28MB 输出 |

这些特征代表了真实世界中 WPS/飞书文档导出 docx 的典型困难，是有效的基准测试场景。

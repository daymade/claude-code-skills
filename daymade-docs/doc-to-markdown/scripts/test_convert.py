"""Tests for doc-to-markdown convert.py post-processing functions.

Run: uv run pytest scripts/test_convert.py -v
"""

import pytest
import re
import sys
from pathlib import Path

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent))
from convert import (
    _fix_cjk_bold_spacing,
    _build_pipe_table,
    _collect_images,
    PostProcessStats,
    postprocess_docx_markdown,
)


# ── CJK Bold Spacing ─────────────────────────────────────────────────────────


class TestCjkBoldSpacing:
    """Test _fix_cjk_bold_spacing: spaces between **bold** and CJK chars."""

    def test_bold_followed_by_cjk_punctuation(self):
        """**text** directly touching CJK colon → add space after **."""
        inp = "**打开阶跃开放平台链接**：https://platform.stepfun.com/"
        out = _fix_cjk_bold_spacing(inp)
        assert "**打开阶跃开放平台链接** ：" in out

    def test_cjk_before_bold(self):
        """CJK char directly before ** → add space before **."""
        assert _fix_cjk_bold_spacing("可用**手机号**进行") == "可用 **手机号** 进行"

    def test_bold_with_emoji_neighbor(self):
        """**text** touching emoji ➡️ → still add space (CJK content rule)."""
        inp = "点击**【接口密码】**➡️**【创建新的密钥**】"
        out = _fix_cjk_bold_spacing(inp)
        # Each CJK-containing bold span should have spaces on both sides
        assert "点击 **【接口密码】** ➡️" in out
        assert "➡️ **【创建新的密钥**" in out

    def test_full_emoji_line(self):
        """Complete line with emoji separators between bold spans."""
        inp = "点击**【接口密码】**➡️**【创建新的密钥**】➡️**【输入密钥名称】**（输入你想取的名称），生成API Key"
        out = _fix_cjk_bold_spacing(inp)
        assert "点击 **【接口密码】** ➡️" in out
        assert "**【输入密钥名称】** （输入" in out

    def test_bold_between_cjk(self):
        """CJK **text** CJK → spaces on both sides."""
        assert _fix_cjk_bold_spacing("打开**飞书**，就可以") == "打开 **飞书** ，就可以"

    def test_bold_with_chinese_quotes(self):
        """Bold containing Chinese quotes."""
        inp = '有个**"企鹅戴龙虾头套的机器人"**，开始'
        out = _fix_cjk_bold_spacing(inp)
        assert '**"企鹅戴龙虾头套的机器人"** ，' in out

    def test_multiple_bold_spans(self):
        """Multiple bold spans in one line."""
        assert _fix_cjk_bold_spacing("这是**测试**和**验证**的效果") == "这是 **测试** 和 **验证** 的效果"

    def test_already_spaced(self):
        """Already has spaces → no double spaces."""
        inp = "已有空格 **粗体** 不需要再加"
        assert _fix_cjk_bold_spacing(inp) == inp

    def test_english_unchanged(self):
        """English bold text should not be modified."""
        inp = "English **bold** text should not change"
        assert _fix_cjk_bold_spacing(inp) == inp

    def test_line_start_bold(self):
        """Bold at line start followed by CJK."""
        assert _fix_cjk_bold_spacing("**重要**内容") == "**重要** 内容"

    def test_line_start_bold_standalone(self):
        """Bold at line start with no CJK neighbor → no change."""
        assert _fix_cjk_bold_spacing("**这是纯粗体不需要改**") == "**这是纯粗体不需要改**"

    def test_no_bold(self):
        """Text without bold markers → unchanged."""
        inp = "这是普通文本，没有粗体"
        assert _fix_cjk_bold_spacing(inp) == inp

    def test_empty_string(self):
        assert _fix_cjk_bold_spacing("") == ""

    def test_bold_at_line_end(self):
        """Bold at line end → no trailing space needed."""
        assert _fix_cjk_bold_spacing("内容是**粗体**") == "内容是 **粗体**"

    def test_mixed_cjk_and_english_bold(self):
        """English bold between CJK → no change (no CJK in content)."""
        inp = "请使用 **API Key** 进行认证"
        assert _fix_cjk_bold_spacing(inp) == inp


# ── Pipe Table Builder ────────────────────────────────────────────────────────


class TestBuildPipeTable:
    """Test _build_pipe_table: rows → markdown pipe table."""

    def test_basic_table(self):
        rows = [["a", "b"], ["c", "d"]]
        result = _build_pipe_table(rows)
        assert result == [
            "|  |  |",
            "| --- | --- |",
            "| a | b |",
            "| c | d |",
        ]

    def test_uneven_rows(self):
        """Rows with different column counts → padded."""
        rows = [["a", "b", "c"], ["d"]]
        result = _build_pipe_table(rows)
        assert "| d |  |  |" in result

    def test_single_cell(self):
        rows = [["only"]]
        result = _build_pipe_table(rows)
        assert len(result) == 3  # header + sep + 1 row

    def test_empty_rows(self):
        assert _build_pipe_table([]) == []

    def test_image_with_caption(self):
        """Images and captions should pair correctly in table."""
        rows = [
            ["![](img1.png)", "![](img2.png)"],
            ["Step 1", "Step 2"],
        ]
        result = _build_pipe_table(rows)
        assert "| ![](img1.png) | ![](img2.png) |" in result
        assert "| Step 1 | Step 2 |" in result


# ── Full Post-Processing Pipeline ─────────────────────────────────────────────


class TestPostprocessPipeline:
    """Integration tests for the full postprocess_docx_markdown pipeline."""

    def test_grid_table_single_column_to_blockquote(self):
        """Single-column grid table → blockquote."""
        inp = """+:---+
| 注意事项 |
+----+"""
        out, stats = postprocess_docx_markdown(inp)
        assert "> 注意事项" in out
        assert "+:---+" not in out

    def test_pandoc_attributes_removed(self):
        """Pandoc {width=...} and {.underline} removed."""
        inp = '![](img.png){width="5in" height="3in"} and [text]{.underline}'
        out, stats = postprocess_docx_markdown(inp)
        assert "{width=" not in out
        assert "{.underline}" not in out
        assert "![](img.png)" in out

    def test_escaped_brackets_fixed(self):
        r"""Pandoc \[ and \] → [ and ]."""
        inp = r"你 \[在飞书里\] 发消息"
        out, stats = postprocess_docx_markdown(inp)
        assert "你 [在飞书里] 发消息" in out

    def test_double_bracket_links_fixed(self):
        """[[text]](url) → [text](url)."""
        inp = "[[点击跳转]](https://example.com)"
        out, stats = postprocess_docx_markdown(inp)
        assert "[点击跳转](https://example.com)" in out

    def test_code_block_with_language(self):
        """Indented dashed block with JSON language hint → ```json."""
        inp = """  ------------------------------------------------------------------
  JSON\\
  {\\
  "provider": "stepfun"\\
  }
  ------------------------------------------------------------------"""
        out, stats = postprocess_docx_markdown(inp)
        assert "```json" in out
        assert '"provider": "stepfun"' in out
        assert "---" not in out

    def test_code_block_plain_text_to_blockquote(self):
        """Indented dashed block with plain text → blockquote."""
        inp = """  --------------------------
  注意：这是一条重要提示
  --------------------------"""
        out, stats = postprocess_docx_markdown(inp)
        assert "> 注意：这是一条重要提示" in out

    def test_cjk_bold_spacing_in_pipeline(self):
        """CJK bold spacing is applied in the full pipeline."""
        inp = "打开**飞书**，就可以看到"
        out, stats = postprocess_docx_markdown(inp)
        assert "打开 **飞书** ，就可以看到" in out

    def test_excessive_blank_lines_collapsed(self):
        """4+ blank lines → 2 blank lines."""
        inp = "line1\n\n\n\n\nline2"
        out, stats = postprocess_docx_markdown(inp)
        assert out.count("\n") < 5

    def test_stats_tracking(self):
        """Stats object correctly tracks fix counts."""
        inp = '![](media/media/img.png){width="5in"}'
        out, stats = postprocess_docx_markdown(inp)
        assert stats.attributes_removed > 0


# ── Simple Table (pandoc) ─────────────────────────────────────────────────────


class TestSimpleTable:
    """Test pandoc simple table (indented dashes with spaces) → pipe table."""

    def test_two_column_image_table(self):
        """Two images side by side in simple table → pipe table."""
        inp = """  ---- ----
   ![](img1.png)   ![](img2.png)

  ---- ----"""
        out, stats = postprocess_docx_markdown(inp)
        assert "| ![](img1.png) | ![](img2.png) |" in out
        assert "----" not in out

    def test_four_column_image_table(self):
        """Four images in simple table → 4-column pipe table."""
        inp = """  ---------- ---------- ---------- ----------
   ![](a.png)   ![](b.png)   ![](c.png)   ![](d.png)

  ---------- ---------- ---------- ----------"""
        out, stats = postprocess_docx_markdown(inp)
        assert "| ![](a.png) | ![](b.png) | ![](c.png) | ![](d.png) |" in out


# ── PDF post-processing (pymupdf4llm output) ────────────────────────────────

from convert import (
    _strip_ocr_picture_text,
    _strip_repeating_lines,
    _normalize_repeat_line,
    _make_image_paths_relative,
)


class TestStripOcrPictureText:
    """Tesseract OCR blocks on image regions must be removed (text-layer PDFs)."""

    def test_ocr_block_removed(self):
        inp = "正文段落\n<!-- Start of picture text -->foxes Soa ON<br>ABMS x RBA<br><!-- End of picture text -->\n下一段"
        stats = PostProcessStats()
        out = _strip_ocr_picture_text(inp, stats)
        assert "foxes" not in out
        assert "Start of picture" not in out
        assert "正文段落" in out and "下一段" in out
        assert stats.pdf_ocr_blocks_removed == 1

    def test_multiline_ocr_block(self):
        inp = "A\n<!-- Start of picture text -->\n乱码一行\n乱码二行<br>\n<!-- End of picture text -->\nB"
        stats = PostProcessStats()
        out = _strip_ocr_picture_text(inp, stats)
        assert "乱码" not in out
        assert stats.pdf_ocr_blocks_removed == 1

    def test_no_block_untouched(self):
        inp = "没有 OCR 块的普通文本"
        stats = PostProcessStats()
        assert _strip_ocr_picture_text(inp, stats) == inp
        assert stats.pdf_ocr_blocks_removed == 0


class TestRepeatingLines:
    """Cross-page header/footer/watermark line stripping."""

    PATTERNS = {"研究报告标题", "第# 页", "火星加速器X云启资本"}

    def test_exact_line_removed(self):
        inp = "正文\n研究报告标题\n第21 页\n下一段"
        stats = PostProcessStats()
        out = _strip_repeating_lines(inp, self.PATTERNS, stats)
        assert "研究报告标题" not in out
        assert "第21 页" not in out
        assert "正文" in out and "下一段" in out
        assert stats.pdf_header_footer_lines_removed == 2

    def test_bold_wrapped_line_removed(self):
        """Bold-wrapped header in markdown still matches plain-text pattern."""
        inp = "**研究报告标题**  \n正文"
        stats = PostProcessStats()
        out = _strip_repeating_lines(inp, self.PATTERNS, stats)
        assert "研究报告标题" not in out
        assert stats.pdf_header_footer_lines_removed == 1

    def test_merged_footer_and_pagenum_removed(self):
        """Converter may merge footer + page number into one line."""
        inp = "**火星加速器X云启资本** 第49 页\n正文段落"
        stats = PostProcessStats()
        out = _strip_repeating_lines(inp, self.PATTERNS, stats)
        assert "火星加速器" not in out
        assert "正文段落" in out
        assert stats.pdf_header_footer_lines_removed == 1

    def test_body_line_kept(self):
        """Normal body lines are never touched."""
        inp = "核心判断四：2026 年更适合被定义为规模化探索拐点年"
        stats = PostProcessStats()
        assert _strip_repeating_lines(inp, self.PATTERNS, stats) == inp
        assert stats.pdf_header_footer_lines_removed == 0

    def test_normalize_strips_bold_and_digits(self):
        assert _normalize_repeat_line("**第21 页**") == "第# 页"
        assert _normalize_repeat_line("## 第3 章 标题") == "第# 章 标题"


class TestImagePathsRelative:
    """Absolute asset paths in image refs become relative to output dir."""

    def test_absolute_to_relative(self, tmp_path):
        assets = tmp_path / "out" / "assets"
        assets.mkdir(parents=True)
        outdir = tmp_path / "out"
        inp = f"![]({assets}/img1.png)"
        stats = PostProcessStats()
        out = _make_image_paths_relative(inp, assets, outdir, stats)
        assert out == "![](assets/img1.png)"
        assert stats.image_paths_fixed == 1

    def test_other_paths_untouched(self, tmp_path):
        assets = tmp_path / "assets"
        assets.mkdir()
        inp = "![](http://example.com/x.png) ![](local/y.png)"
        stats = PostProcessStats()
        out = _make_image_paths_relative(inp, assets, tmp_path, stats)
        assert out == inp
        assert stats.image_paths_fixed == 0

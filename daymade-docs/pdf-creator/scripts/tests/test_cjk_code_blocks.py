#!/usr/bin/env python3
"""
Regression test for CJK code block rendering.

weasyprint renders <pre> blocks with monospace fonts that lack CJK glyphs.
md_to_pdf.py detects CJK characters inside <pre><code> and converts those
blocks to <div class="cjk-code-block"> which inherits the body font.

This test verifies:
1. CJK-containing code blocks get the .cjk-code-block class
2. Pure-ASCII code blocks remain as <pre><code> (monospace preserved)
3. Mixed documents handle both cases in a single pass
"""

import subprocess
import sys
import tempfile
from pathlib import Path

TEST_MARKDOWN = """# CJK Code Block 测试

## 场景1：含中文的代码块（应转为 div）

```
03/08 国金：GPT-5.4发布评测 ← 最早的报告
03/10 华创：多Agent | 国海：Token与算力出海
  ↓ [3/10 CNCERT发布安全预警] ← 重大事件
```

## 场景2：纯 ASCII 代码块（应保持 pre）

```python
def hello():
    print("Hello, World")
    return 42
```

## 场景3：含日文的代码块（应转为 div）

```
こんにちは
さようなら
```

## 场景4：inline code（`中文` 和 `code` 都应保留）

Use `uv run` to execute or reference `配置` file.
"""


def _extract_html(md_path: str) -> str:
    """Invoke the internal _md_to_html helper to get the preprocessed HTML."""
    script_dir = Path(__file__).parent.parent
    result = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "weasyprint",
            "python",
            "-c",
            f"import sys; sys.path.insert(0, '{script_dir}'); "
            f"from md_to_pdf import _md_to_html; "
            f"print(_md_to_html('{md_path}'))",
        ],
        capture_output=True,
        text=True,
        cwd=script_dir.parent,
    )
    if result.returncode != 0:
        raise RuntimeError(f"_md_to_html failed: {result.stderr}")
    return result.stdout


def run_test() -> bool:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as md_file:
        md_file.write(TEST_MARKDOWN)
        md_path = md_file.name

    pdf_path = md_path.replace(".md", ".pdf")

    try:
        # Step 1: verify HTML preprocessing
        print("=== HTML 预处理验证 ===")
        html = _extract_html(md_path)

        tests_passed = 0
        tests_total = 6

        # Test 1: CJK code block converted to div
        if 'class="cjk-code-block"' in html and "CNCERT发布安全预警" in html:
            print("✅ 场景1: 中文 code block 已转为 .cjk-code-block div")
            tests_passed += 1
        else:
            print("❌ 场景1: 中文 code block 未被转换")

        # Test 2: Pure ASCII code block stays inside <pre>...</pre>.
        # pandoc wraps highlighted blocks as
        # <pre class="sourceCode python"><code class="sourceCode python">...
        # so we only check for <pre and the presence of the function name.
        if "<pre" in html and "hello" in html and "print" in html:
            hello_pos = html.find("hello")
            # Walk back to the nearest <pre or <div cjk-code-block.
            preceding = html[max(0, hello_pos - 500) : hello_pos]
            last_pre = preceding.rfind("<pre")
            last_cjk = preceding.rfind("cjk-code-block")
            if last_pre > last_cjk:
                print("✅ 场景2: 纯 ASCII code block 保持 <pre> 结构")
                tests_passed += 1
            else:
                print("❌ 场景2: 纯 ASCII code block 被错误转换为 cjk div")
        else:
            print("❌ 场景2: 纯 ASCII code block 丢失")

        # Test 3: Japanese code block also gets converted
        if "こんにちは" in html:
            jp_pos = html.find("こんにちは")
            preceding = html[max(0, jp_pos - 200) : jp_pos]
            if "cjk-code-block" in preceding:
                print("✅ 场景3: 日文 code block 已转为 .cjk-code-block div")
                tests_passed += 1
            else:
                print("❌ 场景3: 日文 code block 未被转换")
        else:
            print("❌ 场景3: 日文 code block 丢失")

        # Test 4: Inline code preserved (both CJK and ASCII)
        if "<code>中文</code>" in html and "<code>code</code>" in html:
            print("✅ 场景4: inline code 保持 <code> 标签")
            tests_passed += 1
        else:
            print("❌ 场景4: inline code 处理异常")

        # Step 2: verify PDF can actually be generated end-to-end
        print("\n=== PDF 生成验证 ===")
        script_dir = Path(__file__).parent.parent
        md_to_pdf = script_dir / "md_to_pdf.py"
        result = subprocess.run(
            ["uv", "run", "--with", "weasyprint", str(md_to_pdf), md_path, pdf_path],
            capture_output=True,
            text=True,
            cwd=script_dir.parent,
        )

        if result.returncode == 0 and Path(pdf_path).exists():
            print("✅ 场景5: PDF 生成成功")
            tests_passed += 1
        else:
            print(f"❌ 场景5: PDF 生成失败: {result.stderr}")

        # Step 3: verify PDF content contains the CJK text (not garbled)
        txt_path = pdf_path.replace(".pdf", ".txt")
        result = subprocess.run(
            ["pdftotext", pdf_path, txt_path], capture_output=True, text=True
        )
        if result.returncode == 0 and Path(txt_path).exists():
            with open(txt_path, "r", encoding="utf-8") as f:
                pdf_text = f.read()
            # Key test: the CJK text from the code block must be intact
            if "CNCERT发布安全预警" in pdf_text and "国金" in pdf_text:
                print("✅ 场景6: PDF 中 CJK 文本未乱码")
                tests_passed += 1
            else:
                print("❌ 场景6: PDF 中 CJK 文本乱码或丢失")
                print(f"   提取内容（前 500 字符）: {pdf_text[:500]}")
        else:
            print("⚠️  场景6: pdftotext 不可用，跳过 PDF 内容验证")
            tests_total -= 1

        print(f"\n=== 测试结果: {tests_passed}/{tests_total} 通过 ===")

        if tests_passed == tests_total:
            print("\n✅ 所有测试通过！")
            return True
        print(f"\n❌ {tests_total - tests_passed} 个测试失败")
        return False

    except Exception as exc:  # noqa: BLE001
        print(f"❌ 测试异常: {exc}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        Path(md_path).unlink(missing_ok=True)
        Path(pdf_path).unlink(missing_ok=True)
        Path(pdf_path.replace(".pdf", ".txt")).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(0 if run_test() else 1)

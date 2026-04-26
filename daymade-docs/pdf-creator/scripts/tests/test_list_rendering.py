#!/usr/bin/env python3
"""
Test list rendering in PDF generation.

Verifies that markdown lists are correctly rendered in PDFs,
even when they don't have blank lines before them.

The original markdown files are NOT modified - preprocessing
happens in memory during conversion.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

# Test markdown content with various list scenarios
TEST_MARKDOWN = """# 测试列表解析

## 场景1：列表前有空行（正常）

这是一段文字。

- 列表项 1
- 列表项 2
- 列表项 3

## 场景2：列表前没有空行（关键测试）

这是一段文字。
- 列表项 1
- 列表项 2
- 列表项 3

## 场景3：有序列表前没有空行

这是一段文字。
1. 第一项
2. 第二项
3. 第三项

## 场景4：有序列表前有空行（正常）

这是一段文字。

1. 第一项
2. 第二项
3. 第三项
"""


def run_test():
    """Run the list rendering test."""
    # Create temporary files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as md_file:
        md_file.write(TEST_MARKDOWN)
        md_path = md_file.name

    pdf_path = md_path.replace('.md', '.pdf')
    txt_path = md_path.replace('.md', '.txt')

    try:
        # Generate PDF
        script_dir = Path(__file__).parent.parent
        md_to_pdf = script_dir / 'md_to_pdf.py'

        print(f"生成 PDF: {md_path} -> {pdf_path}")
        result = subprocess.run(
            ['uv', 'run', '--with', 'weasyprint', str(md_to_pdf), md_path, pdf_path],
            capture_output=True, text=True, cwd=script_dir.parent
        )

        if result.returncode != 0:
            print(f"❌ PDF 生成失败: {result.stderr}")
            return False

        print(f"✅ PDF 已生成")

        # Extract text from PDF
        result = subprocess.run(
            ['pdftotext', pdf_path, txt_path],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            print(f"❌ 文本提取失败: {result.stderr}")
            return False

        # Read extracted text
        with open(txt_path, 'r', encoding='utf-8') as f:
            pdf_text = f.read()

        # Verify original file was not modified
        with open(md_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        if original_content != TEST_MARKDOWN:
            print("❌ 原始文件被修改了！")
            return False

        print("✅ 原始文件未被修改")

        # Verify list rendering
        print("\n=== 列表渲染验证 ===")

        tests_passed = 0
        tests_total = 4

        # Test 1: List with blank line before it
        if '• 列表项 1' in pdf_text:
            print("✅ 场景1: 列表前有空行 - 正确渲染")
            tests_passed += 1
        else:
            print("❌ 场景1: 列表前有空行 - 渲染失败")

        # Test 2: Critical test - list without blank line before it
        scene2_start = pdf_text.find('场景2')
        scene2_section = pdf_text[scene2_start:scene2_start+200] if scene2_start != -1 else ""

        if '• 列表项 1' in scene2_section and '- 列表项 1' not in scene2_section:
            print("✅ 场景2: 列表前没有空行 - 正确渲染（关键测试）")
            tests_passed += 1
        else:
            print("❌ 场景2: 列表前没有空行 - 渲染失败")
            print(f"   实际内容: {scene2_section}")

        # Test 3: Ordered list without blank line
        scene3_start = pdf_text.find('场景3')
        scene3_section = pdf_text[scene3_start:scene3_start+200] if scene3_start != -1 else ""

        if '1. 第一项' in scene3_section and '2. 第二项' in scene3_section:
            print("✅ 场景3: 有序列表前没有空行 - 正确渲染")
            tests_passed += 1
        else:
            print("❌ 场景3: 有序列表前没有空行 - 渲染失败")

        # Test 4: Ordered list with blank line
        if '1. 第一项' in pdf_text and '2. 第二项' in pdf_text:
            print("✅ 场景4: 有序列表前有空行 - 正确渲染")
            tests_passed += 1
        else:
            print("❌ 场景4: 有序列表前有空行 - 渲染失败")

        print(f"\n=== 测试结果: {tests_passed}/{tests_total} 通过 ===")

        if tests_passed == tests_total:
            print("\n✅ 所有测试通过！")
            print(f"\n生成的文件:")
            print(f"  Markdown: {md_path}")
            print(f"  PDF:      {pdf_path}")
            print(f"  Text:     {txt_path}")
            return True
        else:
            print(f"\n❌ {tests_total - tests_passed} 个测试失败")
            return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)

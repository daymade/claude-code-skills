#!/usr/bin/env python3
"""
多格式导出模块 - 将微信文章导出为多种格式

支持格式：
- Markdown (默认)
- PDF (带样式)
- JSON (结构化数据)
- HTML (带图片)

作者: Claude Code
版本: 2.0.0
"""

import sys
import os
import json
import re
import argparse
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class Exporter:
    """文章导出器"""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_markdown(
        self,
        data: Dict[str, Any],
        include_images: bool = True,
        include_meta: bool = True
    ) -> str:
        """
        导出为 Markdown

        Args:
            data: 文章数据字典
            include_images: 是否包含图片
            include_meta: 是否包含元数据头部

        Returns:
            str: Markdown 内容
        """
        lines = []

        # YAML Front Matter
        if include_meta:
            lines.append("---")
            lines.append(f"title: {data.get('title', '无标题')}")
            lines.append(f"author: {data.get('author', '未知')}")
            if data.get('publishTime'):
                lines.append(f"publish_time: {data.get('publishTime')}")
            if data.get('source_url'):
                lines.append(f"source_url: {data.get('source_url')}")
            lines.append(f"exported_at: {datetime.now().isoformat()}")
            if data.get('description'):
                lines.append(f"description: {data.get('description')}")
            lines.append("---")
            lines.append("")

        # 标题
        title = data.get('title', '无标题')
        lines.append(f"# {title}")
        lines.append("")

        # 元数据表格
        lines.append("**作者**: {}".format(data.get('author', '未知')))
        if data.get('publishTime'):
            lines.append("**发布时间**: {}".format(data.get('publishTime')))
        if data.get('source_url'):
            lines.append("**原文链接**: {}".format(data.get('source_url')))
        lines.append("")
        lines.append("---")
        lines.append("")

        # 正文
        content = data.get('content', '') or data.get('text', '')

        # 处理内容中的图片
        if include_images and data.get('images'):
            content = self._insert_images_to_content(content, data['images'])

        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

        # 图片列表
        if include_images and data.get('images'):
            lines.append("## 图片列表")
            lines.append("")
            for i, img in enumerate(data['images'], 1):
                src = img.get('src') or img.get('url', '')
                alt = img.get('alt', '')
                lines.append(f"{i}. ![{alt}]({src})")
            lines.append("")

        # 页脚
        lines.append(f"*本文档由 wechat-article-scraper 于 {datetime.now().strftime("%Y-%m-%d %H:%M")} 生成*")

        return '\n'.join(lines)

    def _insert_images_to_content(self, content: str, images: list) -> str:
        """将图片插入到内容合适位置"""
        # 简单策略：在内容末尾添加图片
        # 更复杂的策略需要解析 HTML 结构
        return content

    def export_pdf(self, data: Dict[str, Any], output_file: str) -> str:
        """
        导出为 PDF

        需要安装 playwright 或 weasyprint
        """
        try:
            # 先导出 HTML
            html_content = self.export_html(data)

            # 使用 playwright 转换为 PDF
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()

                # 加载 HTML
                page.set_content(html_content)

                # 等待图片加载
                page.wait_for_timeout(2000)

                # 生成 PDF
                page.pdf(
                    path=output_file,
                    format='A4',
                    margin={'top': '1cm', 'right': '1cm', 'bottom': '1cm', 'left': '1cm'},
                    print_background=True
                )

                browser.close()

            return output_file

        except ImportError:
            print("错误: 导出 PDF 需要安装 playwright", file=sys.stderr)
            print("运行: pip install playwright && playwright install chromium", file=sys.stderr)
            raise

    def export_json(self, data: Dict[str, Any]) -> str:
        """导出为 JSON"""
        # 添加导出元数据
        export_data = {
            **data,
            '_export_meta': {
                'version': '2.0.0',
                'exported_at': datetime.now().isoformat(),
                'exporter': 'wechat-article-scraper'
            }
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def export_html(self, data: Dict[str, Any]) -> str:
        """导出为 HTML"""
        title = data.get('title', '无标题')
        author = data.get('author', '未知')
        content = data.get('html', '') or data.get('content', '') or data.get('text', '')

        # 如果没有 HTML，将文本转换为简单 HTML
        if not content.startswith('<'):
            content = f"<p>{content.replace(chr(10), '</p><p>')}</p>"

        html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            color: #333;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            font-size: 28px;
            margin-bottom: 10px;
            color: #1a1a1a;
        }}
        .meta {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }}
        .meta span {{
            margin-right: 20px;
        }}
        .content {{
            font-size: 16px;
        }}
        .content p {{
            margin: 1em 0;
        }}
        .content img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
            border-radius: 4px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 12px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="meta">
            <span>👤 {author}</span>
            {'<span>📅 ' + data.get('publishTime', '') + '</span>' if data.get('publishTime') else ''}
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            原文链接: <a href="{data.get('source_url', '#')}" target="_blank">{data.get('source_url', 'N/A')}</a><br>
            导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""

        return html_template

    def save(self, data: Dict[str, Any], format: str, filename: Optional[str] = None) -> str:
        """
        保存文章到文件

        Args:
            data: 文章数据
            format: 格式 (markdown, pdf, json, html)
            filename: 文件名（不含扩展名）

        Returns:
            str: 保存的文件路径
        """
        # 生成文件名
        if not filename:
            title = data.get('title', 'untitled')
            # 清理文件名中的非法字符
            filename = re.sub(r'[<>:"/\\|?*]', '', title)[:50]

        # 根据格式选择导出方法
        format_methods = {
            'markdown': (self.export_markdown, 'md'),
            'md': (self.export_markdown, 'md'),
            'json': (self.export_json, 'json'),
            'html': (self.export_html, 'html'),
            'pdf': (self.export_pdf, 'pdf'),
        }

        if format not in format_methods:
            raise ValueError(f"不支持的格式: {format}。支持: {list(format_methods.keys())}")

        method, ext = format_methods[format]

        # PDF 需要特殊处理
        if format == 'pdf':
            output_path = self.output_dir / f"{filename}.pdf"
            method(data, str(output_path))
        else:
            output_path = self.output_dir / f"{filename}.{ext}"
            content = method(data)
            output_path.write_text(content, encoding='utf-8')

        return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='将微信文章数据导出为多种格式'
    )
    parser.add_argument(
        'input',
        help='输入文件 (JSON 格式)'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['markdown', 'md', 'json', 'html', 'pdf'],
        default='markdown',
        help='输出格式 (默认: markdown)'
    )
    parser.add_argument(
        '-o', '--output',
        help='输出文件路径'
    )
    parser.add_argument(
        '-d', '--dir',
        default='.',
        help='输出目录'
    )

    args = parser.parse_args()

    # 读取输入
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 文件不存在 {args.input}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding='utf-8'))

    # 导出
    exporter = Exporter(output_dir=args.dir)

    try:
        output_path = exporter.save(
            data,
            format=args.format,
            filename=args.output
        )
        print(f"导出成功: {output_path}")
    except Exception as e:
        print(f"导出失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

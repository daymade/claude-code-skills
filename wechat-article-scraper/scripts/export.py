#!/usr/bin/env python3
"""
多格式导出模块 - 将微信文章导出为多种格式

支持格式：
- Markdown (默认)
- PDF (带样式)
- JSON (结构化数据)
- HTML (带图片)

作者: Claude Code
版本: 2.1.0
"""

import sys
import os
import json
import re
import argparse
import html
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


def _clean_text(text: str) -> str:
    """
    清理文本内容

    吸取 wechat-article-browseruse 精华：
    - 处理 \xa0 非断空格（微信文章常见）
    - 规范化空白字符
    """
    if not text:
        return ""
    # 替换非断空格为普通空格
    text = text.replace("\xa0", " ")
    # 规范化空白字符
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class Exporter:
    """文章导出器"""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_markdown(
        self,
        data: Dict[str, Any],
        include_images: bool = True,
        include_meta: bool = True,
        converter: str = 'default'
    ) -> str:
        """
        导出为 Markdown

        Args:
            data: 文章数据字典
            include_images: 是否包含图片
            include_meta: 是否包含元数据头部
            converter: HTML 转换器选择
                - 'default': 使用原始内容
                - 'markdownify': 使用 markdownify 库
                - 'html2text': 使用 html2text 库（更轻量）

        Returns:
            str: Markdown 内容
        """
        # 根据 converter 选择转换方式
        if data.get('html'):
            if converter == 'markdownify':
                content = self._html_to_markdown_with_markdownify(data['html'])
            elif converter == 'html2text':
                content = self._html_to_markdown_with_html2text(data['html'])
            else:
                content = data.get('content', '') or data.get('text', '')
        else:
            content = data.get('content', '') or data.get('text', '')

        lines = []

        # 清理文本字段 - 吸取精华：处理 \xa0 非断空格
        title = _clean_text(data.get('title', '无标题'))
        author = _clean_text(data.get('author', '未知'))
        publish_time = _clean_text(data.get('publishTime', ''))
        source_url = data.get('source_url', '')
        description = _clean_text(data.get('description', ''))

        # YAML Front Matter
        if include_meta:
            lines.append("---")
            lines.append(f"title: {title}")
            lines.append(f"author: {author}")
            if publish_time:
                lines.append(f"publish_time: {publish_time}")
            if source_url:
                lines.append(f"source_url: {source_url}")
            lines.append(f"exported_at: {datetime.now().isoformat()}")
            if description:
                lines.append(f"description: {description}")
            lines.append("---")
            lines.append("")

        # 标题
        lines.append(f"# {title}")
        lines.append("")

        # 元数据表格
        lines.append("**作者**: {}".format(author))
        if publish_time:
            lines.append("**发布时间**: {}".format(publish_time))
        if data.get('source_url'):
            lines.append("**原文链接**: {}".format(data.get('source_url')))
        lines.append("")
        lines.append("---")
        lines.append("")

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

        # 视频列表 - 新增功能
        if data.get('videos'):
            lines.append("## 视频列表")
            lines.append("")
            for i, video in enumerate(data['videos'], 1):
                src = video.get('src', '')
                poster = video.get('poster', '')
                title = video.get('title', '')
                duration = video.get('duration', '')
                info = f"{title} ({duration})" if title and duration else (title or '视频')
                lines.append(f"{i}. [{info}]({src or poster})")
            lines.append("")

        # 页脚
        lines.append(f"*本文档由 wechat-article-scraper 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 生成*")

        return '\n'.join(lines)

    def _html_to_markdown_with_markdownify(self, html: str) -> str:
        """
        使用 markdownify 将 HTML 转换为 Markdown

        竞品推荐此库，但以下问题需要验证:
        1. 中文排版支持是否更好
        2. 图片处理是否符合微信文章特征
        3. 性能 overhead 是否可接受
        """
        try:
            import markdownify

            # 微信特定的转换配置
            md = markdownify.markdownify(
                html,
                heading_style="ATX",  # # 样式的标题
                bullets="-",          # 统一使用 - 作为列表标记
                strip=['script', 'style', 'nav', 'header', 'footer'],
                convert=['b', 'i', 'strong', 'em', 'a', 'img', 'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'table', 'thead', 'tbody', 'tr', 'th', 'td']
            )

            # 后处理: 清理多余空行
            md = re.sub(r'\n{3,}', '\n\n', md)

            return md

        except ImportError:
            print("警告: markdownify 未安装，使用默认转换", file=sys.stderr)
            # 简单 fallback
            return html

    def _html_to_markdown_with_html2text(self, html: str) -> str:
        """
        使用 html2text 将 HTML 转换为 Markdown

        竞品 fetch-wx-article 使用此库，特点:
        1. 纯 Python 实现，更轻量
        2. 无额外依赖
        3. 转换速度快
        """
        try:
            import html2text

            h = html2text.HTML2Text()
            h.ignore_links = False  # 保留链接
            h.ignore_images = False  # 保留图片
            h.body_width = 0  # 不限制行宽

            return h.handle(html)

        except ImportError:
            print("警告: html2text 未安装，使用默认转换", file=sys.stderr)
            return html

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
                'version': '2.1.0',
                'exported_at': datetime.now().isoformat(),
                'exporter': 'wechat-article-scraper'
            }
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def export_html(self, data: Dict[str, Any]) -> str:
        """导出为 HTML"""
        # 使用 html.escape() 对所有用户输入进行转义，防止 XSS
        title = html.escape(data.get('title', '无标题'))
        author = html.escape(data.get('author', '未知'))
        content = data.get('html', '') or data.get('content', '') or data.get('text', '')
        source_url = html.escape(data.get('source_url', '#'))
        publish_time = html.escape(data.get('publishTime', ''))

        # 如果没有 HTML，将文本转换为简单 HTML
        if not content.startswith('<'):
            # 先转义文本内容，再替换换行符
            content = html.escape(content)
            content = f"<p>{content.replace(chr(10), '</p><p>')}</p>"
        else:
            # 如果已有 HTML，清理潜在的 XSS
            content = self._sanitize_html(content)

        # 时间标签 HTML（已转义）
        time_span = f'<span>&#128197; {publish_time}</span>' if publish_time else ''

        # 视频部分 HTML（新增）
        video_section = ''
        if data.get('videos'):
            video_items = []
            for video in data['videos']:
                src = html.escape(video.get('src', ''))
                poster = html.escape(video.get('poster', ''))
                title = html.escape(video.get('title', '视频'))
                duration = html.escape(video.get('duration', ''))

                # 使用 video 标签或链接
                if src:
                    video_html = f'<video controls preload="metadata" poster="{poster}" style="max-width:100%;margin:20px 0;"><source src="{src}"></video>'
                elif poster:
                    video_html = f'<div style="margin:20px 0;"><img src="{poster}" style="max-width:100%;" alt="{title}"><p>{title} (视频)</p></div>'
                else:
                    continue

                info = f"{title} ({duration})" if duration else title
                video_items.append(f'<div style="margin:20px 0;"><p><strong>{info}</strong></p>{video_html}</div>')

            if video_items:
                video_section = f'<div class="videos" style="margin-top:40px;padding-top:20px;border-top:1px solid #eee;"><h2>视频列表</h2>{"".join(video_items)}</div>'

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
            <span>&#128100; {author}</span>
            {time_span}
        </div>
        <div class="content">
            {content}
        </div>
        {video_section}
        <div class="footer">
            原文链接: <a href="{source_url}" target="_blank">{source_url}</a><br>
            导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""

        return html_template

    def _sanitize_html(self, html_content: str) -> str:
        """清理 HTML 内容中的潜在 XSS（强化版本）"""
        import re

        # 限制输入长度，防止 ReDoS 攻击
        max_length = 10 * 1024 * 1024  # 10MB 上限
        if len(html_content) > max_length:
            html_content = html_content[:max_length]

        # 移除危险标签（非贪婪匹配）
        dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'select']
        for tag in dangerous_tags:
            # 移除开始标签（非贪婪匹配）
            html_content = re.sub(
                rf'<{tag}\b[^>]*?>',
                f'&lt;{tag}&gt;',
                html_content,
                flags=re.IGNORECASE
            )
            # 移除结束标签
            html_content = re.sub(
                rf'</{tag}\s*>',
                f'&lt;/{tag}&gt;',
                html_content,
                flags=re.IGNORECASE
            )

        # 移除事件处理器（非贪婪匹配）
        html_content = re.sub(
            r'\son\w+\s*=\s*["\'][^"\']*?["\']',
            '',
            html_content,
            flags=re.IGNORECASE
        )

        # 移除 javascript: 和 data: 伪协议
        html_content = re.sub(
            r'(href|src|action)\s*=\s*["\']\s*(?:javascript|data):[^"\']*?["\']',
            r'\1="#"',
            html_content,
            flags=re.IGNORECASE
        )

        # 移除 CSS expression（IE 特有的 XSS 攻击向量）
        html_content = re.sub(
            r'expression\s*\(',
            'expression_removed(',
            html_content,
            flags=re.IGNORECASE
        )

        # 移除 style 标签中的 @import 和 behavior
        html_content = re.sub(
            r'@import\s+["\']',
            '@import_removed "',
            html_content,
            flags=re.IGNORECASE
        )
        html_content = re.sub(
            r'behavior\s*:',
            'behavior_removed:',
            html_content,
            flags=re.IGNORECASE
        )

        return html_content

    def save(
        self,
        data: Dict[str, Any],
        format: str,
        filename: Optional[str] = None,
        converter: str = 'default'
    ) -> str:
        """
        保存文章到文件

        Args:
            data: 文章数据
            format: 格式 (markdown, pdf, json, html)
            filename: 文件名（不含扩展名）
            converter: Markdown 转换器选择（'default'/'markdownify'/'html2text'）

        Returns:
            str: 保存的文件路径
        """
        # 生成文件名
        if not filename:
            title = data.get('title', 'untitled')
            # 清理文件名中的非法字符
            filename = re.sub(r'[<>"/\\|?*]', '', title)[:50]

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
        elif format in ('markdown', 'md'):
            output_path = self.output_dir / f"{filename}.{ext}"
            content = method(data, converter=converter)
            output_path.write_text(content, encoding='utf-8')
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

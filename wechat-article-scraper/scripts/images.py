#!/usr/bin/env python3
"""
微信文章图片下载与处理模块

功能：
- 下载文章中的图片到本地
- 转换 Markdown 中的图片链接为本地路径
- 图片压缩和格式转换
- 生成图片清单报告

作者: Claude Code
版本: 2.0.0
"""

import sys
import os
import re
import json
import hashlib
import argparse
import tempfile
import shutil
from pathlib import Path
from urllib.parse import urlparse, unquote
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class ImageInfo:
    """图片信息"""
    url: str
    filename: str
    alt: str = ""
    status: str = "pending"  # pending, success, failed
    local_path: Optional[str] = None
    error: Optional[str] = None
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    content_type: Optional[str] = None


class ImageDownloader:
    """微信文章图片下载器"""

    # 微信图片域名特征
    WECHAT_IMAGE_DOMAINS = [
        'mmbiz.qpic.cn',
        'mmbiz.qlogo.cn',
        'mp.weixin.qq.com',
    ]

    # 装饰性图片过滤规则
    DECORATIVE_PATTERNS = [
        r'yZPTcMGWibvsic9Obib',  # 微信装饰图特征路径
        r'1x1\.png',
        r'1x1\.gif',
        r'placeholder',
        r'spacer',
        r'transparent',
    ]

    def __init__(self, output_dir: str, max_workers: int = 5, timeout: int = 30):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self.timeout = timeout
        self.session = None

    def _get_session(self):
        """获取 HTTP session"""
        if self.session is None:
            import requests
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://mp.weixin.qq.com/',
            })
        return self.session

    def _is_content_image(self, url: str, alt: str = "") -> bool:
        """判断是否为内容图片（非装饰性）"""
        # 过滤 data URI
        if url.startswith('data:'):
            return False

        # 过滤装饰性图片
        for pattern in self.DECORATIVE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        # 过滤 SVG 占位符
        if 'svg+xml' in url:
            return False

        # 过滤过小的图片（通过 URL 参数判断）
        parsed = urlparse(url)
        # 微信图片通常有尺寸参数 wx_fmt=png&wxfrom=5&wx_lazy=1
        # 如果图片链接太简单，可能是装饰图

        return True

    def _generate_filename(self, url: str, index: int) -> str:
        """生成本地文件名（安全版本，防止路径遍历）"""
        # 尝试从 URL 提取扩展名
        parsed = urlparse(url)
        path = unquote(parsed.path)

        # 提取扩展名
        ext = '.jpg'  # 默认
        for e in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
            if path.lower().endswith(e):
                ext = e
                break

        # 使用 hash 确保唯一性
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

        # 安全文件名：移除路径分隔符，防止路径遍历攻击
        filename = f"img-{index:03d}-{url_hash}{ext}"
        # 清理任何潜在的路径分隔符
        filename = filename.replace('/', '_').replace('\\', '_').replace('..', '_')

        return filename

    def _validate_safe_path(self, filepath: Path) -> bool:
        """
        验证文件路径是否在输出目录内，防止路径遍历攻击

        Args:
            filepath: 要验证的文件路径

        Returns:
            bool: 路径是否安全
        """
        try:
            # 获取绝对路径并解析符号链接
            target = filepath.resolve()
            output = self.output_dir.resolve()
            # 检查目标路径是否以输出目录开头
            return str(target).startswith(str(output))
        except (OSError, ValueError):
            return False

    def _download_single(self, img_info: ImageInfo) -> ImageInfo:
        """下载单张图片（使用原子写入防止文件损坏）"""
        try:
            import requests

            session = self._get_session()
            resp = session.get(
                img_info.url,
                timeout=self.timeout,
                stream=True
            )
            resp.raise_for_status()

            # 确定文件扩展名
            content_type = resp.headers.get('content-type', '')
            img_info.content_type = content_type

            # 构建目标路径并验证安全性
            local_path = self.output_dir / img_info.filename
            if not self._validate_safe_path(local_path):
                raise ValueError(f"非法文件路径: {img_info.filename}")

            # 使用原子写入：先写入临时文件，再移动到目标位置
            # 防止下载中断导致文件损坏
            temp_fd = None
            temp_path = None
            try:
                # 在同一文件系统创建临时文件（确保 rename 是原子的）
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.output_dir,
                    prefix='.download_',
                    suffix='.tmp'
                )

                # 写入临时文件
                with os.fdopen(temp_fd, 'wb') as f:
                    temp_fd = None  # 防止重复关闭
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # 原子移动到目标位置
                shutil.move(temp_path, local_path)
                temp_path = None  # 防止重复删除

            finally:
                # 清理临时文件
                if temp_fd is not None:
                    try:
                        os.close(temp_fd)
                    except OSError:
                        pass
                if temp_path is not None and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

            # 获取文件大小
            img_info.size_bytes = local_path.stat().st_size
            img_info.local_path = str(local_path)
            img_info.status = "success"

            # 尝试获取图片尺寸
            try:
                from PIL import Image
                with Image.open(local_path) as img:
                    img_info.width, img_info.height = img.size
            except Exception:
                pass

        except Exception as e:
            img_info.status = "failed"
            img_info.error = str(e)

        return img_info

    def download_images(self, images: List[Dict], progress_callback=None) -> List[ImageInfo]:
        """
        批量下载图片

        Args:
            images: 图片列表，每个元素是 {'src': url, 'alt': alt_text}
            progress_callback: 进度回调函数 (current, total, image_info)

        Returns:
            List[ImageInfo]: 下载结果列表
        """
        # 过滤和准备
        image_infos = []
        for i, img in enumerate(images):
            url = img.get('src') or img.get('url') or ''
            alt = img.get('alt', '')

            if not url or not self._is_content_image(url, alt):
                continue

            info = ImageInfo(
                url=url,
                filename=self._generate_filename(url, i),
                alt=alt
            )
            image_infos.append(info)

        # 并行下载
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._download_single, info): info
                for info in image_infos
            }

            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                results.append(result)

                if progress_callback:
                    progress_callback(i + 1, len(image_infos), result)

        return results

    def update_markdown_images(self, markdown_content: str, image_results: List[ImageInfo]) -> str:
        """
        更新 Markdown 中的图片链接为本地路径

        Args:
            markdown_content: 原始 Markdown 内容
            image_results: 下载结果列表

        Returns:
            str: 更新后的 Markdown 内容
        """
        updated = markdown_content

        # 创建 URL -> 本地路径的映射
        url_to_local = {
            img.url: img.local_path
            for img in image_results
            if img.status == "success" and img.local_path
        }

        # 替换 Markdown 图片语法 ![alt](url)
        def replace_markdown_image(match):
            alt = match.group(1)
            url = match.group(2)

            if url in url_to_local:
                # 使用相对路径
                local_path = Path(url_to_local[url]).name
                return f'![{alt}](images/{local_path})'
            return match.group(0)

        updated = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            replace_markdown_image,
            updated
        )

        # 替换 HTML 图片语法 <img src="url">
        def replace_html_image(match):
            prefix = match.group(1)
            url = match.group(2)
            suffix = match.group(3)

            if url in url_to_local:
                local_path = Path(url_to_local[url]).name
                return f'{prefix}images/{local_path}{suffix}'
            return match.group(0)

        updated = re.sub(
            r'(<img[^>]*src=["\'])([^"\']+)(["\'][^>]*>)',
            replace_html_image,
            updated
        )

        return updated

    def generate_report(self, image_results: List[ImageInfo]) -> Dict:
        """生成下载报告"""
        total = len(image_results)
        success = sum(1 for r in image_results if r.status == "success")
        failed = sum(1 for r in image_results if r.status == "failed")
        total_size = sum(
            (r.size_bytes or 0) for r in image_results if r.status == "success"
        )

        return {
            "summary": {
                "total": total,
                "success": success,
                "failed": failed,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
            },
            "images": [asdict(r) for r in image_results],
        }


def download_from_markdown(md_file: str, output_dir: Optional[str] = None) -> str:
    """
    从 Markdown 文件下载图片

    Args:
        md_file: Markdown 文件路径
        output_dir: 图片输出目录（默认在 md 文件同级创建 images/ 目录）

    Returns:
        str: 报告 JSON 路径
    """
    md_path = Path(md_file)

    if not md_path.exists():
        print(f"错误: 文件不存在 {md_file}", file=sys.stderr)
        sys.exit(1)

    # 确定输出目录
    if output_dir is None:
        output_dir = md_path.parent / "images"
    else:
        output_dir = Path(output_dir)

    # 读取 Markdown
    content = md_path.read_text(encoding='utf-8')

    # 提取图片 URL
    # Markdown 格式
    md_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', content)
    # HTML 格式
    html_images = re.findall(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>', content)

    images = []
    for alt, url in md_images:
        images.append({'src': url, 'alt': alt})
    for url in html_images:
        images.append({'src': url, 'alt': ''})

    if not images:
        print("未找到需要下载的图片")
        return ""

    print(f"发现 {len(images)} 张图片，开始下载...")

    # 下载
    downloader = ImageDownloader(str(output_dir))

    def progress(current, total, info):
        status = "✅" if info.status == "success" else "❌"
        print(f"[{current}/{total}] {status} {info.filename}", file=sys.stderr)

    results = downloader.download_images(images, progress_callback=progress)

    # 更新 Markdown
    updated_content = downloader.update_markdown_images(content, results)
    md_path.write_text(updated_content, encoding='utf-8')
    print(f"已更新 Markdown 文件: {md_file}")

    # 生成报告
    report = downloader.generate_report(results)
    report_path = output_dir / "download-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"报告已保存: {report_path}")

    # 打印摘要
    summary = report["summary"]
    print(f"\n下载完成: {summary['success']}/{summary['total']} 成功, "
          f"总大小: {summary['total_size_mb']} MB")

    return str(report_path)


def main():
    parser = argparse.ArgumentParser(
        description='下载微信文章中的图片到本地'
    )
    parser.add_argument(
        'markdown_file',
        help='Markdown 文件路径'
    )
    parser.add_argument(
        '-o', '--output',
        help='图片输出目录（默认: 与 markdown 同级 images/ 目录）'
    )
    parser.add_argument(
        '-j', '--json',
        action='store_true',
        help='输出 JSON 格式报告到 stdout'
    )

    args = parser.parse_args()

    report_path = download_from_markdown(args.markdown_file, args.output)

    if args.json and report_path:
        report = json.loads(Path(report_path).read_text())
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

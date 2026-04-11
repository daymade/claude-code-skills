#!/usr/bin/env python3
"""
微信公众号评论采集模块

功能：
- 从文章页面提取评论参数
- 调用微信评论 API 获取评论列表
- 支持点赞数排序
- 支持导出为多种格式

作者: Claude Code
版本: 1.0.0
"""

import sys
import re
import json
import time
import logging
import argparse
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlencode, parse_qs, urlparse

import requests

# 配置日志
logger = logging.getLogger('wechat-comments')


@dataclass
class Comment:
    """单条评论"""
    id: str
    content: str
    nick_name: str  # 评论者昵称
    logo_url: str  # 评论者头像
    like_num: int  # 点赞数
    reply_content: Optional[str] = None  # 回复内容
    reply_like_num: int = 0  # 回复点赞数
    create_time: Optional[str] = None  # 评论时间


@dataclass
class CommentSummary:
    """评论汇总信息"""
    comment_count: int  # 评论总数
    like_count: int  # 评论点赞总数
    top_comments: List[Comment]  # 热评


class CommentExtractor:
    """
    微信评论提取器

    通过分析微信文章页面获取评论参数，然后调用评论 API 获取评论数据。

    注意：
    - 需要文章的 __biz 和 comment_id 参数
    - 某些文章可能关闭评论
    - 微信可能限制评论 API 的访问频率
    """

    # 评论 API 端点
    COMMENT_API_URL = "https://mp.weixin.qq.com/mp/appmsg_comment"

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://mp.weixin.qq.com/',
        })

    def extract_params_from_html(self, html: str) -> Dict[str, str]:
        """
        从文章 HTML 中提取评论相关参数

        Args:
            html: 文章页面 HTML

        Returns:
            Dict: 包含 comment_id, __biz 等参数的字典
        """
        params = {}

        # 提取 comment_id
        comment_id_match = re.search(r'comment_id\s*=\s*["\'](\d+)["\']', html)
        if comment_id_match:
            params['comment_id'] = comment_id_match.group(1)

        # 提取 __biz
        biz_match = re.search(r'__biz\s*=\s*["\']([^"\']+)["\']', html)
        if biz_match:
            params['biz'] = biz_match.group(1)

        # 提取 appmsg_token
        token_match = re.search(r'appmsg_token\s*=\s*["\']([^"\']+)["\']', html)
        if token_match:
            params['appmsg_token'] = token_match.group(1)

        # 提取 pass_ticket
        ticket_match = re.search(r'pass_ticket\s*=\s*["\']([^"\']+)["\']', html)
        if ticket_match:
            params['pass_ticket'] = ticket_match.group(1)

        # 提取 wxtoken
        wxtoken_match = re.search(r'wxtoken\s*=\s*["\']([^"\']+)["\']', html)
        if wxtoken_match:
            params['wxtoken'] = wxtoken_match.group(1)

        # 从 URL 中提取
        url_match = re.search(r'var\s+url\s*=\s*["\']([^"\']+)["\']', html)
        if url_match:
            parsed = urlparse(url_match.group(1))
            qs = parse_qs(parsed.query)
            if '__biz' in qs and 'biz' not in params:
                params['biz'] = qs['__biz'][0]
            if 'pass_ticket' in qs and 'pass_ticket' not in params:
                params['pass_ticket'] = qs['pass_ticket'][0]

        return params

    def extract_params_from_url(self, url: str) -> Dict[str, str]:
        """
        从文章 URL 中提取参数

        Args:
            url: 微信文章 URL

        Returns:
            Dict: URL 中的参数
        """
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        params = {}
        if '__biz' in qs:
            params['biz'] = qs['__biz'][0]
        if 'pass_ticket' in qs:
            params['pass_ticket'] = qs['pass_ticket'][0]

        return params

    def fetch_comments(
        self,
        comment_id: str,
        biz: str,
        appmsg_token: str = "",
        pass_ticket: str = "",
        wxtoken: str = "",
        offset: int = 0,
        limit: int = 100
    ) -> List[Comment]:
        """
        获取评论列表

        Args:
            comment_id: 评论 ID
            biz: 公众号 biz
            appmsg_token: 应用消息 token
            pass_ticket: 通行证 ticket
            wxtoken: 微信 token
            offset: 偏移量（分页）
            limit: 每页数量

        Returns:
            List[Comment]: 评论列表
        """
        params = {
            'action': 'getcomment',
            '__biz': biz,
            'comment_id': comment_id,
            'offset': offset,
            'limit': limit,
            'f': 'json',
        }

        if appmsg_token:
            params['appmsg_token'] = appmsg_token
        if pass_ticket:
            params['pass_ticket'] = pass_ticket
        if wxtoken:
            params['wxtoken'] = wxtoken

        try:
            resp = self.session.get(
                self.COMMENT_API_URL,
                params=params,
                timeout=10
            )
            resp.raise_for_status()

            data = resp.json()

            # 检查响应状态
            base_resp = data.get('base_resp', {})
            if base_resp.get('errmsg') != 'ok':
                logger.warning(f"API 错误: {base_resp.get('errmsg')}")
                return []

            # 解析评论
            comments = []
            comment_list = data.get('comment', [])

            for item in comment_list:
                comment = Comment(
                    id=str(item.get('comment_id', '')),
                    content=item.get('content', ''),
                    nick_name=item.get('nick_name', ''),
                    logo_url=item.get('logo_url', ''),
                    like_num=int(item.get('like_num', 0)),
                    reply_content=item.get('reply', {}).get('reply_list', [{}])[0].get('content') if item.get('reply') else None,
                    reply_like_num=int(item.get('reply', {}).get('reply_list', [{}])[0].get('like_num', 0)) if item.get('reply') else 0,
                    create_time=item.get('create_time'),
                )
                comments.append(comment)

            return comments

        except Exception as e:
            logger.error(f"获取评论失败: {e}")
            return []

    def fetch_all_comments(
        self,
        comment_id: str,
        biz: str,
        appmsg_token: str = "",
        pass_ticket: str = "",
        wxtoken: str = "",
        max_comments: int = 500
    ) -> List[Comment]:
        """
        获取所有评论（自动分页）

        Args:
            comment_id: 评论 ID
            biz: 公众号 biz
            appmsg_token: 应用消息 token
            pass_ticket: 通行证 ticket
            wxtoken: 微信 token
            max_comments: 最大获取数量

        Returns:
            List[Comment]: 所有评论
        """
        all_comments = []
        offset = 0
        limit = 100

        while len(all_comments) < max_comments:
            comments = self.fetch_comments(
                comment_id=comment_id,
                biz=biz,
                appmsg_token=appmsg_token,
                pass_ticket=pass_ticket,
                wxtoken=wxtoken,
                offset=offset,
                limit=limit
            )

            if not comments:
                break

            all_comments.extend(comments)

            # 如果返回数量少于 limit，说明已经获取完所有评论
            if len(comments) < limit:
                break

            offset += limit
            time.sleep(self.delay)

        return all_comments[:max_comments]

    def get_comment_summary(self, comments: List[Comment]) -> CommentSummary:
        """
        获取评论汇总信息

        Args:
            comments: 评论列表

        Returns:
            CommentSummary: 评论汇总
        """
        if not comments:
            return CommentSummary(
                comment_count=0,
                like_count=0,
                top_comments=[]
            )

        # 按点赞数排序获取热评
        sorted_comments = sorted(comments, key=lambda x: x.like_num, reverse=True)
        top_comments = sorted_comments[:10]

        # 计算总点赞数
        total_likes = sum(c.like_num for c in comments)

        return CommentSummary(
            comment_count=len(comments),
            like_count=total_likes,
            top_comments=top_comments
        )

    def fetch_from_article(
        self,
        article_url: str,
        html_content: str = "",
        max_comments: int = 500
    ) -> Dict:
        """
        从文章 URL 或 HTML 内容获取评论

        Args:
            article_url: 文章 URL
            html_content: 文章 HTML 内容（可选，如果提供则不从 URL 获取）
            max_comments: 最大获取数量

        Returns:
            Dict: 包含评论列表和汇总信息的字典
        """
        # 获取 HTML 内容
        if not html_content:
            try:
                resp = self.session.get(article_url, timeout=15)
                resp.raise_for_status()
                html_content = resp.text
            except Exception as e:
                logger.error(f"获取文章页面失败: {e}")
                return {'error': str(e), 'comments': []}

        # 提取参数
        params = self.extract_params_from_html(html_content)
        params.update(self.extract_params_from_url(article_url))

        if not params.get('comment_id'):
            logger.warning("未找到 comment_id，该文章可能未开启评论")
            return {
                'error': 'Comment ID not found',
                'params': params,
                'comments': []
            }

        if not params.get('biz'):
            logger.warning("未找到 __biz 参数")
            return {
                'error': 'Biz parameter not found',
                'params': params,
                'comments': []
            }

        logger.info(f"找到评论参数: comment_id={params.get('comment_id')}")

        # 获取评论
        comments = self.fetch_all_comments(
            comment_id=params['comment_id'],
            biz=params['biz'],
            appmsg_token=params.get('appmsg_token', ''),
            pass_ticket=params.get('pass_ticket', ''),
            wxtoken=params.get('wxtoken', ''),
            max_comments=max_comments
        )

        # 生成汇总
        summary = self.get_comment_summary(comments)

        return {
            'params': params,
            'comments': [asdict(c) for c in comments],
            'summary': asdict(summary),
            'total_count': summary.comment_count,
            'top_comments': [asdict(c) for c in summary.top_comments]
        }


def format_comments_output(result: Dict, fmt: str = 'markdown') -> str:
    """格式化输出评论"""

    if fmt == 'json':
        return json.dumps(result, ensure_ascii=False, indent=2)

    comments = result.get('comments', [])
    summary = result.get('summary', {})

    if fmt == 'markdown':
        lines = ['# 文章评论\n']

        # 汇总信息
        lines.append(f"**评论总数**: {summary.get('comment_count', 0)}")
        lines.append(f"**总点赞数**: {summary.get('like_count', 0)}\n")

        # 热评
        top_comments = summary.get('top_comments', [])
        if top_comments:
            lines.append("## 热评 TOP 10\n")
            for i, c in enumerate(top_comments, 1):
                lines.append(f"### {i}. {c['nick_name']} 👍 {c['like_num']}")
                lines.append(f"{c['content']}\n")
                if c.get('reply_content'):
                    lines.append(f"> 作者回复: {c['reply_content']} 👍 {c['reply_like_num']}\n")

        # 全部评论
        if comments:
            lines.append("## 全部评论\n")
            for c in comments:
                lines.append(f"**{c['nick_name']}** 👍 {c['like_num']}")
                lines.append(f"{c['content']}")
                if c.get('reply_content'):
                    lines.append(f"> 作者回复: {c['reply_content']}")
                lines.append('')

        return '\n'.join(lines)

    else:  # table
        lines = [f"评论统计: 共 {summary.get('comment_count', 0)} 条，总点赞 {summary.get('like_count', 0)}"]
        lines.append('-' * 80)

        for c in comments[:20]:  # 只显示前20条
            lines.append(f"{c['nick_name']}: {c['content'][:50]}... 👍 {c['like_num']}")

        if len(comments) > 20:
            lines.append(f"... 还有 {len(comments) - 20} 条评论")

        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='微信公众号评论采集工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从文章 URL 获取评论
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx"

  # 限制获取数量
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx" --max 100

  # 输出 JSON 格式
  %(prog)s "https://mp.weixin.qq.com/s/xxxxx" -f json

  # 从 HTML 文件获取
  %(prog)s --html-file article.html -f markdown
"""
    )

    parser.add_argument(
        'url',
        nargs='?',
        help='微信文章 URL'
    )
    parser.add_argument(
        '--html-file',
        help='从 HTML 文件读取（而非 URL）'
    )
    parser.add_argument(
        '--max',
        type=int,
        default=500,
        dest='max_comments',
        help='最大获取评论数量（默认: 500）'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['table', 'json', 'markdown'],
        default='markdown',
        help='输出格式（默认: markdown）'
    )
    parser.add_argument(
        '-o', '--output',
        help='输出文件路径'
    )

    args = parser.parse_args()

    if not args.url and not args.html_file:
        parser.print_help()
        sys.exit(1)

    extractor = CommentExtractor()

    # 获取 HTML 内容
    html_content = ''
    article_url = args.url or ''

    if args.html_file:
        try:
            html_content = open(args.html_file, 'r', encoding='utf-8').read()
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            sys.exit(1)

    # 获取评论
    result = extractor.fetch_from_article(
        article_url=article_url,
        html_content=html_content,
        max_comments=args.max_comments
    )

    if 'error' in result and not result.get('comments'):
        logger.error(f"获取评论失败: {result['error']}")
        sys.exit(1)

    # 输出结果
    output = format_comments_output(result, args.format)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        logger.info(f"结果已保存: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()

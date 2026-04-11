#!/usr/bin/env python3
"""
公众号历史文章批量抓取模块

功能：
- 从公众号主页提取全历史文章列表
- 支持断点续传
- 反检测机制（随机延迟、UA轮换）
- 自动处理分页（微信使用 10 篇文章/页）
- Token 过期自动刷新提示

吸取竞品 wcplusPro 精华：
- 全历史抓取是其核心付费功能
- 需要处理 biz + appmsg_token 参数
- 反爬检测非常严格

作者: Claude Code
版本: 1.0.0
"""

import re
import json
import time
import random
import logging
import urllib.parse
from pathlib import Path
from typing import Iterator, List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger('wechat-history')


@dataclass
class HistoryArticle:
    """历史文章数据类"""
    aid: str  # 文章唯一ID (appmsgid)
    title: str
    link: str
    publish_time: str
    cover_image: str = ""
    digest: str = ""  # 摘要
    read_count: Optional[int] = None
    like_count: Optional[int] = None
    is_top: bool = False  # 是否头条
    position: int = 0  # 在当天的位置（1=头条, 2=次条...）


@dataclass
class CrawlProgress:
    """抓取进度"""
    account_name: str
    biz: str
    total_count: int = 0
    crawled_count: int = 0
    last_offset: int = 0
    last_crawl_time: str = ""
    is_complete: bool = False
    error_message: str = ""


class HistoryCrawler:
    """
    公众号历史文章抓取器

    技术要点：
    1. 从公众号主页 URL 提取 biz 和 appmsg_token
    2. 构造历史文章 API 请求（mp.weixin.qq.com/mp/profile_ext）
    3. 处理分页参数（offset, count）
    4. 解析返回的 HTML/JSON 混合数据
    """

    # 历史文章 API 模板
    HISTORY_API_URL = "https://mp.weixin.qq.com/mp/profile_ext"

    # 请求间隔（秒）- 反检测
    MIN_DELAY = 2.0
    MAX_DELAY = 5.0

    def __init__(
        self,
        biz: str,
        appmsg_token: str,
        cookie: str = "",
        user_agent: str = "",
        progress_dir: str = "./data/progress"
    ):
        """
        初始化历史抓取器

        Args:
            biz: 公众号唯一标识 (如 __biz=MzI5NjUyMDk0MA==)
            appmsg_token: 临时 token，从页面中提取
            cookie: 登录态 cookie
            user_agent: 自定义 UA
            progress_dir: 进度保存目录
        """
        self.biz = biz
        self.appmsg_token = appmsg_token
        self.cookie = cookie
        self.user_agent = user_agent or self._get_random_ua()
        self.progress_dir = Path(progress_dir)
        self.progress_dir.mkdir(parents=True, exist_ok=True)

        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化 HTTP session"""
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            self.session = requests.Session()

            # 重试策略
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

            # 设置 headers
            self.session.headers.update({
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Cookie': self.cookie,
                'Referer': f'https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={self.biz}',
            })

        except ImportError:
            raise ImportError("需要安装 requests: pip install requests")

    def _get_random_ua(self) -> str:
        """获取随机 User-Agent"""
        ua_list = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        ]
        return random.choice(ua_list)

    def _random_delay(self):
        """随机延迟，防检测"""
        delay = random.uniform(self.MIN_DELAY, self.MAX_DELAY)
        time.sleep(delay)

    def _make_request(self, offset: int = 0, count: int = 10) -> Dict[str, Any]:
        """
        发起历史文章请求

        Args:
            offset: 分页偏移量
            count: 每页数量（微信默认10）

        Returns:
            解析后的响应数据
        """
        params = {
            'action': 'getmsg',
            '__biz': self.biz,
            'f': 'json',
            'offset': offset,
            'count': count,
            'is_ok': 1,
            'appmsg_token': self.appmsg_token,
            'x5': 0,
        }

        try:
            response = self.session.get(
                self.HISTORY_API_URL,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            # 检查错误
            if data.get('ret') != 0:
                error_msg = data.get('errmsg', '未知错误')
                if 'freq control' in error_msg.lower() or 'verify' in error_msg.lower():
                    raise RateLimitError(f"触发频率限制: {error_msg}")
                if 'invalid' in error_msg.lower() or 'expired' in error_msg.lower():
                    raise TokenExpiredError(f"Token 已过期: {error_msg}")
                raise APIError(f"API 错误: {error_msg}")

            return data

        except requests.exceptions.RequestException as e:
            raise NetworkError(f"网络请求失败: {e}")

    def _parse_article_list(self, data: Dict[str, Any]) -> List[HistoryArticle]:
        """
        解析文章列表

        微信返回的数据格式：
        - general_msg_list: JSON 字符串，包含文章列表
        - msg_count: 本次返回的文章数量
        - can_msg_continue: 是否还有更多 (1=有, 0=无)
        - next_offset: 下一页偏移量
        """
        articles = []

        msg_list_str = data.get('general_msg_list', '{}')
        msg_list = json.loads(msg_list_str)

        for msg in msg_list.get('list', []):
            try:
                # 提取发布时间
                comm_msg_info = msg.get('comm_msg_info', {})
                datetime_str = comm_msg_info.get('datetime', '')
                if datetime_str:
                    try:
                        publish_time = datetime.fromtimestamp(int(datetime_str)).isoformat()
                    except:
                        publish_time = datetime_str
                else:
                    publish_time = ""

                # 提取文章信息
                app_msg_ext_info = msg.get('app_msg_ext_info', {})
                if not app_msg_ext_info:
                    continue

                # 头条文章
                article = HistoryArticle(
                    aid=str(app_msg_ext_info.get('msgid', '')),
                    title=app_msg_ext_info.get('title', ''),
                    link=app_msg_ext_info.get('content_url', '').replace('\\x26', '&'),
                    publish_time=publish_time,
                    cover_image=app_msg_ext_info.get('cover', ''),
                    digest=app_msg_ext_info.get('digest', ''),
                    is_top=True,
                    position=1
                )
                articles.append(article)

                # 次条文章（同一天发布的其他文章）
                multi_app_msg_item_list = app_msg_ext_info.get('multi_app_msg_item_list', [])
                for idx, sub_msg in enumerate(multi_app_msg_item_list, start=2):
                    sub_article = HistoryArticle(
                        aid=str(sub_msg.get('msgid', '')),
                        title=sub_msg.get('title', ''),
                        link=sub_msg.get('content_url', '').replace('\\x26', '&'),
                        publish_time=publish_time,
                        cover_image=sub_msg.get('cover', ''),
                        digest=sub_msg.get('digest', ''),
                        is_top=False,
                        position=idx
                    )
                    articles.append(sub_article)

            except Exception as e:
                logger.warning(f"解析单篇文章失败: {e}")
                continue

        return articles

    def crawl_history(
        self,
        account_name: str,
        max_articles: int = 0,
        resume: bool = True
    ) -> Iterator[HistoryArticle]:
        """
        抓取公众号全历史文章

        Args:
            account_name: 账号名称（用于进度保存）
            max_articles: 最大抓取数量（0=无限制）
            resume: 是否从上次中断处继续

        Yields:
            HistoryArticle: 文章数据
        """
        # 加载进度
        progress = self._load_progress(account_name)
        if resume and progress:
            offset = progress.last_offset
            crawled = progress.crawled_count
            logger.info(f"从断点继续: 已抓取 {crawled} 篇，offset={offset}")
        else:
            offset = 0
            crawled = 0
            progress = CrawlProgress(
                account_name=account_name,
                biz=self.biz,
                last_crawl_time=datetime.now().isoformat()
            )

        try:
            while True:
                # 检查是否达到上限
                if max_articles > 0 and crawled >= max_articles:
                    logger.info(f"达到最大数量限制: {max_articles}")
                    break

                logger.info(f"正在抓取 offset={offset}...")

                # 发起请求
                data = self._make_request(offset=offset, count=10)

                # 解析文章
                articles = self._parse_article_list(data)

                if not articles:
                    logger.info("没有更多文章")
                    break

                # 返回文章
                for article in articles:
                    if max_articles > 0 and crawled >= max_articles:
                        break
                    yield article
                    crawled += 1

                # 更新进度
                progress.crawled_count = crawled
                progress.last_offset = offset
                progress.last_crawl_time = datetime.now().isoformat()
                self._save_progress(progress)

                # 检查是否还有更多
                can_continue = data.get('can_msg_continue', 0)
                if not can_continue:
                    logger.info("已抓取全部历史文章")
                    progress.is_complete = True
                    progress.total_count = crawled
                    self._save_progress(progress)
                    break

                # 更新 offset
                offset = data.get('next_offset', offset + 10)

                # 随机延迟
                self._random_delay()

        except TokenExpiredError as e:
            logger.error(f"Token 已过期，需要重新获取: {e}")
            progress.error_message = str(e)
            self._save_progress(progress)
            raise

        except RateLimitError as e:
            logger.error(f"触发频率限制，请稍后重试: {e}")
            progress.error_message = str(e)
            self._save_progress(progress)
            raise

        except Exception as e:
            logger.error(f"抓取失败: {e}")
            progress.error_message = str(e)
            self._save_progress(progress)
            raise

    def _load_progress(self, account_name: str) -> Optional[CrawlProgress]:
        """加载抓取进度"""
        progress_file = self.progress_dir / f"{account_name}.json"

        if not progress_file.exists():
            return None

        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return CrawlProgress(**data)
        except Exception as e:
            logger.warning(f"加载进度失败: {e}")
            return None

    def _save_progress(self, progress: CrawlProgress):
        """保存抓取进度"""
        progress_file = self.progress_dir / f"{progress.account_name}.json"

        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(progress), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存进度失败: {e}")

    @staticmethod
    def extract_params_from_url(profile_url: str) -> Tuple[str, str]:
        """
        从公众号主页 URL 提取参数

        Args:
            profile_url: 公众号主页 URL
                格式: https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=xxx&scene=124#wechat_redirect

        Returns:
            (biz, appmsg_token) 元组
        """
        parsed = urllib.parse.urlparse(profile_url)
        query = urllib.parse.parse_qs(parsed.query)

        # 提取 biz
        biz = query.get('__biz', [''])[0]
        if not biz:
            # 尝试从 fragment 提取
            fragment = parsed.fragment
            if 'biz=' in fragment:
                match = re.search(r'biz=([^&]+)', fragment)
                if match:
                    biz = match.group(1)

        # appmsg_token 通常需要从页面源码中提取，不在 URL 中
        # 这里返回空，需要用户通过其他方式获取
        return biz, ""


class HistoryCrawlerError(Exception):
    """历史抓取基础异常"""
    pass


class TokenExpiredError(HistoryCrawlerError):
    """Token 过期异常"""
    pass


class RateLimitError(HistoryCrawlerError):
    """频率限制异常"""
    pass


class NetworkError(HistoryCrawlerError):
    """网络错误异常"""
    pass


class APIError(HistoryCrawlerError):
    """API 错误异常"""
    pass


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description='公众号历史文章批量抓取')
    parser.add_argument('--biz', required=True, help='公众号 biz 参数')
    parser.add_argument('--token', required=True, help='appmsg_token')
    parser.add_argument('--cookie', default='', help='Cookie')
    parser.add_argument('--account-name', required=True, help='账号名称（用于进度保存）')
    parser.add_argument('--max-articles', type=int, default=0, help='最大抓取数量（0=无限制）')
    parser.add_argument('--no-resume', action='store_true', help='不续传，从头开始')
    parser.add_argument('--progress-dir', default='./data/progress', help='进度保存目录')

    args = parser.parse_args()

    # 初始化日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        crawler = HistoryCrawler(
            biz=args.biz,
            appmsg_token=args.token,
            cookie=args.cookie,
            progress_dir=args.progress_dir
        )

        print(f"开始抓取公众号: {args.account_name}")
        print(f"biz: {args.biz}")
        print(f"token: {args.token[:20]}...")
        print("-" * 50)

        count = 0
        for article in crawler.crawl_history(
            account_name=args.account_name,
            max_articles=args.max_articles,
            resume=not args.no_resume
        ):
            count += 1
            top_mark = "【头条】" if article.is_top else f"【{article.position}条】"
            print(f"{count}. {top_mark} {article.title}")
            print(f"   链接: {article.link}")
            print(f"   时间: {article.publish_time}")
            if article.digest:
                print(f"   摘要: {article.digest[:50]}...")
            print()

        print(f"\n抓取完成！共 {count} 篇文章")

    except TokenExpiredError:
        print("\n❌ Token 已过期，请重新获取 appmsg_token")
        exit(1)
    except RateLimitError:
        print("\n❌ 触发频率限制，请稍后重试")
        exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，进度已保存，可续传")
        exit(0)
    except Exception as e:
        print(f"\n❌ 抓取失败: {e}")
        exit(1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
微信登录态管理模块

功能：
- 微信网页版二维码登录
- 登录态持久化（cookie + localStorage）
- 自动登录态刷新
- 多账号支持

技术方案：
- Playwright 模拟微信网页登录流程
- 保存登录态到本地文件
- 登录态复用避免重复扫码

作者: Claude Code
版本: 1.0.0
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger('wechat-auth')


@dataclass
class WeChatSession:
    """微信登录会话"""
    account_name: str  # 账号标识（用户自定义）
    cookies: list  # Playwright cookies
    local_storage: dict  # localStorage 数据
    session_storage: dict  # sessionStorage 数据
    created_at: str = ""
    expires_at: str = ""
    is_valid: bool = True
    last_used_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.last_used_at:
            self.last_used_at = self.created_at


class WeChatAuthManager:
    """
    微信登录态管理器

    吸取精华：
    - 登录态持久化避免每次扫码
    - 支持多账号切换
    - 自动检测登录态有效性
    """

    def __init__(self, storage_dir: str = "./data/auth"):
        """
        初始化认证管理器

        Args:
            storage_dir: 登录态存储目录
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, account_name: str) -> Path:
        """获取会话文件路径"""
        return self.storage_dir / f"{account_name}.json"

    def save_session(self, session: WeChatSession):
        """保存登录会话"""
        session_path = self._get_session_path(session.account_name)

        # 更新最后使用时间
        session.last_used_at = datetime.now().isoformat()

        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(session), f, ensure_ascii=False, indent=2)

        logger.info(f"登录态已保存: {session.account_name}")

    def load_session(self, account_name: str) -> Optional[WeChatSession]:
        """加载登录会话"""
        session_path = self._get_session_path(account_name)

        if not session_path.exists():
            return None

        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            session = WeChatSession(**data)

            # 检查是否过期（默认7天）
            if session.expires_at:
                expires = datetime.fromisoformat(session.expires_at)
                if datetime.now() > expires:
                    logger.warning(f"登录态已过期: {account_name}")
                    session.is_valid = False

            return session

        except Exception as e:
            logger.error(f"加载登录态失败: {e}")
            return None

    def list_accounts(self) -> list:
        """列出所有已保存的账号"""
        accounts = []

        for session_file in self.storage_dir.glob("*.json"):
            account_name = session_file.stem
            session = self.load_session(account_name)
            if session:
                accounts.append({
                    'name': account_name,
                    'created_at': session.created_at,
                    'last_used_at': session.last_used_at,
                    'is_valid': session.is_valid
                })

        return accounts

    def delete_session(self, account_name: str) -> bool:
        """删除登录会话"""
        session_path = self._get_session_path(account_name)

        if session_path.exists():
            session_path.unlink()
            logger.info(f"登录态已删除: {account_name}")
            return True

        return False

    def login_with_qrcode(
        self,
        account_name: str,
        headless: bool = False,
        timeout: int = 120
    ) -> WeChatSession:
        """
        使用二维码登录微信

        Args:
            account_name: 账号标识（用户自定义，如"个人号"、"公司号"）
            headless: 是否无头模式（登录过程建议显示浏览器）
            timeout: 登录超时时间（秒）

        Returns:
            WeChatSession: 登录会话
        """
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context(
                    viewport={'width': 1280, 'height': 800}
                )
                page = context.new_page()

                # 访问微信文章页面（会触发登录）
                logger.info("正在打开微信登录页面...")
                page.goto('https://mp.weixin.qq.com', wait_until='networkidle')

                # 等待二维码出现
                logger.info("请使用微信扫描页面上的二维码...")

                # 检测登录成功（通过检查特定元素）
                login_success = False
                start_time = time.time()

                while time.time() - start_time < timeout:
                    # 检查是否已登录（出现公众号管理界面元素）
                    try:
                        # 尝试查找登录后的特征元素
                        user_element = page.query_selector('.weui-desktop-account__info')
                        if user_element:
                            login_success = True
                            logger.info("登录成功！")
                            break
                    except:
                        pass

                    # 检查是否有"已登录"提示
                    page_content = page.content()
                    if '公众号' in page_content and '管理' in page_content:
                        login_success = True
                        logger.info("登录成功！")
                        break

                    time.sleep(2)

                if not login_success:
                    browser.close()
                    raise TimeoutError("登录超时，请重试")

                # 获取登录态数据
                cookies = context.cookies()
                local_storage = page.evaluate('() => Object.assign({}, localStorage)')
                session_storage = page.evaluate('() => Object.assign({}, sessionStorage)')

                # 创建会话
                session = WeChatSession(
                    account_name=account_name,
                    cookies=cookies,
                    local_storage=local_storage,
                    session_storage=session_storage,
                    expires_at=(datetime.now() + timedelta(days=7)).isoformat()
                )

                # 保存会话
                self.save_session(session)

                browser.close()
                return session

        except ImportError:
            raise ImportError("需要安装 Playwright: pip install playwright && playwright install chromium")
        except Exception as e:
            logger.error(f"登录失败: {e}")
            raise

    def apply_session(self, context, account_name: str) -> bool:
        """
        将登录态应用到 Playwright context

        Args:
            context: Playwright BrowserContext
            account_name: 账号名称

        Returns:
            bool: 是否成功应用
        """
        session = self.load_session(account_name)

        if not session or not session.is_valid:
            logger.warning(f"没有有效的登录态: {account_name}")
            return False

        try:
            # 添加 cookies
            if session.cookies:
                context.add_cookies(session.cookies)

            # 注意：localStorage 和 sessionStorage 需要在页面加载后设置
            logger.info(f"已应用登录态: {account_name}")

            # 更新最后使用时间
            session.last_used_at = datetime.now().isoformat()
            self.save_session(session)

            return True

        except Exception as e:
            logger.error(f"应用登录态失败: {e}")
            return False

    def verify_session(self, account_name: str) -> bool:
        """
        验证登录态是否有效

        Args:
            account_name: 账号名称

        Returns:
            bool: 登录态是否有效
        """
        session = self.load_session(account_name)

        if not session or not session.is_valid:
            return False

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()

                # 应用登录态
                if not self.apply_session(context, account_name):
                    browser.close()
                    return False

                page = context.new_page()

                # 访问一个需要登录的页面进行验证
                page.goto('https://mp.weixin.qq.com', wait_until='networkidle', timeout=10000)

                # 检查是否已登录
                page_content = page.content()
                is_valid = '公众号' in page_content or '登录' not in page_content

                browser.close()

                # 更新会话状态
                session.is_valid = is_valid
                self.save_session(session)

                return is_valid

        except Exception as e:
            logger.error(f"验证登录态失败: {e}")
            return False


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description='微信登录态管理')
    parser.add_argument('--storage', default='./data/auth', help='存储目录')

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # login 命令
    login_parser = subparsers.add_parser('login', help='二维码登录')
    login_parser.add_argument('account_name', help='账号标识')
    login_parser.add_argument('--headless', action='store_true', help='无头模式')
    login_parser.add_argument('--timeout', type=int, default=120, help='超时时间')

    # list 命令
    list_parser = subparsers.add_parser('list', help='列出账号')

    # verify 命令
    verify_parser = subparsers.add_parser('verify', help='验证登录态')
    verify_parser.add_argument('account_name', help='账号标识')

    # delete 命令
    delete_parser = subparsers.add_parser('delete', help='删除登录态')
    delete_parser.add_argument('account_name', help='账号标识')

    args = parser.parse_args()

    auth_manager = WeChatAuthManager(args.storage)

    if args.command == 'login':
        try:
            session = auth_manager.login_with_qrcode(
                args.account_name,
                headless=args.headless,
                timeout=args.timeout
            )
            print(f"✅ 登录成功: {session.account_name}")
            print(f"   过期时间: {session.expires_at}")
        except Exception as e:
            print(f"❌ 登录失败: {e}")
            exit(1)

    elif args.command == 'list':
        accounts = auth_manager.list_accounts()
        if not accounts:
            print("没有保存的账号")
        else:
            print(f"共 {len(accounts)} 个账号:")
            for acc in accounts:
                status = "✅" if acc['is_valid'] else "❌"
                print(f"  {status} {acc['name']}")
                print(f"     创建: {acc['created_at'][:10]}")
                print(f"     最后使用: {acc['last_used_at'][:10]}")

    elif args.command == 'verify':
        is_valid = auth_manager.verify_session(args.account_name)
        if is_valid:
            print(f"✅ 登录态有效: {args.account_name}")
        else:
            print(f"❌ 登录态无效或已过期: {args.account_name}")

    elif args.command == 'delete':
        if auth_manager.delete_session(args.account_name):
            print(f"✅ 已删除: {args.account_name}")
        else:
            print(f"❌ 账号不存在: {args.account_name}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Playwright 抓取脚本 - 用于 stable 策略

单独脚本形式运行，避免在主进程中加载 Playwright
支持 OG 元数据备选提取和图片段落关联
"""

import sys
import json
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('wechat-playwright')


def _validate_url(url: str) -> bool:
    """验证 URL 是否是允许的微信域名"""
    allowed_domains = ['mp.weixin.qq.com', 'weixin.qq.com']
    return any(domain in url for domain in allowed_domains)


def _extract_og_meta(page) -> dict:
    """提取 OG (Open Graph) 元数据作为备选"""
    return page.evaluate('''() => {
        const getMeta = (prop) => {
            const el = document.querySelector(`meta[property="${prop}"]`);
            return el ? el.getAttribute('content') : null;
        };
        return {
            title: getMeta('og:title'),
            author: getMeta('og:article:author'),
            publishTime: getMeta('og:article:published_time'),
            description: getMeta('og:description'),
        };
    }''')


def scrape_with_playwright(
    url: str,
    screenshot_path: str = None,
    auth_account: str = None,
    auth_storage_dir: str = './data/auth'
) -> dict:
    """
    使用 Playwright 抓取微信文章

    支持：
    - 滚动触发懒加载
    - OG 元数据备选
    - 图片段落关联
    - 装饰性图片过滤
    - 页面截图（可选）
    - 登录态抓取互动数据（可选）

    Args:
        url: 微信文章 URL
        screenshot_path: 截图保存路径（可选）
        auth_account: 微信登录账号标识（可选，用于抓取阅读/点赞数）
        auth_storage_dir: 登录态存储目录
    """
    # 验证 URL
    if not _validate_url(url):
        return {'error': f'不支持的 URL: 必须是微信文章链接'}

    browser = None
    auth_manager = None
    session = None

    try:
        from playwright.sync_api import sync_playwright
        from wechat_auth import WeChatAuthManager, WeChatSession

        # 初始化认证管理器
        if auth_account:
            auth_manager = WeChatAuthManager(auth_storage_dir)
            session = auth_manager.load_session(auth_account)
            if session:
                logger.info(f"使用登录态: {auth_account}")
            else:
                logger.warning(f"未找到登录态: {auth_account}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                )

                # 应用登录态
                if session and session.cookies:
                    context.add_cookies(session.cookies)
                    logger.info(f"已应用 {len(session.cookies)} 个 cookies")

                page = context.new_page()

                # 设置 localStorage 和 sessionStorage（登录态的一部分）
                if session:
                    if session.local_storage or session.session_storage:
                        page.goto('about:blank')
                        if session.local_storage:
                            for key, value in session.local_storage.items():
                                try:
                                    page.evaluate(f'''
                                        () => {{ localStorage.setItem("{key}", {json.dumps(value)}); }}
                                    ''')
                                except:
                                    pass
                        if session.session_storage:
                            for key, value in session.session_storage.items():
                                try:
                                    page.evaluate(f'''
                                        () => {{ sessionStorage.setItem("{key}", {json.dumps(value)}); }}
                                    ''')
                                except:
                                    pass
                        logger.info("已应用 localStorage/sessionStorage")

                # 导航到文章
                page.goto(url, wait_until='networkidle', timeout=30000)

                # 检查是否被拦截
                if '环境异常' in page.content() or 'verify' in page.url:
                    return {'error': 'blocked', 'message': '触发反爬验证'}

                # 滚动触发懒加载
                page.evaluate('''() => {
                    return new Promise(resolve => {
                        let totalHeight = 0;
                        let distance = 300;
                        let timer = setInterval(() => {
                            let scrollHeight = document.body.scrollHeight;
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            if (totalHeight >= scrollHeight) {
                                clearInterval(timer);
                                setTimeout(resolve, 2000);
                            }
                        }, 100);
                    });
                }''')

                # 提取 OG 元数据备选
                og_meta = _extract_og_meta(page)

                # 提取数据（支持图片段落关联）
                data = page.evaluate('''() => {
                    const contentEl = document.querySelector('#js_content');
                    if (!contentEl) return null;

                    // 提取元数据
                    let title = document.querySelector('#activity_name')?.innerText
                        || document.querySelector('#activity-name')?.innerText
                        || '';
                    let author = document.querySelector('#js_name')?.innerText
                        || document.querySelector('.profile_nickname')?.innerText
                        || '';
                    let publishTime = document.querySelector('#publish_time')?.innerText
                        || document.querySelector('#publish-time')?.innerText
                        || '';

                    // 提取图片、视频和段落
                    const images = [];
                    const videos = []; // 新增：视频提取
                    const paragraphs = [];
                    let currentParagraphIndex = 0;

                    const allElements = contentEl.querySelectorAll('p, section, img, video, mpvideosrc');
                    allElements.forEach((el) => {
                        const tagName = el.tagName.toLowerCase();
                        if (tagName === 'img') {
                            // 吸取精华：支持 data-backsrc，过滤 op_res
                            const realSrc = el.getAttribute('data-src') ||
                                            el.getAttribute('data-backsrc') ||
                                            el.src || '';
                            const width = el.naturalWidth || el.width || 0;
                            const height = el.naturalHeight || el.height || 0;

                            // 过滤装饰性图片 - 吸取精华：op_res 过滤
                            const isDecorative = (
                                !realSrc ||
                                realSrc.startsWith('data:') ||
                                realSrc.includes('data:image/svg+xml') ||
                                realSrc.includes('yZPTcMGWibvsic9Obib') ||
                                realSrc.includes('res.wx.qq.com/op_res/') ||
                                (width > 0 && width < 50) ||
                                (height > 0 && height < 50)
                            );

                            if (!isDecorative && realSrc) {
                                images.push({
                                    index: images.length,
                                    src: realSrc,
                                    alt: el.alt || '',
                                    width: width,
                                    height: height,
                                    paragraphIndex: currentParagraphIndex,
                                    isContentImage: width > 200 || height > 200
                                });
                            }
                        } else if (tagName === 'video' || tagName === 'mpvideosrc') {
                            // 新增：视频提取
                            const videoData = {
                                index: videos.length,
                                src: el.getAttribute('data-src') || el.src || '',
                                poster: el.getAttribute('data-poster') || el.poster || '',
                                duration: el.getAttribute('data-duration') || ''
                            };
                            const parent = el.parentElement;
                            if (parent) {
                                const titleEl = parent.querySelector('.video_title, .video-title');
                                if (titleEl) videoData.title = titleEl.innerText?.trim();
                            }
                            if (videoData.src || videoData.poster) {
                                videos.push(videoData);
                            }
                        } else {
                            const text = el.innerText?.trim();
                            if (text && text.length > 5) {
                                paragraphs.push({
                                    index: currentParagraphIndex,
                                    text: text,
                                    html: el.innerHTML
                                });
                                currentParagraphIndex++;
                            }
                        }
                    });

                    // 提取互动数据（登录后可见）
                    const engagement = {};
                    try {
                        // 阅读数 - 多种选择器尝试
                        const readSelectors = [
                            '#js_read_num3', '#readNum', '.read-num',
                            '#read_num', '.read_num', '[data-read-num]'
                        ];
                        for (const sel of readSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent) {
                                engagement.readCount = el.textContent.trim();
                                break;
                            }
                        }

                        // 点赞数/在看数
                        const likeSelectors = [
                            '#js_like_num', '#likeNum', '.like-num',
                            '#like_num', '.like_num', '[data-like-num]'
                        ];
                        for (const sel of likeSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent) {
                                engagement.likeCount = el.textContent.trim();
                                break;
                            }
                        }

                        // 在看数（微信特有）
                        const watchSelectors = [
                            '#js_watched_num', '.watched-num', '#watched_num',
                            '.watched_num', '[data-watched-num]'
                        ];
                        for (const sel of watchSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent) {
                                engagement.watchCount = el.textContent.trim();
                                break;
                            }
                        }

                        // 评论数
                        const commentSelectors = [
                            '#js_comment_num', '.comment-num', '#comment_num',
                            '.js_comment_num', '[data-comment-num]'
                        ];
                        for (const sel of commentSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent) {
                                engagement.commentCount = el.textContent.trim();
                                break;
                            }
                        }

                        // 分享数（某些文章可见）
                        const shareSelectors = [
                            '#js_share_num', '.share-num', '[data-share-num]'
                        ];
                        for (const sel of shareSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent) {
                                engagement.shareCount = el.textContent.trim();
                                break;
                            }
                        }

                        // 检查是否有"登录后查看阅读量"提示
                        const loginPrompt = document.querySelector('.login-tips, .need-login, .login-required');
                        if (loginPrompt) {
                            engagement._loginRequired = true;
                        }

                    } catch (e) {
                        // 互动数据提取失败不影响主流程
                        console.error('互动数据提取失败:', e);
                    }

                    return {
                        title: title,
                        author: author,
                        publishTime: publishTime,
                        engagement: engagement,  // 新增：互动数据
                        content: contentEl.innerText,
                        paragraphs: paragraphs,
                        images: images,
                        videos: videos,  // 新增：视频列表
                        html: contentEl.innerHTML,
                        imageParagraphMap: images
                            .filter(img => img.paragraphIndex >= 0)
                            .map(img => ({
                                imageIndex: img.index,
                                paragraphIndex: img.paragraphIndex,
                                src: img.src
                            }))
                    };
                }''')

                if not data:
                    return {'error': 'parse_empty', 'message': '未找到文章内容'}

                # 使用 OG 元数据填补空缺
                if og_meta.get('title') and not data.get('title'):
                    data['title'] = og_meta['title']
                if og_meta.get('author') and not data.get('author'):
                    data['author'] = og_meta['author']
                if og_meta.get('publishTime') and not data.get('publishTime'):
                    data['publishTime'] = og_meta['publishTime']

                data['og_meta'] = og_meta

                # 保存截图（如果指定了路径）
                if screenshot_path:
                    page.screenshot(path=screenshot_path, full_page=True)
                    data['screenshot_path'] = screenshot_path

                return data
            finally:
                # 确保浏览器被关闭，防止资源泄漏
                if browser:
                    browser.close()

    except ImportError:
        return {'error': 'Playwright 未安装，运行: pip install playwright && playwright install chromium'}
    except Exception as e:
        return {'error': 'fetch_error', 'message': str(e)}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='微信文章 Playwright 抓取')
    parser.add_argument('url', help='文章 URL')
    parser.add_argument('--screenshot', action='store_true', help='保存截图')
    parser.add_argument('--auth', help='使用已保存的登录态账号')
    parser.add_argument('--auth-dir', default='./data/auth', help='登录态存储目录')

    args = parser.parse_args()

    # 生成截图路径
    screenshot_path = None
    if args.screenshot:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f'/tmp/wechat_screenshot_{timestamp}.png'

    result = scrape_with_playwright(
        args.url,
        screenshot_path=screenshot_path,
        auth_account=args.auth,
        auth_storage_dir=args.auth_dir
    )

    if 'error' in result:
        logger.error(result.get('message', result['error']))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)

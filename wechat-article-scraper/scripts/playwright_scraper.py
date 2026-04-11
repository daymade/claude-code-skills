#!/usr/bin/env python3
"""
Playwright 抓取脚本 - 用于 stable 策略

单独脚本形式运行，避免在主进程中加载 Playwright
支持 OG 元数据备选提取和图片段落关联
"""

import sys
import json


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


def scrape_with_playwright(url: str, screenshot_path: str = None) -> dict:
    """
    使用 Playwright 抓取微信文章

    支持：
    - 滚动触发懒加载
    - OG 元数据备选
    - 图片段落关联
    - 装饰性图片过滤
    - 页面截图（可选）

    Args:
        url: 微信文章 URL
        screenshot_path: 截图保存路径（可选）
    """
    # 验证 URL
    if not _validate_url(url):
        return {'error': f'不支持的 URL: 必须是微信文章链接'}

    browser = None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                )
                page = context.new_page()

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

                    // 提取图片和段落
                    const images = [];
                    const paragraphs = [];
                    let currentParagraphIndex = 0;

                    const allElements = contentEl.querySelectorAll('p, section, img');
                    allElements.forEach((el) => {
                        if (el.tagName.toLowerCase() === 'img') {
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

                    return {
                        title: title,
                        author: author,
                        publishTime: publishTime,
                        content: contentEl.innerText,
                        paragraphs: paragraphs,
                        images: images,
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
    if len(sys.argv) < 2:
        print('用法: python3 playwright_scraper.py <url> [--screenshot]', file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    screenshot = '--screenshot' in sys.argv

    # 生成截图路径
    screenshot_path = None
    if screenshot:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = f'/tmp/wechat_screenshot_{timestamp}.png'

    result = scrape_with_playwright(url, screenshot_path)

    if 'error' in result:
        print(result.get('message', result['error']), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)

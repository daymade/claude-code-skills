#!/usr/bin/env python3
"""
Playwright 抓取脚本 - 用于 stable 策略

单独脚本形式运行，避免在主进程中加载 Playwright
"""

import sys
import json


def scrape_with_playwright(url: str) -> dict:
    """使用 Playwright 抓取微信文章"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = context.new_page()

            # 导航到文章
            page.goto(url, wait_until='networkidle', timeout=30000)

            # 检查是否被拦截
            if '环境异常' in page.content() or 'verify' in page.url:
                browser.close()
                return {'error': '触发反爬验证'}

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

            # 提取数据
            data = page.evaluate('''() => {
                const contentEl = document.querySelector('#js_content');
                if (!contentEl) return null;

                const images = [];
                contentEl.querySelectorAll('img').forEach((img, i) => {
                    const realSrc = img.getAttribute('data-src') || img.src;
                    if (realSrc && !realSrc.includes('data:image/svg+xml')) {
                        images.push({ index: i, src: realSrc, alt: img.alt || '' });
                    }
                });

                return {
                    title: document.querySelector('#activity_name')?.innerText
                        || document.querySelector('#activity-name')?.innerText
                        || document.title,
                    author: document.querySelector('#js_name')?.innerText
                        || document.querySelector('.profile_nickname')?.innerText
                        || '',
                    publishTime: document.querySelector('#publish_time')?.innerText
                        || document.querySelector('#publish-time')?.innerText
                        || '',
                    content: contentEl.innerText,
                    images: images,
                    html: contentEl.innerHTML
                };
            }''')

            browser.close()

            if not data:
                return {'error': '未找到文章内容'}

            return data

    except Exception as e:
        return {'error': str(e)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python3 playwright_scraper.py <url>', file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    result = scrape_with_playwright(url)

    if 'error' in result:
        print(result['error'], file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)

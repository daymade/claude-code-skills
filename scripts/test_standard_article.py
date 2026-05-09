import subprocess
import json

# 使用用户之前提供的 URL
url = "https://mp.weixin.qq.com/s/IUS7WXbcfN-PW7PNq3Z0AA?scene=1"

print("测试标准文章提取...")
subprocess.run(['agent-browser', 'open', url, '--timeout', '30000'], capture_output=True)

# 检查是否有 js_content 及其图片
script = """
(function() {
    const content = document.querySelector('#js_content');
    const richContent = document.querySelector('.rich_media_content');

    // 尝试多种选择器
    const selectors = [
        '#js_content img',
        '.rich_media_content img',
        '#img-content img',
        'article img'
    ];

    const results = {};
    selectors.forEach(sel => {
        const imgs = document.querySelectorAll(sel);
        results[sel] = imgs.length;
    });

    // 获取页面所有图片的 data-src
    const allImgs = document.querySelectorAll('img');
    const dataSrcImgs = [];
    allImgs.forEach(img => {
        const src = img.getAttribute('data-src');
        if (src && src.includes('mmbiz')) {
            dataSrcImgs.push(src.substring(0, 50));
        }
    });

    return {
        selectors: results,
        dataSrcImages: dataSrcImgs.slice(0, 5),
        hasRichContent: !!document.querySelector('.rich_media_content')
    };
})()
"""

result = subprocess.run(['agent-browser', 'eval', script], capture_output=True, text=True)
print(result.stdout)

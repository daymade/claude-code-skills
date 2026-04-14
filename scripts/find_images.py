import subprocess
import json

url = "https://mp.weixin.qq.com/s/IUS7WXbcfN-PW7PNq3Z0AA?scene=1"

print("1. 打开页面...")
subprocess.run(['agent-browser', 'open', url, '--timeout', '30000'], capture_output=True)

print("\n2. 查找图片位置...")

script = """
(function() {
    const allImgs = document.querySelectorAll('img');
    const results = [];

    allImgs.forEach((img, i) => {
        const parent = img.parentElement;
        const grandparent = parent?.parentElement;

        results.push({
            index: i,
            src: (img.getAttribute('data-src') || img.src).substring(0, 60),
            parent_tag: parent?.tagName,
            parent_id: parent?.id,
            parent_class: parent?.className?.substring(0, 30),
            grandparent_tag: grandparent?.tagName,
            grandparent_id: grandparent?.id
        });
    });

    return results;
})()
"""

result = subprocess.run(['agent-browser', 'eval', script], capture_output=True, text=True)

try:
    data = json.loads(result.stdout)
    print(f"找到 {len(data)} 张图片:\n")
    for img in data:
        print(f"[{img['index']}] {img['src']}...")
        print(f"    父元素: {img['parent_tag']}#{img['parent_id']}.{img['parent_class']}")
        print(f"    祖父: {img['grandparent_tag']}#{img['grandparent_id']}")
        print()
except Exception as e:
    print(f"错误: {e}")
    print(f"输出: {result.stdout[:500]}")

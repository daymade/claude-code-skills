# 微信公众号抓取失败方案记录

本文档记录所有尝试过的失败方案，防止未来的 agent 重走弯路。

## 方案 1: WebFetch 直接抓取

**尝试方式**：
```python
WebFetch(url="https://mp.weixin.qq.com/s/xxxxx", prompt="提取文章内容")
```

**失败表现**：
返回"环境异常"验证页，而非真实内容：
```
当前环境异常，完成验证后即可继续访问
去验证
```

**根因分析**：
微信服务器检测请求 UA 和 IP 特征，非浏览器请求被拦截。
验证页使用 JavaScript 动态加载 CAPTCHA，需要真实浏览器环境。

**结论**：❌ 不可行

---

## 方案 2: Snapshot 方式

**尝试方式**：
```python
mcp__chrome-devtools__take_snapshot()
```

**失败表现**：
- 只能看到 accessibility tree 的文本节点
- 图片显示为 placeholder SVG：
  ```
  data:image/svg+xml,%3C%3Fxml version='1.0'...%3E%3Crect width='1' height='1'/%3E
  ```

**根因分析**：
微信文章使用懒加载（lazy loading）机制：
- 初始 HTML 中图片 `src` 为 1x1 透明 SVG 占位符
- 真实图片 URL 存储在 `data-src` 属性
- 只有当图片滚动到视口时，JavaScript 才将 `data-src` 复制到 `src`

**结论**：❌ 不完整，需要触发滚动

---

## 方案 3: opencli 探索

**尝试方式**：
```bash
opencli explore "https://mp.weixin.qq.com/s/xxxxx"
opencli list | grep -i wechat
```

**失败表现**：
- 无微信相关 CLI 已注册
- 微信页面结构复杂，opencli 无法自动识别可用 API

**根因分析**：
微信公众号是封闭生态，无公开 API 供 CLI 工具调用。

**结论**：❌ 无可用工具

---

## 方案 4: curl/wget 命令行

**尝试方式**：
```bash
curl -H "User-Agent: Mozilla/5.0..." https://mp.weixin.qq.com/s/xxxxx
```

**失败表现**：
返回 HTML 验证页，与 WebFetch 相同。

**根因分析**：
- 缺少微信登录态 Cookie
- 微信检测 TLS 指纹、HTTP/2 行为等多维特征
- 纯 HTTP 客户端无法绕过反爬

**结论**：❌ 不可行

---

## 唯一可行方案

**Chrome DevTools MCP + JavaScript 执行**：

成功要素：
1. ✅ 利用 Chrome 已有登录态（Cookie）
2. ✅ 真实浏览器 UA 和网络栈
3. ✅ JavaScript 滚动触发懒加载
4. ✅ 等待 2 秒让图片完全加载
5. ✅ 提取 `data-src` 中的真实图片 URL

这是经过 4 次失败尝试后验证的唯一可行方案。

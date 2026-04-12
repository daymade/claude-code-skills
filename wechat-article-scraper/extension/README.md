# 微信文章抓取助手 - 浏览器扩展

一键抓取微信公众号文章内容，支持 Chrome 和 Firefox 浏览器。

## 功能特性

- **一键抓取**: 点击扩展图标即可抓取当前微信文章
- **多种格式**: 支持导出为 Markdown、HTML、JSON
- **图片下载**: 可选下载文章中的图片
- **右键菜单**: 在文章页面右键即可抓取
- **快捷键**: `Ctrl+Shift+S` 快速抓取
- **Web 集成**: 自动上传到本地 Web 仪表盘

## 安装方法

### Chrome / Edge

1. 打开 Chrome 扩展管理页面: `chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `extension/chrome` 文件夹
5. 完成！扩展图标会出现在工具栏

### Firefox

1. 打开 Firefox 调试页面: `about:debugging`
2. 点击"此 Firefox"
3. 点击"临时载入附加组件"
4. 选择 `extension/firefox/manifest.json`
5. 完成！

## 使用说明

### 基本使用

1. 打开任意微信公众号文章 (`mp.weixin.qq.com/s/...`)
2. 点击工具栏的扩展图标
3. 选择导出格式 (Markdown/HTML/JSON)
4. 点击"抓取当前文章"
5. 文章会自动下载或复制到剪贴板

### 快捷键

- `Ctrl+Shift+W` (Mac: `Cmd+Shift+W`): 打开扩展面板
- `Ctrl+Shift+S` (Mac: `Cmd+Shift+S`): 快速抓取当前文章

### 右键菜单

在微信文章页面右键，可以看到:
- 📰 抓取此微信文章
- 🖼️ 抓取并下载图片
- 📊 打开 Web 仪表盘

### 设置选项

在扩展面板中:
- **保存到本地**: 自动下载文章文件
- **上传到服务器**: 发送到本地 Web 仪表盘 (需要启动 web/backend)
- **自动分类**: 使用 AI 自动分类文章

## 文件结构

```
extension/
├── chrome/
│   ├── manifest.json          # Chrome 扩展配置
│   ├── popup/                 # 弹出窗口 (共用)
│   └── icons/                 # 图标 (共用)
├── firefox/
│   ├── manifest.json          # Firefox 扩展配置
│   └── ...
└── shared/
    ├── popup/
    │   ├── popup.html         # 弹出窗口 HTML
    │   └── popup.js           # 弹出窗口逻辑
    ├── content/
    │   ├── content.js         # 内容脚本 (注入到页面)
    │   └── content.css        # 内容样式
    └── background/
        └── background.js      # 后台脚本
```

## 开发调试

### 修改代码后刷新

- **Chrome**: 扩展管理页面点击刷新按钮
- **Firefox**: 调试页面点击重新加载

### 查看日志

- 扩展面板: 右键检查
- 内容脚本: 页面开发者工具 Console
- 后台脚本: 扩展管理页面的"服务工作进程"

## 注意事项

1. 仅适用于微信公众号文章 (`mp.weixin.qq.com`)
2. 需要登录微信才能查看完整内容
3. 部分文章可能有反爬限制
4. 图片下载功能会占用较多带宽

## 竞品对比

| 功能 | 其他工具 | 我们 |
|------|---------|------|
| 浏览器扩展 | ❌ 无 | ✅ Chrome + Firefox |
| 一键抓取 | ❌ 需要复制链接 | ✅ 直接在当前页面 |
| 右键菜单 | ❌ 无 | ✅ 集成到右键 |
| 快捷键 | ❌ 无 | ✅ Ctrl+Shift+S |

**唯一支持浏览器扩展的微信文章抓取工具！**

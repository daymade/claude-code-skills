# Ralph Loop Round 71 - Completed

## 竞品差距分析
当前 v3.28.0 vs 竞品能力矩阵：
- wcplusPro: 有成熟的 Chrome 扩展用于一键采集
- 新榜/西瓜数据: 有自己的浏览器插件
- 开源竞品: 无此功能

Gap: 浏览器扩展是用户便捷使用的重要入口

## 实施结果
- 浏览器扩展 v2.0 完善 ✅
  - Chrome/Firefox Manifest V3 扩展
  - Content Script: 页面内容提取、文章数据解析
    - 标题、作者、发布时间提取
    - 正文内容提取（段落、HTML）
    - 图片提取（data-src、data-backsrc）
    - 视频提取
    - 互动数据读取（阅读数、点赞数、在看数）
  - Background Script: 右键菜单、快捷键、自动下载
    - 右键菜单：抓取文章、抓取并下载图片、打开仪表盘
    - 快捷键：Ctrl+Shift+S 快速抓取
    - Tab 状态监听和徽章显示
  - Popup UI: 格式选择、进度显示、结果操作
    - 状态检测（是否在文章页面）
    - 格式选择：Markdown/HTML/JSON
    - 设置开关：保存本地、上传服务器、自动分类
    - 进度条和结果展示
    - 查看/下载/复制结果
  - w extension CLI命令: install/pack/check
- v3.29.0, 52个唯一支持特性 ✅

## 版本
v3.28.0 → v3.29.0

## 提交
6c5f24d feat(wechat-article-scraper): 浏览器扩展 v2.0 完善

# 微信文章抓取助手 CLI

World-class WeChat Article Scraper Command Line Interface

## 安装

### 方式一：pip 安装

```bash
cd cli
pip install -e .
```

### 方式二：单文件可执行程序

```bash
# 安装依赖
pip install pyinstaller

# 构建单文件可执行程序
pyinstaller w.spec --clean

# 可执行文件在 dist/w
```

## 使用方法

### 抓取单篇文章

```bash
# 基础抓取
w scrape "https://mp.weixin.qq.com/s/xxxxx"

# 指定格式和策略
w scrape "https://mp.weixin.qq.com/s/xxxxx" -f json -s adaptive

# 下载图片
w scrape "https://mp.weixin.qq.com/s/xxxxx" --images -o ./article.md
```

### 批量抓取

```bash
# urls.txt 每行一个 URL
w batch urls.txt -o ./output --workers 5
```

### 搜索发现

```bash
# 搜狗搜索微信文章
w search "人工智能" --limit 20 -o results.json
```

### 监控订阅

```bash
# 添加监控
w monitor add MzI5NjA0MTIxMA== --interval 3600

# 查看监控列表
w monitor list

# 移除监控
w monitor remove MzI5NjA0MTIxMA==
```

### 配置管理

```bash
# 查看配置
w config --show

# 编辑配置
w config --edit
```

## 命令列表

| 命令 | 说明 | 示例 |
|------|------|------|
| `scrape` | 抓取单篇文章 | `w scrape <url>` |
| `batch` | 批量抓取 | `w batch urls.txt` |
| `search` | 搜狗搜索 | `w search <keyword>` |
| `monitor` | 监控管理 | `w monitor add <biz_id>` |
| `config` | 配置管理 | `w config --show` |
| `version` | 版本信息 | `w version` |

## 策略说明

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `auto` | 自动选择最佳策略 | 默认推荐 |
| `fast` | requests + BeautifulSoup | 简单文章，速度快 |
| `adaptive` | Scrapling 自适应 | 需要JS渲染 |
| `stable` | Playwright 无头浏览器 | 复杂页面 |
| `reliable` | Playwright + 重试机制 | 高可靠性要求 |
| `zero_dep` | 纯标准库，零依赖 | 无 pip 环境 |
| `jina_ai` | Jina AI 服务 | 最后保障 |

## 配置文件

配置文件位于 `~/.wechat-scraper/config.yaml`：

```yaml
default_format: markdown
default_strategy: auto
download_images: false
output_dir: ~/Downloads/wechat-articles

monitor:
  interval: 3600
  max_articles: 10

api:
  openai: sk-xxx
  deepseek: sk-xxx
```

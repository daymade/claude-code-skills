# 测试说明

本目录下的测试使用 pytest，**不依赖任何外部网络请求**。

## 运行

```bash
# 进入 skill 目录（把 /path/to 换成实际路径）
cd /path/to/ashare-news-fetcher

# 使用 uv 运行 pytest
uv run --with pytest pytest tests/test_fetch_intel.py -v
```

## 覆盖范围

| 模块 | 说明 |
|---|---|
| Symbol extraction | 正则提取上海/深圳/创业板/科创板/北交所代码；排除指数代码；多代码排序；13 位时间戳不误匹配；extra_names 映射 |
| Sentiment scoring |  bullish / bearish / neutral 判定；否定前缀（不/未/没有/非/否认/难以）翻转 polarity；score 边界 |
| InfoItem serialization | 字段完整性；item_id 由 `source_id:title:url` SHA-256 前 16 位生成，确定性且唯一；JSON 往返 |
| Policy high-impact | 财政/货币/监管/交易所关键词触发 `is_high_impact=True`；中性标题不触发 |
| URL / constants | `_CLS_HOME` 常量值为 bare token `home`，拼接后 URL 正确；不会触发绝对路径误报 |
| HTML strip | 标签清除、空字符串、多标签嵌套 |
| Markdown output | 标题、代码、链接均出现在输出中；空列表不报错 |
| Network-mocked fetchers | `tests/test_fetch_intel_network.py`：用 fake `requests.Session` 覆盖证监会 JSON API、央行 HTML、财联社/华尔街见闻/东财快讯 API 的请求/解析路径 |

## 依赖

运行测试需要安装 `pytest`、`requests`、`beautifulsoup4`：

```bash
uv run --with pytest --with beautifulsoup4 --with requests pytest tests/ -v
```

# 信源 API 参考

本 skill 调用的都是公开、无需 API Key 的接口，仅用于信息聚合。

## 中文财经快讯（`cn`）

### 财联社（CLS）电报
- URL: `https://www.cls.cn/api/cache`
- 方法: GET
- 参数: `app=CailianpressWeb`, `name=telegraph`, `os=web`, `sv=8.7.9`
- Headers: `Referer: https://www.cls.cn/telegraph`
- 解析: `data.roll_data[]`；不存在时依次回退 `data.telegraph[]`、`data.roll[]`、`data.depth_list[]`。字段：`title`, `brief`, `content`, `ctime`, `id`, `level`, `subjects[].subject_name`
- 说明：原 `v3/depth/home/assembled` 接口已要求签名并返回加载中占位，因此改用公开缓存接口。`ctime` 为 Unix 秒。

### 华尔街见闻实时快讯
- URL: `https://api-one.wallstcn.com/apiv1/content/lives`
- 方法: GET
- 参数: `channel=global-channel`, `limit={limit}`
- Headers: `Referer: https://wallstreetcn.com/`, `Origin: https://wallstreetcn.com`
- 解析: `data.items[]` → `content_text`, `display_time`, `uri`, `is_important`

### 金十数据快讯
- URL: `https://flash-api.jin10.com/get_flash_list`
- 方法: GET
- 参数: `channel=-8200`, `max_time=`
- Headers: `Referer: https://www.jin10.com/`, `Origin: https://www.jin10.com`, `x-app-id: <JIN10_APP_ID>`, `x-version: 1.0.0`
- 解析: `data[]` → `data.content`, `time`, `important`
- 说明: `x-app-id` 已从脚本中移除硬编码回退，需在环境变量 `JIN10_APP_ID` 中配置；未配置时 `jin10` 来源会跳过，不影响其他 `cn` 来源。

### 新浪 7x24 全球实时快讯
- URL: `https://zhibo.sina.com.cn/api/zhibo/feed`
- 方法: GET
- 参数: `page=1`, `page_size={limit}`, `zhibo_id=152`, `tag_id=0`, `type=0`
- Headers: `Referer: https://finance.sina.com.cn/7x24/`
- 解析: `result.data.feed.list[]` → `rich_text`, `create_time`, `is_top`, `tag[].name`

### 东方财富快讯
- URL: `https://np-listapi.eastmoney.com/comm/web/getNewsByColumns`
- 方法: GET
- 参数: `client=web`, `biz=web_home_channel`, `column=350,35,466,467`, `order=1`, `needInteractData=0`, `page_index=1`, `page_size={limit}`，以及每次请求需动态生成一个 UUID 作为 `req_trace`
- 解析: `data.list[]` → `title`, `summary`, `showTime`, `uniqueUrl`, `mediaName`

## 政策监管（`policy`）

需要 `beautifulsoup4`（证监会来源使用 JSON API，无需 bs4）。

| 来源 | URL | 解析方式 | 状态 |
|---|---|---|---|
| 证监会 | `https://www.csrc.gov.cn/searchList/<channelid>?_isAgg=true&_isJson=true&_pageSize=20&_template=index&page=1` | JSON：`data.results[]` → `title`, `url`, `publishedTimeStr` | **已启用**（channelid `a1a078ee0bc54721ab6b148884c784a8` 对应"证监会要闻"，2026-06-26 验证） |
| 央行 | `https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html` | HTML 列表：`td:has(font.newslist_style)` → `a`, `span.hui12` | 启用 |
| 上交所 | `https://www.sse.com.cn/disclosure/announcement/general/` | HTML 列表：`.sse_list_1 dl` → `a`, `span` | 启用 |
| 财政部 | `https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/` | HTML 列表：`ul.xwfb_listbox li` → `a`, `span` | 启用 |

证监会 JSON API 说明：
- `channelid` 是 WCM 栏目 ID；`a1a078ee0bc54721ab6b148884c784a8` 为当前"证监会要闻"栏目 ID。
- 返回的 `url` 字段为协议相对链接（如 `//www.csrc.gov.cn/...`），脚本会补全为 `https://...`。
- 旧版 HTML 列表 `c100746/common_list.shtml` 已永久 302 重定向至首页，不再使用。

### 获取 CSRC `channelid` 的方法

1. 打开浏览器，访问 `https://www.csrc.gov.cn/` 并进入目标栏目（如"证监会要闻"）。
2. 按 `F12` 打开 DevTools，切换到 **Network** 标签。
3. 在页面内使用搜索框输入任意关键词（如"IPO"）并搜索。
4. 在 Network 面板中过滤 `searchList` 请求，找到类似 `searchList/<channelid>?_isAgg=true&_isJson=true...` 的 URL。
5. 提取该 URL 中的 `channelid` UUID（如 `a1a078ee0bc54721ab6b148884c784a8`），填入脚本配置即可。

> 注意：栏目改版或迁移时 `channelid` 可能变更，若发现该来源返回空数据，请按上述步骤重新抓取当前栏目的 `channelid`。

### 旧版 HTML 列表永久重定向

- 旧地址 `https://www.csrc.gov.cn/csrc/c100746/common_list.shtml` 已返回 **302** 永久重定向至首页，不再可用。
- 所有 `policy` 来源下的 CSRC 数据均通过上述 JSON API（`searchList/<channelid>`）获取。

## 股吧情绪（`guba`）

### 主 API
- URL: `https://gbapi.eastmoney.com/stkpost/api/v1/post/listbystock`
- 方法: GET
- 参数: `stockcode={code}`, `pageindex=1`, `pagesize=30`, `sort=posttime`, `source=web`
- 解析: `re[]` → `title`, `post_title`, `post_content`, `read_count`, `comment_count`, `user_type`

### HTML 备用
- URL: `https://guba.eastmoney.com/list,{code}.html`
- 解析: 列表页 `read` / `reply` / `title` 字段

### 情绪算法
- 维护牛/熊关键词权重表（1-3 分）
- 检测否定前缀（不、未、没有、非、否认、难以），遇到时反向计分
- 综合得分 = (bull - bear) / (bull + bear)，范围 [-1, 1]
- > 0.15 为 bullish，< -0.15 为 bearish，否则 neutral

## BSE（北京证券交易所）代码处理

### 代码前缀规则
- BSE 股票代码以 **8 开头**，常见前缀：83、87、88、89。
- 在部分数据源（如东方财富）中，BSE 代码会带有 `BJ` 前缀（例如 `BJ430047`）。
- **脚本内部已统一处理**：在调用股吧（Guba）API 前，会自动剥离 `BJ` 前缀，仅保留纯数字代码（如 `430047`）。

### Guba API 参数说明
- Guba 主 API 的 `stockcode` 参数**仅接受纯数字代码**，不接受带前缀的格式。
- 若传入带 `BJ` 前缀的代码，API 将返回空数据或报错。
- 因此，脚本在构造 `guba` 请求前，会先执行 `code = code.replace("BJ", "")` 进行清洗。

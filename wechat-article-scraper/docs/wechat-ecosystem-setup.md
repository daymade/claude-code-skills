# 微信生态集成配置指南

## 概述

微信生态集成实现了 **Cubox 级别的"微信转发即收藏"体验**，将保存流程从 3 步缩短到 1 步：

| 方案 | 操作步骤 | 适用场景 |
|-----|---------|---------|
| **微信小程序** (推荐) | 文章页面 → 转发给朋友 → 选择"文章收藏助手" | 微信内一键保存 |
| **微信公众号** (备用) | 复制链接 → 发送到公众号 | 无需审核快速启动 |

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户在微信内                              │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌──────────────────────┐      ┌──────────────────────┐
    │    微信小程序方案     │      │   微信公众号方案      │
    │   (推荐，体验最佳)    │      │   (备用，无需审核)    │
    └──────────────────────┘      └──────────────────────┘
              │                               │
              ▼                               ▼
    ┌──────────────────────┐      ┌──────────────────────┐
    │   onShareAppMessage  │      │   接收文本消息        │
    │   提取文章链接        │      │   提取URL            │
    └──────────────────────┘      └──────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
              ┌───────────────────────────────┐
              │     Backend API 处理           │
              │   /api/wechat/miniapp/save     │
              │   /api/wechat/official/webhook │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     创建异步抓取任务           │
              │     scrape_jobs 表            │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     6级策略路由抓取            │
              │     fast → adaptive → stable  │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     返回保存结果               │
              │     小程序：跳转阅读           │
              │     公众号：回复链接           │
              └───────────────────────────────┘
```

## 配置步骤

### 1. 微信小程序配置

#### 1.1 注册小程序
1. 访问 [微信公众平台](https://mp.weixin.qq.com/)
2. 选择"小程序"注册（需要企业资质）
3. 完成认证（300元/年）

#### 1.2 获取 AppID 和 Secret
1. 登录小程序后台 → 开发 → 开发设置
2. 记录 **AppID(小程序ID)**
3. 生成并记录 **AppSecret(小程序密钥)**

#### 1.3 配置服务器域名
在"开发 → 开发设置 → 服务器域名"中添加：
- request合法域名: `https://api.your-domain.com`
- uploadFile合法域名: `https://api.your-domain.com`
- downloadFile合法域名: `https://api.your-domain.com`

#### 1.4 配置环境变量
```bash
WECHAT_MINIAPP_APPID=wx_your_appid
WECHAT_MINIAPP_SECRET=your_secret
```

#### 1.5 提交审核
1. 下载开发者工具，导入 `wechat-miniprogram/` 目录
2. 填写 AppID
3. 上传代码 → 提交审核
4. 审核通过后发布

### 2. 微信公众号配置

#### 2.1 注册公众号
1. 访问 [微信公众平台](https://mp.weixin.qq.com/)
2. 选择"订阅号"或"服务号"（个人可用订阅号）
3. 完成注册和认证

#### 2.2 获取配置信息
1. 基本配置 → 公众号开发信息
2. 记录 **AppID** 和 **AppSecret**
3. 服务器配置 → 启用并设置：
   - URL: `https://api.your-domain.com/api/wechat/official/webhook`
   - Token: 自定义令牌（用于签名验证）
   - EncodingAESKey: 随机生成

#### 2.3 配置环境变量
```bash
WECHAT_OFFICIAL_APPID=wx_your_appid
WECHAT_OFFICIAL_SECRET=your_secret
WECHAT_OFFICIAL_TOKEN=your_token
```

#### 2.4 启用自动回复
公众号设置 → 功能设置 → 启用"自动回复"

### 3. 数据库迁移

执行迁移文件创建必要的数据表：

```bash
# 使用 Supabase CLI
supabase db reset

# 或手动执行 SQL
# 文件: cloud/supabase/migrations/006_wechat_bindings.sql
```

## API 端点

### 小程序 API

#### POST /api/wechat/miniapp/login
微信登录，换取 session。

**请求:**
```json
{
  "code": "wechat_login_code"
}
```

**响应:**
```json
{
  "token": "jwt_token",
  "userId": "user_uuid",
  "isNew": true
}
```

#### POST /api/wechat/miniapp/save
保存文章（从小程序调用）。

**请求:**
```json
{
  "url": "https://mp.weixin.qq.com/s/...",
  "title": "文章标题",
  "code": "wechat_login_code"
}
```

**响应:**
```json
{
  "success": true,
  "jobId": "job_uuid",
  "status": "processing"
}
```

#### GET /api/wechat/miniapp/save?jobId=xxx
查询保存任务状态。

**响应:**
```json
{
  "jobId": "job_uuid",
  "status": "completed",
  "result": { "articleId": "...", "title": "..." },
  "error": null
}
```

### 公众号 API

#### GET /api/wechat/official/webhook
服务器验证（微信服务器配置用）。

#### POST /api/wechat/official/webhook
接收微信消息推送。

**自动处理:**
- 文本消息 → 提取URL → 创建抓取任务 → 异步处理 → 回复结果

## 用户绑定流程

### 场景1: 新用户（小程序）
```
用户转发文章到小程序
  → 小程序获取 code
  → 后端 code2Session 获取 openid
  → 创建新用户 + 绑定记录
  → 返回 token
  → 自动保存文章
```

### 场景2: 新用户（公众号）
```
用户发送链接到公众号
  → 公众号收到消息
  → 发现未绑定用户
  → 回复绑定链接
  → 用户访问 /wechat/bind?openid=xxx
  → 登录/注册后创建绑定
  → 后续直接保存
```

### 场景3: 已有用户绑定公众号
```
用户访问 /wechat/bind?openid=xxx
  → 登录现有账号
  → 创建 wechat_bindings 记录
  → 绑定成功
  → 可直接发送链接到公众号
```

## 目录结构

```
wechat-article-scraper/
├── cloud/
│   └── src/
│       └── app/
│           ├── api/wechat/
│           │   ├── miniapp/
│           │   │   ├── login/route.ts      # 小程序登录
│           │   │   └── save/route.ts       # 小程序保存API
│           │   └── official/
│           │       └── webhook/route.ts    # 公众号消息处理
│           └── wechat/
│               └── bind/
│                   └── page.tsx            # 账号绑定页面
├── wechat-miniprogram/                    # 小程序源码
│   ├── app.js
│   ├── app.json
│   └── pages/
│       ├── index/                         # 文章列表页
│       └── save/                          # 保存页面
└── cloud/supabase/migrations/
    └── 006_wechat_bindings.sql            # 数据库迁移
```

## 监控指标

```
微信保存转化率 = 微信保存次数 / 微信文章打开次数
目标: > 80%

平均保存时间 = 从转发到保存完成的时间
目标: < 5秒

用户绑定率 = 绑定微信的用户 / 总用户
目标: > 60%

任务成功率 = 成功抓取数 / 总任务数
目标: > 95%
```

## 故障排查

### 小程序无法登录
- 检查 AppID 和 Secret 是否正确
- 检查服务器域名是否配置
- 查看 `wechat_bindings` 表是否有记录

### 公众号无响应
- 检查 webhook URL 是否可达
- 验证 Token 配置是否正确
- 查看服务器日志确认收到请求
- 检查消息加密模式（建议先用明文模式测试）

### 保存失败
- 检查 `scrape_jobs` 表状态
- 查看抓取日志
- 确认文章 URL 格式正确（mp.weixin.qq.com）

## 竞品对比

| 功能 | Cubox | Matter | 我们 (Round 92) |
|-----|-------|--------|----------------|
| 微信转发保存 | ✅ | ✅ | ✅ 小程序 |
| 公众号消息 | ✅ | ❌ | ✅ 备用路径 |
| 保存进度显示 | ✅ | ✅ | ✅ 实时 |
| 重复检测 | ✅ | ✅ | ✅ 自动提示 |

## 后续优化

1. **消息推送**: 保存完成后微信模板消息通知
2. **UnionID**: 打通小程序和公众号用户身份
3. **支付集成**: 小程序内订阅/支付
4. **社交功能**: 小程序内分享文章给好友

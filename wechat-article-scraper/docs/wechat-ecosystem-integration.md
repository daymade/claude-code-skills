# 微信生态深度集成方案

## 目标
实现 Cubox 级别的"微信转发即收藏"体验

## 用户流程对比

### 当前流程（3步）
```
微信文章 → 复制链接 → 打开Extension → 粘贴 → 点击保存
```

### 目标流程（1步）
```
微信文章 → 转发给小程序/公众号 → 自动保存
```

## 技术架构

### 方案A：微信小程序（推荐）

```
用户在微信内
    ↓
点击文章右上角「...」
    ↓
选择「转发给朋友」
    ↓
选择「文章收藏助手」小程序
    ↓
小程序 onShareAppMessage 接收链接
    ↓
调用 backend API /api/wechat/miniapp/save
    ↓
Backend 触发抓取任务
    ↓
返回小程序：保存成功 + 文章预览
```

**优势：**
- 无需离开微信
- 可以展示保存进度
- 支持返回已保存文章列表

**劣势：**
- 需要小程序审核
- 需要企业资质

### 方案B：微信公众号

```
用户在微信内
    ↓
复制文章链接
    ↓
发送给「文章收藏助手」公众号
    ↓
公众号接收消息，解析链接
    ↓
调用 backend API /api/wechat/official/save
    ↓
Backend 触发抓取任务
    ↓
公众号回复：保存成功 + 阅读链接
```

**优势：**
- 个人订阅号即可
- 无需审核
- 可以推送通知

**劣势：**
- 需要手动复制粘贴
- 交互不如小程序流畅

### 方案C：企业微信机器人

```
用户在任意聊天
    ↓
@文章收藏助手 + 文章链接
    ↓
机器人接收消息
    ↓
调用 backend API
    ↓
回复保存结果
```

## 推荐实现：A + B 双轨

### 1. 微信小程序 (主路径)

**文件结构：**
```
wechat-miniprogram/
├── app.js                 # 小程序入口
├── app.json               # 全局配置
├── pages/
│   ├── index/
│   │   ├── index.js       # 首页 - 展示已保存列表
│   │   ├── index.wxml
│   │   └── index.wxss
│   └── save/
│       ├── save.js        # 保存页面 - 接收分享
│       ├── save.wxml
│       └── save.wxss
├── utils/
│   └── api.js             # API 封装
└── components/
    └── article-card/      # 文章卡片组件
```

**核心代码：**

```javascript
// pages/save/save.js
Page({
  onLoad(options) {
    // 接收分享的文章链接
    const { url, title } = options;
    if (url) {
      this.saveArticle(url, title);
    }
  },

  async saveArticle(url, title) {
    wx.showLoading({ title: '保存中...' });
    
    try {
      const res = await wx.request({
        url: 'https://api.wechat-scraper.com/api/wechat/miniapp/save',
        method: 'POST',
        header: {
          'Authorization': `Bearer ${wx.getStorageSync('token')}`
        },
        data: { url, title }
      });

      if (res.data.success) {
        wx.showToast({ title: '保存成功', icon: 'success' });
        // 跳转到文章详情
        wx.navigateTo({
          url: `/pages/article/article?id=${res.data.articleId}`
        });
      }
    } catch (error) {
      wx.showToast({ title: '保存失败', icon: 'error' });
    }
  }
});
```

### 2. 微信公众号 (备用路径)

**消息处理：**

```typescript
// cloud/src/app/api/wechat/official/webhook/route.ts

export async function POST(request: Request) {
  const body = await request.json();
  
  // 验证微信签名
  if (!verifyWechatSignature(body)) {
    return new Response('Invalid signature', { status: 401 });
  }

  const { MsgType, Content, FromUserName } = body;

  // 提取URL
  const url = extractUrl(Content);
  
  if (url && isWechatArticle(url)) {
    // 异步保存
    const job = await saveArticleFromWechat(url, FromUserName);
    
    // 回复用户
    return Response.json({
      ToUserName: FromUserName,
      FromUserName: 'official_account',
      CreateTime: Date.now(),
      MsgType: 'text',
      Content: `正在保存文章...\n预计 10 秒后完成，完成后将通知您。`
    });
  }

  // 默认回复
  return Response.json({
    ToUserName: FromUserName,
    MsgType: 'text',
    Content: '请发送微信公众号文章链接，我会自动为您保存。'
  });
}
```

### 3. Backend API

```typescript
// cloud/src/app/api/wechat/miniapp/save/route.ts

export async function POST(request: Request) {
  const { url, title } = await request.json();
  const userId = await authenticateWechatUser(request);

  // 验证是微信文章
  if (!isValidWechatUrl(url)) {
    return Response.json({ error: 'Invalid WeChat article URL' }, { status: 400 });
  }

  // 检查是否已存在
  const existing = await findExistingArticle(userId, url);
  if (existing) {
    return Response.json({ 
      success: true, 
      articleId: existing.id,
      message: 'Article already saved'
    });
  }

  // 创建保存任务
  const job = await createScrapeJob({
    url,
    userId,
    source: 'wechat_miniapp',
    priority: 'high'
  });

  // 异步处理
  processScrapeJob(job);

  return Response.json({
    success: true,
    jobId: job.id,
    status: 'processing'
  });
}
```

## 认证方案

### 微信小程序登录

```javascript
// 小程序登录
wx.login({
  success: async (res) => {
    const { code } = res;
    
    // 发送到后端换取 token
    const result = await fetch('/api/wechat/miniapp/login', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    
    const { token, userId } = await result.json();
    wx.setStorageSync('token', token);
  }
});
```

### 公众号用户绑定

```
1. 用户首次发送链接
2. 后端生成绑定二维码/链接
3. 用户扫码登录 Web App
4. 完成公众号与账号绑定
5. 后续直接保存到绑定账号
```

## 数据库设计

```sql
-- 微信用户映射表
CREATE TABLE wechat_bindings (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES profiles(id),
  openid VARCHAR(255) UNIQUE,           -- 微信 OpenID
  unionid VARCHAR(255),                 -- 微信 UnionID
  app_type VARCHAR(50),                 -- 'miniapp' | 'official'
  bound_at TIMESTAMPTZ DEFAULT NOW()
);

-- 微信来源的文章
ALTER TABLE articles ADD COLUMN source VARCHAR(50);
ALTER TABLE articles ADD COLUMN source_metadata JSONB;
```

## 实施计划

### Phase 1: 公众号集成 (Week 1)
- [ ] 申请/配置公众号
- [ ] 实现 Webhook 消息处理
- [ ] 用户绑定流程
- [ ] 测试端到端流程

### Phase 2: 小程序 (Week 2-3)
- [ ] 注册小程序
- [ ] 开发保存页面
- [ ] 开发文章列表
- [ ] 提交审核

### Phase 3: Extension 优化 (Week 4)
- [ ] Extension 检测已保存文章
- [ ] 显示"已在收藏中"提示
- [ ] 快速跳转到阅读器

## 竞品差异化

| 功能 | Cubox | 我们 (Round 92) |
|------|-------|-----------------|
| 微信转发 | ✅ | ✅ 小程序 |
| 公众号 | ✅ | ✅ 消息 |
| Extension | ✅ | ✅ 已有 |
| 抓取速度 | ~5s | 目标 <3s |
| 离线阅读 | ✅ | ✅ PWA |
| TTS朗读 | ❌ | ✅ Round 91 |

## 关键指标

```
微信保存转化率 = 微信保存次数 / 微信文章打开次数
目标: > 80%

平均保存时间 = 从转发到保存完成的时间
目标: < 5秒

用户绑定率 = 绑定微信的用户 / 总用户
目标: > 60%
```

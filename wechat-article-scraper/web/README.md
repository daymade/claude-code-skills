# 微信文章抓取系统 - Web 界面

现代化的 React + TypeScript + Tailwind CSS Web 界面，提供直观的仪表盘、文章管理、任务队列和全文搜索功能。

## 技术栈

### 前端
- **React 18** + **TypeScript** - 现代 UI 框架
- **Vite** - 快速构建工具
- **Tailwind CSS** - 原子化 CSS 框架
- **TanStack Query** - 数据获取和缓存
- **React Router** - 客户端路由
- **Recharts** - 数据可视化图表
- **Lucide React** - 图标库

### 后端
- **FastAPI** - 高性能 Python Web 框架
- **SQLite + FTS5** - 全文搜索引擎
- **WebSocket** - 实时状态推送
- **Pydantic** - 数据验证

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
cd ..
pip install fastapi uvicorn pydantic

# 安装前端依赖
cd web/frontend
npm install
```

### 2. 启动后端

```bash
cd web/backend
python main.py
```

后端服务将在 `http://localhost:8000` 启动，API 文档访问 `http://localhost:8000/docs`。

### 3. 启动前端

```bash
cd web/frontend
npm run dev
```

前端开发服务器将在 `http://localhost:3000` 启动。

## 功能特性

### 📊 仪表盘
- 文章总量统计
- WCI 传播指数分布
- 分类分布图表
- 最新文章列表

### 📄 文章管理
- 文章列表浏览
- 按作者、分类筛选
- 文章详情查看
- 原文链接跳转
- 元数据展示（阅读量、点赞数、在看数）

### 🔍 全文搜索
- 标题和内容搜索
- 实时搜索结果
- 搜索结果高亮

### 📋 任务队列
- 创建批量抓取队列
- 实时进度监控
- 暂停/恢复/停止控制
- 任务状态追踪

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/articles` | GET | 获取文章列表 |
| `/api/articles/{id}` | GET | 获取文章详情 |
| `/api/articles/search` | GET | 搜索文章 |
| `/api/statistics` | GET | 获取统计数据 |
| `/api/queues` | GET/POST | 队列列表/创建 |
| `/api/queues/{id}` | GET | 队列详情 |
| `/api/queues/{id}/status` | GET | 队列状态 |
| `/api/queues/{id}/tasks` | GET | 队列任务 |
| `/api/queues/{id}/start` | POST | 启动队列 |
| `/api/queues/{id}/pause` | POST | 暂停队列 |
| `/api/queues/{id}/resume` | POST | 恢复队列 |
| `/api/queues/{id}/stop` | POST | 停止队列 |
| `/api/scrape` | POST | 单篇文章抓取 |
| `/api/ws` | WebSocket | 实时状态推送 |

## 项目结构

```
web/
├── backend/
│   └── main.py              # FastAPI 后端入口
├── frontend/
│   ├── src/
│   │   ├── api/             # API 客户端
│   │   ├── components/      # UI 组件
│   │   │   └── ui/          # 基础组件
│   │   ├── pages/           # 页面组件
│   │   ├── types/           # TypeScript 类型
│   │   ├── lib/             # 工具函数
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── main.tsx         # 应用入口
│   │   └── index.css        # 全局样式
│   ├── index.html           # HTML 模板
│   ├── package.json         # 依赖配置
│   ├── tailwind.config.js   # Tailwind 配置
│   ├── tsconfig.json        # TypeScript 配置
│   └── vite.config.ts       # Vite 配置
└── README.md                # 本文档
```

## 生产部署

### 构建前端

```bash
cd frontend
npm run build
```

构建输出在 `dist/` 目录。

### 部署方案

1. **独立部署**
   - 后端: `uvicorn main:app --host 0.0.0.0 --port 8000`
   - 前端: 使用 Nginx/Caddy 托管 `dist/` 目录

2. **Docker 部署** (TODO)
   ```bash
   docker build -t wechat-scraper-web .
   docker run -p 8000:8000 wechat-scraper-web
   ```

## 与竞品对比

| 功能 | wcplusPro | 本系统 |
|------|-----------|--------|
| Web GUI | ✅ Vue.js | ✅ **React + TS + Tailwind** |
| 实时进度 | ✅ | ✅ WebSocket |
| 仪表盘 | ✅ | ✅ 现代化图表 |
| 全文搜索 | ✅ | ✅ FTS5 |
| 队列管理 | ✅ | ✅ 完整 CRUD |

我们的优势:
- **TypeScript** 类型安全
- **Tailwind CSS** 现代化设计
- **Recharts** 交互式图表
- **TanStack Query** 高效数据管理

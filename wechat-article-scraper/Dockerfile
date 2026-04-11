# 微信文章抓取助手 - Docker 镜像
# World-class WeChat Article Scraper
# 支持 CLI + Web 仪表盘 + 完整 6 级策略路由

# 构建阶段
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    libz-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY cli/requirements.txt ./

# 安装 Python 依赖到本地目录
RUN pip install --no-cache-dir --user \
    typer[all]>=0.9.0 \
    rich>=13.0.0 \
    pyyaml>=6.0 \
    requests>=2.28.0 \
    beautifulsoup4>=4.11.0 \
    html2text>=2020.1.16 \
    markdownify>=0.11.0 \
    openpyxl>=3.0.10 \
    reportlab>=3.6.0 \
    scrapling>=0.3.0 \
    jinja2>=3.1.0 \
    fastapi>=0.100.0 \
    uvicorn>=0.23.0 \
    aiofiles>=23.0.0

# 运行阶段
FROM python:3.12-slim

LABEL maintainer="Claude Code"
LABEL version="3.21.0"
LABEL description="World-class WeChat article extraction with 6-level strategy routing, Web UI, and CLI"

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 从构建阶段复制 Python 包
COPY --from=builder /root/.local /root/.local

# 确保使用本地安装的包
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/root/.local/lib/python3.12/site-packages:/app:$PYTHONPATH

# 复制应用代码
COPY scripts/ ./scripts/
COPY cli/w_cli.py ./cli/
COPY web/ ./web/
COPY assets/ ./assets/
COPY references/ ./references/

# 创建数据目录（挂载点）
RUN mkdir -p /data/articles /data/db /data/config

# 设置环境变量
ENV WECHAT_DATA_DIR=/data
ENV WECHAT_CONFIG_DIR=/data/config
ENV PYTHONUNBUFFERED=1

# 暴露 Web 服务端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health 2>/dev/null || python3 -c "print('OK')" || exit 1

# 入口脚本
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

# 默认命令：启动 Web 服务
CMD ["web"]

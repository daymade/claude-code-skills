# WeChat Article Scraper - Docker Image
# 支持所有抓取策略的完整容器化方案

FROM python:3.11-slim

LABEL maintainer="Claude Code"
LABEL version="3.3.0"
LABEL description="World-class WeChat article extraction with 6-level strategy routing"

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libz-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件（如果有）
COPY requirements.txt* ./

# 安装Python依赖
RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    lxml \
    pillow \
    markdownify \
    html2text \
    && pip install --no-cache-dir scrapling || true

# 安装 Playwright（可选）
RUN pip install --no-cache-dir playwright && \
    playwright install chromium || true

# 复制应用程序
COPY scripts/ ./scripts/
COPY assets/ ./assets/ 2>/dev/null || true

# 设置可执行权限
RUN chmod +x scripts/*.py

# 创建缓存目录
RUN mkdir -p /app/cache /app/output

# 设置环境变量
ENV PYTHONPATH=/app
ENV WECHAT_CACHE_DIR=/app/cache
ENV WECHAT_OUTPUT_DIR=/app/output

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import sys; sys.path.insert(0, '/app'); from scripts.router import StrategyRouter; print('OK')" || exit 1

# 默认入口点
ENTRYPOINT ["python3", "scripts/scraper.py"]

# 默认命令（显示帮助）
CMD ["--help"]

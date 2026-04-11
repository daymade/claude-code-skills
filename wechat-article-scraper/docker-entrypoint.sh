#!/bin/bash
# Docker 入口脚本 - 支持多种运行模式

set -e

# 确保数据目录存在
mkdir -p /data/articles /data/db /data/config

# 根据命令选择运行模式
case "$1" in
    web|server|api)
        echo "启动 Web 服务..."
        shift
        exec python3 -m uvicorn web.backend.main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --reload \
            "$@"
        ;;
    
    cli|w)
        echo "运行 CLI..."
        shift
        exec python3 cli/w_cli.py "$@"
        ;;
    
    scrape)
        echo "抓取文章..."
        shift
        exec python3 cli/w_cli.py scrape "$@"
        ;;
    
    batch)
        echo "批量抓取..."
        shift
        exec python3 cli/w_cli.py batch "$@"
        ;;
    
    search)
        echo "搜索文章..."
        shift
        exec python3 cli/w_cli.py search "$@"
        ;;
    
    monitor)
        echo "监控模式..."
        shift
        exec python3 cli/w_cli.py monitor "$@"
        ;;
    
    shell|bash|sh)
        echo "进入 Shell..."
        exec /bin/bash
        ;;
    
    --help|-h|help)
        echo "微信文章抓取助手 - Docker 运行模式"
        echo ""
        echo "用法: docker run [镜像] [模式] [参数]"
        echo ""
        echo "模式:"
        echo "  web, server      启动 Web 仪表盘 (默认)"
        echo "  cli, w           运行 CLI 工具"
        echo "  scrape           抓取单篇文章"
        echo "  batch            批量抓取"
        echo "  search           搜狗搜索"
        echo "  monitor          监控管理"
        echo "  shell, bash      进入交互式 Shell"
        echo "  --help           显示此帮助"
        echo ""
        echo "示例:"
        echo "  docker run -p 8000:8000 wechat-scraper web"
        echo "  docker run wechat-scraper scrape 'https://mp.weixin.qq.com/s/xxx'"
        echo "  docker run -v ./data:/data wechat-scraper batch /data/urls.txt"
        echo ""
        echo "数据卷:"
        echo "  /data            数据持久化目录"
        echo "  /data/articles   文章存储"
        echo "  /data/db         SQLite 数据库"
        echo "  /data/config     配置文件"
        exit 0
        ;;
    
    *)
        # 默认启动 Web 服务
        echo "启动 Web 服务..."
        exec python3 -m uvicorn web.backend.main:app \
            --host 0.0.0.0 \
            --port 8000 \
            "$@"
        ;;
esac

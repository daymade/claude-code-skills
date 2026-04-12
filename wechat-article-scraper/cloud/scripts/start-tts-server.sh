#!/bin/bash
# Edge TTS Server 启动脚本
# 使用 Microsoft Edge 在线 TTS 服务（免费，无需 API Key）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PORT="${TTS_PORT:-8020}"
PID_FILE="/tmp/edge-tts-server.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 Python 是否安装
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    log_info "Python version: $(python3 --version)"
}

# 检查 edge-tts 是否安装
check_edge_tts() {
    if ! python3 -c "import edge_tts" 2>/dev/null; then
        log_warn "edge-tts not found, installing..."
        pip3 install edge-tts
    fi
    log_info "edge-tts is installed"
}

# 启动服务器
start_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_warn "TTS server is already running (PID: $PID)"
            log_info "Server URL: http://127.0.0.1:$SERVER_PORT"
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi

    log_info "Starting Edge TTS server on port $SERVER_PORT..."

    # 在后台启动服务器
    nohup python3 "$SCRIPT_DIR/edge-tts-server.py" "$SERVER_PORT" > /tmp/edge-tts.log 2>&1 &
    SERVER_PID=$!

    # 保存 PID
    echo $SERVER_PID > "$PID_FILE"

    # 等待服务器启动
    sleep 2

    # 检查是否成功启动
    if ps -p "$SERVER_PID" > /dev/null 2>&1; then
        log_info "TTS server started successfully (PID: $SERVER_PID)"
        log_info "Server URL: http://127.0.0.1:$SERVER_PORT"
        log_info "Log file: /tmp/edge-tts.log"

        # 测试健康检查
        if curl -s http://127.0.0.1:$SERVER_PORT/health > /dev/null; then
            log_info "Health check passed"
        else
            log_warn "Health check failed, server may still be starting..."
        fi
    else
        log_error "Failed to start TTS server"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# 停止服务器
stop_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_info "Stopping TTS server (PID: $PID)..."
            kill "$PID"
            rm -f "$PID_FILE"
            log_info "TTS server stopped"
        else
            log_warn "TTS server is not running"
            rm -f "$PID_FILE"
        fi
    else
        log_warn "PID file not found, TTS server may not be running"
    fi
}

# 检查服务器状态
check_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_info "TTS server is running (PID: $PID)"
            log_info "Server URL: http://127.0.0.1:$SERVER_PORT"

            # 健康检查
            HEALTH=$(curl -s http://127.0.0.1:$SERVER_PORT/health 2>/dev/null || echo '{"status":"unknown"}')
            log_info "Health: $HEALTH"
        else
            log_warn "TTS server is not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        log_warn "TTS server is not running"
    fi
}

# 重启服务器
restart_server() {
    stop_server
    sleep 1
    start_server
}

# 查看日志
show_logs() {
    if [ -f "/tmp/edge-tts.log" ]; then
        tail -f "/tmp/edge-tts.log"
    else
        log_warn "Log file not found"
    fi
}

# 主命令
case "${1:-start}" in
    start)
        check_python
        check_edge_tts
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        check_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac

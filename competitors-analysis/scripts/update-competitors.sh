#!/bin/bash
# 竞品仓库管理脚本模板
# 复制此文件到你的项目: scripts/update-competitors.sh
# 用法: ./scripts/update-competitors.sh [clone|pull|status]

set -e

# ============================================================
# 配置区域 - 根据你的产品修改
# ============================================================

# 竞品仓库基础目录（按产品区分）
COMPETITORS_BASE="${COMPETITORS_BASE:-$HOME/Workspace/competitors}"

# 你的产品名称（用于子目录）
PRODUCT_NAME="your-product-name"  # TODO: 修改为你的产品名

# 竞品目录
COMPETITORS_DIR="$COMPETITORS_BASE/$PRODUCT_NAME"

# 竞品仓库列表（SSH 方式，网络问题时会自动重试）
declare -A COMPETITORS=(
    # TODO: 添加你的竞品
    # ["competitor-name"]="git@github.com:org/repo.git"
    # 示例:
    # ["openwhispr"]="git@github.com:OpenWhispr/openwhispr.git"
)

# ============================================================
# 以下代码无需修改
# ============================================================

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 函数：克隆仓库
clone_repos() {
    echo -e "${GREEN}=== 克隆竞品仓库 ($PRODUCT_NAME) ===${NC}"
    mkdir -p "$COMPETITORS_DIR"

    for name in "${!COMPETITORS[@]}"; do
        repo="${COMPETITORS[$name]}"
        target="$COMPETITORS_DIR/$name"

        if [ -d "$target" ]; then
            echo -e "${YELLOW}[跳过] $name 已存在${NC}"
        else
            echo -e "${GREEN}[克隆] $name${NC}"
            # 网络问题自动重试
            for i in 1 2 3; do
                if git clone "$repo" "$target" 2>/dev/null; then
                    break
                fi
                echo "  重试 $i/3..."
                sleep 2
            done
        fi
    done

    echo ""
    echo -e "${GREEN}完成！竞品仓库位于: $COMPETITORS_DIR${NC}"
}

# 函数：更新仓库
pull_repos() {
    echo -e "${GREEN}=== 更新竞品仓库 ($PRODUCT_NAME) ===${NC}"

    for name in "${!COMPETITORS[@]}"; do
        target="$COMPETITORS_DIR/$name"

        if [ -d "$target" ]; then
            echo -e "${GREEN}[更新] $name${NC}"
            cd "$target"
            git fetch --all 2>/dev/null || echo -e "${RED}  fetch 失败${NC}"
            git pull --rebase 2>/dev/null || echo -e "${YELLOW}  可能有冲突${NC}"
            cd - > /dev/null
        else
            echo -e "${RED}[缺失] $name - 请先运行 clone${NC}"
        fi
    done
}

# 函数：检查状态
check_status() {
    echo -e "${GREEN}=== 竞品仓库状态 ($PRODUCT_NAME) ===${NC}"
    echo ""

    for name in "${!COMPETITORS[@]}"; do
        target="$COMPETITORS_DIR/$name"

        if [ -d "$target" ]; then
            cd "$target"
            branch=$(git branch --show-current 2>/dev/null || echo "unknown")
            commit=$(git log -1 --format="%h %s" 2>/dev/null | head -c 60)
            behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
            echo -e "${GREEN}$name${NC} ($branch)"
            echo "  最新: $commit"
            echo "  落后: $behind 个提交"
            cd - > /dev/null
        else
            echo -e "${RED}$name${NC}: 未克隆"
        fi
        echo ""
    done
}

# 函数：显示帮助
show_help() {
    echo "竞品仓库管理脚本 - $PRODUCT_NAME"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  clone    克隆所有竞品仓库到 $COMPETITORS_DIR"
    echo "  pull     更新所有竞品仓库"
    echo "  status   检查仓库状态（分支、最新提交、落后数）"
    echo "  help     显示此帮助"
    echo ""
    echo "环境变量:"
    echo "  COMPETITORS_BASE  竞品仓库基础目录 (默认: ~/Workspace/competitors)"
    echo ""
    echo "目录结构:"
    echo "  $COMPETITORS_BASE/"
    echo "  └── $PRODUCT_NAME/"
    echo "      ├── competitor1/"
    echo "      └── competitor2/"
}

# 主逻辑
case "${1:-help}" in
    clone)
        clone_repos
        ;;
    pull)
        pull_repos
        ;;
    status)
        check_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}未知命令: $1${NC}"
        show_help
        exit 1
        ;;
esac

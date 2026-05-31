#!/usr/bin/env bash
# sanitize_history.sh — 检查并清理 git 历史中的敏感信息
# 用法: ./sanitize_history.sh [--check-only] [--path <repo-root>]
#
# 注意：此脚本只辅助检查，最终修复（orphan branch / BFG）需要人工确认后执行。

set -euo pipefail

REPO_ROOT="$(pwd)"
CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=true; shift ;;
    --path) REPO_ROOT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

cd "$REPO_ROOT"

echo "========================================="
echo "Sanitization Check — $REPO_ROOT"
echo "========================================="

# 1. 检查常见敏感模式（全 git 历史）
echo ""
echo "[1/4] Scanning git history for common secrets..."

PATTERNS=(
  'sk-[a-zA-Z0-9_-]{20,}'           # API keys
  'sk-or-v1-[a-zA-Z0-9_-]+'         # OpenRouter
  'sk-ant-[a-zA-Z0-9_-]+'           # Anthropic
  'sk-proj-[a-zA-Z0-9_-]+'          # OpenAI project
  'AK[0-9A-Za-z]{16,}'              # Aliyun AK
  'ghp_[a-zA-Z0-9]{36}'             # GitHub PAT
  '[A-Za-z0-9/+=]{40}'              # Generic long base64
)

FOUND_ISSUES=0
for pat in "${PATTERNS[@]}"; do
  matches=$(git log --all -p -G "$pat" -- | head -20 || true)
  if [[ -n "$matches" ]]; then
    echo "  ⚠️  Pattern matched: $pat"
    echo "$matches" | head -5
    FOUND_ISSUES=$((FOUND_ISSUES + 1))
  fi
done

if [[ $FOUND_ISSUES -eq 0 ]]; then
  echo "  ✅ No common secret patterns found in history."
fi

# 2. 检查个人绝对路径
echo ""
echo "[2/4] Scanning for personal absolute paths..."

PATH_PATTERNS=(
  '/Users/[a-zA-Z0-9_-]+/'
  '/home/[a-zA-Z0-9_-]+/'
)

PATH_ISSUES=0
for pat in "${PATH_PATTERNS[@]}"; do
  matches=$(git log --all -p -G "$pat" -- | grep -oE "$pat" | sort -u | head -10 || true)
  if [[ -n "$matches" ]]; then
    echo "  ⚠️  Personal paths found:"
    echo "$matches"
    PATH_ISSUES=$((PATH_ISSUES + 1))
  fi
done

if [[ $PATH_ISSUES -eq 0 ]]; then
  echo "  ✅ No personal absolute paths found."
fi

# 3. 检查私有域名
echo ""
echo "[3/4] Scanning for private infrastructure domains..."

# 扩展此列表以匹配你的私有域名
PRIVATE_DOMAINS=(
  '<private-domain>\.dev'
  '<private-domain>\.pro'
  '<your-domain>\.ai'
)

DOMAIN_ISSUES=0
for dom in "${PRIVATE_DOMAINS[@]}"; do
  matches=$(git log --all -p -G "$dom" -- | head -10 || true)
  if [[ -n "$matches" ]]; then
    echo "  ⚠️  Private domain found: $dom"
    DOMAIN_ISSUES=$((DOMAIN_ISSUES + 1))
  fi
done

if [[ $DOMAIN_ISSUES -eq 0 ]]; then
  echo "  ✅ No private domains found."
fi

# 4. 当前工作区检查
echo ""
echo "[4/4] Checking current working tree..."

if git rev-parse --git-dir > /dev/null 2>&1; then
  # 检查未提交的文件中是否有敏感信息
  UNCOMMITTED=$(git diff --cached --name-only || true)
  if [[ -n "$UNCOMMITTED" ]]; then
    echo "  ℹ️  Staged files:"
    echo "$UNCOMMITTED" | sed 's/^/    /'
  fi
else
  echo "  ⚠️  Not a git repository."
fi

echo ""
echo "========================================="
echo "Summary: $((FOUND_ISSUES + PATH_ISSUES + DOMAIN_ISSUES)) potential issues found"
echo "========================================="

if [[ "$CHECK_ONLY" == true ]]; then
  echo "--check-only specified. No changes made."
  exit 0
fi

# 如果发现问题，提供修复建议
if [[ $((FOUND_ISSUES + PATH_ISSUES + DOMAIN_ISSUES)) -gt 0 ]]; then
  echo ""
  echo "建议修复流程："
  echo "1. 评估影响：哪些 commit 含敏感信息？是否已 push 到 remote？"
  echo "2. 在 provider 后台 revoke 已泄露的 key"
  echo "3. 生成新 key 替换 .env"
  echo "4. 清理历史（选一）："
  echo "   A) Orphan branch（历史可全丢）：git checkout --orphan new-history"
  echo "   B) BFG Repo-Cleaner（保留历史）：https://rtyley.github.io/bfg-repo-cleaner/"
  echo "5. 通知其他协作者重新 clone"
  exit 1
fi

echo "✅ History looks clean."
exit 0

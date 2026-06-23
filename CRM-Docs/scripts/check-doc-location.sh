#!/bin/bash
# scripts/check-doc-location.sh - 检测 CRM-Docs 根目录散落文档
#
# 用途：确保 CRM-Docs 根目录只有 README.md，其他文档必须在子目录
# 执行时机：pre-commit hook + CI Pipeline
#
# 违规示例：
#   ❌ CRM-Docs/PHASE-1-SUMMARY.md
#   ❌ CRM-Docs/FINAL-COMPLETION-REPORT.md
#   ❌ CRM-Docs/IMPLEMENTATION-PROGRESS.md
#
# 正确做法：
#   ✅ CRM-Docs/README.md（唯一允许）
#   ✅ CRM-Docs/changelog/technical/2026-06-12-lifecycle.md
#   ✅ CRM-Docs/plans/xxx-plan.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRM_DOCS_DIR="$(dirname "$SCRIPT_DIR")"

echo "检查 CRM-Docs 根目录散落文档..."

# CRM-Docs 根目录允许的 md 文件（白名单）
ALLOWED_ROOT_MD="README.md"

# 检查根目录是否有散落的 md 文件
STRAY_FILES=$(find "$CRM_DOCS_DIR" -maxdepth 1 -name "*.md" ! -name "$ALLOWED_ROOT_MD" -print)

if [ -n "$STRAY_FILES" ]; then
    echo ""
    echo "❌ 发现根目录散落文档："
    echo "$STRAY_FILES" | while read -r file; do
        echo "  - $file"
    done
    echo ""
    echo "📋 根目录唯一允许的 md 文件：README.md（导航入口）"
    echo ""
    echo "📂 请将文档移动到正确的子目录："
    echo "  - 实施进度/阶段总结 → changelog/technical/YYYY-MM-DD-xxx.md"
    echo "  - 实施计划 → plans/xxx-PLAN.md（完成后 archive/plans/）"
    echo "  - 需求文档 → requirements/xxx-REQUIREMENTS.md"
    echo "  - 技术总结 → changelog/technical/YYYY-MM-DD-xxx.md"
    echo ""
    echo "💡 进度跟踪替代方案："
    echo "  - 使用 TaskCreate/TaskUpdate 工具跟踪进度"
    echo "  - 使用 Claude Code 内存系统记录临时状态"
    echo "  - 不要创建 PHASE-X-SUMMARY 等临时文档"
    echo ""
    exit 1
fi

echo "✅ 根目录文档结构符合规范（只有 README.md）"
exit 0
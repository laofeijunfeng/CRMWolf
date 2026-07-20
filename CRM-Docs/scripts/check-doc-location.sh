#!/bin/bash
# CRM-Docs/scripts/check-doc-location.sh - 检测 CRM-Docs 根目录散落文档
#
# 用途：避免 CRM-Docs 根目录继续产生散落文档。
#
# 违规示例：
#   ❌ CRM-Docs/PHASE-1-SUMMARY.md
#   ❌ CRM-Docs/FINAL-COMPLETION-REPORT.md
#   ❌ CRM-Docs/IMPLEMENTATION-PROGRESS.md
#
# 正确做法：
#   - V2 设计规范：CRM-Docs/design-system/
#   - 服务器部署：CRM-Docs/deployment/
#   - 脚本说明：CRM-Docs/scripts/README.md

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
    echo "发现 CRM-Docs 根目录散落文档："
    echo "$STRAY_FILES" | while read -r file; do
        echo "  - $file"
    done
    echo ""
    echo "CRM-Docs 根目录只允许保留 README.md。"
    echo ""
    echo "当前保留的文档入口："
    echo "  - V2 设计规范：CRM-Docs/design-system/"
    echo "  - 服务器部署：CRM-Docs/deployment/"
    echo "  - 脚本说明：CRM-Docs/scripts/README.md"
    echo ""
    echo "临时实施记录、阶段总结、需求草稿不要落到仓库文档目录。"
    echo ""
    exit 1
fi

echo "CRM-Docs 根目录文档结构符合规范。"
exit 0

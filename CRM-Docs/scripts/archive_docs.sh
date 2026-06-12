#!/bin/bash

# 文档自动归档脚本
# 用途：自动归档 status: completed 的文档
# 执行时机：每次 CI 运行（或定时运行）
# 前置检查：changelog 存在性验证

set -e

echo "📦 开始自动归档文档..."

# 前置检查：changelog 目录是否有文档
check_changelog_exists() {
  changelog_count=$(find CRM-Docs/changelog -name "*.md" -type f ! -name "README.md" | wc -l | tr -d ' ')

  if [ "$changelog_count" -eq 0 ]; then
    echo "⚠️  警告: changelog 目录无文档，建议先创建 changelog"
    echo "   提示: 参阅 CRM-Docs/standards/DOC-LIFECYCLE.md#五、结果沉淀机制"
    echo ""
    read -p "是否继续归档（不创建 changelog）？[y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "❌ 归档已取消"
      exit 1
    fi
  else
    echo "✅ changelog 检查通过: 发现 $changelog_count 个文档"
  fi
}

# 检查单个文档是否有对应的 changelog（可选检查）
check_doc_changelog() {
  doc_name=$1
  doc_type=$2  # requirements 或 plans

  # 提取文档名（不含扩展名）
  base_name=$(echo "$doc_name" | sed 's/.md$//')

  # 查找对应的 changelog（简单匹配）
  changelog_pattern="CRM-Docs/changelog/enhancements/*${base_name}*.md"
  matching_changelog=$(find CRM-Docs/changelog/enhancements -name "*${base_name}*.md" -type f 2>/dev/null | head -1)

  if [ -z "$matching_changelog" ]; then
    echo "⚠️  警告: $doc_name 未发现对应 changelog"
    return 1
  else
    echo "✅ 发现 changelog: $matching_changelog"
    return 0
  fi
}

# 执行 changelog 前置检查
echo ""
echo "🔍 前置检查: changelog 存在性"
check_changelog_exists

echo ""
echo "📦 开始归档流程..."

# 归档 requirements/ 中 status: completed 的文档
archived_count=0

for doc in CRM-Docs/requirements/*.md; do
  if [ "$doc" == "CRM-Docs/requirements/README.md" ]; then
    continue
  fi

  if [ ! -f "$doc" ]; then
    continue
  fi

  status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')

  if [ "$status" == "completed" ]; then
    echo "  📦 归档: $doc"

    # 获取文档信息
    doc_name=$(basename "$doc")
    created=$(grep -E "^created:" "$doc" | head -1 | sed 's/created: //' | tr -d ' ')
    updated=$(grep -E "^updated:" "$doc" | head -1 | sed 's/updated: //' | tr -d ' ')

    # 迁移文件
    mv "$doc" "CRM-Docs/archive/requirements/$doc_name"

    # 记录归档信息（用于更新 README）
    echo "$doc_name|$created|$updated" >> /tmp/archived_requirements.log

    archived_count=$((archived_count + 1))
  fi
done

# 归档 plans/ 中 status: completed 的文档
for doc in CRM-Docs/plans/*.md; do
  if [ "$doc" == "CRM-Docs/plans/README.md" ]; then
    continue
  fi

  if [ ! -f "$doc" ]; then
    continue
  fi

  status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')

  if [ "$status" == "completed" ]; then
    echo "  📦 归档: $doc"

    doc_name=$(basename "$doc")
    created=$(grep -E "^created:" "$doc" | head -1 | sed 's/created: //' | tr -d ' ')
    updated=$(grep -E "^updated:" "$doc" | head -1 | sed 's/updated: //' | tr -d ' ')

    mv "$doc" "CRM-Docs/archive/plans/$doc_name"

    echo "$doc_name|$created|$updated" >> /tmp/archived_plans.log

    archived_count=$((archived_count + 1))
  fi
done

echo ""
echo "✅ 归档完成: $archived_count 个文档"

if [ $archived_count -gt 0 ]; then
  echo ""
  echo "🔄 更新导航 README..."

  # 调用 Python 导航更新脚本
  if [ -f "CRM-Docs/scripts/update_doc_nav.py" ]; then
    python3 CRM-Docs/scripts/update_doc_nav.py
    echo "✅ 导航更新完成（Python 版本）"
  else
    # 回退到 shell 脚本（简化版）
    bash CRM-Docs/scripts/update-doc-nav.sh
    echo "✅ 导航更新完成（Shell 版本 - 简化）"
  fi
fi

echo ""
echo "✅ 自动归档流程完成"
echo ""
echo "📋 归档统计:"
echo "  - 归档文档数: $archived_count"
echo "  - 归档需求数: $(ls -1 CRM-Docs/archive/requirements/*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "  - 归档计划数: $(ls -1 CRM-Docs/archive/plans/*.md 2>/dev/null | wc -l | tr -d ' ')"
echo ""
echo "💡 提示:"
echo "  - 如需创建 changelog，参阅 CRM-Docs/standards/DOC-LIFECYCLE.md#五、结果沉淀机制"
echo "  - 归档后文档只读，请勿修改内容"
echo "  - Git 提交示例: git commit -m 'docs(archive): 归档已完成文档'"
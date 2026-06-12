#!/bin/bash

# 导航文档更新脚本
# 用途：更新 requirements/README.md, plans/README.md, archive/README.md
# 执行时机：归档后自动执行

set -e

echo "🔄 开始更新导航文档..."

# 更新时间戳
current_date=$(date +%Y-%m-%d)

# 函数：更新 requirements/README.md
update_requirements_readme() {
  echo "  📝 更新 requirements/README.md..."

  # 扫描活跃需求文档
  active_docs=""
  completed_docs=""

  for doc in CRM-Docs/requirements/*.md; do
    if [ "$doc" == "CRM-Docs/requirements/README.md" ]; then
      continue
    fi

    if [ ! -f "$doc" ]; then
      continue
    fi

    doc_name=$(basename "$doc")
    status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')
    created=$(grep -E "^created:" "$doc" | head -1 | sed 's/created: //' | tr -d ' ')
    updated=$(grep -E "^updated:" "$doc" | head -1 | sed 's/updated: //' | tr -d ' ')

    if [ "$status" == "completed" ]; then
      completed_docs="$completed_docs| [$doc_name]($doc_name) | completed | $created | $updated | - |\n"
    else
      active_docs="$active_docs| [$doc_name]($doc_name) | $status | $created | $updated | - |\n"
    fi
  done

  # 生成新的 README 内容（简化版，实际需完整模板）
  # 这里仅更新状态汇总表部分

  echo "    ✅ 活跃需求: $(echo "$active_docs" | wc -l | tr -d ' ') 个"
  echo "    ✅ 待归档需求: $(echo "$completed_docs" | wc -l | tr -d ' ') 个"
}

# 函数：更新 plans/README.md
update_plans_readme() {
  echo "  📝 更新 plans/README.md..."

  active_docs=""
  completed_docs=""

  for doc in CRM-Docs/plans/*.md; do
    if [ "$doc" == "CRM-Docs/plans/README.md" ]; then
      continue
    fi

    if [ ! -f "$doc" ]; then
      continue
    fi

    doc_name=$(basename "$doc")
    status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')
    created=$(grep -E "^created:" "$doc" | head -1 | sed 's/created: //' | tr -d ' ')
    updated=$(grep -E "^updated:" "$doc" | head -1 | sed 's/updated: //' | tr -d ' ')

    if [ "$status" == "completed" ]; then
      completed_docs="$completed_docs| [$doc_name]($doc_name) | completed | $created | $updated | - |\n"
    else
      active_docs="$active_docs| [$doc_name]($doc_name) | $status | $created | $updated | - |\n"
    fi
  done

  echo "    ✅ 活跃计划: $(echo "$active_docs" | wc -l | tr -d ' ') 个"
  echo "    ✅ 待归档计划: $(echo "$completed_docs" | wc -l | tr -d ' ') 个"
}

# 函数：更新 archive/README.md
update_archive_readme() {
  echo "  📝 更新 archive/README.md..."

  archived_requirements=""
  archived_plans=""

  # 扫描归档的需求文档
  for doc in CRM-Docs/archive/requirements/*.md; do
    if [ ! -f "$doc" ]; then
      continue
    fi

    doc_name=$(basename "$doc")
    archived_requirements="$archived_requirements| [$doc_name](requirements/$doc_name) | requirements/ | $current_date | - | - |\n"
  done

  # 扫描归档的计划文档
  for doc in CRM-Docs/archive/plans/*.md; do
    if [ ! -f "$doc" ]; then
      continue
    fi

    doc_name=$(basename "$doc")
    archived_plans="$archived_plans| [$doc_name](plans/$doc_name) | plans/ | $current_date | - | - |\n"
  done

  echo "    ✅ 已归档需求: $(echo "$archived_requirements" | wc -l | tr -d ' ') 个"
  echo "    ✅ 已归档计划: $(echo "$archived_plans" | wc -l | tr -d ' ') 个"
}

# 执行更新
update_requirements_readme
update_plans_readme
update_archive_readme

echo ""
echo "✅ 导航文档更新完成"

# 实际实现中，应该使用更完整的模板生成逻辑
# 可以使用 Python 或 Node.js 处理更复杂的文本替换

echo ""
echo "💡 提示: 实际部署时需完善模板生成逻辑（完整 README 内容替换）"
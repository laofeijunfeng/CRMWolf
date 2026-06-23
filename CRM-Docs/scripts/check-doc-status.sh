#!/bin/bash

# 文档状态检查脚本
# 用途：检查 requirements/ 和 plans/ 文档的状态标签完整性
# 执行时机：每次 PR 提交

set -e

echo "🔍 检查文档状态标签..."

# 检查 requirements/ 目录
echo ""
echo "📋 requirements/ 目录检查:"
for doc in CRM-Docs/requirements/*.md; do
  if [ "$doc" == "CRM-Docs/requirements/README.md" ]; then
    continue
  fi

  if [ ! -f "$doc" ]; then
    continue
  fi

  # 检查是否有 status 标签
  status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')

  if [ -z "$status" ]; then
    echo "❌ 缺少状态标签: $doc"
    exit 1
  fi

  # 检查状态是否合法
  valid_statuses="draft review active completed archived"
  if ! echo "$valid_statuses" | grep -w "$status" > /dev/null; then
    echo "❌ 无效状态标签 ($status): $doc"
    exit 1
  fi

  # 检查是否有 created 标签
  created=$(grep -E "^created:" "$doc" | head -1)
  if [ -z "$created" ]; then
    echo "❌ 缺少创建日期标签: $doc"
    exit 1
  fi

  # 检查是否有 updated 标签
  updated=$(grep -E "^updated:" "$doc" | head -1)
  if [ -z "$updated" ]; then
    echo "❌ 缺少更新日期标签: $doc"
    exit 1
  fi

  echo "✅ $doc: status=$status"
done

# 检查 system/design/ 目录
echo ""
echo "📋 system/design/ 目录检查:"
for doc in CRM-Docs/system/design/*.md; do
  if [ "$doc" == "CRM-Docs/system/design/README.md" ]; then
    continue
  fi

  if [ ! -f "$doc" ]; then
    continue
  fi

  status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')

  if [ -z "$status" ]; then
    echo "❌ 缺少状态标签: $doc"
    exit 1
  fi

  valid_statuses="active deprecated"
  if ! echo "$valid_statuses" | grep -w "$status" > /dev/null; then
    echo "❌ 无效状态标签 ($status): $doc"
    exit 1
  fi

  created=$(grep -E "^created:" "$doc" | head -1)
  if [ -z "$created" ]; then
    echo "❌ 缺少创建日期标签: $doc"
    exit 1
  fi

  updated=$(grep -E "^updated:" "$doc" | head -1)
  if [ -z "$updated" ]; then
    echo "❌ 缺少更新日期标签: $doc"
    exit 1
  fi

  echo "✅ $doc: status=$status"
done

# 检查 plans/ 目录
echo ""
echo "📋 plans/ 目录检查:"
for doc in CRM-Docs/plans/*.md; do
  if [ "$doc" == "CRM-Docs/plans/README.md" ]; then
    continue
  fi

  if [ ! -f "$doc" ]; then
    continue
  fi

  status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')

  if [ -z "$status" ]; then
    echo "❌ 缺少状态标签: $doc"
    exit 1
  fi

  valid_statuses="draft review active completed archived"
  if ! echo "$valid_statuses" | grep -w "$status" > /dev/null; then
    echo "❌ 无效状态标签 ($status): $doc"
    exit 1
  fi

  created=$(grep -E "^created:" "$doc" | head -1)
  if [ -z "$created" ]; then
    echo "❌ 缺少创建日期标签: $doc"
    exit 1
  fi

  updated=$(grep -E "^updated:" "$doc" | head -1)
  if [ -z "$updated" ]; then
    echo "❌ 缺少更新日期标签: $doc"
    exit 1
  fi

  # 计划文档必须关联需求文档（非 completed 状态）
  if [ "$status" != "completed" ] && [ "$status" != "archived" ]; then
    related_req=$(grep -E "^related_requirements:" "$doc" | head -1)
    if [ -z "$related_req" ]; then
      echo "⚠️  计划文档未关联需求文档: $doc"
      # 不强制退出，仅警告
    fi
  fi

  echo "✅ $doc: status=$status"
done

echo ""
echo "✅ 所有文档状态标签检查通过"

# 检查 completed 状态文档是否有对应的 changelog
echo ""
echo "🔍 检查 completed 文档的 changelog..."

completed_docs=()
for doc in CRM-Docs/requirements/*.md CRM-Docs/plans/*.md; do
  if [ "$doc" == "CRM-Docs/requirements/README.md" ] || [ "$doc" == "CRM-Docs/plans/README.md" ]; then
    continue
  fi

  if [ ! -f "$doc" ]; then
    continue
  fi

  status=$(grep -E "^status:" "$doc" | head -1 | sed 's/status: //' | tr -d ' ')
  if [ "$status" == "completed" ]; then
    completed_docs+=("$doc")
  fi
done

if [ ${#completed_docs[@]} -gt 0 ]; then
  echo "📋 发现 ${#completed_docs[@]} 个 completed 文档:"
  for doc in "${completed_docs[@]}"; do
    doc_name=$(basename "$doc" .md)
    echo "  - $doc_name"

    # 检查是否有对应的 changelog（简单匹配）
    # 实际实现中可以根据文档名称精确匹配
    changelog_count=$(find CRM-Docs/changelog -name "*.md" -type f ! -name "README.md" | wc -l)
    if [ "$changelog_count" -eq 0 ]; then
      echo "⚠️  警告: completed 文档但未发现 changelog（归档前需创建）"
    fi
  done
fi

echo ""
echo "✅ 文档状态检查完成"
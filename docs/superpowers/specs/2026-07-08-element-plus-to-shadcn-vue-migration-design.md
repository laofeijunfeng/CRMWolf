# CRMWolf Element Plus → shadcn-vue 迁移设计规范

**版本**: V2
**日期**: 2026-07-08
**状态**: 设计阶段

---

## 一、目标与范围

### 1.1 迁移目标

**核心目标**：彻底替换 Element Plus 为 shadcn-vue，确保不漏迁移。

| 目标 | 说明 |
|------|------|
| **100% 替换** | 所有 Element Plus 组件替换为 shadcn-vue |
| **不漏迁移** | 自动检测 + CI 检查 + ESLint 强制规则 |
| **渐进迁移** | 分阶段迁移（基础组件 → 页面迁移 → 清理） |
| **设计系统统一** | 所有组件使用 V2 Design Tokens |

### 1.2 迁移范围

**当前 Element Plus 使用统计**（Agent 扫描结果）：

| 类别 | 数量 | 说明 |
|------|------|------|
| **组件使用** | 426+ | `el-*` 组件在 Vue 文件中 |
| **Import 语句** | 多处 | `from 'element-plus'` |
| **CSS 类** | 多处 | `.el-*` 类名 |
| **全局注册** | 1 | `app.use(ElementPlus)` |

**高频组件清单**：

| Element Plus 组件 | 使用次数 | 优先级 | shadcn-vue 对应 |
|-----------------|---------|-------|----------------|
| `el-button` | 46+ | P0 | `ButtonV2` |
| `el-table` | 16+ | P0 | `TableV2` |
| `el-form` | 38+ | P0 | `FormV2` (VeeValidate) |
| `el-dialog` | 44+ | P0 | `DialogV2` |
| `el-input` | 40+ | P0 | `InputV2` |
| `el-select` | 25+ | P0 | `SelectV2` |
| `ElMessage` | 26 | P1 | `toast()` |
| `ElMessageBox` | 38 | P1 | `AlertDialog` |
| `el-tooltip` | 14 | P2 | `Tooltip` |
| `el-pagination` | 13 | P2 | `Pagination` |
| `el-descriptions` | 33 | P2 | `Descriptions` |

**Element Plus Icons → Lucide Icons 映射表**（UI/UX Pro Max 规则：禁止 Emoji，必须使用 SVG 图标）：

| Element Plus Icon | Lucide Icon | 使用场景 |
|------------------|-------------|---------|
| `el-icon-edit` | `Pencil` | 编辑按钮 |
| `el-icon-delete` | `Trash2` | 删除按钮 |
| `el-icon-plus` | `Plus` | 新增按钮 |
| `el-icon-search` | `Search` | 搜索框 |
| `el-icon-close` | `X` | 关闭按钮/清除 |
| `el-icon-check` | `Check` | 确认/选择 |
| `el-icon-loading` | `Loader2` (animate-spin) | 加载状态 |
| `el-icon-arrow-left` | `ArrowLeft` | 返回/上一页 |
| `el-icon-arrow-right` | `ArrowRight` | 下一步/下一页 |
| `el-icon-download` | `Download` | 导出/下载 |
| `el-icon-upload` | `Upload` | 上传文件 |
| `el-icon-setting` | `Settings` | 设置/配置 |
| `el-icon-user` | `User` | 用户/个人中心 |
| `el-icon-calendar` | `Calendar` | 日期选择 |
| `el-icon-document` | `FileText` | 文档/合同 |
| `el-icon-refresh` | `RefreshCw` | 刷新/同步 |
| `el-icon-warning` | `AlertTriangle` | 警告提示 |
| `el-icon-success` | `CheckCircle` | 成功提示 |
| `el-icon-error` | `XCircle` | 错误提示 |
| `el-icon-info` | `Info` | 信息提示 |
| `el-icon-view` | `Eye` | 查看/预览 |
| `el-icon-hide` | `EyeOff` | 隐藏/密码隐藏 |
| `el-icon-copy` | `Copy` | 复制 |
| `el-icon-printer` | `Printer` | 打印 |

**迁移规则**：
- ✅ 所有图标必须使用 `lucide-vue-next`
- ❌ 禁止使用 Element Plus Icons (`@element-plus/icons-vue`)
- ❌ 禁止使用 Emoji 作为图标（UI/UX Pro Max §4 CRITICAL）
- ❌ 禁止使用 PNG/JPG 图标（必须使用 SVG）

---

## 二、架构设计

### 2.1 整体架构

```
CRMWolf V2 架构
├── Design Tokens（唯一来源）
│   ├── variables-v2.scss（已完成）
│   └── tailwind.config.js（映射 SCSS 变量）
│
├── shadcn-vue 组件库
│   ├── src/components/ui/（shadcn-vue 基础组件）
│   │   ├── button/
│   │   ├── input/
│   │   ├── table/
│   │   ├── dialog/
│   │   ├── select/
│   │   ├── toast/
│   │   ├── tooltip/
│   │   └── pagination/
│   │
│   └── src/components/common/（业务组件封装）
│       ├── ButtonV2.vue
│       ├── InputV2.vue
│       ├── TableV2.vue
│       └── ...
│
├── 迁移追踪系统
│   ├── docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md（完整清单）
│   ├── eslint.config.js（Element Plus 禁止规则）
│   ├── scripts/scan-element-plus.sh（扫描脚本）
│   └── .github/workflows/element-plus-migration.yml（CI 检查）
│
└── 测试层
    ├── Vitest 单元测试（每个 shadcn-vue 组件）
    └── 功能验证测试（每个迁移页面）
```

### 2.2 组件库结构

**shadcn-vue 组件库**：

```
src/components/ui/
├── button/
│   ├── Button.vue          # shadcn-vue 基础组件
│   ├── Button.test.ts      # 单元测试
│   └── index.ts
│
├── input/
│   ├── Input.vue
│   ├── Input.test.ts
│   └── index.ts
│
├── table/
│   ├── Table.vue
│   ├── Table.test.ts
│   └── index.ts
│
├── dialog/
│   ├── Dialog.vue
│   ├── Dialog.test.ts
│   └and index.ts
│
├── toast/
│   ├── Toast.vue
│   ├── toast.ts            # toast() 函数
│   └── index.ts
│
└── index.ts                 # 组件库统一导出
```

**业务组件封装**：

```
src/components/common/
├── ButtonV2.vue             # 基于 shadcn-vue Button 封装
│   # Props: variant, size, loading, disabled, icon, ariaLabel
│   # 特性: Touch target 44px, Focus ring 2px, Reduced motion
│
├── InputV2.vue              # 基于 shadcn-vue Input 封装
│   # 使用 VeeValidate + Zod
│   # Props: name, label, type, rules, helperText
│
├── TableV2.vue              # 基于 shadcn-vue Table 封装
│   # 使用 TanStack Table
│   # Props: columns, data, pagination, sorting, filtering
│
├── DialogV2.vue             # 基于 shadcn-vue Dialog 封装
│   # Props: title, description, open, onClose
│
├── ToastV2.vue              # 基于 shadcn-vue Toast 封装
│   # 使用 toast.success(), toast.error()
│
└── index.ts                 # 业务组件统一导出
```

### 2.3 Toast/AlertDialog 使用规范

**ElMessage → toast() 映射**（UI/UX Pro Max §8 规则）：

| Element Plus API | shadcn-vue API | 示例代码 |
|-----------------|---------------|---------|
| `ElMessage.success(msg)` | `toast.success(msg)` | `toast.success("保存成功")` |
| `ElMessage.error(msg)` | `toast.error(msg)` | `toast.error("保存失败")` |
| `ElMessage.warning(msg)` | `toast.warning(msg)` | `toast.warning("请先填写必填项")` |
| `ElMessage.info(msg)` | `toast.info(msg)` | `toast.info("加载中...")` |

**ElMessageBox → AlertDialog 映射**：

| Element Plus API | shadcn-vue API | 使用场景 |
|-----------------|---------------|---------|
| `ElMessageBox.confirm(msg, title, options)` | `AlertDialog.confirm()` | 删除确认、提交确认 |
| `ElMessageBox.alert(msg, title)` | `AlertDialog.alert()` | 错误提示、重要通知 |
| `ElMessageBox.prompt(msg, title)` | `AlertDialog.prompt()` | 输入确认（如审批意见） |

**Toast 最佳实践**（UI/UX Pro Max §8 Forms & Feedback）：

| 规则 | 说明 | 代码示例 |
|------|------|---------|
| **语义化方法** | 使用 toast.success/error/warning | ✅ `toast.success("Saved!")` ❌ `toast("Saved!")` |
| **自动消失** | 3-5 秒后自动消失 | `toast.success("Saved!", { duration: 3000 })` |
| **不抢焦点** | aria-live="polite" | Screen reader 兼容 |
| **位置固定** | 右上角或底部 | `toast.position = "top-right"` |
| **可关闭** | 提供关闭按钮 | `toast.closeButton = true` |
| **错误恢复路径** | 包含 retry/action | `toast.error("Failed", { action: { label: "Retry", onClick: retry } })` |

**Toast 组件实现**：

```vue
<!-- src/components/ui/toast/ToastProvider.vue -->
<template>
  <Toaster 
    position="top-right" 
    :toastOptions="{
      duration: 3000,
      closeButton: true,
      richColors: true,
      ariaLive: 'polite'
    }" 
  />
</template>

<script setup lang="ts">
import { Toaster, toast } from 'vue-sonner'

// 导出 toast 函数供全局使用
export { toast }
</script>
```

**全局注册**：

```typescript
// main.ts
import { toast } from '@/components/ui/toast'

// 全局可用
app.provide('toast', toast)

// 使用方式
import { inject } from 'vue'
const toast = inject('toast')
toast.success("保存成功")
```

---

## 三、迁移追踪系统

### 3.1 ESLint 规则（阻止 Element Plus）

```javascript
// eslint.config.js
export default [
  {
    rules: {
      // ===== Element Plus 迁移强制规则 =====
      
      // 1. 禁止 import 'element-plus'
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'element-plus',
              message: '❌ 请使用 shadcn-vue 组件替代 Element Plus。参考：docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md',
            },
          ],
          patterns: [
            {
              group: ['element-plus/*'],
              message: '❌ 请使用 shadcn-vue 组件替代 Element Plus。参考：docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md',
            },
          ],
        },
      ],
      
      // 2. 禁止在模板中使用 el-* 组件
      'no-restricted-syntax': [
        'error',
        {
          // 检测 <el-xxx 组件
          selector: 'Element[name=/^el-.+$/]',
          message: '❌ 请使用 shadcn-vue 组件替代 Element Plus 组件。参考：docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md',
        },
      ],
      
      // 3. 禁止使用 Element Plus CSS 类
      'no-restricted-syntax': [
        'error',
        {
          // 检测字符串中的 .el-xxx 或 el-xxx
          selector: 'Literal[value=/\\.el-|el-/]',
          message: '❌ 请使用 Tailwind 类替代 Element Plus CSS 类。参考：docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md',
        },
      ],
      
      // 4. 禁止 ElMessage, ElMessageBox 等全局 API
      'no-restricted-globals': [
        'error',
        {
          name: 'ElMessage',
          message: '❌ 请使用 toast() 替代 ElMessage',
        },
        {
          name: 'ElMessageBox',
          message: '❌ 请使用 AlertDialog 替代 ElMessageBox',
        },
      ],
    },
  },
]
```

### 3.2 扫描脚本（统计迁移进度）

```bash
#!/bin/bash
# scripts/scan-element-plus.sh
# 扫描项目中所有 Element Plus 使用，生成迁移进度报告

set -e

echo "================================================"
echo "  Element Plus → shadcn-vue 迁移进度报告"
echo "================================================"
echo ""

cd CRM-Client

# ===== 1. 组件使用统计 =====
echo "📊 Vue 文件中的 Element Plus 组件使用统计："
echo ""

el_components=$(grep -roh '<el-[a-z-]*' src --include="*.vue" 2>/dev/null | sort | uniq -c | sort -rn)

if [ -z "$el_components" ]; then
  echo "✅ 没有发现 Element Plus 组件使用！"
  component_count=0
else
  echo "$el_components"
  component_count=$(grep -roh '<el-[a-z-]*' src --include="*.vue" 2>/dev/null | wc -l | tr -d ' ')
  echo ""
  echo "📈 总计: $component_count 处使用 Element Plus 组件"
fi

echo ""

# ===== 2. Import 语句统计 =====
echo "📊 TypeScript/Vue 文件中的 Element Plus import："
echo ""

el_imports=$(grep -r "from 'element-plus'" src --include="*.ts" --include="*.tsx" --include="*.vue" 2>/dev/null)

if [ -z "$el_imports" ]; then
  echo "✅ 没有发现 Element Plus import！"
  import_count=0
else
  echo "$el_imports"
  import_count=$(grep -r "from 'element-plus'" src --include="*.ts" --include="*.tsx" --include="*.vue" 2>/dev/null | wc -l | tr -d ' ')
  echo ""
  echo "📈 总计: $import_count 处 import Element Plus"
fi

echo ""

# ===== 3. 全局 API 使用统计 =====
echo "📊 Element Plus 全局 API 使用（ElMessage, ElMessageBox）："
echo ""

el_message=$(grep -r "ElMessage\|ElMessageBox" src --include="*.ts" --include="*.vue" 2>/dev/null | wc -l | tr -d ' ')
if [ "$el_message" -gt 0 ]; then
  echo "ElMessage: $(grep -r "ElMessage" src --include="*.ts" --include="*.vue" 2>/dev/null | wc -l | tr -d ' ') 处"
  echo "ElMessageBox: $(grep -r "ElMessageBox" src --include="*.ts" --include="*.vue" 2>/dev/null | wc -l | tr -d ' ') 处"
  echo "📈 总计: $el_message 处使用全局 API"
else
  echo "✅ 没有发现 Element Plus 全局 API 使用！"
fi

echo ""

# ===== 4. CSS 类使用统计 =====
echo "📊 CSS/SCSS 文件中的 Element Plus 类："
echo ""

el_css=$(grep -roh 'el-[a-z-]*' src --include="*.scss" --include="*.css" 2>/dev/null | sort | uniq -c | sort -rn)

if [ -z "$el_css" ]; then
  echo "✅ 没有发现 Element Plus CSS 类！"
  css_count=0
else
  echo "$el_css"
  css_count=$(grep -roh 'el-[a-z-]*' src --include="*.scss" --include="*.css" 2>/dev/null | wc -l | tr -d ' ')
  echo ""
  echo "📈 总计: $css_count 处使用 Element Plus CSS 类"
fi

echo ""

# ===== 5. shadcn-vue 组件统计 =====
echo "📊 shadcn-vue 组件创建统计："
echo ""

shadcn_components=$(ls src/components/ui 2>/dev/null | wc -l | tr -d ' ')
if [ "$shadcn_components" -gt 0 ]; then
  echo "✅ 已创建 $shadcn_components 个 shadcn-vue 组件目录"
  ls src/components/ui 2>/dev/null
else
  echo "⚠️ 尚未创建 shadcn-vue 组件"
fi

echo ""

# ===== 6. 迁移进度计算 =====
echo "================================================"
echo "  迁移进度"
echo "================================================"
echo ""

total_element_plus=$((component_count + import_count + el_message + css_count))

if [ "$total_element_plus" -eq 0 ]; then
  echo "🎉 100% 完成！所有 Element Plus 已迁移！"
  echo ""
  echo "下一步："
  echo "  1. 删除 main.ts 中的 app.use(ElementPlus)"
  echo "  2. 删除 package.json 中的 element-plus 依赖"
  echo "  3. 清理 Element Plus CSS import"
else
  progress_percent=$(echo "scale=2; (1 - $total_element_plus / 500) * 100" | bc)
  echo "⏳ 剩余 Element Plus 使用: $total_element_plus 处"
  echo "📈 迁移进度: ${progress_percent}%"
  echo ""
  echo "建议优先迁移高频组件："
  echo "  - el-button (46+ 处)"
  echo "  - el-dialog (44+ 处)"
  echo "  - el-form (38+ 处)"
fi

echo ""
echo "================================================"
echo "  报告结束"
echo "================================================"
```

### 3.3 CI 检查（阻止新增 Element Plus）

```yaml
# .github/workflows/element-plus-migration.yml
name: Element Plus Migration Check

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  migration-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      
      - name: Check new Element Plus usage in PR
        run: |
          cd CRM-Client
          
          # 获取新增文件
          new_files=$(git diff HEAD~1 --name-only --diff-filter=A | grep -E "\.vue$|\.ts$|\.tsx$" || true)
          
          if [ -n "$new_files" ]; then
            echo "检查新增文件中的 Element Plus 使用..."
            
            # 检查新增文件
            el_in_new=$(grep -l "el-\|element-plus\|ElMessage" $new_files 2>/dev/null || true)
            
            if [ -n "$el_in_new" ]; then
              echo "::error::❌ 新增文件使用了 Element Plus！"
              echo "违规文件："
              echo "$el_in_new"
              echo ""
              echo "请使用 shadcn-vue 组件替代 Element Plus。"
              echo "参考：docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md"
              exit 1
            else
              echo "✅ 新增文件未使用 Element Plus"
            fi
          fi
          
          # 检查修改文件是否新增 Element Plus 使用
          modified_files=$(git diff HEAD~1 --name-only --diff-filter=M | grep -E "\.vue$|\.ts$|\.tsx$" || true)
          
          if [ -n "$modified_files" ]; then
            echo "检查修改文件是否新增 Element Plus 使用..."
            
            for file in $modified_files; do
              # 检查 diff 中是否新增 Element Plus
              new_el=$(git diff HEAD~1 "$file" | grep "^+" | grep -E "el-\|element-plus\|ElMessage" || true)
              
              if [ -n "$new_el" ]; then
                echo "::warning::⚠️ 文件 $file 新增了 Element Plus 使用"
                echo "$new_el"
              fi
            done
          fi
      
      - name: Run Element Plus scan
        run: |
          cd CRM-Client
          chmod +x scripts/scan-element-plus.sh
          bash scripts/scan-element-plus.sh > migration-report.txt
          
          # 输出报告
          cat migration-report.txt
          
          # 检查是否还有 Element Plus
          remaining=$(grep "剩余 Element Plus 使用" migration-report.txt | grep -oE '[0-9]+' || true)
          
          if [ -n "$remaining" ] && [ "$remaining" -gt 0 ]; then
            echo "::warning::⚠️ 还有 $remaining 处 Element Plus 使用待迁移"
          fi
      
      - name: Upload migration report
        uses: actions/upload-artifact@v4
        with:
          name: migration-report
          path: CRM-Client/migration-report.txt
```

### 3.4 完整迁移清单

```markdown
# docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md

# Element Plus → shadcn-vue 迁移清单

> **更新时间**: 2026-07-08
> **迁移目标**: 100% 替换 Element Plus，确保不漏迁移

---

## 一、组件迁移进度

### 1.1 高频组件（P0 - Week 1-2）

| Element Plus 组件 | 使用次数 | shadcn-vue 对应 | 迁移状态 | 完成日期 | 负责人 |
|-----------------|---------|----------------|---------|---------|--------|
| `el-button` | 46+ | `ButtonV2` | ⏳ 待迁移 | - | - |
| `el-input` | 40+ | `InputV2` | ⏳ 待迁移 | - | - |
| `el-dialog` | 44+ | `DialogV2` | ⏳ 待迁移 | - | - |
| `el-form` | 38+ | `FormV2` (VeeValidate) | ⏳ 待迁移 | - | - |
| `el-table` | 16+ | `TableV2` | ⏳ 待迁移 | - | - |
| `el-select` | 25+ | `SelectV2` | ⏳ 待迁移 | - | - |

### 1.2 全局 API（P1 - Week 2）

| Element Plus API | 使用次数 | shadcn-vue 对应 | 迁移状态 | 完成日期 |
|-----------------|---------|----------------|---------|---------|
| `ElMessage` | 26 | `toast.success()`, `toast.error()` | ⏳ 待迁移 | - |
| `ElMessageBox.confirm` | 18 | `AlertDialog` | ⏳ 待迁移 | - |
| `ElMessageBox.alert` | 20 | `AlertDialog` | ⏳ 待迁移 | - |

### 1.3 中频组件（P2 - Week 3）

| Element Plus 组件 | 使用次数 | shadcn-vue 对应 | 迁移状态 |
|-----------------|---------|----------------|---------|
| `el-tooltip` | 14 | `Tooltip` | ⏳ 待迁移 |
| `el-pagination` | 13 | `Pagination` | ⏳ 待迁移 |
| `el-descriptions` | 33 | `Descriptions` | ⏳ 待迁移 |
| `el-date-picker` | 15 | `DatePicker` | ⏳ 待迁移 |
| `el-tabs` | 5 | `Tabs` | ⏳ 待迁移 |
| `el-card` | 8 | `Card` | ⏳ 待迁移 |

---

## 二、页面迁移进度

### 2.1 试点页面（Week 2）

| 页面 | Element Plus 组件 | 迁移状态 | 测试状态 |
|------|------------------|---------|---------|
| `Leads.vue` | el-button, el-table | ⏳ 待迁移 | ⏳ 待测试 |

### 2.2 高频页面（Week 3-4）

| 页面 | Element Plus 组件 | 迁移状态 |
|------|------------------|---------|
| `Customers.vue` | el-button, el-table, el-input, el-dialog | ⏳ 待迁移 |
| `Contracts.vue` | el-button, el-table, el-dialog, el-form | ⏳ 待迁移 |
| `Payments.vue` | el-button, el-table, el-dialog | ⏳ 待迁移 |

---

## 三、迁移检查清单

每次迁移完成后，请检查：

### 3.1 功能验证
- [ ] 组件已替换为 shadcn-vue 版本
- [ ] 所有功能正常（单元测试通过）
- [ ] Props 和 Events 正确映射

### 3.2 设计系统合规
- [ ] 使用 V2 Design Tokens（variables-v2.scss）
- [ ] 圆角统一 6px
- [ ] 主色 #2563EB
- [ ] Focus ring 可见（键盘导航测试）
- [ ] Touch target ≥44px（移动端测试）
- [ ] Reduced motion 支持

**Design Tokens 使用验证清单**（UI/UX Pro Max §6 Typography & Color）：

每次组件迁移后，必须验证：

#### 1. 颜色使用验证

| 检查项 | 规则 | 验证命令 |
|-------|------|---------|
| 禁止硬编码颜色 | 不允许 `color: #xxx` | `grep -r "#[0-9a-f]{3,6}" src/components/common` |
| 必须使用 Design Tokens | 使用 `$wolf-*-v2` | `grep -r "\$wolf-primary-v2" src/components/common` |
| 功能色语义化 | 使用 success/warning/danger | `grep -r "\$wolf-success-v2" src/components/common` |

#### 2. 圆角使用验证

| 检查项 | 规则 | 验证命令 |
|-------|------|---------|
| 禁止旧圆角值 | 不允许 4px/8px/12px/16px | `grep -r "border-radius: [4|8|12|16]px" src/components/common` |
| 统一 6px 圆角 | 使用 `$wolf-radius-v2` | `grep -r "\$wolf-radius-v2" src/components/common` |

#### 3. 阴影使用验证

| 检查项 | 规则 | 验证命令 |
|-------|------|---------|
| 禁止硬编码阴影 | 不允许 `box-shadow: 0 2px...` | `grep -r "box-shadow:" src/components/common` |
| 必须使用 Design Tokens | 使用 `$wolf-shadow-*-v2` | `grep -r "\$wolf-shadow-card-v2" src/components/common` |

#### 4. 过渡动画验证

| 检查项 | 规则 | 验证命令 |
|-------|------|---------|
| 禁止硬编码时长 | 不允许 `transition: 300ms` | `grep -r "transition: [0-9]+ms" src/components/common` |
| 统一 150ms | 使用 `$wolf-transition-v2` | `grep -r "\$wolf-transition-v2" src/components/common` |

#### 5. 间距验证

| 检查项 | 规则 | 验证命令 |
|-------|------|---------|
| 禁止硬编码间距 | 不允许 `margin: 20px` | `grep -r "margin: [0-9]+px" src/components/common` |
| 必须使用 8dp grid | 使用 `$wolf-space-*-v2` | `grep -r "\$wolf-space" src/components/common` |

---
- [ ] ESLint 无 Element Plus 警告
- [ ] 扫描脚本检测无新增使用
- [ ] 迁移清单已更新状态
- [ ] 功能测试通过

### 3.3 迁移追踪
- [ ] ESLint 无 Element Plus 警告
- [ ] 扫描脚本检测无新增使用
- [ ] 迁移清单已更新状态
- [ ] 功能测试通过

### 3.4 UI/UX Pro Max CRITICAL 规则验证清单

每次迁移后必须验证以下 **CRITICAL** 规则（UI/UX Pro Max §1 Accessibility + §2 Touch & Interaction）：

#### Accessibility (CRITICAL)

| 规则 | UI/UX Pro Max 要求 | 迁移后验证方法 |
|------|-------------------|---------------|
| **Focus States** | Focus ring 2–4px visible | Keyboard nav 测试（Tab 键） |
| **Touch Target** | Min 44×44px (iOS) / 48×48dp (Android) | Mobile 真机测试 |
| **Color Contrast** | 4.5:1 ratio for normal text | Chrome DevTools → Accessibility |
| **Keyboard Nav** | Tab order matches visual order | Tab 键完整导航测试 |
| **ARIA Labels** | aria-label for icon-only buttons | Screen reader (VoiceOver/NVDA) |
| **Reduced Motion** | Respect prefers-reduced-motion | CSS `@media (prefers-reduced-motion: reduce)` |

#### Touch & Interaction (CRITICAL)

| 规则 | UI/UX Pro Max 要求 | 迁移后验证方法 |
|------|-------------------|---------------|
| **Loading Feedback** | Disable button during async operations | 点击提交按钮 → Spinner 显示 |
| **Error Feedback** | Clear error messages near problem | 表单验证 → 错误显示在字段下方 |
| **cursor-pointer** | Add cursor-pointer to clickable elements | Hover 所有可点击元素 |
| **Press Feedback** | Visual feedback within 80-150ms | 点击按钮 → 立即视觉反馈 |
| **Disabled State** | Opacity 0.38–0.5 + cursor not-allowed | 禁用按钮 → 透明度降低 + 禁止光标 |

#### Forms & Feedback (MEDIUM)

| 规则 | UI/UX Pro Max 要求 | 迁移后验证方法 |
|------|-------------------|---------------|
| **Input Labels** | Visible label per input | FormLabel 存在（非 placeholder-only） |
| **Error Placement** | Show error below the related field | FormMessage 位置验证 |
| **Disabled States** | Opacity 0.38–0.5 + cursor change | Disabled 样式验证 |
| **Inline Validation** | Validate on blur (not keystroke) | VeeValidate 配置：`validateOnBlur: true` |
| **Helper Text** | Persistent helper text below complex inputs | helperText prop 存在 |

#### 验证工具清单

| 工具 | 用途 | 使用方法 |
|------|------|---------|
| Chrome DevTools Accessibility | Contrast ratio 检查 | DevTools → Accessibility → Contrast |
| axe-core | WCAG 合规检查 | npm install axe-core |
| Keyboard Nav Test | Tab 键导航测试 | 手动 Tab 键完整流程 |
| Screen Reader Test | VoiceOver/NVDA 测试 | macOS VoiceOver / Windows NVDA |
| Mobile Test | Touch target 测试 | iOS Safari / Android Chrome |
| Reduced Motion Test | CSS media query 测试 | 系统设置 → 减少动态效果 |

---

## 四、自动检测命令

```bash
# 扫描 Element Plus 使用
cd CRM-Client
bash scripts/scan-element-plus.sh

# 预期输出（完成时）
✅ 没有发现 Element Plus 组件使用！
✅ 没有发现 Element Plus import！
✅ 没有发现 Element Plus 全局 API 使用！
✅ 没有发现 Element Plus CSS 类！
🎉 100% 完成！所有 Element Plus 已迁移！
```

---

## 五、迁移后清理

完成所有迁移后：

1. **删除 Element Plus 全局注册**
   ```typescript
   // main.ts
   // ❌ 删除这行
   // app.use(ElementPlus)
   ```

2. **删除 Element Plus 依赖**
   ```bash
   npm uninstall element-plus @element-plus/icons-vue
   ```

3. **清理 Element Plus CSS**
   ```typescript
   // 删除所有 Element Plus CSS import
   // import 'element-plus/dist/index.css'
   ```

---

**最后更新**: 2026-07-08 | **总进度**: 0% (426+ 处待迁移)
```

---

## 四、迁移策略

### 4.1 渐进式迁移策略

```
迁移流程（确保不漏迁移）

Phase 0: 准备阶段（Week 1）
├─ Step 1: 安装 shadcn-vue + Tailwind + VeeValidate
├─ Step 2: 创建迁移追踪系统（ESLint + 扫描脚本 + CI）
├─ Step 3: 创建基础组件（ButtonV2, InputV2, TableV2）
└─ Step 4: 验证追踪系统工作正常

Phase 1: 试点迁移（Week 2）
├─ Step 5: 选择试点页面（Leads.vue）
├─ Step 6: 替换所有 Element Plus 组件
├─ Step 7: 功能验证 + 视觉验证
├─ Step 8: 运行扫描脚本确认无遗漏
└─ Step 9: 更新迁移清单

Phase 2: 批量迁移（Week 3-6）
├─ Step 10: 按组件类型批量替换（而非按页面）
│   ├── Week 3: el-button → ButtonV2（所有页面）
│   ├── Week 4: el-input → InputV2（所有页面）
│   ├── Week 5: el-table → TableV2（所有页面）
│   └── Week 6: el-dialog → DialogV2（所有页面）
├─ Step 11: 每个组件迁移后运行扫描脚本
└─ Step 12: CI 检查阻止新增 Element Plus 使用

Phase 3: 清理阶段（Week 7）
├─ Step 13: 运行最终扫描脚本（目标：0 处 Element Plus）
├─ Step 14: 删除 Element Plus 全局注册
├─ Step 15: 删除 Element Plus 依赖
└─ Step 16: 清理 Element Plus CSS
```

### 4.2 "确保不漏迁移"保障机制

| 机制 | 说明 | 阻止能力 |
|------|------|---------|
| **ESLint 规则** | 禁止 import + 禁止组件 + 禁止 CSS | ✅ 新代码 100% 阻止 |
| **扫描脚本** | 每日统计剩余 Element Plus 使用 | ✅ 可视化进度 |
| **CI 检查** | PR 中检查新增 Element Plus 使用 | ✅ 阻止新增 |
| **迁移清单** | 完整记录所有组件使用 | ✅ 不遗漏组件 |
| **功能验证** | 每次迁移后测试 | ✅ 功能不遗漏 |

---

## 五、依赖清单

### 5.1 新增依赖

```json
// package.json
{
  "dependencies": {
    // ✅ shadcn-vue（Vue 3 组件库）
    "shadcn-vue": "^0.x.x",
    "radix-vue": "^1.x.x",
    
    // ✅ VeeValidate（Vue 表单验证）
    "vee-validate": "^4.x.x",
    "@vee-validate/zod": "^4.x.x",
    
    // ✅ TanStack Table（表格组件）
    "@tanstack/vue-table": "^8.x.x",
    
    // ✅ Tailwind CSS
    "tailwindcss": "^3.x.x",
    "postcss": "^8.x.x",
    "autoprefixer": "^10.x.x",
    
    // ✅ Lucide Icons（替代 Element Plus Icons）
    "lucide-vue-next": "^0.x.x"
  },
  "devDependencies": {
    // ✅ Tailwind 工具
    "tailwindcss": "^3.x.x"
  }
}
```

### 5.2 移除依赖

```json
// package.json（迁移完成后删除）
{
  "dependencies": {
    // ❌ 删除 Element Plus
    // "element-plus": "^2.13.2",
    // "@element-plus/icons-vue": "^2.3.2"
  }
}
```

---

## 六、验证标准

### 6.1 迁移完成标准

| 标准 | 验证方式 | 目标值 |
|------|---------|-------|
| **Element Plus 使用** | 扫描脚本 | 0 处 |
| **ESLint 警告** | npm run lint | 0 个 Element Plus 相关警告 |
| **功能完整性** | 功能测试 | 100% 功能正常 |
| **设计系统合规** | Stylelint | 100% 使用 V2 Design Tokens |
| **移动端适配** | 移动端测试 | Touch target ≥44px |
| **无障碍** | 键盘导航测试 | Focus ring 可见 |

### 6.2 最终验收命令

```bash
# 验收命令
cd CRM-Client

# 1. 运行扫描脚本（目标：0 处 Element Plus）
bash scripts/scan-element-plus.sh

# 2. 运行 ESLint（目标：无 Element Plus 警告）
npm run lint

# 3. 运行 Stylelint（目标：无硬编码警告）
npm run lint:style

# 4. 运行单元测试（目标：100% 通过）
npm run test:unit

# 5. 功能测试（目标：手动测试所有核心功能）
```

---

## 七、风险与应对

### 7.1 潜在风险

| 风险 | 说明 | 应对措施 |
|------|------|---------|
| **全局注册绕过 ESLint** | `app.use(ElementPlus)` 使组件全局可用 | ESLint 检测模板中的 `el-*` 组件 |
| **迁移规模大** | 426+ 处使用需要系统性追踪 | 扫描脚本 + CI 检查 + 迁移清单 |
| **CSS 类名冲突** | Element Plus CSS 类需要清理 | Stylelint 检测 `.el-*` 类 |
| **功能遗漏** | 迁移后功能缺失 | 功能验证测试 |

### 7.2 应对措施

| 措施 | 说明 |
|------|------|
| **并行运行新旧组件** | 通过 feature flag 控制使用新/旧组件 |
| **视觉回归测试** | Playwright 截图对比 |
| **每次迁移后验证** | 功能测试 + 扫描脚本 |
| **保留 Element Plus 作为 fallback** | 过渡期保留全局注册 |

---

**文档状态**: ✅ 设计完成 | **下一步**: Spec self-review
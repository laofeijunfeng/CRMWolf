# AI 创建线索弹窗改造实施方案

**创建时间**: 2026-07-10
**状态**: 待实施

---

## 一、现状分析

### 1.1 现有实现

| 项目 | 现状 |
|------|------|
| **组件库** | Element Plus（el-dialog, el-button, el-input, el-form） |
| **UI 风格** | Element Plus 默认样式 |
| **设计规范** | 旧版 `variables.scss` |
| **交互流程** | 4 阶段：input → parsing → preview → success |

### 1.2 问题

| 问题 | 影响 |
|------|------|
| ❌ 使用 Element Plus | 违反 shadcn-vue 强制使用规范（CRITICAL） |
| ❌ 使用旧版 variables.scss | 违反 V2 Design Tokens 规范 |
| ❌ 自定义动画 | 可能与 shadcn-vue 原生动画冲突 |
| ❌ 无障碍支持不足 | 无 aria-label, focus 管理 |

---

## 二、改造目标

### 2.1 核心目标

| 目标 | 规范依据 |
|------|----------|
| **使用 shadcn-vue Dialog** | README.md §8.2 强制使用规范 |
| **应用 V2 Design Tokens** | MASTER.md §二 Design Token 规范 |
| **保留原生动画** | README.md §8.5 组件封装原则 |
| **完善无障碍** | UI/UX Pro Max §1 Accessibility |
| **优化表单 UX** | UI/UX Pro Max §8 Forms & Feedback |

### 2.2 关键数值

| 属性 | Token | 值 |
|------|-------|-----|
| **主色** | `$wolf-primary-v2` | `#2563EB` |
| **圆角** | `$wolf-radius-v2` | `6px` |
| **过渡** | `$wolf-transition-v2` | `150ms ease` |
| **按钮高度** | `$wolf-button-height-md-v2` | `32px`（桌面端） |
| **输入框高度** | `$wolf-input-height-v2` | `32px`（桌面端） |

---

## 三、组件选型

### 3.1 shadcn-vue 组件映射

| Element Plus | shadcn-vue | 用途 |
|--------------|-----------|------|
| `el-dialog` | `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogFooter` | 弹窗容器 |
| `el-button` | `Button` | 按钮 |
| `el-input` | `Input` | 输入框 |
| `el-input type="textarea"` | `Textarea` | 多行文本 |
| `el-select` | `Select` | 下拉选择 |
| `el-form`, `el-form-item` | `Form` 组件 + VeeValidate | 表单验证 |
| `el-icon` | Lucide Icons | 图标 |

### 3.2 组件导入方式

```typescript
// ✅ 正确：统一从 crmwolf 导入
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Textarea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/crmwolf'

// 图标
import {
  Info,
  WandSparkles,
  Loader2,
  CheckCircle,
  AlertCircle,
  FileText,
  CircleCheck
} from 'lucide-vue-next'
```

---

## 四、交互流程设计

### 4.1 阶段流程（保持不变）

```
Stage 1: input      → 输入自然语言描述
Stage 2: parsing    → AI 解析（SSE 实时显示思考过程）
Stage 3: preview    → 预览表单 + 手动补充缺失字段
Stage 4: success    → 创建成功 + 查看线索入口
```

### 4.2 Dialog 动画规范（UI/UX Pro Max §7）

| 规范 | 要求 |
|------|------|
| **进入动画** | 使用 Dialog 原生 scale + fade |
| **退出动画** | 保留原生动画（退出时长 ≈ 进入时长 × 0.6） |
| **禁止修改** | 仅封装样式，保留 shadcn-vue 原生动画 |
| **Reduced Motion** | 自动支持 `prefers-reduced-motion` |

---

## 五、UI 规范设计

### 5.1 Dialog 容器样式

```scss
// DialogContent 样式（符合 MASTER.md §5.5）
.ai-lead-create-dialog {
  // 宽度：600px（适中，适合表单）
  max-width: 600px;
  
  // 圆角：统一 6px
  border-radius: $wolf-radius-v2;  // 6px
  
  // 阴影：Modal 级别
  box-shadow: $wolf-shadow-modal-v2;  // 0 4px 16px rgba(0, 0, 0, 0.15)
  
  // 背景：卡片背景
  background: $wolf-bg-card-v2;  // #FFFFFF
}
```

### 5.2 表单布局（UI/UX Pro Max §8）

```scss
// 表单网格布局
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);  // 两列布局
  gap: $wolf-space-md-v2;  // 12px
  margin-bottom: $wolf-space-md-v2;
}

// 表单项样式（符合 MASTER.md §5.2）
.form-item {
  margin-bottom: $wolf-space-md-v2;
}

// 标签样式
.form-label {
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  color: $wolf-text-secondary-v2;  // #64748B
  margin-bottom: $wolf-space-xs-v2;  // 4px
}

// 输入框样式
.input-field {
  height: $wolf-input-height-v2;  // 32px
  border-radius: $wolf-radius-v2;  // 6px
  border: 1px solid $wolf-border-default-v2;  // #E4ECFC
  
  &:focus {
    border-color: $wolf-primary-v2;
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
  }
}
```

---

## 六、无障碍规范（UI/UX Pro Max §1）

### 6.1 必须实现

| 规范 | 实现 |
|------|------|
| **Focus 管理** | Dialog 打开时自动聚焦到输入框 |
| **aria-label** | 所有按钮添加 aria-label |
| **aria-describedby** | 缺失字段提示使用 aria-describedby |
| **role="alert"** | 错误提示使用 role="alert" |
| **键盘导航** | Tab 顺序符合视觉顺序 |
| **Escape 关闭** | 保留 Dialog 原生 Escape 关闭 |

### 6.2 示例代码

```vue
<DialogContent class="ai-lead-create-dialog">
  <DialogHeader>
    <DialogTitle>AI 智能创建线索</DialogTitle>
  </DialogHeader>
  
  <!-- 输入阶段 -->
  <div v-if="stage === 'input'" class="input-stage">
    <Textarea
      v-model="inputText"
      :rows="4"
      placeholder="例如：张三，13800138000，来自杭州的阿里巴巴"
      aria-label="输入线索信息"
      @keydown.ctrl.enter="handleParse"
    />
    
    <Button
      variant="default"
      :disabled="!inputText.trim()"
      aria-label="智能识别线索信息"
      @click="handleParse"
    >
      <WandSparkles class="w-4 h-4 mr-2" />
      智能识别
    </Button>
  </div>
</DialogContent>
```

---

## 七、状态设计

### 7.1 状态徽章（符合 MASTER.md §5.5 Badge 规范）

| 状态 | 样式 | Token |
|------|------|-------|
| **解析中** | 蓝色徽章 | `$wolf-primary-light-v2` |
| **解析完成** | 绿色徽章 | `$wolf-success-bg-v2` |
| **缺失字段** | 黄色徽章 | `$wolf-warning-bg-v2` |
| **创建成功** | 绿色徽章 | `$wolf-success-bg-v2` |

### 7.2 Loading 状态（UI/UX Pro Max §2）

```vue
<!-- 解析中状态 -->
<div v-if="isParsing" class="parse-stage">
  <div class="status-message">
    <Loader2 class="w-5 h-5 animate-spin text-primary" />
    <span>{{ statusMessage }}</span>
  </div>
  
  <!-- AI 思考过程 -->
  <div v-if="thinkingContent" class="thinking-section">
    <div class="thinking-header">AI 思考过程</div>
    <div class="thinking-content">{{ thinkingContent }}</div>
  </div>
</div>
```

### 7.3 Toast 提示（必须使用 vue-sonner）

> **规范依据**: README.md §8.2 已安装组件清单

```typescript
import { toast } from 'vue-sonner'

// 使用示例
toast.success('线索创建成功')
toast.error('解析失败，请重试')
toast.info('正在解析...', { duration: 3000 })
```

**禁止使用**：
- ❌ `ElMessage`（Element Plus）
- ❌ 自定义 Toast 组件

---

## 八、移动端响应式设计（UI/UX Pro Max §5）

> ⚠️ **CRITICAL**: 必须支持移动端 Touch Target 合规

### 8.1 响应式断点

```scss
// 移动端适配（< 768px）
@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .ai-lead-create-dialog {
    // 移动端全屏宽度
    max-width: 100%;
    margin: 0;
    border-radius: 0;
    
    // 移动端 Dialog 从底部滑入（符合 UI/UX Pro Max §7 modal-motion）
    transform: translateY(100%);
    animation: slide-up 300ms ease-out;
  }
  
  // 移动端表单单列布局
  .form-grid {
    grid-template-columns: 1fr;
  }
}
```

### 8.2 Touch Target 合规（UI/UX Pro Max §2）

| 元素 | 桌面端 | 移动端 | 规范 |
|------|--------|--------|------|
| **按钮** | 32px 高度 | **44px 最小高度** | Touch Target Minimum |
| **输入框** | 32px 高度 | **44px 最小高度** | Touch-friendly Input |
| **Select** | 32px 高度 | **44px 最小高度** | Touch Target Minimum |

```scss
// 移动端按钮样式
@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .dialog-button {
    min-height: $wolf-touch-target-min-v2;  // 44px
    padding: $wolf-button-padding-mobile-v2;  // 12px 24px
  }
  
  .dialog-input {
    min-height: $wolf-input-height-mobile-v2;  // 44px
    font-size: $wolf-font-size-body-mobile-v2;  // 16px（避免 iOS auto-zoom）
  }
}
```

### 8.3 Scrim（遮罩层）样式

> **规范依据**: UI/UX Pro Max §7 Light/Dark Mode Contrast

```scss
// Dialog 背景遮罩（40-60% 黑色透明度）
.dialog-overlay {
  background: rgba(0, 0, 0, 0.5);  // 50% 黑色
  backdrop-filter: blur(4px);  // 轻微模糊（iOS HIG 风格）
}
```

---

## 九、表单验证方案

### 9.1 推荐方案：VeeValidate

> **规范依据**: README.md §九参考资料 - VeeValidate 已在技术栈中

```typescript
import { useForm } from 'vee-validate'
import * as z from 'zod'
import { toTypedSchema } from '@vee-validate/zod'

// 定义验证规则
const schema = toTypedSchema(
  z.object({
    lead_name: z.string().min(1, '请输入线索名称'),
    source: z.string().min(1, '请选择线索来源'),
    city: z.string().min(1, '请输入所在城市'),
    contact_name: z.string().min(1, '请输入联系人姓名'),
    contact_phone: z.string().regex(/^1[3-9]\d{9}$/, '请输入正确的手机号码')
  })
)

const { handleSubmit, errors } = useForm({
  validationSchema: schema
})
```

### 9.2 错误提示规范（UI/UX Pro Max §8）

```vue
<!-- 错误提示放在输入框下方 -->
<div class="form-item">
  <Label>线索名称 <span class="required">*</span></Label>
  <Input v-model="form.lead_name" />
  <span v-if="errors.lead_name" class="error-message" role="alert">
    {{ errors.lead_name }}
  </span>
</div>

<style scoped lang="scss">
.error-message {
  display: block;
  margin-top: $wolf-space-xs-v2;  // 4px
  font-size: $wolf-font-size-caption-v2;  // 12px
  color: $wolf-danger-text-v2;  // #DC2626
}
</style>
```

---

## 十、文件结构

### 10.1 新组件位置

```
CRM-Client/src/components/
└── AILeadCreateDialog.vue  # 改造后的组件
```

### 10.2 使用方式（保持不变）

```vue
<!-- Leads.vue -->
<template>
  <AILeadCreateDialog
    v-model="showAILeadCreate"
    @created="fetchLeadList"
  />
</template>

<script setup>
const showAILeadCreate = ref(false)
</script>
```

---

## 十一、实施步骤

### Phase 1：基础结构替换（必须）

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| 1 | 替换 `el-dialog` → `Dialog` 组件 | P0 |
| 2 | 替换 `el-button` → `Button` 组件 | P0 |
| 3 | 替换 `el-input` → `Input` / `Textarea` | P0 |
| 4 | 替换 `el-select` → `Select` 组件 | P0 |
| 5 | 替换 `@element-plus/icons-vue` → `lucide-vue-next` | P0 |

### Phase 2：样式改造（必须）

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| 6 | 移除 `variables.scss` 引用 | P0 |
| 7 | 应用 `variables-v2.scss` | P0 |
| 8 | 应用 V2 Design Tokens | P0 |
| 9 | 保留 shadcn-vue 原生动画 | P0 |

### Phase 3：无障碍优化（推荐）

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| 10 | 添加 aria-label | P1 |
| 11 | 实现 Focus 管理 | P1 |
| 12 | 添加 role="alert" 错误提示 | P1 |

### Phase 4：移动端适配（必须）

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| 13 | 移动端 Touch Target 合规（44px） | P0 |
| 14 | 移动端 Dialog 尺寸适配（全屏） | P0 |
| 15 | 移动端表单单列布局 | P0 |
| 16 | 移动端输入框字号 16px（避免 auto-zoom） | P0 |

### Phase 5：测试验证（必须）

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| 17 | 功能测试（4 阶段流程） | P0 |
| 18 | 样式测试（V2 Token 验证） | P0 |
| 19 | 移动端测试（Touch Target、布局） | P0 |
| 20 | 无障碍测试（键盘导航） | P1 |

---

## 十二、风险与应对

### 12.1 潜在风险

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| Form 验证逻辑复杂 | VeeValidate 学习成本 | 可暂时保留原生验证逻辑 |
| Select 组件样式差异 | 视觉不一致 | 按 MASTER.md §5.2 封装样式 |
| SSE 流式显示动画 | 可能闪烁 | 使用 Vue Transition 组件 |

### 12.2 兼容性保证

| 措施 | 说明 |
|------|------|
| **保持 Props 接口不变** | `v-model` + `@success` 事件 |
| **保持业务逻辑不变** | 4 阶段流程、SSE 解析逻辑 |
| **保持 API 调用不变** | `leadAiApi.parseSSE()` |

---

## 十三、验收标准

### 13.1 必须达成

- ✅ 所有 UI 组件来自 `src/components/ui/`
- ✅ 使用 `variables-v2.scss`
- ✅ 所有颜色/圆角/间距使用 Design Tokens
- ✅ 保留 shadcn-vue 原生动画
- ✅ 4 阶段流程功能正常
- ✅ SSE 实时显示正常
- ✅ **移动端 Touch Target ≥44px**
- ✅ **使用 vue-sonner Toast**

### 13.2 推荐达成

- ✅ 所有按钮有 aria-label
- ✅ 键盘导航流畅
- ✅ Focus 状态可见
- ✅ Reduced Motion 支持
- ✅ VeeValidate 表单验证

---

## 十四、参考资料

| 文档 | 路径 |
|------|------|
| **设计系统规范** | `CRM-Docs/design-system/MASTER.md` |
| **shadcn-vue 组件清单** | `CRM-Docs/design-system/README.md §8.2` |
| **UI/UX Pro Max** | `~/.claude/skills/ui-ux-pro-max/` |
| **组件封装原则** | `CRM-Docs/design-system/README.md §8.5` |

---

## 十五、相关文件

| 文件 | 路径 |
|------|------|
| **现有组件** | `CRM-Client/src/components/AILeadCreateDialog.vue` |
| **设计规范** | `CRM-Docs/design-system/MASTER.md` |
| **组件清单** | `CRM-Docs/design-system/README.md` |

---

**方案状态**: 待实施
**下一步**: 等待用户确认后开始 Phase 1 实施
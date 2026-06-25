---
status: active
created: 2026-06-25
updated: 2026-06-25
related_plan: AI-THINKING-PROCESS-DESIGN.md, AI-HUMAN-IN-THE-LOOP-DESIGN.md
mockup_reference: AI-THINKING-PROCESS-MOCKUP-V2.html
implementation_status: pending
---

# AI Execution Log V2 紧凑优化实施设计

**创建时间**: 2026-06-25
**设计版本**: V2 (10/10 紧凑版)
**目标**: 将 AI 助手执行日志从 V1 (8/10) 优化到 V2 (10/10)，实现信息密度最大化 + 认知负担最小化

---

## 🎯 设计目标

| 指标 | V1 (当前) | V2 (目标) | 提升 |
|------|-----------|-----------|------|
| **信息密度** | 40% 内容 / 60% 结构 | 80% 内容 / 20% 结构 | +100% |
| **认知负担** | 3-4 视觉元素/动作 | 1-2 视觉元素/动作 | -67% |
| **扫描速度** | 2-3 行/步骤 | 1 行/步骤 | +100% |
| **完整对话空间** | 15+ 行 | 5 行 | -67% |

---

## 📐 第一节：整体架构

### 1.1 组件清理策略

**删除的旧组件**：
| 组件 | 原位置 | 替代方案 |
|------|--------|----------|
| `CompactExecutionLog.vue` | `components/` | 重写同名组件 |
| `CollapsedView.vue` | `components/` | 重写同名组件（36px） |
| `ExpandedView.vue` | `components/` | 重写同名组件（Inline Steps） |
| `StatusCard.vue` | `components/` | 替换为 `InlineStep.vue` |
| `PreviewCard.vue` | `components/ai-assistant/` | 替换为 `InlineCandidate.vue` + `CompactConfirmSummary.vue` |
| `PreviewField.vue` | `components/ai-assistant/` | 不需要 |

**保留复用的组件**：
| 组件 | 调整内容 |
|------|----------|
| `SmartBoundaryLine.vue` | 无需修改（渐变动画） |
| `EmptyState.vue` | 高度调整（36px → 28px 紧凑版） |
| `ThinkingBubble.vue` | CSS 调整为 `.thinking-prefix` inline 样式 |

### 1.2 新建组件列表

| 组件 | 功能 | 优先级 |
|------|------|--------|
| `InlineStep.vue` | 单行步骤卡片（标题+描述合并） | P0 |
| `InlineCandidate.vue` | 单行候选卡片 + Radio + Hover Tooltip | P0 |
| `HoverPreviewTooltip.vue` | 悬停预览 Tooltip（通用） | P0 |
| `CompactConfirmSummary.vue` | 紧凑确认摘要（Progressive Disclosure） | P0 |
| `CompactInfoGap.vue` | 紧凑信息补全（inline input） | P1 |

### 1.3 最终文件结构

```
CRM-Client/src/components/
├── CompactExecutionLog.vue      # 重写（V2 容器）
├── CollapsedView.vue            # 重写（36px + Round Badge inline）
├── ExpandedView.vue             # 重写（Inline Steps）
├── InlineStep.vue               # 新建（单行步骤卡片）
├── InlineCandidate.vue          # 新建（单行候选卡片）
├── CompactConfirmSummary.vue    # 新建（紧凑确认摘要）
├── CompactInfoGap.vue           # 新建（紧凑信息补全）
├── HoverPreviewTooltip.vue      # 新建（通用 Tooltip）
├── SmartBoundaryLine.vue        # 保留（渐变动画）
├── EmptyState.vue               # 保留（高度调整）
├── ThinkingBubble.vue           # 保留（CSS 调整为 inline prefix）
│
├── ai-assistant/
│   ├── PreviewCard.vue          # ❌ 删除
│   └── PreviewField.vue         # ❌ 删除
│   └── 其他文件保留不变
```

---

## 📐 第二节：核心组件详细设计

### 2.1 InlineStep.vue

**功能**：单行步骤卡片，标题+描述合并为 inline 文本

**Props**：
```typescript
interface InlineStepProps {
  step: ExecutionStep       // 执行步骤数据
  round?: number            // 轮次（用于 Round Badge）
  totalRounds?: number      // 总轮次（用于进度显示 R2/5）
  isCurrent?: boolean       // 是否当前执行中
  status?: 'success' | 'error' | 'warning' | 'loading'
}
```

**模板结构**：
```vue
<template>
  <div class="step-inline" :class="statusClass">
    <!-- Round Badge (inline) -->
    <span v-if="round" class="round-badge" :class="{ current: isCurrent }">
      {{ roundBadgeText }}
    </span>
    
    <!-- 状态图标 (16px) -->
    <span class="status-icon" :class="statusClass">
      <el-icon><component :is="statusIcon" /></el-icon>
    </span>
    
    <!-- 步骤文本 (单行，合并标题+描述) -->
    <span class="step-text">{{ inlineText }}</span>
    
    <!-- Hover Tooltip (可选) -->
    <HoverPreviewTooltip v-if="hasDetails" :rows="tooltipRows" />
  </div>
</template>
```

**CSS 规范（精确匹配 Mockup V2）**：
```scss
.step-inline {
  padding: 3px 16px;           // V2: 3px (V1: 8px)
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  line-height: 1.4;
  cursor: default;
  transition: background 0.15s;
}

.step-inline:hover {
  background: $wolf-bg-inline-hover;  // rgba(74,111,165,0.05)
}

.step-inline.success .step-text {
  color: $wolf-success-text;   // #2B633C
}

.step-inline.error .step-text {
  color: $wolf-danger-text;    // #7A2828
}

.step-inline.warning .step-text {
  color: $wolf-warning-text;   // #7A4F1E
}

.step-text {
  flex: 1;
}
```

**Round Badge 规范**：
```scss
.round-badge {
  display: inline-flex;
  padding: 2px 6px;
  background: $wolf-primary-light;  // rgba(74,111,165,0.1)
  border-radius: 4px;
  font-size: 11px;             // V2: 11px (V1: 12px)
  color: $wolf-primary;
  font-weight: 500;
  margin-right: 6px;
}

.round-badge.current {
  background: $wolf-warning-bg;     // #FFF6E8
  color: $wolf-warning-text;        // #7A4F1E
}
```

**Inline 文本生成逻辑**：
```typescript
const inlineText = computed(() => {
  // V2 格式：动作描述 + 结果摘要
  // 示例："查找客户信息，找到 1 个客户：光大证券股份有限公司"
  
  // 方案 A：使用后端生成的 inline_text 字段（推荐）
  if (step.inline_text) {
    return step.inline_text
  }
  
  // 方案 B：前端合并 title + description（后备）
  const title = step.title || getBusinessTitle(step.tool)
  const description = step.description || step.summary
  return `${title}，${description}`
})

const roundBadgeText = computed(() => {
  if (totalRounds) {
    return `R${round}/${totalRounds}`  // 进度格式：R2/5
  }
  return `R${round}`                    // 简单格式：R1
})
```

---

### 2.2 InlineCandidate.vue

**功能**：单行候选卡片 + Radio + Hover Tooltip 显示完整详情

**Props**：
```typescript
interface InlineCandidateProps {
  candidate: EntityCandidate    // 候选实体数据
  selected?: boolean           // 是否选中
}
```

**模板结构**：
```vue
<template>
  <div 
    class="candidate-inline"
    :class="{ selected }"
    @click="handleSelect"
    @keydown="handleKeydown"
    tabindex="0"
    role="radio"
    :aria-checked="selected"
  >
    <!-- Radio (14px, flex-shrink: 0) -->
    <span class="candidate-radio" :class="{ selected }">
      <span v-if="selected" class="radio-dot"></span>
    </span>
    
    <!-- 实体名称 -->
    <span class="candidate-name">{{ candidate.name }}</span>
    
    <!-- Entity Info Inline (括号格式，CSS ::before/::after 生成) -->
    <span class="entity-info-inline">{{ candidate.entity_info_inline }}</span>
    
    <!-- Hover Tooltip -->
    <HoverPreviewTooltip :rows="tooltipRows" />
  </div>
</template>
```

**CSS 规范（精确匹配 Mockup V2）**：
```scss
.candidate-inline {
  padding: 6px 12px;           // V2: 6px (V1: 12px)
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid transparent;
  transition: all 0.15s;       // V2: 0.15s (V1: 0.2s)
  font-size: 14px;
}

.candidate-inline:hover {
  background: $wolf-bg-hover;
  border-color: $wolf-border-light;
}

.candidate-inline:focus-visible {
  outline: 2px solid $wolf-primary;
  outline-offset: 1px;
}

.candidate-inline.selected {
  background: $wolf-primary-light;
  border-color: $wolf-primary;
}

.candidate-radio {
  width: 14px;                 // V2: 14px (V1: 16px)
  height: 14px;
  border: 1.5px solid $wolf-border-default;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}

.candidate-inline.selected .candidate-radio {
  border-color: $wolf-primary;
  background: $wolf-primary;
}

.candidate-inline.selected .candidate-radio::after {
  content: '';
  width: 4px;
  height: 4px;
  background: white;
  border-radius: 50%;
}

.candidate-name {
  font-weight: 500;
  color: $wolf-text-primary;
}

.entity-info-inline {
  font-size: 12px;
  color: $wolf-text-tertiary;
  margin-left: 4px;
  
  // ✅ 括号由 CSS 生成，不在模板中写
  &::before { content: '('; }
  &::after { content: ')'; }
}
```

**键盘导航**：
```typescript
const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'Enter':
    case 'Space':
      handleSelect()
      event.preventDefault()
      break
    case 'Escape':
      emit('cancel')
      event.preventDefault()
      break
  }
}
```

---

### 2.3 HoverPreviewTooltip.vue

**功能**：悬停显示完整实体详情

**Props**：
```typescript
interface HoverPreviewTooltipProps {
  rows: TooltipRow[]           // 多行信息
  minWidth?: number            // 最小宽度 (200px)
}

interface TooltipRow {
  label: string                // "商机ID"
  value: string                // "15"
}
```

**模板结构**：
```vue
<template>
  <div class="hover-preview">
    <slot />  <!-- 触发元素 -->
    
    <div class="hover-preview-tooltip">
      <div v-for="row in rows" class="tooltip-row">
        <span class="tooltip-label">{{ row.label }}:</span>
        <span class="tooltip-value">{{ row.value }}</span>
      </div>
    </div>
  </div>
</template>
```

**CSS 规范**：
```scss
.hover-preview {
  position: relative;
}

.hover-preview-tooltip {
  position: absolute;
  left: 0;
  top: 100%;
  margin-top: 4px;
  background: $wolf-bg-card;
  border: 1px solid $wolf-border-default;
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);  // V2 阴影
  font-size: 12px;
  z-index: 100;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s, visibility 0.15s;
  white-space: nowrap;
  min-width: 200px;
}

.hover-preview:hover .hover-preview-tooltip {
  opacity: 1;
  visibility: visible;
}

.tooltip-row {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.tooltip-label {
  color: $wolf-text-tertiary;
}

.tooltip-value {
  color: $wolf-text-primary;
}
```

---

## 📐 第三节：其他组件设计

### 3.1 CompactConfirmSummary.vue

**功能**：确认节点摘要（1 行），点击展开详情（Progressive Disclosure）

**Props**：
```typescript
interface CompactConfirmSummaryProps {
  round?: number
  title: string                 // "创建跟进记录"
  params: Record<string, any>   // 参数数据
  riskLevel?: 'low' | 'medium' | 'high'
  status?: 'waiting' | 'confirmed' | 'cancelled'
}
```

**模板结构**：
```vue
<template>
  <!-- 摘要状态（默认显示） -->
  <div 
    class="confirmation-summary"
    :class="[riskLevelClass, statusClass]"
    @click="toggleExpand"
  >
    <span class="round-badge" :class="{ current: isCurrent }">R{{ round }}</span>
    <span class="status-icon warning">⚠</span>
    <span class="confirm-label" :class="statusClass">{{ statusLabel }}</span>
    <span class="params-inline">{{ inlineParams }}</span>
    <span class="expand-hint">{{ expanded ? '↑ 收起' : '[点击展开详情]' }}</span>
  </div>
  
  <!-- 展开状态（点击后显示） -->
  <div v-if="expanded" class="confirmation-expanded">
    <div class="expanded-params">
      <div v-for="(value, key) in detailParams" class="expanded-param-row">
        <span class="expanded-param-name">{{ key }}：</span>
        <span 
          class="expanded-param-value"
          :class="{ entity: value.isEntity }"
          @click="value.isEntity && handleEntityClick(value)"
        >
          {{ value.text }}
        </span>
      </div>
    </div>
    <div class="action-buttons">
      <button class="btn-sm btn-confirm" @click="handleConfirm">确认执行</button>
      <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
    </div>
  </div>
</template>
```

**CSS 规范**：
```scss
// 摘要状态
.confirmation-summary {
  padding: 6px 16px;
  background: $wolf-warning-bg;
  border-left: 3px solid $wolf-warning-text;
  border-radius: 4px;
  margin: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 14px;
}

.confirmation-summary:hover {
  background: $wolf-warning-bg;
  filter: brightness(0.98);
}

.confirmation-summary.high-risk {
  border-left-width: 4px;
  border-left-color: $wolf-danger-text;
}

.confirmation-summary.low-risk {
  border-left-width: 2px;
  border-left-color: $wolf-success-text;
}

.confirmation-summary.confirmed {
  background: $wolf-success-bg;
  border-left-color: $wolf-success-text;
}

.confirm-label {
  font-size: 12px;
  color: $wolf-warning-text;
  font-weight: 500;
  background: rgba(122, 79, 30, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.confirmation-summary.confirmed .confirm-label {
  color: $wolf-success-text;
  background: rgba(43, 99, 60, 0.1);
}

// Inline 参数
.params-inline {
  font-size: 14px;
  color: $wolf-text-primary;
  flex: 1;
}

// 展开状态
.confirmation-expanded {
  padding: 8px 16px;
  background: $wolf-warning-bg;
  border-left: 3px solid $wolf-warning-text;
  border-radius: 4px;
  margin: 4px 16px;
}

.expanded-params {
  font-size: 12px;
  color: $wolf-text-secondary;
  background: $wolf-bg-card;
  padding: 8px;
  border-radius: 4px;
  margin: 8px 0;
}

.expanded-param-row {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.expanded-param-value.entity {
  color: $wolf-primary;
  cursor: pointer;
}

.expanded-param-value.entity:hover {
  text-decoration: underline;
}

// 按钮
.action-buttons {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn-sm {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  border: none;
  transition: background 0.15s;
}
```

---

### 3.2 CompactInfoGap.vue

**功能**：缺失字段 inline 提示 + inline 输入表单

**Props**：
```typescript
interface CompactInfoGapProps {
  round?: number
  title: string
  filledParams: Record<string, string>  // 已填参数
  missingField: string                   // 缺失字段名
  inputLabel: string                     // 输入框 label
  inputValue?: string                    // 输入值
}
```

**模板结构**：
```vue
<template>
  <!-- 摘要状态 -->
  <div class="info-gap-summary">
    <span class="round-badge current">R{{ round }}</span>
    <span class="status-icon error">✗</span>
    <span class="gap-label">缺失</span>
    <span class="params-inline">{{ inlineText }}</span>
    <span class="missing-field">[需补: {{ missingField }}]</span>
  </div>
  
  <!-- Inline Input Form -->
  <div class="inline-input-row">
    <span class="inline-input-label">{{ inputLabel }}:</span>
    <input 
      v-model="inputValue"
      class="inline-input-box"
      :placeholder="placeholder"
      @keyup.enter="handleSubmit"
    />
    <button class="inline-search-btn" @click="handleSearch">搜索</button>
  </div>
  
  <div class="action-buttons">
    <button class="btn-sm btn-confirm" @click="handleSubmit">重新提交</button>
    <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
  </div>
</template>
```

**CSS 规范**：
```scss
.info-gap-summary {
  padding: 6px 16px;
  background: $wolf-danger-bg;
  border-left: 3px solid $wolf-danger-text;
  border-radius: 4px;
  margin: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.info-gap-summary:hover {
  filter: brightness(0.98);
}

.gap-label {
  font-size: 12px;
  color: $wolf-danger-text;
  font-weight: 500;
  background: rgba(122, 28, 28, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.missing-field {
  color: $wolf-danger-text;
  font-weight: 500;
}

.inline-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 16px;
  background: $wolf-bg-card;
  border: 1px solid $wolf-border-default;
  border-radius: 4px;
  margin: 4px 16px;
}

.inline-input-box {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid $wolf-border-default;
  border-radius: 4px;
  font-size: 14px;
  min-width: 120px;
}

.inline-input-box:focus {
  outline: 2px solid $wolf-primary;
  border-color: $wolf-primary;
}

.inline-search-btn {
  padding: 4px 8px;
  background: $wolf-primary;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
```

---

### 3.3 CollapsedView.vue（重写）

**功能**：收起状态单行显示，36px 高度

**Props**：
```typescript
interface CollapsedViewProps {
  round?: number
  totalRounds?: number
  status: 'empty' | 'loading' | 'success' | 'error' | 'partial'
  stepText: string             // 当前步骤文本
}
```

**模板结构**：
```vue
<template>
  <div 
    class="collapsed-view"
    @click="$emit('click')"
    @keydown="handleKeydown"
    tabindex="0"
    role="button"
    aria-expanded="false"
    aria-label="AI 执行进度"
  >
    <!-- Round Badge (inline) -->
    <RoundBadge 
      v-if="round"
      :round="round"
      :total="totalRounds"
      :current="true"
    />
    
    <!-- 状态图标 (16px) -->
    <StatusIcon :status="status" />
    
    <!-- 当前步骤文本 (flex: 1) -->
    <span class="step-text">{{ stepText }}</span>
    
    <!-- 展开提示 (右侧) -->
    <span class="expand-hint">点击展开 →</span>
  </div>
</template>
```

**CSS 规范**：
```scss
.collapsed-view {
  padding: 4px 16px;           // V2: 4px 16px
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.2s;
  height: 36px;               // V2: 36px
}

.collapsed-view:hover {
  background: $wolf-bg-inline-hover;  // rgba(74,111,165,0.05)
}

.collapsed-view:focus-visible {
  outline: 2px solid $wolf-primary;
  outline-offset: 2px;
}

.step-text {
  flex: 1;
  font-size: 14px;
  color: $wolf-text-primary;
}

.expand-hint {
  font-size: 12px;
  color: $wolf-text-tertiary;
}
```

---

### 3.4 ExpandedView.vue（重写）

**功能**：展开状态 Inline Steps 轨迹显示

**Props**：
```typescript
interface ExpandedViewProps {
  steps: ExecutionStep[]
  currentRound?: number
}
```

**模板结构**：
```vue
<template>
  <div class="expanded-view">
    <!-- 收起按钮（匹配设计文档第 193 行） -->
    <div class="expand-header" @click="$emit('collapse')">
      <span>↑ 收起</span>
    </div>
    
    <!-- 滚动容器 -->
    <div class="expanded-content">
      <!-- 遍历步骤 -->
      <template v-for="step in steps" :key="step.id">
        
        <!-- Inline Step -->
        <InlineStep
          :step="step"
          :round="step.round"
          :total-rounds="step.totalRounds"
          :is-current="step.round === currentRound"
          :status="getStepStatus(step)"
        />
        
        <!-- waiting_for_user 类型处理 -->
        <template v-if="step.type === 'waiting_for_user'">
          
          <!-- InlineCandidate: options.length > 1 -->
          <template v-if="step.confirmationType === 'disambiguation' && step.options?.length > 1">
            <InlineCandidate
              v-for="candidate in step.options"
              :key="candidate.id"
              :candidate="candidate"
              :selected="selectedCandidate === candidate.id"
              @select="handleSelectCandidate(candidate.id)"
            />
            
            <!-- 按钮容器 -->
            <div class="action-buttons-inline">
              <button class="btn-sm btn-confirm" @click="handleConfirmSelect">确认选择</button>
              <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
            </div>
          </template>
          
          <!-- CompactConfirmSummary: confirmation -->
          <template v-else-if="step.confirmationType === 'confirmation'">
            <CompactConfirmSummary
              :round="step.round"
              :title="step.title"
              :params="step.params"
              :risk-level="step.riskLevel"
              :status="step.confirmStatus"
              @confirm="handleConfirm"
              @cancel="handleCancel"
            />
          </template>
          
          <!-- CompactInfoGap: info_gap -->
          <template v-else-if="step.confirmationType === 'info_gap'">
            <CompactInfoGap
              :round="step.round"
              :title="step.title"
              :filled-params="step.filledParams"
              :missing-field="step.missingField"
              @submit="handleSubmit"
              @cancel="handleCancel"
            />
          </template>
        </template>
      </template>
    </div>
  </div>
</template>
```

**CSS 规范**：
```scss
.expanded-view {
  max-height: 280px;           // V2: 280px
  overflow-y: auto;
}

.expand-header {
  padding: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: $wolf-text-tertiary;
  font-size: 12px;
  cursor: pointer;
  background: $wolf-bg-hover;
}

.expand-header:hover {
  background: $wolf-bg-inline-hover;
}

.expanded-content {
  padding: 8px 0;
}

.action-buttons-inline {
  padding: 4px 12px;
  margin-top: 4px;
  display: flex;
  gap: 8px;
}
```

---

## 📐 第四节：组件整合方式

### 4.1 CompactExecutionLog.vue（容器组件重写）

**Props**：
```typescript
interface CompactExecutionLogProps {
  steps: ExecutionStep[]           // 执行步骤数组
  currentRound?: number            // 当前轮次
  totalRounds?: number             // 总轮次
  status: 'empty' | 'loading' | 'success' | 'error' | 'partial'
  autoCollapse?: boolean           // 自动收起（默认 true）
  autoCollapseDelay?: number       // 自动收起延迟（默认 3000ms）
}
```

**模板结构**：
```vue
<template>
  <div class="agent-log">
    <!-- 智能边界线 -->
    <SmartBoundaryLine :status="boundaryStatus" />
    
    <!-- 空状态 -->
    <EmptyState v-if="steps.length === 0" compact />
    
    <!-- 收起状态 -->
    <CollapsedView 
      v-else-if="!expanded"
      :round="currentRound"
      :total-rounds="totalRounds"
      :status="currentStatus"
      :step-text="currentStepText"
      @click="toggleExpand"
    />
    
    <!-- 展开状态 -->
    <ExpandedView
      v-else
      :steps="steps"
      :current-round="currentRound"
      @collapse="toggleExpand"
      @confirm="handleConfirm"
      @cancel="handleCancel"
      @submit="handleSubmit"
    />
  </div>
</template>
```

**核心逻辑**：
```typescript
// 自动收起逻辑（执行完成后 3 秒自动收起）
const autoCollapseTimer = ref<number | null>(null)

const startAutoCollapse = () => {
  if (props.autoCollapse && props.status === 'success') {
    autoCollapseTimer.value = window.setTimeout(() => {
      expanded.value = false
    }, props.autoCollapseDelay)
  }
}

const cancelAutoCollapse = () => {
  if (autoCollapseTimer.value) {
    window.clearTimeout(autoCollapseTimer.value)
    autoCollapseTimer.value = null
  }
}

// 键盘导航
const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'Enter':
    case 'Space':
      toggleExpand()
      event.preventDefault()
      break
    case 'Escape':
      if (expanded.value) {
        toggleExpand()
        event.preventDefault()
      }
      break
  }
}
```

---

## 📐 第五节：测试策略

### 5.1 组件测试覆盖

| 组件 | 测试文件 | 测试重点 |
|------|----------|----------|
| InlineStep.vue | InlineStep.test.ts | Round Badge、状态颜色、inline 文本 |
| InlineCandidate.vue | InlineCandidate.test.ts | Radio 选择、hover tooltip、键盘导航 |
| HoverPreviewTooltip.vue | HoverPreviewTooltip.test.ts | hover 显示/隐藏 |
| CompactConfirmSummary.vue | CompactConfirmSummary.test.ts | Progressive Disclosure、风险等级 |
| CompactInfoGap.vue | CompactInfoGap.test.ts | inline input、missing field |
| CollapsedView.vue | CollapsedView.test.ts | 36px 高度、键盘导航 |
| ExpandedView.vue | ExpandedView.test.ts | 组件整合、max-height 280px |
| CompactExecutionLog.vue | CompactExecutionLog.test.ts | 展开/收切、自动收起、空状态 |

### 5.2 E2E 测试场景

- 基础状态：空状态、收起状态（36px）、展开状态
- 交互测试：展开/收切、InlineCandidate 选择、Progressive Disclosure
- 自动收起：执行完成后 3 秒自动收起
- 键盘导航：Enter 展开、Escape 收起

### 5.3 无障碍测试

- ARIA 属性：role="radio"、aria-checked、aria-expanded
- 键盘导航：Tab、Enter、Space、Escape、↑↓←→
- prefers-reduced-motion：动画禁用测试

---

## 📐 第六节：后端 API 调整需求

### 6.1 必须调整项（P0）

#### SSE waiting_for_user 事件调整

**文件**: `CRM-Server/app/services/langgraph/sse_wrapper.py`

**当前**：
```python
def build_waiting_for_user_event(
    question: str,
    options: Optional[List[str]] = None,
    missing_fields: Optional[List[str]] = None,
    field_options: Optional[Dict[str, Any]] = None,
) -> str:
    data = {
        "question": question,
        "options": options or [],
        "missing_fields": missing_fields or [],
        "field_options": field_options or {},
    }
    return build_sse_event(SSE_EVENT_TYPES["WAITING_FOR_USER"], data)
```

**调整后（V2）**：
```python
def build_waiting_for_user_event(
    question: str,
    confirmationType: str,  # ← 新增："disambiguation" | "confirmation" | "info_gap"
    options: Optional[List[Dict[str, Any]]] = None,  # ← 改为 Dict 格式
    missing_fields: Optional[List[str]] = None,
    field_options: Optional[Dict[str, Any]] = None,
    riskLevel: Optional[str] = None,  # ← 新增："low" | "medium" | "high"
    params: Optional[Dict[str, Any]] = None,  # ← 新增：当前操作参数
) -> str:
    data = {
        "question": question,
        "confirmationType": confirmationType,
        "options": options or [],
        "missing_fields": missing_fields or [],
        "field_options": field_options or {},
        "riskLevel": riskLevel,
        "params": params,
    }
    return build_sse_event(SSE_EVENT_TYPES["WAITING_FOR_USER"], data)
```

---

#### EntityCandidate 数据结构调整

**文件**: `CRM-Server/app/services/langgraph/state.py`

**当前**：
```python
class EntityCandidate(TypedDict):
    id: int
    name: str
    hint: str
    matched_by: str
    entity_type: str
```

**调整后（V2）**：
```python
class EntityCandidate(TypedDict):
    id: int
    name: str
    hint: str
    matched_by: str
    entity_type: str
    # ← 新增字段（用于 Inline 显示）
    industry: Optional[str]       # 行业（用于 Inline: "金融")
    status: Optional[str]         # 状态（用于 Inline: "活跃")
    amount: Optional[float]       # 金额（用于 Inline: "¥50万")
    stage: Optional[str]          # 阶段（用于 Inline: "商务谈判")
    # ← 格式化好的 Inline 文本（后端生成）
    entity_info_inline: Optional[str]  # 示例："ID:16 · 金融 · 活跃"
    # ← Hover Tooltip 详情
    entity_info_detail: Optional[Dict[str, Any]]  # 完整详情
```

---

### 6.2 建议调整项（P1/P2）

#### SSE tool_call/tool_result 事件调整

**文件**: `CRM-Server/app/services/langgraph/sse_wrapper.py`

**tool_call 调整**：
```python
def build_tool_call_event(
    tool: str,
    params: Optional[Dict[str, Any]] = None,
    thinking: Optional[str] = None  # ← 新增：AI 推理过程
) -> str:
    return build_sse_event(
        SSE_EVENT_TYPES["TOOL_CALL"],
        {
            "tool": tool,
            "params": params or {},
            "thinking": thinking  # ← 用于 ThinkingBubble
        }
    )
```

**tool_result 调整**：
```python
def build_tool_result_event(
    tool: str,
    result: Dict[str, Any],
    summary: Optional[str] = None  # ← 新增：业务化结果摘要
) -> str:
    display_result = filter_result_for_display(result)
    return build_sse_event(
        SSE_EVENT_TYPES["TOOL_RESULT"],
        {
            "tool": tool,
            "result": display_result,
            "summary": summary  # ← 示例："找到 1 个客户：光大证券"
        }
    )
```

---

#### ExecutionStepSchema 补充字段

**文件**: `CRM-Server/app/schemas/ai_conversation.py`

**调整后（V2）**：
```python
class ExecutionStepSchema(BaseModel):
    id: str
    type: ExecutionStepType
    title: str
    description: Optional[str] = None
    timestamp: str
    round: Optional[int] = None
    tool: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[Any] = None
    success: Optional[bool] = None
    error: Optional[str] = None
    businessParams: Optional[str] = None
    # ← 新增 V2 字段
    inline_text: Optional[str] = None  # Inline 显示文本（后端生成）
    thinking: Optional[str] = None      # AI 推理过程
    summary: Optional[str] = None      # 业务化结果摘要
    # ← Progressive Disclosure 两层数据
    summary_params: Optional[Dict[str, str]] = None   # 摘要参数
    detail_params: Optional[Dict[str, Any]] = None    # 详情参数
    # ← waiting_for_user 专属字段
    confirmationType: Optional[str] = None  # "disambiguation" | "confirmation" | "info_gap"
    riskLevel: Optional[str] = None         # "low" | "medium" | "high"
    options: Optional[List[Dict[str, Any]]] = None  # 候选列表
```

---

## 📋 实施清单

### 前端调整

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | 新建 InlineStep.vue | P0 | 待实施 |
| 2 | 新建 InlineCandidate.vue | P0 | 待实施 |
| 3 | 新建 HoverPreviewTooltip.vue | P0 | 待实施 |
| 4 | 新建 CompactConfirmSummary.vue | P0 | 待实施 |
| 5 | 新建 CompactInfoGap.vue | P1 | 待实施 |
| 6 | 重写 CompactExecutionLog.vue | P0 | 待实施 |
| 7 | 重写 CollapsedView.vue | P0 | 待实施 |
| 8 | 重写 ExpandedView.vue | P0 | 待实施 |
| 9 | 删除 StatusCard.vue, PreviewCard.vue, PreviewField.vue | P0 | 待实施 |
| 10 | 调整 EmptyState.vue 高度 | P1 | 待实施 |
| 11 | 调整 ThinkingBubble.vue CSS | P1 | 待实施 |
| 12 | 更新测试文件 | P1 | 待实施 |

### 后端调整

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | SSE waiting_for_user 补充 confirmationType/riskLevel/params | P0 | 待实施 |
| 2 | EntityCandidate 补充 industry/status/amount/entity_info_inline | P0 | 待实施 |
| 3 | SSE tool_call 补充 thinking 字段 | P1 | 待实施 |
| 4 | SSE tool_result 补充 summary 字段 | P1 | 待实施 |
| 5 | ExecutionStepSchema 补充 inline_text/summary_params/detail_params | P2 | 待实施 |

---

## 📊 设计决策记录

| 决策项 | 选择 | 原因 |
|--------|------|------|
| **组件命名** | 无 V2 后缀，直接替换原组件 | 避免混淆，简洁 |
| **Inline 文本生成位置** | 后端生成（推荐）+ 前端后备 | 后端有业务上下文，确保一致性 |
| **括号格式实现** | CSS ::before/::after | 纯样式，便于修改 |
| **收起按钮位置** | 展开状态顶部 `[↑ 收起]` | 匹配设计文档第 193 行 |
| **Progressive Disclosure** | 点击展开详情 | 减少默认空间占用 |

---

## 🔗 关联文档

| 文档 | 关系 | 位置 |
|------|------|------|
| AI-THINKING-PROCESS-MOCKUP-V2.html | V2 Mockup 参考 | `CRM-Docs/standards/` |
| AI-THINKING-PROCESS-DESIGN.md | 父设计（紧凑轨迹方案） | `CRM-Docs/system/design/` |
| AI-HUMAN-IN-THE-LOOP-DESIGN.md | 子设计（人机协同节点） | `CRM-Docs/plans/` |

---

**文档完成时间**: 2026-06-25
**设计版本**: V2 (10/10 紧凑版)
**实施状态**: 待实施
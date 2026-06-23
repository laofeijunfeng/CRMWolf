---
status: archived
created: 2026-06-12
updated: 2026-06-23
archived_date: 2026-06-23
related_requirements: ../requirements/AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-REQUIREMENTS.md
related_pr: -
---

# AI Assistant Sidebar UI 优化实施计划

> **状态**：completed ✅ | 创建日期：2026-06-12 | 完成日期：2026-06-14
> 配套需求：[AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-REQUIREMENTS.md](../requirements/AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-REQUIREMENTS.md)

---

## 一、项目概览

### 1.1 目标

优化 AI Assistant Sidebar 的交互体验和视觉样式：

| 目标 | 说明 |
|------|------|
| **交互优化** | 状态驱动 UI，主输入框按需显示 |
| **样式优化** | 参考 ChatGPT，现代简洁设计 |
| **体验提升** | 明确的操作入口，Non-blocking 交互 |

### 1.2 核心收益

| 收益 | 说明 |
|------|------|
| 空间利用率提升 | 主输入框隐藏后，Sidebar 专注进度 |
| 用户心理模型匹配 | 85%场景用户只需输入一次 |
| 视觉体验升级 | 对标业界最佳实践 |
| Non-blocking 强化 | 状态驱动，信息密度最优 |

---

## 二、实施阶段概览

| Phase | 内容 | 工作量 | 优先级 | 风险 |
|-------|------|--------|--------|------|
| **Phase 0** | 状态机扩展 + 状态定义 | 1天 | P0 | 低 |
| **Phase 1** | 主输入框状态驱动显示 | 2天 | P0 | 低 |
| **Phase 2** | 操作按钮实现（新对话/停止） | 1天 | P1 | 低 |
| **Phase 3** | 输入框样式优化 | 2天 | P1 | 中 |
| **Phase 4** | 响应式布局适配 | 1天 | P2 | 低 |
| **Phase 5** | 测试验证 + 性能优化 | 1天 | P0 | 低 |

**总工作量**：**约 6天**

---

## 三、详细实施步骤

### Phase 0：状态机扩展 + 状态定义（1天）

#### 任务清单

| 任务 | 说明 | 输出 |
|------|------|------|
| 状态定义 | 扩展 SidebarState 类型定义 | TypeScript 类型 |
| 状态映射 | 定义状态与 UI 的映射关系 | 状态映射表 |
| 状态转换逻辑 | 定义合法的状态转换规则 | 状态转换函数 |

#### 技术方案

**状态定义**：

```typescript
// types/sidebar.ts

export enum SidebarState {
  IDLE = 'IDLE',                     // 空闲，显示主输入框
  COLLECTING = 'COLLECTING',         // 收集意图
  RESOLVING_ENTITY = 'RESOLVING_ENTITY', // 解析实体
  RESOLVING_AMBIGUITY = 'RESOLVING_AMBIGUITY', // 消解歧义
  PREVIEW = 'PREVIEW',               // 预览确认
  EXECUTING = 'EXECUTING',           // 执行中
  COMPLETED = 'COMPLETED'            // 完成
}

// 状态与 UI 映射
export const StateUIMap: Record<SidebarState, {
  showInputBox: boolean
  showSidebar: boolean
  showStopButton: boolean
  showNewChatButton: boolean
}> = {
  [SidebarState.IDLE]: {
    showInputBox: true,
    showSidebar: false,
    showStopButton: false,
    showNewChatButton: false
  },
  [SidebarState.COLLECTING]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: false,
    showNewChatButton: false
  },
  [SidebarState.EXECUTING]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: true,
    showNewChatButton: false
  },
  [SidebarState.COMPLETED]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: false,
    showNewChatButton: true
  },
  // ... 其他状态
}
```

---

### Phase 1：主输入框状态驱动显示（2天）

#### 任务清单

| 任务 | 说明 | 输出 |
|------|------|------|
| MagicWandDialog.vue 改造 | 状态驱动输入框显示 | Vue 组件 |
| Sidebar.vue 改造 | 状态驱动 Sidebar 显示 | Vue 组件 |
| 状态转换测试 | 测试所有状态转换 | 单元测试 |

#### 技术方案

**MagicWandDialog.vue 改造**：

```vue
<!-- CRM-Client/src/components/MagicWandDialog.vue -->

<template>
  <div class="magic-wand-container">
    <!-- 主输入框：仅在 IDLE 状态显示 -->
    <InputBox
      v-if="sidebarState === SidebarState.IDLE"
      @submit="handleSubmit"
      class="input-box-centered"
    />

    <!-- Sidebar：在非 IDLE 状态显示 -->
    <Sidebar
      v-if="sidebarState !== SidebarState.IDLE"
      :state="sidebarState"
    >
      <!-- Mini-map 进度 -->
      <MiniMap v-if="showMiniMap" :steps="currentSteps" />

      <!-- 实体选择界面（歧义消解） -->
      <EntitySelect
        v-if="sidebarState === SidebarState.RESOLVING_AMBIGUITY"
        :entities="ambiguousEntities"
        @select="handleEntitySelect"
      />

      <!-- Preview 详情 -->
      <PreviewDetails
        v-if="sidebarState === SidebarState.PREVIEW"
        :preview="currentPreview"
        @confirm="handleConfirm"
        @modify="handleModify"
      />

      <!-- 操作按钮 -->
      <ActionButtons
        :showStop="stateUIMap.showStopButton"
        :showNewChat="stateUIMap.showNewChatButton"
        @stop="handleStop"
        @newChat="handleNewChat"
      />
    </Sidebar>
  </div>
</template>

<script setup lang="ts">
import { SidebarState, StateUIMap } from '@/types/sidebar'

const sidebarState = ref<SidebarState>(SidebarState.IDLE)
const stateUIMap = computed(() => StateUIMap[sidebarState.value])

const handleStop = () => {
  // 中断当前操作
  interruptCurrentOperation()
  sidebarState.value = SidebarState.IDLE
}

const handleNewChat = () => {
  // 清空对话，返回 IDLE
  clearConversation()
  sidebarState.value = SidebarState.IDLE
}
</script>
```

---

### Phase 2：操作按钮实现（1天）

#### 任务清单

| 任务 | 说明 | 输出 |
|------|------|------|
| ActionButtons.vue 实现 | 停止/新对话按钮组件 | Vue 组件 |
| 按钮样式设计 | 符合 Design Token | SCSS 样式 |
| 按钮交互逻辑 | 点击后状态转换 | 事件处理 |

#### 技术方案

**ActionButtons.vue 实现**：

```vue
<!-- CRM-Client/src/components/sidebar/ActionButtons.vue -->

<template>
  <div class="action-buttons">
    <!-- 停止操作按钮 -->
    <el-button
      v-if="showStop"
      type="danger"
      size="small"
      @click="emit('stop')"
    >
      停止操作
    </el-button>

    <!-- 新对话按钮 -->
    <el-button
      v-if="showNewChat"
      type="primary"
      size="small"
      @click="emit('newChat')"
    >
      新对话
    </el-button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  showStop: boolean
  showNewChat: boolean
}>()

const emit = defineEmits<{
  (e: 'stop'): void
  (e: 'newChat'): void
}>()
</script>

<style scoped lang="scss">
.action-buttons {
  padding: $wolf-card-padding;
  display: flex;
  justify-content: center;
  gap: $wolf-spacing-md;
}
</style>
```

---

### Phase 3：输入框样式优化（2天）

#### 任务清单

| 任务 | 说明 | 输出 |
|------|------|------|
| InputBox.vue 样式改造 | 参考 ChatGPT 设计 | Vue 组件 + SCSS |
| 提示文本优化 | 简洁文案 + 动态提示 | 文案 + 样式 |
| Design Token 引用 | 使用现有 Design Token | SCSS 变量 |

#### 技术方案

**InputBox.vue 样式改造**：

```vue
<!-- CRM-Client/src/components/InputBox.vue -->

<template>
  <div class="input-container">
    <div class="input-box" :class="{ focused: isFocused }">
      <el-input
        v-model="inputValue"
        :placeholder="placeholderText"
        @focus="handleFocus"
        @blur="handleBlur"
        @keyup.enter="handleSubmit"
        class="input-field"
      />

      <!-- 提示文本（聚焦时动态显示） -->
      <div v-if="showHint" class="input-hint">
        {{ hintText }}
      </div>

      <!-- 发送按钮 -->
      <el-button
        type="primary"
        size="small"
        @click="handleSubmit"
        class="send-button"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
const inputValue = ref('')
const isFocused = ref(false)

const placeholderText = computed(() =>
  inputValue.value ? '' : '有什么我可以帮助你的？'
)

const hintText = computed(() =>
  '描述你想做的操作，比如：创建客户张三，电话13812345678'
)

const showHint = computed(() => isFocused.value && !inputValue.value)
</script>

<style scoped lang="scss">
.input-container {
  max-width: 800px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.input-box {
  border-radius: $wolf-radius-lg; // 12px
  background: $wolf-bg-hover;
  border: 1px solid $wolf-border-light;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  padding: $wolf-input-padding; // 16px 12px
  transition: all 0.3s ease;

  &.focused {
    border-color: $wolf-primary;
    box-shadow: 0 0 0 2px rgba($wolf-primary, 0.1);
  }
}

.input-field {
  width: 100%;

  :deep(.el-input__inner) {
    border: none;
    background: transparent;
    font-size: 14px;
    color: $wolf-text-primary;

    &:placeholder {
      color: $wolf-text-tertiary;
      text-align: center;
    }
  }
}

.input-hint {
  margin-top: $wolf-spacing-sm;
  color: $wolf-text-tertiary;
  font-size: 13px;
  text-align: center;
}

.send-button {
  margin-top: $wolf-spacing-sm;
}

// 响应式
@media (max-width: 768px) {
  .input-container {
    max-width: 100%;
    padding: $wolf-spacing-md;
  }
}
</style>
```

---

### Phase 4：响应式布局适配（1天）

#### 任务清单

| 任务 | 说明 | 输出 |
|------|------|------|
| 输入框响应式 | 大屏居中，中屏全宽 | CSS Media Query |
| Sidebar 响应式 | 小屏时 Sidebar 全宽 | CSS Media Query |
| 测试响应式 | 不同屏幕尺寸测试 | 手动测试 |

#### 技术方案

**响应式样式**：

```scss
// 输入框响应式
@media (min-width: 1200px) {
  .input-container {
    max-width: 800px;
  }
}

@media (max-width: 1199px) and (min-width: 768px) {
  .input-container {
    max-width: 100%;
  }
}

@media (max-width: 767px) {
  .input-container {
    max-width: 100%;
    padding: $wolf-spacing-md;
  }

  .input-box {
    border-radius: $wolf-radius-md; // 8px（小屏圆角减小）
  }
}

// Sidebar 响应式
@media (max-width: 767px) {
  .sidebar {
    width: 100%;
    position: fixed;
    bottom: 0;
    left: 0;
    max-height: 50vh;
    overflow-y: auto;
  }
}
```

---

### Phase 5：测试验证 + 性能优化（1天）

#### 任务清单

| 任务 | 说明 | 输出 |
|------|------|------|
| 单元测试 | 状态转换测试 | Vitest 测试文件 |
| 集成测试 | UI交互测试 | 手动测试 |
| 性能优化 | 状态转换动画优化 | 性能优化 |

#### 验收标准

**功能验收**：

| 验收项 | 标准 |
|--------|------|
| 主输入框状态驱动 | IDLE显示，非IDLE隐藏 ✅ |
| 新对话按钮 | COMPLETED显示，点击返回IDLE ✅ |
| 停止操作按钮 | EXECUTING显示，点击中断 ✅ |
| 输入框样式 | 圆角12px，浅色背景 ✅ |

**性能验收**：

| 验收项 | 标准 |
|--------|------|
| 状态转换响应 | < 100ms ✅ |
| 动画平滑 | 300ms过渡 ✅ |

---

## 四、技术难点与解决方案

### 难点 1：状态机集成复杂度

**问题**：现有 AI GLUE 状态机与新 UI 状态映射复杂

**解决方案**：
- ✅ 扩展现有状态机，不新建状态机
- ✅ 状态映射表统一管理
- ✅ 状态转换逻辑集中处理

---

### 难点 2：动画过渡性能

**问题**：输入框显示/隐藏动画可能闪烁

**解决方案**：
- ✅ 使用 Vue Transition 组件
- ✅ CSS transition: all 0.3s ease
- ✅ 避免白屏，使用 opacity + transform

---

### 难点 3：响应式布局兼容

**问题**：小屏时 Sidebar 与输入框布局冲突

**解决方案**：
- ✅ 小屏时 Sidebar 固定底部，半屏显示
- ✅ 输入框响应式调整宽度
- ✅ Design Token 保证一致性

---

## 五、风险分析

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 状态转换逻辑错误 | 中 | 高 | 充分的单元测试 |
| 动画性能问题 | 低 | 中 | CSS硬件加速 |
| 响应式兼容问题 | 低 | 中 | 多设备测试 |
| 输入框样式偏差 | 低 | 低 | 参考 ChatGPT 原型 |

---

## 六、实施时间表

| Phase | 预计开始 | 预计完成 | 实际完成 | 负责人 |
|-------|----------|----------|----------|--------|
| **Phase 0** | Day 1 | Day 1 | **2026-06-12** ✅ | 前端团队 |
| **Phase 1** | Day 2 | Day 3 | **2026-06-14** ✅ | 前端团队 |
| **Phase 2** | Day 4 | Day 4 | **2026-06-14** ✅ | 前端团队 |
| **Phase 3** | Day 5 | Day 6 | **2026-06-14** ✅ | 前端团队 |
| **Phase 4** | Day 7 | Day 7 | **2026-06-14** ✅ | 前端团队 |
| **Phase 5** | Day 8 | Day 8 | **2026-06-14** ✅ | 前端团队 |

**总工期**：**约 6工作日**

---

## 七、相关文档

| 文档 | 说明 |
|------|------|
| [AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-REQUIREMENTS.md](../requirements/AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-REQUIREMENTS.md) | 配套需求文档 |
| [DESIGN-PRINCIPLES.md](../../CRM-Client/docs/DESIGN-PRINCIPLES.md) | UI设计原则 |
| [DESIGN-QUICK-REF.md](../../CRM-Client/docs/DESIGN-QUICK-REF.md) | Design Token速查 |
| [variables.scss](../../CRM-Client/src/styles/variables.scss) | Design Token定义 |

---

**实施计划状态**：draft（待评审）

**下一步**：评审通过后，开始 Phase 0 实施
---
status: active
created: 2026-06-12
updated: 2026-06-12
related_plan: ../plans/AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-PLAN.md
related_pr: -
---

# 需求文档：AI Assistant Sidebar UI 优化

| 文档版本 | V 1.0 |
| :--- | :--- |
| **项目名称** | AI Assistant Sidebar 交互与样式优化 |
| **关键词** | 状态驱动 UI, 输入框优化, ChatGPT样式, Non-blocking |
| **更新日期** | 2026-06-12 |

---

## 一、需求背景 (Context & Problem Statement)

### 1.1 现状

基于 V3.1 的 Inline Interaction 实施成果，系统已具备：
- **Sidebar 侧边栏**：替代 Modal 弹窗，Non-blocking 交互
- **Mini-map 进度**：多步骤可视化
- **撤销机制**：Undo Service + Undo Handlers
- **确认机制**：ConfirmationCard + UndoToast

当前 Sidebar 结构：

```
┌─────────────────────────────┐
│  Sidebar                    │
│  [主输入框] ← 常驻显示        │
│                             │
│  Mini-map 进度              │
│  Action 详情                │
│  确认按钮                    │
└─────────────────────────────┘
```

### 1.2 核心问题

#### 问题 1：主输入框常驻显示不合理

| 问题表现 | 业务场景分析 |
|----------|--------------|
| **占用空间** | 主输入框占用 Sidebar 大量空间，进度展示受挤压 |
| **干扰用户** | 对话过程中输入框一直显示，用户误以为可以输入 |
| **违反心理模型** | 60%场景用户只需输入一次，之后等待结果 |

**用户反馈**：

> "这个输入框在整个对话过程中一直常驻显示没有必要，对话过程中似乎没有必要一直显示；如果中途有需要补充信息，那过程中是有输入框让我补充信息的"

**业务场景统计**：

| 场景类型 | 占比 | 交互轮数 | 主输入框需求 |
|----------|------|----------|--------------|
| 单意图操作 | 60% | 1轮 | ✅ 仅初始时需要 |
| 多意图操作 | 20% | 1轮 | ✅ 仅初始时需要 |
| 歧义消解 | 10% | 2轮 | ✅ 专用选择界面 |
| 参数补充 | 5% | 2轮 | ✅ 专用表单 |
| 撤销重试 | 5% | 2-3轮 | ✅ 重新开始 |

**结论**：**85%场景主输入框只在初始时需要**，常驻显示不合理。

---

#### 问题 2：输入框样式不美观

| 问题表现 | 用户期望 |
|----------|----------|
| **样式简陋** | 当前输入框缺乏现代设计感 |
| **与业界产品差距大** | ChatGPT、Claude 输入框设计成熟美观 |
| **影响用户体验** | 第一印象不佳，降低用户信任度 |

---

### 1.3 机会

通过优化 Sidebar 交互和样式：

- **提升空间利用率**：隐藏主输入框，专注进度展示
- **符合用户心理模型**：匹配 85%场景的交互需求
- **对标业界最佳实践**：参考 ChatGPT 等成熟产品设计
- **强化 Non-blocking 理念**：状态驱动 UI，信息密度最优

---

## 二、核心原则 (Core Principles)

### 2.1 状态驱动 UI

**原则**：UI 根据对话状态动态调整，匹配当前阶段的信息需求

**对标**：GitHub Copilot（状态驱动 UI）

**实施要点**：
- IDLE 状态：显示主输入框，隐藏 Sidebar
- EXECUTING 状态：隐藏主输入框，显示 Sidebar（进度）
- 其他状态：隐藏主输入框，显示专用 UI

---

### 2.2 任务导向交互

**原则**：一次任务流程中，用户输入一次，等待结果

**对标**：CRM 业务场景（单次操作流程）

**实施要点**：
- 主输入框仅在初始输入时显示
- 中途补充信息使用专用 UI（选择、表单）
- 明确的"重新开始"入口

---

### 2.3 Non-blocking 原则

**原则**：AI 执行过程中，用户可自由操作页面

**对标**：Inline Interaction 设计理念

**实施要点**：
- Sidebar 不阻断用户浏览
- 明确的"停止操作"按钮
- UndoToast 提示撤销机会

---

### 2.4 现代设计美学

**原则**：输入框样式对标业界最佳实践，简洁美观

**对标**：ChatGPT、Claude、Copilot

**实施要点**：
- 简洁的输入框设计
- 清晰的提示文本
- 合理的尺寸和间距

---

## 三、需求定义 (Requirements)

### 3.1 UI 交互优化需求

#### REQ-UI-01：状态驱动主输入框显示

**需求描述**：主输入框根据对话状态动态显示/隐藏

**状态转换表**：

| 状态 | 主输入框 | Sidebar | 触发条件 |
|------|----------|---------|----------|
| **IDLE** | ✅ 显示 | ❌ 隐藏 | 初始状态 / 点击"新对话" |
| **COLLECTING** | ❌ 隐藏 | ✅ 显示 | 用户提交意图 |
| **RESOLVING_ENTITY** | ❌ 隐藏 | ✅ 显示 | AI 开始执行 |
| **RESOLVING_AMBIGUITY** | ❌ 隐藏 | ✅ 专用选择界面 | 发现歧义 |
| **PREVIEW** | ❌ 隐藏 | ✅ Preview详情 | Preview生成 |
| **EXECUTING** | ❌ 隐藏 | ✅ 执行进度 | 用户确认执行 |
| **COMPLETED** | ❌ 隐藏 | ✅ UndoToast | 操作完成 |

**验收标准**：
- ✅ IDLE 状态：主输入框全宽显示，Sidebar 隐藏
- ✅ 非 IDLE 状态：主输入框隐藏，Sidebar 显示
- ✅ 状态转换流畅，无闪烁

---

#### REQ-UI-02：明确的重新开始入口

**需求描述**：提供明确的"新对话"按钮，用户可重新开始

**UI 设计**：

```
Sidebar 底部：

┌───────────────────────────┐
│  ✅ 操作完成               │
│                           │
│  UndoToast                │
│  "30秒内可撤销"            │
│                           │
│  [─────────────────────]  │ ← 新对话按钮
│  [新对话]                  │
└───────────────────────────┘
```

**交互逻辑**：
- 点击"新对话" → 清空对话历史 → IDLE 状态 → 显示主输入框

**验收标准**：
- ✅ COMPLETED 状态：Sidebar 底部显示"新对话"按钮
- ✅ 点击后：清空对话，返回 IDLE，显示主输入框

---

#### REQ-UI-03：明确的停止操作入口

**需求描述**：提供"停止操作"按钮，用户可中断当前流程

**UI 设计**：

```
Sidebar 底部：

┌───────────────────────────┐
│  Mini-map 进度             │
│                           │
│  当前操作详情              │
│                           │
│  [─────────────────────]  │ ← 停止操作按钮
│  [停止操作]                │
└───────────────────────────┘
```

**交互逻辑**：
- 点击"停止操作" → 中断当前操作 → IDLE 状态 → 显示主输入框

**验收标准**：
- ✅ EXECUTING/PREVIEW 状态：Sidebar 底部显示"停止操作"按钮
- ✅ 点击后：中断操作，返回 IDLE，显示主输入框

---

#### REQ-UI-04：专用补充信息 UI

**需求描述**：中途补充信息使用专用 UI，不使用主输入框

**UI 设计**：

**歧义消解**（实体选择界面）：

```
┌───────────────────────────┐
│  ⚠️ 需要选择               │
│                           │
│  发现2个"张三"             │
│                           │
│  ○ 张三 (客户A)            │ ← 选择界面
│  ○ 张三 (客户B)            │
│                           │
│  [确认选择]                │
└───────────────────────────┘
```

**参数补充**（参数表单）：

```
┌───────────────────────────┐
│  ⚠️ 需要补充参数           │
│                           │
│  商机名称：[________]      │ ← 参数表单
│  预计金额：[________]      │
│                           │
│  [提交]                    │
└───────────────────────────┘
```

**验收标准**：
- ✅ RESOLVING_AMBIGUITY 状态：显示选择界面，主输入框隐藏
- ✅ 参数缺失：显示参数表单，主输入框隐藏
- ✅ 不使用主输入框补充信息

---

### 3.2 输入框样式优化需求

#### REQ-STYLE-01：参考 ChatGPT 输入框设计

**需求描述**：主输入框样式参考 ChatGPT 等成熟产品

**ChatGPT 输入框分析**：

| 设计元素 | 特点 |
|----------|------|
| **整体风格** | 简洁、现代、无边框感 |
| **输入区域** | 圆角矩形，浅色背景，微阴影 |
| **提示文本** | 居中显示，灰色字体，简洁文案 |
| **按钮位置** | 右侧或底部，紧凑排列 |
| **响应式** | 自动调整宽度，最大宽度限制 |

**设计目标**：

```
┌─────────────────────────────────────┐
│                                     │
│  ┌───────────────────────────────┐  │
│  │                               │  │ ← 输入框区域
│  │  有什么我可以帮助你的？        │  │ ← 提示文本（居中）
│  │                               │  │
│  └───────────────────────────────┘  │
│                                     │
│  [附件] [发送]                       │ ← 底部按钮（可选）
│                                     │
└─────────────────────────────────────┘
```

**验收标准**：
- ✅ 输入框：圆角矩形（border-radius: 12px），浅色背景
- ✅ 提示文本：居中显示，灰色字体（#9CA3AF），简洁文案
- ✅ 微阴影：box-shadow: 0 1px 2px rgba(0,0,0,0.1)
- ✅ 无边框感：border: 1px solid #E5E7EB

---

#### REQ-STYLE-02：提示文本优化

**需求描述**：提示文本简洁、引导性强

**提示文本文案**：

| 场景 | 提示文本 |
|------|----------|
| **默认** | "有什么我可以帮助你的？" |
| **聚焦** | "描述你想做的操作，比如：创建客户张三，电话13812345678" |
| **空输入提交** | "请输入你的操作意图" |

**验收标准**：
- ✅ 默认提示：居中显示，灰色字体
- ✅ 聚焦提示：输入框底部显示，动态提示
- ✅ 文案简洁，不超过50字

---

#### REQ-STYLE-03：尺寸和间距优化

**需求描述**：输入框尺寸合理，间距符合 Design Token

**尺寸规范**：

| 元素 | 尺寸 |
|------|------|
| **输入框宽度** | 最大 800px（响应式） |
| **输入框高度** | 56px（单行）或动态（多行） |
| **内边距** | 16px（左右），12px（上下） |
| **外边距** | 24px（页面内边距） |
| **圆角** | 12px（border-radius-lg） |

**验收标准**：
- ✅ 输入框最大宽度 800px，响应式调整
- ✅ 内边距：引用 Design Token（$wolf-input-padding）
- ✅ 圆角：引用 Design Token（$wolf-radius-lg）

---

#### REQ-STYLE-04：响应式布局

**需求描述**：输入框在不同屏幕尺寸下自适应

**响应式规则**：

| 屏幕宽度 | 输入框宽度 |
|----------|------------|
| **> 1200px** | 800px（固定最大宽度） |
| **768-1200px** | 100%（容器宽度） |
| **< 768px** | 100%（全宽） |

**验收标准**：
- ✅ 大屏：输入框居中，最大宽度 800px
- ✅ 中屏：输入框占容器宽度 100%
- ✅ 小屏：输入框全宽显示

---

### 3.3 非功能性需求

#### REQ-NF-01：性能要求

**需求描述**：状态转换流畅，无闪烁

**性能指标**：
- ✅ 状态转换响应时间：< 100ms
- ✅ 输入框显示/隐藏动画：平滑过渡（300ms）
- ✅ 无白屏、无闪烁

---

#### REQ-NF-02：兼容性要求

**需求描述**：兼容主流浏览器

**浏览器支持**：
- ✅ Chrome 90+
- ✅ Safari 14+
- ✅ Firefox 88+
- ✅ Edge 90+

---

#### REQ-NF-03：可维护性要求

**需求描述**：代码结构清晰，易于维护

**实现要点**：
- ✅ 状态机驱动 UI（复用现有状态机）
- ✅ 输入框样式使用 Design Token
- ✅ 清晰的状态转换逻辑

---

## 四、技术实现要点 (Implementation Highlights)

### 4.1 状态驱动 UI 实现

**实现方案**：

```typescript
// MagicWandDialog.vue

<template>
  <!-- 主输入框：仅在 IDLE 状态显示 -->
  <div v-if="sidebarState === 'IDLE'" class="input-container">
    <InputBox @submit="handleSubmit" />
  </div>

  <!-- Sidebar：在非 IDLE 状态显示 -->
  <Sidebar v-if="sidebarState !== 'IDLE'" :state="sidebarState">
    <!-- Mini-map -->
    <MiniMap v-if="sidebarState === 'EXECUTING'" />

    <!-- 实体选择界面 -->
    <EntitySelect v-if="sidebarState === 'RESOLVING_AMBIGUITY'" />

    <!-- Preview 详情 -->
    <PreviewDetails v-if="sidebarState === 'PREVIEW'" />

    <!-- 操作按钮 -->
    <ActionButtons
      :showStop="sidebarState === 'EXECUTING'"
      :showNewChat="sidebarState === 'COMPLETED'"
      @stop="handleStop"
      @newChat="handleNewChat"
    />
  </Sidebar>
</template>

<script setup lang="ts">
const sidebarState = ref<SidebarState>('IDLE')

const handleStop = () => {
  // 中断当前操作
  sidebarState.value = 'IDLE'
}

const handleNewChat = () => {
  // 清空对话，返回 IDLE
  clearConversation()
  sidebarState.value = 'IDLE'
}
</script>
```

---

### 4.2 输入框样式实现

**样式方案**：

```scss
// InputBox.vue

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

  &:focus-within {
    border-color: $wolf-primary;
    box-shadow: 0 0 0 2px rgba($wolf-primary, 0.1);
  }
}

.input-placeholder {
  color: $wolf-text-tertiary; // #9CA3AF
  text-align: center;
  font-size: 14px;
}

// 响应式
@media (max-width: 768px) {
  .input-container {
    max-width: 100%;
  }
}
```

---

### 4.3 状态转换逻辑

**状态机集成**：

```typescript
// 复用现有状态机（AI GLUE 状态机）

enum SidebarState {
  IDLE = 'IDLE',
  COLLECTING = 'COLLECTING',
  RESOLVING_ENTITY = 'RESOLVING_ENTITY',
  RESOLVING_AMBIGUITY = 'RESOLVING_AMBIGUITY',
  PREVIEW = 'PREVIEW',
  EXECUTING = 'EXECUTING',
  COMPLETED = 'COMPLETED'
}

// 状态转换映射
const stateTransitionMap = {
  'submit': 'COLLECTING',
  'start_executing': 'RESOLVING_ENTITY',
  'ambiguity_detected': 'RESOLVING_AMBIGUITY',
  'preview_generated': 'PREVIEW',
  'confirm': 'EXECUTING',
  'complete': 'COMPLETED',
  'stop': 'IDLE',
  'new_chat': 'IDLE'
}
```

---

## 五、验收标准 (Acceptance Criteria)

### 5.1 功能验收

| 验收项 | 标准 | 测试方法 |
|--------|------|----------|
| **主输入框状态驱动** | IDLE显示，非IDLE隐藏 | 状态转换测试 |
| **新对话按钮** | COMPLETED状态显示，点击返回IDLE | 点击测试 |
| **停止操作按钮** | EXECUTING状态显示，点击中断 | 点击测试 |
| **专用补充UI** | 不使用主输入框补充信息 | 补充信息测试 |

---

### 5.2 样式验收

| 验收项 | 标准 | 测试方法 |
|--------|------|----------|
| **输入框设计** | 圆角12px，浅色背景，微阴影 | 视觉检查 |
| **提示文本** | 居中，灰色字体，简洁文案 | 视觉检查 |
| **尺寸间距** | 最大800px，响应式调整 | 尺寸测量 |
| **响应式** | 大屏居中，中屏全宽 | 屏幕调整测试 |

---

### 5.3 性能验收

| 验收项 | 标准 | 测试方法 |
|--------|------|----------|
| **状态转换响应** | < 100ms | 性能测试 |
| **动画平滑** | 300ms过渡，无闪烁 | 视觉检查 |
| **无白屏** | 状态转换无空白 | 视觉检查 |

---

## 六、优先级定义

| 需求 | 优先级 | 说明 |
|------|--------|------|
| REQ-UI-01 | **P0** | 核心交互优化 |
| REQ-UI-02 | **P1** | 用户体验提升 |
| REQ-UI-03 | **P1** | 用户体验提升 |
| REQ-UI-04 | **P2** | 已有实现，保持 |
| REQ-STYLE-01 | **P1** | 核心样式优化 |
| REQ-STYLE-02 | **P2** | 文案优化 |
| REQ-STYLE-03 | **P2** | 尺寸细节 |
| REQ-STYLE-04 | **P2** | 响应式支持 |

---

## 七、遗留问题

| 问题 | 影响 | 处理建议 |
|------|------|----------|
| 多行输入支持 | 中 | 后续扩展输入框为多行 |
| 输入历史记录 | 低 | 后续增加历史记录功能 |
| 输入框自动完成 | 低 | 后续增加智能提示 |

---

## 八、相关文档

| 文档 | 说明 |
|------|------|
| [AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md](../archive/requirements/AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md) | Inline 交互原始需求（已归档） |
| [AI-AGENT-INLINE-INTERACTION-PLAN.md](../archive/plans/AI-AGENT-INLINE-INTERACTION-PLAN.md) | Inline 交互实施计划（已归档） |
| [DESIGN-PRINCIPLES.md](../../CRM-Client/docs/DESIGN-PRINCIPLES.md) | UI 设计原则 |
| [DESIGN-QUICK-REF.md](../../CRM-Client/docs/DESIGN-QUICK-REF.md) | Design Token 速查 |

---

**文档状态**：active（评审通过，待实施）

**下一步**：实施计划已创建，参见 `AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-PLAN.md`
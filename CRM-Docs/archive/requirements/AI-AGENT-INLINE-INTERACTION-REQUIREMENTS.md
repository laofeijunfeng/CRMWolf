---
status: completed
created: 2026-06-10
updated: 2026-06-10
related_plan: ../plans/AI-AGENT-INLINE-INTERACTION-PLAN.md
related_pr: -
---

# 需求文档：CRM Agent Inline 交互系统

> **状态：✅ 已实现** | 完成日期：2026-06-10

| 文档版本 | V 4.0 |
| :--- | :--- |
| **项目名称** | CRM 智能流程推进 Agent |
| **关键词** | Inline Actions, Sidebar, Non-blocking, Zero Friction |
| **更新日期** | 2026-06-10 |

---

## 一、需求背景 (Context & Problem Statement)

### 1.1 现状
基于 V3.1 的实施成果，系统已具备：
- **Workflow Orchestrator**：硬编码业务流程（赢单、转化）
- **Control Plane**：Redis Session、Guardrails、TraceId、资源隔离
- **撤销机制**：Undo Service + Undo Handlers + Undo API
- **确认机制**：ConfirmationCard（弹窗确认）+ UndoToast（撤销提示）

当前 UI 交互采用阻断式 Modal 弹窗，用户每次确认都需要：
1. 阅读弹窗内容
2. 点击确认按钮
3. 等待执行完成
4. 关闭弹窗或查看结果

### 1.2 核心问题

**交互摩擦**：
- Modal 弹窗阻断用户浏览客户详情
- 每次确认都需要切换上下文
- 复杂流程需要多次弹窗确认

**被动等待**：
- AI 作为"副驾驶"，被动等待用户输入
- 未能在用户浏览时主动展示流程进度

**信息分散**：
- 确认信息、执行进度、撤销入口分散在不同位置
- 缺乏全流程的宏观视图

### 1.3 解决思路

将现有 MagicWandDialog 从 **Modal 弹窗** 改造为 **Inline Sidebar**：
- 用户点击魔术棒 → 右侧滑出 Sidebar
- Sidebar 覆盖在页面上方，不阻断用户浏览左侧内容
- 确认改为 Inline Pill（一行简洁展示）
- 执行后 Undo Snackbar 出现在底部中央

**关键优势**：
- 改动范围最小（只改 MagicWandDialog）
- 用户可继续浏览客户详情
- 全流程进度一览无余
- 撤销入口统一在底部

---

## 二、核心原则 (Core Principles)

### 2.1 非阻断原则 (Non-blocking)
**用户不应被弹窗打断工作流。**

- Sidebar 覆盖在页面右侧，用户仍可浏览左侧
- Inline Pill 默认一行，不占据过多空间
- 执行完成后 Sidebar 可关闭或保留

### 2.2 渐进披露原则 (Progressive Disclosure)
**默认简洁，需要时可展开。**

- Inline Pill 默认显示摘要（一行）
- 点击"查看详情"展开完整参数
- Workflow Mini-map 默认折叠，可展开查看

### 2.3 可逆性原则 (Reversibility)
**任何操作必须可撤销。**

- Undo Snackbar 在底部中央，进度条可视化剩余时间
- 点击撤销立即回滚，同步更新 UI
- 高风险操作撤销窗口延长（30秒）

---

## 三、交互流程详解 (Interaction Flow)

### 3.1 整体布局改造

#### 当前布局（Modal）

```
┌─────────────────────────────────────┐
│                                     │
│   ┌───────────────────────────────┐ │
│   │    MagicWandDialog (Modal)    │ │ ← 阻断整个页面
│   │                               │ │
│   │  Stage 1: 输入                │ │
│   │  Stage 2: 预览                │ │
│   │  Stage 3: 确认卡片            │ │ ← ConfirmationCard
│   │  Stage 4: 执行                │ │
│   │  Stage 5: 结果                │ │
│   └───────────────────────────────┘ │
│                                     │
└─────────────────────────────────────┘
```

#### 改造后布局（Sidebar）

```
┌─────────────────────┬─────────────────────────────────────┐
│                     │ 🤖 AI Assistant         [× 关闭]    │ ← Sidebar Header
│  客户详情页          │                                     │
│                     │ ┌─────────────────────────────────┐ │
│                     │ │ 输入跟进内容...                  │ │ ← 输入区
│                     │ │                                 │ │
│                     │ │ [Inline Pill 确认]              │ │ ← Inline 确认
│                     │ │ [✓ 确认] [↩ 取消]              │ │
│                     │ └─────────────────────────────────┘ │
│                     │                                     │
│                     │ ┌─────────────────────────────────┐ │
│                     │ │ Workflow Mini-map               │ │ ← 流程进度
│                     │ │ 1. ✅ 创建跟进                  │ │
│                     │ │ 2. 🔄 确认商机                  │ │
│                     │ │ 3. ⏳ 创建合同                  │ │
│                     │ └─────────────────────────────────┘ │
│                     │                                     │
│                     │ [撤销上一步] [暂停流程]             │ ← 操作按钮
│                     │                                     │
│  继续浏览...         │                                     │ ← 左侧可继续浏览
│                     │                                     │
└─────────────────────┴─────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ← Undo Snackbar
│ ✅ 已标记赢单  [撤销]  [关闭]                              │ ← 底部中央
└───────────────────────────────────────────────────────────┘
```

---

### 3.2 场景一：简单操作（创建跟进记录）

**触发**：用户输入"微信联系了客户，客户有意向"

**流程**：

```
Step 1: 输入
  Sidebar 输入框 → 用户输入内容

Step 2: AI 解析
  后端 → 识别为 follow_up_customer
       → 置信度 0.98（高）
       → 风险等级：低（Level 1）

Step 3: Inline Pill 展示
  输入框下方 →
  ┌─────────────────────────────────────────┐
  │ [📄 创建跟进: 微信联系，客户有意向]     │
  │                    [✓ 确认] [↩ 取消]   │ ← 一行，简洁
  └─────────────────────────────────────────┘

Step 4: 用户确认
  点击 [✓ 确认] → 自动执行（低风险可自动）

Step 5: Undo Snackbar
  底部中央 →
  ┌─────────────────────────────────────────────────────┐
  │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
  │ ✅ 跟进记录已创建  [撤销]  [关闭]                   │ ← 10秒后消失
  └─────────────────────────────────────────────────────┘
```

---

### 3.3 场景二：中等风险操作（推进商机阶段）

**触发**：用户输入"推进商机到商务谈判阶段"

**流程**：

```
Step 1: 输入
  Sidebar 输入框 → 用户输入内容

Step 2: AI 解析
  后端 → 识别为 move_to_stage
       → 置信度 0.92（中高）
       → 风险等级：中（Level 2）

Step 3: Inline Pill 展示
  输入框下方 →
  ┌─────────────────────────────────────────────────┐
  │ [📄 推进阶段: 某某项目 → 商务谈判 (赢率40%)]   │
  │                          [查看详情] [✓] [↩]   │
  └─────────────────────────────────────────────────┘

Step 4: 用户点击 [查看详情] → 展开
  ┌─────────────────────────────────────────────────┐
  │ 推进商机阶段                                    │
  │ ├─ 商机：某某项目                               │
  │ ├─ 当前阶段：需求确认 (赢率20%)                │
  │ ├─ 目标阶段：商务谈判 (赢率40%)                │
  │ └─ 撤销：10秒内可撤销                           │
  │ [✓ 确认执行] [↩ 取消]                          │
  └─────────────────────────────────────────────────┘

Step 5: 用户确认 → 执行

Step 6: Undo Snackbar（10秒）
```

---

### 3.4 场景三：高风险操作（赢单）

**触发**：用户输入"客户确认采购"

**流程**：

```
Step 1: 输入
  Sidebar 输入框 → 用户输入"客户确认采购"

Step 2: AI 解析
  后端 → 识别为 customer_win_flow（Workflow）
       → 步骤数：4（跟进 → 商机确认 → 赢单 → 合同）
       → 自动触发 Workflow Mini-map

Step 3: Sidebar 展示 Workflow Mini-map
  右侧 →
  ┌─────────────────────────────────────────┐
  │ Workflow 进度                           │
  │                                         │
  │ 1. ✅ 创建跟进记录                      │ ← 已完成
  │                                         │
  │ 2. 🔄 确认商机                          │ ← 当前步骤
  │    ┌─────────────────────────────────┐ │
  │    │ [某某项目 - 50万 (推荐)]        │ │ ← Inline Pill + 推荐
  │    │   [切换其他商机 ▼]              │ │
  │    │   [✓ 确认] [↩ 取消]            │ │
  │    └─────────────────────────────────┘ │
  │                                         │
  │ 3. ⏳ 标记赢单                          │ ← 待执行
  │                                         │
  │ 4. ⏳ 创建合同                          │ ← 待执行
  │                                         │
  │ [撤销上一步] [暂停流程]                 │
  └─────────────────────────────────────────┘

Step 4: 用户选择商机
  点击 [切换其他商机 ▼] → 下拉列表
  ┌─────────────────────────────────────────┐
  │ > [✓] 某某项目 (50万, 谈判中) ← 推荐    │ ← 加粗 + 高亮
  │   某某项目 (30万, 已赢单)               │
  └─────────────────────────────────────────┘

Step 5: 用户确认 → 赢单执行

Step 6: Workflow Mini-map 更新
  ┌─────────────────────────────────────────┐
  │ 1. ✅ 创建跟进                          │
  │ 2. ✅ 确认商机                          │ ← 变绿色
  │ 3. 🔄 标记赢单                          │ ← 当前步骤
  │    ┌─────────────────────────────────┐ │
  │    │ 准备标记赢单                    │ │
  │    │ 商机：某某项目                  │ │
  │    │ 金额：50万                      │ │
  │    │ 撤销：30秒内可撤销              │ │
  │    │ [✓ 确认] [↩ 取消]              │ │
  │    └─────────────────────────────────┘ │
  │ 4. ⏳ 创建合同                          │
  │                                         │
  │ [撤销上一步] [暂停流程]                 │
  └─────────────────────────────────────────┘

Step 7: 用户确认赢单 → 执行

Step 8: Undo Snackbar（30秒，高风险）
  ┌───────────────────────────────────────────────────────────┐
  │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ← 进度条较长
  │ ✅ 已标记赢单：某某项目 (50万)  [撤销]  [关闭]           │ ← 30秒撤销窗口
  └───────────────────────────────────────────────────────────┘
```

---

### 3.5 Undo Snackbar 统一设计

**位置**：页面底部中央（不遮挡内容）

**布局**：

```
┌─────────────────────────────────────────────────────────────┐
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ← 进度条（倒计时可视化）
│                                                             │
│ ✅ 操作结果描述                          [撤销]  [关闭]     │ ← 三列布局
│    （如：已标记赢单：某某项目）                            │
└─────────────────────────────────────────────────────────────┘
```

**状态**：

| 状态 | 进度条颜色 | 操作按钮 |
|------|----------|----------|
| 可撤销（活跃） | 橙色动画 | [撤销] 可点击 |
| 撤销成功 | 绿色 | 显示"已撤销" 2秒后消失 |
| 撤销窗口过期 | 灰色 | [撤销] 变灰不可点击 |
| 关闭 | 无 | 立即消失 |

---

## 四、技术方案 (Technical Design)

### 4.1 MagicWandDialog 改造

#### 4.1.1 从 Modal 到 Drawer

**当前**：
```vue
<el-dialog v-model="visible" width="500px">
  <!-- 内容 -->
</el-dialog>
```

**改造后**：
```vue
<el-drawer
  v-model="visible"
  direction="rtl"
  size="400px"
  :with-header="true"
  :modal="false"  <!-- 关键：不显示遮罩层 -->
  :append-to-body="true"
>
  <template #header>
    <div class="drawer-header">
      <span>🤖 AI Assistant</span>
      <el-button text @click="handleClose">关闭</el-button>
    </div>
  </template>
  
  <!-- 内容 -->
</el-drawer>
```

**关键配置**：
- `direction="rtl"`：右侧滑出
- `size="400px"`：宽度固定
- `:modal="false"`：不显示遮罩层，用户可继续浏览左侧
- `:append-to-body="true"`：避免层级问题

---

#### 4.1.2 Sidebar 内部布局

**结构**：

```vue
<el-drawer>
  <!-- 输入区 -->
  <div class="sidebar-input">
    <el-input
      v-model="userInput"
      type="textarea"
      :rows="2"
      placeholder="输入跟进内容或操作指令..."
    />
    
    <!-- Inline Pill（确认时显示） -->
    <InlinePill
      v-if="stage === 'pending-confirmation'"
      :action="currentAction"
      :params="confirmationParams"
      :risk-level="riskLevel"
      @confirm="handleConfirm"
      @cancel="handleCancel"
      @expand="handleExpandDetails"
    />
  </div>
  
  <!-- Workflow Mini-map（Workflow 时显示） -->
  <WorkflowMiniMap
    v-if="workflowActive"
    :steps="workflowSteps"
    :current-step="currentStep"
    @step-click="handleStepClick"
    @undo-last="handleUndoLastStep"
    @pause="handlePauseWorkflow"
  />
  
  <!-- 执行状态 -->
  <div v-if="stage === 'loading'" class="sidebar-loading">
    <el-icon class="is-loading"><Loading /></el-icon>
    <span>{{ loadingMessage }}</span>
  </div>
  
  <!-- 操作按钮 -->
  <div class="sidebar-actions">
    <el-button v-if="workflowActive" @click="handleUndoLastStep">
      撤销上一步
    </el-button>
    <el-button v-if="workflowActive" @click="handlePauseWorkflow">
      暂停流程
    </el-button>
  </div>
</el-drawer>
```

---

### 4.2 Inline Pill 组件设计

#### 4.2.1 组件接口

```typescript
interface InlinePillProps {
  action: {
    type: string            // 'follow_up' | 'win' | 'create_contract'
    displayName: string     // '创建跟进' | '标记赢单'
  }
  params: Record<string, any>
  riskLevel: 'low' | 'medium' | 'high'
  recommendedOption?: {
    id: number
    name: string
    reason: string          // 推荐理由
  }
  alternatives?: Array<{
    id: number
    name: string
    details: string         // 区分度信息（金额、阶段等）
  }>
  undoTtl: number           // 撤销窗口（秒）
}

interface InlinePillEmits {
  confirm: [params?: Record<string, any>]
  cancel: []
  expand: []                // 展开详情
  selectAlternative: [id: number]
}
```

---

#### 4.2.2 组件布局

**默认态（一行）**：

```vue
<div class="inline-pill">
  <div class="pill-content">
    <span class="pill-icon">📄</span>
    <span class="pill-text">{{ action.displayName }}: {{ summaryText }}</span>
  </div>
  
  <div class="pill-actions">
    <el-button size="small" text @click="handleExpand">
      查看详情
    </el-button>
    <el-button size="small" type="primary" @click="handleConfirm">
      ✓ 确认
    </el-button>
    <el-button size="small" text @click="handleCancel">
      ↩ 取消
    </el-button>
  </div>
</div>
```

**展开态（多行）**：

```vue
<div class="inline-pill expanded">
  <div class="pill-header">
    <span class="pill-title">{{ action.displayName }}</span>
    <el-tag :type="riskLevelTagType" size="small">
      {{ riskLevelLabel }}
    </el-tag>
  </div>
  
  <div class="pill-details">
    <div v-for="(value, key) in displayParams" :key="key" class="detail-item">
      <span class="detail-label">{{ getParamLabel(key) }}:</span>
      <span class="detail-value">{{ formatParamValue(key, value) }}</span>
    </div>
  </div>
  
  <!-- 推荐选项（多歧义时） -->
  <div v-if="recommendedOption" class="pill-recommendation">
    <div class="recommendation-header">
      <el-icon><Star /></el-icon>
      <span>推荐</span>
    </div>
    <div class="recommendation-option">
      <span>{{ recommendedOption.name }}</span>
      <span class="recommendation-reason">{{ recommendedOption.reason }}</span>
    </div>
    
    <!-- 切换下拉 -->
    <el-dropdown v-if="alternatives?.length > 0">
      <el-button size="small" text>
        切换其他 <el-icon><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item 
            v-for="alt in alternatives"
            :key="alt.id"
            @click="handleSelectAlternative(alt.id)"
          >
            {{ alt.name }} - {{ alt.details }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
  
  <!-- 撤销提示 -->
  <div class="pill-undo-hint">
    <el-icon><Clock /></el-icon>
    <span>确认后 {{ undoTtl }} 秒内可撤销</span>
  </div>
  
  <div class="pill-actions-expanded">
    <el-button type="primary" @click="handleConfirm">✓ 确认执行</el-button>
    <el-button @click="handleCancel">↩ 取消</el-button>
  </div>
</div>
```

---

### 4.3 Workflow Mini-map 组件设计

#### 4.3.1 组件接口

```typescript
interface WorkflowMiniMapProps {
  steps: Array<{
    id: string
    name: string              // '创建跟进记录'
    status: 'pending' | 'running' | 'completed' | 'failed'
    result?: {
      success: boolean
      message: string
      undoable: boolean
    }
    currentAction?: InlinePillProps  // 当前步骤的确认动作
  }>
  currentStep: number
}

interface WorkflowMiniMapEmits {
  stepClick: [stepId: string]
  undoLast: []
  pause: []
}
```

---

#### 4.3.2 组件布局

```vue
<div class="workflow-mini-map">
  <div class="mini-map-header">
    <el-icon><Location /></el-icon>
    <span>流程进度</span>
  </div>
  
  <div class="mini-map-steps">
    <div
      v-for="(step, index) in steps"
      :key="step.id"
      class="mini-map-step"
      :class="`step-${step.status}`"
    >
      <!-- 步骤图标 -->
      <div class="step-icon">
        <el-icon v-if="step.status === 'completed'">
          <CircleCheckFilled />
        </el-icon>
        <el-icon v-else-if="step.status === 'running'" class="is-loading">
          <Loading />
        </el-icon>
        <el-icon v-else>
          <Clock />
        </el-icon>
      </div>
      
      <!-- 步骤名称 -->
      <div class="step-name">
        <span>{{ step.name }}</span>
        <el-tag v-if="step.status === 'running'" type="warning" size="small">
          进行中
        </el-tag>
      </div>
      
      <!-- 步骤结果 -->
      <div v-if="step.result" class="step-result">
        <span v-if="step.result.success" class="result-success">
          {{ step.result.message }}
        </span>
        <span v-else class="result-failed">
          {{ step.result.message }}
        </span>
      </div>
      
      <!-- 当前步骤的 Inline Pill -->
      <InlinePill
        v-if="step.status === 'running' && step.currentAction"
        :action="step.currentAction"
        :params="step.currentAction.params"
        :risk-level="step.currentAction.riskLevel"
        @confirm="handleStepConfirm"
        @cancel="handleStepCancel"
      />
      
      <!-- 连接线 -->
      <div v-if="index < steps.length - 1" class="step-connector">
        <div class="connector-line" :class="connectorClass(step.status)"></div>
      </div>
    </div>
  </div>
  
  <!-- 操作按钮 -->
  <div class="mini-map-actions">
    <el-button size="small" @click="handleUndoLast">
      撤销上一步
    </el-button>
    <el-button size="small" type="warning" @click="handlePause">
      暂停流程
    </el-button>
  </div>
</div>
```

---

### 4.4 Undo Snackbar 组件改造

#### 4.4.1 从 Toast 到底部 Snackbar

**当前 UndoToast.vue**：
- 位置：`bottom: 24px; right: 24px`（右下角）
- 形式：小型 Toast

**改造后**：
- 位置：`bottom: 0; left: 50%; transform: translateX(-50%)`（底部中央）
- 形式：宽度占满或固定宽度（如 600px）
- 布局：三列（进度条 + 结果描述 + 操作按钮）

---

#### 4.4.2 组件布局改造

```vue
<template>
  <Teleport to="body">
    <Transition name="snackbar-slide-up">
      <div class="undo-snackbar-container" v-if="visible">
        <div class="undo-snackbar">
          <!-- 进度条 -->
          <div class="snackbar-progress">
            <el-progress
              :percentage="progressPercentage"
              :show-text="false"
              :stroke-width="6"
              :color="progressColor"
            />
          </div>
          
          <!-- 内容区 -->
          <div class="snackbar-content">
            <!-- 左侧：结果图标 + 描述 -->
            <div class="snackbar-left">
              <el-icon :size="24" class="snackbar-icon">
                <CircleCheckFilled />
              </el-icon>
              <span class="snackbar-message">{{ message }}</span>
            </div>
            
            <!-- 右侧：操作按钮 -->
            <div class="snackbar-right">
              <el-button
                size="small"
                type="warning"
                :disabled="!canUndo"
                :loading="isUndoing"
                @click="handleUndo"
              >
                撤销
              </el-button>
              <el-button size="small" text @click="handleDismiss">
                关闭
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.undo-snackbar-container {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  width: 100%;
  max-width: 800px;
}

.undo-snackbar {
  background: #fff;
  border-top: 1px solid #ebeef5;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.1);
  
  .snackbar-progress {
    padding: 4px 16px 0;
  }
  
  .snackbar-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 24px;
    
    .snackbar-left {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
      
      .snackbar-icon {
        color: #67c23a;
      }
      
      .snackbar-message {
        font-size: 14px;
        color: #303133;
      }
    }
    
    .snackbar-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }
}

.snackbar-slide-up-enter-active {
  animation: slideUp 0.3s ease-out;
}

.snackbar-slide-up-leave-active {
  animation: slideDown 0.3s ease-in;
}

@keyframes slideUp {
  from {
    transform: translateX(-50%) translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }
}

@keyframes slideDown {
  from {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }
  to {
    transform: translateX(-50%) translateY(100%);
    opacity: 0;
  }
}
</style>
```

---

### 4.5 SSE 事件扩展

#### 4.5.1 新增事件类型

```typescript
// pending_confirmation 事件扩展
interface PendingConfirmationEvent {
  event: 'pending_confirmation'
  
  // Inline Pill 展示数据
  inline_pill: {
    action: {
      type: string
      displayName: string
    }
    params: Record<string, any>
    risk_level: 'low' | 'medium' | 'high'
    summary_text: string          // 摘要文本（一行）
    detailed_params: Record<string, any>  // 详细参数（展开时）
    
    // 推荐选项（多歧义时）
    recommendation?: {
      option: {
        id: number
        name: string
        details: string
      }
      reason: string
      alternatives: Array<{
        id: number
        name: string
        details: string
      }>
    }
    
    // 撤销配置
    undo_config: {
      ttl: number
      scope: 'single' | 'workflow'
    }
  }
  
  // Workflow Mini-map 数据（Workflow 时）
  workflow_mini_map?: {
    steps: Array<{
      id: string
      name: string
      status: 'pending' | 'running' | 'completed' | 'failed'
      result?: {
        success: boolean
        message: string
      }
    }>
    current_step: number
  }
}
```

---

### 4.6 状态管理

#### 4.6.1 Sidebar 状态

```typescript
interface SidebarState {
  visible: boolean
  stage: 'input' | 'pending-confirmation' | 'loading' | 'workflow-progress' | 'result'
  
  // Inline Pill 数据
  inlinePillData: InlinePillProps | null
  
  // Workflow Mini-map 数据
  workflowMiniMapData: WorkflowMiniMapProps | null
  
  // Undo Snackbar 数据
  undoSnackbarData: UndoSnackbarProps | null
  
  // 执行历史（用于撤销）
  executionHistory: Array<{
    stepId: string
    operationId: number
    undoable: boolean
  }>
}
```

---

### 4.7 风险等级配置

```typescript
// 风险等级与交互策略映射
const RISK_LEVEL_CONFIG = {
  low: {
    auto_execute: true,          // 低风险可自动执行
    undo_ttl: 10,                // 撤销窗口 10秒
    inline_pill_default: 'collapsed',  // 默认折叠
    require_confirmation: false  // 不需要确认
  },
  medium: {
    auto_execute: false,
    undo_ttl: 10,
    inline_pill_default: 'collapsed',
    require_confirmation: true   // 需要确认
  },
  high: {
    auto_execute: false,
    undo_ttl: 30,                // 高风险撤销窗口延长
    inline_pill_default: 'expanded',  // 默认展开详情
    require_confirmation: true
  }
}
```

---

## 五、需求清单 (Requirements)

### 5.1 Sidebar 改造

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-01 | MagicWandDialog 从 Modal 改为 Drawer | P0 | 用户可继续浏览左侧内容 |
| REQ-02 | Sidebar 方向为右侧（rtl），宽度 400px | P0 | 布局正确，不遮挡关键信息 |
| REQ-03 | 不显示遮罩层（modal=false） | P0 | 用户可点击左侧元素 |
| REQ-04 | Sidebar 包含输入区、Inline Pill、Mini-map | P0 | 布局完整 |
| REQ-05 | Sidebar Header 显示标题和关闭按钮 | P1 | UI 规范 |

### 5.2 Inline Pill 组件

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-06 | Inline Pill 默认一行展示（摘要） | P0 | 简洁，不占据过多空间 |
| REQ-07 | Inline Pill 支持展开详情 | P0 | 用户点击"查看详情"展开 |
| REQ-08 | Inline Pill 展示风险等级标签 | P1 | 低/中/高 三种颜色区分 |
| REQ-09 | Inline Pill 展示推荐选项（多歧义时） | P0 | 推荐+理由+切换下拉 |
| REQ-10 | Inline Pill 支持切换推荐项 | P0 | 用户可选择其他选项 |
| REQ-11 | Inline Pill 展示撤销窗口提示 | P1 | 用户知晓可撤销时长 |

### 5.3 Workflow Mini-map 组件

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-12 | Mini-map 展示所有 Workflow 步骤 | P0 | 用户看到全流程 |
| REQ-13 | Mini-map 每步骤显示状态图标（✅ 🔄 ⏳ ❌） | P0 | 状态可视化 |
| REQ-14 | 当前步骤嵌入 Inline Pill | P0 | 确认在 Mini-map 内完成 |
| REQ-15 | Mini-map 支持"撤销上一步" | P0 | 撤销后 Mini-map 更新 |
| REQ-16 | Mini-map 支持"暂停流程" | P1 | 用户可暂停后继续 |

### 5.4 Undo Snackbar 改造

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-17 | Snackbar 位置改为底部中央 | P0 | 不遮挡工作区 |
| REQ-18 | Snackbar 包含进度条（倒计时可视化） | P0 | 用户感知剩余时间 |
| REQ-19 | Snackbar 布局三列（图标+描述+按钮） | P1 | 信息布局合理 |
| REQ-20 | Snackbar 进度条颜色动态变化（活跃→过期） | P1 | 状态可视化 |

### 5.5 SSE 事件扩展

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-21 | pending_confirmation 事件包含 inline_pill 数据 | P0 | 前端正确渲染 Inline Pill |
| REQ-22 | pending_confirmation 事件包含 workflow_mini_map 数据 | P0 | 前端正确渲染 Mini-map |
| REQ-23 | recommendation 字段包含推荐选项和理由 | P0 | 推荐逻辑生效 |

---

## 六、成功指标 (Success Metrics)

1. **非阻断率**：用户在 Sidebar 交互时，仍可浏览左侧内容的比例达到 100%
2. **交互路径长度**：完成一次赢单流程的点击次数从 5+ 降到 2-3
3. **撤销使用率**：Undo Snackbar 使用率 < 5%（表明 AI 预判准确）
4. **详情展开率**：Inline Pill 详情展开率 < 30%（表明默认摘要足够）
5. **用户停留时长**：用户在 Sidebar 交互时，左侧浏览时长占比 > 50%

---

## 七、实施优先级

### Phase G-1（核心）P0
- REQ-01, 02, 03, 04, 06, 07, 12, 13, 14, 17, 18, 21, 22

### Phase G-2（增强）P1
- REQ-05, 08, 09, 11, 15, 16, 19, 20, 23, 10

---

> **文档状态**：需求定义完成
> **下一步**：形成实施计划
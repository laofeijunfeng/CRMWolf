---
status: completed
created: 2026-06-10
updated: 2026-06-10
related_requirements: ../requirements/AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md
related_pr: -
---

# Agent Inline 交互系统 - 实施计划

> **状态：✅ 已完成** | 完成日期：2026-06-10

| 文档版本 | V 1.0 |
| :--- | :--- |
| **基于需求** | AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md |
| **实施原则** | 不计成本，以成熟、稳健为首要 |
| **更新日期** | 2026-06-10 |

---

## 一、实施阶段划分

### 总览

| Phase | 内容 | 优先级 | 工期 |
|-------|------|--------|------|
| **Phase G-1** | Sidebar 改造 + Inline Pill + Undo Snackbar 改造 | P0（核心） | 2-3 天 |
| **Phase G-2** | Workflow Mini-map + SSE 事件扩展 | P0（核心） | 2-3 天 |
| **Phase G-3** | 推荐逻辑 + 样式优化 + 增强功能 | P1 | 1-2 天 |

---

## 二、Phase G-1：核心组件改造

### 2.1 目标
- MagicWandDialog 从 Modal 改为 Drawer
- ConfirmationCard 改为 Inline Pill
- UndoToast 改为底部 Snackbar

### 2.2 前端实施

#### 2.2.1 MagicWandDialog 改造

**改动文件**：`CRM-Client/src/components/MagicWandDialog.vue`

**改动内容**：

1. **Dialog → Drawer**

```vue
// 当前
<el-dialog
  v-model="visible"
  :title="dialogTitle"
  width="500px"
  :close-on-click-modal="false"
  @close="handleClose"
>
  <!-- 内容 -->
</el-dialog>

// 改造后
<el-drawer
  v-model="visible"
  direction="rtl"
  size="400px"
  :modal="false"
  :with-header="true"
  @close="handleClose"
>
  <template #header>
    <div class="drawer-header">
      <span class="drawer-title">🤖 AI Assistant</span>
      <el-button text size="small" @click="handleClose">
        <el-icon><Close /></el-icon>
      </el-button>
    </div>
  </template>
  
  <!-- Sidebar 内容 -->
  <div class="sidebar-content">
    <!-- 输入区 -->
    <div class="sidebar-input-section">
      <!-- ... -->
    </div>
    
    <!-- Inline Pill 区域 -->
    <div class="sidebar-pill-section" v-if="stage === 'pending-confirmation'">
      <InlinePill ... />
    </div>
    
    <!-- Workflow Mini-map 区域 -->
    <div class="sidebar-minimap-section" v-if="workflowActive">
      <WorkflowMiniMap ... />
    </div>
  </div>
</el-drawer>
```

---

2. **Stage 类型扩展**

```typescript
// 当前
type Stage =
  | 'input'
  | 'clarify'
  | 'preview'
  | 'preview-form'
  | 'pending-confirmation'
  | 'loading'
  | 'result'

// 改造后（新增 Sidebar 专属状态）
type Stage =
  | 'sidebar-input'           // Sidebar 输入态
  | 'sidebar-pill'            // Inline Pill 确认态
  | 'sidebar-minimap'         // Workflow Mini-map 态
  | 'sidebar-loading'         // 执行中
  | 'sidebar-result'          // 结果态
  | 'error'
```

---

3. **新增 Sidebar 状态变量**

```typescript
// Sidebar 专属状态
const sidebarExpanded = ref(false)           // Sidebar 是否展开显示更多内容
const inlinePillExpanded = ref(false)        // Inline Pill 是否展开详情

// Inline Pill 数据
interface InlinePillData {
  actionType: string
  actionDisplayName: string
  params: Record<string, any>
  riskLevel: 'low' | 'medium' | 'high'
  summaryText: string
  detailedParams: Record<string, any>
  recommendation?: {
    option: { id: number; name: string; details: string }
    reason: string
    alternatives: Array<{ id: number; name: string; details: string }>
  }
  undoTtl: number
}

const inlinePillData = ref<InlinePillData | null>(null)
```

---

#### 2.2.2 Inline Pill 组件实现

**新增文件**：`CRM-Client/src/components/InlinePill.vue`

**组件结构**：

```vue
<template>
  <div class="inline-pill" :class="{ 'expanded': isExpanded, [`risk-${riskLevel}`]: true }">
    <!-- 默认态（一行） -->
    <div class="pill-collapsed" v-if="!isExpanded">
      <div class="pill-content">
        <span class="pill-icon">📄</span>
        <span class="pill-summary">{{ actionDisplayName }}: {{ summaryText }}</span>
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
    
    <!-- 展开态（多行） -->
    <div class="pill-expanded" v-if="isExpanded">
      <div class="pill-header">
        <span class="pill-title">{{ actionDisplayName }}</span>
        <el-tag :type="riskLevelTagType" size="small">
          {{ riskLevelLabel }}
        </el-tag>
      </div>
      
      <div class="pill-details">
        <div v-for="(value, key) in detailedParams" :key="key" class="detail-item">
          <span class="detail-label">{{ getParamLabel(key) }}:</span>
          <span class="detail-value">{{ formatParamValue(key, value) }}</span>
        </div>
      </div>
      
      <!-- 推荐选项 -->
      <div v-if="recommendation" class="pill-recommendation">
        <div class="recommendation-header">
          <el-icon><StarFilled /></el-icon>
          <span>推荐选项</span>
        </div>
        <div class="recommendation-option">
          <span class="option-name">{{ recommendation.option.name }}</span>
          <span class="option-details">{{ recommendation.option.details }}</span>
          <span class="option-reason">{{ recommendation.reason }}</span>
        </div>
        
        <!-- 切换下拉 -->
        <el-dropdown v-if="recommendation.alternatives?.length > 0">
          <el-button size="small" text>
            切换其他 <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="alt in recommendation.alternatives"
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
        <el-button type="primary" size="default" @click="handleConfirm">
          ✓ 确认执行
        </el-button>
        <el-button size="default" @click="handleCancel">
          ↩ 取消
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { StarFilled, ArrowDown, Clock } from '@element-plus/icons-vue'

interface Props {
  actionType: string
  actionDisplayName: string
  params: Record<string, any>
  riskLevel: 'low' | 'medium' | 'high'
  summaryText: string
  detailedParams: Record<string, any>
  recommendation?: {
    option: { id: number; name: string; details: string }
    reason: string
    alternatives: Array<{ id: number; name: string; details: string }>
  }
  undoTtl: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: [params?: Record<string, any>]
  cancel: []
  expand: []
  selectAlternative: [id: number]
}>()

const isExpanded = ref(false)

// 风险等级映射
const riskLevelTagType = computed(() => {
  switch (props.riskLevel) {
    case 'high': return 'danger'
    case 'medium': return 'warning'
    default: return 'info'
  }
})

const riskLevelLabel = computed(() => {
  switch (props.riskLevel) {
    case 'high': return '高风险'
    case 'medium': return '中风险'
    default: return '低风险'
  }
})

// 参数标签映射
const PARAM_LABEL_MAP: Record<string, string> = {
  content: '跟进内容',
  method: '跟进方式',
  opportunity_name: '商机',
  customer_name: '客户',
  amount: '金额',
  stage_name: '阶段'
}

function getParamLabel(key: string): string {
  return PARAM_LABEL_MAP[key] || key
}

function formatParamValue(key: string, value: any): string {
  if (value === null || value === undefined) return '未设置'
  if (typeof value === 'number' && key.includes('amount')) return `${value}万`
  return String(value)
}

function handleExpand() {
  isExpanded.value = !isExpanded.value
  emit('expand')
}

function handleConfirm() {
  emit('confirm')
}

function handleCancel() {
  emit('cancel')
}

function handleSelectAlternative(id: number) {
  emit('selectAlternative', id)
}
</script>

<style scoped lang="scss">
.inline-pill {
  margin: 12px 0;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;
  
  // 风险等级边框
  &.risk-low {
    border-left: 3px solid #67c23a;
  }
  &.risk-medium {
    border-left: 3px solid #e6a23c;
  }
  &.risk-high {
    border-left: 3px solid #f56c6c;
    background: #fef0f0;
  }
  
  &.expanded {
    padding: 16px;
    background: #fff;
  }
}

.pill-collapsed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  
  .pill-content {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    
    .pill-icon {
      font-size: 16px;
    }
    
    .pill-summary {
      font-size: 14px;
      color: #303133;
    }
  }
  
  .pill-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }
}

.pill-expanded {
  .pill-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    
    .pill-title {
      font-size: 16px;
      font-weight: 500;
    }
  }
  
  .pill-details {
    margin-bottom: 12px;
    
    .detail-item {
      display: flex;
      align-items: center;
      padding: 4px 0;
      
      .detail-label {
        width: 80px;
        font-size: 13px;
        color: #909399;
      }
      
      .detail-value {
        font-size: 14px;
        color: #303133;
      }
    }
  }
  
  .pill-recommendation {
    padding: 12px;
    background: #ecf5ff;
    border-radius: 6px;
    margin-bottom: 12px;
    
    .recommendation-header {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: #409eff;
      margin-bottom: 8px;
    }
    
    .recommendation-option {
      .option-name {
        font-size: 14px;
        font-weight: 500;
        color: #303133;
      }
      
      .option-details {
        font-size: 12px;
        color: #606266;
        margin-left: 8px;
      }
      
      .option-reason {
        font-size: 12px;
        color: #409eff;
        margin-left: 8px;
      }
    }
  }
  
  .pill-undo-hint {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: #e6a23c;
    margin-bottom: 12px;
  }
  
  .pill-actions-expanded {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
  }
}
</style>
```

---

#### 2.2.3 Undo Snackbar 改造

**改动文件**：`CRM-Client/src/components/UndoToast.vue`

**改动内容**：

1. **位置改为底部中央**

```scss
// 当前
.undo-toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
}

// 改造后
.undo-snackbar-container {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  width: 100%;
  max-width: 800px;
}
```

---

2. **布局改为三列**

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

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

interface Props {
  operationId: number
  undoEndpoint: string
  ttl: number
  message: string
  visible: boolean
}

const props = withDefaults(defineProps<Props>(), {
  ttl: 10,
  visible: true
})

const emit = defineEmits<{
  'undo-success': []
  'undo-failed': [reason: string]
  'expired': []
  'dismiss': []
}>()

const remainingSeconds = ref(props.ttl)
const isUndoing = ref(false)
const canUndo = ref(true)
const localVisible = ref(props.visible)

// 进度条
const progressPercentage = computed(() => {
  return (remainingSeconds.value / props.ttl) * 100
})

// 进度条颜色（动态变化）
const progressColor = computed(() => {
  if (remainingSeconds.value > props.ttl * 0.5) {
    return '#e6a23c'  // 橙色（活跃）
  } else if (remainingSeconds.value > props.ttl * 0.2) {
    return '#909399'  // 灰色（即将过期）
  } else {
    return '#c0c4cc'  // 更浅灰色（快过期）
  }
})

// 倒计时
let countdownTimer: ReturnType<typeof setInterval> | null = null

const startCountdown = () => {
  countdownTimer = setInterval(() => {
    remainingSeconds.value -= 1
    if (remainingSeconds.value <= 0) {
      stopCountdown()
      canUndo.value = false
      localVisible.value = false
      emit('expired')
    }
  }, 1000)
}

const stopCountdown = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

watch(() => props.visible, (newVal) => {
  localVisible.value = newVal
  if (newVal) {
    remainingSeconds.value = props.ttl
    canUndo.value = true
    startCountdown()
  } else {
    stopCountdown()
  }
}, { immediate: true })

onUnmounted(() => {
  stopCountdown()
})

// 撤销
const handleUndo = async () => {
  if (!canUndo.value) return
  
  isUndoing.value = true
  stopCountdown()
  
  try {
    const response = await fetch(props.undoEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    
    const result = await response.json()
    
    if (result.success) {
      localVisible.value = false
      emit('undo-success')
      ElMessage.success({
        message: result.message || '操作已撤销',
        duration: 2000
      })
    } else {
      emit('undo-failed', result.reason || '撤销失败')
      ElMessage.error({
        message: result.reason || '撤销失败',
        duration: 3000
      })
      if (remainingSeconds.value > 0) {
        startCountdown()
      }
    }
  } catch (error) {
    console.error('Undo failed:', error)
    emit('undo-failed', '撤销请求失败')
    ElMessage.error('撤销请求失败')
    if (remainingSeconds.value > 0) {
      startCountdown()
    }
  } finally {
    isUndoing.value = false
  }
}

const handleDismiss = () => {
  stopCountdown()
  localVisible.value = false
  emit('dismiss')
}
</script>

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
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
  
  .snackbar-progress {
    padding: 4px 16px 0;
  }
  
  .snackbar-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    
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

### 2.3 后端改动

#### 2.3.1 SSE 事件扩展

**改动文件**：`CRM-Server/app/services/workflow/workflow_orchestrator.py`

**新增方法**：构建 Inline Pill 数据

```python
def _build_inline_pill_data(
    self,
    step: Dict,
    params: Dict,
    session: Dict,
    risk_level: str
) -> Dict[str, Any]:
    """构建 Inline Pill 展示数据"""
    
    # 获取工具配置
    tool_name = step.get("tool_name")
    tool_config = self._get_tool_config(tool_name)
    
    # 构建摘要文本
    summary_text = self._build_summary_text(tool_name, params)
    
    # 构建详细参数
    detailed_params = self._build_detailed_params(tool_name, params)
    
    # 构建推荐选项（如果有多歧义）
    recommendation = self._build_recommendation(session)
    
    return {
        "action_type": tool_name,
        "action_display_name": tool_config.get("display_name", tool_name),
        "params": params,
        "risk_level": risk_level,
        "summary_text": summary_text,
        "detailed_params": detailed_params,
        "recommendation": recommendation,
        "undo_ttl": step.get("undo_ttl", 10)
    }

def _build_summary_text(self, tool_name: str, params: Dict) -> str:
    """构建摘要文本（一行）"""
    if tool_name == "follow_up_customer":
        content = params.get("content", "")
        return content[:30] + "..." if len(content) > 30 else content
    
    elif tool_name == "win_opportunity":
        opportunity_name = params.get("opportunity_name", "未知商机")
        amount = params.get("actual_amount", "未知金额")
        return f"{opportunity_name} ({amount}万)"
    
    elif tool_name == "create_contract":
        customer_name = params.get("customer_name", "未知客户")
        amount = params.get("contract_amount", "未知金额")
        return f"{customer_name} ({amount}万)"
    
    return str(params)

def _build_detailed_params(self, tool_name: str, params: Dict) -> Dict:
    """构建详细参数（展开时）"""
    # 根据工具类型选择要展示的参数
    display_param_keys = {
        "follow_up_customer": ["content", "method", "next_follow_time"],
        "win_opportunity": ["opportunity_name", "actual_amount", "actual_closing_date"],
        "create_contract": ["customer_name", "contract_amount", "signed_date"]
    }
    
    keys = display_param_keys.get(tool_name, list(params.keys()))
    
    return {k: params.get(k) for k in keys if k in params}

def _build_recommendation(self, session: Dict) -> Optional[Dict]:
    """构建推荐选项"""
    # 如果 session 中有候选列表
    candidates = session.get("candidates", [])
    
    if not candidates or len(candidates) <= 1:
        return None
    
    # 选择推荐项（第一个或相关性最高的）
    from app.services.workflow.entity_renderer import entity_renderer
    
    entity_type = session.get("entity_type", "opportunity")
    rendered = entity_renderer.render_for_selection(entity_type, candidates)
    
    if rendered:
        recommended = rendered[0]  # 第一个为推荐项
        alternatives = rendered[1:] if len(rendered) > 1 else []
        
        return {
            "option": {
                "id": recommended["id"],
                "name": recommended["name"],
                "details": recommended["display"]
            },
            "reason": "最近更新，相关性最高",
            "alternatives": [
                {
                    "id": alt["id"],
                    "name": alt["name"],
                    "details": alt["display"]
                }
                for alt in alternatives
            ]
        }
    
    return None
```

---

#### 2.3.2 Workflow Mini-map 数据构建

```python
def _build_workflow_mini_map_data(self, session: Dict) -> Dict[str, Any]:
    """构建 Workflow Mini-map 数据"""
    
    workflow_id = session.get("workflow_id")
    workflow_config = self.workflow_definitions.WORKFLOW_REGISTRY.get(workflow_id)
    
    if not workflow_config:
        return {}
    
    steps = workflow_config.get("steps", [])
    executed_steps = session.get("executed_steps", [])
    current_step_id = session.get("current_step_id")
    
    mini_map_steps = []
    
    for step in steps:
        step_id = step.get("id")
        
        # 确定步骤状态
        if step_id in executed_steps:
            status = "completed"
            result = executed_steps.get(step_id)
        elif step_id == current_step_id:
            status = "running"
            result = None
        else:
            status = "pending"
            result = None
        
        mini_map_steps.append({
            "id": step_id,
            "name": step.get("description", step_id),
            "status": status,
            "result": {
                "success": result.get("success", False) if result else False,
                "message": result.get("message", "") if result else ""
            } if result else None
        })
    
    return {
        "steps": mini_map_steps,
        "current_step": self._find_current_step_index(mini_map_steps)
    }

def _find_current_step_index(self, steps: List[Dict]) -> int:
    """找到当前步骤的索引"""
    for i, step in enumerate(steps):
        if step.get("status") == "running":
            return i
    return -1
```

---

#### 2.3.3 pending_confirmation 事件扩展

```python
# 在 _execute_tool_with_confirmation 方法中
def _execute_tool_with_confirmation(self, step, session, db):
    """执行工具（带确认）"""
    
    if step.get("require_confirmation"):
        # 构建 Inline Pill 数据
        risk_level = step.get("confirmation_config", {}).get("risk_level", "medium")
        inline_pill_data = self._build_inline_pill_data(step, session.get("params", {}), session, risk_level)
        
        # 构建 Mini-map 数据（如果是 Workflow）
        workflow_mini_map_data = None
        if session.get("workflow_id"):
            workflow_mini_map_data = self._build_workflow_mini_map_data(session)
        
        yield {
            "event": "pending_confirmation",
            "step_id": step["id"],
            "inline_pill": inline_pill_data,
            "workflow_mini_map": workflow_mini_map_data,
            "undo_config": {
                "ttl": step.get("undo_ttl", 10),
                "scope": "workflow" if session.get("workflow_id") else "single"
            }
        }
        
        session["waiting_for_confirmation"] = step["id"]
        self._save_session(session)
        return
```

---

## 三、Phase G-2：Workflow Mini-map 实现

### 3.1 目标
- Workflow Mini-map 组件完整实现
- SSE 事件正确携带 Mini-map 数据
- Mini-map 与 Inline Pill 联动

### 3.2 前端实施

#### 3.2.1 Workflow Mini-map 组件

**新增文件**：`CRM-Client/src/components/WorkflowMiniMap.vue`

**组件结构**：

```vue
<template>
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
          <el-icon v-if="step.status === 'completed'" class="icon-completed">
            <CircleCheckFilled />
          </el-icon>
          <el-icon v-else-if="step.status === 'running'" class="is-loading">
            <Loading />
          </el-icon>
          <el-icon v-else class="icon-pending">
            <Clock />
          </el-icon>
        </div>
        
        <!-- 步骤名称 -->
        <div class="step-content">
          <div class="step-name">{{ step.name }}</div>
          
          <!-- 步骤结果 -->
          <div v-if="step.result" class="step-result">
            <span :class="step.result.success ? 'success' : 'failed'">
              {{ step.result.message }}
            </span>
          </div>
          
          <!-- 当前步骤的 Inline Pill -->
          <InlinePill
            v-if="step.status === 'running' && step.inlinePill"
            :action-type="step.inlinePill.actionType"
            :action-display-name="step.inlinePill.actionDisplayName"
            :params="step.inlinePill.params"
            :risk-level="step.inlinePill.riskLevel"
            :summary-text="step.inlinePill.summaryText"
            :detailed-params="step.inlinePill.detailedParams"
            :recommendation="step.inlinePill.recommendation"
            :undo-ttl="step.inlinePill.undoTtl"
            @confirm="handleConfirm"
            @cancel="handleCancel"
            @select-alternative="handleSelectAlternative"
          />
        </div>
        
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
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Location, CircleCheckFilled, Loading, Clock } from '@element-plus/icons-vue'
import InlinePill from './InlinePill.vue'

interface Step {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result?: {
    success: boolean
    message: string
  }
  inlinePill?: any
}

interface Props {
  steps: Step[]
  currentStep: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: [params?: any]
  cancel: []
  selectAlternative: [id: number]
  undoLast: []
  pause: []
}>()

function connectorClass(status: string): string {
  if (status === 'completed') return 'completed'
  return 'pending'
}

function handleConfirm(params?: any) {
  emit('confirm', params)
}

function handleCancel() {
  emit('cancel')
}

function handleSelectAlternative(id: number) {
  emit('selectAlternative', id)
}

function handleUndoLast() {
  emit('undoLast')
}

function handlePause() {
  emit('pause')
}
</script>

<style scoped lang="scss">
.workflow-mini-map {
  margin: 16px 0;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  
  .mini-map-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 500;
    color: #303133;
    margin-bottom: 16px;
  }
  
  .mini-map-steps {
    .mini-map-step {
      position: relative;
      padding: 8px 0;
      
      .step-icon {
        position: absolute;
        left: 0;
        top: 8px;
        width: 24px;
        height: 24px;
        
        .icon-completed {
          color: #67c23a;
        }
        
        .icon-pending {
          color: #c0c4cc;
        }
      }
      
      .step-content {
        margin-left: 32px;
        
        .step-name {
          font-size: 14px;
          color: #303133;
          margin-bottom: 4px;
        }
        
        .step-result {
          font-size: 12px;
          
          .success {
            color: #67c23a;
          }
          
          .failed {
            color: #f56c6c;
          }
        }
      }
      
      &.step-running {
        .step-content {
          .step-name {
            color: #e6a23c;
            font-weight: 500;
          }
        }
      }
      
      .step-connector {
        position: absolute;
        left: 11px;
        top: 32px;
        height: 24px;
        width: 2px;
        
        .connector-line {
          width: 2px;
          height: 100%;
          background: #c0c4cc;
          
          &.completed {
            background: #67c23a;
          }
        }
      }
    }
  }
  
  .mini-map-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
  }
}
</style>
```

---

## 四、Phase G-3：增强功能

### 4.1 推荐逻辑完善
- EntityRenderer 根据上下文计算相关性
- 推荐理由展示（"最近更新"、"金额匹配"等）

### 4.2 样式优化
- Inline Pill 动画效果
- Mini-map 步骤过渡动画
- Snackbar 进度条动画优化

---

## 五、文件改动清单

### 5.1 新增文件

| 文件 | 说明 |
|------|------|
| `CRM-Client/src/components/InlinePill.vue` | Inline Pill 组件 |
| `CRM-Client/src/components/WorkflowMiniMap.vue` | Workflow Mini-map 组件 |

### 5.2 改动文件

| 文件 | 改动内容 |
|------|----------|
| `CRM-Client/src/components/MagicWandDialog.vue` | Modal → Drawer，Sidebar 布局 |
| `CRM-Client/src/components/UndoToast.vue` | 位置 + 布局改造 |
| `CRM-Server/app/services/workflow/workflow_orchestrator.py` | Inline Pill 数据构建 + Mini-map 数据 |

---

## 六、验收清单

| 验收项 | 标准 | 测试方式 |
|--------|------|----------|
| Sidebar 非阻断 | 用户可继续浏览左侧 | 打开 Sidebar，点击左侧元素 |
| Inline Pill 默认一行 | 摘要展示，不占据过多空间 | 手动测试 |
| Inline Pill 展开 | 点击"查看详情"展开完整参数 | 手动测试 |
| 推荐选项 | 多歧义时展示推荐+切换 | 测试多商机场景 |
| Mini-map 进度 | Workflow 步骤状态正确 | 测试赢单流程 |
| Undo Snackbar 底部 | 进度条可视化，一键撤销 | 手动测试 |

---

## 七、实施顺序

```
Day 1:
  - MagicWandDialog Modal → Drawer
  - UndoToast 位置 + 布局改造

Day 2:
  - InlinePill 组件实现
  - MagicWandDialog 集成 Inline Pill

Day 3:
  - WorkflowMiniMap 组件实现
  - SSE 事件扩展（后端）

Day 4:
  - 推荐逻辑完善
  - 样式优化
  - 测试验证

Day 5:
  - 文档更新
  - 功能验收
```

---

> **实施计划状态**：定义完成
> **下一步**：按 Phase 顺序实施
# AI Execution Log V2 紧凑优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AI 助手执行日志从 V1 (8/10) 优化到 V2 (10/10)，实现信息密度最大化 + 认知负担最小化

**Architecture:** 新建 5 个核心组件（InlineStep、InlineCandidate、HoverPreviewTooltip、CompactConfirmSummary、CompactInfoGap），重写 3 个容器组件（CompactExecutionLog、CollapsedView、ExpandedView），删除 3 个旧组件，调整后端 SSE 事件补充 V2 所需字段

**Tech Stack:** Vue 3 + TypeScript + Element Plus + Pinia + Vitest + Cypress

## Global Constraints

- **CSS 变量**: 使用 `$wolf-*` Sass 变量，如 `$wolf-primary: #4A6FA5`
- **尺寸精确**: InlineStep padding `3px 16px`，CollapsedView height `36px`，Radio `14px`
- **动画时长**: 所有 transition `0.15s`（V2），禁止超过 `0.2s`
- **无 Emoji**: 使用 Element Plus SVG 图标，禁止 emoji 作为 UI 图标
- **括号格式**: CSS `::before { content: '(' }` + `::after { content: ')' }`
- **ARIA**: 所有候选卡片 `role="radio"` + `aria-checked`
- **TDD**: 每个组件先写测试再实现

---

## Phase 1: 后端调整（P0）

### Task 1: SSE waiting_for_user 事件补充字段

**Files:**
- Modify: `CRM-Server/app/services/langgraph/sse_wrapper.py`
- Test: `CRM-Server/tests/test_sse_wrapper.py`

**Interfaces:**
- Consumes: `build_waiting_for_user_event()` 现有签名
- Produces: 新字段 `confirmationType`, `riskLevel`, `params`, `options` (Dict格式)

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/test_sse_wrapper.py

def test_waiting_for_user_v2_fields():
    """测试 V2 SSE waiting_for_user 事件包含所有必需字段"""
    event = build_waiting_for_user_event(
        question="请选择目标客户",
        confirmationType="disambiguation",
        options=[
            {"id": 16, "name": "光大证券", "entity_info_inline": "ID:16 · 金融 · 活跃"}
        ],
        riskLevel="low",
        params={"action": "create_follow_up", "customer": "光大证券"}
    )
    
    data = json.loads(event.split("data: ")[1])
    
    assert data["confirmationType"] == "disambiguation"
    assert data["riskLevel"] == "low"
    assert data["params"]["action"] == "create_follow_up"
    assert len(data["options"]) == 1
    assert data["options"][0]["entity_info_inline"] == "ID:16 · 金融 · 活跃"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_waiting_for_user_v2_fields -v`
Expected: FAIL with "TypeError: build_waiting_for_user_event() got unexpected keyword argument 'confirmationType'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/langgraph/sse_wrapper.py

def build_waiting_for_user_event(
    question: str,
    confirmationType: str,  # ← V2 新增："disambiguation" | "confirmation" | "info_gap"
    options: Optional[List[Dict[str, Any]]] = None,  # ← V2 改为 Dict 格式
    missing_fields: Optional[List[str]] = None,
    field_options: Optional[Dict[str, Any]] = None,
    riskLevel: Optional[str] = None,  # ← V2 新增："low" | "medium" | "high"
    params: Optional[Dict[str, Any]] = None,  # ← V2 新增：当前操作参数
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_waiting_for_user_v2_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/langgraph/sse_wrapper.py CRM-Server/tests/test_sse_wrapper.py
git commit -m "feat(sse): add V2 fields to waiting_for_user event (confirmationType/riskLevel/params)"
```

---

### Task 2: EntityCandidate 补充字段

**Files:**
- Modify: `CRM-Server/app/services/langgraph/state.py`
- Test: `CRM-Server/tests/test_state.py`

**Interfaces:**
- Consumes: `EntityCandidate` 现有字段
- Produces: 新字段 `industry`, `status`, `amount`, `stage`, `entity_info_inline`, `entity_info_detail`

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/test_state.py

def test_entity_candidate_v2_fields():
    """测试 EntityCandidate V2 字段完整性"""
    candidate: EntityCandidate = {
        "id": 16,
        "name": "光大证券股份有限公司",
        "hint": "金融行业客户",
        "matched_by": "name",
        "entity_type": "customer",
        "industry": "金融",
        "status": "活跃",
        "amount": None,
        "stage": None,
        "entity_info_inline": "ID:16 · 金融 · 活跃",
        "entity_info_detail": {
            "industry": "金融服务业",
            "status": "活跃",
            "address": "上海市静安区"
        }
    }
    
    assert candidate["industry"] == "金融"
    assert candidate["status"] == "活跃"
    assert candidate["entity_info_inline"] == "ID:16 · 金融 · 活跃"
    assert candidate["entity_info_detail"]["address"] == "上海市静安区"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest CRM-Server/tests/test_state.py::test_entity_candidate_v2_fields -v`
Expected: FAIL with "KeyError: 'industry'" (TypedDict 字段不存在)

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/langgraph/state.py

class EntityCandidate(TypedDict):
    id: int
    name: str
    hint: str
    matched_by: str
    entity_type: str
    # ← V2 新增字段
    industry: Optional[str]       # 行业
    status: Optional[str]         # 状态
    amount: Optional[float]       # 金额（商机）
    stage: Optional[str]          # 阶段（商机）
    entity_info_inline: Optional[str]  # 格式化 Inline 文本
    entity_info_detail: Optional[Dict[str, Any]]  # Hover 详情
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest CRM-Server/tests/test_state.py::test_entity_candidate_v2_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/langgraph/state.py CRM-Server/tests/test_state.py
git commit -m "feat(state): add V2 fields to EntityCandidate (industry/status/entity_info_inline)"
```

---

### Task 3: SSE tool_call/tool_result 补充字段

**Files:**
- Modify: `CRM-Server/app/services/langgraph/sse_wrapper.py`
- Test: `CRM-Server/tests/test_sse_wrapper.py`

**Interfaces:**
- Consumes: `build_tool_call_event()`, `build_tool_result_event()` 现有签名
- Produces: `thinking` (tool_call), `summary` (tool_result)

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/test_sse_wrapper.py

def test_tool_call_v2_thinking_field():
    """测试 tool_call 事件包含 AI 推理过程"""
    event = build_tool_call_event(
        tool="search_customer",
        params={"keyword": "光大证券"},
        thinking="用户想跟进光大证券，需要先找到客户..."
    )
    
    data = json.loads(event.split("data: ")[1])
    
    assert data["tool"] == "search_customer"
    assert data["params"]["keyword"] == "光大证券"
    assert data["thinking"] == "用户想跟进光大证券，需要先找到客户..."

def test_tool_result_v2_summary_field():
    """测试 tool_result 事件包含业务化摘要"""
    event = build_tool_result_event(
        tool="search_customer",
        result={"count": 1, "customers": [{"name": "光大证券"}]},
        summary="找到 1 个客户：光大证券股份有限公司"
    )
    
    data = json.loads(event.split("data: ")[1])
    
    assert data["tool"] == "search_customer"
    assert data["result"]["count"] == 1
    assert data["summary"] == "找到 1 个客户：光大证券股份有限公司"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_tool_call_v2_thinking_field -v`
Expected: FAIL with "TypeError: build_tool_call_event() got unexpected keyword argument 'thinking'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/langgraph/sse_wrapper.py

def build_tool_call_event(
    tool: str,
    params: Optional[Dict[str, Any]] = None,
    thinking: Optional[str] = None  # ← V2 新增：AI 推理过程
) -> str:
    return build_sse_event(
        SSE_EVENT_TYPES["TOOL_CALL"],
        {
            "tool": tool,
            "params": params or {},
            "thinking": thinking
        }
    )

def build_tool_result_event(
    tool: str,
    result: Dict[str, Any],
    summary: Optional[str] = None  # ← V2 新增：业务化摘要
) -> str:
    display_result = filter_result_for_display(result)
    return build_sse_event(
        SSE_EVENT_TYPES["TOOL_RESULT"],
        {
            "tool": tool,
            "result": display_result,
            "summary": summary
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_tool_call_v2_thinking_field CRM-Server/tests/test_sse_wrapper.py::test_tool_result_v2_summary_field -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/langgraph/sse_wrapper.py CRM-Server/tests/test_sse_wrapper.py
git commit -m "feat(sse): add thinking/summary fields to tool_call/tool_result events"
```

---

### Task 4: ExecutionStepSchema 补充 V2 字段

**Files:**
- Modify: `CRM-Server/app/schemas/ai_conversation.py`
- Test: `CRM-Server/tests/test_ai_conversation_schema.py`

**Interfaces:**
- Consumes: `ExecutionStepSchema` 现有字段
- Produces: `inline_text`, `thinking`, `summary`, `summary_params`, `detail_params`, `confirmationType`, `riskLevel`, `options`

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/test_ai_conversation_schema.py

from app.schemas.ai_conversation import ExecutionStepSchema

def test_execution_step_v2_inline_fields():
    """测试 ExecutionStepSchema V2 inline 字段"""
    step_data = {
        "id": "step-001",
        "type": "tool_call",
        "title": "查找客户信息",
        "timestamp": "2026-06-25T10:30:01Z",
        "round": 1,
        "tool": "search_customer",
        "inline_text": "查找客户信息，找到 1 个客户：光大证券股份有限公司",
        "thinking": "用户想跟进光大证券...",
        "summary": "找到 1 个客户：光大证券股份有限公司"
    }
    
    step = ExecutionStepSchema(**step_data)
    
    assert step.inline_text == "查找客户信息，找到 1 个客户：光大证券股份有限公司"
    assert step.thinking == "用户想跟进光大证券..."
    assert step.summary == "找到 1 个客户：光大证券股份有限公司"

def test_execution_step_v2_progressive_disclosure():
    """测试 Progressive Disclosure 两层数据"""
    step_data = {
        "id": "step-002",
        "type": "waiting_for_user",
        "title": "创建跟进记录",
        "timestamp": "2026-06-25T10:30:02Z",
        "round": 2,
        "confirmationType": "confirmation",
        "riskLevel": "low",
        "summary_params": {"客户": "光大证券", "内容": "项目立项"},
        "detail_params": {
            "客户": {"value": "光大证券股份有限公司", "isEntity": True},
            "内容": {"value": "项目立项阶段，等待采购方式确认", "isEntity": False}
        }
    }
    
    step = ExecutionStepSchema(**step_data)
    
    assert step.confirmationType == "confirmation"
    assert step.riskLevel == "low"
    assert step.summary_params["客户"] == "光大证券"
    assert step.detail_params["客户"]["isEntity"] == True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest CRM-Server/tests/test_ai_conversation_schema.py -v`
Expected: FAIL with "TypeError: ExecutionStepSchema() got unexpected keyword argument 'inline_text'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/schemas/ai_conversation.py

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
    # ← V2 新增字段
    inline_text: Optional[str] = None       # Inline 显示文本
    thinking: Optional[str] = None          # AI 推理过程
    summary: Optional[str] = None           # 业务化摘要
    summary_params: Optional[Dict[str, str]] = None   # 摘要参数
    detail_params: Optional[Dict[str, Any]] = None    # 详情参数
    confirmationType: Optional[str] = None   # "disambiguation" | "confirmation" | "info_gap"
    riskLevel: Optional[str] = None          # "low" | "medium" | "high"
    options: Optional[List[Dict[str, Any]]] = None    # 候选列表
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest CRM-Server/tests/test_ai_conversation_schema.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/schemas/ai_conversation.py CRM-Server/tests/test_ai_conversation_schema.py
git commit -m "feat(schema): add V2 fields to ExecutionStepSchema (inline_text/progressive_disclosure)"
```

---

## Phase 2: 前端核心组件（P0）

### Task 5: InlineStep.vue

**Files:**
- Create: `CRM-Client/src/components/InlineStep.vue`
- Create: `CRM-Client/src/components/__tests__/InlineStep.test.ts`

**Interfaces:**
- Consumes: `ExecutionStep` 类型（从 `types/agentExecution.ts`）
- Produces: `<InlineStep />` 组件，props: `step`, `round`, `totalRounds`, `isCurrent`, `status`

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/InlineStep.test.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InlineStep from '../InlineStep.vue'

describe('InlineStep.vue', () => {
  it('renders Round Badge with correct format', () => {
    const wrapper = mount(InlineStep, {
      props: {
        round: 1,
        step: { id: 's1', type: 'tool_result', title: '查找客户信息' }
      }
    })
    
    expect(wrapper.find('.round-badge').text()).toBe('R1')
  })
  
  it('renders Round Badge with progress format R2/5', () => {
    const wrapper = mount(InlineStep, {
      props: {
        round: 2,
        totalRounds: 5,
        step: { id: 's1', type: 'tool_result', title: '查找商机' }
      }
    })
    
    expect(wrapper.find('.round-badge').text()).toBe('R2/5')
  })
  
  it('applies success color when status is success', () => {
    const wrapper = mount(InlineStep, {
      props: {
        status: 'success',
        step: { id: 's1', type: 'tool_result', inline_text: '查找成功' }
      }
    })
    
    expect(wrapper.find('.step-inline.success').exists()).toBe(true)
    expect(wrapper.find('.step-text').classes()).toContain('success')
  })
  
  it('merges inline_text from backend', () => {
    const wrapper = mount(InlineStep, {
      props: {
        step: {
          id: 's1',
          type: 'tool_result',
          inline_text: '查找客户信息，找到 1 个客户：光大证券股份有限公司'
        }
      }
    })
    
    expect(wrapper.find('.step-text').text()).toBe('查找客户信息，找到 1 个客户：光大证券股份有限公司')
  })
  
  it('has correct padding 3px 16px', () => {
    const wrapper = mount(InlineStep, {
      props: { step: { id: 's1', type: 'tool_result', inline_text: 'test' } }
    })
    
    const style = wrapper.find('.step-inline').attributes('style')
    // CSS 规范已定义，测试视觉回归
    expect(wrapper.find('.step-inline').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- InlineStep.test.ts`
Expected: FAIL with "Cannot find module '../InlineStep.vue'"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- CRM-Client/src/components/InlineStep.vue -->

<script setup lang="ts">
import { computed } from 'vue'
import type { ExecutionStep } from '@/types/agentExecution'

interface Props {
  step: ExecutionStep
  round?: number
  totalRounds?: number
  isCurrent?: boolean
  status?: 'success' | 'error' | 'warning' | 'loading'
}

const props = withDefaults(defineProps<Props>(), {
  isCurrent: false,
  status: 'success'
})

const roundBadgeText = computed(() => {
  if (props.totalRounds) {
    return `R${props.round}/${props.totalRounds}`
  }
  return props.round ? `R${props.round}` : ''
})

const inlineText = computed(() => {
  // 使用后端生成的 inline_text（推荐）
  if (props.step.inline_text) {
    return props.step.inline_text
  }
  // 前端后备合并 title + description
  const title = props.step.title || ''
  const desc = props.step.description || props.step.summary || ''
  return desc ? `${title}，${desc}` : title
})

const statusClass = computed(() => props.status)
</script>

<template>
  <div class="step-inline" :class="statusClass">
    <!-- Round Badge (inline) -->
    <span 
      v-if="roundBadgeText" 
      class="round-badge"
      :class="{ current: isCurrent }"
    >
      {{ roundBadgeText }}
    </span>
    
    <!-- 状态图标 (16px) -->
    <span class="status-icon" :class="statusClass">
      <el-icon>
        <CircleCheckFilled v-if="status === 'success'" />
        <CircleCloseFilled v-if="status === 'error'" />
        <WarningFilled v-if="status === 'warning'" />
        <Loading v-if="status === 'loading'" />
      </el-icon>
    </span>
    
    <!-- 步骤文本 (单行) -->
    <span class="step-text">{{ inlineText }}</span>
    
    <!-- Hover Tooltip (可选，后续任务实现) -->
    <HoverPreviewTooltip v-if="step.entity_info_detail" :rows="tooltipRows" />
  </div>
</template>

<style scoped lang="scss">
.step-inline {
  padding: 3px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  line-height: 1.4;
  cursor: default;
  transition: background 0.15s;
}

.step-inline:hover {
  background: rgba(74, 111, 165, 0.05);
}

.step-inline.success .step-text {
  color: #2B633C;
}

.step-inline.error .step-text {
  color: #7A2828;
}

.step-inline.warning .step-text {
  color: #7A4F1E;
}

.step-text {
  flex: 1;
}

.round-badge {
  display: inline-flex;
  padding: 2px 6px;
  background: rgba(74, 111, 165, 0.1);
  border-radius: 4px;
  font-size: 11px;
  color: #4A6FA5;
  font-weight: 500;
  margin-right: 6px;
}

.round-badge.current {
  background: #FFF6E8;
  color: #7A4F1E;
}

.status-icon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  flex-shrink: 0;
}

.status-icon.success {
  background: #2B633C;
  color: white;
}

.status-icon.error {
  background: #7A2828;
  color: white;
}

.status-icon.warning {
  background: #7A4F1E;
  color: white;
}

.status-icon.loading {
  background: #4A6FA5;
  color: white;
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- InlineStep.test.ts`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/InlineStep.vue CRM-Client/src/components/__tests__/InlineStep.test.ts
git commit -m "feat(ui): add InlineStep component with V2 compact design"
```

---

### Task 6: InlineCandidate.vue

**Files:**
- Create: `CRM-Client/src/components/InlineCandidate.vue`
- Create: `CRM-Client/src/components/__tests__/InlineCandidate.test.ts`

**Interfaces:**
- Consumes: `EntityCandidate` 类型（从后端 SSE）
- Produces: `<InlineCandidate />` 组件，props: `candidate`, `selected`

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/InlineCandidate.test.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InlineCandidate from '../InlineCandidate.vue'

describe('InlineCandidate.vue', () => {
  const mockCandidate = {
    id: 16,
    name: '光大证券股份有限公司',
    entity_info_inline: 'ID:16 · 金融 · 活跃'
  }
  
  it('renders entity name and inline info', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })
    
    expect(wrapper.find('.candidate-name').text()).toBe('光大证券股份有限公司')
    expect(wrapper.find('.entity-info-inline').text()).toBe('ID:16 · 金融 · 活跃')
  })
  
  it('has parentheses around entity info via CSS', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })
    
    // 括号由 CSS ::before/::after 生成，检查 class 存在
    expect(wrapper.find('.entity-info-inline').exists()).toBe(true)
  })
  
  it('toggles selected state on click', async () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })
    
    await wrapper.find('.candidate-inline').trigger('click')
    
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')[0]).toEqual([16])
  })
  
  it('selects candidate on Enter key', async () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })
    
    await wrapper.find('.candidate-inline').trigger('keydown', { key: 'Enter' })
    
    expect(wrapper.emitted('select')).toBeTruthy()
  })
  
  it('applies selected class when selected prop is true', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate, selected: true }
    })
    
    expect(wrapper.find('.candidate-inline.selected').exists()).toBe(true)
    expect(wrapper.find('.candidate-radio.selected').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- InlineCandidate.test.ts`
Expected: FAIL with "Cannot find module '../InlineCandidate.vue'"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- CRM-Client/src/components/InlineCandidate.vue -->

<script setup lang="ts">
interface EntityCandidate {
  id: number
  name: string
  entity_info_inline?: string
}

interface Props {
  candidate: EntityCandidate
  selected?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selected: false
})

const emit = defineEmits<{
  select: [id: number]
  cancel: []
}>()

const handleSelect = () => {
  emit('select', props.candidate.id)
}

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
</script>

<template>
  <div 
    class="candidate-inline"
    :class="{ selected: selected }"
    @click="handleSelect"
    @keydown="handleKeydown"
    tabindex="0"
    role="radio"
    :aria-checked="selected"
  >
    <!-- Radio (14px) -->
    <span class="candidate-radio" :class="{ selected: selected }">
      <span v-if="selected" class="radio-dot"></span>
    </span>
    
    <!-- 实体名称 -->
    <span class="candidate-name">{{ candidate.name }}</span>
    
    <!-- Entity Info Inline (括号由 CSS 生成) -->
    <span class="entity-info-inline">{{ candidate.entity_info_inline }}</span>
    
    <!-- Hover Tooltip (后续任务实现) -->
    <HoverPreviewTooltip v-if="candidate.entity_info_detail" :rows="tooltipRows" />
  </div>
</template>

<style scoped lang="scss">
.candidate-inline {
  padding: 6px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid transparent;
  transition: all 0.15s;
  font-size: 14px;
}

.candidate-inline:hover {
  background: #F5F5F5;
  border-color: #F2F3F5;
}

.candidate-inline:focus-visible {
  outline: 2px solid #4A6FA5;
  outline-offset: 1px;
}

.candidate-inline.selected {
  background: rgba(74, 111, 165, 0.1);
  border-color: #4A6FA5;
}

.candidate-radio {
  width: 14px;
  height: 14px;
  border: 1.5px solid #E5E5E5;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}

.candidate-radio.selected {
  border-color: #4A6FA5;
  background: #4A6FA5;
}

.radio-dot {
  width: 4px;
  height: 4px;
  background: white;
  border-radius: 50%;
}

.candidate-name {
  font-weight: 500;
  color: #1C1C1C;
}

.entity-info-inline {
  font-size: 12px;
  color: #636363;
  margin-left: 4px;
  
  &::before { content: '('; }
  &::after { content: ')'; }
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- InlineCandidate.test.ts`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/InlineCandidate.vue CRM-Client/src/components/__tests__/InlineCandidate.test.ts
git commit -m "feat(ui): add InlineCandidate component with one-line design + CSS parentheses"
```

---

### Task 7: HoverPreviewTooltip.vue

**Files:**
- Create: `CRM-Client/src/components/HoverPreviewTooltip.vue`
- Create: `CRM-Client/src/components/__tests__/HoverPreviewTooltip.test.ts`

**Interfaces:**
- Consumes: 无（通用组件）
- Produces: `<HoverPreviewTooltip />` 组件，props: `rows`, `minWidth`

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/HoverPreviewTooltip.test.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HoverPreviewTooltip from '../HoverPreviewTooltip.vue'

describe('HoverPreviewTooltip.vue', () => {
  const mockRows = [
    { label: '客户ID', value: '16' },
    { label: '行业', value: '金融服务业' },
    { label: '状态', value: '活跃' }
  ]
  
  it('renders tooltip rows correctly', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: {
        default: '<span class="trigger">Hover me</span>'
      }
    })
    
    expect(wrapper.findAll('.tooltip-row')).toHaveLength(3)
    expect(wrapper.find('.tooltip-label').text()).toBe('客户ID:')
    expect(wrapper.find('.tooltip-value').text()).toBe('16')
  })
  
  it('is hidden by default', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span>Trigger</span>' }
    })
    
    expect(wrapper.find('.hover-preview-tooltip').isVisible()).toBe(false)
  })
  
  it('shows on hover', async () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span class="trigger">Trigger</span>' }
    })
    
    await wrapper.find('.hover-preview').trigger('mouseenter')
    
    expect(wrapper.find('.hover-preview-tooltip').isVisible()).toBe(true)
  })
  
  it('has correct min-width 200px', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows, minWidth: 200 }
    })
    
    expect(wrapper.find('.hover-preview-tooltip').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- HoverPreviewTooltip.test.ts`
Expected: FAIL with "Cannot find module '../HoverPreviewTooltip.vue'"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- CRM-Client/src/components/HoverPreviewTooltip.vue -->

<script setup lang="ts">
interface TooltipRow {
  label: string
  value: string
}

interface Props {
  rows: TooltipRow[]
  minWidth?: number
}

const props = withDefaults(defineProps<Props>(), {
  minWidth: 200
})
</script>

<template>
  <div class="hover-preview">
    <slot />  <!-- 触发元素 -->
    
    <div 
      class="hover-preview-tooltip"
      :style="{ minWidth: `${minWidth}px` }"
    >
      <div v-for="row in rows" class="tooltip-row">
        <span class="tooltip-label">{{ row.label }}:</span>
        <span class="tooltip-value">{{ row.value }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.hover-preview {
  position: relative;
}

.hover-preview-tooltip {
  position: absolute;
  left: 0;
  top: 100%;
  margin-top: 4px;
  background: white;
  border: 1px solid #E5E5E5;
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 12px;
  z-index: 100;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s, visibility 0.15s;
  white-space: nowrap;
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
  color: #636363;
}

.tooltip-value {
  color: #1C1C1C;
}

// 无障碍：减少动画
@media (prefers-reduced-motion: reduce) {
  .hover-preview-tooltip {
    transition: none;
  }
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- HoverPreviewTooltip.test.ts`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/HoverPreviewTooltip.vue CRM-Client/src/components/__tests__/HoverPreviewTooltip.test.ts
git commit -m "feat(ui): add HoverPreviewTooltip component for V2 inline details"
```

---

### Task 8: CompactConfirmSummary.vue

**Files:**
- Create: `CRM-Client/src/components/CompactConfirmSummary.vue`
- Create: `CRM-Client/src/components/__tests__/CompactConfirmSummary.test.ts`

**Interfaces:**
- Consumes: `step.params`, `step.riskLevel`, `step.summary_params`, `step.detail_params`
- Produces: `<CompactConfirmSummary />` 组件，Progressive Disclosure 功能

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/CompactConfirmSummary.test.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CompactConfirmSummary from '../CompactConfirmSummary.vue'

describe('CompactConfirmSummary.vue', () => {
  const mockParams = {
    客户: { value: '光大证券', isEntity: true },
    内容: { value: '项目立项阶段', isEntity: false },
    方式: { value: '电话沟通', isEntity: false }
  }
  
  it('shows summary by default', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })
    
    expect(wrapper.find('.confirmation-summary').exists()).toBe(true)
    expect(wrapper.find('.confirmation-expanded').exists()).toBe(false)
  })
  
  it('shows expanded params on click', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })
    
    await wrapper.find('.confirmation-summary').trigger('click')
    
    expect(wrapper.find('.confirmation-summary.expanded').exists()).toBe(true)
    expect(wrapper.find('.confirmation-expanded').isVisible()).toBe(true)
  })
  
  it('applies high-risk border style', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '删除客户', params: mockParams, riskLevel: 'high' }
    })
    
    expect(wrapper.find('.confirmation-summary.high-risk').exists()).toBe(true)
  })
  
  it('applies low-risk border style', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, riskLevel: 'low' }
    })
    
    expect(wrapper.find('.confirmation-summary.low-risk').exists()).toBe(true)
  })
  
  it('shows confirmed state', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, status: 'confirmed' }
    })
    
    expect(wrapper.find('.confirmation-summary.confirmed').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- CompactConfirmSummary.test.ts`
Expected: FAIL with "Cannot find module '../CompactConfirmSummary.vue'"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- CRM-Client/src/components/CompactConfirmSummary.vue -->

<script setup lang="ts">
import { ref, computed } from 'vue'

interface ParamValue {
  value: string
  isEntity?: boolean
}

interface Props {
  round?: number
  title: string
  params: Record<string, ParamValue>
  riskLevel?: 'low' | 'medium' | 'high'
  status?: 'waiting' | 'confirmed' | 'cancelled'
}

const props = withDefaults(defineProps<Props>(), {
  riskLevel: 'medium',
  status: 'waiting'
})

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const expanded = ref(false)

const toggleExpand = () => {
  expanded.value = !expanded.value
}

const riskLevelClass = computed(() => {
  return props.riskLevel === 'low' ? 'low-risk' : 
         props.riskLevel === 'high' ? 'high-risk' : ''
})

const statusClass = computed(() => props.status)

const statusLabel = computed(() => {
  return props.status === 'confirmed' ? '已确认' :
         props.status === 'cancelled' ? '已取消' : '待确认'
})

const inlineParams = computed(() => {
  // 摘要参数：最多 3 个
  const keys = Object.keys(props.params).slice(0, 3)
  return keys.map(k => `${k}: ${props.params[k].value}`).join(' · ')
})

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<template>
  <!-- 摘要状态 -->
  <div 
    class="confirmation-summary"
    :class="[riskLevelClass, statusClass, { expanded: expanded }]"
    @click="toggleExpand"
  >
    <span v-if="round" class="round-badge current">R{{ round }}</span>
    <span class="status-icon warning">⚠</span>
    <span class="confirm-label" :class="statusClass">{{ statusLabel }}</span>
    <span class="params-inline">{{ title }} · {{ inlineParams }}</span>
    <span class="expand-hint">{{ expanded ? '↑ 收起' : '[点击展开详情]' }}</span>
  </div>
  
  <!-- 展开状态 -->
  <div v-if="expanded" class="confirmation-expanded">
    <div class="expanded-params">
      <div v-for="(value, key) in params" class="expanded-param-row">
        <span class="expanded-param-name">{{ key }}：</span>
        <span 
          class="expanded-param-value"
          :class="{ entity: value.isEntity }"
          @click.stop="value.isEntity && $emit('entityClick', value)"
        >
          {{ value.value }}
        </span>
      </div>
    </div>
    <div class="action-buttons">
      <button class="btn-sm btn-confirm" @click="handleConfirm">确认执行</button>
      <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.confirmation-summary {
  padding: 6px 16px;
  background: #FFF6E8;
  border-left: 3px solid #7A4F1E;
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
  filter: brightness(0.98);
}

.confirmation-summary.high-risk {
  border-left-width: 4px;
  border-left-color: #7A2828;
}

.confirmation-summary.low-risk {
  border-left-width: 2px;
  border-left-color: #2B633C;
}

.confirmation-summary.confirmed {
  background: #EDF7EF;
  border-left-color: #2B633C;
}

.confirm-label {
  font-size: 12px;
  color: #7A4F1E;
  font-weight: 500;
  background: rgba(122, 79, 30, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.confirmation-summary.confirmed .confirm-label {
  color: #2B633C;
  background: rgba(43, 99, 60, 0.1);
}

.params-inline {
  flex: 1;
}

.expand-hint {
  font-size: 12px;
  color: #636363;
}

.confirmation-expanded {
  padding: 8px 16px;
  background: #FFF6E8;
  border-left: 3px solid #7A4F1E;
  border-radius: 4px;
  margin: 4px 16px;
}

.expanded-params {
  font-size: 12px;
  background: white;
  padding: 8px;
  border-radius: 4px;
}

.expanded-param-row {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.expanded-param-value.entity {
  color: #4A6FA5;
  cursor: pointer;
}

.expanded-param-value.entity:hover {
  text-decoration: underline;
}

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

.btn-confirm {
  background: #4A6FA5;
  color: white;
}

.btn-confirm:hover {
  background: #4065A0;
}

.btn-cancel {
  background: #F5F5F5;
  color: #3A3A3A;
  border: 1px solid #E5E5E5;
}

.btn-cancel:hover {
  background: #F5F5F5;
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- CompactConfirmSummary.test.ts`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/CompactConfirmSummary.vue CRM-Client/src/components/__tests__/CompactConfirmSummary.test.ts
git commit -m "feat(ui): add CompactConfirmSummary with Progressive Disclosure"
```

---

## Phase 3: 前端容器组件（P0）

### Task 9: CollapsedView.vue（重写）

**Files:**
- Modify: `CRM-Client/src/components/CollapsedView.vue`（重写）
- Modify: `CRM-Client/src/components/__tests__/CollapsedView.test.ts`（更新测试）

**Interfaces:**
- Consumes: `executionSteps`, `currentRound`, `totalRounds`
- Produces: 36px 高度收起状态 + Round Badge inline

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/CollapsedView.test.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CollapsedView from '../CollapsedView.vue'

describe('CollapsedView.vue (V2)', () => {
  it('has height 36px', () => {
    const wrapper = mount(CollapsedView, {
      props: {
        round: 2,
        totalRounds: 5,
        status: 'loading',
        stepText: '正在查询商机...'
      }
    })
    
    expect(wrapper.find('.collapsed-view').exists()).toBe(true)
    // CSS 规范已定义 height: 36px
  })
  
  it('shows Round Badge with progress format', () => {
    const wrapper = mount(CollapsedView, {
      props: {
        round: 2,
        totalRounds: 5,
        status: 'success',
        stepText: '查找成功'
      }
    })
    
    expect(wrapper.find('.round-badge').text()).toBe('R2/5')
  })
  
  it('emits click event on click', async () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })
    
    await wrapper.find('.collapsed-view').trigger('click')
    
    expect(wrapper.emitted('click')).toBeTruthy()
  })
  
  it('toggles expand on Enter key', async () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })
    
    await wrapper.find('.collapsed-view').trigger('keydown', { key: 'Enter' })
    
    expect(wrapper.emitted('click')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- CollapsedView.test.ts`
Expected: FAIL（现有组件不符合 V2 规范）

- [ ] **Step 3: Write implementation（重写）**

```vue
<!-- CRM-Client/src/components/CollapsedView.vue -->

<script setup lang="ts">
interface Props {
  round?: number
  totalRounds?: number
  status: 'empty' | 'loading' | 'success' | 'error' | 'partial'
  stepText: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
}>()

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' || event.key === 'Space') {
    emit('click')
    event.preventDefault()
  }
}

const roundBadgeText = computed(() => {
  if (props.totalRounds) {
    return `R${props.round}/${props.totalRounds}`
  }
  return props.round ? `R${props.round}` : ''
})
</script>

<template>
  <div 
    class="collapsed-view"
    @click="emit('click')"
    @keydown="handleKeydown"
    tabindex="0"
    role="button"
    aria-expanded="false"
    aria-label="AI 执行进度"
  >
    <!-- Round Badge -->
    <span v-if="roundBadgeText" class="round-badge current">
      {{ roundBadgeText }}
    </span>
    
    <!-- 状态图标 (16px) -->
    <span class="status-icon" :class="status">
      <el-icon>
        <Loading v-if="status === 'loading'" />
        <CircleCheckFilled v-if="status === 'success'" />
        <CircleCloseFilled v-if="status === 'error'" />
        <WarningFilled v-if="status === 'partial'" />
      </el-icon>
    </span>
    
    <!-- 步骤文本 -->
    <span class="step-text">{{ stepText }}</span>
    
    <!-- 展开提示 -->
    <span class="expand-hint">点击展开 →</span>
  </div>
</template>

<style scoped lang="scss">
.collapsed-view {
  padding: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.2s;
  height: 36px;
}

.collapsed-view:hover {
  background: rgba(74, 111, 165, 0.05);
}

.collapsed-view:focus-visible {
  outline: 2px solid #4A6FA5;
  outline-offset: 2px;
}

.round-badge {
  display: inline-flex;
  padding: 2px 6px;
  background: #FFF6E8;
  border-radius: 4px;
  font-size: 11px;
  color: #7A4F1E;
  font-weight: 500;
  margin-right: 6px;
}

.status-icon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.status-icon.loading {
  background: #4A6FA5;
  color: white;
  animation: rotate 1s linear infinite;
}

.status-icon.success {
  background: #2B633C;
  color: white;
}

.status-icon.error {
  background: #7A2828;
  color: white;
}

.step-text {
  flex: 1;
  font-size: 14px;
  color: #1C1C1C;
}

.expand-hint {
  font-size: 12px;
  color: #636363;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- CollapsedView.test.ts`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/CollapsedView.vue CRM-Client/src/components/__tests__/CollapsedView.test.ts
git commit -m "feat(ui): rewrite CollapsedView to V2 36px compact design"
```

---

### Task 10: ExpandedView.vue（重写）

**Files:**
- Modify: `CRM-Client/src/components/ExpandedView.vue`（重写）
- Modify: `CRM-Client/src/components/__tests__/ExpandedView.test.ts`（更新测试）

**Interfaces:**
- Consumes: `InlineStep`, `InlineCandidate`, `CompactConfirmSummary`, `CompactInfoGap`
- Produces: max-height 280px 展开轨迹

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/ExpandedView.test.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ExpandedView from '../ExpandedView.vue'

describe('ExpandedView.vue (V2)', () => {
  const mockSteps = [
    { id: 's1', type: 'tool_result', round: 1, inline_text: '查找客户信息，找到 1 个客户' },
    { id: 's2', type: 'tool_result', round: 2, inline_text: '查找商机，找到 2 个商机' }
  ]
  
  it('renders InlineStep components', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps, currentRound: 2 }
    })
    
    expect(wrapper.findAllComponents({ name: 'InlineStep' })).toHaveLength(2)
  })
  
  it('has max-height 280px', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })
    
    expect(wrapper.find('.expanded-view').exists()).toBe(true)
    // CSS 规范已定义 max-height: 280px
  })
  
  it('emits collapse on header click', async () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })
    
    await wrapper.find('.expand-header').trigger('click')
    
    expect(wrapper.emitted('collapse')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- ExpandedView.test.ts`
Expected: FAIL（现有组件不符合 V2 规范）

- [ ] **Step 3: Write implementation（重写）**

```vue
<!-- CRM-Client/src/components/ExpandedView.vue -->

<script setup lang="ts">
import InlineStep from './InlineStep.vue'
import InlineCandidate from './InlineCandidate.vue'
import CompactConfirmSummary from './CompactConfirmSummary.vue'
import CompactInfoGap from './CompactInfoGap.vue'
import type { ExecutionStep } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  currentRound?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  collapse: []
  confirm: [stepId: string]
  cancel: []
  submit: [value: string]
}>()

const getStepStatus = (step: ExecutionStep) => {
  if (step.success) return 'success'
  if (step.error) return 'error'
  if (step.type === 'waiting_for_user') return 'warning'
  return 'loading'
}
</script>

<template>
  <div class="expanded-view">
    <!-- 收起按钮 -->
    <div class="expand-header" @click="emit('collapse')">
      <span>↑ 收起</span>
    </div>
    
    <!-- 滚动容器 -->
    <div class="expanded-content">
      <template v-for="step in steps" :key="step.id">
        
        <!-- Inline Step -->
        <InlineStep
          :step="step"
          :round="step.round"
          :is-current="step.round === currentRound"
          :status="getStepStatus(step)"
        />
        
        <!-- waiting_for_user 类型处理 -->
        <template v-if="step.type === 'waiting_for_user'">
          
          <!-- InlineCandidate: 候选选择 -->
          <template v-if="step.confirmationType === 'disambiguation' && step.options?.length > 1">
            <InlineCandidate
              v-for="candidate in step.options"
              :key="candidate.id"
              :candidate="candidate"
              @select="selectedCandidate = candidate.id"
            />
            
            <div class="action-buttons-inline">
              <button class="btn-sm btn-confirm" @click="emit('confirm', step.id)">确认选择</button>
              <button class="btn-sm btn-cancel" @click="emit('cancel')">取消</button>
            </div>
          </template>
          
          <!-- CompactConfirmSummary: 操作确认 -->
          <template v-else-if="step.confirmationType === 'confirmation'">
            <CompactConfirmSummary
              :round="step.round"
              :title="step.title"
              :params="step.params"
              :risk-level="step.riskLevel"
              @confirm="emit('confirm', step.id)"
              @cancel="emit('cancel')"
            />
          </template>
          
          <!-- CompactInfoGap: 信息补全 -->
          <template v-else-if="step.confirmationType === 'info_gap'">
            <CompactInfoGap
              :round="step.round"
              :title="step.title"
              :filled-params="step.summary_params"
              :missing-field="step.missing_fields?.[0]"
              @submit="emit('submit', $event)"
              @cancel="emit('cancel')"
            />
          </template>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.expanded-view {
  max-height: 280px;
  overflow-y: auto;
}

.expand-header {
  padding: 4px 16px;
  display: flex;
  align-items: center;
  color: #636363;
  font-size: 12px;
  cursor: pointer;
  background: #F5F5F5;
}

.expand-header:hover {
  background: rgba(74, 111, 165, 0.05);
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

.btn-sm {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  border: none;
  transition: background 0.15s;
}

.btn-confirm {
  background: #4A6FA5;
  color: white;
}

.btn-cancel {
  background: #F5F5F5;
  color: #3A3A3A;
  border: 1px solid #E5E5E5;
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- ExpandedView.test.ts`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/ExpandedView.vue CRM-Client/src/components/__tests__/ExpandedView.test.ts
git commit -m "feat(ui): rewrite ExpandedView to V2 Inline Steps trajectory"
```

---

### Task 11: CompactExecutionLog.vue（重写）

**Files:**
- Modify: `CRM-Client/src/components/CompactExecutionLog.vue`（重写）
- Modify: `CRM-Client/src/components/__tests__/CompactExecutionLog.test.ts`（更新测试）

**Interfaces:**
- Consumes: `CollapsedView`, `ExpandedView`, `EmptyState`, `SmartBoundaryLine`
- Produces: 完整容器 + 自动收起逻辑 + 键盘导航

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/CompactExecutionLog.test.ts

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CompactExecutionLog from '../CompactExecutionLog.vue'

describe('CompactExecutionLog.vue (V2)', () => {
  it('shows empty state when no steps', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: [], status: 'empty' }
    })
    
    expect(wrapper.findComponent({ name: 'EmptyState' }).exists()).toBe(true)
  })
  
  it('shows collapsed view by default', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: [{ id: 's1' }], status: 'success' }
    })
    
    expect(wrapper.findComponent({ name: 'CollapsedView' }).exists()).toBe(true)
  })
  
  it('expands on collapsed view click', async () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: [{ id: 's1' }], status: 'success' }
    })
    
    await wrapper.findComponent({ name: 'CollapsedView' }).vm.$emit('click')
    
    expect(wrapper.findComponent({ name: 'ExpandedView' }).exists()).toBe(true)
  })
  
  it('auto collapses after 3 seconds', async () => {
    vi.useFakeTimers()
    
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: [{ id: 's1' }],
        status: 'success',
        autoCollapse: true,
        autoCollapseDelay: 3000
      }
    })
    
    // 设置展开状态
    wrapper.vm.expanded = true
    
    // 快进 3 秒
    vi.advanceTimersByTime(3000)
    
    expect(wrapper.vm.expanded).toBe(false)
    
    vi.useRealTimers()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- CompactExecutionLog.test.ts`
Expected: FAIL（现有组件不符合 V2 规范）

- [ ] **Step 3: Write implementation（重写）**

```vue
<!-- CRM-Client/src/components/CompactExecutionLog.vue -->

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import SmartBoundaryLine from './SmartBoundaryLine.vue'
import EmptyState from './EmptyState.vue'
import CollapsedView from './CollapsedView.vue'
import ExpandedView from './ExpandedView.vue'
import type { ExecutionStep } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  currentRound?: number
  totalRounds?: number
  status: 'empty' | 'loading' | 'success' | 'error' | 'partial'
  autoCollapse?: boolean
  autoCollapseDelay?: number
}

const props = withDefaults(defineProps<Props>(), {
  autoCollapse: true,
  autoCollapseDelay: 3000
})

const emit = defineEmits<{
  confirm: [stepId: string]
  cancel: []
  submit: [value: string]
}>()

const expanded = ref(false)
const autoCollapseTimer = ref<number | null>(null)

const boundaryStatus = computed(() => {
  return props.status === 'loading' ? 'executing' :
         props.status === 'success' ? 'success' :
         props.status === 'error' ? 'error' : ''
})

const currentStepText = computed(() => {
  const currentStep = props.steps.find(s => s.round === props.currentRound)
  return currentStep?.inline_text || '正在处理...'
})

const toggleExpand = () => {
  expanded.value = !expanded.value
  
  if (!expanded.value) {
    cancelAutoCollapse()
  }
}

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

const handleConfirm = (stepId: string) => {
  emit('confirm', stepId)
}

const handleCancel = () => {
  emit('cancel')
}

const handleSubmit = (value: string) => {
  emit('submit', value)
}

onUnmounted(() => {
  cancelAutoCollapse()
})
</script>

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
      :status="status"
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

<style scoped lang="scss">
.agent-log {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- CompactExecutionLog.test.ts`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/CompactExecutionLog.vue CRM-Client/src/components/__tests__/CompactExecutionLog.test.ts
git commit -m "feat(ui): rewrite CompactExecutionLog with auto-collapse + keyboard navigation"
```

---

## Phase 4: 清理旧组件

### Task 12: 删除旧组件

**Files:**
- Delete: `CRM-Client/src/components/StatusCard.vue`
- Delete: `CRM-Client/src/components/ai-assistant/PreviewCard.vue`
- Delete: `CRM-Client/src/components/ai-assistant/PreviewField.vue`

- [ ] **Step 1: Remove StatusCard.vue**

```bash
rm CRM-Client/src/components/StatusCard.vue
rm CRM-Client/src/components/__tests__/StatusCard.test.ts
```

- [ ] **Step 2: Remove PreviewCard.vue**

```bash
rm CRM-Client/src/components/ai-assistant/PreviewCard.vue
rm CRM-Client/src/components/ai-assistant/__tests__/PreviewCard.test.ts
```

- [ ] **Step 3: Remove PreviewField.vue**

```bash
rm CRM-Client/src/components/ai-assistant/PreviewField.vue
rm CRM-Client/src/components/ai-assistant/__tests__/PreviewField.test.ts
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove V1 components (StatusCard/PreviewCard/PreviewField)"
```

---

## Self-Review

### 1. Spec Coverage ✅

| 规范要求 | 对应任务 | 状态 |
|----------|----------|------|
| InlineStep.vue | Task 5 | ✅ |
| InlineCandidate.vue | Task 6 | ✅ |
| HoverPreviewTooltip.vue | Task 7 | ✅ |
| CompactConfirmSummary.vue | Task 8 | ✅ |
| CollapsedView.vue (36px) | Task 9 | ✅ |
| ExpandedView.vue (280px) | Task 10 | ✅ |
| CompactExecutionLog.vue (auto-collapse) | Task 11 | ✅ |
| SSE waiting_for_user V2 | Task 1 | ✅ |
| EntityCandidate V2 | Task 2 | ✅ |
| SSE tool_call/tool_result V2 | Task 3 | ✅ |
| ExecutionStepSchema V2 | Task 4 | ✅ |

### 2. Placeholder Scan ✅

- 无 TBD/TODO
- 无 "implement later"
- 所有测试代码完整
- 所有实现代码完整

### 3. Type Consistency ✅

- `EntityCandidate.id: number` 一致
- `ExecutionStep.inline_text: string` 一致
- `confirmationType: "disambiguation" | "confirmation" | "info_gap"` 一致

---

Plan complete and saved to `CRM-Docs/specs/AI-EXECUTION-LOG-V2-IMPLEMENTATION-PLAN.md`

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
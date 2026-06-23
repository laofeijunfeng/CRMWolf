---
status: completed
created: 2026-06-09
updated: 2026-06-09
related_plan: -
related_pr: -
---

# CRMWolf AI Agent 增强需求文档

> 版本：2.0 | 创建日期：2026-06-09 | 状态：需求确认
> 替代文档：AI-TOOL-ENHANCEMENT-REQUIREMENTS.md + AI-INTENT-RECOGNITION-OPTIMIZATION.md

---

## 一、背景与核心痛点

### 1.1 现状

CRMWolf 已实现 Function Calling 架构（`ai_tool_service.py`），支持 AI 通过工具调用执行业务操作：

| 模块 | 工具数量 | 状态 |
|------|---------|------|
| 线索管理 | 9 个 | ✅ 已实现 |
| 客户管理 | 4 个 | ✅ 已实现 |
| 商机管理 | 8 个 | ✅ 已实现 |
| 合同管理 | 0 个 | ❌ 未实现 |
| 回款管理 | 0 个 | ❌ 未实现 |
| 发票管理 | 0 个 | ❌ 未实现 |

### 1.2 核心痛点

#### 痛点 1：单轮单工具调用

**表现：** 用户一段话包含多个意图，但 AI 只执行第一个工具

```
用户输入："今天已签订合同，30万，50人1年订阅"

期望行为：
  1. 创建跟进记录 ✅
  2. 标记商机赢单 ✅
  3. 创建合同记录 ✅

实际行为：
  只执行 create_follow_up，后续两个动作丢失

根本原因：tool_calls[0] 只取第一个工具，无多轮循环机制
```

#### 痛点 2：无上下文预加载

**表现：** AI 在执行工具前不知道客户是否有商机、商机状态等关键信息

```
用户输入："客户确认采购了"

AI 需要判断：
  - 这个客户有没有商机？
  - 有商机 → 推到 100%
  - 无商机 → 创建商机（需补充信息）

实际问题：
  AI 不知道客户是否有商机，盲目调用工具或错误决策
```

#### 痛点 3：工具描述不充分

**表现：** 工具描述太简单，AI 无法理解"何时使用"

```python
# 当前描述
"description": "添加客户跟进记录"

# 问题：AI 不知道"沟通内容"应该用跟进工具
# 导致："微信确认采购" → 错误调用 query_opportunities
```

#### 痛点 4：实体歧义无处理

**表现：** 客户有 2 个商机时，AI 不知道操作哪个

```
用户输入："已和客户签订合同"

问题：客户有 2 个跟进中商机，AI 不知道是哪个
结果：盲目选择第一个，或直接报错
```

#### 痛点 5：无暂停-等待机制

**表现：** AI 无法在缺少信息时暂停，等待用户补充后继续

```
用户输入："客户确认采购了"

期望流程：
  1. AI 发现无商机 → 询问用户补充产品、金额
  2. 用户补充 → AI 创建商机
  3. AI 询问是否创建合同
  4. 用户确认 → AI 创建合同

实际：缺少信息直接报错，或盲目使用默认值
```

---

## 二、需求目标与架构设计

### 2.1 核心目标

| 目标 | 说明 |
|------|------|
| **完整业务链路** | 补充合同、回款、发票模块工具，覆盖完整销售流程 |
| **多意图自动编排** | AI 从一段话提取多个意图，自动编排工具调用顺序 |
| **上下文预加载** | 工具调用前获取必要上下文（商机状态、客户信息等） |
| **Human-in-the-Loop** | 关键节点暂停等待用户确认/补充信息 |
| **实体歧义消解** | 多候选实体时返回候选列表让用户选择 |
| **意图精准识别** | 工具描述包含"何时使用"，AI 自行判断意图 |

### 2.2 核心架构：ReAct Agent + Human-in-the-Loop

```
用户输入
    ↓
┌─────────────────────────────────────────────────────────┐
│  AI Agent Loop (ReAct Pattern)                          │
│                                                         │
│  Think → Act → Observe → Decide → Repeat/Exit           │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 1. THINK (推理)                                    │ │
│  │    分析意图，获取上下文，规划下一步                │ │
│  └───────────────────────────────────────────────────┘ │
│                        ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 2. ACT (行动)                                      │ │
│  │    调用工具 / 询问用户                             │ │
│  └───────────────────────────────────────────────────┘ │
│                        ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 3. OBSERVE (观察)                                  │ │
│  │    获取执行结果，更新上下文                        │ │
│  └───────────────────────────────────────────────────┘ │
│                        ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 4. DECIDE (决策)                                   │ │
│  │    完成？继续？暂停等用户？                        │ │
│  └───────────────────────────────────────────────────┘ │
│                        ↓                               │
│     ┌──────────┬──────────┬──────────┐               │
│     │ 完成     │ 继续     │ 等待用户  │               │
│     ↓          ↓          ↓                          │
│   返回结果   下一轮循环   暂停，等待用户输入          │
│                        ↓                               │
│                   用户回复                             │
│                        ↓                               │
│                   继续循环                             │
└─────────────────────────────────────────────────────────┘
    ↓
最终结果
```

### 2.3 设计原则

| 原则 | 说明 |
|------|------|
| **AI 自主决策** | 不硬编码规则，让 AI 根据上下文自主判断 |
| **工具描述驱动** | 工具描述包含"何时使用"，AI 自行选择 |
| **上下文优先** | 工具调用前先获取必要上下文 |
| **关键节点确认** | 重要操作（创建合同、回款）需用户确认 |
| **智能暂停** | 缺少信息时主动询问，不盲目执行 |
| **安全降级** | 支持配置开关，可降级到原有单工具模式 |

---

## 三、功能需求详细设计

### 3.1 Phase 1：工具描述优化 + 补充完整工具

#### 3.1.1 工具描述规范

每个工具描述必须包含：

```python
{
    "name": "工具名",
    "description": """{一句话概述}

适用于：{触发场景列表}
触发条件：{明确的触发条件}
示例：{典型输入示例}

注意：{容易混淆的场景说明}
""",
    "parameters": {...}
}
```

#### 3.1.2 核心工具描述示例

**跟进工具（follow_up_customer）**

```python
{
    "name": "create_follow_up",
    "description": """记录与客户的沟通互动情况。

适用于：用户描述沟通内容、业务进展、客户反馈、下一步安排
触发条件：用户提到与客户的互动（微信、电话、拜访、邮件等）
示例：
- "微信确认了采购意向"
- "电话讨论了报价方案"
- "客户说下周签约"
- "今天拜访客户，聊了需求"
- "客户反馈已经确认采购"

注意：如果用户要"查看/搜索"信息，请用查询工具，而非跟进。
""",
    "parameters": {
        "customer_id": {"type": "string", "description": "客户ID（从上下文获取）"},
        "content": {"type": "string", "description": "沟通内容详情"},
        "follow_up_type": {"type": "string", "enum": ["wechat", "phone", "visit", "email", "other"]}
    }
}
```

**查询商机工具（query_opportunities）**

```python
{
    "name": "query_opportunities",
    "description": """搜索查看商机列表。

适用于：用户明确要"查看/搜索/找"商机
触发条件：用户使用"看看"、"查一下"、"找找"、"搜索"等查看类动词
示例：
- "看看有哪些商机"
- "查一下跟进中的商机"
- "找找这个客户的商机"

注意：如果用户描述的是沟通内容而非查看需求，请使用跟进工具。
""",
    "parameters": {
        "status": {"type": "string", "enum": ["following", "won", "lost"]},
        "keyword": {"type": "string"}
    }
}
```

**创建商机工具（create_opportunity）**

```python
{
    "name": "create_opportunity",
    "description": """创建新的销售商机。

适用于：用户明确要"创建/新建/添加"商机，或客户有购买意向但无商机
触发条件：
- 用户明确说"创建商机"
- 客户确认采购但无商机记录
示例：
- "创建一个商机"
- "新建商机"
- "客户确认采购了"（若无商机）

注意：商机名称格式为 {客户名}-{用户数}人{年限}年订阅
""",
    "parameters": {
        "customer_id": {"type": "string"},
        "product": {"type": "string", "description": "产品名称"},
        "amount": {"type": "number", "description": "预计金额"},
        "probability": {"type": "integer", "description": "成交概率 0-100"}
    },
    "risk_level": "medium"  # 需用户确认产品、金额
}
```

**更新商机阶段工具（update_opportunity_stage）**

```python
{
    "name": "update_opportunity_stage",
    "description": """更新商机阶段和成交概率。

适用于：客户购买意向发生变化（加强、减弱、确认、放弃）
触发条件：
- 客户明确表示"确认采购"、"已签约" → probability=100%
- 客户表示"有意向"、"考虑中" → probability=50-80%
- 客户表示"暂不考虑" → probability=20%
示例：
- "客户确认采购了"
- "客户已签约"
- "客户说很有意向"

注意：确认采购时 probability 应设为 100%，表示已成交
""",
    "parameters": {
        "opportunity_id": {"type": "string"},
        "stage": {"type": "string"},
        "probability": {"type": "integer"}
    }
}
```

#### 3.1.3 补充合同、回款、发票工具

**合同模块工具**

| 工具名 | 描述 | 参数 | 风险等级 |
|--------|------|------|----------|
| `create_contract` | 创建合同。适用于客户已签约，需要正式记录合同信息。触发条件：用户说"签合同"、"创建合同"、"已签约"。 | `customer_id`, `opportunity_id`, `contract_name`, `total_amount`, `user_count`, `license_type`, `subscription_years`, `signing_date` | HIGH（需确认） |
| `query_contracts` | 搜索查看合同列表。适用于用户要查看/搜索合同。 | `status`, `customer_name`, `keyword` | LOW |
| `get_contract_detail` | 获取合同详情。适用于用户要查看具体合同信息。 | `contract_id` | LOW |
| `update_contract_status` | 更新合同状态。适用于合同状态变更（生效、到期、终止）。 | `contract_id`, `status` | MEDIUM |

**回款模块工具**

| 工具名 | 描述 | 参数 | 风险等级 |
|--------|------|------|----------|
| `create_payment_plan` | 创建回款计划。适用于签订合同后设置回款阶段。 | `contract_id`, `stage_name`, `planned_amount`, `due_date` | MEDIUM |
| `create_payment_record` | 登记回款。适用于客户已付款，记录实际回款信息。 | `payment_plan_id`, `actual_amount`, `payment_date` | HIGH（财务操作） |
| `query_payment_records` | 查询回款记录。适用于查看回款情况。 | `contract_id`, `status` | LOW |

**发票模块工具**

| 工具名 | 描述 | 参数 | 风险等级 |
|--------|------|------|----------|
| `create_invoice_application` | 申请开票。适用于客户要求开具发票。 | `contract_id`, `invoice_amount`, `invoice_type`, `invoice_title_id` | HIGH（财务操作） |
| `query_invoice_applications` | 查询开票申请。适用于查看开票情况。 | `contract_id`, `status` | LOW |

#### 3.1.4 特殊工具：用户交互工具

**询问用户工具（ask_user）**

```python
{
    "name": "ask_user",
    "description": """向用户提问以获取缺失信息或确认操作。

适用于：
- 缺少必要字段时询问用户补充
- 重要操作前需要用户确认
- 多个候选实体需要用户选择
- 需要用户决策的场景

触发条件：AI 判断当前信息不足以继续，或操作需要用户确认
示例：
- 缺少商机信息 → "请补充产品名称和预计金额"
- 多个商机 → "请选择是哪个商机"
- 创建合同 → "是否现在创建合同？"

注意：此工具会暂停 Agent 循环，等待用户回复后继续
""",
    "parameters": {
        "question": {"type": "string", "description": "向用户提出的问题"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "可选的选项列表（用于选择场景）"},
        "missing_fields": {"type": "array", "items": {"type": "string"}, "description": "缺失的字段列表"}
    },
    "halts_loop": true  # 标记：调用此工具会暂停循环
}
```

**获取上下文工具（get_entity_context）**

```python
{
    "name": "get_entity_context",
    "description": """获取实体的完整上下文信息。

适用于：执行业务操作前，获取必要上下文
触发条件：
- 用户提到客户，需要知道商机状态
- 用户要签合同，需要知道合同依赖信息
- AI 需要判断是否需要创建商机等

返回信息：
- 客户：商机列表、最近跟进、合同列表
- 商机：关联客户、合同状态、回款状态
- 合同：回款计划、发票状态

注意：应在其他业务工具调用前先调用此工具获取上下文
""",
    "parameters": {
        "entity_type": {"type": "string", "enum": ["customer", "opportunity", "contract"]},
        "entity_id": {"type": "string"}
    }
}
```

---

### 3.2 Phase 2：上下文预加载机制

#### 3.2.1 目标

在 Agent 第一轮 Think 时，自动加载必要上下文，而非等工具调用后才知道。

#### 3.2.2 实现方案

```python
class CRMAgent:
    async def process(self, user_input: str, entity_context: dict):
        # Step 1: 根据实体类型预加载上下文
        if entity_context["entity_type"] == "customer":
            context = await self.load_customer_context(
                entity_context["entity_id"]
            )
            # context 包含：
            # - customer_info: 客户基础信息
            # - opportunities: 商机列表（ID、名称、金额、状态）
            # - recent_follow_ups: 最近 5 条跟进
            # - contracts: 合同列表
        
        # Step 2: 将上下文注入系统提示词
        system_prompt = self._build_system_prompt(context)
        
        # Step 3: 开始 Agent 循环
        ...
```

#### 3.2.3 上下文注入示例

```python
def _build_system_prompt(self, context: dict) -> str:
    return """你是 CRMWolf 的 AI 助手，帮助用户管理销售业务。

【当前上下文】（已为你预加载）
- 操作对象：客户 #{customer_id}（{customer_name}）
- 客户状态：{status}
- 关联商机：{opportunity_count} 个
  {opportunity_details}
- 最近跟进：{last_follow_up_date} {last_follow_up_content}
- 合同记录：{contract_count} 个

【工作原则】
1. 充分思考再行动：每次工具调用前，先分析当前状态
2. 利用上下文：根据已有商机、跟进情况判断下一步
3. 智能暂停：缺少信息时使用 ask_user 工具询问用户
4. 关键确认：重要操作（创建合同、回款）前先确认

【可用工具】
{tool_descriptions}

今天是 {current_date}
"""
```

---

### 3.3 Phase 3：ReAct Agent 循环机制

#### 3.3.1 核心流程

```python
class CRMAgent:
    async def execute(self, user_input: str, entity_context: dict):
        # 1. 预加载上下文
        context = await self.load_context(entity_context)
        
        # 2. 构建初始消息
        messages = [
            {"role": "system", "content": self._build_system_prompt(context)},
            {"role": "user", "content": user_input}
        ]
        
        # 3. Agent 循环
        max_rounds = 10
        for round_num in range(max_rounds):
            # 3.1 THINK: AI 分析
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )
            
            # 3.2 DECIDE: AI 返回文本（完成）
            if not response.tool_calls:
                return {
                    "status": "completed",
                    "message": response.content,
                    "actions": self._extract_actions(messages)
                }
            
            # 3.3 ACT: 处理工具调用
            for tool_call in response.tool_calls:
                # 3.3.1 执行工具
                result = await self._execute_tool(tool_call, context)
                
                # 3.3.2 记录到消息历史
                messages.append({
                    "role": "assistant",
                    "tool_calls": [tool_call]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
                
                # 3.3.3 OBSERVE: 检查是否需要暂停
                if tool_call.function.name == "ask_user":
                    # 暂停，等待用户输入
                    return {
                        "status": "waiting_for_user",
                        "question": result["question"],
                        "options": result.get("options"),
                        "context": context,  # 保存上下文
                        "messages": messages  # 保存消息历史
                    }
        
        # 超过最大轮数
        return {"status": "max_rounds_reached"}
    
    async def continue_with_user_response(
        self, 
        user_response: str, 
        saved_context: dict,
        saved_messages: list
    ):
        """用户回复后继续执行"""
        saved_messages.append({"role": "user", "content": user_response})
        
        # 继续 Agent 循环...
        return await self.execute(user_response, saved_context)
```

#### 3.3.2 完整执行流程示例

```
用户输入："微信找客户沟通，客户反馈已经确认采购了，后续采购会联系沟通合同相关事宜"
实体上下文：customer_id = 10

=== 预加载上下文 ===
上下文信息：
- 客户 #10（中国科学院）
- 关联商机：0 个
- 最近跟进：2026-06-05 电话沟通报价

=== Round 1: THINK ===
AI 分析：
"用户提到微信沟通和确认采购。
上下文显示客户无商机。
规划：
1. 创建跟进记录（有足够信息）
2. 发现无商机 → 询问用户是否创建商机"

Tool Calls:
  - create_follow_up(customer_id=10, content="客户反馈已确认采购...", follow_up_type="wechat")

=== OBSERVE Round 1 ===
Tool Result: {"success": true, "follow_up_id": "fu_123"}

=== Round 2: THINK ===
AI 分析：
"跟进已创建。客户无商机，但用户说'确认采购'，应该询问是否创建商机"

Tool Calls:
  - ask_user(
      question="客户确认采购了，是否需要创建商机？",
      options=["是，创建商机", "否，暂不创建"],
      missing_fields=["product", "amount"]
    )

=== 暂停等待用户 ===
返回：{
  "status": "waiting_for_user",
  "question": "客户确认采购了，是否需要创建商机？",
  "options": ["是，创建商机", "否，暂不创建"]
}

=== 用户回复 ===
用户选择："是，创建商机，产品是XX软件，金额50万"

=== Round 3: THINK ===
AI 分析：
"用户确认创建商机，产品=XX软件，金额=50万"

Tool Calls:
  - create_opportunity(
      customer_id=10,
      product="XX软件",
      amount=500000,
      probability=100
    )

=== OBSERVE Round 3 ===
Tool Result: {"success": true, "opportunity_id": "opp_456"}

=== Round 4: THINK ===
AI 分析：
"商机创建成功。用户提到'合同相关事宜'，询问是否现在创建合同"

Tool Calls:
  - ask_user(
      question="商机已创建（XX软件 50万）。是否现在创建合同？",
      options=["是，创建合同", "稍后创建"]
    )

=== 暂停等待用户 ===
返回：{status: "waiting_for_user", question: "是否现在创建合同？"}

=== 用户回复 ===
用户选择："是，创建合同"

=== Round 5: THINK ===
AI 分析：
"用户确认创建合同。需要调用 create_contract"

Tool Calls:
  - create_contract(
      customer_id=10,
      opportunity_id="opp_456",
      total_amount=500000,
      ...
    )

=== OBSERVE Round 5 ===
Tool Result: {"success": true, "contract_id": "con_789", "status": "draft"}

=== Round 6: THINK ===
AI 分析：
"所有操作完成，返回总结"

=== 完成 ===
返回：{
  "status": "completed",
  "message": "已完成：跟进记录、商机创建（XX软件 50万）、合同草稿（ID: con_789）"
}
```

#### 3.3.3 消息格式（OpenAI 标准）

```python
messages = [
    # 初始消息
    {"role": "system", "content": "..."},
    {"role": "user", "content": "微信找客户沟通..."},
    
    # Round 1
    {"role": "assistant", "tool_calls": [
        {"id": "call_1", "type": "function", "function": {
            "name": "create_follow_up",
            "arguments": '{"customer_id":"10","content":"客户反馈已确认采购...","follow_up_type":"wechat"}'
        }}
    ]},
    {"role": "tool", "tool_call_id": "call_1", "content": '{"success":true,"follow_up_id":"fu_123"}'},
    
    # Round 2
    {"role": "assistant", "tool_calls": [
        {"id": "call_2", "type": "function", "function": {
            "name": "ask_user",
            "arguments": '{"question":"客户确认采购了，是否需要创建商机？","options":["是，创建商机","否，暂不创建"]}'
        }}
    ]},
    
    # 暂停，等待用户
    # 用户回复后继续...
    
    {"role": "user", "content": "是，创建商机，产品是XX软件，金额50万"},
    
    # Round 3
    {"role": "assistant", "tool_calls": [
        {"id": "call_3", "type": "function", "function": {
            "name": "create_opportunity",
            "arguments": '{"customer_id":"10","product":"XX软件","amount":500000,"probability":100}'
        }}
    ]},
    {"role": "tool", "tool_call_id": "call_3", "content": '{"success":true,"opportunity_id":"opp_456"}'},
    
    # ... 继续后续轮次
]
```

---

### 3.4 Phase 4：实体歧义消解机制

#### 3.4.1 场景定义

| 场景 | 触发条件 | 消解方式 |
|------|----------|----------|
| **商机歧义** | 客户有多个跟进中商机 | 返回候选列表，让用户选择 |
| **合同歧义** | 客户有多份合同 | 返回候选列表，让用户选择 |
| **联系人歧义** | 客户有多个联系人 | 返回候选列表，让用户选择 |

#### 3.4.2 实现方案

**方案 A：AI 自动检测（推荐）**

```python
# 在工具调用前，AI 通过上下文判断是否有歧义
# 如果有歧义，AI 自主调用 ask_user 工具

# 上下文注入示例：
"""
关联商机：2 个
  - opp_101: CRM项目-50人1年订阅（30万）- 跟进中
  - opp_102: OA项目-30人1年订阅（18万）- 跟进中
"""

# AI 判断：
"用户要签合同，但客户有 2 个跟进中商机，需要用户选择"
→ 调用 ask_user(question="请选择签订合同的商机", options=[...])
```

**方案 B：工具执行层检测（兜底）**

```python
async def execute_tool(self, tool_call, context):
    # 如果工具需要 opportunity_id 但上下文有多个商机
    if tool_call.function.name in ["create_contract", "update_opportunity_stage"]:
        if len(context["opportunities"]) > 1:
            # 自动返回歧义提示
            return {
                "event": "disambiguation_required",
                "entity_type": "opportunity",
                "candidates": context["opportunities"],
                "message": "客户有多个商机，请选择"
            }
    
    # 正常执行工具
    ...
```

#### 3.4.3 前端交互

```
AI 返回：
{
  "status": "waiting_for_user",
  "question": "客户有多个商机，请选择签订合同的是哪个？",
  "options": [
    "CRM项目-50人1年订阅（30万）",
    "OA项目-30人1年订阅（18万）"
  ],
  "metadata": {
    "candidates": [
      {"id": "opp_101", "name": "CRM项目...", "amount": 300000},
      {"id": "opp_102", "name": "OA项目...", "amount": 180000}
    ]
  }
}

前端展示：
┌──────────────────────────────────────┐
│ 请选择签订合同的商机：                │
│                                      │
│ ○ CRM项目-50人1年订阅 (30万)         │
│ ○ OA项目-30人1年订阅 (18万)          │
│                                      │
│ [确认] [取消]                         │
└──────────────────────────────────────┘
```

---

### 3.5 Phase 5：前端交互设计

#### 3.5.1 状态流转

```
前端状态：
- idle: 空闲，等待用户输入
- thinking: AI 分析中（显示 loading）
- tool_executing: 工具执行中（显示进度）
- waiting_for_user: 暂停，等待用户确认/补充
- completed: 完成，显示总结
```

#### 3.5.2 SSE 事件协议

```typescript
// 事件类型
interface AgentEvent {
  event: 
    | "thinking"          // AI 分析中
    | "tool_call"         // 工具调用
    | "tool_result"       // 工具结果
    | "waiting_for_user"  // 暂停等待用户
    | "completed"         // 完成
    | "error";            // 错误
  
  data: {
    round?: number;       // 当前轮次
    tool?: string;        // 工具名
    params?: object;      // 工具参数
    result?: object;      // 工具结果
    question?: string;    // 向用户的问题
    options?: string[];   // 选项列表
    message?: string;     // 最终总结
  }
}

// 示例事件流
event: thinking
data: {"round": 1, "message": "分析用户意图"}

event: tool_call
data: {"round": 1, "tool": "create_follow_up", "params": {...}}

event: tool_result
data: {"round": 1, "result": {"success": true, "follow_up_id": "fu_123"}}

event: waiting_for_user
data: {"round": 2, "question": "是否创建商机？", "options": ["是", "否"]}

// 用户回复后继续...

event: completed
data: {"message": "已完成：跟进、商机、合同"}
```

#### 3.5.3 用户确认界面

**单次确认（简单场景）**

```
┌──────────────────────────────────────┐
│ AI 准备执行：创建商机                 │
│                                      │
│ 商机名称：XX软件-50人1年订阅          │
│ 预计金额：50万                        │
│ 成交概率：100%                        │
│                                      │
│ [确认执行] [修改参数] [取消]          │
└──────────────────────────────────────┘
```

**多候选选择（歧义场景）**

```
┌──────────────────────────────────────┐
│ 请选择签订合同的商机：                │
│                                      │
│ ○ CRM项目-50人1年订阅 (30万)         │
│ ○ OA项目-30人1年订阅 (18万)          │
│                                      │
│ [确认] [取消]                         │
└──────────────────────────────────────┘
```

**信息补充（缺失字段场景）**

```
┌──────────────────────────────────────┐
│ 请补充商机信息：                      │
│                                      │
│ 产品名称：[输入框]                    │
│ 预计金额：[输入框]                    │
│                                      │
│ [提交] [取消]                         │
└──────────────────────────────────────┘
```

#### 3.5.4 进度展示

```
┌──────────────────────────────────────┐
│ 执行进度：                            │
│                                      │
│ ✓ Round 1: 创建跟进记录               │
│   → 成功                              │
│                                      │
│ ✓ Round 2: 创建商机                   │
│   → 成功（ID: opp_456）               │
│                                      │
│ ○ Round 3: 创建合同                   │
│   → 等待用户确认                      │
│                                      │
│ [查看详情] [取消执行]                  │
└──────────────────────────────────────┘
```

---

## 四、后端架构改造

### 4.1 文件结构

```
CRM-Server/app/services/
├── ai/
│   ├── agent_service.py        # 新增：Agent 编排层
│   ├── agent_loop.py           # 新增：ReAct 循环核心
│   ├── context_loader.py       # 新增：上下文预加载
│   ├── ai_tool_service.py      # 保留：底层工具执行
│   └── action_entry.py         # 保留：统一入口
│
├── skills/
│   ├── handlers/
│   │   ├── customer_handler.py     # 保留
│   │   ├── opportunity_handler.py  # 保留
│   │   ├── contract_handler.py     # 新增
│   │   ├── payment_handler.py      # 新增
│   │   └── invoice_handler.py      # 新增
│   │   └── ask_user_handler.py     # 新增：用户交互工具
│   │   └── context_handler.py      # 新增：上下文工具
│   │
│   └── handler_configs.py      # 扩展：新增工具配置
│
└── constants/
    ├── tools.py                 # 扩展：新增工具定义（含完整描述）
    └── agent_config.py          # 新增：Agent 配置（max_rounds等）
```

### 4.2 核心类设计

```python
# agent_service.py
class CRMAgentService:
    """AI Agent 主服务"""
    
    async def process_message(
        self,
        user_input: str,
        entity_context: dict,
        team_id: str,
        user_id: str
    ) -> AsyncGenerator[AgentEvent, None]:
        """处理用户消息，流式返回事件"""
        
        # 1. 预加载上下文
        context = await self.context_loader.load(entity_context, team_id)
        
        # 2. 构建初始消息
        messages = self._build_messages(user_input, context)
        
        # 3. 开始 Agent 循环
        agent_loop = AgentLoop(
            llm=self.llm,
            tools=self.tools,
            max_rounds=self.config.max_rounds,
            timeout=self.config.timeout
        )
        
        for event in agent_loop.run(messages, context):
            yield event
            
            if event.event == "waiting_for_user":
                # 暂停，保存状态
                self._save_session(event.session_id, messages, context)
                return
    
    async def continue_session(
        self,
        session_id: str,
        user_response: str
    ) -> AsyncGenerator[AgentEvent, None]:
        """用户回复后继续会话"""
        
        # 1. 恢复会话
        session = self._load_session(session_id)
        
        # 2. 添加用户回复
        session.messages.append({"role": "user", "content": user_response})
        
        # 3. 继续 Agent 循环
        agent_loop = AgentLoop(...)
        for event in agent_loop.run(session.messages, session.context):
            yield event


# agent_loop.py
class AgentLoop:
    """ReAct 循环核心"""
    
    async def run(
        self,
        messages: list,
        context: dict
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行 Agent 循环"""
        
        for round_num in range(self.max_rounds):
            # THINK
            yield AgentEvent(event="thinking", data={"round": round_num})
            
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )
            
            # DECIDE: 完成
            if not response.tool_calls:
                yield AgentEvent(
                    event="completed",
                    data={"message": response.content}
                )
                return
            
            # ACT
            for tool_call in response.tool_calls:
                yield AgentEvent(
                    event="tool_call",
                    data={
                        "round": round_num,
                        "tool": tool_call.function.name,
                        "params": json.loads(tool_call.function.arguments)
                    }
                )
                
                # 执行工具
                result = await self._execute_tool(tool_call, context)
                
                yield AgentEvent(
                    event="tool_result",
                    data={"round": round_num, "result": result}
                )
                
                # 添加到消息历史
                messages.append({
                    "role": "assistant",
                    "tool_calls": [tool_call]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
                
                # OBSERVE: 检查是否需要暂停
                if tool_call.function.name == "ask_user":
                    yield AgentEvent(
                        event="waiting_for_user",
                        data={
                            "question": result["question"],
                            "options": result.get("options"),
                            "session_id": self._generate_session_id()
                        }
                    )
                    return


# context_loader.py
class ContextLoader:
    """上下文预加载"""
    
    async def load(self, entity_context: dict, team_id: str) -> dict:
        """根据实体类型加载上下文"""
        
        if entity_context["entity_type"] == "customer":
            return await self._load_customer_context(
                entity_context["entity_id"],
                team_id
            )
        
        elif entity_context["entity_type"] == "opportunity":
            return await self._load_opportunity_context(...)
        
        ...
    
    async def _load_customer_context(self, customer_id: str, team_id: str) -> dict:
        """加载客户上下文"""
        
        customer = await self.customer_repo.get(customer_id, team_id)
        opportunities = await self.opportunity_repo.list_by_customer(customer_id, team_id)
        follow_ups = await self.follow_up_repo.list_recent(customer_id, limit=5)
        contracts = await self.contract_repo.list_by_customer(customer_id, team_id)
        
        return {
            "entity_type": "customer",
            "entity_id": customer_id,
            "customer_info": {
                "name": customer.name,
                "status": customer.status,
                "industry": customer.industry,
                ...
            },
            "opportunities": [
                {
                    "id": opp.id,
                    "name": opp.name,
                    "amount": opp.amount,
                    "probability": opp.probability,
                    "status": opp.status
                }
                for opp in opportunities
            ],
            "recent_follow_ups": [...],
            "contracts": [...]
        }
```

---

## 五、非功能需求

### 5.1 性能要求

| 指标 | 要求 | 说明 |
|------|------|------|
| 单轮 AI 响应 | ≤ 5s | 单次 LLM 调用 |
| 工具执行时间 | ≤ 3s/个 | 单个工具执行 |
| Agent 总时间 | ≤ 120s | 完整循环 |
| 上下文加载 | ≤ 1s | 预加载时间 |

### 5.2 安全控制

| 控制项 | 配置 | 说明 |
|--------|------|------|
| 最大轮数 | `AGENT_MAX_ROUNDS = 10` | 防止无限循环 |
| 单轮超时 | `AGENT_ROUND_TIMEOUT = 30s` | 单轮超时 |
| 总超时 | `AGENT_TOTAL_TIMEOUT = 120s` | 总超时 |
| 高风险确认 | `risk_level >= "high"` | 强制用户确认 |
| 开关降级 | `AGENT_ENABLED = true` | 可关闭降级到原模式 |

### 5.3 可用性要求

| 要求 | 说明 |
|------|------|
| 错误隔离 | 单个工具失败不影响其他工具 |
| 日志追踪 | 每轮完整记录，支持排查 |
| 状态保存 | 暂停会话可恢复 |
| 向后兼容 | 不影响原有单工具调用 |

---

## 六、验收标准

### 6.1 功能验收

| 验收项 | 标准 |
|--------|------|
| **工具完整性** | 合同、回款、发票模块工具正常工作 |
| **工具描述** | 所有工具包含"适用于"、"触发条件"、"示例" |
| **上下文预加载** | Agent 启动时自动加载实体上下文 |
| **多意图编排** | 一段话多个意图能自动串联执行 |
| **Human-in-loop** | 缺少信息时能暂停询问，用户回复后继续 |
| **实体歧义消解** | 多候选实体时返回选择列表 |
| **配置开关** | 关闭 Agent 时降级到原有模式 |

### 6.2 场景验收

#### 场景 1：完整链路

```
输入："今天签了合同，30万，50人1年订阅"

期望流程：
1. Round 1: 创建跟进
2. Round 2: 标记商机赢单
3. Round 3: 创建合同
4. 完成

验收：所有步骤执行，无遗漏
```

#### 场景 2：信息缺失

```
输入："客户确认采购了"（客户无商机）

期望流程：
1. Round 1: 创建跟进
2. Round 2: 检测无商机 → 询问用户
3. 用户补充 → Round 3: 创建商机
4. 完成

验收：能暂停询问，用户回复后继续
```

#### 场景 3：实体歧义

```
输入："签合同"（客户有 2 个商机）

期望流程：
1. 检测到多个商机 → 返回候选列表
2. 用户选择 → 继续执行

验收：正确返回候选，用户选择后继续
```

#### 场景 4：意图识别

```
输入："微信确认了采购意向"

期望：选择 follow_up_customer（而非 query_opportunities）
验收：意图识别准确率 ≥ 95%
```

### 6.3 测试覆盖

| 测试类型 | 覆盖率要求 |
|----------|-----------|
| 单元测试 | 新增 Handler ≥ 80% |
| 集成测试 | Agent 循环完整覆盖 |
| E2E 测试 | 上述 4 个场景全部通过 |

---

## 七、风险评估与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| Agent 无限循环 | 资源耗尽 | max_rounds=10 + 总超时 120s |
| AI 返回错误工具 | 业务数据错误 | 风险分级 + 强制确认 |
| Token 消耗过大 | 成本增加 | 上下文精简 + 描述控制在 150 字内 |
| 前端改动大 | 开发周期长 | 分阶段实施 + 配置开关 |
| 状态保存丢失 | 会话中断 | Redis 持久化 + 超时清理 |

---

## 八、实施阶段划分

| 阶段 | 内容 | 依赖 | 工作量 |
|------|------|------|--------|
| **Phase 1** | 工具描述优化 + 补充合同/回款/发票工具 + ask_user/context 工具 | 无 | 2 天 |
| **Phase 2** | 上下文预加载机制 | Phase 1 | 1 天 |
| **Phase 3** | Agent 循环核心（后端） | Phase 2 | 2-3 天 |
| **Phase 4** | 实体歧义消解机制 | Phase 3 | 1 天 |
| **Phase 5** | 前端交互 + SSE 事件协议 | Phase 3-4 | 2 天 |
| **Phase 6** | 测试 + 文档 + 开关配置 | Phase 1-5 | 1 天 |

**总工作量：约 7-9 天**

---

## 九、关联文档

| 文档 | 说明 |
|------|------|
| AGENTS.md | AI 行为准则入口 |
| CRM-Docs/system/ARCHITECTURE.md | 前后端架构 |
| CRM-Server/app/constants/tools.py | 工具定义文件（需扩展） |
| CRM-Server/app/services/ai_tool_service.py | 当前工具服务（需保留兼容） |

---

> **文档版本**：2.0
> **最后更新**：2026-06-09
> **替代文档**：AI-TOOL-ENHANCEMENT-REQUIREMENTS.md v1.0 + AI-INTENT-RECOGNITION-OPTIMIZATION.md v1.0
> **维护团队**：CRMWolf 开发团队
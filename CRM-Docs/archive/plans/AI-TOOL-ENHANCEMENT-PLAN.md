---
status: completed
created: 2026-06-08
updated: 2026-06-08
related_requirements: ../requirements/AI-TOOL-ENHANCEMENT-REQUIREMENTS.md
related_pr: -
---

# AI 工具增强实施计划

> 版本：1.1 | 创建日期：2026-06-08 | 状态：Phase 6 已完成
> 配套需求文档：[AI-TOOL-ENHANCEMENT-REQUIREMENTS.md](../requirements/AI-TOOL-ENHANCEMENT-REQUIREMENTS.md)
> Phase 6 技术说明：[PHASE-6-FRONTEND-TECH-SPEC.md](./PHASE-6-FRONTEND-TECH-SPEC.md)

---

## 一、项目概览

### 1.1 目标

增强现有 Function Calling 架构，实现：
1. 补充合同、回款、发票模块的 Tools 定义
2. 支持 ReAct 循环（多轮 Reasoning → Action → Observation）
3. 支持实体歧义消解

### 1.2 核心收益

| 收益 | 说明 |
|------|------|
| 完整业务链路 | AI 可处理"签合同 → 创建合同 → 回款计划"完整流程 |
| 智能工具编排 | AI 自动判断需要哪些工具，无需硬编码规则 |
| 用户体验提升 | 实体歧义时主动询问，避免错误操作 |
| 可控风险 | 配置开关 + 分阶段实施 + 强制确认机制 |

### 1.3 工作量评估

| 阶段 | 工作量 | 优先级 | 风险 |
|------|--------|--------|------|
| Phase 1：补充合同 Tools | 1 天 | P0 | 低 |
| Phase 2：补充回款/发票 Tools | 1 天 | P1 | 低 |
| Phase 3：多工具返回支持 | 0.5 天 | P2 | 中 |
| Phase 4：实体歧义消解 | 1 天 | P3 | 中 |
| Phase 5：ReAct 循环机制 | 2-3 天 | P4 | 高 |
| Phase 6：前端依次确认 UI | 1-2 天 | P5 | 中 |

**总计**：约 7-9 工作日

---

## 二、分阶段实施计划

### Phase 1：补充合同 Tools

**目标**：为合同模块添加 4 个工具定义

#### 2.1.1 工具清单

| 工具名 | 描述 | Handler | 权限码 |
|--------|------|---------|--------|
| `create_contract` | 创建合同 | CreateHandler | contract:create |
| `query_contracts` | 查询合同列表 | QueryListHandler | contract:view |
| `get_contract_detail` | 合同详情 | QueryDetailHandler | contract:view |
| `update_contract_status` | 更新合同状态 | StatusChangeHandler | contract:edit |

#### 2.1.2 实现文件

| 文件 | 改动内容 |
|------|----------|
| `constants/tools.py` | 添加 4 个工具定义到 TOOLS 数组 |
| `constants/tools.py` | 添加 4 个 Handler 配置到 TOOL_HANDLER_MAP |
| `schemas/contract.py` | 确认 ContractCreate 等 Schema 存在 |
| `crud/contract.py` | 确认 CRUD 方法支持 team_id |

#### 2.1.3 工具定义示例

```python
# constants/tools.py 新增
{
    "type": "function",
    "function": {
        "name": "create_contract",
        "description": "创建合同。需要关联客户和商机，合同名称格式：{客户名称}-{商机名称}-合同",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "客户名称（用于查找客户ID）"
                },
                "opportunity_name": {
                    "type": "string",
                    "description": "商机名称（用于查找商机ID）"
                },
                "contract_name": {
                    "type": "string",
                    "description": "合同名称"
                },
                "total_amount": {
                    "type": "number",
                    "description": "合同总金额"
                },
                "user_count": {
                    "type": "integer",
                    "description": "采购用户数"
                },
                "license_type": {
                    "type": "string",
                    "enum": ["订阅制", "买断制"],
                    "description": "授权模式"
                },
                "subscription_years": {
                    "type": "integer",
                    "description": "订阅年限（订阅制时必填）"
                },
                "signing_date": {
                    "type": "string",
                    "description": "签署日期（YYYY-MM-DD）"
                }
            },
            "required": ["customer_name", "opportunity_name", "total_amount", "user_count"]
        }
    }
}
```

#### 2.1.4 Handler 配置示例

```python
# constants/tools.py TOOL_HANDLER_MAP 新增
"create_contract": {
    "handler": "CreateHandler",
    "config": {
        "crud_mapping": "contract",
        "schema_class": "ContractCreate",
        "parent_lookup": {
            "parent_crud_mapping": "customer",
            "parent_lookup_field": "customer_name",
            "parent_name_field": "account_name",
            "parent_result_field": "customer_id"
        },
        "secondary_parent_lookup": {
            "parent_crud_mapping": "opportunity",
            "parent_lookup_field": "opportunity_name",
            "parent_name_field": "opportunity_name",
            "parent_result_field": "opportunity_id"
        },
        "auto_fields": {
            "owner_id": "user_id"
        },
        "permission_code": "contract:create"
    }
}
```

#### 2.1.5 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 定义 create_contract 工具 | `constants/tools.py` | ✅ 完成 |
| 定义 query_contracts 工具 | `constants/tools.py` | ✅ 完成 |
| 定义 get_contract_detail 工具 | `constants/tools.py` | ✅ 完成 |
| 定义 update_contract_status 工具 | `constants/tools.py` | ✅ 完成 |
| 配置 Handler 映射 | `constants/tools.py` | ✅ 完成 |
| 扩展 CreateHandler 支持 secondary_parent_lookup | `handlers/create_handler.py` | ✅ 完成 |
| 扩展 BaseHandler 支持 filter_status | `handlers/base_handler.py` | ✅ 完成 |
| 单元测试 | `tests/unit/test_contract_tools.py` | ✅ 完成 |

#### 2.1.6 验收标准

- ✅ 4 个工具定义格式正确，符合 OpenAI Function Calling 规范
- ✅ Handler 配置正确，能通过工具名找到对应 Handler
- ✅ secondary_parent_lookup 支持创建合同时查找商机（parent_filter_status=WON）
- ✅ 单元测试验证通过

---

### Phase 2：补充回款/发票 Tools

**目标**：为回款、发票模块添加工具定义

#### 2.2.1 回款工具清单

| 工具名 | 描述 | Handler | 权限码 |
|--------|------|---------|--------|
| `create_payment_plan` | 创建回款计划 | CreateHandler | contract:edit |
| `create_payment_record` | 登记回款 | CreateHandler | payment:create |
| `query_payment_records` | 查询回款记录 | QueryListHandler | payment:view |
| `confirm_payment` | 确认回款 | StatusChangeHandler | payment:confirm |

#### 2.2.2 发票工具清单

| 工具名 | 描述 | Handler | 权限码 |
|--------|------|---------|--------|
| `create_invoice_application` | 申请开票 | CreateHandler | invoice:create |
| `query_invoice_applications` | 查询开票申请 | QueryListHandler | invoice:view |
| `get_invoice_application_detail` | 开票申请详情 | QueryDetailHandler | invoice:view |

#### 2.2.3 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 定义回款 4 个工具 | `constants/tools.py` | ✅ 完成 |
| 定义发票 3 个工具 | `constants/tools.py` | ✅ 完成 |
| 配置 Handler 映射 | `constants/tools.py` | ✅ 完成 |
| 添加 invoice_type 枚举映射 | `constants/handler_configs.py` | ✅ 完成 |
| 单元测试 | `tests/unit/test_payment_tools.py` | ✅ 完成 |

#### 2.2.4 验收标准

- ✅ 7 个工具定义格式正确
- ✅ Handler 配置正确，能通过工具名找到对应 Handler
- ✅ invoice_type 枚举映射存在
- ✅ 验证测试通过

---

### Phase 3：后端支持多工具返回

**目标**：修改 `ai_tool_service.py`，支持返回多个工具调用

#### 2.3.1 当前代码分析

```python
# 当前代码（只返回第一个）
first_call = tool_calls[0]
tool_name = first_call["name"]
params = json.loads(first_call["arguments"])

yield {
    "event": "parsed",
    "tool": tool_name,
    "params": params,
    ...
}
```

#### 2.3.2 改动方案

```python
# 改动后（返回全部）
all_calls = []
for call in tool_calls:
    tool_name = call["name"]
    params = json.loads(call["arguments"])
    params = self._inherit_parent_fields_in_parsed(tool_name, params, db, team_id)
    param_definitions = self._get_tool_param_definitions(tool_name, db, team_id)
    missing_params = self._get_missing_params(tool_name, params)
    
    all_calls.append({
        "tool": tool_name,
        "params": params,
        "param_definitions": param_definitions,
        "missing_params": missing_params,
        "reply_text": self._get_tool_description(tool_name, params)
    })

yield {
    "event": "parsed_multi",
    "tool_calls": all_calls
}
```

#### 2.3.3 兼容策略

| 策略 | 说明 |
|------|------|
| 新增事件 | 新增 `parsed_multi` 事件，保留原 `parsed` 事件 |
| 前端兼容 | 前端未改造时，检测到 `parsed_multi` 取第一个处理 |
| 配置开关 | `MULTI_TOOL_ENABLED = True` 控制是否启用多工具 |

#### 2.3.4 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 新增 parsed_multi 事件 | `services/ai_tool_service.py` | ✅ 完成 |
| 添加配置开关 | `core/config.py` | ✅ 完成 |
| 修改 handle_message_stream | `services/ai_tool_service.py` | ✅ 完成 |
| 新增 _get_multi_tool_description 方法 | `services/ai_tool_service.py` | ✅ 完成 |
| 单元测试 | 验证测试通过 | ✅ 完成 |

#### 2.3.5 验收标准

- ✅ AI 返回多个工具时，后端返回 `parsed_multi` 事件（当 MULTI_TOOL_ENABLED=True）
- ✅ `MULTI_TOOL_ENABLED=False` 时降级返回 `parsed` 事件（兼容现有逻辑）
- ✅ 不影响现有单工具调用逻辑
- ✅ 配置开关默认关闭，需要手动开启

---

### Phase 4：实体歧义消解机制

**目标**：当实体不唯一时，返回候选列表让用户选择

#### 2.4.1 触发场景

| 场景 | 检测条件 | 返回内容 |
|------|----------|----------|
| 商机歧义 | `opportunity_name` 查询返回多条 | 商机候选列表（名称、金额） |
| 联系人歧义 | `contact_name` 查询返回多条 | 联系人候选列表（姓名、职位） |
| 合同歧义 | `contract_name` 查询返回多条 | 合同候选列表（名称、金额） |

#### 2.4.2 实现方案

```python
# services/ai_tool_service.py 新增方法

def _check_entity_disambiguation(
    self,
    tool_name: str,
    params: dict,
    db: Session,
    team_id: int
) -> Optional[dict]:
    """检查实体是否存在歧义"""
    
    # 定义歧义检测规则
    DISAMBIGUATION_RULES = {
        "win_opportunity": {
            "lookup_field": "opportunity_name",
            "entity_type": "opportunity",
            "search_func": lambda db, name, team_id: 
                opportunity_crud.search_by_name(db, name, team_id, status="跟进中")
        },
        "create_contract": {
            "lookup_field": "opportunity_name",
            "entity_type": "opportunity",
            "search_func": lambda db, name, team_id: 
                opportunity_crud.search_by_name(db, name, team_id, status="跟进中")
        },
        # ... 其他规则
    }
    
    rule = DISAMBIGUATION_RULES.get(tool_name)
    if not rule:
        return None
    
    lookup_value = params.get(rule["lookup_field"])
    if not lookup_value:
        return None
    
    # 搜索实体
    entities = rule["search_func"](db, lookup_value, team_id)
    
    # 只有一条或没有，无歧义
    if len(entities) <= 1:
        return None
    
    # 有歧义，返回候选列表
    return {
        "entity_type": rule["entity_type"],
        "candidates": [
            {
                "id": e.id,
                "name": e.name if hasattr(e, 'name') else e.opportunity_name,
                "display_info": self._get_entity_display_info(e, rule["entity_type"])
            }
            for e in entities[:5]  # 最多返回 5 个候选
        ]
    }

def _get_entity_display_info(self, entity, entity_type) -> str:
    """生成实体展示信息"""
    if entity_type == "opportunity":
        return f"{entity.opportunity_name} ({entity.total_amount}元)"
    elif entity_type == "contact":
        return f"{entity.name} ({entity.position})"
    # ...
```

#### 2.4.3 事件结构

```python
yield {
    "event": "disambiguation_required",
    "entity_type": "opportunity",
    "candidates": [
        {"id": 101, "name": "CRM项目", "display_info": "CRM项目 (300000元)"},
        {"id": 102, "name": "OA项目", "display_info": "OA项目 (180000元)}
    ],
    "tool_call": {
        "tool": "win_opportunity",
        "params": {...}
    },
    "message": "该客户有多个商机，请选择要标记赢单的商机"
}
```

#### 2.4.4 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 定义歧义检测规则 | `constants/disambiguation_rules.py` | ✅ 完成 |
| 实现 _check_entity_disambiguation | `services/ai_tool_service.py` | ✅ 完成 |
| 修改 handle_message_stream 添加歧义检测 | `services/ai_tool_service.py` | ✅ 完成 |
| 单元测试 | 验证测试通过 | ✅ 完成 |

#### 2.4.5 验收标准

- ✅ 定义了 5 个歧义检测规则（win_opportunity、create_contract、create_payment_plan、create_payment_record、create_invoice_application）
- ✅ 客户有多个商机时，返回 `disambiguation_required` 事件
- ✅ 候选列表最多 10 个，包含 ID、名称、展示信息
- ✅ 单一实体时不触发歧义检测

---

### Phase 5：ReAct 循环机制

**目标**：实现多轮 Reasoning → Action → Observation → Repeat

#### 2.5.1 核心实现

```python
# services/ai_tool_service.py 新增方法

async def handle_message_with_react(
    self,
    db: Session,
    user: Any,
    content: str,
    team_id: int
) -> AsyncGenerator[Dict[str, Any], None]:
    """ReAct 循环处理"""
    
    messages = [{"role": "user", "content": content}]
    executed_results = []
    round_num = 0
    
    while round_num < settings.REACT_MAX_ROUNDS:
        round_num += 1
        
        # 调用 AI
        response = await self._call_ai_with_tools(messages)
        
        # AI 判断完成，无工具调用
        if not response.tool_calls:
            yield {"event": "result", "message": response.content, "round": round_num}
            break
        
        # 返回工具调用，等待用户确认
        yield {
            "event": "parsed_multi",
            "round": round_num,
            "tool_calls": response.tool_calls,
            "previous_results": executed_results
        }
        
        # 等待用户确认并执行（通过 SSE 反馈）
        # 执行结果加入 messages
        for call in response.tool_calls:
            result = await self._execute_tool(db, user, call, team_id)
            executed_results.append({
                "tool": call["name"],
                "result": result
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result)
            })
        
        # 返回执行结果
        yield {
            "event": "round_completed",
            "round": round_num,
            "results": executed_results
        }
    
    # 超过最大轮数
    if round_num >= settings.REACT_MAX_ROUNDS:
        yield {"event": "max_rounds_reached", "round": round_num}
```

#### 2.5.2 配置开关

```python
# core/config.py 新增
REACT_ENABLED: bool = False  # 默认关闭，稳定后开启
REACT_MAX_ROUNDS: int = 5
REACT_SINGLE_ROUND_TIMEOUT: int = 30
REACT_TOTAL_TIMEOUT: int = 120
```

#### 2.5.3 降级策略

```python
# services/ai_tool_service.py

async def handle_message_stream(...):
    if settings.REACT_ENABLED:
        # ReAct 模式
        async for event in self.handle_message_with_react(...):
            yield event
    else:
        # 原有单工具模式
        async for event in self._handle_message_legacy(...):
            yield event
```

#### 2.5.4 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 添加配置项 | `core/config.py` | ✅ 完成 |
| 实现 _handle_message_with_react | `services/ai_tool_service.py` | ✅ 完成 |
| 实现 continue_react_round | `services/ai_tool_service.py` | ✅ 完成 |
| 实现 _generate_summary | `services/ai_tool_service.py` | ✅ 完成 |
| 实现降级逻辑（入口判断） | `services/ai_tool_service.py` | ✅ 完成 |
| 单元测试 | 验证测试通过 | ✅ 完成 |

#### 2.5.5 验收标准

- ✅ 配置开关 REACT_ENABLED 默认关闭
- ✅ handle_message_stream 根据 REACT_ENABLED 选择模式
- ✅ _handle_message_with_react 实现多轮循环
- ✅ continue_react_round 支持继续下一轮
- ✅ max_rounds=5 正确配置
- ✅ 总超时 120s 正确配置
- ✅ `REACT_ENABLED=False` 时降级到原有模式

---

### Phase 6：前端依次确认 UI

**目标**：前端支持多工具依次确认、多轮展示

#### 2.6.1 UI 组件改动

| 组件 | 改动内容 |
|------|----------|
| `MagicWand.vue` | 支持 `parsed_multi` 事件，依次展示确认弹窗 |
| `ToolConfirmDialog.vue` | 支持多工具展示，添加"跳过"按钮 |
| `ReactProgress.vue` | 新增组件，展示多轮进度 |

#### 2.6.2 事件处理

```typescript
// 处理 parsed_multi 事件
case 'parsed_multi':
  const toolCalls = event.tool_calls
  const round = event.round
  
  // 显示进度
  showReactProgress(round, toolCalls.length)
  
  // 依次确认
  for (const call of toolCalls) {
    const userAction = await showToolConfirmDialog(call)
    if (userAction === 'confirm') {
      await executeTool(call.tool, call.params)
    } else if (userAction === 'skip') {
      // 跳过此工具
    } else if (userAction === 'cancel') {
      // 取消后续所有工具
      break
    }
  }
  
  // 反馈执行结果
  sendExecutionResults(round, executedResults)
  break

// 处理 round_completed 事件
case 'round_completed':
  showRoundResult(event.round, event.results)
  // 等待下一轮或显示完成
  break
```

#### 2.6.4 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 技术说明文档 | `CRM-Docs/plans/PHASE-6-FRONTEND-TECH-SPEC.md` | ✅ 完成 |
| 扩展 SSE 事件类型定义 | `api/aiAssistant.ts` | ✅ 完成 |
| 新增 continue_react 接口 | `api/aiAssistant.ts` | ✅ 完成 |
| 新增 Stage 类型 + 状态变量 | `MagicWandDialog.vue` | ✅ 完成 |
| 实现 parsed_multi 处理逻辑 | `MagicWandDialog.vue` | ✅ 完成 |
| 实现依次确认 UI | `MagicWandDialog.vue` | ✅ 完成 |
| 实现 ReactProgress 组件 | `ReactProgress.vue` | ✅ 完成 |
| 处理 disambiguation_required | `MagicWandDialog.vue` | ✅ 完成 |
| 实体选择 UI | `EntitySelectDialog.vue` | ✅ 完成 |
| TypeScript 类型检查 | 前端全部文件 | ✅ 通过 |

#### 2.6.5 验收标准

- ✅ 多工具时依次展示确认弹窗
- ✅ 用户可"确认"、"跳过"、"取消"
- ✅ 多轮时显示进度（Round 1/5）
- ✅ 实体歧义时显示选择界面
- ✅ TypeScript 类型检查通过
- ⏳ E2E 测试（可选，后续补充）

---

## 三、依赖关系

```
Phase 1 ────┬── Phase 2（可并行）
            │
            └── Phase 3（依赖 Phase 1-2 工具定义）
                    │
                    ├── Phase 4（依赖 Phase 3）
                    │
                    └── Phase 5（依赖 Phase 3 + Phase 4）
                            │
                            └── Phase 6（依赖 Phase 5）
```

**并行建议**：
- Phase 1 + Phase 2 可并行开发（约 2 天）
- Phase 3 独立开发（约 0.5 天）
- Phase 4 + Phase 5 可部分并行（约 3 天）
- Phase 6 在 Phase 5 完成后启动（约 1-2 天）

---

## 四、验收标准总览

### 4.1 功能验收

| 验收项 | 标准 |
|--------|------|
| 合同 Tools | 创建、查询、详情、状态更新 4 个工具正常工作 |
| 回款 Tools | 回款计划、登记、查询、确认 4 个工具正常工作 |
| 发票 Tools | 开票申请、查询、详情 3 个工具正常工作 |
| 多工具返回 | AI 返回多个工具时，后端返回 parsed_multi 事件 |
| 实体歧义消解 | 多商机场景返回候选列表，用户选择后继续 |
| ReAct 循环 | 多轮调用正常，最多 5 蛇，总时间 ≤ 120s |
| 配置开关 | 关闭 ReAct 时降级到原有单工具模式 |
| 前端 UI | 依次确认、跳过、取消功能正常 |

### 4.2 测试验收

| 测试类型 | 覆盖率要求 |
|----------|-----------|
| 单元测试 | 新增 Handler ≥ 80% |
| 集成测试 | ReAct 流程完整覆盖 |
| E2E 测试 | 签合同完整链路 |

---

## 五、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| ReAct 无限循环 | 资源耗尽 | max_rounds=5 + 总超时 120s |
| AI 返回错误工具 | 业务数据错误 | 风险分级 + 强制确认 |
| 前端改动大 | 开发周期长 | 分阶段实施 + 配置开关 |
| 现有功能受影响 | 用户投诉 | 降级开关 + 充分测试 |

---

## 六、后续维护

| 维护项 | 说明 |
|--------|------|
| 新增 Tools | 按本文档格式添加工具定义 |
| 调整轮数 | 修改 `REACT_MAX_ROUNDS` 配置 |
| 新增歧义场景 | 扩展 `DISAMBIGUATION_RULES` |

---

> **文档版本**：1.1
> **最后更新**：2026-06-09
> **维护团队**：CRMWolf 开发团队
> **实施状态**：Phase 1-6 全部完成
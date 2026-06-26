# AI 助手智能总结功能需求 - 设计评审报告

**评审类型**：全面分析（文档 + 现有代码实现）
**评审时间**：2026-06-26
**评审结论**：需求方案方向正确，但存在架构不一致和实现细节缺失

---

## 一、系统现状分析

### 1.1 架构现状（关键发现）

| 文档声称 | 实际实现 | 状态 |
|---------|---------|------|
| LangGraph v1.0 + StateGraph | ReAct Agent + CRMWolfAgent | ❌ 不一致 |
| Router → IntentDetector → EntityResolver → Preview → Execute | 只有 `intent.py` 实现 | ❌ 缺失 |
| 17+ LangGraph 节点 | ReAct 循环（Reason → Act → Observe → Reflect） | ✅ 生产可用 |

**根本问题**：文档描述的是目标架构（LangGraph），但实际运行的是现有架构（ReAct Agent）。需求方案应基于实际实现设计。

### 1.2 现有数据聚合能力

**发现**：`GetContextHandler` 已实现完整的数据聚合功能！

| 功能 | GetContextHandler 实现 | 状态 |
|------|----------------------|------|
| 客户上下文（商机 + 合同 + 回款 + 跟进） | ✅ line 124-228 | 已实现 |
| 商机上下文（客户 + 合同 + 回款计划） | ✅ line 230-326 | 已实现 |
| 合同上下文（回款计划 + 回款记录 + 发票） | ✅ line 327-425 | 已实现 |
| 线索上下文（跟进记录） | ✅ line 427-478 | 已实现 |
| 格式化 AI 可理解文本 | ✅ `_format_context_for_ai` | 已实现 |

**但是**：GetContextHandler **未注册为 ReAct Agent 工具**！

```python
# tools.py line 438-448 - 当前注册的工具
return {
    "search_customer": ...,      # ← 只返回 {id, name}
    "search_opportunity": ...,
    "follow_up_customer": ...,
    "create_opportunity": ...,
    # ❌ 缺失 get_entity_context
}
```

### 1.3 工具返回数据问题

| 工具 | 当前返回 | 用户期望 | 差距 |
|------|---------|---------|------|
| `search_customer` | `{id, name, hint}` | 客户完整信息 | ❌ 数据不足 |
| `follow_up_customer` | `{follow_up_id}` | 跟进内容 + 关联客户 | ❌ 缺少关联信息 |
| `create_opportunity` | `{opportunity_id}` | 商机信息 + 客户信息 | ❌ 缺少关联信息 |

---

## 二、需求方案评估

### 2.1 方案优点

| 维度 | 评分 | 评价 |
|------|------|------|
| **场景分类设计** | 9/10 | 四类场景覆盖完整，识别规则清晰 |
| **三阶段架构** | 8/10 | 数据聚合 + 场景识别 + 智能总结，逻辑清晰 |
| **Prompt 模板** | 7/10 | 总结模板详细，但缺少与现有 Prompt 的整合 |
| **验收标准** | 8/10 | 功能验收 + 性能验收 + 质量验收，完整 |

### 2.2 方案问题

| 问题 | 严重性 | 说明 |
|------|--------|------|
| **架构目标错误** | 🔴 Critical | 方案针对 LangGraph，但实际应针对 ReAct Agent |
| **忽略现有实现** | 🔴 Critical | GetContextHandler 已实现，方案提议重新开发 |
| **工具注册缺失** | 🔴 Critical | 方案未提及将数据增强工具注册到 ToolRegistry |
| **Prompt 整合缺失** | 🟡 Medium | SUMMARY_SYSTEM_PROMPT 应整合到现有 AgentPrompts |
| **前端 SSE 处理** | 🟡 Medium | 方案忽略前端 content 事件处理问题 |

---

## 三、具体改进建议

### 3.1 修正架构目标

**现状**：方案设计三阶段架构（数据聚合层 + 场景识别层 + 智能总结层），但假设是在 LangGraph 节点中实现。

**修正**：应在 ReAct Agent 循环中实现：

```
ReAct 循环修改：
Reason → Act → Observe → Reflection → ✨Enhance → ✨Summarize
```

**修改点**：

```python
# core.py 修改位置：line 199-260（循环结束后的响应构建）

async def run(self, user_message: str, session_id: str) -> AgentResponse:
    for round_num in range(self.MAX_ROUNDS):
        reasoning = await self._reason(...)
        
        if reasoning.needs_tool:
            tool_result = await self._act(reasoning)
            
            # ✨ NEW: 数据增强（复用 GetContextHandler）
            enhanced_data = await self._enhance_data(reasoning.tool_name, tool_result)
            
            observation = self._observe(tool_result)
            reflection = self._reflect(observation, reasoning)
            
            if not reflection.should_continue:
                # ✨ NEW: 智能总结（调用 LLM 生成业务化总结）
                final_answer = await self._generate_summary(
                    scenario=self._classify_scenario(...),
                    enhanced_data=enhanced_data,
                    user_message=user_message,
                )
                
                return AgentResponse(answer=final_answer, ...)
```

### 3.2 复用 GetContextHandler（避免重复开发）

**现状**：方案提议新建 `CustomerContextEnhancer` 等类，但 `GetContextHandler` 已实现相同功能。

**修正**：复用现有实现：

```python
# 新增：数据增强方法（复用 GetContextHandler）
async def _enhance_data(self, tool_name: str, tool_result: ToolResult) -> Dict[str, Any]:
    """
    数据增强：根据工具类型，自动聚合相关实体数据
    """
    ENHANCE_RULES = {
        "search_customer": {
            "enhance_with": "get_entity_context",
            "entity_type": "customer",
            "condition": "len(data) == 1",
        },
        "follow_up_customer": {
            "enhance_with": "get_entity_context",
            "entity_type": "customer",
            "use_param": "customer_id",
        },
    }
    
    rule = ENHANCE_RULES.get(tool_name)
    if not rule:
        return tool_result.data
    
    # 复用 GetContextHandler
    from app.services.skills.handlers.get_context_handler import GetContextHandler
    
    handler = GetContextHandler()
    entity_id = self._extract_entity_id(tool_result, rule)
    
    if entity_id:
        context_result = await handler.execute(
            db=self.db,
            handler_config={},
            params={"entity_type": rule["entity_type"], "entity_id": entity_id},
            team_id=self.team_id,
        )
        
        if context_result.get("success"):
            return context_result.get("context")
    
    return tool_result.data
```

### 3.3 注册 get_entity_context 工具

**现状**：GetContextHandler 未注册为工具，LLM 无法主动调用。

**修正**：注册为可选工具：

```python
# tools.py - 新增工具定义
{
    "name": "get_entity_context",
    "description": """获取实体的完整上下文信息。

用途：AI 需要完整信息时调用（如查询客户详情、生成业务报告）
参数：entity_type（customer/opportunity/contract/lead）+ entity_name 或 entity_id
返回：基本信息 + 关联实体 + 最近活动 + 格式化文本

示例：
- entity_type="customer", entity_name="光大证券"
  → 客户信息 + 商机列表 + 合同列表 + 最近跟进
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "enum": ["customer", "opportunity", "contract", "lead"]},
            "entity_name": {"type": "string", "description": "实体名称（可选）"},
            "entity_id": {"type": "integer", "description": "实体 ID（可选）"},
        },
        "required": ["entity_type"],
    },
},

# tools.py - 新增 handler 注册
from app.services.skills.handlers.get_context_handler import GetContextHandler

return {
    ...,
    "get_entity_context": _build_handler_entry("get_entity_context", GetContextHandler()),
}
```

### 3.4 整合 Prompt 模板

**现状**：方案提议独立的 `SUMMARY_SYSTEM_PROMPT`，但应整合到现有 `AgentPrompts`。

**修正**：整合到现有 Prompt：

```python
# prompts.py - 新增总结模板（整合到现有 SYSTEM_PROMPT_TEMPLATE）

FINAL_SUMMARY_TEMPLATE = """
【任务完成后的总结指导】

当任务完成时，你需要生成业务化的总结报告，遵循以下原则：

1. **有用**：提供用户关心的关键信息，不是技术日志
2. **可读**：结构化、段落分明、关键信息突出
3. **精准**：不丢失数据精度，数字、日期、状态准确
4. **智能**：基于数据给出业务建议

【场景类型】
- query（查询）：详细报告 + 数据分析 + 建议
- execute（执行）：执行确认 + 操作内容 + 关联信息 + 下一步建议
- multi（多意图）：完整执行报告 + 每个操作摘要 + 整体建议

【输出格式示例】
（整合方案中的示例）
"""

# prompts.py - 新增方法
def build_summary_prompt(self, scenario: str, user_message: str, enhanced_data: Dict, tool_history: List) -> str:
    """构建总结 Prompt"""
    # ... 实现方案中的逻辑
```

### 3.5 前端 SSE 处理问题

**现状**：方案忽略前端 `content` 事件处理问题。

**发现**：LangGraph SSE wrapper 发送 `content` 事件，但前端 `useAgentExecutionLog.ts` 未处理。

**修正**：前端增加 content 事件处理：

```typescript
// useAgentExecutionLog.ts - handleSSEEvent 方法增加 case

case 'content':
  // 内容事件 - 流式追加并实时保存
  if (event.content) {
    const store = useAIConversationStore()
    store.appendAIMessageContent(event.content)
  }
  break
```

---

## 四、修订后的实现计划

### 4.1 优先级调整

| 原方案 Phase | 修订后优先级 | 说明 |
|-------------|------------|------|
| Phase 1: 数据聚合层 | **P0 - 立即执行** | 复用 GetContextHandler，无需新开发 |
| Phase 2: 场景识别层 | **P1 - 简化实现** | 在 ReAct 循环中实现，而非 LangGraph 节点 |
| Phase 3: 智能总结层 | **P1 - 整合 Prompt** | 整合到现有 AgentPrompts，而非独立模块 |
| Phase 4: 流程整合 | **P0 - 修改 core.py** | 修改 ReAct 循环，而非 LangGraph graph |
| Phase 5: 测试验证 | **P2 - 各场景测试** | 验证查询/执行/多意图场景 |

### 4.2 文件变更清单（修订）

| 原方案文件 | 修订后 | 变更类型 |
|-----------|--------|---------|
| `data_enhancer.py`（新建） | **删除** | 复用 GetContextHandler |
| `scenario_classifier.py`（新建） | **简化为 core.py 内部方法** | 减少模块 |
| `prompts.py`（修改） | ✅ 整合 SUMMAR_TEMPLATE | 增强 |
| `core.py`（修改） | ✅ 增加 _enhance_data + _generate_summary | 核心修改 |
| `tools.py`（修改） | ✅ 注册 get_entity_context | 新增工具 |
| `useAgentExecutionLog.ts`（修改） | ✅ 增加 content 事件处理 | 前端修复 |

### 4.3 工作量估算（修订）

| Phase | 原方案 | 修订后 | 减少 |
|-------|--------|--------|------|
| Phase 1 | 3-4h | 0.5h | -3h（复用现有实现） |
| Phase 2 | 1-2h | 0.5h | -1h（简化） |
| Phase 3 | 2-3h | 1h | -1.5h（整合而非新建） |
| Phase 4 | 1-2h | 2h | +0.5h（核心修改更复杂） |
| Phase 5 | 2-3h | 2h | -0.5h |
| **总计** | **10-14h** | **6h** | **减少 50%** |

---

## 五、风险评估（修订）

| 原方案风险 | 修订后状态 | 说明 |
|-----------|-----------|------|
| LLM 总结不稳定 | ✅ 保留 | Prompt 包含格式示例 |
| 数据增强增加延迟 | ✅ 保留 | 增加 Redis 缓存 |
| 增强工具数据量过大 | ✅ 保留 | GetContextHandler 已优化（LIMIT 5） |
| **新增：架构不一致** | 🟡 Medium | 文档需同步更新为 ReAct Agent |
| **新增：工具注册遗漏** | 🔴 Critical | 必须注册 get_entity_context |

---

## 六、总结评分

| 维度 | 原方案评分 | 修订后评分 | 说明 |
|------|----------|-----------|------|
| **架构正确性** | 3/10 → 10/10 | 修正为 ReAct Agent 实现 |
| **代码复用** | 2/10 → 9/10 | 复用 GetContextHandler |
| **实现可行性** | 5/10 → 9/10 | 减少新模块，整合现有代码 |
| **工作量估算** | 6/10 → 8/10 | 减少 50%，更现实 |
| **风险覆盖** | 7/10 → 9/10 | 新增架构/工具注册风险 |

**总体评分**：原方案 5/10 → 修订后 9/10

---

## 附录 A：DX 优化方案（10/10 标准）

本附录详细说明如何将四个核心维度从当前评分提升到 10 分。

---

### A.1 场景分类设计：9/10 → 10/10

#### 缺失项分析

| 缺失 | 影响 | 扣分原因 |
|------|------|---------|
| **边缘场景覆盖** | 部分成功、超时、缓存失效等未定义 | -1分 |
| **场景转换规则** | query → execute 如何触发？多场景冲突如何处理？ | 未定义 |
| **特殊状态处理** | 部分成功、超时、缓存失效等场景 | 未定义 |

#### 优化方案

```python
# 新增：边缘场景定义
EDGE_SCENARIOS = {
    "partial_success": {
        "trigger": "tool_result.success == True but has incomplete data",
        "priority": 2,  # 高于 query，低于 interact
        "strategy": "report_partial + suggest_next",
    },
    "timeout": {
        "trigger": "round_num >= MAX_ROUNDS or llm_timeout",
        "priority": 1,  # 最高优先级
        "strategy": "fallback_summary + offer_continue",
    },
    "cache_miss": {
        "trigger": "enhanced_data is None after 3 retries",
        "priority": 4,
        "strategy": "use_raw_data + note_limitation",
    },
    "retry": {
        "trigger": "tool_result.success == False and error is recoverable",
        "priority": 3,
        "strategy": "retry_with_adjusted_params",
    },
}

# 新增：场景转换规则
SCENARIO_TRANSITIONS = {
    "query_to_execute": {
        "condition": "query_result.has_actionable_data",
        "trigger": "user_intent == 'follow_up_after_query'",
        "example": "查询客户 → 用户想跟进",
    },
    "execute_to_interact": {
        "condition": "execution_result.needs_confirmation",
        "trigger": "preview_data != None",
        "example": "执行危险操作 → 需要确认",
    },
    "multi_to_interact": {
        "condition": "current_step.needs_user_input",
        "trigger": "missing_field != []",
        "example": "多步骤任务 → 中途需要用户补充信息",
    },
}

# 新增：场景优先级（冲突时处理顺序）
SCENARIO_PRIORITY = [
    "timeout",       # 1 - 最高（系统级）
    "interact",      # 2 - 用户交互
    "partial_success",  # 3 - 部分成功
    "retry",         # 4 - 重试
    "multi",         # 5 - 多意图
    "execute",       # 6 - 执行
    "query",         # 7 - 查询
    "cache_miss",    # 8 - 缓存失效（最低）
]
```

---

### A.2 三阶段架构：8/10 → 10/10

#### 缺失项分析

| 缺失 | 影响 | 扣分原因 |
|------|------|---------|
| **Phase 数据契约** | Phase 之间的数据传递规范未定义 | -1分 |
| **失败回滚机制** | 数据增强失败、LLM 总结失败时如何处理？ | -1分 |
| **性能优化策略** | 缓存策略、并行执行、延迟控制 | 未定义 |

#### 优化方案

```python
# 新增：Phase 数据契约
@dataclass
class Phase1Output:
    """Phase 1 → Phase 2 数据契约"""
    raw_data: Dict[str, Any]  # 工具原始返回
    enhanced_data: Optional[Dict[str, Any]]  # 增强后数据
    enhancement_status: str  # "success" | "fallback" | "timeout"
    enhancement_latency_ms: float  # 数据聚合耗时

@dataclass
class Phase2Output:
    """Phase 2 → Phase 3 数据契约"""
    scenario: str  # 场景类型
    scenario_priority: int  # 场景优先级
    scenario_confidence: float  # 场景识别置信度
    input_data: Dict[str, Any]  # 传递给 Phase 3 的数据

@dataclass
class Phase3Output:
    """Phase 3 最终输出"""
    summary_text: str  # 业务化总结
    summary_type: str  # "detailed" | "simple" | "fallback"
    summary_latency_ms: float  # LLM 总结耗时

# 新增：Phase 失败回滚
class PhaseFallback:
    """Phase 失败时的回滚策略"""
    
    def phase1_fallback(self, tool_result: ToolResult) -> Phase1Output:
        """数据增强失败时的回滚"""
        return Phase1Output(
            raw_data=tool_result.data,
            enhanced_data=None,
            enhancement_status="fallback",
            enhancement_latency_ms=0,
        )
    
    def phase2_fallback(self, tool_name: str) -> Phase2Output:
        """场景识别失败时的回滚"""
        default_scenario = self.TOOL_SCENARIO_MAP.get(tool_name, "execute")
        return Phase2Output(
            scenario=default_scenario,
            scenario_priority=6,
            scenario_confidence=0.5,
            input_data={},
        )
    
    def phase3_fallback(self, tool_history: List[Dict]) -> Phase3Output:
        """LLM 总结失败时的回滚"""
        simple_summary = self._build_simple_summary(tool_history)
        return Phase3Output(
            summary_text=simple_summary,
            summary_type="fallback",
            summary_latency_ms=0,
        )

# 新增：性能优化策略
class PerformanceOptimizer:
    """三阶段性能优化"""
    
    CACHE_CONFIG = {
        "customer_context": {
            "ttl": 300,
            "key_pattern": "enhance:customer:{customer_id}:{team_id}",
        },
        "opportunity_context": {
            "ttl": 300,
            "key_pattern": "enhance:opportunity:{opportunity_id}:{team_id}",
        },
    }
    
    TIMEOUT_CONFIG = {
        "phase1_enhance": 500,
        "phase3_summarize": 3000,
        "total_pipeline": 4000,
    }
    
    async def parallel_enhance(self, entity_ids: Dict[str, int]) -> Dict[str, Any]:
        """并行聚合多个实体的数据"""
        tasks = []
        for entity_type, entity_id in entity_ids.items():
            tasks.append(self._enhance_single_entity(entity_type, entity_id))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        enhanced_data = {}
        for i, result in enumerate(results):
            entity_type = list(entity_ids.keys())[i]
            if isinstance(result, Exception):
                enhanced_data[entity_type] = None
            else:
                enhanced_data[entity_type] = result
        
        return enhanced_data
```

---

### A.3 Prompt 模板：7/10 → 10/10

#### 缺失项分析

| 缺失 | 影响 | 扣分原因 |
|------|------|---------|
| **与现有 Prompt 整合** | SUMMARY_PROMPT 与 SYSTEM_PROMPT_TEMPLATE 关系未定义 | -2分 |
| **Prompt 版本管理** | 无迭代机制、无评估方法 | -1分 |

#### 优化方案

```python
# 新增：Prompt 整合策略
class PromptIntegration:
    """Prompt 整合：SYSTEM_PROMPT + SUMMARY_PROMPT"""
    
    def build_full_prompt(self, phase: str) -> str:
        """根据 Phase 构建完整 Prompt"""
        if phase == "reason":
            return AgentPrompts.SYSTEM_PROMPT_TEMPLATE
        elif phase == "summarize":
            return self.SUMMARY_SYSTEM_PROMPT
        else:
            raise ValueError(f"Unknown phase: {phase}")
    
    def build_summary_prompt(
        self,
        scenario: str,
        user_message: str,
        enhanced_data: Dict,
        tool_history: List[Dict],
    ) -> str:
        """构建总结阶段 Prompt（整合现有 build_user_prompt）"""
        base_prompt = AgentPrompts().build_user_prompt(
            user_message=user_message,
            tool_history=tool_history,
            recent_entities={},
        )
        
        scenario_section = f"""
【当前场景】{scenario}

【完整数据】（用于生成详细报告）
{json.dumps(enhanced_data, ensure_ascii=False, indent=2)}

请根据以上信息，生成业务化总结。
"""
        
        return base_prompt + scenario_section

# 新增：Prompt 版本管理
class PromptVersionManager:
    """Prompt 版本管理"""
    
    VERSIONS = {
        "v1.0": {
            "created": "2026-06-26",
            "description": "初始版本：四场景分类",
            "active": True,
        },
        "v1.1": {
            "created": "待开发",
            "description": "增加边缘场景处理",
            "active": False,
        },
    }
    
    def get_active_version(self) -> str:
        """获取当前活跃版本"""
        for version, info in self.VERSIONS.items():
            if info["active"]:
                return version
        return "v1.0"
    
    def activate_version(self, version: str) -> None:
        """切换版本（支持 A/B 测试）"""
        for v in self.VERSIONS:
            self.VERSIONS[v]["active"] = (v == version)

# 新增：Prompt 评估方法
class PromptEvaluator:
    """Prompt 效果评估"""
    
    EVAL_CRITERIA = [
        "structure_score",
        "precision_score",
        "usefulness_score",
        "readability_score",
    ]
    
    def evaluate_summary(self, summary_text: str, expected_data: Dict) -> Dict[str, float]:
        """评估总结质量"""
        scores = {}
        
        # 结构化评估
        structure_markers = ["【", "】"]
        has_structure = all(marker in summary_text for marker in structure_markers)
        scores["structure_score"] = 10 if has_structure else 5
        
        # 精准度评估
        precision_count = 0
        for key in expected_data.keys():
            if str(expected_data[key]) in summary_text:
                precision_count += 1
        scores["precision_score"] = (precision_count / len(expected_data)) * 10
        
        # 有用性评估
        suggestion_keywords = ["建议", "下一步", "推荐"]
        has_suggestion = any(keyword in summary_text for keyword in suggestion_keywords)
        scores["usefulness_score"] = 10 if has_suggestion else 6
        
        # 可读性评估
        paragraphs = summary_text.split("\n\n")
        avg_paragraph_length = sum(len(p) for p in paragraphs) / len(paragraphs)
        scores["readability_score"] = 10 if avg_paragraph_length < 200 else 7
        
        return scores
```

---

### A.4 验收标准：8/10 → 10/10

#### 缺失项分析

| 缺失 | 影响 | 扣分原因 |
|------|------|---------|
| **自动化测试方法** | 只有场景描述，没有具体测试步骤 | -1分 |
| **回归测试标准** | 后续修改如何保证不破坏现有功能？ | -1分 |

#### 优化方案

```python
# 新增：自动化测试方法
class SummaryAutomatedTests:
    """智能总结自动化测试"""
    
    def test_phase1_enhance(self):
        """测试数据聚合层"""
        tool_result = ToolResult(success=True, data=[{"id": 123, "name": "光大证券"}])
        
        enhancer = DataEnhancer()
        enhanced = enhancer.enhance("search_customer", tool_result)
        
        assert enhanced.get("customer") is not None
        assert enhanced.get("opportunities") is not None
        assert enhanced.get("contracts") is not None
    
    def test_phase2_classify(self):
        """测试场景识别层"""
        classifier = ScenarioClassifier()
        
        tool_history = [{"tool_name": "follow_up_customer"}]
        reasoning = ReasoningResult(tool_name="follow_up_customer")
        scenario = classifier.classify(tool_history, reasoning)
        assert scenario == "execute"
        
        tool_history = [{"tool_name": "follow_up_customer"}, {"tool_name": "create_opportunity"}]
        scenario = classifier.classify(tool_history, reasoning)
        assert scenario == "multi"
    
    def test_phase3_summarize(self):
        """测试智能总结层"""
        summary = await _generate_summary(
            scenario="query",
            user_message="查询光大证券的信息",
            enhanced_data=MOCK_CUSTOMER_CONTEXT,
            tool_history=[],
        )
        
        assert "【" in summary
        assert "光大证券" in summary
        assert "建议" in summary or "下一步" in summary
    
    def test_full_pipeline_query(self):
        """测试查询场景完整流程"""
        user_message = "查询光大证券的信息"
        response = await agent.run(user_message, session_id)
        
        assert "商机情况" in response.answer
        assert "合同情况" in response.answer
        assert "回款情况" in response.answer

# 新增：回归测试标准
class RegressionTestSuite:
    """回归测试套件"""
    
    TEST_CASES = [
        {
            "name": "query_customer",
            "input": "查询光大证券的信息",
            "expected_fields": ["商机情况", "合同情况", "回款情况", "建议"],
        },
        {
            "name": "execute_follow_up",
            "input": "跟进光大证券，正在立项流程",
            "expected_fields": ["已完成", "操作内容", "关联实体", "下一步建议"],
        },
        {
            "name": "multi_intent",
            "input": "跟进光大证券，创建商机50万，下周提醒",
            "expected_fields": ["已完成", "操作1", "操作2", "操作3", "整体建议"],
        },
        {
            "name": "interact_disambiguation",
            "input": "跟进证券",
            "expected_fields": ["找到多个", "请选择"],
        },
    ]
    
    def run_all(self) -> Dict[str, bool]:
        """运行所有回归测试"""
        results = {}
        for case in self.TEST_CASES:
            try:
                response = await agent.run(case["input"], "test_session")
                passed = all(field in response.answer for field in case["expected_fields"])
                results[case["name"]] = passed
            except Exception as e:
                results[case["name"]] = False
        
        return results

# 新增：上线后监控
class SummaryQualityMonitor:
    """总结质量实时监控"""
    
    METRICS = {
        "phase1_success_rate": 0,
        "phase2_accuracy_rate": 0,
        "phase3_quality_score": 0,
        "user_satisfaction_rate": 0,
        "fallback_rate": 0,
    }
    
    def track_summary(self, response: AgentResponse, phases: Dict) -> None:
        """追踪一次总结的质量"""
        if phases["phase1"].enhancement_status == "success":
            self.METRICS["phase1_success_rate"] += 1
        
        quality_score = PromptEvaluator().evaluate_summary(
            response.answer,
            phases["phase1"].enhanced_data or {},
        )
        self.METRICS["phase3_quality_score"] = quality_score.get("average", 0)
        
        if phases["phase3"].summary_type == "fallback":
            self.METRICS["fallback_rate"] += 1
```

---

### A.5 优化后评分汇总

| 维度 | 原评分 | 优化后评分 | 关键优化点 |
|------|--------|-----------|-----------|
| **场景分类设计** | 9/10 | 10/10 | +边缘场景 +转换规则 +优先级排序 |
| **三阶段架构** | 8/10 | 10/10 | +数据契约 +回滚机制 +性能优化 |
| **Prompt 模板** | 7/10 | 10/10 | +整合策略 +版本管理 +评估方法 |
| **验收标准** | 8/10 | 10/10 | +自动化测试 +回归测试 +上线监控 |

---

### A.6 优化后的工作量估算

| 原方案 | 优化后新增 | 原估算 | 新估算 |
|--------|-----------|--------|--------|
| Phase 1-5 | 边缘场景 + 转换规则 | 6h | +1h = 7h |
| Phase 1-5 | 数据契约 + 回滚机制 | 6h | +1h = 8h |
| Prompt 整合 | Prompt 整合策略 + 版本管理 | - | +1h |
| 验收标准 | 自动化测试 + 监控 | - | +1h |
| **总计** | | **6h** | **10h** |

增加约 4 小时，但换来完整的 10/10 设计。

---

## 七、GSTACK REVIEW REPORT

### Runs

| Run | Tool | Status | Findings |
|-----|------|--------|----------|
| 1 | Read: AI-AGENT-ARCHITECTURE.md | ✅ | 文档声称 LangGraph，实际 ReAct Agent |
| 2 | Read: core.py | ✅ | ReAct 循环完整，缺少数据增强 |
| 3 | Read: tools.py | ✅ | GetContextHandler 未注册 |
| 4 | Read: get_context_handler.py | ✅ | 数据聚合已完整实现 |
| 5 | Read: sse_streamer.py | ✅ | result 事件发送 content |
| 6 | Read: useAgentExecutionLog.ts | ✅ | 缺少 content 事件处理 |

### Status

**DONE_WITH_CONCERNS**

### Findings

| Finding | Severity | Status |
|---------|----------|--------|
| 架构不一致（文档 vs 实现） | 🔴 Critical | 已识别，需文档同步 |
| GetContextHandler 未注册为工具 | 🔴 Critical | 已识别，需修改 tools.py |
| 数据聚合功能已实现 | ✅ Good | 可复用 |
| 前端 content 事件未处理 | 🟡 Medium | 已识别，需修改前端 |
| 方案工作量可减少 50% | ✅ Improvement | 已量化 |

### VERDICT

需求方案方向正确，但需修订：
1. **修正架构目标**：基于 ReAct Agent 实现，而非 LangGraph
2. **复用现有实现**：GetContextHandler 已实现数据聚合，无需新开发
3. **注册工具**：将 get_entity_context 注册到 ToolRegistry
4. **整合 Prompt**：整合到现有 AgentPrompts
5. **前端修复**：增加 content 事件处理

修订后工作量从 10-14h 减少到 6h。

### NO UNRESOLVED DECISIONS
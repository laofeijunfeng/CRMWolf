---
status: archived
created: 2026-06-22
updated: 2026-06-23
archived_date: 2026-06-23
priority: critical
completion_date: 2026-06-22
related_requirements: -
related_pr: -
---

# Agent 安全机制补全实施计划

**任务性质**：Non-trivial（核心架构修改 + 安全机制集成）
**实施日期**：2026-06-22
**预估时间**：16 小时（4 个 P0 任务）

---

## 一、已完成的修改

### 1.1 数据结构修改（已完成）

**修改位置**：`agent/core.py` 数据结构定义

**新增字段**：

```python
@dataclass
class ReasoningResult:
    # ===== 新增：安全机制字段 =====
    confidence: float = 1.0  # LLM 输出的置信度
    waiting_for_user: bool = False  # 是否需要等待用户
    pending_question: Optional[str] = None  # 待询问的问题
    pending_options: Optional[List[str]] = None  # 待选择的选项
    preview_data: Optional[Dict[str, Any]] = None  # Preview 数据

@dataclass
class AgentResponse:
    # ===== 新增：Human-in-the-Loop 字段 =====
    waiting_for_user: bool = False  # 是否等待用户回复
    pending_question: Optional[str] = None  # 待询问的问题
    pending_options: Optional[List[str]] = None  # 待选择的选项
    preview_data: Optional[Dict[str, Any]] = None  # Preview 变更计划
```

**修改原因**：支持 Guardrails 置信度拦截和 Human-in-the-Loop 机制

---

### 1.2 Guardrails 导入（已完成）

**修改位置**：`agent/core.py` 导入部分

**新增导入**：

```python
# ===== 新增：导入 Guardrails =====
from app.services.workflow.guardrails import (
    ConfidenceGuardrail,
    GuardrailDecision,
    DecisionType,
)
```

**修改原因**：复用现有的 Guardrails 实现（避免重复开发）

---

### 1.3 危险工具列表定义（已完成）

**修改位置**：`agent/core.py` CRMWolfAgent 类定义

**新增常量**：

```python
# ===== 新增：危险工具列表（需要 Preview） =====
DANGEROUS_TOOLS = [
    "win_opportunity",
    "lose_opportunity",
    "delete_customer",
    "delete_opportunity",
    "create_contract",
    "update_amount",
]
```

**修改原因**：标识哪些工具需要强制 Preview

---

### 1.4 Guardrails 初始化（已完成）

**修改位置**：`agent/core.py` __init__ 方法

**新增初始化**：

```python
# ===== 新增：Guardrails =====
self.guardrail = ConfidenceGuardrail()
```

**修改原因**：初始化 Guardrails 实例

---

## 二、待完成的修改（分阶段实施）

### Phase 1：集成 Guardrails 置信度拦截（待实施）

**修改位置**：`agent/core.py` _reason 方法

**实施内容**：

```python
async def _reason(self, user_message: str, round_num: int) -> ReasoningResult:
    """Reason: 调用 LLM 推理（集成 Guardrails）"""
    
    # 调用 LLM 推理
    response_text = await ai_service._stream_chat_collect(...)
    reasoning = self._parse_reasoning_response(response_text)
    
    # ===== 新增：Guardrails 置信度检查 =====
    # 从 LLM 输出提取置信度（需要修改 Prompt）
    confidence = self._extract_confidence(response_text)
    
    # 调用 Guardrails 决策
    guardrail_decision = self.guardrail.check(
        confidence=confidence,
        action_type=reasoning.tool_name or "unknown",
        context={"round_num": round_num}
    )
    
    # 根据决策类型处理
    if guardrail_decision.decision == DecisionType.BLOCK:
        # 极低置信度：阻断操作
        logger.warning(f"Guardrails BLOCK: confidence={confidence}")
        return ReasoningResult(
            is_complete=True,
            needs_tool=False,
            final_answer=f"操作被拦截：置信度过低 ({confidence:.2f})，请提供更多信息",
            thinking="Guardrails: confidence < 0.5 → block",
            confidence=confidence,
        )
    
    elif guardrail_decision.decision == DecisionType.HUMAN_LOOP:
        # 低置信度：需人工确认
        logger.info(f"Guardrails HUMAN_LOOP: confidence={confidence}")
        return ReasoningResult(
            is_complete=False,
            needs_tool=False,
            waiting_for_user=True,  # ← 暂停等待用户
            pending_question=f"操作置信度较低 ({confidence:.2f})，是否继续？",
            pending_options=["确认执行", "取消"],
            thinking="Guardrails: confidence < 0.7 → human_loop",
            confidence=confidence,
        )
    
    elif guardrail_decision.decision == DecisionType.STRONG_CONFIRM:
        # 高风险操作：强确认（Modal）
        logger.info(f"Guardrails STRONG_CONFIRM: confidence={confidence}")
        # 继续执行，但在 _act 中会检查是否需要 Preview
        return reasoning
    
    # AUTO 或 WEAK_CONFIRM：正常执行
    return reasoning
```

**新增辅助方法**：

```python
def _extract_confidence(self, response_text: str) -> float:
    """
    从 LLM 输出提取置信度
    
    Args:
        response_text: LLM 响应文本
        
    Returns:
        float: 置信度（0.0 - 1.0）
    """
    try:
        # 解析 JSON
        result = json.loads(response_text)
        
        # 提取 confidence 字段（需要在 Prompt 中定义）
        confidence = result.get("confidence", 1.0)
        
        return float(confidence)
    
    except:
        # 无法解析，默认高置信度
        return 1.0
```

**需要同步修改**：
- `agent/prompts.py` 的 Prompt 添加 confidence 输出要求

---

### Phase 2：集成 Preview 模式（待实施）

**修改位置**：`agent/core.py` _act 方法

**实施内容**：

```python
async def _act(self, tool_name: str, tool_params: Dict[str, Any]) -> ToolResult:
    """Act: 执行工具（集成 Preview）"""
    
    logger.info(f"Act: tool_name={tool_name}, params={tool_params}")
    
    # 获取工具 Handler
    handler = self.tool_registry.get_handler(tool_name)
    
    if not handler:
        return ToolResult(success=False, error=f"工具'{tool_name}'不存在")
    
    # ===== 新增：Preview 检查 =====
    if tool_name in self.DANGEROUS_TOOLS:
        # 危险工具：生成 Preview
        logger.info(f"Preview required for dangerous tool: {tool_name}")
        
        # 调用 Handler 的 preview 方法（需要确保 Handler 支持）
        try:
            preview_result = await handler.preview(
                db=self.db,
                team_id=self.team_id,
                user_id=self.user_id,
                params=tool_params,
            )
            
            # 返回等待状态（不执行）
            return ToolResult(
                success=False,  # ← 暂时返回失败，等待用户确认
                waiting_for_user=True,  # ← 新增字段（需要修改 ToolResult）
                preview_data=preview_result,  # ← Preview 数据
                message="请确认变更计划",
            )
        
        except Exception as e:
            logger.error(f"Preview failed: {str(e)}")
            # Preview 失败，直接执行（降级策略）
            return await self._execute_tool(handler, tool_params)
    
    # 正常工具：直接执行
    return await self._execute_tool(handler, tool_params)

async def _execute_tool(self, handler, tool_params: Dict[str, Any]) -> ToolResult:
    """执行工具（抽取为独立方法）"""
    try:
        result = await handler.execute(
            db=self.db,
            team_id=self.team_id,
            user_id=self.user_id,
            params=tool_params,
        )
        
        logger.info(f"Tool result: success={result.success}")
        return result
    
    except Exception as e:
        logger.error(f"Tool execution failed: {str(e)}")
        return ToolResult(success=False, error=str(e))
```

**需要同步修改**：
- `agent/tools.py` 的 ToolResult 添加 waiting_for_user、preview_data 字段
- 确保 Handler 支持 preview 方法（从 skills handlers 复用）

---

### Phase 3：集成 Human-in-the-Loop（待实施）

**修改位置**：`agent/core.py` run 方法

**实施内容**：

```python
async def run(self, user_message: str, session_id: Optional[str] = None) -> AgentResponse:
    """执行 Agent ReAct 循环（支持 Human-in-the-Loop）"""
    
    logger.info(f"Agent started: user_message='{user_message}'")
    
    # 加载或初始化会话记忆
    if session_id:
        self.memory.load_session(session_id)
    else:
        session_id = self.memory.create_session()
    
    self.memory.add_user_message(user_message)
    
    # ===== ReAct 循环 =====
    for round_num in range(self.MAX_ROUNDS):
        logger.info(f"ReAct Round {round_num + 1}/{self.MAX_ROUNDS}")
        
        # Step 1: Reason（推理）
        reasoning = await self._reason(user_message, round_num)
        
        # ===== 新增：处理 waiting_for_user =====
        if reasoning.waiting_for_user:
            # 暂停循环，等待用户回复
            logger.info(f"Agent paused: waiting_for_user at round {round_num + 1}")
            return AgentResponse(
                session_id=session_id,
                answer=reasoning.pending_question,
                waiting_for_user=True,
                pending_question=reasoning.pending_question,
                pending_options=reasoning.pending_options,
                preview_data=reasoning.preview_data,
                tool_calls=self.memory.get_tool_history(),
                rounds=round_num + 1,
            )
        
        # Step 2: 判断是否完成
        if reasoning.is_complete:
            final_answer = reasoning.final_answer or "任务完成"
            self.memory.add_agent_message(final_answer)
            
            return AgentResponse(
                session_id=session_id,
                answer=final_answer,
                tool_calls=self.memory.get_tool_history(),
                rounds=round_num + 1,
            )
        
        # Step 3: Act（工具调用）
        if reasoning.needs_tool:
            tool_result = await self._act(reasoning.tool_name, reasoning.tool_params)
            
            # ===== 新增：处理 tool_result.waiting_for_user =====
            if tool_result.waiting_for_user:
                # Preview 状态，等待用户确认
                logger.info(f"Agent paused: Preview required for {reasoning.tool_name}")
                return AgentResponse(
                    session_id=session_id,
                    answer=tool_result.message,
                    waiting_for_user=True,
                    pending_question=f"是否确认执行 {reasoning.tool_name}？",
                    pending_options=["确认执行", "取消"],
                    preview_data=tool_result.preview_data,
                    tool_calls=self.memory.get_tool_history(),
                    rounds=round_num + 1,
                )
            
            # 正常执行结果处理
            observation = self._observe(tool_result)
            reflection = self._reflect(observation, reasoning)
            
            self.memory.add_tool_call(
                tool_name=reasoning.tool_name,
                tool_params=reasoning.tool_params,
                tool_result=tool_result,
                reasoning=reasoning.thinking,
            )
            
            if not reflection.should_continue:
                final_answer = reflection.final_answer or "部分完成"
                self.memory.add_agent_message(final_answer)
                
                return AgentResponse(
                    session_id=session_id,
                    answer=final_answer,
                    tool_calls=self.memory.get_tool_history(),
                    rounds=round_num + 1,
                )
    
    # 超过最大轮数
    logger.warning(f"Agent exceeded max rounds ({self.MAX_ROUNDS})")
    partial_answer = self._build_partial_answer()
    
    return AgentResponse(
        session_id=session_id,
        answer=partial_answer,
        tool_calls=self.memory.get_tool_history(),
        rounds=self.MAX_ROUNDS,
        is_partial=True,
    )
```

---

### Phase 4：修改 Prompt（添加 confidence 输出）（待实施）

**修改位置**：`agent/prompts.py` SYSTEM_PROMPT_TEMPLATE

**新增要求**：

```python
【输出格式】（强制 JSON 格式）

**如果需要调用工具**：
```json
{
  "reasoning": "推理过程",
  "confidence": 0.85,  // ← 新增：置信度（0.0 - 1.0）
  "needs_tool": true,
  "tool_name": "工具名称",
  "tool_params": {...},
  "is_complete": false
}
```

**如果任务完成**：
```json
{
  "reasoning": "任务完成推理",
  "confidence": 0.95,  // ← 新增：置信度
  "needs_tool": false,
  "is_complete": true,
  "final_answer": "最终答案"
}
```

**置信度定义**：
- 0.95+：非常确定，可以直接执行
- 0.80-0.95：确定，但需弱确认（Toast）
- 0.70-0.80：较确定，但需强确认（Modal）
- 0.50-0.70：不确定，需人工介入
- <0.50：非常不确定，应拦截
```

---

### Phase 5：修改 ToolResult（支持 Preview）（待实施）

**修改位置**：`agent/tools.py` ToolResult 定义

**新增字段**：

```python
@dataclass
class ToolResult:
    """工具执行结果（支持 Preview）"""
    success: bool
    error: Optional[str]
    data: Optional[Any]
    message: Optional[str]
    # ===== 新增：Preview 支持 =====
    waiting_for_user: bool = False  # 是否等待用户确认
    preview_data: Optional[Dict[str, Any]] = None  # Preview 变更计划
```

---

### Phase 6：修改 Handler（支持 Preview）（待实施）

**修改位置**：`agent/handlers/` 所有 Handler

**新增方法**：

```python
class BaseHandler:
    async def preview(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Preview 方法（生成变更计划）
        
        Returns:
            {
                "description": "创建客户「张三科技」",
                "changes": [
                    {"field": "account_name", "from": null, "to": "张三科技"},
                    {"field": "industry", "from": null, "to": "互联网"}
                ],
                "risk_level": "medium"
            }
        """
        # 默认实现：返回参数本身
        return {
            "description": f"执行 {self.__class__.__name__}",
            "changes": [{"field": k, "to": v} for k, v in params.items()],
            "risk_level": "medium"
        }
```

---

## 三、实施顺序建议

| Phase | 任务 | 依赖 | 预估时间 |
|-------|------|------|----------|
| **Phase 1** | Guardrails 置信度拦截 | 无 | 4 小时 |
| **Phase 2** | Preview 模式 | Phase 1 | 6 小时 |
| **Phase 3** | Human-in-the-Loop | Phase 1, 2 | 4 小时 |
| **Phase 4** | Prompt 添加 confidence | Phase 1 | 2 小时 |
| **Phase 5** | ToolResult 支持 Preview | Phase 2 | 1 小时 |
| **Phase 6** | Handler 支持 Preview | Phase 2, 5 | 3 小时 |

**总计**：16 小时（约 2-3 个工作日）

---

## 四、测试计划

### 4.1 单测补充

| 测试场景 | 测试内容 | 优先级 |
|----------|----------|----------|
| Guardrails 拦截 | confidence < 0.5 → BLOCK | 🔴 P0 |
| Guardrails Human-loop | confidence < 0.7 → HUMAN_LOOP | 🔴 P0 |
| Preview 生成 | 危险工具 → Preview | 🔴 P0 |
| Preview 确认 | 用户确认 → Execute | 🔴 P0 |
| Human-in-the-Loop | waiting_for_user → resume | 🟡 P1 |

---

### 4.2 集成测试

| 场景 | 测试内容 | 预期行为 |
|------|----------|----------|
| **创建客户（低置信度）** | 输入模糊 | Guardrails → HUMAN_LOOP → 用户确认 |
| **赢单流程（高置信度）** | 输入完整 | Preview → 用户确认 → Execute |
| **删除客户（极低置信度）** | 输入不明确 | Guardrails → BLOCK → 拒绝执行 |

---

## 五、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| **修改核心逻辑** | 🟡 中 | 充分单测 + 灰度发布 |
| **Prompt 修改影响 LLM 输出** | 🟡 中 | 测试多种场景 + fallback 逻辑 |
| **Handler Preview 实现不完整** | 🟡 中 | 优先实现危险工具 Preview |

---

## 六、后续改进（可选）

### Phase 7：集成 Undo 撤销机制（可选）

**修改位置**：`agent/memory.py`

**新增功能**：
- 每次工具执行成功后记录 Undo 快照
- 支持 10 秒内撤销
- 从 workflow.undo_service 复用代码

---

### Phase 8：集成 Workflow Engine（可选）

**修改位置**：`agent/core.py`

**新增逻辑**：
- Router 检测关键词 → Workflow Engine
- Workflow Engine 使用硬编码流程
- 双引擎共存（Workflow + ReAct）

---

## 七、文档同步

### 7.1 需要更新的文档

| 文档 | 修改内容 |
|------|----------|
| `CRM-Server/CLAUDE.md` | 删除 LangGraph 描述，添加 CRMWolfAgent + 安全机制说明 |
| `CRM-Docs/system/AI-ASSISTANT-WORKFLOW.md` | 更新为实际架构（CRMWolfAgent） |
| `CRM-Docs/system/AGENT-ARCHITECTURE.md` | 新建，详细描述 Agent 实现 |

---

## 八、验收标准

### 8.1 功能验收

| 功能 | 验收标准 |
|------|----------|
| **Guardrails** | confidence < 0.5 的操作被拦截 |
| **Preview** | 危险工具显示变更计划 |
| **Confirm** | 用户确认后才执行 |
| **Human-in-the-Loop** | 可以暂停询问用户 |

---

### 8.2 安全验收

| 安全机制 | 验收标准 |
|----------|----------|
| **阻断危险操作** | confidence < 0.5 的删除操作被拒绝 |
| **Preview 强制** | 赢单、删除等操作必须 Preview |
| **审计日志** | 所有 Guardrails 决策记录日志 |

---

**版本**：1.0 | 创建日期：2026-06-22 | 最后更新：2026-06-22
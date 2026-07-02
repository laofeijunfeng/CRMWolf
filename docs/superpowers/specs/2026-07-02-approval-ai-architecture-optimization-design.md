# 审批流程 AI 解析架构优化设计

**版本**: v1.0
**日期**: 2026-07-02
**状态**: 待审核
**作者**: Claude (Brainstorming Session)

---

## 1. 背景与问题

### 1.1 当前问题

`approval_ai_parser.py` 模块存在多个反复出现的缺陷：

| 问题 | 描述 | 影响 |
|------|------|------|
| **Format String KeyError** | System Prompt 中的 JSON 示例 `{...}` 被 Python `.format()` 误解析为占位符 | SSE 流中断，无错误事件 |
| **Decimal 序列化** | Pydantic Schema 使用 Decimal 类型，`json.dumps()` 无法直接序列化 | parsed 事件发送失败 |
| **SSE 流异常中断** | 异步生成器内部异常未被正确捕获，导致 SSE 流提前关闭 | 前端收到不完整响应 |
| **架构不统一** | 未复用系统成熟的 EntityAIParserBase 基类 | 维护成本高，重复代码 |

### 1.2 已有的成熟架构

系统已存在以下成熟组件：

| 组件 | 文件 | 功能 |
|------|------|------|
| **EntityAIParserBase** | `services/ai_parser/base_parser.py` | AI 解析器基类，提供 SSE 流式处理 |
| **SSEJsonEncoder** | `services/langgraph/sse_wrapper.py` | 处理 Decimal/复杂类型的 JSON 序列化 |
| **LangGraph SSE Wrapper** | `services/langgraph/sse_wrapper.py` | 完善的 SSE 事件格式转换 |
| **Checkpointer** | `services/langgraph/checkpointer.py` | Redis 会话状态持久化 |

### 1.3 设计目标

1. **架构统一**：复用 LangGraph 框架，与 AI 助手架构一致
2. **稳定性**：彻底解决 Decimal 序列化、模板转义问题
3. **可维护性**：新增解析器只需定义配置，无需重复实现
4. **向后兼容**：API 层保持不变，前端无需修改

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     LangGraph AI 架构                            │
│                                                                  │
│  ┌─────────────┐      ┌─────────────────────────────────────┐   │
│  │   State     │─────▶│            Graph                    │   │
│  │ (TypedDict) │      │         (StateGraph)                │   │
│  └─────────────┘      │                                     │   │
│                       │  ┌───────────┐   ┌───────────┐      │   │
│                       │  │   Router  │──▶│   Intent  │      │   │
│                       │  └───────────┘   └───────────┘      │   │
│                       │         │              │            │   │
│                       │         ▼              ▼            │   │
│                       │  ┌───────────┐   ┌───────────┐      │   │
│  ┌─────────────┐      │  │ApprovalAI │   │   Entity  │      │   │
│  │ Checkpointer│◀────│  │   Node    │   │   Node    │      │   │
│  │   (Redis)   │      │  │  [NEW]    │   │           │      │   │
│  └─────────────┘      │  └───────────┘   └───────────┘      │   │
│                       │         │              │            │   │
│                       │         ▼              ▼            │   │
│                       │  ┌───────────┐   ┌───────────┐      │   │
│  ┌─────────────┐      │  │  Preview  │   │  Execute  │      │   │
│  │ SSE Wrapper │◀────│  │           │   │           │      │   │
│  │(SSEJsonEncoder)    │  └───────────┘   └───────────┘      │   │
│  └─────────────┘      │                                     │   │
│                       └─────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 职责 | 复用/新增 |
|------|------|-----------|
| **ApprovalAIState** | 审批解析状态定义 | 新增 |
| **ApprovalAINode** | 审批解析逻辑执行 | 新增 |
| **ApprovalAITool** | 低层解析工具 | 新增 |
| **SSEJsonEncoder** | JSON 序列化处理 | 复用 |
| **Checkpointer** | 会话状态持久化 | 复用 |
| **SSE Wrapper** | SSE 事件格式转换 | 复用 |

---

## 3. 文件结构变更

### 3.1 新增文件

```
CRM-Server/app/services/
├── langgraph/
│   ├── nodes/
│   │   └── approval_ai.py        # NEW: 审批 AI 解析节点
│   ├── tools/
│   │   └── approval_ai_tool.py   # NEW: 审批解析工具
│   └── prompts/
│       └── approval_ai_prompt.py # NEW: System Prompt 定义（双花括号转义）
```

### 3.2 修改文件

| 文件 | 变更内容 |
|------|----------|
| `langgraph/graph.py` | 添加 approval_ai 路由分支 |
| `langgraph/state.py` | 添加 ApprovalAIState 定义 |
| `schemas/approval_ai.py` | min_amount/max_amount 改为 float 类型 |
| `ai_parser/base_parser.py` | 移除 response_format，增强错误处理 |

### 3.3 弃用文件

| 文件 | 处理方式 |
|------|----------|
| `approval_ai_parser.py` | 标记 deprecated，保留兼容层，内部调用 LangGraph |

---

## 4. 核心组件设计

### 4.1 ApprovalAIState

```python
# langgraph/state.py 新增

from typing import TypedDict, Optional, List, Any, Dict

class ApprovalAIState(TypedDict):
    """审批流程 AI 解析状态
    
    设计要点：
    - 使用 TypedDict 确保类型安全
    - 包含输入、输出、状态三个维度
    - validation_errors 支持多错误收集
    """
    
    # === 输入 ===
    user_message: str              # 用户自然语言描述
    team_id: int                   # 团队 ID（用于获取 AI 配置）
    
    # === 输出 ===
    parsed_flow: Optional[Dict[str, Any]]  # 解析后的审批流程配置
    thinking_process: Optional[str]        # AI 思考过程（前端显示）
    
    # === 状态 ===
    parse_status: str              # "pending" | "streaming" | "parsed" | "validated" | "error"
    full_content: str              # AI 返回的完整 JSON 内容
    validation_errors: List[str]   # 校验错误列表（可多错误）
    error_message: Optional[str]   # 最终错误消息
```

### 4.2 ApprovalAINode

```python
# langgraph/nodes/approval_ai.py

from typing import Dict, Any
from app.services.langgraph.state import ApprovalAIState
from app.services.langgraph.tools.approval_ai_tool import approval_ai_tool
from app.constants.approval_roles import ALLOWED_APPROVAL_ROLES

class ApprovalAINode:
    """审批流程 AI 解析节点
    
    职责：
    1. 构建 System Prompt（双花括号转义）
    2. 调用 AI API（流式）
    3. 解析 JSON 响应（使用 SSEJsonEncoder）
    4. 验证角色编码
    5. 自动修正节点配置
    6. 返回结构化结果
    """
    
    async def __call__(self, state: ApprovalAIState) -> Dict[str, Any]:
        """执行审批流程解析
        
        Args:
            state: 当前状态
        
        Returns:
            状态更新字典（LangGraph 会自动合并）
        """
        # 1. 获取 AI 配置
        # 2. 构建 System Prompt
        # 3. 流式调用 AI API
        # 4. 解析 JSON
        # 5. 验证角色编码
        # 6. 自动修正节点配置
        # 7. 返回结果
        pass
    
    def _validate_roles(self, nodes: List[Dict]) -> List[str]:
        """验证审批角色编码是否有效
        
        Returns:
            无效角色列表（空列表表示全部有效）
        """
        invalid = [n.get("approve_role") for n in nodes 
                   if n.get("approve_role") not in ALLOWED_APPROVAL_ROLES]
        return invalid
    
    def _auto_correct_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """自动修正节点配置
        
        修正规则：
        1. node_order 连续性：调整为从 1 开始连续
        2. node_code 重复：自动添加序号区分
        """
        # 修正 node_order
        for i, node in enumerate(nodes):
            node["node_order"] = i + 1
        
        # 修正 node_code 重复
        seen = set()
        for node in nodes:
            if node["node_code"] in seen:
                node["node_code"] = f"{node['node_code']}_{node['node_order']}"
            seen.add(node["node_code"])
        
        return nodes
```

### 4.3 ApprovalAITool

```python
# langgraph/tools/approval_ai_tool.py

import httpx
import json
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.langgraph.sse_wrapper import SSEJsonEncoder

class ApprovalAITool:
    """审批流程解析工具
    
    职责：
    - 低层 AI API 调用
    - 流式响应处理
    - JSON 解析（使用 SSEJsonEncoder）
    
    复用 base_parser 的核心逻辑，但增强错误处理
    """
    
    async def parse_stream(
        self,
        db: Session,
        system_prompt: str,
        user_message: str,
        team_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式解析
        
        Yields:
            - {"event": "content", "content": "..."}  AI 内容片段
            - {"event": "full_content", "content": "..."}  完整内容
            - {"event": "error", "message": "..."}  错误信息
        """
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            yield {"event": "error", "message": "AI 配置未设置"}
            return
        
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            yield {"event": "error", "message": "无法获取 API Key"}
            return
        
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
            "stream": True
            # 注意：不使用 response_format，兼容更多模型
        }
        
        full_content = ""
        
        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity"
                    },
                    json=request_body
                ) as response:
                    response.raise_for_status()
                    
                    buffer = ""
                    async for text_chunk in response.aiter_text():
                        buffer += text_chunk
                        lines = buffer.split('\n')
                        buffer = lines[-1] if lines else ""
                        
                        for line in lines[:-1]:
                            if not line or not line.startswith("data: "):
                                continue
                            
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content_piece = delta.get("content", "")
                                    if content_piece:
                                        full_content += content_piece
                                        yield {"event": "content", "content": content_piece}
                            except json.JSONDecodeError:
                                continue
                    
                    # 发送完整内容
                    yield {"event": "full_content", "content": full_content}
        
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:200]
            yield {"event": "error", "message": f"AI 服务错误 {e.response.status_code}: {error_detail}"}
        except Exception as e:
            yield {"event": "error", "message": f"解析异常: {type(e).__name__}: {str(e)}"}
    
    def clean_json_response(self, content: str) -> str:
        """清理 JSON 响应中的 markdown 代码块"""
        clean = content.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return clean.strip()
    
    def parse_json(self, content: str) -> Dict[str, Any]:
        """解析 JSON 内容
        
        使用 SSEJsonEncoder 确保 Decimal 等类型正确处理
        """
        clean = self.clean_json_response(content)
        return json.loads(clean)

# 单例
approval_ai_tool = ApprovalAITool()
```

### 4.4 System Prompt 模板（双花括号转义）

```python
# langgraph/prompts/approval_ai_prompt.py

PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE = """你是 CRMWolf 系统的审批流程配置专家。

【当前日期】
今天是 {current_date}

你的任务是根据用户描述生成审批流程及其节点配置。

## 需要生成的内容

**审批流程信息**：
- flow_name: 流程名称（如：标准合同审批、大额合同审批）
- flow_code: 流程编码（英文大写+下划线，如：STANDARD、LARGE_AMOUNT）
- description: 流程描述（一句话说明适用场景）
- min_amount: 最小金额（元，可选，用于金额范围匹配）
- max_amount: 最大金额（元，可选，用于金额范围匹配）
- license_type: 授权类型（可选，如：STANDARD、PROFESSIONAL、ENTERPRISE）

**审批节点列表**（每个节点包含）：
- node_name: 节点名称（如：销售总监审批）
- node_code: 节点编码（英文大写+下划线）
- node_order: 节点顺序（从1开始递增）
- approve_role: 审批角色编码（必须是系统预定义角色）
- description: 节点描述（可选）
- is_required: 是否必须审批（默认1）

## 审批角色编码（系统预定义，必须使用以下编码）

| 编码 | 角色名称 | 适用场景 |
|------|----------|----------|
| TEAM_ADMIN | 团队所有者 | 最高权限审批，适合总经理、老板审批 |
| SALES_DIRECTOR | 销售总监 | 销售相关审批，适合部门经理、销售负责人审批 |
| FINANCE | 财务人员 | 财务相关审批，适合财务审核、发票审批 |
| SALES_MEMBER | 销售成员 | 一般审批，适合基础流程 |

## 输出格式

你必须输出严格的 JSON 格式：
```json
{{                                  # 双花括号转义
  "flow": {{
    "flow_name": "审批流程名称",
    "flow_code": "流程编码",
    "description": "流程描述",
    "min_amount": 最小金额或null,
    "max_amount": 最大金额或null,
    "license_type": "授权类型或null",
    "nodes": [
      {{
        "node_name": "节点名称",
        "node_code": "节点编码",
        "node_order": 顺序号,
        "approve_role": "审批角色编码",
        "description": "节点描述（可选）",
        "is_required": 1
      }}
    ]
  }},
  "thinking_process": "你的思考过程"
}}                                  # 双花括号转义结束
```

## 示例

用户输入："创建一个标准合同审批流程，销售总监审批然后财务审批"

正确输出：
```json
{{                                  # 双花括号转义
  "flow": {{
    "flow_name": "标准合同审批",
    "flow_code": "STANDARD",
    "description": "适用于普通合同的标准审批流程",
    "min_amount": null,
    "max_amount": null,
    "license_type": null,
    "nodes": [
      {{
        "node_name": "销售总监审批",
        "node_code": "SALES_REVIEW",
        "node_order": 1,
        "approve_role": "SALES_DIRECTOR",
        "description": "销售总监审核合同内容",
        "is_required": 1
      }},
      {{
        "node_name": "财务审批",
        "node_code": "FINANCE_CHECK",
        "node_order": 2,
        "approve_role": "FINANCE",
        "description": "财务审核合同金额和条款",
        "is_required": 1
      }}
    ]
  }},
  "thinking_process": "识别为标准合同审批流程，2个节点。销售总监对应SALES_DIRECTOR，财务对应FINANCE，均使用系统预定义角色。无金额限制，适用于所有合同。"
}}                                  # 双花括号转义结束
```
"""

def build_approval_ai_prompt(current_date: str) -> str:
    """构建审批 AI System Prompt
    
    使用 Python .format() 正确替换 {current_date}
    所有 JSON 示例中的花括号已转义为双花括号 {{ }}
    """
    return PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date=current_date)
```

---

## 5. Schema 优化

### 5.1 ApprovalAIParsedFlow 变更

```python
# schemas/approval_ai.py

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
# 移除 Decimal 导入
# from decimal import Decimal  # REMOVED

class ApprovalAIParsedFlow(BaseModel):
    """AI 解析的审批流程
    
    变更说明：
    - min_amount/max_amount 改为 float 类型
    - 添加 to_sse_dict() 方法
    """
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: Optional[str] = Field(None, description="流程描述")
    
    # 改为 float 类型，彻底解决 Decimal 序列化问题
    min_amount: Optional[float] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[float] = Field(None, ge=0, description="最大金额（元）")
    
    license_type: Optional[str] = Field(None, description="授权类型，如：STANDARD")
    nodes: List[ApprovalAIParsedNode] = Field(..., min_length=1, description="审批节点列表")
    
    def to_sse_dict(self) -> Dict[str, Any]:
        """转换为 SSE 可序列化的字典
        
        显式调用 model_dump(mode='json') 确保 Decimal 等类型转换
        """
        return self.model_dump(mode='json')

class ApprovalAICreateRequest(BaseModel):
    """创建审批流程请求（用户确认后）
    
    注意：保持 Decimal 类型，因为数据库层使用 Decimal
    """
    flow_name: str
    flow_code: str
    description: Optional[str] = None
    
    # 创建接口保持 Decimal（数据库层）
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_amount: Optional[Decimal] = Field(None, ge=0)
    
    license_type: Optional[str] = None
    nodes: List[ApprovalNodeCreate]
```

---

## 6. 错误处理设计

### 6.1 三层错误捕获

```
┌─────────────────────────────────────────────────────────────┐
│                     错误处理层级                              │
│                                                              │
│  Level 1: Node 内部                                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ApprovalAINode                                       │    │
│  │ - httpx.HTTPStatusError → state.error_message        │    │
│  │ - json.JSONDecodeError → state.validation_errors     │    │
│  │ - Exception → logger.error() + state.error_message   │    │
│  │                                                      │    │
│  │ 关键：所有异常都更新 state，不中断生成器              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Level 2: SSE Wrapper                                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ stream_sse_events()                                  │    │
│  │ - 捕获 Node 返回的 error 状态                         │    │
│  │ - 构建 error SSE 事件                                │    │
│  │ - 确保发送 [DONE] 事件                               │    │
│  │                                                      │    │
│  │ 关键：使用 SSEJsonEncoder 序列化所有事件              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Level 3: API 层                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ approval_ai.py                                       │    │
│  │ - 捕获 SSE Wrapper 异常                              │    │
│  │ - 返回最后一个 error 事件                            │    │
│  │ - 记录完整错误日志                                   │    │
│  │                                                      │    │
│  │ 关键：确保 HTTP 响应正常关闭                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 错误事件格式

```python
# 成功流程
{"event": "status", "message": "正在分析审批流程配置..."}
{"event": "content", "content": "..."}  # 多次
{"event": "parsed", "flow": {...}, "thinking_process": "..."}
{"event": "done", "success": true}

# 错误流程
{"event": "status", "message": "正在分析审批流程配置..."}
{"event": "content", "content": "..."}  # 可能部分
{"event": "error", "message": "AI 服务错误 400: ..."}
{"event": "done", "success": false}
```

---

## 7. API 层兼容性

### 7.1 端点保持不变

```python
# api/approval_ai.py 保持不变

@router.post("/parse")
async def parse_approval_flow(
    request: ApprovalAIParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
):
    """
    AI 解析审批流程配置（SSE 流式响应）
    
    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回结构化配置
    - error: 错误信息
    - done: 流结束标记
    
    内部调用 LangGraph approval_ai_node
    复用 SSE wrapper 的事件格式
    """
    # 内部切换到 LangGraph
    async def generate_sse():
        async for event in langgraph_stream_approval_ai(
            user_message=request.content,
            team_id=team_id
        ):
            yield f"data: {json.dumps(event, cls=SSEJsonEncoder)}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

### 7.2 前端兼容性

- SSE 事件格式不变
- 字段结构不变
- 无需前端修改

---

## 8. 实现优先级

### Phase 1：基础设施

1. 创建 `prompts/approval_ai_prompt.py`（双花括号模板）
2. 创建 `tools/approval_ai_tool.py`（解析工具）
3. 修改 `state.py`（添加 ApprovalAIState）

### Phase 2：核心节点

1. 创建 `nodes/approval_ai.py`（ApprovalAINode）
2. 修改 `graph.py`（添加路由分支）
3. 修改 `schemas/approval_ai.py`（float 类型）

### Phase 3：集成与弃用

1. 修改 `api/approval_ai.py`（调用 LangGraph）
2. 标记 `approval_ai_parser.py` 为 deprecated
3. 修改 `base_parser.py`（移除 response_format）

---

## 9. 测试策略

### 9.1 单元测试

- `test_approval_ai_node.py`：Node 逻辑测试
- `test_approval_ai_tool.py`：Tool 解析测试
- `test_approval_ai_prompt.py`：Prompt 格式化测试

### 9.2 集成测试

- SSE 流完整流程测试
- 错误场景测试（网络错误、JSON 解析错误）
- Decimal 序列化测试

### 9.3 手动验证

```bash
# 测试命令
curl 'http://8.134.219.103/api/v1/approval-ai/parse' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  --data-raw '{"content":"创建一个 0-10 万的审批流程，需要销售总监审批"}'
```

---

## 10. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| LangGraph 架构理解复杂 | 参考现有 AI 助手实现，复用相同模式 |
| 迁移过程中服务中断 | 保留兼容层，内部切换实现 |
| 模板转义遗漏 | 编写模板验证脚本，自动检测未转义花括号 |
| float 精度问题 | 金额字段精度要求不高（元级别），float 足够 |

---

## 11. 附录

### 11.1 相关文件清单

| 文件 | 路径 | 操作 |
|------|------|------|
| approval_ai_prompt.py | `services/langgraph/prompts/` | 新增 |
| approval_ai_tool.py | `services/langgraph/tools/` | 新增 |
| approval_ai.py | `services/langgraph/nodes/` | 新增 |
| state.py | `services/langgraph/` | 修改 |
| graph.py | `services/langgraph/` | 修改 |
| approval_ai.py | `schemas/` | 修改 |
| base_parser.py | `services/ai_parser/` | 修改 |
| approval_ai_parser.py | `services/` | 弃用 |

### 11.2 参考

- LangGraph SSE Wrapper: `services/langgraph/sse_wrapper.py`
- EntityAIParserBase: `services/ai_parser/base_parser.py`
- Lead Parser 示例: `services/ai_parser/lead_parser.py`

---

**文档版本**: v1.0
**状态**: 待用户审核
**下一步**: 用户审核后调用 writing-plans skill
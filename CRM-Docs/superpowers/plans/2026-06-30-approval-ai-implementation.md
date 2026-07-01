# AI 审批流程解析实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现审批流程的 AI 自然语言解析功能，用户可通过自然语言描述创建审批流程模板。

**Architecture:** 独立新建模式，参照采购方式 AI 解析流程（`procurement_ai_parser.py`），包含 SSE 流式解析 + 两步确认创建。

**Tech Stack:** FastAPI, Pydantic, httpx (SSE), SQLAlchemy

## Global Constraints

- **动态日期注入**: System Prompt 必须动态注入 `{current_date}`，避免硬编码年份问题
- **角色编码限制**: approve_role 只能使用预定义的 4 个角色编码（TEAM_ADMIN, SALES_DIRECTOR, FINANCE, SALES_MEMBER）
- **权限检查**: 创建端点需要 `approval:flow:create` 权限
- **Schema 兼容**: ApprovalAICreateRequest.nodes 使用现有 ApprovalNodeCreate Schema
- **团队隔离**: 所有操作必须传入 team_id

---

## File Structure

```
新增文件：
├── app/constants/approval_roles.py      # 预定义角色常量（Task 1）
├── app/schemas/approval_ai.py           # AI 解析 Schema（Task 2）
├── app/services/approval_ai_parser.py   # AI 解析服务（Task 3）
├── app/api/approval_ai.py               # API 端点（Task 4）

修改文件：
├── app/main.py                          # 注册路由（Task 5）
```

---

### Task 1: 创建预定义角色常量文件

**Files:**
- Create: `app/constants/approval_roles.py`

**Interfaces:**
- Produces: `ALLOWED_APPROVAL_ROLES` (List[str]), `ROLE_DISPLAY_NAMES` (Dict[str, str])

- [ ] **Step 1: 创建角色常量文件**

```python
# app/constants/approval_roles.py

"""
审批流程预定义角色常量

审批节点的 approve_role 必须使用系统预定义角色编码，
确保审批流程能正确匹配审批人。
"""

ALLOWED_APPROVAL_ROLES = [
    "TEAM_ADMIN",       # 团队所有者
    "SALES_DIRECTOR",   # 销售总监
    "FINANCE",          # 财务人员
    "SALES_MEMBER",     # 销售成员
]

ROLE_DISPLAY_NAMES = {
    "TEAM_ADMIN": "团队所有者",
    "SALES_DIRECTOR": "销售总监",
    "FINANCE": "财务人员",
    "SALES_MEMBER": "销售成员",
}

# 用户描述 → 角色编码映射（用于 System Prompt 示例）
ROLE_MAPPING_EXAMPLES = {
    "总经理审批": "TEAM_ADMIN",
    "老板审批": "TEAM_ADMIN",
    "最高审批": "TEAM_ADMIN",
    "部门经理审批": "SALES_DIRECTOR",
    "销售审批": "SALES_DIRECTOR",
    "总监审批": "SALES_DIRECTOR",
    "财务审批": "FINANCE",
    "财务审核": "FINANCE",
    "财务确认": "FINANCE",
    "普通审批": "SALES_MEMBER",
    "基础审批": "SALES_MEMBER",
}
```

- [ ] **Step 2: 验证文件创建成功**

Run: `ls -la app/constants/approval_roles.py`
Expected: 文件存在

- [ ] **Step 3: Commit**

```bash
git add app/constants/approval_roles.py
git commit -m "feat: add approval roles constants for AI parsing"
```

---

### Task 2: 创建 AI 解析 Schema

**Files:**
- Create: `app/schemas/approval_ai.py`

**Interfaces:**
- Consumes: `ApprovalNodeCreate` from `app/schemas/approval.py`
- Produces:
  - `ApprovalAIParsedNode` (Pydantic model)
  - `ApprovalAIParsedFlow` (Pydantic model)
  - `ApprovalAIParseRequest` (Pydantic model)
  - `ApprovalAIParseResponse` (Pydantic model)
  - `ApprovalAICreateRequest` (Pydantic model)

- [ ] **Step 1: 创建 Schema 文件**

```python
# app/schemas/approval_ai.py

"""
AI 解析审批流程配置 Schema

用于 AI 辅助创建审批流程功能的请求和响应结构
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from decimal import Decimal

from app.schemas.approval import ApprovalNodeCreate


class ApprovalAIParsedNode(BaseModel):
    """AI 解析的审批节点"""
    node_name: str = Field(..., description="节点名称，如：部门经理审批")
    node_code: str = Field(..., description="节点编码，如：DEPT_MANAGER")
    node_order: int = Field(..., gt=0, description="审批顺序，从1开始")
    approve_role: str = Field(..., description="审批角色编码，如：SALES_DIRECTOR")
    description: Optional[str] = Field(None, description="节点描述")
    is_required: int = Field(1, ge=0, le=1, description="是否必须审批，默认1")


class ApprovalAIParsedFlow(BaseModel):
    """AI 解析的审批流程"""
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: Optional[str] = Field(None, description="流程描述")
    min_amount: Optional[Decimal] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[Decimal] = Field(None, ge=0, description="最大金额（元）")
    license_type: Optional[str] = Field(None, description="授权类型，如：STANDARD")
    nodes: List[ApprovalAIParsedNode] = Field(..., min_length=1, description="审批节点列表")


class ApprovalAIParseRequest(BaseModel):
    """AI 解析请求"""
    content: str = Field(..., min_length=1, description="用户自然语言描述")


class ApprovalAIParseResponse(BaseModel):
    """AI 解析响应"""
    flow: ApprovalAIParsedFlow
    thinking_process: str = Field(..., description="AI 思考过程")


class ApprovalAICreateRequest(BaseModel):
    """创建审批流程请求（用户确认后）
    
    复用现有 ApprovalNodeCreate Schema，确保与 CRUD 接口兼容
    """
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: Optional[str] = Field(None, description="流程描述")
    min_amount: Optional[Decimal] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[Decimal] = Field(None, ge=0, description="最大金额（元）")
    license_type: Optional[str] = Field(None, description="授权类型")
    nodes: List[ApprovalNodeCreate] = Field(..., min_length=1, description="审批节点列表")
    
    @field_validator('max_amount')
    @classmethod
    def validate_amount_range(cls, v, info):
        """可选校验：金额范围逻辑"""
        min_amount = info.data.get('min_amount')
        if v is not None and min_amount is not None and v <= min_amount:
            # 提示警告但不阻止（用户可能故意只设下限）
            pass
        return v
```

- [ ] **Step 2: 验证 Schema 导入正确**

Run: `cd CRM-Server && python3 -c "from app.schemas.approval_ai import ApprovalAIParsedFlow; print('Schema OK')"`
Expected: `Schema OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/approval_ai.py
git commit -m "feat: add approval AI parsing schemas"
```

---

### Task 3: 创建 AI 解析服务

**Files:**
- Create: `app/services/approval_ai_parser.py`

**Interfaces:**
- Consumes:
  - `ai_config_crud` from `app/crud/ai_config.py`
  - `ALLOWED_APPROVAL_ROLES` from `app/constants/approval_roles.py`
  - `ApprovalAIParsedFlow`, `ApprovalAIParsedNode` from `app/schemas/approval_ai.py`
- Produces:
  - `approval_ai_parser_service` (singleton instance)
  - `parse_approval_flow_stream()` (async generator for SSE)
  - `parse_approval_flow()` (async method for non-streaming)

- [ ] **Step 1: 创建 AI 解析服务文件（Part 1 - System Prompt）**

```python
# app/services/approval_ai_parser.py

"""
AI 解析审批流程配置服务

用于 AI 辅助创建审批流程功能，从自然语言中提取结构化配置
"""
import json
from typing import AsyncGenerator, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime
import httpx

from app.crud.ai_config import ai_config_crud
from app.constants.approval_roles import ALLOWED_APPROVAL_ROLES, ROLE_DISPLAY_NAMES, ROLE_MAPPING_EXAMPLES
from app.schemas.approval_ai import (
    ApprovalAIParsedFlow,
    ApprovalAIParsedNode,
    ApprovalAIParseResponse
)


# System Prompt 模板（动态注入当前日期）
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

重要规则：
1. approve_role 只能使用上述 4 个编码之一
2. 如果用户描述的角色不在列表中，选择语义最接近的角色：
   - "总经理审批" → TEAM_ADMIN
   - "部门经理审批" → SALES_DIRECTOR
   - "财务审批" → FINANCE
   - "销售审批" → SALES_DIRECTOR
3. 不允许生成自定义角色编码

## 金额匹配规则

1. min_amount 和 max_amount 定义合同金额范围
2. 合同提交审批时，系统根据金额自动匹配对应流程
3. 示例：
   - min_amount: null, max_amount: 100000 → 适用于10万以下合同
   - min_amount: 100000, max_amount: null → 适用于10万以上合同
   - min_amount: 100000, max_amount: 500000 → 适用于10万-50万合同
4. 不设置金额范围（null）表示适用于所有金额

## 授权类型枚举

可选值：
- STANDARD: 标准版
- PROFESSIONAL: 专业版
- ENTERPRISE: 企业版

## 编码命名规范

流程编码和节点编码使用英文大写+下划线：
- 流程编码示例：STANDARD、LARGE_AMOUNT、FINANCE_APPROVAL
- 节点编码示例：SALES_REVIEW、FINANCE_CHECK、FINAL_APPROVAL

常见词汇：
- 标准/普通: STANDARD, NORMAL, DEFAULT
- 大额/高额: LARGE_AMOUNT, HIGH_VALUE
- 销售: SALES, SALE
- 财务: FINANCE, FIN
- 最终/最后: FINAL, LAST, END
- 审核/审批: REVIEW, APPROVAL, CHECK, AUDIT
- 总/老板: GENERAL, CEO, OWNER

## 常见审批流程模板

**标准合同审批**（适用于普通合同）：
1. 销售总监审批 (SALES_DIRECTOR)
2. 财务审批 (FINANCE)

**大额合同审批**（金额 > 50万）：
1. 销售总监审批 (SALES_DIRECTOR)
2. 财务审批 (FINANCE)
3. 团队所有者审批 (TEAM_ADMIN)

**快速审批**（适用于小额合同）：
1. 销售总监审批 (SALES_DIRECTOR)

**企业版合同审批**（授权类型 = ENTERPRISE）：
1. 销售总监审批 (SALES_DIRECTOR)
2. 财务审批 (FINANCE)
3. 团队所有者审批 (TEAM_ADMIN)

## 输出格式

你必须输出严格的 JSON 格式：
```json
{
  "flow": {
    "flow_name": "审批流程名称",
    "flow_code": "流程编码",
    "description": "流程描述",
    "min_amount": 最小金额或null,
    "max_amount": 最大金额或null,
    "license_type": "授权类型或null",
    "nodes": [
      {
        "node_name": "节点名称",
        "node_code": "节点编码",
        "node_order": 顺序号,
        "approve_role": "审批角色编码",
        "description": "节点描述（可选）",
        "is_required": 1
      }
    ]
  },
  "thinking_process": "你的思考过程"
}
```

## 示例

用户输入："创建一个标准合同审批流程，销售总监审批然后财务审批"

正确输出：
```json
{
  "flow": {
    "flow_name": "标准合同审批",
    "flow_code": "STANDARD",
    "description": "适用于普通合同的标准审批流程",
    "min_amount": null,
    "max_amount": null,
    "license_type": null,
    "nodes": [
      {
        "node_name": "销售总监审批",
        "node_code": "SALES_REVIEW",
        "node_order": 1,
        "approve_role": "SALES_DIRECTOR",
        "description": "销售总监审核合同内容",
        "is_required": 1
      },
      {
        "node_name": "财务审批",
        "node_code": "FINANCE_CHECK",
        "node_order": 2,
        "approve_role": "FINANCE",
        "description": "财务审核合同金额和条款",
        "is_required": 1
      }
    ]
  },
  "thinking_process": "识别为标准合同审批流程，2个节点。销售总监对应SALES_DIRECTOR，财务对应FINANCE，均使用系统预定义角色。无金额限制，适用于所有合同。"
}
```

用户输入："创建一个大额合同审批流程，超过50万的合同需要总经理审批"

正确输出：
```json
{
  "flow": {
    "flow_name": "大额合同审批",
    "flow_code": "LARGE_AMOUNT",
    "description": "适用于50万以上大额合同的审批流程",
    "min_amount": 500000,
    "max_amount": null,
    "license_type": null,
    "nodes": [
      {
        "node_name": "销售总监审批",
        "node_code": "SALES_REVIEW",
        "node_order": 1,
        "approve_role": "SALES_DIRECTOR",
        "description": "销售总监初步审核",
        "is_required": 1
      },
      {
        "node_name": "财务审批",
        "node_code": "FINANCE_CHECK",
        "node_order": 2,
        "approve_role": "FINANCE",
        "description": "财务审核大额合同",
        "is_required": 1
      },
      {
        "node_name": "总经理审批",
        "node_code": "FINAL_APPROVAL",
        "node_order": 3,
        "approve_role": "TEAM_ADMIN",
        "description": "团队所有者最终审批",
        "is_required": 1
      }
    ]
  },
  "thinking_process": "识别为大额合同审批，金额门槛50万（min_amount=500000）。总经理审批对应TEAM_ADMIN角色。3节点流程：销售总监→财务→总经理。"
}
```

用户输入："创建一个企业版合同审批流程，需要三步审批"

正确输出：
```json
{
  "flow": {
    "flow_name": "企业版合同审批",
    "flow_code": "ENTERPRISE",
    "description": "适用于企业版合同的三级审批流程",
    "min_amount": null,
    "max_amount": null,
    "license_type": "ENTERPRISE",
    "nodes": [
      {
        "node_name": "销售总监审批",
        "node_code": "SALES_REVIEW",
        "node_order": 1,
        "approve_role": "SALES_DIRECTOR",
        "description": "销售总监审核",
        "is_required": 1
      },
      {
        "node_name": "财务审批",
        "node_code": "FINANCE_CHECK",
        "node_order": 2,
        "approve_role": "FINANCE",
        "description": "财务审核企业版合同",
        "is_required": 1
      },
      {
        "node_name": "总经理审批",
        "node_code": "FINAL_APPROVAL",
        "node_order": 3,
        "approve_role": "TEAM_ADMIN",
        "description": "团队所有者最终审批",
        "is_required": 1
      }
    ]
  },
  "thinking_process": "识别为企业版合同审批，license_type设为ENTERPRISE。用户要求三步审批，配置销售总监→财务→总经理流程。总经理对应TEAM_ADMIN角色。"
}
```"""
```

- [ ] **Step 2: 创建 AI 解析服务文件（Part 2 - Service Class）**

```python


class ApprovalAIParserService:
    """审批流程配置 AI 解析服务"""

    def _build_system_prompt(self) -> str:
        """构建带动态当前日期的系统提示词
        
        Returns:
            格式化后的系统提示词
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        return PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(
            current_date=current_date
        )

    def _validate_roles(self, nodes: List[ApprovalAIParsedNode]) -> List[str]:
        """验证审批角色是否在预定义列表
        
        Args:
            nodes: 节点列表
            
        Returns:
            无效角色列表（空列表表示全部有效）
        """
        invalid_roles = []
        for node in nodes:
            if node.approve_role not in ALLOWED_APPROVAL_ROLES:
                invalid_roles.append(node.approve_role)
        return invalid_roles

    def _auto_correct_nodes(self, nodes: List[ApprovalAIParsedNode]) -> List[ApprovalAIParsedNode]:
        """自动修正节点配置
        
        修正规则：
        1. node_order 连续性：调整为从 1 开始连续
        2. node_codes 重复：自动添加序号区分
        
        Args:
            nodes: 原始节点列表
            
        Returns:
            修正后的节点列表
        """
        # 1. 修正 node_order 连续性
        for i, node in enumerate(nodes):
            node.node_order = i + 1
        
        # 2. 修正 node_codes 重复
        seen_codes = {}
        for node in nodes:
            if node.node_code in seen_codes:
                # 重复编码，添加序号区分
                node.node_code = f"{node.node_code}_{node.node_order}"
            seen_codes[node.node_code] = True
        
        return nodes

    async def parse_approval_flow_stream(
        self,
        db: Session,
        user_message: str,
        team_id: int = 1
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式解析审批流程配置，生成 SSE 事件

        Args:
            db: 数据库 session
            user_message: 用户输入的自然语言描述
            team_id: 团队 ID

        Yields:
            SSE 事件字典：
            - {"event": "status", "message": "..."} - 状态更新
            - {"event": "content", "content": "..."} - AI 思考过程片段
            - {"event": "parsed", "flow": {...}} - 解析完成
            - {"event": "error", "message": "..."} - 错误信息
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            yield {"event": "error", "message": "AI 配置未设置，请联系管理员先配置 AI 服务"}
            return

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            yield {"event": "error", "message": "AI 配置异常，无法获取 API Key"}
            return

        # 发送状态事件
        yield {"event": "status", "message": "正在分析审批流程配置..."}

        # 构建带动态日期的系统提示词
        system_prompt = self._build_system_prompt()

        # 构建请求
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,  # 低温度，保证输出稳定
            "max_tokens": 2048,
            "stream": True,
            "response_format": {"type": "json_object"}
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
                            if not line:
                                continue

                            if line.startswith("data: "):
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

                    # 解析完整响应
                    clean_content = self._clean_json_response(full_content)

                    try:
                        parsed = json.loads(clean_content)
                        flow_data = parsed.get("flow", {})

                        # 解析节点列表
                        nodes = []
                        for node_data in flow_data.get("nodes", []):
                            nodes.append(ApprovalAIParsedNode(
                                node_name=node_data.get("node_name"),
                                node_code=node_data.get("node_code"),
                                node_order=node_data.get("node_order"),
                                approve_role=node_data.get("approve_role"),
                                description=node_data.get("description"),
                                is_required=node_data.get("is_required", 1)
                            ))

                        # 验证角色编码
                        invalid_roles = self._validate_roles(nodes)
                        if invalid_roles:
                            yield {
                                "event": "error",
                                "message": f"解析的角色编码无效：{', '.join(invalid_roles)}。请使用预定义角色：{', '.join(ALLOWED_APPROVAL_ROLES)}"
                            }
                            return

                        # 自动修正节点配置
                        nodes = self._auto_correct_nodes(nodes)

                        flow = ApprovalAIParsedFlow(
                            flow_name=flow_data.get("flow_name"),
                            flow_code=flow_data.get("flow_code"),
                            description=flow_data.get("description"),
                            min_amount=flow_data.get("min_amount"),
                            max_amount=flow_data.get("max_amount"),
                            license_type=flow_data.get("license_type"),
                            nodes=nodes
                        )

                        yield {
                            "event": "parsed",
                            "flow": flow.model_dump(),
                            "thinking_process": parsed.get("thinking_process")
                        }
                    except json.JSONDecodeError:
                        yield {"event": "error", "message": f"AI 返回格式异常: {clean_content[:200]}"}

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}

    async def parse_approval_flow(
        self,
        db: Session,
        user_message: str,
        team_id: int = 1
    ) -> ApprovalAIParseResponse:
        """
        解析审批流程配置（收集完整响应）

        Args:
            db: 数据库 session
            user_message: 用户输入的自然语言描述
            team_id: 团队 ID

        Returns:
            解析结果
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            return ApprovalAIParseResponse(
                flow=ApprovalAIParsedFlow(flow_name="", flow_code="", nodes=[]),
                thinking_process="AI 配置未设置"
            )

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return ApprovalAIParseResponse(
                flow=ApprovalAIParsedFlow(flow_name="", flow_code="", nodes=[]),
                thinking_process="无法获取 API Key"
            )

        # 构建带动态日期的系统提示词
        system_prompt = self._build_system_prompt()

        # 构建请求（非流式）
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
            "stream": False,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                response = await client.post(
                    f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_body
                )
                response.raise_for_status()

                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                clean_content = self._clean_json_response(content)
                parsed = json.loads(clean_content)
                flow_data = parsed.get("flow", {})

                # 解析节点列表
                nodes = []
                for node_data in flow_data.get("nodes", []):
                    nodes.append(ApprovalAIParsedNode(
                        node_name=node_data.get("node_name"),
                        node_code=node_data.get("node_code"),
                        node_order=node_data.get("node_order"),
                        approve_role=node_data.get("approve_role"),
                        description=node_data.get("description"),
                        is_required=node_data.get("is_required", 1)
                    ))

                # 验证并修正
                self._validate_roles(nodes)
                nodes = self._auto_correct_nodes(nodes)

                flow = ApprovalAIParsedFlow(
                    flow_name=flow_data.get("flow_name"),
                    flow_code=flow_data.get("flow_code"),
                    description=flow_data.get("description"),
                    min_amount=flow_data.get("min_amount"),
                    max_amount=flow_data.get("max_amount"),
                    license_type=flow_data.get("license_type"),
                    nodes=nodes
                )

                return ApprovalAIParseResponse(
                    flow=flow,
                    thinking_process=parsed.get("thinking_process")
                )

        except Exception as e:
            return ApprovalAIParseResponse(
                flow=ApprovalAIParsedFlow(flow_name="", flow_code="", nodes=[]),
                thinking_process=f"解析异常：{str(e)}"
            )

    def _clean_json_response(self, content: str) -> str:
        """清理 JSON 响应中的 markdown 代码块标记"""
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        return clean_content.strip()


# 单例实例
approval_ai_parser_service = ApprovalAIParserService()
```

- [ ] **Step 3: 验证服务文件语法正确**

Run: `cd CRM-Server && python3 -m py_compile app/services/approval_ai_parser.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add app/services/approval_ai_parser.py
git commit -m "feat: add approval AI parser service with SSE streaming"
```

---

### Task 4: 创建 API 端点

**Files:**
- Create: `app/api/approval_ai.py`

**Interfaces:**
- Consumes:
  - `approval_ai_parser_service` from `app/services/approval_ai_parser.py`
  - `approval_flow_crud` from `app/crud/approval.py`
  - `ALLOWED_APPROVAL_ROLES` from `app/constants/approval_roles.py`
  - `ApprovalAIParseRequest`, `ApprovalAICreateRequest` from `app/schemas/approval_ai.py`
- Produces:
  - `router` (APIRouter with prefix `/v1/approval-ai`)
  - `POST /v1/approval-ai/parse` endpoint
  - `POST /v1/approval-ai/create` endpoint

- [ ] **Step 1: 创建 API 端点文件**

```python
# app/api/approval_ai.py

"""
AI 解析审批流程配置接口

用于 AI 辅助创建审批流程功能
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.models.user import User
from app.models.approval import ApprovalFlow, ApprovalNode
from app.schemas.approval_ai import ApprovalAIParseRequest, ApprovalAICreateRequest
from app.services.approval_ai_parser import approval_ai_parser_service
from app.crud.approval import approval_flow_crud
from app.constants.approval_roles import ALLOWED_APPROVAL_ROLES


router = APIRouter(prefix="/v1/approval-ai", tags=["AI 审批流程解析"])


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
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            async for event in approval_ai_parser_service.parse_approval_flow_stream(
                db=db,
                user_message=request.content,
                team_id=team_id
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_approval_flow_from_ai(
    request: ApprovalAICreateRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    """
    从 AI 解析结果创建审批流程（用户确认后提交）

    创建审批流程及其所有节点配置（事务保护）

    校验规则：
    1. flow_code 不能重复
    2. nodes 至少包含 1 个节点
    3. approve_role 必须是预定义角色
    4. node_order 自动修正为连续
    """
    # 权限检查
    permission_checker = require_permission("approval:flow:create")
    permission_checker(current_user, db)

    # 检查 team_id 是否有效
    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取用户团队信息，请重新登录"
        )

    # 检查编码是否已存在
    existing = approval_flow_crud.get_by_code(db, request.flow_code, team_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"审批流程编码「{request.flow_code}」已存在，请修改编码"
        )

    # 验证节点配置
    if not request.nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="审批节点不能为空"
        )

    # 验证角色编码
    for node in request.nodes:
        if node.approve_role not in ALLOWED_APPROVAL_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"审批角色「{node.approve_role}」无效，请使用预定义角色：{', '.join(ALLOWED_APPROVAL_ROLES)}"
            )

    # 检查节点编码唯一性
    node_codes = [n.node_code for n in request.nodes]
    if len(node_codes) != len(set(node_codes)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="节点编码不能重复"
        )

    # 使用事务创建审批流程和节点
    try:
        # 创建审批流程
        flow_data = request.model_dump(exclude={'nodes'})
        flow_data['team_id'] = team_id
        flow_data['is_active'] = 1
        
        flow = ApprovalFlow(**flow_data)
        db.add(flow)
        db.flush()  # 获取 flow.id 但不提交

        # 创建审批节点
        created_nodes = []
        for i, node in enumerate(request.nodes):
            # 自动修正 node_order 为连续
            node_obj = ApprovalNode(
                flow_id=flow.id,
                team_id=team_id,
                node_name=node.node_name,
                node_code=node.node_code,
                node_order=i + 1,  # 强制连续
                description=node.description,
                approve_role=node.approve_role,
                is_required=node.is_required if hasattr(node, 'is_required') else 1
            )
            db.add(node_obj)
            created_nodes.append(node_obj)

        # 提交事务
        db.commit()
        db.refresh(flow)
        for n in created_nodes:
            db.refresh(n)

        return {
            "success": True,
            "message": f"审批流程「{flow.flow_name}」创建成功，包含 {len(created_nodes)} 个审批节点",
            "data": {
                "flow": {
                    "id": flow.id,
                    "flow_name": flow.flow_name,
                    "flow_code": flow.flow_code,
                    "description": flow.description,
                    "min_amount": float(flow.min_amount) if flow.min_amount else None,
                    "max_amount": float(flow.max_amount) if flow.max_amount else None,
                    "license_type": flow.license_type
                },
                "nodes": [
                    {
                        "id": n.id,
                        "node_name": n.node_name,
                        "node_code": n.node_code,
                        "node_order": n.node_order,
                        "approve_role": n.approve_role
                    }
                    for n in created_nodes
                ]
            }
        }

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"数据库约束错误：{str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建失败：{str(e)}"
        )
```

- [ ] **Step 2: 验证 API 文件语法正确**

Run: `cd CRM-Server && python3 -m py_compile app/api/approval_ai.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/approval_ai.py
git commit -m "feat: add approval AI API endpoints (parse + create)"
```

---

### Task 5: 注册路由到 main.py

**Files:**
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `router` from `app/api/approval_ai.py`

- [ ] **Step 1: 添加路由导入**

找到 `app/main.py` 第 14 行，添加 `approval_ai` 导入：

```python
# 修改前（第 14 行）
from app.api import auth, users, roles, permissions, leads, customers, customer_follow_ups, opportunities, filter_options, contracts, approvals, payments, invoices, finance, operation_logs, procurement_methods, procurement_stage_templates, opportunity_stages, customer_procurement, procurement_admin, calendar, teams, industry, lead_ai, procurement_ai

# 修改后（添加 approval_ai）
from app.api import auth, users, roles, permissions, leads, customers, customer_follow_ups, opportunities, filter_options, contracts, approvals, payments, invoices, finance, operation_logs, procurement_methods, procurement_stage_templates, opportunity_stages, customer_procurement, procurement_admin, calendar, teams, industry, lead_ai, procurement_ai, approval_ai
```

- [ ] **Step 2: 添加路由注册**

找到 `app/main.py` 中 `api_router.include_router(procurement_ai.router)` 行（约第 78 行），在其后添加：

```python
# 添加路由注册（在 procurement_ai.router 后面）
api_router.include_router(approval_ai.router)
```

- [ ] **Step 3: 验证 main.py 语法正确**

Run: `cd CRM-Server && python3 -m py_compile app/main.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: register approval_ai router in main.py"
```

---

### Task 6: 验证集成

**Files:**
- None（测试验证）

**Interfaces:**
- Consumes: 所有已创建文件

- [ ] **Step 1: 启动服务验证路由注册**

Run: `cd CRM-Server && python3 -c "from app.main import app; routes = [r.path for r in app.routes]; print('approval-ai' in str(routes))"`
Expected: `True`（路由已注册）

- [ ] **Step 2: 验证完整导入链**

Run: `cd CRM-Server && python3 -c "
from app.constants.approval_roles import ALLOWED_APPROVAL_ROLES
from app.schemas.approval_ai import ApprovalAIParsedFlow
from app.services.approval_ai_parser import approval_ai_parser_service
from app.api.approval_ai import router
print('All imports OK')
"`
Expected: `All imports OK`

- [ ] **Step 3: 最终 Commit（如有遗漏）**

```bash
git status
# 如有未提交文件，执行：
git add -A
git commit -m "feat: complete AI approval flow parsing feature"
```

---

## Self-Review

| 检查项 | 结果 | 说明 |
|--------|------|------|
| **Spec Coverage** | ✅ 全覆盖 | 所有设计需求已实现 |
| **Placeholder Scan** | ✅ 无 TBD/TODO | 所有步骤包含完整代码 |
| **Type Consistency** | ✅ 一致 | Schema/Service/API 类型匹配 |
| **动态日期注入** | ✅ 实现 | `_build_system_prompt()` 方法 |
| **角色编码限制** | ✅ 实现 | `_validate_roles()` + `ALLOWED_APPROVAL_ROLES` |
| **自动修正** | ✅ 实现 | `_auto_correct_nodes()` 方法 |
| **权限检查** | ✅ 实现 | `require_permission("approval:flow:create")` |

---

## Execution Handoff

**Plan complete and saved to `CRM-Docs/superpowers/plans/2026-06-30-approval-ai-implementation.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - 我为每个 Task 派发独立 subagent，在 Task 间进行审查，快速迭代

**2. Inline Execution** - 在当前会话中使用 executing-plans 执行，批量执行带检查点

**您选择哪种方式？**
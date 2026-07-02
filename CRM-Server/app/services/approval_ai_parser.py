"""
AI 解析审批流程配置服务

用于 AI 辅助创建审批流程功能，从自然语言中提取结构化配置
"""
import json
import logging
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

logger = logging.getLogger(__name__)


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


class ApprovalAIParserService:
    """审批流程配置 AI 解析服务"""

    def _build_system_prompt(self) -> str:
        """构建带动态当前日期的系统提示词

        Returns:
            格式化后的系统提示词

        注意：使用字符串替换而非 .format()，因为模板包含 JSON 示例中的花括号
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        # 使用简单替换，避免 JSON 示例中的 {} 被 format() 误解析
        return PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.replace(
            "{current_date}", current_date
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

        # 构建请求（不使用 response_format，依赖提示词引导 JSON 输出）
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,  # 低温度，保证输出稳定
            "max_tokens": 2048,
            "stream": True
            # 注意：移除 response_format 参数，因为部分 AI 模型不支持此参数
            # JSON 格式输出由系统提示词中的示例和格式说明保证
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
                    except json.JSONDecodeError as e:
                        logger.error(f"AI 返回 JSON 解析失败: {e}, 内容: {clean_content[:200]}")
                        yield {"event": "error", "message": f"AI 返回格式异常: {clean_content[:200]}"}

        except httpx.HTTPStatusError as e:
            logger.error(f"AI 服务 HTTP 错误: {e.response.status_code}, 详情: {e.response.text[:200]}")
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code} - {e.response.text[:100]}"}
        except Exception as e:
            logger.error(f"AI 服务异常: {type(e).__name__}: {str(e)}")
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

        # 构建请求（非流式，不使用 response_format）
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
            "stream": False
            # 注意：移除 response_format 参数，因为部分 AI 模型不支持此参数
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
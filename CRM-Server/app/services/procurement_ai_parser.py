"""
AI 解析采购方式配置服务

用于 AI 辅助创建采购方式功能，从自然语言中提取结构化配置
"""
import json
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session
import httpx

from app.crud.ai_config import ai_config_crud
from app.schemas.procurement_ai import (
    ProcurementAIParsedMethod,
    ProcurementAIParsedStage,
    ProcurementAIParseResponse
)


# 系统提示词：用于解析采购方式配置
PARSE_PROCUREMENT_SYSTEM_PROMPT = """你是 CRMWolf 系统的采购流程配置专家。

你的任务是根据用户描述生成采购方式及其阶段配置。

## 需要生成的内容

**采购方式信息**：
- name: 采购方式名称（如：公开招标、竞争性谈判、单一来源采购）
- code: 编码（英文大写+下划线，如：PUBLIC_BIDDING）
- description: 一句话描述

**阶段配置列表**（每个阶段包含）：
- stage_name: 阶段名称
- template_code: 阶段编码（英文大写+下划线）
- win_probability: 赢率（10-100，最后阶段为100）
- sort_order: 顺序号（从1开始递增）
- is_default_start: 是否默认起始阶段（只有第一个为true）
- can_skip: 是否可跳过（默认false）
- description: 阶段描述（可选）

## 行业参考模板

以下是常见采购方式的标准流程，供参考：

**公开招标**：
1. 发布公告 (ANNOUNCEMENT, 10%) - 发布招标公告
2. 报名登记 (REGISTRATION, 20%) - 供应商报名
3. 资格审查 (QUALIFICATION, 30%) - 审核供应商资质
4. 开标 (BID_OPENING, 50%) - 公开开标
5. 评标 (EVALUATION, 70%) - 专家评审
6. 定标 (AWARD, 90%) - 确定中标方
7. 签约 (CONTRACT, 100%) - 签订合同

**竞争性谈判**：
1. 需求确认 (NEED_CONFIRM, 20%) - 明确采购需求
2. 谈判准备 (PREPARE, 30%) - 准备谈判方案
3. 谈判实施 (NEGOTIATION, 50%) - 多轮谈判
4. 确定供应商 (SUPPLIER_SELECT, 80%) - 选择最优方案
5. 签约 (CONTRACT, 100%) - 签订合同

**单一来源采购**：
1. 申请审批 (APPLICATION, 30%) - 提交单一来源申请
2. 审批通过 (APPROVAL, 60%) - 审批流程
3. 签约 (CONTRACT, 100%) - 签订合同

**询价比价**：
1. 需求确认 (NEED_CONFIRM, 20%) - 明确采购需求
2. 询价 (INQUIRY, 40%) - 发出询价单
3. 比价分析 (COMPARISON, 60%) - 比较报价
4. 确定供应商 (SUPPLIER_SELECT, 80%) - 选择供应商
5. 签约 (CONTRACT, 100%) - 签订合同

## 编码命名规范

编码使用英文缩写，常见词汇：
- 发布/公告: ANNOUNCEMENT, ANNOUNCE, PUBLISH
- 报名/登记: REGISTRATION, REGISTER, SIGN_UP
- 资格/审查: QUALIFICATION, REVIEW, AUDIT
- 开标: BID_OPENING, OPEN_BID
- 评标/评审: EVALUATION, EVALUATE, REVIEW
- 定标/中标: AWARD, WINNER_SELECT
- 签约/合同: CONTRACT, SIGNING
- 谈判: NEGOTIATION, NEGOTIATE
- 询价: INQUIRY, INQUIRE
- 比价: COMPARISON, COMPARE
- 确认: CONFIRM, CONFIRMATION
- 审批: APPROVAL, APPROVE
- 申请: APPLICATION, APPLY
- 选择: SELECT, SELECTION

## 赢率分配原则

1. 赢率从低到高递增，体现销售成功概率的增长
2. 最后阶段（签约）赢率为 100%
3. 赢率差值建议在 10-20% 之间
4. 起始阶段通常为 10-30%
5. 关键节点阶段赢率跳跃可稍大（如评标到定标）

## 输出格式

你必须输出严格的 JSON 格式：
```json
{
  "method": {
    "name": "采购方式名称",
    "code": "采购方式编码",
    "description": "一句话描述",
    "stages": [
      {
        "stage_name": "阶段名称",
        "template_code": "阶段编码",
        "win_probability": 赢率数字,
        "sort_order": 顺序号,
        "is_default_start": true/false,
        "can_skip": true/false,
        "description": "阶段描述（可选）"
      }
    ]
  },
  "thinking_process": "你的思考过程"
}
```

## 示例

用户输入："创建一个公开招标采购方式，包含发布公告、报名、开标、评标、定标五个阶段"

正确输出：
```json
{
  "method": {
    "name": "公开招标",
    "code": "PUBLIC_BIDDING",
    "description": "政府采购标准招标流程",
    "stages": [
      {
        "stage_name": "发布公告",
        "template_code": "ANNOUNCEMENT",
        "win_probability": 10,
        "sort_order": 1,
        "is_default_start": true,
        "can_skip": false,
        "description": "发布招标公告"
      },
      {
        "stage_name": "报名",
        "template_code": "REGISTRATION",
        "win_probability": 20,
        "sort_order": 2,
        "is_default_start": false,
        "can_skip": false,
        "description": "供应商报名登记"
      },
      {
        "stage_name": "开标",
        "template_code": "BID_OPENING",
        "win_probability": 40,
        "sort_order": 3,
        "is_default_start": false,
        "can_skip": false,
        "description": "公开开标"
      },
      {
        "stage_name": "评标",
        "template_code": "EVALUATION",
        "win_probability": 60,
        "sort_order": 4,
        "is_default_start": false,
        "can_skip": false,
        "description": "专家评审"
      },
      {
        "stage_name": "定标",
        "template_code": "AWARD",
        "win_probability": 100,
        "sort_order": 5,
        "is_default_start": false,
        "can_skip": false,
        "description": "确定中标方"
      }
    ]
  },
  "thinking_process": "识别为公开招标流程，5个阶段按标准招标流程排列，赢率从10%递增至100%，起始阶段为发布公告"
}
```

用户输入："我想创建一个简单的竞争性谈判流程，三步：需求确认、谈判、签约"

正确输出：
```json
{
  "method": {
    "name": "竞争性谈判",
    "code": "COMPETITIVE_NEGOTIATION",
    "description": "简化版竞争性谈判流程",
    "stages": [
      {
        "stage_name": "需求确认",
        "template_code": "NEED_CONFIRM",
        "win_probability": 30,
        "sort_order": 1,
        "is_default_start": true,
        "can_skip": false,
        "description": "明确采购需求"
      },
      {
        "stage_name": "谈判",
        "template_code": "NEGOTIATION",
        "win_probability": 60,
        "sort_order": 2,
        "is_default_start": false,
        "can_skip": false,
        "description": "多轮商务谈判"
      },
      {
        "stage_name": "签约",
        "template_code": "CONTRACT",
        "win_probability": 100,
        "sort_order": 3,
        "is_default_start": false,
        "can_skip": false,
        "description": "签订采购合同"
      }
    ]
  },
  "thinking_process": "识别为简化的竞争性谈判，3个阶段，起始赢率30%（因为需求确认阶段成功概率较高），签约阶段100%"
}
```"""


class ProcurementAIParserService:
    """采购方式配置 AI 解析服务"""

    async def parse_procurement_method_stream(
        self,
        db: Session,
        user_message: str,
        team_id: int = 1
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式解析采购方式配置，生成 SSE 事件

        Args:
            db: 数据库 session
            user_message: 用户输入的自然语言描述
            team_id: 团队 ID

        Yields:
            SSE 事件字典
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
        yield {"event": "status", "message": "正在分析采购流程配置..."}

        # 构建请求
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": PARSE_PROCUREMENT_SYSTEM_PROMPT},
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
                        method_data = parsed.get("method", {})

                        # 解析阶段列表
                        stages = []
                        for stage_data in method_data.get("stages", []):
                            stages.append(ProcurementAIParsedStage(
                                stage_name=stage_data.get("stage_name"),
                                template_code=stage_data.get("template_code"),
                                win_probability=stage_data.get("win_probability"),
                                sort_order=stage_data.get("sort_order"),
                                is_default_start=stage_data.get("is_default_start", False),
                                can_skip=stage_data.get("can_skip", False),
                                description=stage_data.get("description")
                            ))

                        method = ProcurementAIParsedMethod(
                            name=method_data.get("name"),
                            code=method_data.get("code"),
                            description=method_data.get("description"),
                            stages=stages
                        )

                        yield {
                            "event": "parsed",
                            "method": method.model_dump(),
                            "thinking_process": parsed.get("thinking_process")
                        }
                    except json.JSONDecodeError:
                        yield {"event": "error", "message": f"AI 返回格式异常: {clean_content[:200]}"}

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}

    async def parse_procurement_method(
        self,
        db: Session,
        user_message: str,
        team_id: int = 1
    ) -> ProcurementAIParseResponse:
        """
        解析采购方式配置（收集完整响应）

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
            return ProcurementAIParseResponse(
                method=ProcurementAIParsedMethod(name="", code="", stages=[]),
                thinking_process="AI 配置未设置"
            )

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return ProcurementAIParseResponse(
                method=ProcurementAIParsedMethod(name="", code="", stages=[]),
                thinking_process="无法获取 API Key"
            )

        # 构建请求（非流式）
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": PARSE_PROCUREMENT_SYSTEM_PROMPT},
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
                method_data = parsed.get("method", {})

                # 解析阶段列表
                stages = []
                for stage_data in method_data.get("stages", []):
                    stages.append(ProcurementAIParsedStage(
                        stage_name=stage_data.get("stage_name"),
                        template_code=stage_data.get("template_code"),
                        win_probability=stage_data.get("win_probability"),
                        sort_order=stage_data.get("sort_order"),
                        is_default_start=stage_data.get("is_default_start", False),
                        can_skip=stage_data.get("can_skip", False),
                        description=stage_data.get("description")
                    ))

                method = ProcurementAIParsedMethod(
                    name=method_data.get("name"),
                    code=method_data.get("code"),
                    description=method_data.get("description"),
                    stages=stages
                )

                return ProcurementAIParseResponse(
                    method=method,
                    thinking_process=parsed.get("thinking_process")
                )

        except Exception as e:
            return ProcurementAIParseResponse(
                method=ProcurementAIParsedMethod(name="", code="", stages=[]),
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


procurement_ai_parser_service = ProcurementAIParserService()
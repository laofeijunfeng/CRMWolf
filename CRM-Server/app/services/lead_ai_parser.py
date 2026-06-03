"""
AI 解析线索信息服务

用于智能创建线索功能，从自然语言中提取结构化信息
"""
import json
from typing import AsyncGenerator, Dict, Any, Optional
from sqlalchemy.orm import Session
import httpx

from app.crud.ai_config import ai_config_crud
from app.schemas.lead_ai import LeadAIParsedInfo, LeadAIParseResponse, LeadAIFollowUpInfo
from app.services.follow_up_parser import follow_up_parser_service


# 系统提示词：用于解析线索信息
# 注意：next_follow_time 让 AI 返回原始表述，后端代码会用 parse_relative_time 转换
PARSE_LEAD_SYSTEM_PROMPT = """你是 CRMWolf 系统的线索信息解析助手。

你的任务是从用户的自然语言描述中提取线索信息，并分离出额外信息用于跟进记录。

## 需要提取的字段

**必填字段**：
- lead_name: 线索名称（通常是公司名称或项目名称）
- source: 线索来源
- city: 所在城市
- contact_name: 联系人姓名
- contact_phone: 联系电话（11位手机号）

**可选字段**：
- company_scale: 公司规模

## 线索来源枚举值

用户可能用各种描述，你需要智能匹配到以下枚举值之一：
- "线上注册": 包括网站注册、官网注册、网上注册等
- "市场活动": 包括展会、活动、营销活动等
- "客户推荐": 包括转介绍、朋友推荐、老客户介绍等
- "电话营销": 包括电话推销、电话联系、电话沟通等
- "网站咨询": 包括网上咨询、官网咨询、在线咨询等
- "展会": 包括参展、展览、博览会等
- "其他": 无法匹配到上述分类时使用

## 公司规模枚举值

用户可能说"大概500人"、"几百人"、"几十人"等，你需要智能匹配：
- "1-50人": 人数在50人以下
- "51-200人": 人数在51-200人之间
- "201-500人": 人数在201-500人之间
- "501-1000人": 人数在501-1000人之间
- "1000人以上": 人数超过1000人

如果用户未提及公司规模，不要猜测，返回 null。

## 额外信息识别

用户描述中不属于上述字段的额外信息需要提取出来，分为三部分：
- **content**: 跟进内容（业务需求、意向产品、备注等，排除"下一步计划"）
- **next_action**: 下一步动作/计划（识别"下一步"、"接下来"、"计划"等表述）
- **next_follow_time**: 下次跟进时间（识别时间表达，**输出 YYYY-MM-DD 格式的具体日期**）

**时间转换规则**（基于当前日期推算）：
- 相对时间需要转换为具体日期：
  - "下周一" → 计算下周一的具体日期
  - "下周三" → 计算下周三的具体日期
  - "三天后"/"3天后" → 当前日期+3天
  - "一周后"/"下周" → 当前日期+7天
- 具体日期保持原样：
  - "5月25日" → 2026-05-25
  - "2024-05-25" → 2024-05-25

如果无法识别对应字段，返回 null。

## 输出格式

你必须输出严格的 JSON 格式：
```json
{
  "lead_info": {
    "lead_name": "提取的线索名称",
    "source": "匹配的线索来源枚举值",
    "city": "提取的城市",
    "company_scale": "匹配的公司规模枚举值或 null",
    "contact_name": "提取的联系人姓名",
    "contact_phone": "提取的11位手机号",
    "missing_fields": ["缺失的必填字段列表"]
  },
  "follow_up_info": {
    "content": "跟进内容（除下一步计划外的信息）",
    "next_action": "下一步动作",
    "next_follow_time": "YYYY-MM-DD格式日期或null"
  },
  "thinking_process": "你的解析思考过程（简要描述如何识别各字段）"
}
```

## 解析规则

1. **公司名称识别**: 通常在"来自XX的XXX"、"XX公司"、"XXX科技"等表述中
2. **联系人识别**: 通常在最前面的人名，或在"联系人"、"负责人"、"对接人"后面
3. **电话识别**: 查找11位数字，通常以1开头
4. **城市识别**: 通常在"来自XX"、"XX的"中，或明确说"在XX"
5. **来源识别**: 根据用户的描述匹配枚举值，如"网上注册来的"→"线上注册"
6. **规模识别**: 根据人数描述匹配范围，如"五百人左右"→"501-1000人"
7. **缺失字段**: 必填字段缺失时，在 missing_fields 中列出字段名
8. **下一步计划识别**: 识别"下一步"、"接下来"、"计划"后面的内容
9. **时间转换**: 相对时间需要转换为 YYYY-MM-DD 格式的具体日期

## 示例

用户输入："张三，13800138000，来自杭州的阿里巴巴，大概500人，网上注册来的，想做电商系统，下一步推进POC部署试用，下周三再联系"

正确输出：
```json
{
  "lead_info": {
    "lead_name": "阿里巴巴",
    "source": "线上注册",
    "city": "杭州",
    "company_scale": "501-1000人",
    "contact_name": "张三",
    "contact_phone": "13800138000",
    "missing_fields": []
  },
  "follow_up_info": {
    "content": "想做电商系统",
    "next_action": "推进POC部署试用",
    "next_follow_time": "下周三"
  },
  "thinking_process": "识别联系人张三、电话、城市杭州、公司阿里巴巴、规模500人匹配501-1000人、来源网上注册匹配线上注册。额外信息中'想做电商系统'为跟进内容，'下一步推进POC部署试用'为下一步动作，'下周三'为下次跟进时间"
}
```

用户输入："有个客户叫李四，电话不记得了，在广州"

正确输出：
```json
{
  "lead_info": {
    "lead_name": null,
    "source": null,
    "city": "广州",
    "company_scale": null,
    "contact_name": "李四",
    "contact_phone": null,
    "missing_fields": ["lead_name", "source", "contact_phone"]
  },
  "follow_up_info": null,
  "thinking_process": "识别到联系人李四，城市广州，但缺少公司名称、来源和电话，无额外信息"
}
```"""


class LeadAIParserService:
    """线索信息 AI 解析服务"""

    async def parse_lead_info_stream(
        self,
        db: Session,
        user_message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式解析线索信息，生成 SSE 事件

        Args:
            db: 数据库 session
            user_message: 用户输入的自然语言描述

        Yields:
            SSE 事件字典
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db)
        if not config:
            yield {"event": "error", "message": "AI 配置未设置，请联系管理员先配置 AI 服务"}
            return

        api_key = ai_config_crud.get_decrypted_api_key(db)
        if not api_key:
            yield {"event": "error", "message": "AI 配置异常，无法获取 API Key"}
            return

        # 发送状态事件
        yield {"event": "status", "message": "正在解析线索信息..."}

        # 构建请求
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": PARSE_LEAD_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,  # 低温度，保证输出稳定
            "max_tokens": 1024,
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
                        lead_info = LeadAIParsedInfo(
                            lead_name=parsed.get("lead_info", {}).get("lead_name"),
                            source=parsed.get("lead_info", {}).get("source"),
                            city=parsed.get("lead_info", {}).get("city"),
                            company_scale=parsed.get("lead_info", {}).get("company_scale"),
                            contact_name=parsed.get("lead_info", {}).get("contact_name"),
                            contact_phone=parsed.get("lead_info", {}).get("contact_phone"),
                            missing_fields=parsed.get("lead_info", {}).get("missing_fields", [])
                        )

                        # 解析跟进信息
                        follow_up_data = parsed.get("follow_up_info")
                        follow_up_info = None
                        if follow_up_data and isinstance(follow_up_data, dict):
                            follow_up_info = LeadAIFollowUpInfo(
                                content=follow_up_data.get("content"),
                                next_action=follow_up_data.get("next_action"),
                                next_follow_time=follow_up_data.get("next_follow_time")
                            )

                        yield {
                            "event": "parsed",
                            "lead_info": lead_info.model_dump(),
                            "follow_up_info": follow_up_info.model_dump() if follow_up_info else None,
                            "thinking_process": parsed.get("thinking_process")
                        }
                    except json.JSONDecodeError:
                        yield {"event": "error", "message": f"AI 返回格式异常: {clean_content[:200]}"}

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}

    async def parse_lead_info(
        self,
        db: Session,
        user_message: str
    ) -> LeadAIParseResponse:
        """
        解析线索信息（收集完整响应）

        Args:
            db: 数据库 session
            user_message: 用户输入的自然语言描述

        Returns:
            解析结果
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db)
        if not config:
            return LeadAIParseResponse(
                lead_info=LeadAIParsedInfo(missing_fields=["all"]),
                extra_info=None,
                thinking_process="AI 配置未设置"
            )

        api_key = ai_config_crud.get_decrypted_api_key(db)
        if not api_key:
            return LeadAIParseResponse(
                lead_info=LeadAIParsedInfo(missing_fields=["all"]),
                extra_info=None,
                thinking_process="无法获取 API Key"
            )

        # 构建请求（非流式）
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": PARSE_LEAD_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
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

                lead_info = LeadAIParsedInfo(
                    lead_name=parsed.get("lead_info", {}).get("lead_name"),
                    source=parsed.get("lead_info", {}).get("source"),
                    city=parsed.get("lead_info", {}).get("city"),
                    company_scale=parsed.get("lead_info", {}).get("company_scale"),
                    contact_name=parsed.get("lead_info", {}).get("contact_name"),
                    contact_phone=parsed.get("lead_info", {}).get("contact_phone"),
                    missing_fields=parsed.get("lead_info", {}).get("missing_fields", [])
                )

                # 解析跟进信息
                follow_up_data = parsed.get("follow_up_info")
                follow_up_info = None
                if follow_up_data and isinstance(follow_up_data, dict):
                    follow_up_info = LeadAIFollowUpInfo(
                        content=follow_up_data.get("content"),
                        next_action=follow_up_data.get("next_action"),
                        next_follow_time=follow_up_data.get("next_follow_time")
                    )

                return LeadAIParseResponse(
                    lead_info=lead_info,
                    follow_up_info=follow_up_info,
                    thinking_process=parsed.get("thinking_process")
                )

        except Exception as e:
            return LeadAIParseResponse(
                lead_info=LeadAIParsedInfo(missing_fields=["all"]),
                follow_up_info=None,
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


lead_ai_parser_service = LeadAIParserService()
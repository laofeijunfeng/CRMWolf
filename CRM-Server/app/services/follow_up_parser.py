"""
跟进信息解析服务

可复用的跟进信息解析逻辑，用于：
1. AI 创建线索时的额外信息识别
2. MagicWand 魔法棒操作
3. 日历待办跟进
4. 其他需要解析跟进信息的场景
"""
import json
import re
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, Any, Optional, List
from sqlalchemy.orm import Session
import httpx

from app.crud.ai_config import ai_config_crud
from app.schemas.lead_ai import LeadAIFollowUpInfo


# 系统提示词：用于从文本中提取跟进信息
PARSE_FOLLOW_UP_SYSTEM_PROMPT_TEMPLATE = """你是 CRMWolf 系统的跟进信息解析助手。

【当前日期】
今天是 {current_date}

你的任务是从用户的描述中提取跟进记录相关信息。

## 需要提取的字段

**content**: 跟进内容
- 提取除"下一步计划"之外的描述内容
- 包括：业务需求、沟通内容、客户情况、产品意向等
- 如果描述只有下一步计划，content 可为 null

**method**: 跟进方式（推断）
- 包含"打电话"、"电话沟通"、"通了电话"、"下午和客户沟通" → "电话"
- 包含"微信"、"微信聊" → "微信"
- 包含"拜访"、"上门"、"见面" → "拜访"
- 包含"邮件"、"发邮件" → "邮件"
- 默认 → "电话"

**next_action**: 下一步动作/计划
- 识别"下一步"、"接下来"、"计划"、"准备"、"等"后面的内容
- 例如："下一步推进POC部署试用" → "推进POC部署试用"
- 例如："下周要去拜访" → "去拜访"
- 例如："等下周三看看，如果采购还没有联系，再和客户对齐" → "如果采购还没有联系，再和客户对齐"
- 如果没有明确表述，返回 null

**next_follow_time**: 下次跟进时间
- 识别时间表达，**输出 YYYY-MM-DD 格式的具体日期**
- 相对时间需要基于当前日期 {current_date} 转换为具体日期：
  - "下周一" → 计算下周一的具体日期
  - "下周三" → 计算下周三的具体日期
  - "三天后"/"3天后" → 当前日期+3天
  - "一周后"/"下周" → 当前日期+7天
- 具体日期保持原样（注意年份必须正确）：
  - "5月25日" → 根据当前年份推断
- 如果无法识别，返回 null

## 输出格式

你必须输出严格的 JSON 格式：
```json
{
  "content": "跟进内容（除下一步计划外的信息）",
  "method": "电话/微信/拜访/邮件",
  "next_action": "下一步动作",
  "next_follow_time": "下次跟进时间表达"
}
```

如果某个字段无法识别，返回 null。

## 示例

输入："下午和客户沟通了下，客户反馈已经经过领导审批，后续会有采购来联系；先提供了报价方案；等下周三看看，如果采购还没有联系，再和客户对齐下采购联系的时间"

输出：
```json
{
  "content": "客户反馈已经经过领导审批，后续会有采购来联系；先提供了报价方案",
  "method": "电话",
  "next_action": "如果采购还没有联系，再和客户对齐下采购联系的时间",
  "next_follow_time": "{next_week_example}"
}
```

输入："想做电商系统，预算50万左右，下一步推进POC部署试用，下周三再联系"

输出：
```json
{
  "content": "想做电商系统，预算50万左右",
  "method": "电话",
  "next_action": "推进POC部署试用",
  "next_follow_time": "{next_week_example}"
}
```

输入："微信上聊了下，客户对产品很感兴趣，下周要去拜访"

输出：
```json
{
  "content": "客户对产品很感兴趣",
  "method": "微信",
  "next_action": "去拜访",
  "next_follow_time": "{next_week_example}"
}
```

输入："需要CRM系统，大概20人团队"

输出：
```json
{
  "content": "需要CRM系统，大概20人团队",
  "method": "电话",
  "next_action": null,
  "next_follow_time": null
}
```"""


class FollowUpParserService:
    """跟进信息解析服务"""

    # 从名称中提取 ID 的正则表达式
    ID_PATTERN = re.compile(r'[（(]\s*ID[：:]\s*(\d+)\s*[）)]')

    def parse_relative_time(
        self,
        time_text: Optional[str],
        base_date: datetime = None
    ) -> Optional[datetime]:
        """
        解析相对时间表达

        支持：
        - 具体日期：2024-05-25, 5月25日
        - 相对天数：后天、三天后、3天后、一周后、下周三
        - 今天/明天

        Args:
            time_text: 时间文本
            base_date: 基准日期（默认今天）

        Returns:
            datetime 对象或 None
        """
        if not time_text:
            return None

        base_date = base_date or datetime.now()
        time_text = time_text.strip().lower()

        # 先尝试标准日期格式
        parsed = self._parse_standard_date(time_text)
        if parsed:
            return parsed

        # 相对时间解析
        # 今天
        if "今天" in time_text or "当日" in time_text:
            return base_date

        # 明天
        if "明天" in time_text or "次日" in time_text:
            return base_date + timedelta(days=1)

        # 后天
        if "后天" in time_text:
            return base_date + timedelta(days=2)

        # X天后、X天、X日后（支持中文数字）
        chinese_num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        days_match = re.search(r'([一二三四五六七八九十\d]+)\s*天[后以]?|([一二三四五六七八九十\d]+)\s*日后', time_text)
        if days_match:
            num_str = days_match.group(1) or days_match.group(2)
            # 处理中文数字
            if num_str in chinese_num_map:
                days = chinese_num_map[num_str]
            else:
                days = int(num_str)
            return base_date + timedelta(days=days)

        # 下周X（如下周三）- 更具体的规则优先检查
        weekday_match = re.search(r'下周([一二三四五六七日天])', time_text)
        if weekday_match:
            weekday_map = {
                '一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '七': 6, '日': 6, '天': 6
            }
            target_weekday = weekday_map.get(weekday_match.group(1))
            if target_weekday:
                current_weekday = base_date.weekday()
                days_to_add = (target_weekday - current_weekday + 7) % 7
                if days_to_add == 0:
                    days_to_add = 7  # 如果是同一天，跳到下周
                return base_date + timedelta(days=days_to_add)

        # 一周后、下周（通用规则）
        if "一周后" in time_text or "下周" in time_text:
            return base_date + timedelta(days=7)

        # 两周后
        if "两周后" in time_text or "半个月后" in time_text:
            return base_date + timedelta(days=14)

        # 本周末
        if "本周末" in time_text:
            current_weekday = base_date.weekday()
            days_to_saturday = (5 - current_weekday) % 7
            return base_date + timedelta(days=days_to_saturday)

        return None

    def _parse_standard_date(self, date_text: str) -> Optional[datetime]:
        """尝试解析标准日期格式"""
        # YYYY-MM-DD
        try:
            return datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            pass

        # MM月DD日 或 M月D日
        month_day_match = re.search(r'(\d{1,2})月(\d{1,2})日', date_text)
        if month_day_match:
            month = int(month_day_match.group(1))
            day = int(month_day_match.group(2))
            year = datetime.now().year
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        return None

    def extract_id_from_name(self, name_text: Optional[str]) -> Optional[int]:
        """
        从名称中提取 ID

        支持格式：
        - 名称（ID：xxx）
        - 名称(ID:xxx)

        Args:
            name_text: 名称文本

        Returns:
            提取的 ID 数字或 None
        """
        if not name_text:
            return None

        match = self.ID_PATTERN.search(name_text)
        if match:
            return int(match.group(1))
        return None

    def _build_system_prompt(self) -> str:
        """
        构建带动态当前日期的系统提示词

        Returns:
            格式化后的系统提示词
        """
        current_date = datetime.now()
        next_week_example = (current_date + timedelta(days=7)).strftime("%Y-%m-%d")

        return PARSE_FOLLOW_UP_SYSTEM_PROMPT_TEMPLATE.format(
            current_date=current_date.strftime("%Y-%m-%d"),
            next_week_example=next_week_example
        )

    async def parse_follow_up_info_stream(
        self,
        db: Session,
        user_message: str,
        team_id: int = 1
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式解析跟进信息，生成 SSE 事件

        Args:
            db: 数据库 session
            user_message: 用户输入的描述文本
            team_id: 团队 ID

        Yields:
            SSE 事件字典
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            yield {"event": "error", "message": "AI 配置未设置"}
            return

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            yield {"event": "error", "message": "无法获取 API Key"}
            return

        # 发送状态事件
        yield {"event": "status", "message": "正在解析跟进信息..."}

        # 构建带动态日期的系统提示词
        system_prompt = self._build_system_prompt()

        # 构建请求
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 512,
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
                        next_follow_time_raw = parsed.get("next_follow_time")

                        # 尝试将相对时间转换为具体日期
                        next_follow_time_dt = None
                        if next_follow_time_raw:
                            next_follow_time_dt = self.parse_relative_time(
                                next_follow_time_raw,
                                base_date=datetime.now()
                            )

                        # 如果能转换成功，使用具体日期；否则保留原始表述
                        next_follow_time_final = next_follow_time_raw
                        if next_follow_time_dt:
                            next_follow_time_final = next_follow_time_dt.strftime("%Y-%m-%d")

                        follow_up_info = LeadAIFollowUpInfo(
                            content=parsed.get("content"),
                            method=parsed.get("method"),
                            next_action=parsed.get("next_action"),
                            next_follow_time=next_follow_time_final
                        )

                        yield {
                            "event": "parsed",
                            "follow_up_info": follow_up_info.model_dump()
                        }
                    except json.JSONDecodeError:
                        yield {"event": "error", "message": f"AI 返回格式异常"}

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}

    async def parse_follow_up_info(
        self,
        db: Session,
        user_message: str,
        team_id: int = 1
    ) -> LeadAIFollowUpInfo:
        """
        解析跟进信息（收集完整响应）

        Args:
            db: 数据库 session
            user_message: 用户输入的描述文本
            team_id: 团队 ID

        Returns:
            解析结果
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            return LeadAIFollowUpInfo()

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return LeadAIFollowUpInfo()

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
            "max_tokens": 512,
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

                return LeadAIFollowUpInfo(
                    content=parsed.get("content"),
                    next_action=parsed.get("next_action"),
                    next_follow_time=parsed.get("next_follow_time")
                )

        except Exception:
            return LeadAIFollowUpInfo()

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
follow_up_parser_service = FollowUpParserService()
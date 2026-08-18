"""
线索解析器

保留原有线索解析逻辑，供 Agent 或其他内部能力复用。
"""
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.services.ai_parser.base_parser import EntityAIParserBase
from app.services.ai_parser.constants import COMPANY_SCALE_ENUM_MAP
from app.services.acquisition_source_service import (
    default_source_name,
    format_active_source_names,
    resolve_source_for_ai,
)
from app.services.lead_ai_confirmed_write_service import lead_ai_confirmed_write_service
from app.utils.time import business_now
from app.crud.lead import lead_crud
from app.schemas.lead import LeadCreate
from app.models.lead import CompanyScale, FollowUpMethod


# 系统提示词：保留既有线索解析规则，供内部解析流程复用
# 注意：next_follow_time 让 AI 返回原始表述，后端统一使用 AgentTemporalResolver 转换
PARSE_LEAD_SYSTEM_PROMPT_TEMPLATE = """你是 CRMWolf 系统的线索信息解析助手。

【当前日期】
今天是 {current_date}

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

只能输出当前团队启用的获客来源名称之一，禁止发明新来源，禁止输出“线索转化”：
{source_enum_block}
用户未明确来源时输出“{default_source_name}”，不要追问来源。

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
- **next_follow_time**: 下次跟进时间（识别时间表达，**输出原始表述**，如"下周三"、"三天后"。注意：不要硬编码年份，年份由后续解析器基于当前日期 {current_date} 自动计算）

如果无法识别对应字段，返回 null。

## 输出格式

你必须输出严格的 JSON 格式：
```json
{{
  "lead_info": {{
    "lead_name": "提取的线索名称",
    "source": "匹配的线索来源枚举值",
    "city": "提取的城市",
    "company_scale": "匹配的公司规模枚举值或 null",
    "contact_name": "提取的联系人姓名",
    "contact_phone": "提取的11位手机号",
    "missing_fields": ["缺失的必填字段列表"]
  }},
  "follow_up_info": {{
    "content": "跟进内容（除下一步计划外的信息）",
    "next_action": "下一步动作",
    "next_follow_time": "下次跟进时间原始表述或null"
  }},
  "thinking_process": "你的解析思考过程（简要描述如何识别各字段）"
}}
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
9. **时间转换**: 输出原始时间表述，由后端代码转换

## 示例

用户输入："张三，13800138000，来自杭州的阿里巴巴，大概500人，网上注册来的，想做电商系统，下一步推进POC部署试用，下周三再联系"

正确输出：
```json
{{
  "lead_info": {{
    "lead_name": "阿里巴巴",
    "source": "线上注册",
    "city": "杭州",
    "company_scale": "501-1000人",
    "contact_name": "张三",
    "contact_phone": "13800138000",
    "missing_fields": []
  }},
  "follow_up_info": {{
    "content": "想做电商系统",
    "next_action": "推进POC部署试用",
    "next_follow_time": "下周三"
  }},
  "thinking_process": "识别联系人张三、电话、城市杭州、公司阿里巴巴、规模500人匹配501-1000人、来源网上注册匹配线上注册。额外信息中'想做电商系统'为跟进内容，'下一步推进POC部署试用'为下一步动作，'下周三'为下次跟进时间"
}}
```

用户输入："有个客户叫李四，电话不记得了，在广州"

正确输出：
```json
{{
  "lead_info": {{
    "lead_name": null,
    "source": null,
    "city": "广州",
    "company_scale": null,
    "contact_name": "李四",
    "contact_phone": null,
    "missing_fields": ["lead_name", "source", "contact_phone"]
  }},
  "follow_up_info": null,
  "thinking_process": "识别到联系人李四，城市广州，但缺少公司名称、来源和电话，无额外信息"
}}
```"""


class LeadAIParser(EntityAIParserBase):
    """线索 AI 解析器"""

    entity_type = "lead"

    def get_system_prompt(self, db: Session | None = None, team_id: int | None = None) -> str:
        """
        构建带动态当前日期和团队获客来源的系统提示词
        """
        current_date = business_now().strftime("%Y-%m-%d")
        names = format_active_source_names(db, team_id)
        source_enum_block = "\n".join(f'- "{name}"' for name in names)
        return (
            PARSE_LEAD_SYSTEM_PROMPT_TEMPLATE
            .replace("{current_date}", current_date)
            .replace("{source_enum_block}", source_enum_block)
            .replace("{default_source_name}", default_source_name(db, team_id))
        )

    def get_enum_maps(self) -> Dict[str, Dict[str, Any]]:
        return {
            "scale": COMPANY_SCALE_ENUM_MAP
        }

    def parse_ai_response(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 AI 响应，转换为结构化数据

        Args:
            parsed: AI 返回的 JSON

        Returns:
            {
                "lead_info": {...},
                "follow_up_info": {...} or null,
                "thinking_process": str
            }
        """
        lead_info = parsed.get("lead_info", {})
        follow_up_data = parsed.get("follow_up_info")

        # 构建返回结构
        result = {
            "lead_info": {
                "lead_name": lead_info.get("lead_name"),
                "source": lead_info.get("source"),
                "city": lead_info.get("city"),
                "company_scale": lead_info.get("company_scale"),
                "contact_name": lead_info.get("contact_name"),
                "contact_phone": lead_info.get("contact_phone"),
                "missing_fields": lead_info.get("missing_fields", [])
            },
            "follow_up_info": None,
            "thinking_process": parsed.get("thinking_process")
        }

        # 解析跟进信息
        if follow_up_data and isinstance(follow_up_data, dict):
            result["follow_up_info"] = {
                "content": follow_up_data.get("content"),
                "next_action": follow_up_data.get("next_action"),
                "next_follow_time": follow_up_data.get("next_follow_time")
            }

        return result

    async def create_entity(
        self,
        db: Session,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> Any:
        """
        创建线索

        Args:
            db: 数据库 Session
            parsed_data: 解析后的数据（来自前端预览确认）
            user_id: 用户 ID
            team_id: 团队 ID

        Returns:
            创建的 Lead 对象
        """
        source_row = resolve_source_for_ai(db, team_id, parsed_data.get("source"))

        company_scale_str = parsed_data.get("company_scale")
        company_scale_enum = None
        if company_scale_str:
            company_scale_enum = COMPANY_SCALE_ENUM_MAP.get(company_scale_str)

        lead_create = LeadCreate(
            lead_name=parsed_data["lead_name"],
            source_public_id=source_row.public_id,
            city=parsed_data["city"],
            contact_name=parsed_data["contact_name"],
            contact_phone=parsed_data["contact_phone"],
            company_scale=CompanyScale(company_scale_enum) if company_scale_enum else None
        )

        lead = lead_crud.create(db, lead_create, user_id, team_id)

        return lead

    async def post_create_actions(
        self,
        db: Session,
        entity: Any,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> None:
        """
        创建线索后的额外操作：创建跟进记录

        Args:
            entity: 创建的 Lead 对象
            parsed_data: 解析后的数据（包含跟进信息）
        """
        # 如果有跟进信息，创建跟进记录
        follow_up_content = parsed_data.get("follow_up_content")
        next_action = parsed_data.get("next_action")
        next_follow_time_str = parsed_data.get("next_follow_time")

        if follow_up_content or next_action:
            content = follow_up_content or "【线索解析时提取的信息】"
            await lead_ai_confirmed_write_service.create_lead_follow_up(
                db=db,
                lead_id=entity.id,
                lead_public_id=entity.public_id,
                team_id=team_id,
                user_id=user_id,
                content=content,
                method=FollowUpMethod.OTHER,
                next_action=next_action,
                next_follow_time_text=next_follow_time_str,
                action_namespace="lead_create_follow_up",
            )

"""
线索 AI 解析器

从 lead_ai_parser.py 迁移，保持原有解析逻辑
"""
from typing import Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.ai_parser.base_parser import EntityAIParserBase
from app.services.ai_parser.constants import LEAD_SOURCE_ENUM_MAP, COMPANY_SCALE_ENUM_MAP
from app.services.follow_up_parser import follow_up_parser_service
from app.crud.lead import lead_crud, lead_follow_up_crud
from app.schemas.lead import LeadCreate, LeadFollowUpCreate
from app.models.lead import LeadSource, CompanyScale, FollowUpMethod


# 系统提示词（从 lead_ai_parser.py 复制，保持向后兼容）
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


class LeadAIParser(EntityAIParserBase):
    """线索 AI 解析器"""

    entity_type = "lead"

    def get_system_prompt(self) -> str:
        return PARSE_LEAD_SYSTEM_PROMPT

    def get_enum_maps(self) -> Dict[str, Dict[str, Any]]:
        return {
            "source": LEAD_SOURCE_ENUM_MAP,
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
        # 枚举值转换
        source_str = parsed_data.get("source")
        source_enum = LEAD_SOURCE_ENUM_MAP.get(source_str)
        if not source_enum:
            raise ValueError(f"无效的线索来源：{source_str}")

        company_scale_str = parsed_data.get("company_scale")
        company_scale_enum = None
        if company_scale_str:
            company_scale_enum = COMPANY_SCALE_ENUM_MAP.get(company_scale_str)

        # 创建线索
        lead_create = LeadCreate(
            lead_name=parsed_data["lead_name"],
            source=LeadSource(source_enum),
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
            # 解析下次跟进时间
            next_follow_time_dt = None
            if next_follow_time_str:
                next_follow_time_dt = follow_up_parser_service.parse_relative_time(
                    next_follow_time_str,
                    base_date=datetime.now()
                )

            # 构建跟进内容
            content = follow_up_content or "【AI 创建线索时提取的信息】"

            follow_up_create = LeadFollowUpCreate(
                content=content,
                method=FollowUpMethod.OTHER,
                next_action=next_action,
                next_follow_time=next_follow_time_dt
            )

            lead_follow_up_crud.create(
                db=db,
                obj_in=follow_up_create,
                lead_id=entity.id,
                creator_id=user_id,
                team_id=team_id
            )
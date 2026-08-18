"""
客户 AI 解析器

实现客户创建的 AI 解析功能，含行业识别和档案生成
"""
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.crud.customer import contact_crud, customer_crud
from app.crud.industry import industry_crud
from app.schemas.customer import ContactCreate, CustomerCreate
from app.services.acquisition_source_service import (
    default_source_name,
    format_active_source_names,
    resolve_source_for_ai,
)
from app.services.ai_parser.base_parser import EntityAIParserBase
from app.services.ai_parser.constants import COMPANY_SCALE_ENUM_MAP
from app.services.customer_ai_confirmed_write_service import customer_ai_confirmed_write_service
from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service
from app.utils.time import business_now


# 系统提示词（针对客户创建定制）
PARSE_CUSTOMER_SYSTEM_PROMPT_TEMPLATE = """你是 CRMWolf 系统的客户信息解析助手。

【当前日期】
今天是 {current_date}

你的任务是从用户的自然语言描述中提取客户信息，并分离出额外信息用于跟进记录。

## 需要提取的字段

**必填字段**：
- account_name: 客户公司名称（必填）
- city: 所在城市（必填）
- contact_name: 主联系人姓名（必填）
- contact_phone: 主联系人电话（11位手机号，必填）
- contact_position: 主联系人职务（必填）
- contact_gender: 主联系人性别（必填，男返回 "1"，女返回 "2"）

**可选字段**：
- contact_email: 主联系人邮箱
- company_scale: 公司规模
- source: 客户来源

## 客户来源枚举值

只能输出当前团队启用的获客来源名称之一，禁止发明新来源，禁止输出“线索转化”：
{source_enum_block}
用户未明确来源时输出“{default_source_name}”，不要追问来源。

## 缺失字段

以下字段缺失时必须放入 missing_fields：
- account_name
- city
- contact_name
- contact_phone
- contact_position
- contact_gender

## 公司规模枚举值

用户可能说"大概500人"、"几百人"、"几十人"等，你需要智能匹配：
- "1-50人": 人数在50人以下
- "51-200人": 人数在51-200人之间
- "201-500人": 人数在201-500人之间
- "501-1000人": 人数在501-1000人之间
- "1000人以上": 人数超过1000人

如果用户未提及公司规模，返回 null。

## 行业识别

用户描述中如果包含行业关键词（如"互联网公司"、"金融"、"制造业"等），提取为 industry_hint 字段。
如果无法识别，返回 null。

## 额外信息识别

用户描述中不属于上述字段的额外信息需要提取出来，分为三部分：
- **content**: 跟进内容（业务需求、意向产品、备注等，排除"下一步计划"）
- **next_action**: 下一步动作/计划（识别"下一步"、"接下来"、"计划"等表述）
- **next_follow_time**: 下次跟进时间（识别时间表达，**输出原始表述**，如"下周三"、"三天后"。注意：不要硬编码年份，年份由后续解析器基于当前日期 {current_date} 自动计算）

## 输出格式

你必须输出严格的 JSON 格式：
```json
{
  "customer_info": {
    "account_name": "提取的客户公司名称",
    "city": "提取的城市",
    "company_scale": "匹配的公司规模枚举值或 null",
    "source": "匹配的客户来源枚举值或 null",
    "industry_hint": "行业关键词或 null",
    "missing_fields": ["缺失的必填字段列表"]
  },
  "contact_info": {
    "contact_name": "提取的联系人姓名",
    "contact_phone": "提取的11位手机号",
    "contact_position": "职务或 null",
    "contact_gender": "1或2，无法识别则返回null",
    "contact_email": "邮箱或 null"
  },
  "follow_up_info": {
    "content": "跟进内容（除下一步计划外的信息）",
    "next_action": "下一步动作",
    "next_follow_time": "下次跟进时间原始表述或null"
  },
  "thinking_process": "你的解析思考过程"
}
```

## 示例

用户输入："阿里巴巴，杭州，张三 13800138000 技术总监 zhangsan@alibaba.com，大概500人，网上注册来的，互联网公司，想做电商系统，下周三再联系"

正确输出：
```json
{
  "customer_info": {
    "account_name": "阿里巴巴",
    "city": "杭州",
    "company_scale": "501-1000人",
    "source": "线上注册",
    "industry_hint": "互联网",
    "missing_fields": []
  },
  "contact_info": {
    "contact_name": "张三",
    "contact_phone": "13800138000",
    "contact_position": "技术总监",
    "contact_gender": "1",
    "contact_email": "zhangsan@alibaba.com"
  },
  "follow_up_info": {
    "content": "想做电商系统",
    "next_action": null,
    "next_follow_time": "下周三"
  },
  "thinking_process": "识别客户阿里巴巴、城市杭州、规模500人匹配501-1000人、来源网上注册匹配线上注册、行业互联网。联系人张三、电话、职务技术总监、邮箱。额外信息中'想做电商系统'为跟进内容，'下周三'为下次跟进时间"
}
```"""


class CustomerAIParser(EntityAIParserBase):
    """客户 AI 解析器"""

    entity_type = "customer"

    def get_system_prompt(self, db: Session | None = None, team_id: int | None = None) -> str:
        current_date = business_now().strftime("%Y-%m-%d")
        names = format_active_source_names(db, team_id)
        source_enum_block = "\n".join(f'- "{name}"' for name in names)
        return (
            PARSE_CUSTOMER_SYSTEM_PROMPT_TEMPLATE
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
        解析 AI 响应

        Returns:
            {
                "customer_info": {...},
                "contact_info": {...},
                "follow_up_info": {...} or null,
                "thinking_process": str
            }
        """
        customer_info = parsed.get("customer_info", {})
        contact_info = parsed.get("contact_info", {})
        follow_up_data = parsed.get("follow_up_info")

        result = {
            "customer_info": {
                "account_name": customer_info.get("account_name"),
                "city": customer_info.get("city"),
                "company_scale": customer_info.get("company_scale"),
                "source": customer_info.get("source"),
                "industry_hint": customer_info.get("industry_hint"),
                "missing_fields": customer_info.get("missing_fields", [])
            },
            "contact_info": {
                "contact_name": contact_info.get("contact_name"),
                "contact_phone": contact_info.get("contact_phone"),
                "contact_position": contact_info.get("contact_position"),
                "contact_gender": contact_info.get("contact_gender"),
                "contact_email": contact_info.get("contact_email")
            },
            "follow_up_info": None,
            "thinking_process": parsed.get("thinking_process")
        }

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
        创建客户 + 主联系人

        Args:
            parsed_data: 前端预览确认后的数据（包含 customer_info + contact_info）
        """
        customer_info = parsed_data.get("customer_info", {})
        contact_info = parsed_data.get("contact_info", {})

        # 枚举值转换
        company_scale_str = customer_info.get("company_scale")
        company_scale_value = None
        if company_scale_str:
            # Customer 使用字符串存储，直接使用显示值
            company_scale_value = company_scale_str

        # 行业识别（如果 AI 提供了 industry_hint，则匹配数据库行业）
        industry_code = None
        industry_hint = customer_info.get("industry_hint")
        if industry_hint:
            industry_code = self._match_industry(db, industry_hint)

        source_row = resolve_source_for_ai(db, team_id, customer_info.get("source"))
        customer_create = CustomerCreate(
            account_name=customer_info["account_name"],
            city=customer_info["city"],
            company_scale=company_scale_value,
            source_public_id=source_row.public_id,
            industry=industry_code  # AI 识别的行业编码
        )

        customer = customer_crud.create(
            db=db,
            obj_in=customer_create,
            creator_id=user_id,
            team_id=team_id
        )

        # 创建主联系人
        contact_create = ContactCreate(
            name=contact_info["contact_name"],
            mobile=contact_info["contact_phone"],
            position=contact_info.get("contact_position"),
            gender=contact_info.get("contact_gender"),
            email=contact_info.get("contact_email"),
            is_primary=True
        )

        contact = contact_crud.create(
            db=db,
            obj_in=contact_create,
            customer_id=customer.id,
            team_id=team_id,
            is_primary=True
        )

        return customer

    def _match_industry(self, db: Session, industry_hint: str) -> str:
        """
        匹配行业编码（从数据库一二级行业中选择）

        Args:
            industry_hint: AI 提取的行业关键词

        Returns:
            行业编码（如 "internet", "finance"）或 None
        """
        # 获取行业层级结构
        hierarchy = industry_crud.get_industry_hierarchy(db)

        # 从二级行业开始匹配
        for primary_code, primary_info in hierarchy.items():
            for child in primary_info['children']:
                # 检查行业名称是否包含关键词
                if industry_hint.lower() in child['name'].lower():
                    return child['code']

        # 如果二级行业未匹配，尝试一级行业
        for primary_code, primary_info in hierarchy.items():
            if industry_hint.lower() in primary_info['name'].lower():
                return primary_code

        return None

    async def post_create_actions(
        self,
        db: Session,
        entity: Any,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> None:
        """
        创建客户后的额外操作：
        1. 触发档案生成（异步）
        2. 创建客户活动（如果有）
        """
        customer = entity

        # 1. 触发客户智能档案生成（异步，进入 LangGraph 统一编排）
        await customer_intelligence_refresh_service.trigger_customer_created_refresh(
            db,
            team_id=team_id,
            customer_id=customer.id,
            actor_id=user_id,
        )

        # 2. 创建客户活动（如果有）
        follow_up_info = parsed_data.get("follow_up_info")
        if follow_up_info and (follow_up_info.get("content") or follow_up_info.get("next_action")):
            from app.services.customer_activity_kinds import CustomerActivityKind

            source_content_parts = []
            if follow_up_info.get("content"):
                source_content_parts.append(str(follow_up_info["content"]))
            if follow_up_info.get("next_action"):
                source_content_parts.append(f"下一步：{follow_up_info['next_action']}")

            await customer_ai_confirmed_write_service.create_customer_activity(
                db=db,
                customer_id=customer.id,
                customer_public_id=customer.public_id,
                team_id=team_id,
                user_id=user_id,
                content="\n".join(source_content_parts) or "AI 创建客户时提取的信息",
                activity_kind=CustomerActivityKind.OTHER_FOLLOW_UP,
                next_action=follow_up_info.get("next_action"),
                next_follow_time_text=follow_up_info.get("next_follow_time"),
                action_namespace="customer_create_follow_up",
            )

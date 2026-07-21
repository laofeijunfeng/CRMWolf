"""
客户 AI 解析器

实现客户创建的 AI 解析功能，含行业识别和档案生成
"""
from typing import Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.ai_parser.base_parser import EntityAIParserBase
from app.services.ai_parser.constants import CUSTOMER_SOURCE_ENUM_MAP, COMPANY_SCALE_ENUM_MAP
from app.services.follow_up_parser import follow_up_parser_service
from app.crud.customer import customer_crud, contact_crud
from app.crud.industry import industry_crud
from app.schemas.customer import CustomerCreate, ContactCreate
from app.models.customer import CustomerSource
from app.services.customer_profile_service import customer_profile_service


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

用户可能用各种描述，你需要智能匹配到以下枚举值之一：
- "线上注册": 包括网站注册、官网注册、网上注册等
- "市场活动": 包括展会、活动、营销活动等
- "客户推荐": 包括转介绍、朋友推荐、老客户介绍等
- "电话营销": 包括电话推销、电话联系、电话沟通等
- "网站咨询": 包括网上咨询、官网咨询、在线咨询等
- "展会": 包括参展、展览、博览会等
- "其他": 无法匹配到上述分类时使用

如果用户未提及客户来源，返回 null。

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

    def get_system_prompt(self) -> str:
        """
        构建带动态当前日期的系统提示词

        Returns:
            格式化后的系统提示词
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        return PARSE_CUSTOMER_SYSTEM_PROMPT_TEMPLATE.replace("{current_date}", current_date)

    def get_enum_maps(self) -> Dict[str, Dict[str, Any]]:
        return {
            "source": CUSTOMER_SOURCE_ENUM_MAP,
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
        source_str = customer_info.get("source")
        source_enum = None
        if source_str:
            source_enum = CUSTOMER_SOURCE_ENUM_MAP.get(source_str)

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

        # 创建客户
        customer_create = CustomerCreate(
            account_name=customer_info["account_name"],
            city=customer_info["city"],
            company_scale=company_scale_value,
            source=CustomerSource(source_enum) if source_enum else None,
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
        2. 创建跟进记录（如果有）
        """
        customer = entity

        # 1. 触发档案生成（异步）
        await customer_profile_service.trigger_generation(
            customer_id=customer.id,
            account_name=customer.account_name,
            team_id=team_id
        )

        # 2. 创建跟进记录（如果有）
        follow_up_info = parsed_data.get("follow_up_info")
        if follow_up_info and (follow_up_info.get("content") or follow_up_info.get("next_action")):
            from app.crud.customer_follow_up import customer_follow_up_crud
            from app.schemas.customer_follow_up import CustomerFollowUpCreate

            # 解析下次跟进时间
            next_follow_time_dt = None
            next_follow_time_str = follow_up_info.get("next_follow_time")
            if next_follow_time_str:
                next_follow_time_dt = follow_up_parser_service.parse_relative_time(
                    next_follow_time_str,
                    base_date=datetime.now()
                )

            follow_up_create = CustomerFollowUpCreate(
                content=follow_up_info.get("content") or "【AI 创建客户时提取的信息】",
                method="其他",
                next_action=follow_up_info.get("next_action"),
                next_follow_time=next_follow_time_dt
            )

            customer_follow_up_crud.create(
                db=db,
                obj_in=follow_up_create,
                customer_id=customer.id,
                creator_id=user_id,
                team_id=team_id
            )

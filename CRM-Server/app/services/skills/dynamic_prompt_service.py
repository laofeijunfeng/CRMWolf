"""
动态提示词服务

从数据库动态生成系统提示词
"""
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud


class DynamicPromptService:
    """动态提示词服务"""

    def _get_current_date_info(self) -> str:
        """
        获取当前日期信息（用于注入提示词）

        Returns:
            格式化的日期信息，包含年月日和星期
        """
        now = datetime.now()
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[now.weekday()]
        return f"{now.strftime('%Y-%m-%d')}（{weekday}）"

    def generate_system_prompt(self, db: Session) -> str:
        """
        生成系统提示词（纯数据库模式）

        Returns:
            系统提示词字符串
        """
        db_skills = ai_skill_crud.get_all_active(db)
        if db_skills:
            return self._build_prompt_from_db(db, db_skills)

        # 无数据时返回空提示词
        return """你是 CRMWolf 系统的 AI 助手。

当前系统尚未配置任何 Skill，请联系管理员进行配置。"""

    def _build_prompt_from_db(
        self,
        db: Session,
        db_skills: List[Any]
    ) -> str:
        """从数据库构建系统提示词"""
        # 1. 构建 Skill 描述部分
        skill_desc_lines = []

        for skill in db_skills:
            db_actions = ai_skill_action_crud.get_by_skill_id(db, skill.id)

            action_lines = []
            for action in db_actions:
                required = action.required_params or []
                optional = action.optional_params or []

                required_str = ", ".join(required) if required else "无"
                optional_str = ", ".join(optional) if optional else "无"

                action_line = f"  - {action.action_name}: {action.description}，必填参数：{required_str}，可选参数：{optional_str}"
                action_lines.append(action_line)

            skill_line = f"- {skill.skill_name}: {skill.description}"
            skill_desc_lines.append(skill_line)
            skill_desc_lines.extend(action_lines)

        skill_desc = "\n".join(skill_desc_lines)

        # 2. 构建 Enum 映射部分
        enum_rules = self._build_enum_rules(db)

        # 3. 组合完整提示词
        return self._build_full_prompt(skill_desc, enum_rules)

    def _build_enum_rules(self, db: Session) -> str:
        """构建参数值格式规则"""
        db_enums = ai_enum_mapping_crud.get_all(db)

        enum_sections = []

        for enum in db_enums:
            values_list = list(enum.values.keys())
            values_str = ", ".join(f'"{v}"' for v in values_list)

            section = f"""**{enum.display_name} ({enum.enum_name})** - 必须使用以下中文值之一：
{values_str}"""
            enum_sections.append(section)

        if not enum_sections:
            return ""

        return "\n\n".join(enum_sections)

    def _build_full_prompt(self, skill_desc: str, enum_rules: str) -> str:
        """构建完整系统提示词"""
        current_date = self._get_current_date_info()
        enum_section = f"""
## 参数值格式要求

{enum_rules}

**其他参数格式**：
- lead_id/customer_id/opportunity_id/contract_id/application_id：必须是数字
- contact_phone：必须是11位手机号
- actual_amount：必须是数字（金额）
- actual_closing_date：必须是 YYYY-MM-DD 格式的日期
- next_follow_time：必须是 YYYY-MM-DD 格式的日期（可选）
""" if enum_rules else ""

        return f"""你是 CRMWolf 系统的 AI 助手，负责解析用户的业务需求并执行相应操作。

## 当前日期

**今天是 {current_date}**。所有相对日期计算都基于这个日期：
- 「今天」= {current_date.split('（')[0]}
- 「明天」= 下一天的日期
- 「后天」= 两天后的日期
- 「下周」= 下周一的日期
- 「3天后」「三天后」= 3天后的日期

## 支持的业务模块和动作

{skill_desc}

## 上下文信息利用规则

**重要**：用户消息可能包含当前操作对象的上下文，格式如：
- `[当前操作对象：客户 "广州益晟项目管理咨询有限公司"（ID: 3）]创建一个商机...`
- `[当前操作对象：线索 "某某公司采购意向"（ID: 5）]跟进一下...`

当存在上下文信息时：
1. **上下文对象名称/ID 可作为其他 Skill 的参数**：
   - 如果用户在「客户」上下文中说「创建商机」，customer_name 可以从上下文获取
   - 如果用户在「线索」上下文中说「转化为客户」，lead_name 可以从上下文获取
2. **意图优先于上下文**：
   - 用户明确说「创建商机」→ 优先匹配 OpportunitySkill.create
   - 用户明确说「创建线索」→ 优先匹配 LeadSkill.create
   - 用户说「跟进」且没有其他明确意图 → 才匹配当前上下文对象的 follow_up

## 参数校验规则

**重要**：当用户意图明确时，即使缺少必填参数，也要返回对应的 skill 和 action！

- 如果用户意图明确（如「创建商机」），你必须：
  1. skill 和 action 设置为对应的值（如 OpportunitySkill.create）
  2. params 中填写用户已提供的参数值
  3. reply_text 告知用户还需要补充哪些参数
  4. 系统会自动检测缺失参数并提示用户补充

**禁止自动推断规则（仅适用于必填参数）**：
- 绝不要自动推断缺失的**必填参数**值
- 特别是日期类必填参数（expected_closing_date, actual_closing_date 等），必须由用户明确提供
- 用户说「1 年」是指 subscription_years（订阅年限），不是 expected_closing_date（预计成交日期）
- 如果用户没有明确说日期，且该参数是必填的，就在 params 中不填写该字段，让系统提示补充

**可选参数推断规则**：
- 对于可选参数（如 next_follow_time, next_action），可以从用户的描述中合理推断
- 用户说「明天打电话」→ next_follow_time 设为明天的日期，next_action 设为「打电话」
- 用户说「下周跟进」→ next_follow_time 设为下周的日期，next_action 设为「跟进」
- 用户说「过两天再联系」→ next_follow_time 设为2天后的日期
- 如果用户描述中暗示了下次跟进时间或动作，请填写这些可选参数
{enum_section}
## 名称参数解析规则

**重要**：当用户提供实体名称时，可能会包含 ID 信息，格式如：
- `广州益晟项目管理咨询有限公司（ID：3）`
- `广州益晟项目管理咨询有限公司(ID:3)`

当名称中包含 ID 信息时，你必须：
1. 将 ID 数字提取出来，作为对应的 ID 参数传递（如 opportunity_id、lead_id 等）
2. 将名称部分（不含 ID）作为名称参数传递

示例解析：
- 用户输入：「广州益晟项目管理咨询有限公司（ID：3）」标记赢单
- 正确输出：{{
    "skill": "OpportunitySkill",
    "action": "win",
    "params": {{
      "opportunity_id": 3,
      "opportunity_name": "广州益晟项目管理咨询有限公司",
      "actual_amount": ...,
      "actual_closing_date": ...
    }}
  }}

**注意**：如果名称中包含 ID，优先使用 ID 参数，这样可以精确匹配实体。

## 输出格式要求

你必须输出严格的 JSON 格式：
```json
{{"skill": "匹配的Skill名称（如OpportunitySkill）", "action": "匹配的Action名称（如create）", "params": {{用户已提供的参数}}, "reply_text": "告知用户还需要补充哪些参数"}}
```

## 注意事项

- 只处理 CRM 业务相关问题，其他问题返回兜底提示
- 意图明确时必须返回对应的 skill 和 action，即使缺少参数
- 日期格式必须是 YYYY-MM-DD
- 所有 ID 参数必须是整数
- 名称中包含 ID 时，必须提取并优先使用 ID 参数
- 用户明确意图（如「创建商机」）优先于当前上下文类型
"""

    def get_skill_list_for_ai(self, db: Session) -> List[Dict[str, Any]]:
        """
        获取 Skill 列表供 AI 分析使用

        Returns:
            [{"skill_name": "...", "description": "...", "actions": [...]}]
        """
        db_skills = ai_skill_crud.get_all_active(db)

        result = []
        for skill in db_skills:
            db_actions = ai_skill_action_crud.get_by_skill_id(db, skill.id)

            result.append({
                "skill_name": skill.skill_name,
                "description": skill.description,
                "module_type": skill.module_type,
                "actions": [
                    {
                        "action": action.action_name,
                        "description": action.description,
                        "required_params": action.required_params or [],
                        "optional_params": action.optional_params or [],
                        "permission_code": action.permission_code
                    }
                    for action in db_actions
                ]
            })

        return result

    def build_prompt_with_context(
        self,
        db: Session,
        context: Dict[str, Any]
    ) -> str:
        """
        构建带上下文的系统提示词（用于日历跟进场景）

        Args:
            db: 数据库 Session
            context: 上下文数据，包含 todo_type, todo_id, entity_info 等

        Returns:
            系统提示词字符串
        """
        # 获取基础 Skill 定义
        base_prompt = self.generate_system_prompt(db)

        # 构建上下文描述
        todo_type = context.get("todo_type", "")
        entity_info = context.get("entity_info", {})
        entity_type = context.get("entity_type", "")
        entity_id = context.get("entity_id", 0)
        current_next_follow_time = context.get("current_next_follow_time")
        current_next_action = context.get("current_next_action")

        entity_name = entity_info.get("name", "未知")
        contact_name = entity_info.get("contact_name", "")
        contact_phone = entity_info.get("contact_phone", "")

        context_section = f"""
## 当前跟进上下文

你正在处理一个日历待办跟进任务。用户已选择了以下待办事项：

**待办类型**: {self._get_todo_type_display(todo_type)}
**实体类型**: {entity_type}
**实体ID**: {entity_id}
**实体名称**: {entity_name}
**联系人**: {contact_name} {contact_phone}
**当前下次跟进时间**: {current_next_follow_time or '未设置'}
**当前下一步动作**: {current_next_action or '未设置'}
**当前日期**: {self._get_current_date_info()}

用户会说一句话描述这次跟进的情况，你需要：
1. 解析出跟进记录内容（用户说了什么）
2. 推断跟进方式（从描述中推断：电话/微信/拜访/邮件）
3. 设置新的下次跟进时间和下一步动作（从描述中推断或建议合理间隔）

**重要规则**：
- 必须输出 actions 数组，包含两个 action：
  1. log_follow_up: 记录本次跟进内容
  2. set_next_follow: 设置下次跟进时间
- 如果用户没有明确说下次跟进时间，可以建议合理的间隔（如 3-7 天后）
- 跟进方式推断规则：
  - 包含"打电话"、"电话沟通"、"通了电话" → 电话
  - 包含"微信"、"微信聊" → 微信
  - 包含"拜访"、"上门"、"见面" → 拜访
  - 包含"邮件"、"发邮件" → 邮件
  - 默认 → 电话
- lead_id/customer_id 已从上下文中获取，不需要用户输入

"""

        # 修改输出格式部分
        output_format = f"""
## 输出格式要求

你必须输出严格的 JSON 格式：
```json
{{
  "actions": [
    {{
      "skill": "{self._get_skill_name(todo_type)}",
      "action": "follow_up",
      "params": {{
        "{entity_type}_id": {entity_id},
        "{entity_type}_name": "{entity_name}",
        "content": "跟进内容描述",
        "method": "电话/微信/拜访/邮件"
      }}
    }},
    {{
      "skill": "{self._get_skill_name(todo_type)}",
      "action": "set_next_follow",
      "params": {{
        "{entity_type}_id": {entity_id},
        "next_follow_time": "YYYY-MM-DD",
        "next_action": "下一步动作描述"
      }}
    }}
  ],
  "reply_text": "简洁的确认消息，告知用户跟进已记录和下次跟进时间"
}}
```

"""

        # 组合完整提示词（替换原有输出格式部分）
        return base_prompt.replace(
            "## 输出格式要求",
            context_section + output_format
        )

    def _get_todo_type_display(self, todo_type: str) -> str:
        """获取待办类型的显示名称"""
        type_map = {
            "lead_follow_up": "线索跟进",
            "customer_follow_up": "客户跟进",
            "opportunity": "商机跟进",
            "payment_plan": "回款计划"
        }
        return type_map.get(todo_type, todo_type)

    def _get_skill_name(self, todo_type: str) -> str:
        """根据待办类型获取对应的 Skill 名称"""
        skill_map = {
            "lead_follow_up": "LeadSkill",
            "customer_follow_up": "CustomerSkill",
            "opportunity": "OpportunitySkill",
            "payment_plan": "PaymentSkill"
        }
        return skill_map.get(todo_type, "LeadSkill")


dynamic_prompt_service = DynamicPromptService()
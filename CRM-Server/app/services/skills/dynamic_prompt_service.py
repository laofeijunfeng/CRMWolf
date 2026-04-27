"""
动态提示词服务

从数据库动态生成系统提示词
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud


class DynamicPromptService:
    """动态提示词服务"""

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

## 支持的业务模块和动作

{skill_desc}

## 参数校验规则

**重要**：在匹配任何动作之前，必须先校验必填参数是否完整！

- 如果用户消息中缺少必填参数，你必须：
  1. skill 和 action 设置为 null
  2. reply_text 塋写追问内容，明确告知用户需要补充哪些参数
  3. 不要匹配任何 Skill/Action
{enum_section}
## 输出格式要求

你必须输出严格的 JSON 格式：
```json
{{"skill": "匹配的Skill名称，参数缺失时填null", "action": "匹配的Action名称，参数缺失时填null", "params": {{}}, "reply_text": "参数缺失时填追问内容，参数完整时填'正在为你执行操作，请稍候...'"}}
```

## 注意事项

- 只处理 CRM 业务相关问题，其他问题返回兜底提示
- 参数缺失时绝对不要匹配任何 Skill/Action
- 日期格式必须是 YYYY-MM-DD
- 所有 ID 参数必须是整数
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


dynamic_prompt_service = DynamicPromptService()
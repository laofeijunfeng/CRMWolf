"""
动态 Skill 服务

从数据库读取 Skill/Action 定义，通过 HandlerFactory 执行
"""
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session

from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_crud_mapping import ai_crud_mapping_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud
from app.schemas.ai_skill import SkillExecutionResult
from app.services.skills.handlers.handler_factory import HandlerFactory


class DynamicSkillService:
    """动态 Skill 服务"""

    # 缓存（可选优化，后续可引入 Redis）
    _skill_cache: Optional[List[Any]] = None
    _action_cache: Optional[Dict[int, List[Any]]] = None

    def get_all_skill_definitions(self, db: Session) -> List[Any]:
        """
        获取所有 Skill 定义（纯数据库模式）

        Returns:
            SkillDefinition 列表
        """
        db_skills = ai_skill_crud.get_all_active(db)
        if db_skills:
            return self._build_skill_definitions_from_db(db, db_skills)
        return []

    def _build_skill_definitions_from_db(
        self,
        db: Session,
        db_skills: List[Any]
    ) -> List[Any]:
        """从数据库构建 SkillDefinition 格式"""
        from app.schemas.ai_skill import SkillDefinition, SkillActionDefinition

        definitions = []

        for skill in db_skills:
            # 获取该 Skill 的所有 Action
            db_actions = ai_skill_action_crud.get_by_skill_id(db, skill.id)

            actions = []
            for action in db_actions:
                action_def = SkillActionDefinition(
                    action=action.action_name,
                    description=action.description,
                    required_params=action.required_params or [],
                    optional_params=action.optional_params or [],
                    permission_code=action.permission_code
                )
                actions.append(action_def)

            skill_def = SkillDefinition(
                skill_name=skill.skill_name,
                description=skill.description,
                actions=actions
            )
            definitions.append(skill_def)

        return definitions

    def get_skill_definition(self, db: Session, skill_name: str) -> Optional[Any]:
        """获取单个 Skill 定义"""
        definitions = self.get_all_skill_definitions(db)
        for skill_def in definitions:
            if skill_def.skill_name == skill_name:
                return skill_def
        return None

    def get_action_definition(
        self,
        db: Session,
        skill_name: str,
        action_name: str
    ) -> Optional[Any]:
        """获取 Action 定义"""
        skill_def = self.get_skill_definition(db, skill_name)
        if not skill_def:
            return None

        for action_def in skill_def.actions:
            if action_def.action == action_name:
                return action_def
        return None

    async def execute_action(
        self,
        db: Session,
        skill_name: str,
        action_name: str,
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None
    ) -> SkillExecutionResult:
        """
        执行 Action（纯数据库模式）

        Args:
            db: 数据库 Session
            skill_name: Skill 名称
            action_name: Action 名称
            params: 参数
            user_id: 用户 ID
            user_feishu_open_id: 用户飞书 Open ID

        Returns:
            SkillExecutionResult
        """
        db_skill = ai_skill_crud.get_by_name(db, skill_name)

        if not db_skill:
            return SkillExecutionResult(
                success=False,
                message=f"系统暂不支持该功能模块：{skill_name}"
            )

        db_action = ai_skill_action_crud.get_by_skill_and_action(
            db, db_skill.id, action_name
        )

        if not db_action:
            return SkillExecutionResult(
                success=False,
                message=f"系统暂不支持该操作：{skill_name}.{action_name}"
            )

        return await self._execute_via_handler(
            db,
            db_action.handler_type,
            db_action.handler_config,
            params,
            user_id,
            user_feishu_open_id
        )

    async def _execute_via_handler(
        self,
        db: Session,
        handler_type: str,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str]
    ) -> SkillExecutionResult:
        """通过 HandlerFactory 执行"""
        result = await HandlerFactory.execute_handler(
            handler_type,
            db,
            handler_config,
            params,
            user_id,
            user_feishu_open_id
        )

        return SkillExecutionResult(
            success=result.get("success", False),
            message=result.get("message", ""),
            data=result.get("data")
        )

    def validate_action_supported(
        self,
        db: Session,
        skill_name: str,
        action_name: str
    ) -> Tuple[bool, str]:
        """
        验证 Skill/Action 是否被支持

        Returns:
            (是否支持, 错误消息)
        """
        # 检查 Skill
        skill_def = self.get_skill_definition(db, skill_name)
        if not skill_def:
            # 获取所有支持的模块
            all_skills = self.get_all_skill_definitions(db)
            module_names = [s.description for s in all_skills]
            return False, f"系统暂不支持【{skill_name}】模块。当前支持的模块有：{', '.join(module_names)}"

        # 检查 Action
        action_def = self.get_action_definition(db, skill_name, action_name)
        if not action_def:
            action_names = [a.action for a in skill_def.actions]
            return False, f"{skill_def.description}不支持【{action_name}】操作。支持的操作有：{', '.join(action_names)}"

        return True, ""

    def get_supported_modules(self, db: Session) -> List[str]:
        """获取所有支持的模块列表"""
        definitions = self.get_all_skill_definitions(db)
        return [f"{s.skill_name}（{s.description})" for s in definitions]

    def check_capability(
        self,
        db: Session,
        module_type: str,
        operation_type: str
    ) -> Tuple[bool, str]:
        """
        检查系统是否支持某模块的某操作（用于 AI 分析后告知用户）

        Args:
            module_type: 模块类型（如 product）
            operation_type: 操作类型（如 create）

        Returns:
            (是否支持, 提示消息)
        """
        # 获取所有支持的模块
        definitions = self.get_all_skill_definitions(db)
        supported_modules = {s.skill_name.lower(): s for s in definitions}

        module_lower = module_type.lower()

        if module_lower not in supported_modules:
            # 模块不存在
            all_modules = [s.description for s in definitions]
            return False, f"系统暂不支持【{module_type}】模块。当前支持的模块有：{', '.join(all_modules)}。如需新增该模块，请联系技术团队评估开发需求。"

        skill_def = supported_modules[module_lower]
        supported_actions = {a.action.lower(): a for a in skill_def.actions}

        action_lower = operation_type.lower()

        if action_lower not in supported_actions:
            # 操作不存在
            all_actions = [a.description for a in skill_def.actions]
            return False, f"{skill_def.description}暂不支持【{operation_type}】操作。支持的操作有：{', '.join(all_actions)}。如需新增该操作，请联系技术团队评估开发需求。"

        return True, f"系统支持【{module_type}】模块的【{operation_type}】操作。"


dynamic_skill_service = DynamicSkillService()
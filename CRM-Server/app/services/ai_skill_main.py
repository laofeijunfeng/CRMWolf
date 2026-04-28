"""
主 Skill 调度服务
"""
import json
from typing import Dict, Any, Optional, Tuple, AsyncGenerator
from sqlalchemy.orm import Session
from app.crud.user import user_crud
from app.crud.conversation_log import conversation_log_crud
from app.services.ai_service import ai_service
from app.services.permission_service import permission_service
from app.schemas.ai_skill import AIParsedIntent, SkillExecutionResult
from app.services.skills import dynamic_skill_service


class AISkillMainService:
    """主 Skill 调度服务（三层校验）"""

    def _get_skill_definition(self, db: Session, skill_name: str) -> Optional[Any]:
        """获取 Skill 定义（数据库优先，代码兜底）"""
        return dynamic_skill_service.get_skill_definition(db, skill_name)

    def _get_action_definition(self, db: Session, skill_name: str, action_name: str) -> Optional[Any]:
        """获取 Action 定义（数据库优先，代码兜底）"""
        return dynamic_skill_service.get_action_definition(db, skill_name, action_name)

    def _validate_params(self, action_def: Any, params: Dict[str, Any]) -> Tuple[bool, str]:
        """验证必填参数"""
        missing_params = []
        for required_param in action_def.required_params:
            if required_param not in params or params[required_param] is None:
                missing_params.append(required_param)

        if missing_params:
            param_names = "、".join(missing_params)
            return False, f"缺少必填参数：【{param_names}】，请补充完整信息后再次发起请求"
        return True, ""

    def _check_permission(self, db: Session, user_id: int, permission_code: str) -> bool:
        """检查用户是否有指定权限"""
        permissions = permission_service.get_user_permissions_from_db(db, user_id)
        for p in permissions:
            if p.code == permission_code:
                return True
        return False

    def _get_user_by_channel(self, db: Session, channel_user_id: str, channel_type: str) -> Optional[Any]:
        """根据渠道用户标识获取 CRM 用户"""
        if channel_type == "feishu":
            return user_crud.get_by_feishu_open_id(db, channel_user_id)
        return None

    def _get_channel_name(self, channel_type: str) -> str:
        """获取渠道名称"""
        return {
            "feishu": "飞书",
            "dingtalk": "钉钉",
            "wechat": "企业微信",
            "slack": "Slack",
            "web_assistant": "AI 助手"
        }.get(channel_type, channel_type)

    async def handle_message_stream_for_user(
        self,
        db: Session,
        user: Any,
        content: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理 AI 助手聊天消息（SSE 流式响应，面向 Web 用户）

        Args:
            db: 数据库 session
            user: 用户对象（直接传入，跳过渠道查找）
            content: 用户输入内容

        Yields:
            SSE 事件字典: {"event": "status/content/result/error", ...}
        """
        user_id = user.id
        channel_type = "web_assistant"

        # 创建会话日志
        log = conversation_log_crud.create_log(
            db,
            user_id=user_id,
            channel_user_id=str(user_id),
            channel_type=channel_type,
            request_text=content,
            status="PENDING"
        )

        # 发送状态事件
        yield {"event": "status", "message": "正在解析您的请求..."}

        # 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(db)
        if not config or not api_key:
            error_msg = "AI 配置未设置，请联系管理员先配置 AI 服务"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        # 流式解析意图
        parsed_intent = None
        ai_content_collected = ""

        async for event in ai_service.stream_intent_parse(db, config, api_key, content):
            if event["event"] == "content":
                ai_content_collected += event.get("content", "")
                yield event
            elif event["event"] == "parsed":
                parsed_intent = AIParsedIntent(
                    skill=event.get("skill"),
                    action=event.get("action"),
                    params=event.get("params", {}),
                    reply_text=event.get("reply_text", "正在为你执行操作...")
                )
            elif event["event"] == "error":
                error_msg = event.get("message", "AI 解析失败")
                conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
                yield event
                return

        # 检查是否成功解析
        if not parsed_intent or parsed_intent.skill is None or parsed_intent.action is None:
            reply_text = parsed_intent.reply_text if parsed_intent else "无法解析您的请求"
            conversation_log_crud.update_result(db, log.id, execution_result=reply_text, status="PARAM_MISSING")
            yield {"event": "result", "message": reply_text}
            return

        # 更新日志
        conversation_log_crud.update_result(db, log.id, status="PARSED")

        # 校验 skill/action 合法性
        yield {"event": "status", "message": "正在校验参数和权限..."}

        is_supported, error_msg = dynamic_skill_service.validate_action_supported(
            db, parsed_intent.skill, parsed_intent.action
        )
        if not is_supported:
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        # 获取 Action 定义并校验必填参数
        action_def = self._get_action_definition(db, parsed_intent.skill, parsed_intent.action)
        if not action_def:
            error_msg = f"抱歉，系统不支持该操作：【{parsed_intent.skill}.{parsed_intent.action}】"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        params_valid, params_error = self._validate_params(action_def, parsed_intent.params)
        if not params_valid:
            conversation_log_crud.update_result(db, log.id, execution_result=params_error, status="PARAM_MISSING")
            yield {"event": "result", "message": params_error}
            return

        # 校验用户权限
        if not self._check_permission(db, user_id, action_def.permission_code):
            error_msg = f"抱歉，您没有执行该操作的权限，请联系管理员申请【{action_def.permission_code}】权限"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        # 执行 Skill
        skill_def = self._get_skill_definition(db, parsed_intent.skill)
        yield {"event": "status", "message": f"正在执行【{skill_def.description if skill_def else parsed_intent.skill}】的【{action_def.description}】操作..."}

        try:
            result: SkillExecutionResult = await dynamic_skill_service.execute_action(
                db=db,
                skill_name=parsed_intent.skill,
                action_name=parsed_intent.action,
                params=parsed_intent.params,
                user_id=user_id,
                user_feishu_open_id=user.feishu_open_id
            )

            reply_text = self._format_result(result)

            conversation_log_crud.update_result(
                db,
                log.id,
                execution_result=reply_text,
                status="SUCCESS" if result.success else "FAILED"
            )

            yield {"event": "result", "message": reply_text, "success": result.success}

        except Exception as e:
            error_msg = f"执行失败：{str(e)}"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED", error_message=str(e))
            yield {"event": "error", "message": error_msg}

    async def handle_message(self, db: Session, channel_user_id: str, channel_type: str = "feishu", content: str = "") -> str:
        """
        处理聊天消息（同步返回完整结果）
        """
        # 1. 用户身份验证
        user = self._get_user_by_channel(db, channel_user_id, channel_type)
        if not user:
            return f"抱歉，您的{self._get_channel_name(channel_type)}账号未绑定 CRMWolf 系统用户，请联系管理员进行绑定"

        user_id = user.id

        # 创建会话日志
        log = conversation_log_crud.create_log(
            db,
            user_id=user_id,
            channel_user_id=channel_user_id,
            channel_type=channel_type,
            request_text=content,
            status="PENDING"
        )

        try:
            # 2. AI 解析意图
            parsed_intent: AIParsedIntent = await ai_service.parse_intent(db, content)

            conversation_log_crud.update_result(
                db,
                log.id,
                status="PARAM_MISSING" if parsed_intent.skill is None else "PARSED",
                error_message=parsed_intent.reply_text if parsed_intent.skill is None else None
            )

            # 3. AI 返回 skill 为 null → 直接返回追问文本
            if parsed_intent.skill is None or parsed_intent.action is None:
                conversation_log_crud.update_result(
                    db,
                    log.id,
                    execution_result=parsed_intent.reply_text,
                    status="PARAM_MISSING"
                )
                return parsed_intent.reply_text

            # 4-8: 执行操作
            reply_text = await self._execute_skill(db, log.id, user_id, user, parsed_intent)
            return reply_text

        except Exception as e:
            error_msg = f"系统异常：{str(e)}"
            conversation_log_crud.update_result(
                db,
                log.id,
                execution_result=error_msg,
                status="FAILED",
                error_message=str(e)
            )
            return error_msg

    async def _execute_skill(
        self,
        db: Session,
        log_id: int,
        user_id: int,
        user: Any,
        parsed_intent: AIParsedIntent
    ) -> str:
        """执行 Skill 操作（数据库优先，代码兜底）"""
        # 4. 第二层：验证 skill/action 合法性
        is_supported, error_msg = dynamic_skill_service.validate_action_supported(
            db, parsed_intent.skill, parsed_intent.action
        )
        if not is_supported:
            conversation_log_crud.update_result(
                db,
                log_id,
                execution_result=error_msg,
                status="FAILED"
            )
            return error_msg

        # 5. 获取 Action 定义并校验必填参数
        action_def = self._get_action_definition(db, parsed_intent.skill, parsed_intent.action)
        if not action_def:
            error_msg = f"抱歉，系统不支持该操作：【{parsed_intent.skill}.{parsed_intent.action}】"
            conversation_log_crud.update_result(
                db,
                log_id,
                execution_result=error_msg,
                status="FAILED"
            )
            return error_msg

        params_valid, params_error = self._validate_params(action_def, parsed_intent.params)
        if not params_valid:
            conversation_log_crud.update_result(
                db,
                log_id,
                execution_result=params_error,
                status="PARAM_MISSING"
            )
            return params_error

        # 6. 校验用户权限
        if not self._check_permission(db, user_id, action_def.permission_code):
            error_msg = f"抱歉，您没有执行该操作的权限，请联系管理员申请【{action_def.permission_code}】权限"
            conversation_log_crud.update_result(
                db,
                log_id,
                execution_result=error_msg,
                status="FAILED"
            )
            return error_msg

        # 7. 第三层：通过动态 Skill 服务执行（数据库优先，代码兜底）
        result: SkillExecutionResult = await dynamic_skill_service.execute_action(
            db=db,
            skill_name=parsed_intent.skill,
            action_name=parsed_intent.action,
            params=parsed_intent.params,
            user_id=user_id,
            user_feishu_open_id=user.feishu_open_id
        )

        # 8. 格式化结果
        reply_text = self._format_result(result)

        conversation_log_crud.update_result(
            db,
            log_id,
            execution_result=reply_text,
            status="SUCCESS" if result.success else "FAILED"
        )

        return reply_text

    async def handle_message_stream(
        self,
        db: Session,
        channel_user_id: str,
        channel_type: str = "feishu",
        content: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理聊天消息（SSE 流式响应）

        Yields:
            SSE 事件字典: {"event": "status/content/result/error", ...}
        """
        # 1. 用户身份验证
        user = self._get_user_by_channel(db, channel_user_id, channel_type)
        if not user:
            yield {"event": "error", "message": f"抱歉，您的{self._get_channel_name(channel_type)}账号未绑定 CRMWolf 系统用户，请联系管理员进行绑定"}
            return

        user_id = user.id

        # 创建会话日志
        log = conversation_log_crud.create_log(
            db,
            user_id=user_id,
            channel_user_id=channel_user_id,
            channel_type=channel_type,
            request_text=content,
            status="PENDING"
        )

        # 发送状态事件
        yield {"event": "status", "message": "正在解析您的请求..."}

        # 2. 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(db)
        if not config or not api_key:
            error_msg = "AI 配置未设置，请联系管理员先配置 AI 服务"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        # 3. 流式解析意图（使用动态提示词）
        parsed_intent = None
        ai_content_collected = ""

        async for event in ai_service.stream_intent_parse(db, config, api_key, content):
            if event["event"] == "content":
                # AI 思考过程内容
                ai_content_collected += event.get("content", "")
                yield event
            elif event["event"] == "parsed":
                # AI 解析完成
                parsed_intent = AIParsedIntent(
                    skill=event.get("skill"),
                    action=event.get("action"),
                    params=event.get("params", {}),
                    reply_text=event.get("reply_text", "正在为你执行操作...")
                )
            elif event["event"] == "error":
                error_msg = event.get("message", "AI 解析失败")
                conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
                yield event
                return

        # 4. 检查是否成功解析
        if not parsed_intent or parsed_intent.skill is None or parsed_intent.action is None:
            # AI 返回追问文本
            reply_text = parsed_intent.reply_text if parsed_intent else "无法解析您的请求"
            conversation_log_crud.update_result(db, log.id, execution_result=reply_text, status="PARAM_MISSING")
            yield {"event": "result", "message": reply_text}
            return

        # 更新日志
        conversation_log_crud.update_result(db, log.id, status="PARSED")

        # 5. 校验 skill/action 合法性
        yield {"event": "status", "message": "正在校验参数和权限..."}

        is_supported, error_msg = dynamic_skill_service.validate_action_supported(
            db, parsed_intent.skill, parsed_intent.action
        )
        if not is_supported:
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        # 6. 获取 Action 定义并校验必填参数
        action_def = self._get_action_definition(db, parsed_intent.skill, parsed_intent.action)
        if not action_def:
            error_msg = f"抱歉，系统不支持该操作：【{parsed_intent.skill}.{parsed_intent.action}】"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        params_valid, params_error = self._validate_params(action_def, parsed_intent.params)
        if not params_valid:
            conversation_log_crud.update_result(db, log.id, execution_result=params_error, status="PARAM_MISSING")
            yield {"event": "result", "message": params_error}
            return

        # 7. 校验用户权限
        if not self._check_permission(db, user_id, action_def.permission_code):
            error_msg = f"抱歉，您没有执行该操作的权限，请联系管理员申请【{action_def.permission_code}】权限"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED")
            yield {"event": "error", "message": error_msg}
            return

        # 8. 执行 Skill（通过动态 Skill 服务）
        skill_def = self._get_skill_definition(db, parsed_intent.skill)
        yield {"event": "status", "message": f"正在执行【{skill_def.description if skill_def else parsed_intent.skill}】的【{action_def.description}】操作..."}

        try:
            result: SkillExecutionResult = await dynamic_skill_service.execute_action(
                db=db,
                skill_name=parsed_intent.skill,
                action_name=parsed_intent.action,
                params=parsed_intent.params,
                user_id=user_id,
                user_feishu_open_id=user.feishu_open_id
            )

            reply_text = self._format_result(result)

            conversation_log_crud.update_result(
                db,
                log.id,
                execution_result=reply_text,
                status="SUCCESS" if result.success else "FAILED"
            )

            yield {"event": "result", "message": reply_text, "success": result.success}

        except Exception as e:
            error_msg = f"执行失败：{str(e)}"
            conversation_log_crud.update_result(db, log.id, execution_result=error_msg, status="FAILED", error_message=str(e))
            yield {"event": "error", "message": error_msg}

    def _format_result(self, result: SkillExecutionResult) -> str:
        """格式化执行结果为纯文本"""
        if result.success:
            return result.message
        else:
            return f"操作失败：{result.message}"


ai_skill_main_service = AISkillMainService()
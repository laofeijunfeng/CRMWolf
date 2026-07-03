"""对话状态机

管理对话流程的状态流转，整合 LLM 增强组件。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 五、对话状态机
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 2.1
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

from sqlalchemy.orm import Session

from app.glue.config import SessionMode
from app.glue.core.session import GlueSession, PendingAction
from app.glue.core.intent import IntentDetector, IntentResult, MultiIntentResult
from app.glue.core.entity import EntityResolver, EntityResolveResult
from app.glue.core.collector import SlotCollector, CollectResult
from app.glue.core.corrector import CorrectionResolver, CorrectionResult
from app.glue.core.cancel import CancelDetector, CancelResult
from app.glue.core.confirm import ConfirmationDetector, ConfirmationResult
from app.glue.core.ambiguity import AmbiguityResolver, AmbiguityResult
from app.glue.core.executor import ActionExecutor, ExecutionResult, PreviewResult


logger = logging.getLogger(__name__)


class DialogueAction(Enum):
    """对话动作类型"""

    PARSE_INTENT = "parse_intent"  # 解析意图
    COLLECT_SLOT = "collect_slot"  # 收集槽位
    RESOLVE_ENTITY = "resolve_entity"  # 实体消解
    RESOLVE_AMBIGUITY = "resolve_ambiguity"  # 消歧
    PREVIEW_ACTION = "preview_action"  # 预览动作
    CORRECT_ACTION = "correct_action"  # 修正动作
    EXECUTE_ACTION = "execute_action"  # 执行动作
    CANCEL_ACTION = "cancel_action"  # 取消动作
    UNKNOWN = "unknown"  # 未知输入
    ERROR = "error"  # 错误


@dataclass
class DialogueResult:
    """对话处理结果"""

    action: DialogueAction
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    next_mode: Optional[str] = None
    needs_response: bool = True  # 是否需要响应用户


class DialogueEngine:
    """对话引擎

    整合 LLM 增强组件，管理对话流程状态流转。

    状态流转:
    - IDLE: 解析意图 → COLLECTING / RESOLVING_ENTITY / PREVIEW
    - COLLECTING: 补齐槽位 → RESOLVING_ENTITY / PREVIEW / 继续问
    - RESOLVING_ENTITY: 实体消解 → RESOLVING_AMBIGUITY / COLLECTING / PREVIEW
    - RESOLVING_AMBIGUITY: 消歧 → RESOLVING_ENTITY / 取消
    - PREVIEW: 确认/修正/取消 → EXECUTING / IDLE
    - EXECUTING: 执行 → 回执 → IDLE
    - ERROR: → IDLE
    """

    def __init__(self, db: Session, tenant_id: int, user_id: int = 0):
        """初始化对话引擎

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
            user_id: 用户 ID（用于 Skill 执行）
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

        # 初始化 LLM 增强组件
        self.intent_detector = IntentDetector(db, tenant_id)
        self.entity_resolver = EntityResolver(db, tenant_id)
        self.slot_collector = SlotCollector(db, tenant_id)
        self.correction_resolver = CorrectionResolver(db, tenant_id)
        self.cancel_detector = CancelDetector(db, tenant_id)
        self.confirm_detector = ConfirmationDetector(db, tenant_id)
        self.ambiguity_resolver = AmbiguityResolver(db, tenant_id)

        # 初始化执行器（需要 user_id）
        self.action_executor = ActionExecutor(db, tenant_id, user_id)

    async def dispatch(
        self,
        session: GlueSession,
        text: str,
        auth_token: Optional[str] = None,
    ) -> DialogueResult:
        """根据 session.mode 分发处理

        Args:
            session: 当前会话状态
            text: 用户输入文本
            auth_token: 用户认证 token（用于 Skill 调用）

        Returns:
            DialogueResult: 处理结果
        """
        mode = session.mode

        # 检查 pending 是否过期
        if session.pending and session.pending.is_expired():
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="上条待确认已过期，请重新告诉我您要做什么。",
                next_mode=SessionMode.IDLE,
            )

        # 根据 mode 分发
        if mode == SessionMode.IDLE:
            return await self._handle_idle(session, text, auth_token)

        elif mode == SessionMode.COLLECTING:
            return await self._handle_collecting(session, text)

        elif mode == SessionMode.RESOLVING_ENTITY:
            return await self._handle_resolving_entity(session, text)

        elif mode == SessionMode.RESOLVING_AMBIGUITY:
            return await self._handle_resolving_ambiguity(session, text)

        elif mode == SessionMode.PREVIEW:
            return await self._handle_preview(session, text)

        elif mode == SessionMode.EXECUTING:
            return await self._handle_executing(session, text)

        elif mode == SessionMode.ERROR:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="发生错误，请重新开始。",
                next_mode=SessionMode.IDLE,
            )

        else:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=f"未知状态: {mode}",
                next_mode=SessionMode.IDLE,
            )

    async def _handle_idle(
        self,
        session: GlueSession,
        text: str,
        auth_token: Optional[str] = None,
    ) -> DialogueResult:
        """IDLE 状态处理

        解析意图，判断是否需要槽位收集或实体消解。
        支持多意图解析（复合指令如"跟进张三并设置提醒"）。
        """
        # 1. 先尝试多意图解析
        multi_result = await self.intent_detector.detect_multi(
            text, session, auth_token
        )

        # AI 服务不可用
        if multi_result.error:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=multi_result.error,
                next_mode=SessionMode.IDLE,
            )

        # 2. 处理多意图
        if multi_result.is_multi and len(multi_result.intents) > 1:
            # 创建 pending_queue（多个 PendingAction）
            pending_queue = []
            for intent_result in multi_result.intents:
                pending = PendingAction(
                    action_id=intent_result.skill_id or intent_result.intent,
                    skill_name=intent_result.skill_name,
                    slots=intent_result.slots or {},
                    missing_slots=intent_result.missing_slots or [],
                )
                pending_queue.append(pending)

            session.pending_queue = pending_queue

            # 取第一个意图作为当前 pending
            first_pending = pending_queue[0]
            session.pending = first_pending
            first_intent = multi_result.intents[0]

            # 构建提示消息
            intent_summary = self._summarize_multi_intents(multi_result.intents)
            message = f"识别到多个操作：{intent_summary}。正在处理第一个..."

            # 检查是否需要实体消解
            if first_intent.needs_entity_resolution:
                session.entity_resolution_context = {
                    "entity_type": first_intent.entity_type_hint,
                    "keyword": first_intent.entity_keyword,
                }
                return DialogueResult(
                    action=DialogueAction.RESOLVE_ENTITY,
                    success=True,
                    message=f"{message} 正在查找{first_intent.entity_type_hint or '相关记录'}...",
                    data={
                        "is_multi": True,
                        "total_intents": len(multi_result.intents),
                        "current_intent": 1,
                        "intent": first_intent.intent,
                        "entity_type": first_intent.entity_type_hint,
                        "keyword": first_intent.entity_keyword,
                    },
                    next_mode=SessionMode.RESOLVING_ENTITY,
                )

            # 检查是否有缺失槽位
            if first_intent.missing_slots:
                return DialogueResult(
                    action=DialogueAction.COLLECT_SLOT,
                    success=True,
                    message=f"{message} 请补充：{self._format_missing_slots(first_intent.missing_slots)}",
                    data={
                        "is_multi": True,
                        "total_intents": len(multi_result.intents),
                        "current_intent": 1,
                        "missing_slots": first_intent.missing_slots,
                    },
                    next_mode=SessionMode.COLLECTING,
                )

            # 槽位完整，直接预览
            return DialogueResult(
                action=DialogueAction.PREVIEW_ACTION,
                success=True,
                message=f"{message} 正在生成预览...",
                data={
                    "is_multi": True,
                    "total_intents": len(multi_result.intents),
                    "current_intent": 1,
                    "intent": first_intent.intent,
                    "slots": first_pending.slots,
                },
                next_mode=SessionMode.PREVIEW,
            )

        # 3. 单意图处理（原有逻辑）
        intent_result = multi_result.intents[0] if multi_result.intents else None

        # 如果多意图解析返回空，尝试单意图解析
        if not intent_result:
            intent_result = await self.intent_detector.detect(
                text, session, auth_token
            )

            # AI 服务不可用
            if intent_result.error:
                return DialogueResult(
                    action=DialogueAction.ERROR,
                    success=False,
                    message=intent_result.error,
                    next_mode=SessionMode.IDLE,
                )

        # 未识别意图
        if intent_result.intent == "unknown":
            return DialogueResult(
                action=DialogueAction.UNKNOWN,
                success=False,
                message="抱歉，我不太理解您的意思。请告诉我您想做什么？",
                next_mode=SessionMode.IDLE,
            )

        # 识别到意图，创建 pending action
        pending = PendingAction(
            action_id=intent_result.skill_id or intent_result.intent,
            skill_name=intent_result.skill_name,
            slots=intent_result.slots or {},
            missing_slots=intent_result.missing_slots or [],
        )
        session.pending = pending

        # 检查是否有实体引用需要消解
        if intent_result.needs_entity_resolution:
            session.entity_resolution_context = {
                "entity_type": intent_result.entity_type_hint,
                "keyword": intent_result.entity_keyword,
            }
            return DialogueResult(
                action=DialogueAction.RESOLVE_ENTITY,
                success=True,
                message=f"正在查找{intent_result.entity_type_hint or '相关记录'}...",
                data={
                    "intent": intent_result.intent,
                    "entity_type": intent_result.entity_type_hint,
                    "keyword": intent_result.entity_keyword,
                },
                next_mode=SessionMode.RESOLVING_ENTITY,
            )

        # 检查是否有缺失槽位
        if intent_result.missing_slots:
            return DialogueResult(
                action=DialogueAction.COLLECT_SLOT,
                success=True,
                message=f"请补充：{self._format_missing_slots(intent_result.missing_slots)}",
                data={
                    "missing_slots": intent_result.missing_slots,
                },
                next_mode=SessionMode.COLLECTING,
            )

        # 槽位完整，直接预览
        return DialogueResult(
            action=DialogueAction.PREVIEW_ACTION,
            success=True,
            message="正在生成预览...",
            data={
                "intent": intent_result.intent,
                "slots": pending.slots,
            },
            next_mode=SessionMode.PREVIEW,
        )

    async def _handle_collecting(
        self,
        session: GlueSession,
        text: str,
    ) -> DialogueResult:
        """COLLECTING 状态处理

        补齐槽位，判断是否完成或需要实体消解。
        """
        pending = session.pending
        if not pending:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="内部错误：无 pending action。",
                next_mode=SessionMode.IDLE,
            )

        # 调用 SlotCollector
        collect_result = await self.slot_collector.collect(
            text, pending.missing_slots, pending.slots
        )

        # AI 服务不可用
        if collect_result.error:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=collect_result.error,
                next_mode=SessionMode.COLLECTING,
            )

        # 未识别补充信息
        if not collect_result.collected:
            return DialogueResult(
                action=DialogueAction.COLLECT_SLOT,
                success=False,
                message=f"未能理解，请补充：{self._format_missing_slots(pending.missing_slots)}",
                data={"missing_slots": pending.missing_slots},
                next_mode=SessionMode.COLLECTING,
            )

        # 更新 pending slots
        pending.slots.update(collect_result.updated_slots)
        pending.missing_slots = collect_result.remaining_missing

        # 检查是否需要实体消解
        if collect_result.needs_entity_resolution:
            session.entity_resolution_context = {
                "entity_type": collect_result.entity_type_hint,
                "keyword": collect_result.entity_keyword,
            }
            return DialogueResult(
                action=DialogueAction.RESOLVE_ENTITY,
                success=True,
                message=f"正在查找{collect_result.entity_type_hint or '相关记录'}...",
                data={
                    "entity_type": collect_result.entity_type_hint,
                    "keyword": collect_result.entity_keyword,
                },
                next_mode=SessionMode.RESOLVING_ENTITY,
            )

        # 检查是否还有缺失槽位
        if pending.missing_slots:
            return DialogueResult(
                action=DialogueAction.COLLECT_SLOT,
                success=True,
                message=f"请补充：{self._format_missing_slots(pending.missing_slots)}",
                data={"missing_slots": pending.missing_slots},
                next_mode=SessionMode.COLLECTING,
            )

        # 槽位完整，进入预览
        return DialogueResult(
            action=DialogueAction.PREVIEW_ACTION,
            success=True,
            message="正在生成预览...",
            data={"slots": pending.slots},
            next_mode=SessionMode.PREVIEW,
        )

    async def _handle_resolving_entity(
        self,
        session: GlueSession,
        text: str,
    ) -> DialogueResult:
        """RESOLVING_ENTITY 状态处理

        实体消解，判断是否唯一或需要消歧。
        """
        context = session.entity_resolution_context
        if not context:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="内部错误：无实体消解上下文。",
                next_mode=SessionMode.IDLE,
            )

        # 调用 EntityResolver（B1 修复：对齐 resolve(text, entity_type, session) 签名）
        resolve_result = await self.entity_resolver.resolve(
            text,
            entity_type=context.get("entity_type"),
            session=session,
        )

        # AI 服务不可用
        if resolve_result.error:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=resolve_result.error,
                next_mode=SessionMode.RESOLVING_ENTITY,
            )

        # 唯一匹配
        if resolve_result.entity_id and resolve_result.confidence >= 0.8:
            # 更新 pending slots
            if session.pending:
                slot_field = self._get_entity_slot_field(resolve_result.entity_type)
                if slot_field:
                    session.pending.slots[slot_field] = resolve_result.entity_id

            # 清除消解上下文
            session.entity_resolution_context = None

            # 检查是否还有缺失槽位
            if session.pending and session.pending.missing_slots:
                return DialogueResult(
                    action=DialogueAction.COLLECT_SLOT,
                    success=True,
                    message=f"已锁定 {resolve_result.entity_type}，请补充：{self._format_missing_slots(session.pending.missing_slots)}",
                    data={"resolved_entity": resolve_result.entity_id},
                    next_mode=SessionMode.COLLECTING,
                )

            # 槽位完整，进入预览
            return DialogueResult(
                action=DialogueAction.PREVIEW_ACTION,
                success=True,
                message=f"已锁定 {resolve_result.entity_type}，正在生成预览...",
                data={"resolved_entity": resolve_result.entity_id},
                next_mode=SessionMode.PREVIEW,
            )

        # 多候选，需要消歧
        if resolve_result.candidates:
            session.ambiguity_context = {
                "candidates": resolve_result.candidates,
                "entity_type": resolve_result.entity_type,
            }
            return DialogueResult(
                action=DialogueAction.RESOLVE_AMBIGUITY,
                success=True,
                message=self.ambiguity_resolver.render_candidates(resolve_result.candidates),
                data={"candidates": resolve_result.candidates},
                next_mode=SessionMode.RESOLVING_AMBIGUITY,
            )

        # 无匹配
        return DialogueResult(
            action=DialogueAction.ERROR,
            success=False,
            message=f"未找到匹配的{context.get('entity_type', '记录')}，请重新描述。",
            next_mode=SessionMode.RESOLVING_ENTITY,
        )

    async def _handle_resolving_ambiguity(
        self,
        session: GlueSession,
        text: str,
    ) -> DialogueResult:
        """RESOLVING_AMBIGUITY 状态处理

        消歧选择，更新 pending slots。
        """
        context = session.ambiguity_context
        if not context:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="内部错误：无消歧上下文。",
                next_mode=SessionMode.IDLE,
            )

        candidates = context.get("candidates", [])

        # 调用 AmbiguityResolver
        ambiguity_result = await self.ambiguity_resolver.resolve(text, candidates)

        # AI 服务不可用（仅支持序号/名称选择）
        if ambiguity_result.error:
            return DialogueResult(
                action=DialogueAction.RESOLVE_AMBIGUITY,
                success=False,
                message=ambiguity_result.message,
                data={"candidates": candidates},
                next_mode=SessionMode.RESOLVING_AMBIGUITY,
            )

        # 已消解
        if ambiguity_result.resolved and ambiguity_result.selected_id:
            entity_type = context.get("entity_type")

            # 更新 pending slots
            if session.pending:
                slot_field = self._get_entity_slot_field(entity_type)
                if slot_field:
                    session.pending.slots[slot_field] = ambiguity_result.selected_id

            # 清除消歧上下文
            session.ambiguity_context = None

            # 检查是否还有缺失槽位
            if session.pending and session.pending.missing_slots:
                return DialogueResult(
                    action=DialogueAction.COLLECT_SLOT,
                    success=True,
                    message=f"{ambiguity_result.message}，请补充：{self._format_missing_slots(session.pending.missing_slots)}",
                    data={"resolved_entity": ambiguity_result.selected_id},
                    next_mode=SessionMode.COLLECTING,
                )

            # 槽位完整，进入预览
            return DialogueResult(
                action=DialogueAction.PREVIEW_ACTION,
                success=True,
                message=f"{ambiguity_result.message}，正在生成预览...",
                data={"resolved_entity": ambiguity_result.selected_id},
                next_mode=SessionMode.PREVIEW,
            )

        # 取消选择
        if ambiguity_result.resolved and ambiguity_result.selected_id is None:
            session.ambiguity_context = None
            session.entity_resolution_context = None
            return DialogueResult(
                action=DialogueAction.CANCEL_ACTION,
                success=True,
                message="已取消。",
                next_mode=SessionMode.IDLE,
            )

        # 未消解，继续询问
        return DialogueResult(
            action=DialogueAction.RESOLVE_AMBIGUITY,
            success=False,
            message=ambiguity_result.message,
            data={"candidates": ambiguity_result.remaining_candidates},
            next_mode=SessionMode.RESOLVING_AMBIGUITY,
        )

    async def _handle_preview(
        self,
        session: GlueSession,
        text: str,
    ) -> DialogueResult:
        """PREVIEW 状态处理

        处理用户确认/修正/取消。
        """
        pending = session.pending
        if not pending:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="内部错误：无 pending action。",
                next_mode=SessionMode.IDLE,
            )

        # 1. 检测取消（强关键词优先）
        if self.cancel_detector.is_strong_cancel(text):
            return DialogueResult(
                action=DialogueAction.CANCEL_ACTION,
                success=True,
                message="已取消操作。",
                next_mode=SessionMode.IDLE,
            )

        # 2. LLM 检测取消意图
        cancel_result = await self.cancel_detector.detect(text)
        if cancel_result.error:
            # AI 不可用，强关键词已处理，提示用户使用强关键词
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=f"{cancel_result.error}\n请回复「取消」或「算了」放弃。",
                next_mode=SessionMode.PREVIEW,
            )

        if cancel_result.is_cancel and cancel_result.confidence >= 0.8:
            return DialogueResult(
                action=DialogueAction.CANCEL_ACTION,
                success=True,
                message=f"已取消操作。（{cancel_result.reasoning}）",
                next_mode=SessionMode.IDLE,
            )

        # 3. 检测确认（强关键词优先）
        if self.confirm_detector.is_strong_confirm(text):
            return DialogueResult(
                action=DialogueAction.EXECUTE_ACTION,
                success=True,
                message="正在执行...",
                next_mode=SessionMode.EXECUTING,
            )

        # 4. LLM 检测确认意图
        confirm_result = await self.confirm_detector.detect(text)
        if confirm_result.error:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=f"{confirm_result.error}\n请回复「确认」执行。",
                next_mode=SessionMode.PREVIEW,
            )

        if confirm_result.is_confirm and confirm_result.confidence >= 0.8:
            return DialogueResult(
                action=DialogueAction.EXECUTE_ACTION,
                success=True,
                message=f"正在执行...（{confirm_result.reasoning}）",
                next_mode=SessionMode.EXECUTING,
            )

        # 5. LLM 检测修正意图
        correct_result = await self.correction_resolver.resolve(text, pending)

        # AI 不可用
        if correct_result.error:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=f"{correct_result.error}\n请回复「确认」执行或「取消」放弃。",
                next_mode=SessionMode.PREVIEW,
            )

        # 检测到修正
        if correct_result.success:
            pending.slots = correct_result.updated_slots

            # 检查是否需要实体消解
            if correct_result.updated_slots.get("needs_entity_resolution"):
                session.entity_resolution_context = {
                    "entity_type": correct_result.updated_slots.get("entity_type_hint"),
                    "keyword": correct_result.updated_slots.get("entity_keyword"),
                }
                return DialogueResult(
                    action=DialogueAction.RESOLVE_ENTITY,
                    success=True,
                    message=f"{correct_result.message} 正在查找...",
                    data={"correction": correct_result.corrected_field},
                    next_mode=SessionMode.RESOLVING_ENTITY,
                )

            # 重新生成预览
            return DialogueResult(
                action=DialogueAction.CORRECT_ACTION,
                success=True,
                message=f"{correct_result.message} 正在重新生成预览...",
                data={
                    "correction": correct_result.corrected_field,
                    "slots": pending.slots,
                },
                next_mode=SessionMode.PREVIEW,
            )

        # 未能理解
        return DialogueResult(
            action=DialogueAction.ERROR,
            success=False,
            message="请回复「确认」执行，或回复「取消」放弃，或告诉我需要修改的内容。",
            next_mode=SessionMode.PREVIEW,
        )

    async def _handle_executing(
        self,
        session: GlueSession,
        text: str,
    ) -> DialogueResult:
        """EXECUTING 状态处理

        执行动作并返回结果。
        支持多意图队列：执行完成后检查是否有下一个意图。
        """
        pending = session.pending
        if not pending:
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message="内部错误：无 pending action。",
                next_mode=SessionMode.IDLE,
            )

        # 调用 ActionExecutor 执行
        exec_result = await self.action_executor.execute(pending)

        if exec_result.success:
            # 执行成功
            message = exec_result.message or "操作已完成。"
            if exec_result.data:
                # 有业务数据，可以构建更详细的回执
                message = self._build_receipt_message(exec_result)

            # 检查是否有多意图队列中的下一个
            if session.pending_queue and len(session.pending_queue) > 1:
                # 从队列取出下一个意图
                next_pending = session.pending_queue[1]
                session.pending_queue = session.pending_queue[1:]  # 移除已执行的
                session.pending = next_pending

                # 构建消息
                remaining_count = len(session.pending_queue)
                next_message = f"{message} 正在处理下一个操作（剩余 {remaining_count} 个）..."

                # 检查下一个意图是否需要实体消解或槽位收集
                if next_pending.missing_slots:
                    return DialogueResult(
                        action=DialogueAction.COLLECT_SLOT,
                        success=True,
                        message=f"{next_message} 请补充：{self._format_missing_slots(next_pending.missing_slots)}",
                        data={
                            "is_multi": True,
                            "total_intents": remaining_count + 1,
                            "current_intent": 2,
                            "missing_slots": next_pending.missing_slots,
                            "prev_result": {
                                "action_id": exec_result.action_id,
                                "success": True,
                            },
                        },
                        next_mode=SessionMode.COLLECTING,
                    )

                # 槽位完整，直接进入预览
                return DialogueResult(
                    action=DialogueAction.PREVIEW_ACTION,
                    success=True,
                    message=next_message,
                    data={
                        "is_multi": True,
                        "total_intents": remaining_count + 1,
                        "current_intent": 2,
                        "slots": next_pending.slots,
                        "prev_result": {
                            "action_id": exec_result.action_id,
                            "success": True,
                        },
                    },
                    next_mode=SessionMode.PREVIEW,
                )

            # 单意图或多意图全部完成，清除 pending
            session.pending = None
            session.pending_queue = []

            return DialogueResult(
                action=DialogueAction.EXECUTE_ACTION,
                success=True,
                message=message,
                data={
                    "action_id": exec_result.action_id,
                    "skill_name": exec_result.skill_name,
                    "action_name": exec_result.action_name,
                    "result_data": exec_result.data,
                },
                next_mode=SessionMode.IDLE,
            )
        else:
            # 执行失败
            return DialogueResult(
                action=DialogueAction.ERROR,
                success=False,
                message=exec_result.message or "执行失败。",
                data={"error": exec_result.error},
                next_mode=SessionMode.IDLE,
            )

    def _build_receipt_message(self, exec_result: ExecutionResult) -> str:
        """构建执行回执消息"""
        skill_name = exec_result.skill_name or "操作"
        action_name = exec_result.action_name or ""

        # 根据 action 类型构建消息
        action_messages = {
            "create": f"已创建 {skill_name} 记录",
            "update": f"已更新 {skill_name} 信息",
            "delete": f"已删除 {skill_name} 记录",
            "follow_up": "已添加跟进记录",
            "amount": "已更新金额",
            "stage": "已更新阶段",
            "win": "已标记赢单",
            "lose": "已标记输单",
        }

        # 匹配 action 关键词
        for key, msg in action_messages.items():
            if key in action_name.lower():
                return msg

        return exec_result.message or f"{skill_name} 操作已完成"

    def _format_missing_slots(self, missing_slots: list) -> str:
        """格式化缺失槽位提示"""
        if not missing_slots:
            return ""

        slot_names = {
            "amount": "金额",
            "stage_description": "阶段",
            "content": "跟进内容",
            "customer_id": "客户",
            "opportunity_id": "商机",
            "date_description": "跟进时间",
        }

        formatted = [slot_names.get(s, s) for s in missing_slots[:3]]
        return "、".join(formatted)

    def _get_entity_slot_field(self, entity_type: Optional[str]) -> Optional[str]:
        """获取实体对应的 slot 字段"""
        if entity_type == "Customer":
            return "customer_id"
        elif entity_type == "Opportunity":
            return "opportunity_id"
        return None

    def _summarize_multi_intents(self, intents: list) -> str:
        """总结多意图列表（用于提示消息）

        Args:
            intents: IntentResult 列表

        Returns:
            意图摘要字符串，如"跟进、设置提醒"
        """
        intent_names = {
            "create_follow_up": "跟进",
            "init_opportunity": "创建商机",
            "update_opportunity": "更新商机",
            "update_amount": "修改金额",
            "update_stage": "推进阶段",
            "win_opportunity": "标记赢单",
            "lose_opportunity": "标记输单",
            "convert_lead": "转化线索",
            "set_reminder": "设置提醒",
            "query_info": "查询信息",
        }

        summaries = []
        for intent in intents:
            intent_type = intent.intent
            summaries.append(intent_names.get(intent_type, intent_type))

        return "、".join(summaries[:3])  # 最多显示 3 个


__all__ = [
    "DialogueAction",
    "DialogueResult",
    "DialogueEngine",
]
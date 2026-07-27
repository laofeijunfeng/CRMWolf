"""Unified IM entrypoint for Agent conversations."""
import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.crud.ai_config import ai_config_crud
from app.crud.im_bot import agent_channel_session_crud, im_inbound_event_crud
from app.services.agent.im_conversation import agent_im_conversation_service
from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


class IMAgentGateway:
    """Normalize IM-only interaction semantics before entering the Agent."""

    confirmation_emojis = {"Yes", "CheckMark", "OK", "THUMBSUP", "DONE", "JIAYI", "LGTM"}
    rejection_emojis = {"No", "CrossMark", "ThumbsDown", "MinusOne"}
    confidence_threshold = 0.82

    async def handle_text(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        session_id: int,
        user_text: str,
        agent_content: str,
    ) -> Dict[str, Any]:
        content = await self._normalize_confirmation_text(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            user_text=user_text,
        )
        if content is None:
            return {
                "final_content": "我还不能确定你是要确认还是取消。请明确回复「确认」或「取消」。",
                "interaction": None,
                "events": [],
                "im_events": [],
            }
        return await agent_im_conversation_service.handle_message(
            content=content or agent_content,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )

    async def handle_reaction(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        provider: str,
        response_message_id: str,
        emoji_type: str,
    ) -> Optional[Dict[str, Any]]:
        intent = self.intent_from_emoji(emoji_type)
        if not intent:
            return None

        source_event = im_inbound_event_crud.get_by_response_message_id(
            db,
            provider=provider,
            response_message_id=response_message_id,
            team_id=team_id,
        )
        source_message = (((source_event.raw_event or {}) if source_event else {}).get("message") or {})
        chat_id = source_message.get("chat_id")
        thread_id = source_message.get("thread_id") or source_message.get("root_id") or ""
        if not chat_id:
            logger.info("IM 表情未命中机器人回复消息，跳过: provider=%s message_id=%s", provider, response_message_id)
            return None

        channel_session = agent_channel_session_crud.get_by_scope(
            db,
            team_id=team_id,
            user_id=user_id,
            provider=provider,
            chat_id=chat_id,
            thread_id=thread_id,
        )
        if not channel_session:
            logger.info("IM 表情未找到 Agent 会话，跳过: provider=%s message_id=%s chat_id=%s", provider, response_message_id, chat_id)
            return None
        if not self._latest_waiting_task(db, team_id=team_id, user_id=user_id, session_id=channel_session.agent_session_id):
            logger.info("IM 表情当前没有待确认任务，跳过: provider=%s message_id=%s emoji_type=%s", provider, response_message_id, emoji_type)
            return None

        return await agent_im_conversation_service.handle_message(
            content="是" if intent == "confirm" else "否",
            team_id=team_id,
            user_id=user_id,
            session_id=channel_session.agent_session_id,
        )

    def intent_from_emoji(self, emoji_type: str) -> Optional[str]:
        if emoji_type in self.confirmation_emojis:
            return "confirm"
        if emoji_type in self.rejection_emojis:
            return "reject"
        return None

    async def _normalize_confirmation_text(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        user_text: str,
    ) -> Optional[str]:
        task = self._latest_waiting_task(db, team_id=team_id, user_id=user_id, session_id=session_id)
        if not task:
            return ""

        intent = await self._classify_confirmation_intent(db, team_id, user_text, task)
        if intent == "confirm":
            return "是"
        if intent == "reject":
            return "否"
        return None

    def _latest_waiting_task(self, db: Session, *, team_id: int, user_id: int, session_id: int):
        return agent_task_crud.get_latest_waiting(
            db,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
        )

    async def _classify_confirmation_intent(self, db: Session, team_id: int, content: str, task) -> Optional[str]:
        try:
            config = ai_config_crud.get_config(db, team_id)
            api_key = ai_config_crud.get_decrypted_api_key(db, team_id) if config else None
            if not config or not api_key:
                return None
            task_payload = {
                "summary": task.summary,
                "intent": task.intent,
                "state": task.state_json or {},
                "input": task.input_json or {},
            }
            raw = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是 CRM IM 确认流程的语义分类器。只判断用户回复是否在确认或拒绝当前待确认动作。"
                            "只输出 JSON：{\"intent\":\"confirm|reject|unknown\",\"confidence\":0.0,\"reason\":\"...\"}。"
                            "不要执行任务，不要解释业务。用户补充字段、提出新要求、闲聊、表情含义不明确时输出 unknown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "【当前待确认动作】\n"
                            f"{json.dumps(task_payload, ensure_ascii=False, default=str)}\n\n"
                            "【用户回复】\n"
                            f"{content}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(self._clean_json(raw))
            intent = parsed.get("intent")
            confidence = float(parsed.get("confidence") or 0.0)
            if intent in {"confirm", "reject"} and confidence >= self.confidence_threshold:
                return intent
            logger.info("IM 确认语义分类不明确: intent=%s confidence=%s raw=%s", intent, confidence, raw)
        except Exception as exc:
            logger.info("IM 确认语义分类失败: %s", exc)
        return None

    def _clean_json(self, raw: str) -> str:
        content = raw.strip()
        if content.startswith("```json"):
            content = content[7:].strip()
        elif content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end >= start:
            return content[start:end + 1]
        return content


im_agent_gateway = IMAgentGateway()

"""Feishu bot adapter for IM Agent messages."""

import base64
from dataclasses import dataclass
import hashlib
import json
import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.orm import Session

from app.crud.oauth import oauth_provider_config_crud, user_oauth_account_crud
from app.crud.im_bot import agent_channel_session_crud, im_inbound_event_crud
from app.models.im_bot import IMBotProvider, IMInboundEventStatus
from app.models.oauth import OAuthProviderConfig
from app.schemas.agent import AgentSessionCreate
from app.services.agent import agent_copy
from app.services.agent.task_factory import WAITING_TASK_EVENT_TYPES
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
    follow_up_task_confirmation_channel_service,
)
from app.services.im_agent_gateway import im_agent_gateway


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IMReplyBinding:
    agent_session_id: Optional[int] = None
    agent_task_id: Optional[int] = None
    agent_interaction_type: Optional[str] = None
    confirmation_delivery_public_id: Optional[str] = None
    confirmation_case_public_id: Optional[str] = None
    agent_interaction_id: Optional[str] = None
    prompt_delivery_key: Optional[str] = None

    @property
    def is_follow_up_confirmation(self) -> bool:
        return bool(self.confirmation_delivery_public_id and self.confirmation_case_public_id)


@dataclass(frozen=True)
class IMReplyDelivery:
    reply_to_message_id: Optional[str]
    text: Optional[str]
    binding: Optional[IMReplyBinding] = None


class FeishuBotEventError(Exception):
    pass


class FeishuBotService:
    api_base_url = "https://open.feishu.cn/open-apis"
    receipt_emoji_type = "Get"

    async def handle_event(
        self,
        db: Session,
        payload: Dict[str, Any],
        raw_body: bytes,
    ) -> Dict[str, Any]:
        encrypted_config = None
        if "encrypt" in payload:
            payload, encrypted_config = self._decrypt_event_payload(db, payload["encrypt"])

        if payload.get("type") == "url_verification":
            self._resolve_url_verification_config(db, payload, encrypted_config)
            return {"challenge": payload.get("challenge")}

        header = payload.get("header") or {}
        event = payload.get("event") or {}
        app_id = header.get("app_id")
        logger.info(
            "收到飞书机器人事件: event_id=%s event_type=%s app_id=%s",
            header.get("event_id"),
            header.get("event_type"),
            app_id,
        )
        integration_config = encrypted_config or (
            oauth_provider_config_crud.get_by_app_id(db, IMBotProvider.FEISHU, app_id) if app_id else None
        )
        if not integration_config:
            raise FeishuBotEventError("未找到匹配的飞书第三方集成配置")
        if app_id and integration_config.app_id and app_id != integration_config.app_id:
            raise FeishuBotEventError("飞书事件 App ID 与第三方集成配置不匹配")
        if not integration_config.bot_enabled:
            logger.info(
                "飞书机器人未启用，跳过事件: event_id=%s team_id=%s", header.get("event_id"), integration_config.team_id
            )
            return {"message": "bot disabled"}
        payload_token = payload.get("token") or header.get("token")
        if integration_config.bot_verification_token and payload_token != integration_config.bot_verification_token:
            raise FeishuBotEventError("飞书事件校验 Token 不匹配")

        event_type = header.get("event_type") or ""
        message = event.get("message") or {}
        reaction_message_id = event.get("message_id") or event.get("messageId")
        event_id = header.get("event_id") or message.get("message_id") or reaction_message_id
        message_id = message.get("message_id") or reaction_message_id
        if not event_id:
            raise FeishuBotEventError("飞书事件缺少 event_id")

        inbound_event, duplicate = im_inbound_event_crud.create_received(
            db,
            provider=IMBotProvider.FEISHU,
            event_id=event_id,
            message_id=message_id,
            request_hash=hashlib.sha256(raw_body).hexdigest(),
            team_id=integration_config.team_id,
            raw_event=self._compact_raw_event(payload),
        )
        if duplicate:
            return {"message": "duplicate"}

        failure_persisted = False
        try:
            im_inbound_event_crud.mark_status(db, inbound_event, IMInboundEventStatus.PROCESSING)
            delivery = IMReplyDelivery(reply_to_message_id=message_id, text=None)
            if "reaction" in event_type:
                delivery = await self._handle_reaction_event(db, integration_config, event, event_type)
            else:
                delivery = await self._handle_message_event(db, integration_config, event)
            response_message_id = None
            binding = delivery.binding if delivery.text and delivery.reply_to_message_id else None
            if delivery.text and delivery.reply_to_message_id:
                try:
                    response_message_id = await self.reply_text(
                        db, integration_config, delivery.reply_to_message_id, delivery.text
                    )
                except Exception as send_exc:
                    db.rollback()
                    if binding and binding.confirmation_delivery_public_id:
                        follow_up_task_confirmation_channel_service.acknowledge_im_provider_failed(
                            db,
                            team_id=integration_config.team_id,
                            delivery_public_id=binding.confirmation_delivery_public_id,
                            error_message=str(send_exc),
                            commit=False,
                        )
                    im_inbound_event_crud.mark_status(
                        db,
                        inbound_event,
                        IMInboundEventStatus.FAILED,
                        error_message=str(send_exc),
                        commit=False,
                    )
                    db.commit()
                    failure_persisted = True
                    raise

            persisted_binding = binding if response_message_id else None
            if response_message_id and persisted_binding and persisted_binding.confirmation_delivery_public_id:
                acknowledged = follow_up_task_confirmation_channel_service.acknowledge_im_provider_visible(
                    db,
                    team_id=integration_config.team_id,
                    delivery_public_id=persisted_binding.confirmation_delivery_public_id,
                    provider_message_id=response_message_id,
                    commit=False,
                )
                if acknowledged is None or acknowledged.provider_message_id != response_message_id:
                    db.rollback()
                    raise FeishuBotEventError("确认提示未能绑定到飞书可见消息")
            im_inbound_event_crud.mark_status(
                db,
                inbound_event,
                IMInboundEventStatus.PROCESSED,
                response_message_id=response_message_id,
                agent_session_id=persisted_binding.agent_session_id if persisted_binding else None,
                agent_task_id=persisted_binding.agent_task_id if persisted_binding else None,
                agent_interaction_type=persisted_binding.agent_interaction_type if persisted_binding else None,
                confirmation_delivery_public_id=(
                    persisted_binding.confirmation_delivery_public_id if persisted_binding else None
                ),
                confirmation_case_public_id=(
                    persisted_binding.confirmation_case_public_id if persisted_binding else None
                ),
                agent_interaction_id=persisted_binding.agent_interaction_id if persisted_binding else None,
                prompt_delivery_key=persisted_binding.prompt_delivery_key if persisted_binding else None,
                commit=False,
            )
            db.commit()
            return {"message": "processed"}
        except Exception as exc:
            logger.exception("飞书机器人事件处理失败: %s", exc)
            if not failure_persisted:
                db.rollback()
                im_inbound_event_crud.mark_status(
                    db,
                    inbound_event,
                    IMInboundEventStatus.FAILED,
                    error_message=str(exc),
                )
            raise

    async def _handle_message_event(
        self, db: Session, integration_config: OAuthProviderConfig, event: Dict[str, Any]
    ) -> IMReplyDelivery:
        message = event.get("message") or {}
        message_id = message.get("message_id")
        message_type = message.get("message_type")
        logger.info(
            "处理飞书消息事件: message_id=%s chat_type=%s message_type=%s mention_count=%s",
            message.get("message_id"),
            message.get("chat_type"),
            message_type,
            len(message.get("mentions") or []),
        )
        if message_type != "text":
            return IMReplyDelivery(message_id, agent_copy.im_text_only())

        chat_type = message.get("chat_type")
        if chat_type != "p2p" and not self._mentions_bot(db, message, integration_config):
            logger.info(
                "飞书群消息未识别为 @ 当前机器人，跳过: message_id=%s bot_open_id=%s app_id=%s mentions=%s",
                message.get("message_id"),
                integration_config.bot_open_id,
                integration_config.app_id,
                message.get("mentions") or [],
            )
            return IMReplyDelivery(message_id, None)

        sender_id = (event.get("sender") or {}).get("sender_id") or {}
        open_id = sender_id.get("open_id")
        if not open_id:
            logger.info("飞书消息缺少发送人 open_id: message_id=%s sender_id=%s", message.get("message_id"), sender_id)
            return IMReplyDelivery(message_id, agent_copy.im_identity_missing("飞书"))

        account = user_oauth_account_crud.get_by_open_id(db, integration_config.team_id, IMBotProvider.FEISHU, open_id)
        if not account:
            logger.info(
                "飞书发送人未绑定 CRM 账号: message_id=%s team_id=%s sender_open_id=%s",
                message.get("message_id"),
                integration_config.team_id,
                open_id,
            )
            return IMReplyDelivery(message_id, agent_copy.im_account_not_bound("飞书"))

        content = self._extract_text(message)
        if not content:
            return IMReplyDelivery(message_id, agent_copy.im_text_missing())

        if message_id:
            try:
                await self.add_message_reaction(db, integration_config, message_id, self.receipt_emoji_type)
            except Exception as exc:
                logger.warning("飞书机器人收到确认表情失败，继续处理消息: message_id=%s error=%s", message_id, exc)

        chat_id = message.get("chat_id") or open_id
        thread_id = message.get("thread_id") or message.get("root_id") or ""
        session_scope = hashlib.sha256(
            f"{integration_config.team_id}:{integration_config.provider}:{chat_id}:{thread_id}:{account.user_id}".encode()
        ).hexdigest()[:32]
        channel_session = agent_channel_session_crud.get_or_create(
            db,
            team_id=integration_config.team_id,
            user_id=account.user_id,
            provider=IMBotProvider.FEISHU,
            chat_id=chat_id,
            thread_id=thread_id,
            external_tenant_key=account.tenant_key,
            session_create=AgentSessionCreate(
                session_key=f"im_feishu_{session_scope}",
                team_id=integration_config.team_id,
                user_id=account.user_id,
                title=content[:50],
                context_json={
                    "channel": "im",
                    "provider": IMBotProvider.FEISHU,
                    "chat_id": message.get("chat_id"),
                },
            ),
        )
        agent_content = await self._build_agent_content(integration_config, message, content)
        referenced_message_ids = self._referenced_message_ids(message)
        result = await im_agent_gateway.handle_text(
            db,
            team_id=integration_config.team_id,
            user_id=account.user_id,
            provider=IMBotProvider.FEISHU,
            session_id=channel_session.agent_session_id,
            user_text=content,
            agent_content=agent_content,
            chat_id=chat_id,
            thread_id=thread_id,
            referenced_message_ids=referenced_message_ids,
        )
        if message.get("message_id"):
            agent_channel_session_crud.mark_message(db, channel_session, message["message_id"])
        return IMReplyDelivery(
            message_id,
            self._render_im_reply(result),
            self._extract_reply_binding(result),
        )

    async def _handle_reaction_event(
        self,
        db: Session,
        integration_config: OAuthProviderConfig,
        event: Dict[str, Any],
        event_type: str,
    ) -> IMReplyDelivery:
        if event_type != "im.message.reaction.created_v1":
            logger.info("飞书消息表情事件不是新增表情，跳过: event_type=%s", event_type)
            return IMReplyDelivery(None, None)
        message_id = event.get("message_id") or event.get("messageId")
        reaction = event.get("reaction") or event
        operator = reaction.get("operator") or event.get("operator") or {}
        operator_type = operator.get("operator_type") or event.get("operator_type")
        emoji_type = (
            ((reaction.get("reaction_type") or event.get("reaction_type") or {}).get("emoji_type")) or ""
        ).strip()
        logger.info(
            "处理飞书消息表情事件: message_id=%s emoji_type=%s operator_type=%s",
            message_id,
            emoji_type,
            operator_type,
        )
        if operator_type == "app":
            return IMReplyDelivery(None, None)
        if not im_agent_gateway.intent_from_emoji(emoji_type):
            return IMReplyDelivery(None, None)

        operator_id = self._extract_operator_open_id(operator) or self._extract_operator_open_id(
            event.get("user_id") or {}
        )
        if not operator_id:
            logger.info(
                "飞书消息表情事件缺少用户 open_id: message_id=%s operator=%s user_id=%s",
                message_id,
                operator,
                event.get("user_id"),
            )
            return IMReplyDelivery(None, None)
        account = user_oauth_account_crud.get_by_open_id(
            db, integration_config.team_id, IMBotProvider.FEISHU, operator_id
        )
        if not account:
            logger.info("飞书消息表情操作人未绑定 CRM 账号: message_id=%s operator_open_id=%s", message_id, operator_id)
            return IMReplyDelivery(message_id, agent_copy.im_account_not_bound("飞书"))

        result = await im_agent_gateway.handle_reaction(
            db,
            team_id=integration_config.team_id,
            user_id=account.user_id,
            provider=IMBotProvider.FEISHU,
            response_message_id=message_id,
            emoji_type=emoji_type,
        )
        if not result:
            return IMReplyDelivery(None, None)
        return IMReplyDelivery(message_id, self._render_im_reply(result), self._extract_reply_binding(result))

    async def reply_text(
        self, db: Session, integration_config: OAuthProviderConfig, message_id: str, text: str
    ) -> Optional[str]:
        secret = oauth_provider_config_crud.get_secret(integration_config)
        if not integration_config.app_id or not secret:
            raise FeishuBotEventError("机器人 app_id 或 app_secret 未配置")
        token = await self._get_tenant_access_token(integration_config.app_id, secret)
        payload = {
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base_url}/im/v1/messages/{message_id}/reply",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 0:
            raise FeishuBotEventError(data.get("msg") or "飞书回复消息失败")
        logger.info(
            "飞书机器人回复成功: message_id=%s response_message_id=%s",
            message_id,
            ((data.get("data") or {}).get("message_id")),
        )
        return (data.get("data") or {}).get("message_id")

    async def add_message_reaction(
        self,
        db: Session,
        integration_config: OAuthProviderConfig,
        message_id: str,
        emoji_type: str,
    ) -> Optional[str]:
        secret = oauth_provider_config_crud.get_secret(integration_config)
        if not integration_config.app_id or not secret:
            raise FeishuBotEventError("机器人 app_id 或 app_secret 未配置")
        token = await self._get_tenant_access_token(integration_config.app_id, secret)
        payload = {
            "reaction_type": {
                "emoji_type": emoji_type,
            },
        }
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base_url}/im/v1/messages/{quote(message_id, safe='')}/reactions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 0:
            raise FeishuBotEventError(data.get("msg") or "飞书添加消息表情失败")
        reaction_id = (data.get("data") or {}).get("reaction_id")
        logger.info(
            "飞书机器人添加消息表情成功: message_id=%s emoji_type=%s reaction_id=%s",
            message_id,
            emoji_type,
            reaction_id,
        )
        return reaction_id

    async def _get_tenant_access_token(self, app_id: str, app_secret: str) -> str:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base_url}/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 0:
            raise FeishuBotEventError(data.get("msg") or "获取飞书 tenant_access_token 失败")
        return data["tenant_access_token"]

    async def _fetch_message_text(self, integration_config: OAuthProviderConfig, message_id: str) -> Optional[str]:
        secret = oauth_provider_config_crud.get_secret(integration_config)
        if not integration_config.app_id or not secret:
            return None
        token = await self._get_tenant_access_token(integration_config.app_id, secret)
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.get(
                f"{self.api_base_url}/im/v1/messages/{quote(message_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            logger.warning("获取飞书引用消息失败: message_id=%s status=%s", message_id, response.status_code)
            return None
        data = response.json()
        if data.get("code") != 0:
            logger.warning(
                "获取飞书引用消息失败: message_id=%s code=%s msg=%s", message_id, data.get("code"), data.get("msg")
            )
            return None
        items = (data.get("data") or {}).get("items") or []
        if not items:
            return None
        item = items[0]
        raw_content = (item.get("body") or {}).get("content") or "{}"
        return self._extract_content_text(raw_content, item.get("msg_type"), item.get("mentions") or [])

    def _resolve_url_verification_config(
        self,
        db: Session,
        payload: Dict[str, Any],
        integration_config: Optional[OAuthProviderConfig] = None,
    ) -> OAuthProviderConfig:
        token = payload.get("token") or ((payload.get("header") or {}).get("token"))
        app_id = (payload.get("header") or {}).get("app_id")
        if integration_config and app_id and integration_config.app_id and app_id != integration_config.app_id:
            raise FeishuBotEventError("飞书事件 App ID 与第三方集成配置不匹配")
        if integration_config is None and app_id:
            integration_config = oauth_provider_config_crud.get_by_app_id(db, IMBotProvider.FEISHU, app_id)
        if integration_config is None and token:
            integration_config = oauth_provider_config_crud.get_by_verification_token(db, IMBotProvider.FEISHU, token)
        if not integration_config:
            raise FeishuBotEventError("未找到匹配的飞书第三方集成配置")
        if integration_config.bot_verification_token and token != integration_config.bot_verification_token:
            raise FeishuBotEventError("飞书事件校验 Token 不匹配")
        return integration_config

    def _decrypt_event_payload(self, db: Session, encrypted_payload: str) -> tuple[Dict[str, Any], OAuthProviderConfig]:
        configs = oauth_provider_config_crud.list_with_encrypt_key(db, IMBotProvider.FEISHU)
        decrypted_candidates: list[tuple[Dict[str, Any], OAuthProviderConfig]] = []
        for integration_config in configs:
            try:
                decrypted = self._decrypt_with_key(encrypted_payload, integration_config.bot_encrypt_key or "")
                payload = json.loads(decrypted)
                app_id = (payload.get("header") or {}).get("app_id")
                if app_id and integration_config.app_id == app_id:
                    return payload, integration_config
                decrypted_candidates.append((payload, integration_config))
            except Exception:
                continue
        if len(decrypted_candidates) == 1:
            return decrypted_candidates[0]
        if decrypted_candidates:
            raise FeishuBotEventError("飞书加密事件匹配到多个第三方集成配置，请检查 App ID 和 Encrypt Key")
        raise FeishuBotEventError("飞书加密事件解密失败，请检查 Encrypt Key 配置")

    def _decrypt_with_key(self, encrypted_payload: str, encrypt_key: str) -> str:
        key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
        encrypted_bytes = base64.b64decode(encrypted_payload)
        if len(encrypted_bytes) <= 16:
            raise ValueError("encrypted payload is too short")
        iv = encrypted_bytes[:16]
        encrypted_event = encrypted_bytes[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_event) + decryptor.finalize()
        padding = decrypted[-1]
        if padding < 1 or padding > 16:
            raise ValueError("invalid padding")
        return decrypted[:-padding].decode("utf-8")

    def _extract_content_text(self, raw_content: Any, message_type: Optional[str], mentions: list[dict]) -> str:
        try:
            content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
        except ValueError:
            return str(raw_content).strip()
        if not isinstance(content, dict):
            return str(content).strip()
        text = str(content.get("text") or "").strip()
        if not text and message_type == "post":
            text = self._extract_post_text(content)
        if not text:
            text = json.dumps(content, ensure_ascii=False)
        for mention in mentions:
            key = (mention.get("key") or "").strip()
            if key:
                text = text.replace(key, "")
            name = (mention.get("name") or "").strip()
            if name:
                text = re.sub(rf"@{re.escape(name)}\b", "", text)
                text = text.replace(f"@{name}", "")
        text = re.sub(r"<at[^>]*>.*?</at>", "", text, flags=re.IGNORECASE | re.DOTALL)
        return text.strip()

    def _extract_text(self, message: Dict[str, Any]) -> str:
        return self._extract_content_text(
            message.get("content") or "{}",
            message.get("message_type"),
            message.get("mentions") or [],
        )

    def _extract_post_text(self, content: Dict[str, Any]) -> str:
        zh_cn = content.get("zh_cn") or {}
        post_content = zh_cn.get("content") or []
        parts = []
        for line in post_content:
            if not isinstance(line, list):
                continue
            for node in line:
                if isinstance(node, dict) and node.get("text"):
                    parts.append(str(node["text"]))
        return "\n".join(parts).strip()

    async def _build_agent_content(
        self, integration_config: OAuthProviderConfig, message: Dict[str, Any], content: str
    ) -> str:
        root_id = message.get("root_id") or message.get("parent_id")
        if not root_id:
            return content
        quote_text = await self._fetch_message_text(integration_config, root_id)
        if quote_text:
            return f"引用消息：\n{quote_text}\n\n本次指令：\n{content}"
        return f"引用消息ID：{root_id}\n\n本次指令：\n{content}"

    def _referenced_message_ids(self, message: Dict[str, Any]) -> list[str]:
        ids = []
        for key in ("parent_id", "root_id"):
            message_id = message.get(key)
            if message_id and message_id not in ids:
                ids.append(message_id)
        return ids

    def _extract_operator_open_id(self, operator: Dict[str, Any]) -> Optional[str]:
        operator_id = operator.get("operator_id")
        if isinstance(operator_id, dict):
            return operator_id.get("open_id") or operator_id.get("user_id") or operator_id.get("union_id")
        return operator.get("open_id") or (str(operator_id) if operator_id else None)

    def _mentions_bot(self, db: Session, message: Dict[str, Any], integration_config: OAuthProviderConfig) -> bool:
        mentions = message.get("mentions") or []
        if not mentions:
            return False
        for mention in mentions:
            mention_id = (mention.get("id") or {}) if isinstance(mention, dict) else {}
            if integration_config.bot_open_id and mention_id.get("open_id") == integration_config.bot_open_id:
                return True
            if integration_config.app_id and mention_id.get("app_id") == integration_config.app_id:
                return True
            if mention.get("mentioned_type") == "bot":
                mention_open_id = mention_id.get("open_id")
                if mention_open_id and not integration_config.bot_open_id:
                    integration_config.bot_open_id = mention_open_id
                    db.commit()
                    logger.info(
                        "已从飞书 @ 信息自动记录 Bot Open ID: config_id=%s bot_open_id=%s",
                        integration_config.id,
                        mention_open_id,
                    )
                return True
        return False

    def _extract_reply_binding(self, result: Dict[str, Any]) -> IMReplyBinding:
        session = result.get("session") or {}
        agent_session_id = self._safe_int(session.get("session_id"))
        interactions: list[dict[str, Any]] = []
        top_level_interaction = result.get("interaction")
        if isinstance(top_level_interaction, dict):
            interactions.append(top_level_interaction)
        waiting_event = None
        for event in result.get("events") or []:
            if not isinstance(event, dict):
                continue
            event_interaction = event.get("interaction")
            if isinstance(event_interaction, dict):
                interactions.append(event_interaction)
            if event.get("event") in WAITING_TASK_EVENT_TYPES and event.get("task_id"):
                waiting_event = event

        for interaction in interactions:
            if interaction.get("business_action") != FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION:
                continue
            payload = interaction.get("payload") if isinstance(interaction.get("payload"), dict) else {}
            case = payload.get("case") if isinstance(payload.get("case"), dict) else {}
            case_public_id = self._clean_string(
                payload.get("case_public_id") or case.get("public_id") or case.get("id")
            )
            delivery_public_id = self._clean_string(
                payload.get("confirmation_delivery_public_id") or payload.get("delivery_public_id")
            )
            prompt_delivery_key = self._clean_string(payload.get("prompt_delivery_key"))
            interaction_id = self._clean_string(interaction.get("interaction_id") or payload.get("interaction_id"))
            if case_public_id and delivery_public_id:
                return IMReplyBinding(
                    agent_session_id=agent_session_id,
                    agent_interaction_type=str(interaction.get("type") or "choice"),
                    confirmation_delivery_public_id=delivery_public_id,
                    confirmation_case_public_id=case_public_id,
                    agent_interaction_id=interaction_id,
                    prompt_delivery_key=prompt_delivery_key,
                )

        if not waiting_event:
            return IMReplyBinding(agent_session_id=agent_session_id)
        return IMReplyBinding(
            agent_session_id=agent_session_id,
            agent_task_id=self._safe_int(waiting_event.get("task_id")),
            agent_interaction_type=waiting_event.get("event"),
        )

    @staticmethod
    def _clean_string(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    def _safe_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _render_im_reply(self, result: Dict[str, Any]) -> str:
        content = str(result.get("final_content") or "").strip()
        interaction = result.get("interaction") or {}
        if interaction.get("type") == "choice" and "回复" not in content:
            choices = interaction.get("choices") if isinstance(interaction.get("choices"), list) else []
            labels = [
                str(choice.get("label") or choice.get("value") or "").strip()
                for choice in choices
                if isinstance(choice, dict) and str(choice.get("label") or choice.get("value") or "").strip()
            ]
            if labels == ["是", "否"]:
                return f"{content}\n\n回复「是」确认，回复「否」取消。"
            if labels:
                options = "\n".join(f"{index}. {label}" for index, label in enumerate(labels, start=1))
                return f"{content}\n\n{options}\n\n回复序号或选项文字。"
        return content or "已处理。"

    def _compact_raw_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        header = payload.get("header") or {}
        event = payload.get("event") or {}
        message = event.get("message") or {}
        reaction = event.get("reaction") or {}
        return {
            "header": {
                "event_id": header.get("event_id"),
                "event_type": header.get("event_type"),
                "app_id": header.get("app_id"),
                "tenant_key": header.get("tenant_key"),
            },
            "message": {
                "message_id": message.get("message_id"),
                "message_type": message.get("message_type"),
                "chat_id": message.get("chat_id"),
                "chat_type": message.get("chat_type"),
                "thread_id": message.get("thread_id"),
                "root_id": message.get("root_id"),
                "parent_id": message.get("parent_id"),
                "mentions": message.get("mentions") or [],
            },
            "reaction": {
                "message_id": event.get("message_id") or event.get("messageId"),
                "operator": reaction.get("operator") or event.get("operator"),
                "reaction_type": reaction.get("reaction_type") or event.get("reaction_type"),
            },
        }


feishu_bot_service = FeishuBotService()

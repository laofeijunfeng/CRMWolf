import json
import logging
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.constants.business_types import BUSINESS_TYPE_DISPLAY_NAMES
from app.core.config import get_settings
from app.crud.oauth import oauth_provider_config_crud, user_oauth_account_crud


logger = logging.getLogger(__name__)
settings = get_settings()


class FeishuNotificationService:
    api_base_url = "https://open.feishu.cn/open-apis"

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
            raise RuntimeError(data.get("msg") or "获取飞书 tenant_access_token 失败")
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError("飞书未返回 tenant_access_token")
        return token

    def _get_enabled_config(self, db: Session, team_id: int):
        config = oauth_provider_config_crud.get(db, team_id, "feishu")
        if not config or not config.enabled or not config.app_id:
            return None, None
        secret = oauth_provider_config_crud.get_secret(config)
        if not secret:
            return None, None
        return config, secret

    async def send_to_user(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        msg_type: str,
        content: Dict[str, Any],
    ) -> bool:
        config, secret = self._get_enabled_config(db, team_id)
        if not config or not secret:
            logger.info("飞书通知未启用，跳过发送（team_id=%s, user_id=%s）", team_id, user_id)
            return False

        account = user_oauth_account_crud.get_by_user(db, team_id, "feishu", user_id)
        if not account or not account.open_id:
            logger.info("用户未绑定飞书，跳过发送（team_id=%s, user_id=%s）", team_id, user_id)
            return False

        token = await self._get_tenant_access_token(config.app_id, secret)
        payload = {
            "receive_id": account.open_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base_url}/im/v1/messages?receive_id_type=open_id",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            raise RuntimeError(data.get("msg") or "飞书消息发送失败")
        return True

    async def send_to_users(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        msg_type: str,
        content: Dict[str, Any],
    ) -> Dict[str, int]:
        result = {"success": 0, "failed": 0, "skipped": 0}
        seen_user_ids = []
        for user_id in user_ids:
            if user_id not in seen_user_ids:
                seen_user_ids.append(user_id)

        for user_id in seen_user_ids:
            try:
                sent = await self.send_to_user(db, team_id, user_id, msg_type, content)
                result["success" if sent else "skipped"] += 1
            except Exception as exc:
                result["failed"] += 1
                logger.error("飞书通知发送失败（team_id=%s, user_id=%s）: %s", team_id, user_id, exc)
        return result

    async def notify_approval_pending(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        entity_type: str,
        entity_name: str,
        flow_name: str,
        node_name: str,
        business_id: Optional[int] = None,
        submitter_name: Optional[str] = None,
        approval_type_name: Optional[str] = None,
        customer_name: Optional[str] = None,
        detail_fields: Optional[Dict[str, str]] = None,
    ) -> Dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        fields = detail_fields or self._fallback_approval_fields(
            approval_type_name=approval_type_name,
            entity_name=entity_name,
            customer_name=customer_name,
        )
        content = self._approval_card(
            entity_type=entity_type,
            title=f"{submitter_name or '有人'}有个{approval_type_name}需要你审批",
            template="blue",
            fields=fields,
            button_text="去处理",
            button_url=self._absolute_frontend_url(db, team_id, "/approvals"),
        )
        return await self.send_to_users(db, team_id, user_ids, "interactive", content)

    async def notify_approval_approved(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        entity_type: str,
        entity_name: str,
        business_id: Optional[int] = None,
        detail_fields: Optional[Dict[str, str]] = None,
        button_path: Optional[str] = None,
    ) -> Dict[str, int]:
        approval_type_name = self._entity_type_label(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"你的{approval_type_name}已通过",
            template="green",
            fields=detail_fields or self._fallback_approval_fields(
                approval_type_name=approval_type_name,
                entity_name=entity_name,
            ),
            button_text="去看看",
            button_url=self._absolute_frontend_url(db, team_id, button_path),
        )
        return await self.send_to_users(db, team_id, [user_id], "interactive", content)

    async def notify_approval_rejected(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        entity_type: str,
        entity_name: str,
        reject_reason: str,
        business_id: Optional[int] = None,
        detail_fields: Optional[Dict[str, str]] = None,
        button_path: Optional[str] = None,
    ) -> Dict[str, int]:
        approval_type_name = self._entity_type_label(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"你的{approval_type_name}被驳回了",
            template="red",
            fields=detail_fields or self._fallback_approval_fields(
                approval_type_name=approval_type_name,
                entity_name=entity_name,
            ),
            button_text="去看看",
            button_url=self._absolute_frontend_url(db, team_id, button_path),
        )
        return await self.send_to_users(db, team_id, [user_id], "interactive", content)

    async def notify_approval_cancelled(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        entity_type: str,
        entity_name: str,
        submitter_name: Optional[str] = None,
        approval_type_name: Optional[str] = None,
        detail_fields: Optional[Dict[str, str]] = None,
    ) -> Dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"{submitter_name or '有人'}撤回了{approval_type_name}的审批申请",
            template="yellow",
            fields=detail_fields or self._fallback_approval_fields(
                approval_type_name=approval_type_name,
                entity_name=entity_name,
            ),
        )
        return await self.send_to_users(db, team_id, user_ids, "interactive", content)

    async def notify_approval_issued(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        entity_type: str,
        entity_name: str,
        detail_fields: Optional[Dict[str, str]] = None,
        button_path: Optional[str] = None,
    ) -> Dict[str, int]:
        approval_type_name = self._entity_type_label(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"你的{approval_type_name}文件已下发",
            template="blue",
            fields=detail_fields or self._fallback_approval_fields(
                approval_type_name=approval_type_name,
                entity_name=entity_name,
            ),
            button_text="去下载",
            button_url=self._absolute_frontend_url(db, team_id, button_path),
        )
        return await self.send_to_users(db, team_id, [user_id], "interactive", content)

    def _approval_card(
        self,
        entity_type: str,
        title: str,
        template: str,
        fields: Dict[str, str],
        button_text: Optional[str] = None,
        button_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        elements = []
        for label, value in fields.items():
            display_value = value if value not in (None, "") else "-"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{label}**：{display_value}"}})

        if button_text and button_url:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": button_text},
                            "type": "primary",
                            "url": button_url,
                        }
                    ],
                }
            )

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": elements,
        }

    def _fallback_approval_fields(
        self,
        approval_type_name: str,
        entity_name: str,
        customer_name: Optional[str] = None,
    ) -> Dict[str, str]:
        fields = {}
        if customer_name is not None:
            fields["客户名称"] = customer_name or "-"
        fields[f"{approval_type_name}名称"] = entity_name or "-"
        return fields

    def _entity_type_label(self, entity_type: Optional[str]) -> str:
        return BUSINESS_TYPE_DISPLAY_NAMES.get(entity_type or "", "审批")

    def _frontend_base_url(self, db: Session, team_id: int) -> Optional[str]:
        frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
        if not frontend_url:
            config = oauth_provider_config_crud.get(db, team_id, "feishu")
            parsed = urlparse(config.redirect_uri) if config and config.redirect_uri else None
            if parsed and parsed.scheme and parsed.netloc:
                frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        return frontend_url or None

    def _absolute_frontend_url(self, db: Session, team_id: int, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        frontend_url = self._frontend_base_url(db, team_id)
        if not frontend_url:
            return None
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{frontend_url}{normalized_path}"


feishu_notification_service = FeishuNotificationService()

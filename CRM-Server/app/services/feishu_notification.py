import json
import logging
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode, urlparse

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
    ) -> Dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        content = self._approval_pending_card(
            title=f"{submitter_name or '有人'}有个{approval_type_name}需要你处理",
            template="blue",
            entity_name=entity_name,
            approval_type_name=approval_type_name,
            customer_name=customer_name,
            button_url=self._approval_center_url(db, team_id, entity_type),
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
    ) -> Dict[str, int]:
        approval_type_name = self._entity_type_label(entity_type)
        content = self._approval_result_card(
            title=f"你的{approval_type_name}申请已通过",
            template="green",
            entity_name=entity_name,
            approval_type_name=approval_type_name,
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
    ) -> Dict[str, int]:
        content = self._approval_card(
            title="审批已拒绝",
            template="red",
            entity_type=entity_type,
            entity_name=entity_name,
            fields={
                "原因": reject_reason,
                "单据ID": str(business_id) if business_id else "",
            },
        )
        return await self.send_to_users(db, team_id, [user_id], "interactive", content)

    def _approval_card(
        self,
        title: str,
        template: str,
        entity_type: str,
        entity_name: str,
        fields: Dict[str, str],
    ) -> Dict[str, Any]:
        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**类型**：{entity_type}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**名称**：{entity_name}"}},
        ]
        for label, value in fields.items():
            if value:
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{label}**：{value}"}})

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": elements,
        }

    def _approval_pending_card(
        self,
        title: str,
        template: str,
        entity_name: str,
        approval_type_name: str,
        customer_name: Optional[str],
        button_url: Optional[str],
    ) -> Dict[str, Any]:
        elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{approval_type_name}名称**：{entity_name}"},
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**客户名称**：{customer_name or '-'}"},
            },
        ]
        if button_url:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "去处理"},
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

    def _approval_result_card(
        self,
        title: str,
        template: str,
        entity_name: str,
        approval_type_name: str,
    ) -> Dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**{approval_type_name}名称**：{entity_name}"},
                },
            ],
        }

    def _entity_type_label(self, entity_type: Optional[str]) -> str:
        return BUSINESS_TYPE_DISPLAY_NAMES.get(entity_type or "", "审批")

    def _approval_center_url(self, db: Session, team_id: int, entity_type: str) -> Optional[str]:
        frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
        if not frontend_url:
            config = oauth_provider_config_crud.get(db, team_id, "feishu")
            parsed = urlparse(config.redirect_uri) if config and config.redirect_uri else None
            if parsed and parsed.scheme and parsed.netloc:
                frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        if not frontend_url:
            return None
        query = urlencode({"status": "PENDING", "business_type": entity_type})
        return f"{frontend_url}/approvals?{query}"


feishu_notification_service = FeishuNotificationService()

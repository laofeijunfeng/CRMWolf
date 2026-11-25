from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.constants.business_types import BUSINESS_TYPE_DISPLAY_NAMES, BusinessType
from app.core.config import get_settings
from app.crud.oauth import oauth_provider_config_crud, user_oauth_account_crud

if TYPE_CHECKING:
    from app.models.oauth import OAuthProviderConfig


logger = logging.getLogger(__name__)
settings = get_settings()


def _format_amount(value: object) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value or "0.00")


_OWNER_TRANSFER_CUSTOMER = "CUSTOMER"


def _cascade_text(cascade: dict[str, int]) -> str:
    return (
        f"商机 {cascade.get('opportunities', 0)} 个、合同 {cascade.get('contracts', 0)} 份\uff1b"
        f"未转移合同 {cascade.get('locked', 0)} 份\uff08审批中或已签署\uff09"
    )


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

    def _get_enabled_config(self, db: Session, team_id: int) -> tuple[OAuthProviderConfig | None, str | None]:
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
        content: dict[str, Any],
    ) -> bool:
        config, secret = self._get_enabled_config(db, team_id)
        if not config or not secret:
            logger.info("飞书通知未启用\uff0c跳过发送\uff08team_id=%s, user_id=%s\uff09", team_id, user_id)
            return False

        account = user_oauth_account_crud.get_by_user(db, team_id, "feishu", user_id)
        if not account or not account.open_id:
            logger.info("用户未绑定飞书\uff0c跳过发送\uff08team_id=%s, user_id=%s\uff09", team_id, user_id)
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
        content: dict[str, Any],
    ) -> dict[str, int]:
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
                logger.error("飞书通知发送失败\uff08team_id=%s, user_id=%s\uff09: %s", team_id, user_id, exc)
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
        business_id: int | None = None,
        submitter_name: str | None = None,
        approval_type_name: str | None = None,
        customer_name: str | None = None,
        detail_fields: dict[str, str] | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        fields = detail_fields or self._fallback_approval_fields(
            approval_type_name=approval_type_name,
            entity_name=entity_name,
            customer_name=customer_name,
        )
        content = self._approval_card(
            entity_type=entity_type,
            title=f"{submitter_name or '有人'}{sep}有个{sep}{approval_type_name}需要你审批",
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
        business_id: int | None = None,
        detail_fields: dict[str, str] | None = None,
        approval_type_name: str | None = None,
        button_path: str | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"你的{sep}{approval_type_name}已通过",
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
        business_id: int | None = None,
        detail_fields: dict[str, str] | None = None,
        approval_type_name: str | None = None,
        button_path: str | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"你的{sep}{approval_type_name}被驳回了",
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
        submitter_name: str | None = None,
        approval_type_name: str | None = None,
        detail_fields: dict[str, str] | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"{submitter_name or '有人'}{sep}撤回了{sep}{approval_type_name}的审批申请",
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
        detail_fields: dict[str, str] | None = None,
        approval_type_name: str | None = None,
        button_path: str | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        content = self._approval_card(
            entity_type=entity_type,
            title=f"你的{sep}{approval_type_name}文件已下发",
            template="blue",
            fields=detail_fields or self._fallback_approval_fields(
                approval_type_name=approval_type_name,
                entity_name=entity_name,
            ),
            button_text="去下载",
            button_url=self._absolute_frontend_url(db, team_id, button_path),
        )
        return await self.send_to_users(db, team_id, [user_id], "interactive", content)

    async def notify_approval_cc(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        entity_type: str,
        entity_name: str,
        approval_id: int,
        cc_node_name: str,
        submitter_name: str | None = None,
        approval_type_name: str | None = None,
        customer_name: str | None = None,
        detail_fields: dict[str, str] | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        fields = detail_fields or self._fallback_approval_fields(
            approval_type_name=approval_type_name,
            entity_name=entity_name,
            customer_name=customer_name,
        )
        if cc_node_name:
            fields = {**fields, "抄送节点": cc_node_name}
        content = self._approval_card(
            entity_type=entity_type,
            title=f"{submitter_name or '有人'}{sep}的{sep}{approval_type_name}抄送给你",
            template="wathet",
            fields=fields,
            button_text="查看详情",
            button_url=self._absolute_frontend_url(db, team_id, f"/approvals?tab=cc&approval_id={int(approval_id)}"),
        )
        return await self.send_to_users(db, team_id, user_ids, "interactive", content)

    async def notify_approval_reminder(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        entity_type: str,
        entity_name: str,
        node_name: str,
        business_id: int | None = None,
        submitter_name: str | None = None,
        approval_type_name: str | None = None,
        detail_fields: dict[str, str] | None = None,
    ) -> dict[str, int]:
        approval_type_name = approval_type_name or self._entity_type_label(entity_type)
        sep = self._title_separator(entity_type)
        fields = detail_fields or self._fallback_approval_fields(
            approval_type_name=approval_type_name,
            entity_name=entity_name,
        )
        if node_name:
            fields = {**fields, "当前审批节点": node_name}

        content = self._approval_card(
            entity_type=entity_type,
            title=f"{submitter_name or '提交人'}{sep}催你处理{sep}{approval_type_name}审批",
            template="orange",
            fields=fields,
            button_text="去审批",
            button_url=self._absolute_frontend_url(db, team_id, "/approvals"),
        )
        return await self.send_to_users(db, team_id, user_ids, "interactive", content)

    async def notify_markdown_card(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        title: str,
        markdown: str,
        template: str = "blue",
    ) -> dict[str, int]:
        content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": markdown}},
            ],
        }
        return await self.send_to_users(db, team_id, user_ids, "interactive", content)

    async def notify_account_created(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        account_name: str,
        contact_name: str,
    ) -> dict[str, int]:
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="🎉 新客户创建成功",
            markdown=(
                f"客户创建成功\uff01\n\n**客户名称**: {account_name}\n"
                f"**主联系人**: {contact_name}\n\n请及时跟进客户\uff01"
            ),
        )

    async def notify_account_status_won(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        account_name: str,
    ) -> dict[str, int]:
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="🎊 恭喜赢单",
            markdown=f"恭喜您成功赢单\uff01\n\n**客户名称**: {account_name}\n\n太棒了\uff0c继续保持\uff01",
            template="green",
        )

    async def notify_account_status_lost(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        account_name: str,
    ) -> dict[str, int]:
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="😔 客户已输单",
            markdown=f"客户已输单\n\n**客户名称**: {account_name}\n\n请总结经验\uff0c继续加油\uff01",
            template="red",
        )

    async def notify_customer_returned(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        account_name: str,
        return_reason: str,
        previous_owner: str | None = None,
    ) -> dict[str, int]:
        previous = previous_owner or "-"
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="🔄 客户已退回公海",
            markdown=(
                f"客户已退回公海\n\n**客户名称**: {account_name}\n"
                f"**退回原因**: {return_reason}\n**原负责人**: {previous}\n\n"
                "其他销售人员可以领取该客户。"
            ),
            template="yellow",
        )

    async def notify_lead_claimed(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        lead_name: str,
    ) -> dict[str, int]:
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="✅ 线索领取成功",
            markdown=f"您已成功领取线索\uff1a**{lead_name}**\n\n请尽快跟进\uff0c祝您成交\uff01",
            template="green",
        )

    async def notify_owner_transfer_received(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        entity_type: str,
        name: str,
        operator_name: str | None,
        previous_owner_name: str | None,
        contact_name: str | None,
        contact_phone: str | None,
        follow_up: dict[str, str | None] | None,
        remark: str | None,
        cascade: dict[str, int] | None,
        detail_path: str | None,
    ) -> dict[str, int]:
        is_customer = entity_type == _OWNER_TRANSFER_CUSTOMER
        fields = {f"{'客户' if is_customer else '线索'}名称": name}
        if operator_name:
            fields["操作人"] = operator_name
        fields["原负责人"] = previous_owner_name or "无"
        fields["联系人"] = contact_name or "暂无联系人"
        if contact_name and contact_phone:
            fields["联系电话"] = contact_phone
        if follow_up:
            head = " · ".join(part for part in (follow_up.get("occurred_at"), follow_up.get("method")) if part)
            content = follow_up.get("content") or ""
            fields[f"最近{follow_up.get('kind_label') or '跟进记录'}"] = "\n".join(
                part for part in (head, content) if part
            )
        if remark:
            fields["移交备注"] = remark
        if cascade:
            fields["随客户转移"] = _cascade_text(cascade)
        content_card = self._approval_card(
            entity_type=entity_type,
            title="📦 你收到一个移交的客户" if is_customer else "🎯 你收到一条新分配的线索",
            template="blue",
            fields=fields,
            button_text="查看详情",
            button_url=self._absolute_frontend_url(db, team_id, detail_path),
        )
        return await self.send_to_users(db, team_id, user_ids, "interactive", content_card)

    async def notify_owner_transfer_previous(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        entity_type: str,
        name: str,
        new_owner_name: str | None,
        operator_name: str | None,
        cascade: dict[str, int] | None,
    ) -> dict[str, int]:
        is_customer = entity_type == _OWNER_TRANSFER_CUSTOMER
        fields = {
            f"{'客户' if is_customer else '线索'}名称": name,
            "移交给" if is_customer else "分配给": new_owner_name or "-",
        }
        if operator_name:
            fields["操作人"] = operator_name
        if cascade:
            fields["随客户转移"] = _cascade_text(cascade)
        content_card = self._approval_card(
            entity_type=entity_type,
            title="📤 你负责的客户已移交" if is_customer else "📤 你负责的线索已重新分配",
            template="grey",
            fields=fields,
        )
        return await self.send_to_users(db, team_id, user_ids, "interactive", content_card)

    async def notify_opportunity_won(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        opportunity_name: str,
        customer_name: str,
        actual_amount: object = 0,
    ) -> dict[str, int]:
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="🎊 恭喜赢单",
            markdown=(
                f"恭喜您成功赢单\uff01\n\n**商机名称**: {opportunity_name}\n"
                f"**客户名称**: {customer_name}\n**实际金额**: ¥{_format_amount(actual_amount)}\n\n"
                "太棒了\uff0c继续保持\uff01"
            ),
            template="green",
        )

    async def notify_opportunity_lost(
        self,
        db: Session,
        team_id: int,
        user_ids: Iterable[int],
        *,
        opportunity_name: str,
        customer_name: str,
        loss_reason: str,
    ) -> dict[str, int]:
        return await self.notify_markdown_card(
            db,
            team_id,
            user_ids,
            title="😔 商机已输单",
            markdown=(
                f"商机已输单\n\n**商机名称**: {opportunity_name}\n"
                f"**客户名称**: {customer_name}\n**输单原因**: {loss_reason}\n\n"
                "请总结经验\uff0c继续加油\uff01"
            ),
            template="red",
        )

    @staticmethod
    def _title_separator(entity_type: str) -> str:
        # License 卡片标题按产品要求在中英文之间加空格,其他单据保持原写法
        return " " if entity_type == BusinessType.LICENSE else ""

    def _approval_card(
        self,
        entity_type: str,
        title: str,
        template: str,
        fields: dict[str, str],
        button_text: str | None = None,
        button_url: str | None = None,
    ) -> dict[str, Any]:
        elements = []
        for label, value in fields.items():
            display_value = value if value not in (None, "") else "-"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{label}**\uff1a{display_value}"}})

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
        customer_name: str | None = None,
    ) -> dict[str, str]:
        fields = {}
        if customer_name is not None:
            fields["客户名称"] = customer_name or "-"
        fields[f"{approval_type_name}名称"] = entity_name or "-"
        return fields

    def _entity_type_label(self, entity_type: str | None) -> str:
        return BUSINESS_TYPE_DISPLAY_NAMES.get(entity_type or "", "审批")

    def _frontend_base_url(self, db: Session, team_id: int) -> str | None:
        frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
        if not frontend_url:
            config = oauth_provider_config_crud.get(db, team_id, "feishu")
            parsed = urlparse(config.redirect_uri) if config and config.redirect_uri else None
            if parsed and parsed.scheme and parsed.netloc:
                frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        return frontend_url or None

    def _absolute_frontend_url(self, db: Session, team_id: int, path: str | None) -> str | None:
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

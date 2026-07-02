import logging
import httpx
from typing import Optional, Dict, Any
from app.constants.business_types import BusinessType
from app.core.config import get_settings
from app.schemas.user import FeishuTokenResponse, FeishuUserInfo

settings = get_settings()
logger = logging.getLogger(__name__)


# 单据类型展示名 —— 通知文案标题里 fallback 用，避免硬编码"合同"
_ENTITY_TYPE_LABEL = {
    BusinessType.CONTRACT: "合同",
    BusinessType.PAYMENT: "回款登记",
    BusinessType.INVOICE: "发票申请",
}


def _entity_label(entity_type: Optional[str]) -> str:
    """取单据类型中文标签；未知类型回退 '单据'。"""
    if not entity_type:
        return "合同"
    return _ENTITY_TYPE_LABEL.get(entity_type, "单据")


def _resolve_entity(
    entity_type: Optional[str],
    entity_name: Optional[str],
    business_id: Optional[int],
    contract_name: Optional[str],
    contract_id: Optional[int],
) -> tuple[str, Optional[str], Optional[int]]:
    """feishu_service 内部别名解析：contract_name/contract_id 回退到新签名，
    entity_type 缺省视为 CONTRACT。"""
    if entity_name is None and contract_name is not None:
        entity_name = contract_name
    if business_id is None and contract_id is not None:
        business_id = contract_id
    if entity_type is None:
        entity_type = BusinessType.CONTRACT
    return entity_type, entity_name, business_id


class FeishuService:
    def __init__(self):
        self.base_url = "https://open.feishu.cn"
        self.app_id = settings.FEISHU_APP_ID if hasattr(settings, 'FEISHU_APP_ID') else ""
        self.app_secret = settings.FEISHU_APP_SECRET if hasattr(settings, 'FEISHU_APP_SECRET') else ""

    async def get_user_access_token(self, code: str) -> FeishuTokenResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/open-apis/authen/v1/access_token",
                json={
                    "grant_type": "authorization_code",
                    "code": code
                },
                headers={
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"飞书API错误: {data.get('msg')}")
            
            return FeishuTokenResponse(**data["data"])

    async def get_user_info(self, access_token: str) -> FeishuUserInfo:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/authen/v1/user_info",
                headers={
                    "Authorization": f"Bearer {access_token}"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"飞书API错误: {data.get('msg')}")
            
            return FeishuUserInfo(**data["data"])

    async def refresh_user_access_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str
    ) -> FeishuTokenResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/authen/v1/refresh_access_token",
                json={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token
                },
                headers={
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"飞书API错误: {data.get('msg')}")
            
            return FeishuTokenResponse(**data["data"])

    async def get_tenant_access_token(self) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret
                },
                headers={
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"飞书API错误: {data.get('msg')}")
            
            return data["data"]["tenant_access_token"]

    async def send_message_card(
        self,
        user_id: str,
        title: str,
        content: str,
        tenant_access_token: Optional[str] = None
    ) -> bool:
        try:
            if not tenant_access_token:
                tenant_access_token = await self.get_tenant_access_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/open-apis/message/v4/send",
                    json={
                        "msg_type": "interactive",
                        "receive_id": user_id,
                        "receive_id_type": "open_id",
                        "content": {
                            "config": {
                                "wide_screen_mode": True
                            },
                            "header": {
                                "title": {
                                    "tag": "plain_text",
                                    "content": title
                                },
                                "template": "blue"
                            },
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": content
                                    }
                                }
                            ]
                        }
                    },
                    headers={
                        "Authorization": f"Bearer {tenant_access_token}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                    print(f"飞书发送消息失败: {data.get('msg')}")
                    return False
                
                return True
        except Exception as e:
            print(f"飞书发送消息异常: {str(e)}")
            return False

    async def send_text_message(
        self,
        user_id: str,
        text: str,
        tenant_access_token: Optional[str] = None
    ) -> bool:
        try:
            if not tenant_access_token:
                tenant_access_token = await self.get_tenant_access_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/open-apis/message/v4/send",
                    json={
                        "msg_type": "text",
                        "receive_id": user_id,
                        "receive_id_type": "open_id",
                        "content": {
                            "text": text
                        }
                    },
                    headers={
                        "Authorization": f"Bearer {tenant_access_token}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                    print(f"飞书发送消息失败: {data.get('msg')}")
                    return False
                
                return True
        except Exception as e:
            print(f"飞书发送消息异常: {str(e)}")
            return False

    async def notify_lead_assigned(
        self,
        user_id: str,
        lead_name: str,
        contact_name: str,
        contact_phone: str
    ) -> bool:
        title = "🎯 新线索分配通知"
        content = f"""**线索信息**
        
**线索名称**: {lead_name}
**联系人**: {contact_name}
**联系电话**: {contact_phone}

请及时跟进该线索！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_lead_claimed(
        self,
        user_id: str,
        lead_name: str
    ) -> bool:
        title = "✅ 线索领取成功"
        content = f"""您已成功领取线索：**{lead_name}**

请尽快跟进，祝您成交！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_follow_up_reminder(
        self,
        user_id: str,
        lead_name: str,
        days: int
    ) -> bool:
        title = "⏰ 跟进提醒"
        content = f"""您有线索需要跟进

**线索名称**: {lead_name}
**未跟进天数**: {days}天

请尽快联系客户！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_account_created(
        self,
        user_id: str,
        account_name: str,
        contact_name: str
    ) -> bool:
        title = "🎉 新客户创建成功"
        content = f"""客户创建成功！

**客户名称**: {account_name}
**主联系人**: {contact_name}

请及时跟进客户！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_account_status_won(
        self,
        user_id: str,
        account_name: str
    ) -> bool:
        title = "🎊 恭喜赢单"
        content = f"""恭喜您成功赢单！

**客户名称**: {account_name}

太棒了，继续保持！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_account_status_lost(
        self,
        user_id: str,
        account_name: str
    ) -> bool:
        title = "😔 客户已输单"
        content = f"""客户已输单

**客户名称**: {account_name}

请总结经验，继续加油！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_account_assigned(
        self,
        user_id: str,
        account_name: str
    ) -> bool:
        title = "🎯 新客户分配通知"
        content = f"""您有新的客户

**客户名称**: {account_name}

请及时跟进！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_opportunity_created(
        self,
        user_id: str,
        opportunity_name: str,
        customer_name: str,
        expected_amount: float
    ) -> bool:
        title = "🎯 新商机创建通知"
        content = f"""您有新的商机

**商机名称**: {opportunity_name}
**客户名称**: {customer_name}
**预计金额**: ¥{expected_amount:,.2f}

请及时跟进！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_opportunity_stage_updated(
        self,
        user_id: str,
        opportunity_name: str,
        stage_name: str,
        win_probability: int
    ) -> bool:
        title = "📊 商机阶段更新"
        content = f"""商机阶段已更新

**商机名称**: {opportunity_name}
**当前阶段**: {stage_name}
**赢单概率**: {win_probability}%

请继续推进！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_opportunity_won(
        self,
        user_id: str,
        opportunity_name: str,
        actual_amount: float,
        customer_name: str
    ) -> bool:
        title = "🎊 恭喜赢单"
        content = f"""恭喜您成功赢单！

**商机名称**: {opportunity_name}
**客户名称**: {customer_name}
**实际金额**: ¥{actual_amount:,.2f}

太棒了，继续保持！"""
        
        return await self.send_message_card(user_id, title, content)

    async def send_customer_returned_notification(
        self,
        customer_name: str,
        return_reason: str,
        previous_owner: str
    ) -> bool:
        title = "🔄 客户已退回公海"
        content = f"""客户已退回公海

**客户名称**: {customer_name}
**退回原因**: {return_reason}
**原负责人**: {previous_owner}

其他销售人员可以领取该客户。"""
        
        return await self.send_message_card(previous_owner, title, content)

    async def send_customer_claimed_notification(
        self,
        user_id: str,
        customer_name: str
    ) -> bool:
        title = "✅ 客户领取成功"
        content = f"""您已成功领取客户：**{customer_name}**

请尽快跟进，祝您成交！"""
        
        return await self.send_message_card(user_id, title, content)

    async def notify_opportunity_lost(
        self,
        user_id: str,
        opportunity_name: str,
        loss_reason: str,
        customer_name: str
    ) -> bool:
        title = "😔 商机已输单"
        content = f"""商机已输单

**商机名称**: {opportunity_name}
**客户名称**: {customer_name}
**输单原因**: {loss_reason}

请总结经验，继续加油！"""
        
        return await self.send_message_card(user_id, title, content)
    
    async def notify_approval_pending(
        self,
        user_id: str,
        contract_name: Optional[str] = None,
        flow_name: str = "",
        node_name: str = "",
        *,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        business_id: Optional[int] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过飞书 API 发送审批待处理通知（A8 泛化）。

        旧合同调用方仍可按 `(user_id, contract_name, flow_name, node_name)`
        位置参数调用；新调用方传 `entity_type / entity_name / business_id`
        关键字参数。两种形式内部统一解析到泛化字段。
        """
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = f"📋 新的{label}审批待处理"
        content = f"""您有一个新的{label}审批需要处理

**{label}名称**: {entity_name}
**审批流程**: {flow_name}
**当前节点**: {node_name}

请及时处理，避免影响业务进度。"""

        return await self.send_message_card(user_id, title, content)

    async def notify_approval_approved(
        self,
        user_id: str,
        contract_name: Optional[str] = None,
        *,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        business_id: Optional[int] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过飞书 API 发送审批通过通知（A8 泛化）。"""
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = f"✅ {label}审批已通过"
        content = f"""您的{label}审批已全部通过

**{label}名称**: {entity_name}

{label}已审批通过，可以进行后续操作。"""

        return await self.send_message_card(user_id, title, content)

    async def notify_approval_rejected(
        self,
        user_id: str,
        contract_name: Optional[str] = None,
        reject_reason: str = "",
        *,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        business_id: Optional[int] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过飞书 API 发送审批拒绝通知（A8 泛化）。"""
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = f"❌ {label}审批被拒绝"
        content = f"""您的{label}审批被拒绝

**{label}名称**: {entity_name}
**拒绝原因**: {reject_reason}

请根据审批意见修改后重新提交。"""

        return await self.send_message_card(user_id, title, content)

    # ========== Webhook 群聊通知方法 ==========

    async def send_webhook_message(
        self,
        webhook_url: str,
        title: str,
        content: str,
        button_url: Optional[str] = None
    ) -> bool:
        """通过飞书群聊机器人 Webhook 发送消息卡片

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            title: 消息卡片标题
            content: 消息卡片内容（支持 lark_md 格式）
            button_url: 可选按钮跳转链接

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        try:
            elements = [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                }
            ]

            # 添加按钮（如果有）
            if button_url:
                elements.append({
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "查看详情"
                            },
                            "url": button_url,
                            "type": "primary"
                        }
                    ]
                })

            card = {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue"
                },
                "elements": elements
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "msg_type": "interactive",
                        "card": card
                    },
                    headers={
                        "Content-Type": "application/json"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    logger.warning(f"飞书 Webhook 发送失败: {data.get('msg')}")
                    return False

                return True
        except Exception as e:
            logger.error(f"飞书 Webhook 发送异常: {str(e)}")
            return False

    def _entity_detail_url(self, entity_type: str, business_id: Optional[int]) -> Optional[str]:
        """构造业务单据详情页跳转链接。

        旧合同沿用 `/contracts/{id}`；PAYMENT / INVOICE 走各自的模块路由。
        business_id 缺省或前端基址未配 → 返回 None（无按钮）。
        """
        frontend_url = settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else ""
        if not frontend_url or business_id is None:
            return None
        path_map = {
            BusinessType.CONTRACT: "contracts",
            BusinessType.PAYMENT: "payments",
            BusinessType.INVOICE: "invoices",
        }
        segment = path_map.get(entity_type, "contracts")
        return f"{frontend_url}/{segment}/{business_id}"

    async def notify_approval_webhook(
        self,
        webhook_url: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        flow_name: str = "",
        node_name: str = "",
        approver_name: str = "",
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过 Webhook 发送审批待处理通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            flow_name: 审批流程名称
            node_name: 当前审批节点名称
            approver_name: 审批人姓名
            business_id: 业务单据ID（用于生成跳转链接）
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = f"📋 新的{label}审批待处理"
        content = f"""您有一个新的{label}审批需要处理

**{label}名称**: {entity_name}
**审批流程**: {flow_name}
**当前节点**: {node_name}
**审批人**: {approver_name}

请及时处理，避免影响业务进度。"""

        button_url = self._entity_detail_url(entity_type, business_id)

        return await self.send_webhook_message(webhook_url, title, content, button_url)

    async def notify_approval_approved_webhook(
        self,
        webhook_url: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过 Webhook 发送审批通过通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            business_id: 业务单据ID（用于生成跳转链接）
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = f"✅ {label}审批已通过"
        content = f"""您的{label}审批已全部通过

**{label}名称**: {entity_name}

{label}已审批通过，可以进行后续操作。"""

        button_url = self._entity_detail_url(entity_type, business_id)

        return await self.send_webhook_message(webhook_url, title, content, button_url)

    async def notify_approval_rejected_webhook(
        self,
        webhook_url: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        reject_reason: str = "",
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过 Webhook 发送审批拒绝通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            reject_reason: 拒绝原因
            business_id: 业务单据ID（用于生成跳转链接）
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = f"❌ {label}审批被拒绝"
        content = f"""您的{label}审批被拒绝

**{label}名称**: {entity_name}
**拒绝原因**: {reject_reason}

请根据审批意见修改后重新提交。"""

        button_url = self._entity_detail_url(entity_type, business_id)

        return await self.send_webhook_message(webhook_url, title, content, button_url)

    async def notify_approval_cancelled_webhook(
        self,
        webhook_url: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        submitter_name: str = "",
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过 Webhook 发送审批撤回通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            submitter_name: 撤回人姓名
            business_id: 业务单据ID（用于生成跳转链接）
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)
        title = "🔄 审批已撤回"
        content = f"""审批任务已取消

**{label}名称**: {entity_name}
**撤回人**: {submitter_name}

提交人已撤回审批，您无需继续处理此审批任务。"""

        button_url = self._entity_detail_url(entity_type, business_id)

        return await self.send_webhook_message(webhook_url, title, content, button_url)

    # ========== 审批催办通知方法 ==========

    async def notify_approval_reminder(
        self,
        user_id: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        waiting_hours: int = 0,
        node_name: str = "",
        reminder_level: str = "light",
        *,
        contract_name: Optional[str] = None,
    ) -> bool:
        """通过飞书 API 发送审批催办通知给审批人

        泛化签名（A8）：entity_type / entity_name 替代 contract_name（旧别名仍兼容）。

        Args:
            user_id: 审批人 open_id
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            waiting_hours: 已等待小时数
            node_name: 当前审批节点名称
            reminder_level: 提醒级别（light/medium/strong）
            contract_name: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        level_icons = {
            "light": "⏰",
            "medium": "🔔",
            "strong": "🚨"
        }
        level_texts = {
            "light": "轻度提醒",
            "medium": "中度催办",
            "strong": "强度告警"
        }

        icon = level_icons.get(reminder_level, "⏰")
        level_text = level_texts.get(reminder_level, "提醒")

        entity_type, entity_name, _ = _resolve_entity(
            entity_type, entity_name, None, contract_name, None
        )
        label = _entity_label(entity_type)

        title = f"{icon} 审批催办通知（{level_text}）"
        content = f"""您有待处理的审批任务

**{label}名称**: {entity_name}
**当前节点**: {node_name}
**已等待**: {waiting_hours}小时

请尽快处理或联系提交人说明情况。"""

        return await self.send_message_card(user_id, title, content)

    async def notify_approval_reminder_webhook(
        self,
        webhook_url: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        waiting_hours: int = 0,
        node_name: str = "",
        approver_name: str = "",
        business_id: Optional[int] = None,
        reminder_level: str = "light",
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过 Webhook 发送审批催办通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            waiting_hours: 已等待小时数
            node_name: 当前审批节点名称
            approver_name: 审批人姓名
            business_id: 业务单据ID
            reminder_level: 提醒级别（light/medium/strong）
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        level_icons = {
            "light": "⏰",
            "medium": "🔔",
            "strong": "🚨"
        }
        level_texts = {
            "light": "轻度提醒",
            "medium": "中度催办",
            "strong": "强度告警"
        }

        icon = level_icons.get(reminder_level, "⏰")
        level_text = level_texts.get(reminder_level, "提醒")

        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)

        title = f"{icon} 审批催办通知（{level_text}）"
        content = f"""审批人 {approver_name} 有待处理的审批任务

**{label}名称**: {entity_name}
**当前节点**: {node_name}
**审批人**: {approver_name}
**已等待**: {waiting_hours}小时

请尽快处理或联系提交人说明情况。"""

        button_url = self._entity_detail_url(entity_type, business_id)

        return await self.send_webhook_message(webhook_url, title, content, button_url)

    async def notify_approval_timeout_alert(
        self,
        user_id: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        node_name: str = "",
        approver_name: str = "",
        waiting_hours: int = 0,
        reminder_level: str = "medium",
        is_admin: bool = False,
        *,
        contract_name: Optional[str] = None,
    ) -> bool:
        """通过飞书 API 发送审批超时告警给提交人或管理员

        泛化签名（A8）：entity_type / entity_name 替代 contract_name（旧别名仍兼容）。

        Args:
            user_id: 提交人/管理员 open_id
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            node_name: 当前审批节点名称
            approver_name: 当前审批人姓名
            waiting_hours: 已等待小时数
            reminder_level: 提醒级别（medium/strong）
            is_admin: 是否通知管理员
            contract_name: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        level_icons = {
            "medium": "⚠️",
            "strong": "🚨"
        }
        level_texts = {
            "medium": "中度催办",
            "strong": "强度告警"
        }

        icon = level_icons.get(reminder_level, "⚠️")
        level_text = level_texts.get(reminder_level, "告警")

        entity_type, entity_name, _ = _resolve_entity(
            entity_type, entity_name, None, contract_name, None
        )
        label = _entity_label(entity_type)

        if is_admin:
            title = f"{icon} 审批超时告警（管理员）"
            content = f"""审批任务超时告警

**{label}名称**: {entity_name}
**当前节点**: {node_name}
**当前审批人**: {approver_name}
**已等待**: {waiting_hours}小时

作为管理员，请关注此审批进度，必要时介入处理。"""
        else:
            title = f"{icon} 您的审批任务等待超时"
            content = f"""您的审批任务等待超时

**{label}名称**: {entity_name}
**当前节点**: {node_name}
**当前审批人**: {approver_name}
**已等待**: {waiting_hours}小时

您可以选择：
→ 联系审批人催办
→ 撤回审批，修改后重新提交"""

        return await self.send_message_card(user_id, title, content)

    async def notify_approval_timeout_webhook(
        self,
        webhook_url: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        node_name: str = "",
        approver_name: str = "",
        waiting_hours: int = 0,
        business_id: Optional[int] = None,
        reminder_level: str = "medium",
        is_admin: bool = False,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """通过 Webhook 发送审批超时告警

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            webhook_url: 飞书群聊机器人 Webhook URL
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            node_name: 当前审批节点名称
            approver_name: 当前审批人姓名
            waiting_hours: 已等待小时数
            business_id: 业务单据ID
            reminder_level: 提醒级别（medium/strong）
            is_admin: 是否通知管理员
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        level_icons = {
            "medium": "⚠️",
            "strong": "🚨"
        }
        level_texts = {
            "medium": "中度催办",
            "strong": "强度告警"
        }

        icon = level_icons.get(reminder_level, "⚠️")
        level_text = level_texts.get(reminder_level, "告警")

        entity_type, entity_name, business_id = _resolve_entity(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        label = _entity_label(entity_type)

        if is_admin:
            title = f"{icon} 审批超时告警（管理员 - {level_text}）"
            content = f"""审批任务超时告警，请管理员关注

**{label}名称**: {entity_name}
**当前节点**: {node_name}
**当前审批人**: {approver_name}
**已等待**: {waiting_hours}小时

作为管理员，请关注此审批进度，必要时介入处理。"""
        else:
            title = f"{icon} 审批超时通知（{level_text}）"
            content = f"""审批任务等待超时

**{label}名称**: {entity_name}
**当前节点**: {node_name}
**当前审批人**: {approver_name}
**已等待**: {waiting_hours}小时

提交人可以选择：
→ 联系审批人催办
→ 撤回审批，修改后重新提交"""

        button_url = self._entity_detail_url(entity_type, business_id)

        return await self.send_webhook_message(webhook_url, title, content, button_url)


feishu_service = FeishuService()

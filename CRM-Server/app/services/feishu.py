import httpx
from typing import Optional, Dict, Any
from app.core.config import get_settings
from app.schemas.user import FeishuTokenResponse, FeishuUserInfo

settings = get_settings()


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
        contract_name: str,
        flow_name: str,
        node_name: str
    ) -> bool:
        title = "📋 新的合同审批待处理"
        content = f"""您有一个新的合同审批需要处理

**合同名称**: {contract_name}
**审批流程**: {flow_name}
**当前节点**: {node_name}

请及时处理，避免影响业务进度。"""
        
        return await self.send_message_card(user_id, title, content)
    
    async def notify_approval_approved(
        self,
        user_id: str,
        contract_name: str
    ) -> bool:
        title = "✅ 合同审批已通过"
        content = f"""您的合同审批已全部通过

**合同名称**: {contract_name}

合同状态已更新为"已签署"，可以进行后续操作。"""
        
        return await self.send_message_card(user_id, title, content)
    
    async def notify_approval_rejected(
        self,
        user_id: str,
        contract_name: str,
        reject_reason: str
    ) -> bool:
        title = "❌ 合同审批被拒绝"
        content = f"""您的合同审批被拒绝

**合同名称**: {contract_name}
**拒绝原因**: {reject_reason}

请根据审批意见修改后重新提交。"""
        
        return await self.send_message_card(user_id, title, content)


feishu_service = FeishuService()

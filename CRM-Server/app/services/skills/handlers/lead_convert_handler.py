"""
线索转化 Handler

执行线索转化为客户的完整业务流程：
1. 创建客户（从线索数据）
2. 创建主联系人
3. 迁移跟进记录
4. 更新线索状态为 CONVERTED

支持名称查找和 ID 查找
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.services.skills.handlers.status_change_handler import StatusChangeHandler
from app.crud.customer import customer_crud
from app.models.lead import Lead, LeadStatus


class LeadConvertHandler(StatusChangeHandler):
    """线索转化 Handler"""

    handler_type = "LeadConvertHandler"

    async def execute(
        self,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行线索转化操作

        handler_config 结构（继承 StatusChangeHandler，增加转化配置）:
        {
            "crud_mapping": "lead",
            "status_field": "status",
            "target_status": "CONVERTED",
            "exclude_status": ["CONVERTED", "INVALID"],
            "name_lookup_field": "lead_name",
            "name_field": "lead_name",
            "result_template": "线索转化成功..."
        }
        """
        # 查找线索（复用 StatusChangeHandler 的查找逻辑）
        crud_mapping_name = handler_config.get("crud_mapping", "lead")
        name_lookup_field = handler_config.get("name_lookup_field")
        name_field = handler_config.get("name_field", "lead_name")

        # 获取排除状态
        exclude_status_keys = handler_config.get("exclude_status", ["CONVERTED", "INVALID"])
        exclude_status_values = self.get_status_enum_values(db, "lead_status", exclude_status_keys) if exclude_status_keys else []

        # 尝试通过名称查找
        lead = None
        lead_id = None

        if name_lookup_field and name_field:
            name_lookup_value = params.get(name_lookup_field)
            if name_lookup_value:
                try:
                    _, entities = self.search_active_entities(
                        db,
                        Lead,
                        name_field,
                        name_lookup_value,
                        exclude_status=exclude_status_values,
                        status_field="status"
                    )
                except Exception as e:
                    return self.build_result(False, f"查询失败: {str(e)}")

                if not entities:
                    return self.build_result(False, f"未找到可转化的线索: {name_lookup_value}")

                if len(entities) > 1:
                    # 显示更多信息帮助用户区分
                    entity_list = []
                    for e in entities[:5]:
                        entity_name = getattr(e, name_field)
                        entity_status = e.status.name if hasattr(e.status, 'name') else str(e.status)
                        created_time = getattr(e, 'created_time', None)
                        time_str = created_time.strftime('%Y-%m-%d') if created_time else '未知'
                        entity_list.append(f"{entity_name}(ID:{e.id}, 状态:{entity_status}, 创建:{time_str})")
                    return self.build_result(
                        False,
                        f"找到多个匹配的线索，请使用 ID 或更精确的名称指定。匹配结果:\n{chr(10).join(entity_list)}"
                    )

                lead = entities[0]
                lead_id = lead.id

        # 如果名称查找失败，从参数获取 ID
        if not lead_id:
            for key in ["lead_id", "entity_id", "id"]:
                if key in params:
                    lead_id = params.get(key)
                    break

        if not lead_id:
            return self.build_result(False, "缺少参数: lead_id 或 lead_name")

        # 通过 ID 获取线索
        if not lead:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()

        if not lead:
            return self.build_result(False, f"线索 ID {lead_id} 不存在")

        # 检查线索状态
        if lead.status in exclude_status_values:
            status_str = lead.status.name if hasattr(lead.status, 'name') else str(lead.status)
            return self.build_result(False, f"线索 ID {lead_id} 状态为 {status_str}，无法转化")

        # 获取用户信息
        from app.crud.user import user_crud
        user = user_crud.get_by_id(db, user_id)
        operator_id = str(user.id) if user else user_feishu_open_id or "system"
        operator_name = user.name if user else None

        # 执行转化业务逻辑
        try:
            customer, contact = customer_crud.convert_from_lead(
                db=db,
                lead_id=lead_id,
                account_name=None,  # 使用线索名称
                industry=None,
                address=None,
                creator_id=operator_id,
                operator_name=operator_name
            )
        except ValueError as e:
            return self.build_result(False, str(e))
        except Exception as e:
            db.rollback()
            return self.build_result(False, f"转化失败: {str(e)}")

        # 构建结果
        result_template = handler_config.get(
            "result_template",
            "线索转化成功\n线索：{lead_name}\n已转化为客户"
        )

        message = result_template.format(
            lead_name=lead.lead_name,
            customer_name=customer.account_name,
            contact_name=contact.name,
            customer_id=customer.id
        )

        return self.build_result(True, message, {
            "lead": lead,
            "customer": customer,
            "contact": contact
        })
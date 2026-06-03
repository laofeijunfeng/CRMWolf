"""
设置采购方式 Handler

为未设置采购方式的商机设置采购方式，自动进入默认起始阶段
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class SetProcurementMethodHandler(BaseHandler):
    """设置采购方式 Handler"""

    handler_type = "SetProcurementMethodHandler"

    # 默认排除的状态（已完成状态的商机不应设置采购方式）
    DEFAULT_EXCLUDE_STATUS = ["WON", "LOST"]

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
        执行设置采购方式

        handler_config 结构:
        {
            "crud_mapping": "opportunity",
            "name_lookup_field": "opportunity_name",
            "name_field": "opportunity_name",
            "method_lookup_field": "procurement_method_name",
            "exclude_status": ["WON", "LOST"],
            "require_no_method": true,  // 要求商机未设置采购方式
            "customer_lookup": {...},
            "result_template": "..."
        }
        """
        # 获取用户信息
        user = user_crud.get_by_id(db, user_id)
        if not user:
            return self.build_result(False, "用户不存在")

        # 查找商机
        opportunity, error = self.find_opportunity(db, params, handler_config)
        if error:
            return error

        # 检查商机状态
        exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)
        exclude_status_values = self.get_opportunity_status_values(db, exclude_status_keys)

        if opportunity.status in exclude_status_values:
            status_text = self.get_status_text(opportunity.status)
            return self.build_result(
                False,
                f"商机「{opportunity.opportunity_name}」当前状态为「{status_text}」，已完成销售流程，无需设置采购方式"
            )

        # 检查是否已设置采购方式
        if opportunity.procurement_method_id:
            current_method = self.get_procurement_method(db, opportunity.procurement_method_id)
            if current_method:
                return self.build_result(
                    False,
                    f"商机「{opportunity.opportunity_name}」已设置采购方式为「{current_method.name}」，无法重复设置"
                )

        # 获取采购方式名称
        method_lookup_field = handler_config.get("method_lookup_field", "procurement_method_name")
        method_name = params.get(method_lookup_field)

        if not method_name:
            # 列出可用采购方式
            return self.list_procurement_methods(db, opportunity, handler_config)

        # 匹配采购方式
        method = self.match_procurement_method(db, method_name)
        if not method:
            return self.list_procurement_methods(db, opportunity, handler_config, method_name)

        # 获取默认起始阶段
        from app.crud.procurement import procurement_stage_template_crud
        default_stage = procurement_stage_template_crud.get_default_stage(db, method.id)

        if not default_stage:
            return self.build_result(
                False,
                f"采购方式「{method.name}」未设置默认起始阶段，请联系管理员配置"
            )

        # 设置采购方式
        try:
            from app.crud.opportunity import opportunity_crud
            updated = opportunity_crud.set_procurement_method(
                db, opportunity.id, method.id, str(user.id)
            )
        except Exception as e:
            return self.build_result(False, f"设置采购方式失败：{str(e)}")

        # 获取当前阶段信息
        current_stage = updated.current_stage_snapshot

        # 构建结果
        result_template = handler_config.get(
            "result_template",
            "商机「{opportunity_name}」已设置采购方式为「{method_name}」\n\n"
            "当前阶段：{current_stage}（赢率 {win_probability}%）\n"
            "进入时间：{enter_time}"
        )

        # 获取阶段数量
        stages = procurement_stage_template_crud.get_by_method(db, method.id)

        # 构建可推进阶段提示
        available_stages = []
        for stage in stages:
            if stage.sort_order > default_stage.sort_order:
                available_stages.append(f"  → {stage.stage_name}（赢率 {stage.win_probability}%）")

        stage_hint = ""
        if available_stages:
            stage_hint = "\n\n可推进阶段：\n" + "\n".join(available_stages[:5])
            if len(available_stages) > 5:
                stage_hint += f"\n  ... 等 {len(available_stages)} 个阶段"

        template_data = {
            "opportunity_name": opportunity.opportunity_name,
            "method_name": method.name,
            "current_stage": current_stage.stage_name if current_stage else default_stage.stage_name,
            "win_probability": current_stage.win_probability if current_stage else default_stage.win_probability,
            "enter_time": self.format_datetime(datetime.now()),
            "stage_hint": stage_hint
        }

        message = result_template.format(**template_data) + stage_hint

        return self.build_result(True, message, {
            "procurement_method_id": method.id,
            "procurement_method_name": method.name,
            "current_stage": default_stage.stage_name,
            "win_probability": default_stage.win_probability
        })

    def list_procurement_methods(
        self,
        db: Session,
        opportunity: Any,
        handler_config: Dict[str, Any],
        invalid_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """列出可用采购方式"""
        from app.crud.procurement import procurement_method_crud, procurement_stage_template_crud

        methods, _ = procurement_method_crud.get_multi(db, is_active=1, limit=10)

        if not methods:
            return self.build_result(False, "暂无可用的采购方式，请联系管理员配置")

        method_list = []
        for i, method in enumerate(methods, 1):
            stages = procurement_stage_template_crud.get_by_method(db, method.id)
            default_stage = procurement_stage_template_crud.get_default_stage(db, method.id)
            default_info = ""
            if default_stage:
                default_info = f"，默认起始：{default_stage.stage_name}（赢率 {default_stage.win_probability}%）"
            method_list.append(f"{i}. {method.name}（{len(stages)} 个阶段{default_info}）")

        prefix = ""
        if invalid_name:
            prefix = f"未找到采购方式「{invalid_name}」\n\n"

        return self.build_result(
            False,
            f"{prefix}商机「{opportunity.opportunity_name}」请设置采购方式，可用选项：\n\n" + "\n".join(method_list) + "\n\n"
            f"💡 设置方式示例：「{opportunity.opportunity_name}设置为公开招标」"
        )

    def find_opportunity(
        self,
        db: Session,
        params: Dict[str, Any],
        handler_config: Dict[str, Any]
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        """查找商机（支持 ID、商机名称、客户名称）"""
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud
        from app.crud.opportunity import opportunity_crud
        from app.models.opportunity import Opportunity

        crud_mapping_name = handler_config.get("crud_mapping", "opportunity")
        crud_mapping = ai_crud_mapping_crud.get_by_name(db, crud_mapping_name)
        if not crud_mapping:
            return None, self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        name_field = handler_config.get("name_field", crud_mapping.name_field)
        name_lookup_field = handler_config.get("name_lookup_field", "opportunity_name")

        # 尝试通过 ID 获取
        opportunity = None
        for key in ["opportunity_id", "id", "entity_id"]:
            if key in params:
                entity_id = params.get(key)
                opportunity = opportunity_crud.get_by_id(db, entity_id)
                break

        # 尝试通过商机名称查找
        if not opportunity:
            name_value = params.get(name_lookup_field)
            if name_value:
                name_attr = getattr(Opportunity, name_field)
                opportunities = db.query(Opportunity).filter(
                    name_attr.like(f"%{name_value}%")
                ).all()

                if not opportunities:
                    return None, self.build_result(False, f"未找到匹配的商机：{name_value}")

                if len(opportunities) > 1:
                    opp_list = []
                    for opp in opportunities[:5]:
                        status_text = self.get_status_text(opp.status)
                        method_text = "未设置" if not opp.procurement_method_id else "已设置"
                        opp_list.append(
                            f"  - {opp.opportunity_name}（ID: {opp.id}，{status_text}，采购方式：{method_text}）"
                        )
                    return None, self.build_result(
                        False,
                        f"找到多个匹配的商机，请指定具体商机：\n" + "\n".join(opp_list)
                    )

                opportunity = opportunities[0]

        # 尝试通过客户名称查找
        if not opportunity:
            customer_lookup = handler_config.get("customer_lookup")
            if customer_lookup:
                customer_name = params.get(customer_lookup.get("customer_lookup_field", "customer_name"))
                if customer_name:
                    return self.find_opportunity_by_customer(db, customer_name, handler_config)

        if not opportunity:
            return None, self.build_result(
                False,
                f"缺少参数：请提供商机 ID、商机名称或客户名称"
            )

        return opportunity, None

    def find_opportunity_by_customer(
        self,
        db: Session,
        customer_name: str,
        handler_config: Dict[str, Any]
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        """通过客户名称查找商机"""
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity

        customer_lookup = handler_config.get("customer_lookup", {})
        customer_name_field = customer_lookup.get("customer_name_field", "account_name")

        # 查找客户
        name_attr = getattr(Customer, customer_name_field)
        customers = db.query(Customer).filter(
            name_attr.like(f"%{customer_name}%")
        ).all()

        if not customers:
            return None, self.build_result(False, f"未找到匹配的客户：{customer_name}")

        if len(customers) > 1:
            cust_list = [f"  - {c.account_name}（ID: {c.id})" for c in customers[:5]]
            return None, self.build_result(
                False,
                f"找到多个匹配的客户，请指定具体客户：\n" + "\n".join(cust_list)
            )

        customer = customers[0]

        # 查找该客户下未设置采购方式的商机
        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.procurement_method_id == None,
            Opportunity.status == 0
        ).all()

        if not opportunities:
            # 检查是否有已设置采购方式的商机
            all_opps = db.query(Opportunity).filter(
                Opportunity.customer_id == customer.id,
                Opportunity.status == 0
            ).all()
            if all_opps:
                opp_list = [f"  - {opp.opportunity_name}（已设置采购方式）" for opp in all_opps[:5]]
                return None, self.build_result(
                    False,
                    f"客户「{customer.account_name}」下的商机均已设置采购方式：\n" + "\n".join(opp_list)
                )
            else:
                return None, self.build_result(
                    False,
                    f"客户「{customer.account_name}」暂无跟进中的商机"
                )

        if len(opportunities) > 1:
            opp_list = []
            for opp in opportunities:
                opp_list.append(
                    f"  {len(opp_list) + 1}. {opp.opportunity_name}（未设置采购方式）"
                )
            return None, self.build_result(
                False,
                f"客户「{customer.account_name}」下有以下未设置采购方式的商机：\n\n" + "\n".join(opp_list) + "\n\n请指定具体商机名称或 ID 进行设置"
            )

        return opportunities[0], None

    def get_procurement_method(self, db: Session, method_id: int) -> Optional[Any]:
        """获取采购方式"""
        from app.crud.procurement import procurement_method_crud
        return procurement_method_crud.get(db, method_id)

    def match_procurement_method(self, db: Session, name: str) -> Optional[Any]:
        """模糊匹配采购方式"""
        from app.crud.procurement import procurement_method_crud

        methods, _ = procurement_method_crud.get_multi(db, is_active=1, limit=100)

        name_lower = name.lower()

        # 精确匹配
        for method in methods:
            if method.name.lower() == name_lower:
                return method
            if method.code.lower() == name_lower:
                return method

        # 包含匹配
        for method in methods:
            if name_lower in method.name.lower():
                return method

        return None

    def get_opportunity_status_values(self, db: Session, status_keys: List[str]) -> List[int]:
        """获取商机状态枚举值"""
        from app.models.opportunity import OpportunityStatus

        values = []
        for key in status_keys:
            try:
                enum_value = getattr(OpportunityStatus, key)
                values.append(enum_value.value if hasattr(enum_value, 'value') else enum_value)
            except AttributeError:
                continue

        return values

    def get_status_text(self, status: int) -> str:
        """获取状态文本"""
        status_map = {0: "跟进中", 1: "已赢单", 2: "已输单"}
        return status_map.get(status, "未知")
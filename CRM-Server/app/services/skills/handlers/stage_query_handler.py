"""
阶段查询 Handler

查询商机阶段相关信息：
- 当前阶段 + 可推进阶段列表
- 阶段推进历史
- 可用采购方式列表

硬编码版：不再依赖数据库获取 CRUD/Enum 映射配置
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class StageQueryHandler(BaseHandler):
    """阶段查询 Handler"""

    handler_type = "StageQueryHandler"

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
        执行阶段查询

        handler_config 结构:
        {
            "crud_mapping": "opportunity",
            "name_lookup_field": "opportunity_name",
            "name_field": "opportunity_name",
            "query_type": "current",  // current | history | methods
            "customer_lookup": {...},  // 可选，客户名称查找配置
            "result_template": "..."
        }
        """
        query_type = handler_config.get("query_type", "current")

        if query_type == "methods":
            # 查询可用采购方式（无需指定商机）
            return self.query_procurement_methods(db, handler_config)

        # 查找商机
        opportunity, error = self.find_opportunity(db, params, handler_config)
        if error:
            return error

        if query_type == "current":
            return self.query_current_stage(db, opportunity, handler_config)
        elif query_type == "history":
            return self.query_stage_history(db, opportunity, handler_config)

        return self.build_result(False, f"未知的查询类型: {query_type}")

    def query_procurement_methods(
        self,
        db: Session,
        handler_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """查询所有可用的采购方式"""
        from app.crud.procurement import procurement_method_crud

        methods, total = procurement_method_crud.get_multi(
            db, is_active=1, limit=100
        )

        if not methods:
            return self.build_result(False, "暂无可用的采购方式")

        method_list = []
        for i, method in enumerate(methods, 1):
            # 获取该采购方式的阶段数量
            from app.crud.procurement import procurement_stage_template_crud
            stages = procurement_stage_template_crud.get_by_method(db, method.id)
            stage_count = len(stages)
            method_list.append(f"{i}. {method.name}（{stage_count} 个阶段）")

        result = "可用采购方式列表：\n" + "\n".join(method_list)
        return self.build_result(True, result, {"methods": methods})

    def query_current_stage(
        self,
        db: Session,
        opportunity: Any,
        handler_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """查询当前阶段和可推进阶段"""
        from app.crud.procurement import (
            procurement_stage_template_crud,
            opportunity_stage_snapshot_crud
        )

        # 检查是否设置了采购方式
        if not opportunity.procurement_method_id:
            # 返回提示，引导用户设置采购方式
            from app.crud.procurement import procurement_method_crud
            methods, _ = procurement_method_crud.get_multi(db, is_active=1, limit=5)
            method_names = [m.name for m in methods]

            return self.build_result(
                False,
                f"商机「{opportunity.opportunity_name}」未设置采购方式，无法查看阶段信息。\n\n"
                f"请先设置采购方式，可用选项：\n" + "\n".join([f"  - {m}" for m in method_names])
            )

        # 获取当前阶段快照
        current_snapshot = opportunity_stage_snapshot_crud.get_current(
            db, opportunity.id
        )

        if not current_snapshot:
            return self.build_result(
                False,
                f"商机「{opportunity.opportunity_name}」尚未进入任何阶段"
            )

        # 获取所有阶段模板
        stages = procurement_stage_template_crud.get_by_method(
            db, opportunity.procurement_method_id
        )

        # 计算在当前阶段停留天数
        days_in_stage = 0
        if current_snapshot.entered_at:
            days_in_stage = (datetime.now() - current_snapshot.entered_at).days

        # 构建可推进阶段列表
        available_stages = []
        for stage in stages:
            if stage.sort_order > current_snapshot.template_sort_order:
                auto_won_note = ""
                if stage.win_probability == 100:
                    auto_won_note = "（推进后自动标记赢单）"
                available_stages.append(
                    f"  → {stage.stage_name}（赢率 {stage.win_probability}%）{auto_won_note}"
                )

        # 构建结果
        result_lines = [
            f"商机「{opportunity.opportunity_name}」当前阶段信息：",
            "",
            f"当前阶段：{current_snapshot.stage_name}（赢率 {current_snapshot.win_probability}%）",
            f"进入时间：{self.format_datetime(current_snapshot.entered_at)}",
            f"停留时长：{days_in_stage} 天",
            "",
        ]

        if available_stages:
            result_lines.append("可推进阶段：")
            result_lines.extend(available_stages)
        else:
            result_lines.append("✅ 商机已在最后阶段，无需继续推进")

        # 添加历史推进提示
        result_lines.append("")
        result_lines.append(f"💡 查看阶段推进历史：输入「{opportunity.opportunity_name}阶段历史」")

        return self.build_result(
            True,
            "\n".join(result_lines),
            {
                "current_stage": current_snapshot.stage_name,
                "current_win_probability": current_snapshot.win_probability,
                "days_in_stage": days_in_stage,
                "available_stages_count": len(available_stages)
            }
        )

    def query_stage_history(
        self,
        db: Session,
        opportunity: Any,
        handler_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """查询阶段推进历史"""
        from app.crud.procurement import opportunity_stage_snapshot_crud

        history = opportunity_stage_snapshot_crud.get_history(db, opportunity.id)

        if not history:
            return self.build_result(
                False,
                f"商机「{opportunity.opportunity_name}」暂无阶段推进历史"
            )

        history_lines = [
            f"商机「{opportunity.opportunity_name}」阶段推进历史：",
            ""
        ]

        for i, snapshot in enumerate(history, 1):
            status = "当前阶段" if snapshot.exited_at is None else "已完成"

            duration = ""
            if snapshot.entered_at and snapshot.exited_at:
                days = (snapshot.exited_at - snapshot.entered_at).days
                duration = f"，停留 {days} 天"
            elif snapshot.entered_at and snapshot.exited_at is None:
                days = (datetime.now() - snapshot.entered_at).days
                duration = f"，已停留 {days} 天"

            history_lines.append(
                f"{i}. {snapshot.stage_name}（赢率 {snapshot.win_probability}%）- {status}{duration}"
            )
            history_lines.append(f"   进入：{self.format_datetime(snapshot.entered_at)}")
            if snapshot.exited_at:
                history_lines.append(f"   退出：{self.format_datetime(snapshot.exited_at)}")

        return self.build_result(
            True,
            "\n".join(history_lines),
            {"history_count": len(history)}
        )

    def find_opportunity(
        self,
        db: Session,
        params: Dict[str, Any],
        handler_config: Dict[str, Any]
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        """
        查找商机（支持 ID、商机名称、客户名称查找）

        硬编码版：不再依赖数据库获取 CRUD 映射

        Returns:
            (opportunity, error_result) - 成功时 error_result 为 None
        """
        from app.crud.opportunity import opportunity_crud

        crud_mapping_name = handler_config.get("crud_mapping", "opportunity")
        crud_config = self.get_crud_mapping(crud_mapping_name)
        if not crud_config:
            return None, self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        name_field = handler_config.get("name_field", crud_config.get("name_field"))
        name_lookup_field = handler_config.get("name_lookup_field", "opportunity_name")

        # 从配置直接获取 Model 类
        model_class = crud_config["model"]

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
                name_attr = getattr(model_class, name_field)
                opportunities = db.query(model_class).filter(
                    name_attr.like(f"%{name_value}%")
                ).all()

                if not opportunities:
                    return None, self.build_result(
                        False,
                        f"未找到匹配的商机：{name_value}"
                    )

                if len(opportunities) > 1:
                    opp_list = []
                    for opp in opportunities[:5]:
                        opp_list.append(
                            f"  - {opp.opportunity_name}（ID: {opp.id}，状态: {self.get_status_text(opp.status)}）"
                        )
                    return None, self.build_result(
                        False,
                        f"找到多个匹配的商机，请使用 ID 或更精确的名称指定：\n" + "\n".join(opp_list)
                    )

                opportunity = opportunities[0]

        # 尝试通过客户名称查找（如果配置了 customer_lookup）
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

        # 查找该客户下跟进中的商机
        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.status == 0  # 跟进中
        ).all()

        if not opportunities:
            return None, self.build_result(
                False,
                f"客户「{customer.account_name}」暂无跟进中的商机"
            )

        if len(opportunities) > 1:
            opp_list = []
            for opp in opportunities:
                stage_name = opp.current_stage_name or "未设置阶段"
                win_prob = opp.current_win_probability or 0
                opp_list.append(
                    f"  {len(opp_list) + 1}. {opp.opportunity_name}\n     当前阶段：{stage_name}（赢率 {win_prob}%）"
                )

            return None, self.build_result(
                False,
                f"客户「{customer.account_name}」下有以下跟进中的商机：\n\n" + "\n".join(opp_list) + "\n\n请指定具体商机名称或 ID 进行操作"
            )

        return opportunities[0], None

    def get_status_text(self, status: int) -> str:
        """获取状态文本"""
        status_map = {0: "跟进中", 1: "已赢单", 2: "已输单"}
        return status_map.get(status, "未知")
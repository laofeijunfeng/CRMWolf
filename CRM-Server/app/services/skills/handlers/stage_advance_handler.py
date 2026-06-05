"""
阶段推进/回退 Handler

处理商机阶段推进和回退操作

支持从名称中提取 ID（格式：名称（ID：xxx）或 名称(ID:xxx)）
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import re

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class StageAdvanceHandler(BaseHandler):
    """阶段推进/回退 Handler"""

    handler_type = "StageAdvanceHandler"

    # 默认排除的状态（已完成状态的商机不应再推进阶段）
    DEFAULT_EXCLUDE_STATUS = ["WON", "LOST"]

    # 从名称中提取 ID 的正则表达式
    ID_PATTERN = re.compile(r'[（(]\s*ID[：:]\s*(\d+)\s*[）)]')

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
        执行阶段推进/回退

        handler_config 结构:
        {
            "crud_mapping": "opportunity",
            "name_lookup_field": "opportunity_name",
            "name_field": "opportunity_name",
            "stage_lookup_field": "target_stage_name",
            "advance_mode": "forward",  // forward | backward
            "default_action": "next",   // next | prev
            "exclude_status": ["WON", "LOST"],
            "support_notes": true,
            "validate_rollback_history": true,  // 回退时验证是否在历史中
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

        # 获取配置
        advance_mode = handler_config.get("advance_mode", "forward")
        stage_lookup_field = handler_config.get("stage_lookup_field", "target_stage_name")
        default_action = handler_config.get("default_action", "next")
        support_notes = handler_config.get("support_notes", False)
        notes = params.get("notes") if support_notes else None

        # 检查商机状态
        exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)
        exclude_status_values = self.get_opportunity_status_values(exclude_status_keys)

        if opportunity.status in exclude_status_values:
            status_text = self.get_status_text(opportunity.status)
            return self.build_result(
                False,
                f"商机「{opportunity.opportunity_name}」当前状态为「{status_text}」，已完成销售流程，无法继续推进阶段。\n\n"
                f"💡 如需查看阶段历史，可输入：「{opportunity.opportunity_name}阶段历史」"
            )

        # 检查是否设置了采购方式
        if not opportunity.procurement_method_id:
            return self.handle_no_procurement_method(db, opportunity, handler_config)

        # 获取当前阶段
        from app.crud.procurement import opportunity_stage_snapshot_crud
        current_snapshot = opportunity_stage_snapshot_crud.get_current(db, opportunity.id)

        if not current_snapshot:
            return self.build_result(
                False,
                f"商机「{opportunity.opportunity_name}」尚未进入任何阶段"
            )

        # 获取所有阶段模板
        from app.crud.procurement import procurement_stage_template_crud
        stages = procurement_stage_template_crud.get_by_method(
            db, opportunity.procurement_method_id
        )

        if not stages:
            return self.build_result(False, "该采购方式下暂无阶段模板")

        # 确定目标阶段
        target_stage_name = params.get(stage_lookup_field)

        if target_stage_name:
            target_stage = self.match_stage_by_name(stages, target_stage_name)
            if not target_stage:
                available_names = [s.stage_name for s in stages]
                return self.build_result(
                    False,
                    f"未找到匹配的阶段「{target_stage_name}」\n\n可用阶段：{', '.join(available_names)}"
                )
        else:
            # 自动取下一/上一阶段
            target_stage = self.get_adjacent_stage(
                stages, current_snapshot, advance_mode, default_action
            )

        if not target_stage:
            if advance_mode == "forward":
                return self.build_result(
                    False,
                    f"商机「{opportunity.opportunity_name}」已在最后阶段「{current_snapshot.stage_name}」，无法继续推进\n\n"
                    f"💡 当前赢率已达 {current_snapshot.win_probability}%"
                )
            else:
                return self.build_result(
                    False,
                    f"商机「{opportunity.opportunity_name}」已在起始阶段「{current_snapshot.stage_name}」，无法回退"
                )

        # 验证推进方向合规
        validation_error = self.validate_advance(
            current_snapshot, target_stage, advance_mode, stages, handler_config
        )
        if validation_error:
            return validation_error

        # 执行推进/回退
        previous_stage_name = current_snapshot.stage_name
        previous_win_prob = current_snapshot.win_probability

        try:
            from app.crud.opportunity import opportunity_crud
            updated = opportunity_crud.move_to_stage(
                db, opportunity.id, target_stage.id, str(user.id)
            )
        except Exception as e:
            return self.build_result(False, f"阶段推进失败：{str(e)}")

        # 构建结果
        result_template = handler_config.get("result_template", self.get_default_template(advance_mode))

        # 特殊提示
        status_note = ""
        if updated.status == 1:  # WON
            status_note = "\n\n🎉 商机已自动标记为「赢单」状态！\n💡 建议下一步：创建合同以锁定交易"
        elif advance_mode == "forward" and target_stage.win_probability == 100:
            # 将要推进到100%阶段的提示（但还没推进）
            pass  # move_to_stage 已自动处理

        template_data = {
            "opportunity_name": opportunity.opportunity_name,
            "previous_stage": previous_stage_name,
            "previous_win_probability": previous_win_prob,
            "current_stage": target_stage.stage_name,
            "win_probability": target_stage.win_probability,
            "notes": notes or "无",
            "status_note": status_note,
            "action": "推进" if advance_mode == "forward" else "回退",
            "time": self.format_datetime(datetime.now())
        }

        message = result_template.format(**template_data)

        return self.build_result(True, message, {
            "previous_stage": previous_stage_name,
            "target_stage": target_stage.stage_name,
            "win_probability": target_stage.win_probability,
            "auto_won": updated.status == 1
        })

    def handle_no_procurement_method(
        self,
        db: Session,
        opportunity: Any,
        handler_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理未设置采购方式的情况"""
        from app.crud.procurement import procurement_method_crud
        methods, _ = procurement_method_crud.get_multi(db, is_active=1, limit=10)

        if not methods:
            return self.build_result(False, "暂无可用的采购方式，请联系管理员配置")

        method_list = []
        for i, method in enumerate(methods, 1):
            from app.crud.procurement import procurement_stage_template_crud
            stages = procurement_stage_template_crud.get_by_method(db, method.id)
            method_list.append(f"{i}. {method.name}（{len(stages)} 个阶段）")

        return self.build_result(
            False,
            f"商机「{opportunity.opportunity_name}」未设置采购方式，无法推进阶段。\n\n"
            f"请先设置采购方式，可用选项：\n" + "\n".join(method_list) + "\n\n"
            f"💡 设置方式示例：「{opportunity.opportunity_name}设置为公开招标」"
        )

    def find_opportunity(
        self,
        db: Session,
        params: Dict[str, Any],
        handler_config: Dict[str, Any]
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        """
        查找商机（支持 ID、商机名称、客户名称）

        硬编码版：不再依赖数据库获取 CRUD 映射
        """
        from app.crud.opportunity import opportunity_crud
        from app.models.opportunity import Opportunity

        crud_mapping_name = handler_config.get("crud_mapping", "opportunity")
        crud_config = self.get_crud_mapping(crud_mapping_name)
        if not crud_config:
            return None, self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        name_field = handler_config.get("name_field", crud_config.get("name_field"))
        name_lookup_field = handler_config.get("name_lookup_field", "opportunity_name")

        # 尝试通过 ID 获取
        opportunity = None
        entity_id = None

        # 先从 params 中直接获取 ID
        for key in ["opportunity_id", "id", "entity_id"]:
            if key in params:
                entity_id = params.get(key)
                opportunity = opportunity_crud.get_by_id(db, entity_id)
                break

        # 尝试通过商机名称查找
        if not opportunity:
            name_value = params.get(name_lookup_field)
            if name_value:
                # 先尝试从名称中提取 ID
                id_match = self.ID_PATTERN.search(name_value)
                if id_match:
                    entity_id = int(id_match.group(1))
                    opportunity = opportunity_crud.get_by_id(db, entity_id)
                    if not opportunity:
                        return None, self.build_result(False, f"商机 ID {entity_id} 不存在")
                else:
                    # 没有 ID，使用名称模糊查找
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
                            stage_text = opp.current_stage_name or "未设置阶段"
                            opp_list.append(
                                f"  - {opp.opportunity_name}（ID: {opp.id}，{status_text}，{stage_text}）"
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

        # 查找该客户下跟进中的商机
        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.status == 0
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

    def match_stage_by_name(self, stages: List[Any], name: str) -> Optional[Any]:
        """模糊匹配阶段名称"""
        name_lower = name.lower()

        # 精确匹配优先
        for stage in stages:
            if stage.stage_name.lower() == name_lower:
                return stage

        # 包含匹配
        for stage in stages:
            if name_lower in stage.stage_name.lower():
                return stage

        # 关键词匹配（如"谈判"匹配"商务谈判阶段"）
        for stage in stages:
            # 提取阶段名称的核心关键词
            stage_keywords = stage.stage_name.replace("阶段", "").lower()
            if name_lower in stage_keywords:
                return stage

        return None

    def get_adjacent_stage(
        self,
        stages: List[Any],
        current_snapshot: Any,
        advance_mode: str,
        default_action: str
    ) -> Optional[Any]:
        """获取相邻阶段"""
        current_order = current_snapshot.template_sort_order

        if advance_mode == "forward" or default_action == "next":
            # 找下一个阶段
            for stage in stages:
                if stage.sort_order > current_order:
                    return stage
        else:
            # 找上一个阶段（回退）
            prev_stage = None
            for stage in stages:
                if stage.sort_order < current_order:
                    prev_stage = stage
                else:
                    break
            return prev_stage

        return None

    def validate_advance(
        self,
        current_snapshot: Any,
        target_stage: Any,
        advance_mode: str,
        stages: List[Any],
        handler_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """验证推进方向合规"""
        current_order = current_snapshot.template_sort_order
        target_order = target_stage.sort_order

        if advance_mode == "forward":
            # 推进：目标阶段顺序必须大于当前（或可跳过）
            if target_order < current_order:
                if not target_stage.can_skip:
                    return self.build_result(
                        False,
                        f"只能向前推进阶段\n当前阶段：{current_snapshot.stage_name}\n目标阶段：{target_stage.stage_name}"
                    )
        else:
            # 回退：需要验证是否在历史中
            if handler_config.get("validate_rollback_history"):
                # 一般只允许回退到已经过的阶段
                if target_order > current_order:
                    return self.build_result(
                        False,
                        f"只能回退到已经过的阶段\n当前阶段：{current_snapshot.stage_name}\n目标阶段：{target_stage.stage_name}（尚未经过）"
                    )

        return None

    def get_opportunity_status_values(self, status_keys: List[str]) -> List[int]:
        """获取商机状态枚举值（硬编码版）"""
        return self.get_status_enum_values("opportunity_status", status_keys)

    def get_status_text(self, status: int) -> str:
        """获取状态文本"""
        status_map = {0: "跟进中", 1: "已赢单", 2: "已输单"}
        return status_map.get(status, "未知")

    def get_default_template(self, advance_mode: str) -> str:
        """获取默认结果模板"""
        if advance_mode == "forward":
            return (
                "商机「{opportunity_name}」已从「{previous_stage}」推进到「{current_stage}」\n\n"
                "当前赢率：{win_probability}%（从 {previous_win_probability}% 提升）\n"
                "{action}时间：{time}\n"
                "{status_note}"
            )
        else:
            return (
                "商机「{opportunity_name}」已从「{previous_stage}」回退到「{current_stage}」\n\n"
                "当前赢率：{win_probability}%（从 {previous_win_probability}% 下降）\n"
                "{action}时间：{time}\n"
                "备注：{notes}"
            )
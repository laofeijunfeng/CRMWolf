"""
get_entity_context 工具 Handler

获取实体的完整上下文信息，用于 AI 决策

这是 ReAct Agent 架构的关键组件，让 AI 能够自主获取上下文并做出判断
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import re


class GetContextHandler:
    """上下文获取 Handler"""

    handler_type = "GetContextHandler"

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
        获取实体上下文

        Args:
            db: 数据库 Session
            handler_config: Handler 配置
            params: 包含 entity_type, entity_name
            user_id: 用户 ID
            user_feishu_open_id: 飞书 Open ID（可选）
            team_id: 团队 ID

        Returns:
            实体的完整上下文信息，包括：
            - 基本信息
            - 关联实体列表
            - 最近活动
            - 格式化文本（用于注入 AI 消息）
        """
        entity_type = params.get("entity_type")
        entity_name = params.get("entity_name")

        if not entity_type:
            return {
                "success": False,
                "message": "缺少实体类型参数"
            }

        if not team_id:
            return {
                "success": False,
                "message": "缺少团队 ID"
            }

        # 根据实体类型获取上下文
        context = self._get_context(db, entity_type, entity_name, team_id)

        if not context:
            return {
                "success": False,
                "message": f"未找到实体: {entity_name or entity_type}",
                "entity_type": entity_type
            }

        # 格式化上下文为 AI 可理解的文本
        context_text = self._format_context_for_ai(context, entity_type)

        return {
            "success": True,
            "action": "get_entity_context",
            "returns_context": True,  # 标记：返回上下文，应注入消息
            "context": context,
            "context_text": context_text,  # 用于注入 AI 消息
            "entity_type": entity_type,
            "entity_id": context.get("entity_id"),
            "message": f"已获取 {entity_type} 的上下文信息"
        }

    def _get_context(
        self,
        db: Session,
        entity_type: str,
        entity_name: Optional[str],
        team_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        获取实体上下文（核心逻辑）

        Args:
            db: 数据库 Session
            entity_type: 实体类型（customer, opportunity, contract, lead）
            entity_name: 实体名称（可选）
            team_id: 团队 ID

        Returns:
            上下文信息字典
        """
        entity_id = None

        # 尝试从名称中提取 ID
        if entity_name:
            match = self.ID_PATTERN.search(entity_name)
            if match:
                entity_id = int(match.group(1))

        context = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "basic_info": {},
            "related_entities": [],
            "recent_activities": []
        }

        # ==================== 客户上下文 ====================
        if entity_type == "customer":
            if entity_id:
                customer = db.execute(
                    text("SELECT * FROM crm_customers WHERE id = :id AND team_id = :team_id"),
                    {"id": entity_id, "team_id": team_id}
                ).fetchone()
            elif entity_name:
                customer = db.execute(
                    text("""
                        SELECT * FROM crm_customers
                        WHERE account_name LIKE :name AND team_id = :team_id
                        LIMIT 1
                    """),
                    {"name": f"%{entity_name}%", "team_id": team_id}
                ).fetchone()
            else:
                return None

            if customer:
                mapping = customer._mapping if hasattr(customer, '_mapping') else {}
                context["entity_id"] = mapping.get("id")
                context["entity_name"] = mapping.get("account_name")  # Customer 模型用 account_name
                context["basic_info"] = {
                    "account_name": mapping.get("account_name"),
                    "status": self._status_to_text(mapping.get("status"), "customer"),
                    "industry": mapping.get("industry"),
                    "city": mapping.get("city"),
                    "owner_id": mapping.get("owner_id"),
                }

                # 商机列表（关键信息，用于 AI 判断是否有商机）
                opportunities = db.execute(
                    text("""
                        SELECT id, opportunity_name, status, total_amount,
                               current_stage_name, win_probability, created_time
                        FROM crm_opportunities
                        WHERE customer_id = :id AND team_id = :team_id
                        ORDER BY created_time DESC
                        LIMIT 10
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for opp in opportunities:
                    opp_map = opp._mapping if hasattr(opp, '_mapping') else {}
                    amount = opp_map.get("total_amount")
                    if amount is not None:
                        try:
                            amount = float(amount)
                        except:
                            amount = str(amount)

                    context["related_entities"].append({
                        "type": "opportunity",
                        "id": opp_map.get("id"),
                        "name": opp_map.get("opportunity_name"),
                        "status": self._status_to_text(opp_map.get("status"), "opportunity"),
                        "amount": amount,
                        "stage": opp_map.get("current_stage_name"),
                        "win_probability": opp_map.get("win_probability")
                    })

                # 最近跟进（用于 AI 了解沟通历史）
                follow_ups = db.execute(
                    text("""
                        SELECT id, content, method, created_time
                        FROM crm_customer_follow_ups
                        WHERE customer_id = :id AND team_id = :team_id
                        ORDER BY created_time DESC
                        LIMIT 5
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for fu in follow_ups:
                    fu_map = fu._mapping if hasattr(fu, '_mapping') else {}
                    context["recent_activities"].append({
                        "type": "follow_up",
                        "content": fu_map.get("content"),
                        "method": fu_map.get("method"),
                        "date": str(fu_map.get("created_time"))
                    })

                # 合同列表
                contracts = db.execute(
                    text("""
                        SELECT id, contract_name, status, total_amount
                        FROM crm_contracts
                        WHERE customer_id = :id AND team_id = :team_id
                        ORDER BY created_time DESC
                        LIMIT 5
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for con in contracts:
                    con_map = con._mapping if hasattr(con, '_mapping') else {}
                    context["related_entities"].append({
                        "type": "contract",
                        "id": con_map.get("id"),
                        "name": con_map.get("contract_name"),
                        "status": self._status_to_text(con_map.get("status"), "contract"),
                        "amount": con_map.get("total_amount")
                    })

        # ==================== 商机上下文 ====================
        elif entity_type == "opportunity":
            if entity_id:
                opp = db.execute(
                    text("SELECT * FROM crm_opportunities WHERE id = :id AND team_id = :team_id"),
                    {"id": entity_id, "team_id": team_id}
                ).fetchone()
            elif entity_name:
                opp = db.execute(
                    text("""
                        SELECT * FROM crm_opportunities
                        WHERE opportunity_name LIKE :name AND team_id = :team_id
                        LIMIT 1
                    """),
                    {"name": f"%{entity_name}%", "team_id": team_id}
                ).fetchone()
            else:
                return None

            if opp:
                mapping = opp._mapping if hasattr(opp, '_mapping') else {}
                context["entity_id"] = mapping.get("id")
                context["entity_name"] = mapping.get("opportunity_name")
                context["basic_info"] = {
                    "opportunity_name": mapping.get("opportunity_name"),
                    "status": self._status_to_text(mapping.get("status"), "opportunity"),
                    "total_amount": mapping.get("total_amount"),
                    "win_probability": mapping.get("win_probability"),
                    "current_stage": mapping.get("current_stage_name"),
                    "customer_id": mapping.get("customer_id"),
                    "user_count": mapping.get("user_count"),
                    "subscription_years": mapping.get("subscription_years"),
                }

                # 关联客户
                customer_id = mapping.get("customer_id")
                if customer_id:
                    customer = db.execute(
                        text("""
                            SELECT id, account_name, industry, status
                            FROM crm_customers WHERE id = :id
                        """),
                        {"id": customer_id}
                    ).fetchone()
                    if customer:
                        cm = customer._mapping if hasattr(customer, '_mapping') else {}
                        context["related_entities"].append({
                            "type": "customer",
                            "id": customer_id,
                            "name": cm.get("account_name"),
                            "industry": cm.get("industry"),
                            "status": self._status_to_text(cm.get("status"), "customer")
                        })

                # 关联合同
                contracts = db.execute(
                    text("""
                        SELECT id, contract_name, status, total_amount
                        FROM crm_contracts
                        WHERE opportunity_id = :id AND team_id = :team_id
                        ORDER BY created_time DESC
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for con in contracts:
                    con_map = con._mapping if hasattr(con, '_mapping') else {}
                    context["related_entities"].append({
                        "type": "contract",
                        "id": con_map.get("id"),
                        "name": con_map.get("contract_name"),
                        "status": self._status_to_text(con_map.get("status"), "contract"),
                        "amount": con_map.get("total_amount")
                    })

                # 回款计划
                plans = db.execute(
                    text("""
                        SELECT cp.id, cp.stage_name, cp.planned_amount, cp.status, cp.due_date
                        FROM crm_contract_payment_plans cp
                        JOIN crm_contracts c ON cp.contract_id = c.id
                        WHERE c.opportunity_id = :id AND c.team_id = :team_id
                        ORDER BY cp.due_date
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for plan in plans:
                    plan_map = plan._mapping if hasattr(plan, '_mapping') else {}
                    context["related_entities"].append({
                        "type": "payment_plan",
                        "id": plan_map.get("id"),
                        "name": plan_map.get("stage_name"),
                        "status": plan_map.get("status"),
                        "amount": plan_map.get("planned_amount")
                    })

        # ==================== 合同上下文 ====================
        elif entity_type == "contract":
            if entity_id:
                contract = db.execute(
                    text("SELECT * FROM crm_contracts WHERE id = :id AND team_id = :team_id"),
                    {"id": entity_id, "team_id": team_id}
                ).fetchone()
            elif entity_name:
                contract = db.execute(
                    text("""
                        SELECT * FROM crm_contracts
                        WHERE contract_name LIKE :name AND team_id = :team_id
                        LIMIT 1
                    """),
                    {"name": f"%{entity_name}%", "team_id": team_id}
                ).fetchone()
            else:
                return None

            if contract:
                mapping = contract._mapping if hasattr(contract, '_mapping') else {}
                context["entity_id"] = mapping.get("id")
                context["entity_name"] = mapping.get("contract_name")
                context["basic_info"] = {
                    "contract_name": mapping.get("contract_name"),
                    "status": self._status_to_text(mapping.get("status"), "contract"),
                    "total_amount": mapping.get("total_amount"),
                    "customer_id": mapping.get("customer_id"),
                    "opportunity_id": mapping.get("opportunity_id"),
                    "signing_date": mapping.get("signing_date"),
                    "effective_date": mapping.get("effective_date"),
                }

                # 回款计划
                plans = db.execute(
                    text("""
                        SELECT id, stage_name, planned_amount, status, due_date
                        FROM crm_contract_payment_plans
                        WHERE contract_id = :id AND team_id = :team_id
                        ORDER BY due_date
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for plan in plans:
                    plan_map = plan._mapping if hasattr(plan, '_mapping') else {}
                    context["related_entities"].append({
                        "type": "payment_plan",
                        "id": plan_map.get("id"),
                        "name": plan_map.get("stage_name"),
                        "status": plan_map.get("status"),
                        "amount": plan_map.get("planned_amount"),
                        "due_date": plan_map.get("due_date")
                    })

                # 回款记录
                records = db.execute(
                    text("""
                        SELECT pr.id, pr.actual_amount, pr.payment_date, pr.status
                        FROM crm_contract_payment_records pr
                        JOIN crm_contract_payment_plans pp ON pr.payment_plan_id = pp.id
                        WHERE pp.contract_id = :id AND pp.team_id = :team_id
                        ORDER BY pr.payment_date DESC
                        LIMIT 10
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for record in records:
                    rec_map = record._mapping if hasattr(record, '_mapping') else {}
                    context["recent_activities"].append({
                        "type": "payment_record",
                        "amount": rec_map.get("actual_amount"),
                        "date": str(rec_map.get("payment_date")),
                        "status": rec_map.get("status")
                    })

                # 发票申请
                invoices = db.execute(
                    text("""
                        SELECT ia.id, ia.invoice_amount, ia.status, ia.invoice_type
                        FROM crm_invoice_applications ia
                        JOIN crm_contract_payment_plans pp ON ia.payment_plan_id = pp.id
                        WHERE pp.contract_id = :id AND pp.team_id = :team_id
                        ORDER BY ia.created_time DESC
                        LIMIT 5
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for inv in invoices:
                    inv_map = inv._mapping if hasattr(inv, '_mapping') else {}
                    context["related_entities"].append({
                        "type": "invoice_application",
                        "id": inv_map.get("id"),
                        "amount": inv_map.get("invoice_amount"),
                        "status": inv_map.get("status"),
                        "invoice_type": inv_map.get("invoice_type")
                    })

        # ==================== 线索上下文 ====================
        elif entity_type == "lead":
            if entity_id:
                lead = db.execute(
                    text("SELECT * FROM crm_leads WHERE id = :id AND team_id = :team_id"),
                    {"id": entity_id, "team_id": team_id}
                ).fetchone()
            elif entity_name:
                lead = db.execute(
                    text("""
                        SELECT * FROM crm_leads
                        WHERE name LIKE :name AND team_id = :team_id
                        LIMIT 1
                    """),
                    {"name": f"%{entity_name}%", "team_id": team_id}
                ).fetchone()
            else:
                return None

            if lead:
                mapping = lead._mapping if hasattr(lead, '_mapping') else {}
                context["entity_id"] = mapping.get("id")
                context["entity_name"] = mapping.get("name")
                context["basic_info"] = {
                    "lead_name": mapping.get("name"),
                    "status": self._status_to_text(mapping.get("status"), "lead"),
                    "source": mapping.get("source"),
                    "city": mapping.get("city"),
                    "contact_phone": mapping.get("contact_phone"),
                    "contact_name": mapping.get("contact_name"),
                }

                # 最近跟进
                follow_ups = db.execute(
                    text("""
                        SELECT id, content, method, created_time
                        FROM crm_lead_follow_ups
                        WHERE lead_id = :id AND team_id = :team_id
                        ORDER BY created_time DESC
                        LIMIT 5
                    """),
                    {"id": context["entity_id"], "team_id": team_id}
                ).fetchall()

                for fu in follow_ups:
                    fu_map = fu._mapping if hasattr(fu, '_mapping') else {}
                    context["recent_activities"].append({
                        "type": "follow_up",
                        "content": fu_map.get("content"),
                        "method": fu_map.get("method"),
                        "date": str(fu_map.get("created_time"))
                    })

        return context

    def _format_context_for_ai(self, context: Dict[str, Any], entity_type: str) -> str:
        """
        将上下文格式化为 AI 可理解的文本

        Args:
            context: 上下文信息
            entity_type: 实体类型

        Returns:
            格式化文本，用于注入 AI 消息
        """
        # 实体类型映射
        type_map = {
            "customer": "客户",
            "opportunity": "商机",
            "contract": "合同",
            "lead": "线索"
        }

        entity_type_text = type_map.get(entity_type, entity_type)
        lines = []

        # 基本信息
        if context.get("basic_info"):
            lines.append(f"【{entity_type_text}基本信息】")
            for key, value in context["basic_info"].items():
                if value:
                    lines.append(f"  - {key}: {value}")

        # 关联实体（关键信息，帮助 AI 判断）
        if context.get("related_entities"):
            lines.append(f"\n【关联信息】")
            for entity in context["related_entities"]:
                type_text = type_map.get(entity["type"], entity["type"])
                info = f"  - {type_text}: {entity.get('name', '')}"
                if entity.get("status"):
                    info += f"(状态: {entity['status']})"
                if entity.get("amount"):
                    info += f"(金额: {entity['amount']})"
                lines.append(info)

        # 最近活动
        if context.get("recent_activities"):
            lines.append(f"\n【最近活动】")
            for activity in context["recent_activities"]:
                if activity["type"] == "follow_up":
                    lines.append(f"  - 跟进: {activity.get('content', '')}(方式: {activity.get('method', '')})")
                elif activity["type"] == "payment_record":
                    lines.append(f"  - 回款: {activity.get('amount')}元(日期: {activity.get('date')})")

        return "\n".join(lines)

    def _status_to_text(self, status: Any, entity_type: str) -> str:
        """
        将状态值转换为可读文本

        Args:
            status: 状态值（可能是枚举或整数）
            entity_type: 实体类型

        Returns:
            状态文本
        """
        if status is None:
            return "未知"

        # 如果是枚举，获取 value
        if hasattr(status, 'value'):
            status_value = status.value
        else:
            status_value = status

        # 状态映射表
        status_map = {
            "customer": {
                0: "跟进中",
                1: "已成交",
                2: "已流失",
                3: "非激活",
            },
            "opportunity": {
                0: "跟进中",
                1: "赢单",
                2: "输单",
            },
            "lead": {
                0: "新建",
                1: "跟进中",
                2: "已转化",
                3: "无效",
            },
            "contract": {
                0: "草稿",
                1: "待审核",
                2: "已签署",
                3: "生效中",
                4: "已到期",
                5: "已终止",
            }
        }

        mapping = status_map.get(entity_type, {})
        return mapping.get(status_value, str(status_value))
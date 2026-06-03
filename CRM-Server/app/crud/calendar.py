from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from app.models.lead import Lead, LeadFollowUp, LeadStatus
from app.models.customer import Customer, CustomerStatus
from app.models.customer_follow_up import CustomerFollowUp
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.payment import PaymentPlan, PaymentPlanStatus
from app.models.contract import Contract
from app.schemas.calendar import (
    TodoCount,
    LeadFollowUpTodo,
    CustomerFollowUpTodo,
    OpportunityTodo,
    PaymentPlanTodo,
)


class CalendarCRUD:
    def get_month_todos(self, db: Session, owner_id: str, team_id: int, year: int, month: int) -> Dict[str, TodoCount]:
        """
        获取指定月份每天的待办数量统计

        Args:
            db: 数据库会话
            owner_id: 当前用户ID（飞书用户ID）
            team_id: 团队ID
            year: 年份
            month: 月份

        Returns:
            Dict[str, TodoCount]: key为日期字符串(YYYY-MM-DD)，value为各类型待办数量
        """
        # 计算月份范围
        if month == 12:
            start_date = date(year, month, 1)
            end_date = date(year + 1, 1, 1)
        else:
            start_date = date(year, month, 1)
            end_date = date(year, month + 1, 1)

        result: Dict[str, TodoCount] = {}

        # 1. 线索跟进统计 - LeadFollowUp.next_follow_time
        # 筛选条件：Lead.owner_id = owner_id, Lead.status IN (NEW, FOLLOWING), Lead.team_id = team_id
        lead_follow_ups = db.query(
            func.date(LeadFollowUp.next_follow_time).label('todo_date'),
            func.count(LeadFollowUp.id).label('count')
        ).join(
            Lead, LeadFollowUp.lead_id == Lead.id
        ).filter(
            Lead.owner_id == owner_id,
            Lead.team_id == team_id,
            Lead.status.in_([LeadStatus.NEW, LeadStatus.FOLLOWING]),
            LeadFollowUp.next_follow_time >= start_date,
            LeadFollowUp.next_follow_time < end_date,
            LeadFollowUp.next_follow_time.isnot(None)
        ).group_by(
            func.date(LeadFollowUp.next_follow_time)
        ).all()

        for record in lead_follow_ups:
            date_str = str(record.todo_date)
            if date_str not in result:
                result[date_str] = TodoCount()
            result[date_str].lead = record.count

        # 2. 客户跟进统计 - CustomerFollowUp.next_follow_time
        # 筛选条件：Customer.owner_id = owner_id, Customer.status = FOLLOWING, Customer.team_id = team_id
        customer_follow_ups = db.query(
            func.date(CustomerFollowUp.next_follow_time).label('todo_date'),
            func.count(CustomerFollowUp.id).label('count')
        ).join(
            Customer, CustomerFollowUp.customer_id == Customer.id
        ).filter(
            Customer.owner_id == owner_id,
            Customer.team_id == team_id,
            Customer.status == CustomerStatus.FOLLOWING,
            CustomerFollowUp.next_follow_time >= start_date,
            CustomerFollowUp.next_follow_time < end_date,
            CustomerFollowUp.next_follow_time.isnot(None)
        ).group_by(
            func.date(CustomerFollowUp.next_follow_time)
        ).all()

        for record in customer_follow_ups:
            date_str = str(record.todo_date)
            if date_str not in result:
                result[date_str] = TodoCount()
            result[date_str].customer = record.count

        # 3. 商机跟进统计 - Opportunity.expected_closing_date
        # 筛选条件：Opportunity.owner_id = owner_id, status = FOLLOWING, team_id = team_id
        opportunities = db.query(
            Opportunity.expected_closing_date.label('todo_date'),
            func.count(Opportunity.id).label('count')
        ).filter(
            Opportunity.owner_id == owner_id,
            Opportunity.team_id == team_id,
            Opportunity.status == OpportunityStatus.FOLLOWING,
            Opportunity.expected_closing_date >= start_date,
            Opportunity.expected_closing_date < end_date
        ).group_by(
            Opportunity.expected_closing_date
        ).all()

        for record in opportunities:
            date_str = str(record.todo_date)
            if date_str not in result:
                result[date_str] = TodoCount()
            result[date_str].opportunity = record.count

        # 4. 回款计划统计 - PaymentPlan.due_date
        # 筛选条件：PaymentPlan.status = PENDING, Contract.creator_id = owner_id, Contract.team_id = team_id
        # 需要JOIN Contract 表获取 creator_id 和 team_id
        payment_plans = db.query(
            PaymentPlan.due_date.label('todo_date'),
            func.count(PaymentPlan.id).label('count')
        ).join(
            Contract, PaymentPlan.contract_id == Contract.id
        ).filter(
            Contract.creator_id == owner_id,
            Contract.team_id == team_id,
            PaymentPlan.status == PaymentPlanStatus.PENDING,
            PaymentPlan.due_date >= start_date,
            PaymentPlan.due_date < end_date
        ).group_by(
            PaymentPlan.due_date
        ).all()

        for record in payment_plans:
            date_str = str(record.todo_date)
            if date_str not in result:
                result[date_str] = TodoCount()
            result[date_str].payment = record.count

        # 计算总数
        for date_str in result:
            result[date_str].total = (
                result[date_str].lead +
                result[date_str].customer +
                result[date_str].opportunity +
                result[date_str].payment
            )

        return result

    def get_date_detail_todos(
        self,
        db: Session,
        owner_id: str,
        team_id: int,
        target_date: date
    ) -> tuple[List[LeadFollowUpTodo], List[CustomerFollowUpTodo], List[OpportunityTodo], List[PaymentPlanTodo]]:
        """
        获取指定日期的所有待办事项详情

        Args:
            db: 数据库会话
            owner_id: 当前用户ID
            team_id: 团队ID
            target_date: 目标日期

        Returns:
            tuple: 四种待办类型的详情列表
        """
        today = date.today()
        is_overdue = target_date < today

        # 1. 线索跟进详情 - 添加 team_id 过滤
        lead_follow_ups = db.query(
            LeadFollowUp.id,
            LeadFollowUp.lead_id,
            Lead.lead_name,
            Lead.contact_name,
            Lead.contact_phone,
            LeadFollowUp.next_action,
            LeadFollowUp.next_follow_time
        ).join(
            Lead, LeadFollowUp.lead_id == Lead.id
        ).filter(
            Lead.owner_id == owner_id,
            Lead.team_id == team_id,
            Lead.status.in_([LeadStatus.NEW, LeadStatus.FOLLOWING]),
            func.date(LeadFollowUp.next_follow_time) == target_date,
            LeadFollowUp.next_follow_time.isnot(None)
        ).all()

        lead_todos = [
            LeadFollowUpTodo(
                id=record.id,
                lead_id=record.lead_id,
                lead_name=record.lead_name,
                contact_name=record.contact_name,
                contact_phone=record.contact_phone,
                next_action=record.next_action,
                next_follow_time=record.next_follow_time,
                is_overdue=is_overdue
            )
            for record in lead_follow_ups
        ]

        # 2. 客户跟进详情 - 添加 team_id 过滤
        customer_follow_ups = db.query(
            CustomerFollowUp.id,
            CustomerFollowUp.customer_id,
            Customer.account_name,
            CustomerFollowUp.next_action,
            CustomerFollowUp.next_follow_time
        ).join(
            Customer, CustomerFollowUp.customer_id == Customer.id
        ).filter(
            Customer.owner_id == owner_id,
            Customer.team_id == team_id,
            Customer.status == CustomerStatus.FOLLOWING,
            func.date(CustomerFollowUp.next_follow_time) == target_date,
            CustomerFollowUp.next_follow_time.isnot(None)
        ).all()

        customer_todos = [
            CustomerFollowUpTodo(
                id=record.id,
                customer_id=record.customer_id,
                account_name=record.account_name,
                next_action=record.next_action,
                next_follow_time=record.next_follow_time,
                is_overdue=is_overdue
            )
            for record in customer_follow_ups
        ]

        # 3. 商机跟进详情 - 添加 team_id 过滤
        opportunities = db.query(
            Opportunity.id,
            Opportunity.opportunity_name,
            Customer.account_name.label('customer_name'),
            Opportunity.total_amount,
            Opportunity.expected_closing_date,
            Opportunity.current_stage_name
        ).join(
            Customer, Opportunity.customer_id == Customer.id
        ).filter(
            Opportunity.owner_id == owner_id,
            Opportunity.team_id == team_id,
            Opportunity.status == OpportunityStatus.FOLLOWING,
            Opportunity.expected_closing_date == target_date
        ).all()

        opportunity_todos = [
            OpportunityTodo(
                id=record.id,
                opportunity_name=record.opportunity_name,
                customer_name=record.customer_name,
                total_amount=float(record.total_amount),
                expected_closing_date=record.expected_closing_date,
                current_stage_name=record.current_stage_name,
                is_overdue=is_overdue
            )
            for record in opportunities
        ]

        # 4. 回款计划详情 - 添加 team_id 过滤
        payment_plans = db.query(
            PaymentPlan.id,
            PaymentPlan.contract_id,
            Contract.contract_name,
            Customer.account_name.label('customer_name'),
            PaymentPlan.stage_name,
            PaymentPlan.planned_amount,
            PaymentPlan.due_date
        ).join(
            Contract, PaymentPlan.contract_id == Contract.id
        ).join(
            Customer, Contract.customer_id == Customer.id
        ).filter(
            Contract.creator_id == owner_id,
            Contract.team_id == team_id,
            PaymentPlan.status == PaymentPlanStatus.PENDING,
            PaymentPlan.due_date == target_date
        ).all()

        payment_todos = [
            PaymentPlanTodo(
                id=record.id,
                contract_id=record.contract_id,
                contract_name=record.contract_name,
                customer_name=record.customer_name,
                stage_name=record.stage_name,
                planned_amount=float(record.planned_amount),
                due_date=record.due_date,
                is_overdue=is_overdue
            )
            for record in payment_plans
        ]

        return lead_todos, customer_todos, opportunity_todos, payment_todos

    def get_todo_context(
        self,
        db: Session,
        todo_type: str,
        todo_id: int,
        owner_id: str,
        team_id: int
    ) -> Optional[Dict]:
        """
        获取待办的上下文信息（用于 AI 跟进）

        Args:
            db: 数据库 Session
            todo_type: 待办类型 (lead_follow_up/customer_follow_up/opportunity/payment_plan)
            todo_id: 待办 ID
            owner_id: 当前用户 ID（飞书用户 ID）
            team_id: 团队 ID

        Returns:
            上下文数据字典，包含 entity_info, current_next_follow_time 等
        """
        if todo_type == "lead_follow_up":
            # LeadFollowUp 记录的 ID
            follow_up = db.query(LeadFollowUp).filter(
                LeadFollowUp.id == todo_id
            ).join(Lead).filter(
                Lead.owner_id == owner_id,
                Lead.team_id == team_id,
                Lead.status.in_([LeadStatus.NEW, LeadStatus.FOLLOWING])
            ).first()

            if not follow_up:
                return None

            return {
                "todo_type": todo_type,
                "todo_id": todo_id,
                "entity_type": "lead",
                "entity_id": follow_up.lead_id,
                "entity_info": {
                    "name": follow_up.lead.lead_name,
                    "contact_name": follow_up.lead.contact_name,
                    "contact_phone": follow_up.lead.contact_phone
                },
                "current_next_follow_time": follow_up.next_follow_time.strftime("%Y-%m-%d") if follow_up.next_follow_time else None,
                "current_next_action": follow_up.next_action
            }

        elif todo_type == "customer_follow_up":
            # CustomerFollowUp 记录的 ID
            follow_up = db.query(CustomerFollowUp).filter(
                CustomerFollowUp.id == todo_id
            ).join(Customer).filter(
                Customer.owner_id == owner_id,
                Customer.team_id == team_id,
                Customer.status == CustomerStatus.FOLLOWING
            ).first()

            if not follow_up:
                return None

            return {
                "todo_type": todo_type,
                "todo_id": todo_id,
                "entity_type": "customer",
                "entity_id": follow_up.customer_id,
                "entity_info": {
                    "name": follow_up.customer.account_name,
                    "contact_name": "",
                    "contact_phone": ""
                },
                "current_next_follow_time": follow_up.next_follow_time.strftime("%Y-%m-%d") if follow_up.next_follow_time else None,
                "current_next_action": follow_up.next_action
            }

        elif todo_type == "opportunity":
            # Opportunity 的 ID（expected_closing_date）
            opportunity = db.query(Opportunity).filter(
                Opportunity.id == todo_id,
                Opportunity.owner_id == owner_id,
                Opportunity.team_id == team_id,
                Opportunity.status == OpportunityStatus.FOLLOWING
            ).join(Customer).first()

            if not opportunity:
                return None

            return {
                "todo_type": todo_type,
                "todo_id": todo_id,
                "entity_type": "opportunity",
                "entity_id": opportunity.id,
                "entity_info": {
                    "name": opportunity.opportunity_name,
                    "customer_name": opportunity.customer.account_name,
                    "total_amount": float(opportunity.total_amount)
                },
                "current_next_follow_time": opportunity.expected_closing_date.strftime("%Y-%m-%d") if opportunity.expected_closing_date else None,
                "current_next_action": None
            }

        elif todo_type == "payment_plan":
            # PaymentPlan 的 ID（due_date）
            payment_plan = db.query(PaymentPlan).filter(
                PaymentPlan.id == todo_id,
                PaymentPlan.status == PaymentPlanStatus.PENDING
            ).join(Contract).filter(
                Contract.creator_id == owner_id,
                Contract.team_id == team_id
            ).join(Customer).first()

            if not payment_plan:
                return None

            return {
                "todo_type": todo_type,
                "todo_id": todo_id,
                "entity_type": "payment_plan",
                "entity_id": payment_plan.id,
                "entity_info": {
                    "name": payment_plan.contract.contract_name,
                    "customer_name": payment_plan.contract.customer.account_name,
                    "stage_name": payment_plan.stage_name,
                    "planned_amount": float(payment_plan.planned_amount)
                },
                "current_next_follow_time": payment_plan.due_date.strftime("%Y-%m-%d") if payment_plan.due_date else None,
                "current_next_action": None
            }

        return None


calendar_crud = CalendarCRUD()
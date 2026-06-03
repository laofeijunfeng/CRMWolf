"""热力值计算服务

核心计算逻辑：
1. 获取权重配置（优先团队配置，其次系统默认）
2. 基础分数 50 分
3. 逐因子计算分数变化
4. 确保分数在 0-100 范围内
5. 更新对象的 score 字段
6. 保存计算明细
"""
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.lead import Lead, LeadFollowUp, LeadStatus
from app.models.customer import Customer, Contact, CustomerStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.contract import Contract
from app.models.score_weight import ScoreWeightConfig, ScoreDetail
from app.crud.score_weight import score_weight_crud

logger = logging.getLogger(__name__)


class ScoreService:
    """热力值计算服务"""

    BASE_SCORE = 50  # 基础分数

    def calculate_lead_score(
        self,
        db: Session,
        lead_id: int,
        team_id: int
    ) -> int:
        """计算线索热力值

        Args:
            db: 数据库会话
            lead_id: 线索ID
            team_id: 团队ID

        Returns:
            计算后的热力值（0-100）
        """
        # 获取线索
        lead = db.query(Lead).filter(
            Lead.id == lead_id,
            Lead.team_id == team_id
        ).first()

        if not lead:
            logger.warning(f"线索不存在: lead_id={lead_id}, team_id={team_id}")
            return 0

        # 已转化或无效的线索不计分
        if lead.status in [LeadStatus.CONVERTED, LeadStatus.INVALID]:
            lead.score = None
            lead.score_updated_at = None
            db.commit()
            return 0

        # 获取权重配置
        weights = score_weight_crud.get_active_weights(db, team_id, 'LEAD')

        # 计算各因子分数
        total_score = self.BASE_SCORE
        details = []

        for weight in weights:
            score_change, actual_value, reason = self._calculate_lead_factor_score(
                db, lead, weight
            )
            total_score += score_change

            details.append({
                'team_id': team_id,
                'module_type': 'LEAD',
                'record_id': lead_id,
                'factor_key': weight.factor_key,
                'factor_name': weight.factor_name,
                'weight_value': weight.weight_value,
                'actual_value': actual_value,
                'score_change': score_change,
                'reason': reason
            })

        # 确保分数在 0-100 范围内
        final_score = max(0, min(100, total_score))

        # 更新线索分数
        lead.score = final_score
        lead.score_updated_at = datetime.now()

        # 清除旧的明细记录（保留最近10次）
        self._clear_old_details(db, 'LEAD', lead_id, keep=10)

        # 保存计算明细
        self._save_score_details(db, details)

        db.commit()

        logger.info(f"线索热力值计算完成: lead_id={lead_id}, score={final_score}")
        return final_score

    def _calculate_lead_factor_score(
        self,
        db: Session,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """计算单个线索因子的分数

        Returns:
            (分数变化, 实际值, 原因说明)
        """
        factor_key = weight.factor_key
        condition_rules = weight.condition_rules

        if factor_key == 'source':
            return self._calc_source_score(lead, weight)
        elif factor_key == 'company_scale':
            return self._calc_company_scale_score(lead, weight)
        elif factor_key == 'status':
            return self._calc_status_score(lead, weight)
        elif factor_key == 'in_pool':
            return self._calc_in_pool_score(lead, weight)
        elif factor_key == 'last_follow_up_days':
            return self._calc_last_follow_up_days_score(db, lead, weight)
        elif factor_key == 'next_follow_time':
            return self._calc_next_follow_time_score(db, lead, weight)

        return (0, None, "未知因子")

    def _calc_source_score(
        self,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """线索来源分数"""
        source_value = lead.source.value if hasattr(lead.source, 'value') else str(lead.source)

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                score = rules.get(source_value, weight.weight_value)
                return (score, source_value, f"来源为{source_value}")
            except json.JSONDecodeError:
                pass

        return (weight.weight_value, source_value, f"来源为{source_value}")

    def _calc_company_scale_score(
        self,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """公司规模分数"""
        if not lead.company_scale:
            return (0, "未知", "公司规模未填写")

        scale_value = lead.company_scale.value if hasattr(lead.company_scale, 'value') else str(lead.company_scale)

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                score = rules.get(scale_value, weight.weight_value)
                return (score, scale_value, f"规模为{scale_value}")
            except json.JSONDecodeError:
                pass

        return (weight.weight_value, scale_value, f"规模为{scale_value}")

    def _calc_status_score(
        self,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """状态分数"""
        status_name = lead.status.name if hasattr(lead.status, 'name') else str(lead.status)

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                score = rules.get(status_name, 0)
                return (score, status_name, f"状态为{status_name}")
            except json.JSONDecodeError:
                pass

        return (weight.weight_value, status_name, f"状态为{status_name}")

    def _calc_in_pool_score(
        self,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """公海池分数"""
        if lead.owner_id is None:
            return (-weight.weight_value, "在公海池", "线索在公海池")
        return (0, "有负责人", "线索有负责人")

    def _calc_last_follow_up_days_score(
        self,
        db: Session,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """最近跟进时间分数"""
        latest_follow_up = db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead.id
        ).order_by(LeadFollowUp.created_time.desc()).first()

        if not latest_follow_up:
            return (-10, "无跟进", "无跟进记录")

        days = (datetime.now() - latest_follow_up.created_time).days

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                if days <= 7:
                    score = rules.get('<=7', 5)
                    return (score, f"{days}天", f"最近跟进{days}天")
                elif days <= 30:
                    score = rules.get('7-30', -5)
                    return (score, f"{days}天", f"最近跟进{days}天")
                else:
                    score = rules.get('>30', -10)
                    return (score, f"{days}天", f"超过30天未跟进")
            except json.JSONDecodeError:
                pass

        # 默认规则
        if days <= 7:
            return (5, f"{days}天", f"最近跟进{days}天")
        elif days <= 30:
            return (-5, f"{days}天", f"超过7天未跟进")
        else:
            return (-10, f"{days}天", f"超过30天未跟进")

    def _calc_next_follow_time_score(
        self,
        db: Session,
        lead: Lead,
        weight: ScoreWeightConfig
    ) -> tuple:
        """下次跟进时间分数"""
        latest_follow_up = db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead.id
        ).order_by(LeadFollowUp.created_time.desc()).first()

        if not latest_follow_up or not latest_follow_up.next_follow_time:
            return (0, "无计划", "无下次跟进计划")

        # 有计划跟进时间
        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                score = rules.get('has_plan', 5)
                return (score, "有计划", f"计划于{latest_follow_up.next_follow_time.strftime('%Y-%m-%d')}跟进")
            except json.JSONDecodeError:
                pass

        return (weight.weight_value, "有计划", f"计划于{latest_follow_up.next_follow_time.strftime('%Y-%m-%d')}跟进")

    def calculate_customer_score(
        self,
        db: Session,
        customer_id: int,
        team_id: int
    ) -> int:
        """计算客户热力值

        Args:
            db: 数据库会话
            customer_id: 客户ID
            team_id: 团队ID

        Returns:
            计算后的热力值（0-100）
        """
        # 获取客户
        customer = db.query(Customer).filter(
            Customer.id == customer_id,
            Customer.team_id == team_id
        ).first()

        if not customer:
            logger.warning(f"客户不存在: customer_id={customer_id}, team_id={team_id}")
            return 0

        # 获取权重配置
        weights = score_weight_crud.get_active_weights(db, team_id, 'CUSTOMER')

        # 计算各因子分数
        total_score = self.BASE_SCORE
        details = []

        for weight in weights:
            score_change, actual_value, reason = self._calculate_customer_factor_score(
                db, customer, weight
            )
            total_score += score_change

            details.append({
                'team_id': team_id,
                'module_type': 'CUSTOMER',
                'record_id': customer_id,
                'factor_key': weight.factor_key,
                'factor_name': weight.factor_name,
                'weight_value': weight.weight_value,
                'actual_value': actual_value,
                'score_change': score_change,
                'reason': reason
            })

        # 确保分数在 0-100 范围内
        final_score = max(0, min(100, total_score))

        # 更新客户分数
        customer.score = final_score
        customer.score_updated_at = datetime.now()

        # 清除旧的明细记录
        self._clear_old_details(db, 'CUSTOMER', customer_id, keep=10)

        # 保存计算明细
        self._save_score_details(db, details)

        db.commit()

        logger.info(f"客户热力值计算完成: customer_id={customer_id}, score={final_score}")
        return final_score

    def _calculate_customer_factor_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """计算单个客户因子的分数"""
        factor_key = weight.factor_key

        if factor_key == 'opportunity_count':
            return self._calc_opportunity_count_score(db, customer, weight)
        elif factor_key == 'opportunity_amount':
            return self._calc_opportunity_amount_score(db, customer, weight)
        elif factor_key == 'opportunity_win_prob':
            return self._calc_opportunity_win_prob_score(db, customer, weight)
        elif factor_key == 'contract_count':
            return self._calc_contract_count_score(db, customer, weight)
        elif factor_key == 'contract_amount':
            return self._calc_contract_amount_score(db, customer, weight)
        elif factor_key == 'payment_status':
            return self._calc_payment_status_score(db, customer, weight)
        elif factor_key == 'decision_maker_count':
            return self._calc_decision_maker_score(db, customer, weight)
        elif factor_key == 'primary_contact':
            return self._calc_primary_contact_score(db, customer, weight)
        elif factor_key == 'status':
            return self._calc_customer_status_score(customer, weight)
        elif factor_key == 'return_count':
            return self._calc_return_count_score(customer, weight)

        return (0, None, "未知因子")

    def _calc_opportunity_count_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """商机数量分数"""
        count = db.query(Opportunity).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.status == OpportunityStatus.FOLLOWING
        ).count()

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                max_count = rules.get('max_count', 3)
                per_count = rules.get('per_count', 10)
                score = min(count, max_count) * per_count
                return (score, f"{count}个", f"活跃商机{count}个")
            except json.JSONDecodeError:
                pass

        score = min(count, 3) * weight.weight_value
        return (score, f"{count}个", f"活跃商机{count}个")

    def _calc_opportunity_amount_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """商机金额分数"""
        total = db.query(func.sum(Opportunity.total_amount)).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.status == OpportunityStatus.FOLLOWING
        ).scalar() or 0

        total_float = float(total)

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                per_100k = rules.get('per_100k', 1)
                max_score = rules.get('max_score', 30)
                score = min(int(total_float / 100000 * per_100k), max_score)
                return (score, f"{total_float:.0f}元", f"商机总金额{total_float:.0f}元")
            except json.JSONDecodeError:
                pass

        score = int(total_float / 100000) * weight.weight_value
        return (score, f"{total_float:.0f}元", f"商机总金额{total_float:.0f}元")

    def _calc_opportunity_win_prob_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """商机赢率分数"""
        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.status == OpportunityStatus.FOLLOWING
        ).all()

        if not opportunities:
            return (0, "无商机", "无活跃商机")

        # 计算加权平均赢率
        total_amount = sum(float(o.total_amount) for o in opportunities)
        if total_amount == 0:
            return (0, "0%", "商机金额为0")

        weighted_prob = sum(
            float(o.total_amount) * (o.current_win_probability or 0) / total_amount
            for o in opportunities
        )

        # 按赢率比例计算分数
        score = int(weighted_prob / 100 * weight.weight_value)
        return (score, f"{weighted_prob:.0f}%", f"加权赢率{weighted_prob:.0f}%")

    def _calc_contract_count_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """合同数量分数"""
        count = db.query(Contract).filter(
            Contract.customer_id == customer.id
        ).count()

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                max_count = rules.get('max_count', 2)
                per_count = rules.get('per_count', 15)
                score = min(count, max_count) * per_count
                return (score, f"{count}个", f"合同{count}个")
            except json.JSONDecodeError:
                pass

        score = min(count, 2) * weight.weight_value
        return (score, f"{count}个", f"合同{count}个")

    def _calc_contract_amount_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """合同金额分数"""
        total = db.query(func.sum(Contract.total_amount)).filter(
            Contract.customer_id == customer.id
        ).scalar() or 0

        total_float = float(total)

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                per_100k = rules.get('per_100k', 2)
                max_score = rules.get('max_score', 40)
                score = min(int(total_float / 100000 * per_100k), max_score)
                return (score, f"{total_float:.0f}元", f"合同总金额{total_float:.0f}元")
            except json.JSONDecodeError:
                pass

        score = int(total_float / 100000) * weight.weight_value
        return (score, f"{total_float:.0f}元", f"合同总金额{total_float:.0f}元")

    def _calc_payment_status_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """回款状态分数"""
        # 获取最新合同的回款状态
        contract = db.query(Contract).filter(
            Contract.customer_id == customer.id
        ).order_by(Contract.created_time.desc()).first()

        if not contract:
            return (0, "无合同", "无合同记录")

        status = contract.payment_status or "UNPAID"

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                score = rules.get(status, 0)
                return (score, status, f"回款状态为{status}")
            except json.JSONDecodeError:
                pass

        return (weight.weight_value, status, f"回款状态为{status}")

    def _calc_decision_maker_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """决策人分数"""
        count = db.query(Contact).filter(
            Contact.customer_id == customer.id,
            Contact.is_decision_maker == 1
        ).count()

        if count > 0:
            return (weight.weight_value, f"{count}人", f"有{count}个决策人")
        return (0, "无", "无决策人")

    def _calc_primary_contact_score(
        self,
        db: Session,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """主联系人分数"""
        count = db.query(Contact).filter(
            Contact.customer_id == customer.id,
            Contact.is_primary == 1
        ).count()

        if count > 0:
            return (weight.weight_value, "有", "有主联系人")
        return (0, "无", "无主联系人")

    def _calc_customer_status_score(
        self,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """客户状态分数"""
        status_map = {
            CustomerStatus.WON: "WON",
            CustomerStatus.FOLLOWING: "FOLLOWING",
            CustomerStatus.LOST: "LOST",
            CustomerStatus.INACTIVE: "INACTIVE"
        }
        status_name = status_map.get(customer.status, str(customer.status))

        if weight.condition_rules:
            try:
                rules = json.loads(weight.condition_rules)
                score = rules.get(status_name, 0)
                return (score, status_name, f"状态为{status_name}")
            except json.JSONDecodeError:
                pass

        return (weight.weight_value, status_name, f"状态为{status_name}")

    def _calc_return_count_score(
        self,
        customer: Customer,
        weight: ScoreWeightConfig
    ) -> tuple:
        """退回公海次数分数"""
        if customer.return_reason:
            return (-weight.weight_value, "有退回", f"退回原因:{customer.return_reason}")
        return (0, "无退回", "无退回公海记录")

    def _save_score_details(
        self,
        db: Session,
        details: List[Dict]
    ) -> None:
        """保存计算明细"""
        for detail in details:
            score_detail = ScoreDetail(**detail)
            db.add(score_detail)

    def _clear_old_details(
        self,
        db: Session,
        module_type: str,
        record_id: int,
        keep: int = 10
    ) -> None:
        """清除旧的明细记录

        保留最近 keep 次计算的明细
        """
        # 获取最近的计算时间
        recent_times = db.query(ScoreDetail.calculated_time).filter(
            ScoreDetail.module_type == module_type,
            ScoreDetail.record_id == record_id
        ).order_by(ScoreDetail.calculated_time.desc()).limit(keep).all()

        if len(recent_times) < keep:
            return

        # 删除更早的记录
        earliest_keep = recent_times[-1][0]
        db.query(ScoreDetail).filter(
            ScoreDetail.module_type == module_type,
            ScoreDetail.record_id == record_id,
            ScoreDetail.calculated_time < earliest_keep
        ).delete()

    def batch_update_lead_scores(
        self,
        db: Session,
        team_id: int,
        limit: Optional[int] = None
    ) -> int:
        """批量更新线索热力值

        Args:
            db: 数据库会话
            team_id: 团队ID
            limit: 限制数量（用于测试）

        Returns:
            更新的数量
        """
        query = db.query(Lead).filter(
            Lead.team_id == team_id,
            Lead.status.not_in([LeadStatus.CONVERTED, LeadStatus.INVALID])
        )

        if limit:
            query = query.limit(limit)

        leads = query.all()

        count = 0
        for lead in leads:
            self.calculate_lead_score(db, lead.id, team_id)
            count += 1

        logger.info(f"批量更新线索热力值: team_id={team_id}, count={count}")
        return count

    def batch_update_customer_scores(
        self,
        db: Session,
        team_id: int,
        limit: Optional[int] = None
    ) -> int:
        """批量更新客户热力值

        Args:
            db: 数据库会话
            team_id: 团队ID
            limit: 限制数量（用于测试）

        Returns:
            更新的数量
        """
        query = db.query(Customer).filter(
            Customer.team_id == team_id
        )

        if limit:
            query = query.limit(limit)

        customers = query.all()

        count = 0
        for customer in customers:
            self.calculate_customer_score(db, customer.id, team_id)
            count += 1

        logger.info(f"批量更新客户热力值: team_id={team_id}, count={count}")
        return count


# 单例实例
score_service = ScoreService()
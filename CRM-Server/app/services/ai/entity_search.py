"""只读实体搜索服务（R-ST-01~06 合规）

为 glue 层提供只读实体搜索，不暴露 CRUD 直接调用。

原则:
- glue 层不直接 import CRUD（C-1合规）
- 通过此服务层提供只读搜索
- 租户隔离（team_id 过滤）
- 三阶降级搜索（norm精确→norm宽匹配→raw兜底）
- 归一化优先（R-ST-02）

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md R-ST-01~06
"""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.glue.core.types import EntityCandidate
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.customer_follow_up import CustomerFollowUp
from app.utils.name_normalizer import normalize_corp_name


logger = logging.getLogger(__name__)


class EntitySearchService:
    """只读实体搜索服务（R-ST-01~06 合规）"""

    def __init__(self, db: Session, team_id: int):
        """初始化搜索服务

        Args:
            db: 数据库会话
            team_id: 租户 ID（用于权限隔离）
        """
        self.db = db
        self.team_id = team_id

    def search_customers(
        self,
        keyword: str,
        limit: int = 5,  # R-ST-03: 最多返回 5~8
    ) -> List[EntityCandidate]:
        """搜索客户（三阶降级 R-ST-03）

        优先级：
        ① norm 精确/前缀（走索引）
        ② norm 宽匹配（分词 OR / similarity）
        ③ 兜底 raw ILIKE

        Args:
            keyword: 搜索关键词（口语化，如"光大证券")
            limit: 返回数量限制（R-ST-03: 5~8）

        Returns:
            EntityCandidate 列表（R-ST-04: 带 hint 和 matched_by）
        """
        candidates = []
        kw_norm = normalize_corp_name(keyword)

        # ① norm 精确/前缀（走 GIN 索引）
        exact_matches = self._search_customers_norm_exact(kw_norm, limit)
        for m in exact_matches:
            candidates.append(EntityCandidate(
                id=m.id,
                name=m.account_name,
                hint=self._build_customer_hint(m.id),
                matched_by="exact_norm",
                entity_type="Customer",
            ))

        if len(candidates) >= limit:
            return candidates[:limit]

        # ② norm 宽匹配（ILIKE %kw_norm%，允许部分匹配）
        wide_matches = self._search_customers_norm_wide(kw_norm, limit - len(candidates))
        for m in wide_matches:
            if m.id not in [c.id for c in candidates]:
                candidates.append(EntityCandidate(
                    id=m.id,
                    name=m.account_name,
                    hint=self._build_customer_hint(m.id),
                    matched_by="wide",
                    entity_type="Customer",
                ))

        if len(candidates) >= limit:
            return candidates[:limit]

        # ③ 兜底 raw ILIKE（防止"光大"拉回半省）
        raw_matches = self._search_customers_raw(keyword, limit - len(candidates))
        for m in raw_matches:
            if m.id not in [c.id for c in candidates]:
                candidates.append(EntityCandidate(
                    id=m.id,
                    name=m.account_name,
                    hint=self._build_customer_hint(m.id),
                    matched_by="raw",
                    entity_type="Customer",
                ))

        return candidates[:limit]

    def load_customer_by_id(self, customer_id: int) -> Optional[EntityCandidate]:
        """根据 ID 加载客户（R-ST-05：#ID 汇入搜索工具）

        Args:
            customer_id: 客户 ID

        Returns:
            EntityCandidate 或 None（无权限/不存在）
        """
        customer = self.db.query(Customer).filter(
            and_(
                Customer.team_id == self.team_id,
                Customer.id == customer_id,
            )
        ).first()

        if not customer:
            return None

        return EntityCandidate(
            id=customer.id,
            name=customer.account_name,
            hint=self._build_customer_hint(customer.id),
            matched_by="raw",  # ID 不需要 matched_by
            entity_type="Customer",
        )

    def load_opportunity_by_id(self, opportunity_id: int) -> Optional[EntityCandidate]:
        """根据 ID 加载商机（R-ST-05）"""
        opportunity = self.db.query(Opportunity).filter(
            and_(
                Opportunity.team_id == self.team_id,
                Opportunity.id == opportunity_id,
            )
        ).first()

        if not opportunity:
            return None

        return EntityCandidate(
            id=opportunity.id,
            name=opportunity.opportunity_name,
            hint=self._build_opportunity_hint(opportunity),
            matched_by="raw",
            entity_type="Opportunity",
        )

    def search_opportunities(
        self,
        keyword: str,
        customer_id: Optional[int] = None,
        limit: int = 5,
    ) -> List[EntityCandidate]:
        """搜索商机（类似 search_customers）"""
        # 简化实现：直接用 keyword ILIKE（暂无商机归一化列）
        query = self.db.query(Opportunity).filter(
            Opportunity.team_id == self.team_id,
            Opportunity.opportunity_name.ilike(f"%{keyword}%"),
        )

        if customer_id:
            query = query.filter(Opportunity.customer_id == customer_id)

        opportunities = query.order_by(Opportunity.created_time.desc()).limit(limit).all()

        return [
            EntityCandidate(
                id=opp.id,
                name=opp.opportunity_name,
                hint=self._build_opportunity_hint(opp),
                matched_by="raw",
                entity_type="Opportunity",
            )
            for opp in opportunities
        ]

    def search_entities(
        self,
        entity_type: str,
        keyword: str,
        limit: int = 5,
    ) -> List[EntityCandidate]:
        """通用实体搜索"""
        if entity_type == "Customer":
            return self.search_customers(keyword, limit)
        elif entity_type == "Opportunity":
            return self.search_opportunities(keyword, limit=limit)
        else:
            logger.warning(f"不支持的实体类型: {entity_type}")
            return []

    # ==================== 内部方法 ====================

    def _search_customers_norm_exact(
        self,
        kw_norm: str,
        limit: int,
    ) -> List[Customer]:
        """① norm 精确/前缀匹配"""
        return self.db.query(Customer).filter(
            and_(
                Customer.team_id == self.team_id,
                or_(
                    Customer.account_name_norm == kw_norm,  # 精确
                    Customer.account_name_norm.ilike(f"{kw_norm}%"),  # 前缀
                ),
            )
        ).order_by(Customer.created_time.desc()).limit(limit).all()

    def _search_customers_norm_wide(
        self,
        kw_norm: str,
        limit: int,
    ) -> List[Customer]:
        """② norm 宽匹配"""
        return self.db.query(Customer).filter(
            and_(
                Customer.team_id == self.team_id,
                Customer.account_name_norm.ilike(f"%{kw_norm}%"),
            )
        ).order_by(Customer.created_time.desc()).limit(limit).all()

    def _search_customers_raw(
        self,
        keyword: str,
        limit: int,
    ) -> List[Customer]:
        """③ 兜底 raw ILIKE"""
        return self.db.query(Customer).filter(
            and_(
                Customer.team_id == self.team_id,
                Customer.account_name.ilike(f"%{keyword}%"),
            )
        ).order_by(Customer.created_time.desc()).limit(limit).all()

    def _build_customer_hint(self, customer_id: int) -> str:
        """构建客户 hint（R-ST-04：最近跟进 + 商机信息）"""
        parts = []

        # 1. 最近跟进时间
        try:
            follow_up = self.db.query(CustomerFollowUp).filter(
                CustomerFollowUp.customer_id == customer_id
            ).order_by(CustomerFollowUp.follow_up_time.desc()).first()

            if follow_up and follow_up.follow_up_time:
                parts.append(f"最近跟进 {follow_up.follow_up_time.strftime('%m/%d')}")
        except Exception as e:
            logger.debug(f"获取客户跟进信息失败: {e}")

        # 2. 最高优先级商机
        try:
            opportunity = self.db.query(Opportunity).filter(
                and_(
                    Opportunity.team_id == self.team_id,
                    Opportunity.customer_id == customer_id,
                )
            ).order_by(Opportunity.created_time.desc()).first()

            if opportunity:
                stage = opportunity.current_stage_name or "未知阶段"
                title = opportunity.opportunity_name
                parts.append(f"商机：{title} · {stage}")
        except Exception as e:
            logger.debug(f"获取商机信息失败: {e}")

        return " · ".join(parts) if parts else ""

    def _build_opportunity_hint(self, opportunity: Opportunity) -> str:
        """构建商机 hint"""
        try:
            stage = opportunity.current_stage_name or "未知阶段"
            amount = opportunity.amount or 0
            return f"阶段：{stage} · 金额：{amount}万"
        except Exception as e:
            logger.debug(f"构建商机 hint 失败: {e}")
            return ""


__all__ = [
    "EntitySearchService",
]
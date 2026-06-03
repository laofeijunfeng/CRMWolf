"""
行业 CRUD 操作
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.industry import Industry


class IndustryCRUD:
    """行业 CRUD 操作"""

    def get_all_primary(self, db: Session) -> List[Industry]:
        """获取所有一级行业"""
        return db.query(Industry).filter(
            Industry.level == 1,
            Industry.is_active == 1
        ).order_by(Industry.sort_order).all()

    def get_all_secondary(self, db: Session) -> List[Industry]:
        """获取所有二级行业"""
        return db.query(Industry).filter(
            Industry.level == 2,
            Industry.is_active == 1
        ).order_by(Industry.sort_order).all()

    def get_by_code(self, db: Session, code: str) -> Optional[Industry]:
        """根据 code 获取行业"""
        return db.query(Industry).filter(Industry.code == code).first()

    def get_by_code_with_parent(self, db: Session, code: str) -> Optional[Industry]:
        """根据 code 获取行业（含父行业）"""
        from sqlalchemy.orm import joinedload
        return db.query(Industry).options(
            joinedload(Industry.parent)
        ).filter(Industry.code == code).first()

    def get_by_id(self, db: Session, id: int) -> Optional[Industry]:
        """根据 ID 获取行业"""
        return db.query(Industry).filter(Industry.id == id).first()

    def get_secondary_by_parent(self, db: Session, parent_code: str) -> List[Industry]:
        """根据父行业 code 获取所有二级行业"""
        parent = self.get_by_code(db, parent_code)
        if not parent:
            return []
        return db.query(Industry).filter(
            Industry.level == 2,
            Industry.parent_id == parent.id,
            Industry.is_active == 1
        ).order_by(Industry.sort_order).all()

    def get_all_active(self, db: Session) -> List[Industry]:
        """获取所有启用的行业"""
        return db.query(Industry).filter(
            Industry.is_active == 1
        ).order_by(Industry.level, Industry.sort_order).all()

    def get_industry_hierarchy(self, db: Session) -> dict:
        """
        获取行业层级结构（用于 AI 提示词）
        返回格式: {一级行业code: {name, children: [{code, name}]}}
        """
        primary = self.get_all_primary(db)
        hierarchy = {}

        for p in primary:
            children = db.query(Industry).filter(
                Industry.level == 2,
                Industry.parent_id == p.id,
                Industry.is_active == 1
            ).order_by(Industry.sort_order).all()

            hierarchy[p.code] = {
                "name": p.name,
                "children": [{"code": c.code, "name": c.name} for c in children]
            }

        return hierarchy

    def get_by_codes_with_parent(self, db: Session, codes: List[str]) -> dict:
        """
        批量根据 codes 获取行业（包含父行业信息）
        用于客户列表等批量查询场景
        返回格式: {code: Industry对象（含parent）}
        """
        from sqlalchemy.orm import joinedload

        industries = db.query(Industry).options(
            joinedload(Industry.parent)
        ).filter(
            Industry.code.in_(codes)
        ).all()

        return {i.code: i for i in industries}

    def get_customers_by_industry(
        self,
        db: Session,
        industry_code: str,
        exclude_customer_id: int,
        team_id: int,
        limit: int = 50
    ) -> List[str]:
        """
        获取同行业的有效客户名称列表
        用于 AI 同行业客户匹配
        只检索当前团队的有效客户：跟进中(0)和赢单(1)
        """
        from app.models.customer import Customer

        # 先按二级行业精确匹配，只检索当前团队的有效客户
        customers = db.query(Customer.account_name).filter(
            Customer.industry == industry_code,
            Customer.id != exclude_customer_id,
            Customer.team_id == team_id,  # 限制在当前团队
            Customer.status.in_([0, 1])  # 只检索跟进中和赢单客户
        ).limit(limit).all()

        if len(customers) >= 5:
            return [c[0] for c in customers]

        # 如果二级行业客户不足，尝试一级行业匹配
        industry = self.get_by_code(db, industry_code)
        if industry and industry.level == 2:
            parent_id = industry.parent_id
            # 获取同一父行业下的所有二级行业
            sibling_codes = db.query(Industry.code).filter(
                Industry.parent_id == parent_id,
                Industry.is_active == 1
            ).all()
            sibling_codes = [c[0] for c in sibling_codes]

            customers = db.query(Customer.account_name).filter(
                Customer.industry.in_(sibling_codes),
                Customer.id != exclude_customer_id,
                Customer.team_id == team_id,  # 限制在当前团队
                Customer.status.in_([0, 1])  # 只检索跟进中和赢单客户
            ).limit(limit).all()

        return [c[0] for c in customers if c[0]]


industry_crud = IndustryCRUD()
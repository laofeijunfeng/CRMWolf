"""热力值计算明细 CRUD

提供热力值计算明细的查询操作。
"""
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime

from app.models.score_weight import ScoreDetail


class ScoreDetailCRUD:
    """热力值计算明细 CRUD"""

    def get_latest_details(
        self,
        db: Session,
        module_type: str,
        record_id: int,
        limit: int = 20
    ) -> List[ScoreDetail]:
        """获取最近一次计算的明细记录

        Args:
            db: 数据库会话
            module_type: 模块类型（LEAD/CUSTOMER）
            record_id: 记录ID
            limit: 返回数量限制

        Returns:
            计算明细列表
        """
        # 获取最近一次计算时间
        latest_time = db.query(ScoreDetail.calculated_time).filter(
            ScoreDetail.module_type == module_type,
            ScoreDetail.record_id == record_id
        ).order_by(ScoreDetail.calculated_time.desc()).first()

        if not latest_time:
            return []

        # 获取该次计算的明细
        return db.query(ScoreDetail).filter(
            and_(
                ScoreDetail.module_type == module_type,
                ScoreDetail.record_id == record_id,
                ScoreDetail.calculated_time == latest_time[0]
            )
        ).order_by(ScoreDetail.factor_key).limit(limit).all()

    def get_history(
        self,
        db: Session,
        module_type: str,
        record_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[ScoreDetail]:
        """获取历史计算明细

        Args:
            db: 数据库会话
            module_type: 模块类型
            record_id: 记录ID
            skip: 跳过数量
            limit: 返回数量

        Returns:
            计算明细列表（按时间倒序）
        """
        return db.query(ScoreDetail).filter(
            and_(
                ScoreDetail.module_type == module_type,
                ScoreDetail.record_id == record_id
            )
        ).order_by(
            ScoreDetail.calculated_time.desc()
        ).offset(skip).limit(limit).all()

    def delete_by_record(
        self,
        db: Session,
        module_type: str,
        record_id: int
    ) -> int:
        """删除指定记录的所有明细

        Args:
            db: 数据库会话
            module_type: 模块类型
            record_id: 记录ID

        Returns:
            删除的数量
        """
        count = db.query(ScoreDetail).filter(
            and_(
                ScoreDetail.module_type == module_type,
                ScoreDetail.record_id == record_id
            )
        ).delete()

        db.commit()
        return count


# 单例实例
score_detail_crud = ScoreDetailCRUD()
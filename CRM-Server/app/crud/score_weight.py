"""热力值权重配置 CRUD

提供权重配置的查询、创建、更新操作。

核心逻辑：
- 优先返回团队自定义配置
- 若无团队配置则返回系统默认配置
- 支持从系统默认复制到团队
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime

from app.models.score_weight import ScoreWeightConfig


class ScoreWeightCRUD:
    """热力值权重配置 CRUD"""

    def get_active_weights(
        self,
        db: Session,
        team_id: int,
        module_type: str
    ) -> List[ScoreWeightConfig]:
        """获取有效的权重配置

        优先级：
        1. 团队自定义配置（team_id = 具体值）
        2. 系统默认配置（team_id = NULL）

        Args:
            db: 数据库会话
            team_id: 团队ID
            module_type: 模块类型（LEAD/CUSTOMER）

        Returns:
            权重配置列表（按 sort_order 排序）
        """
        # 先查询团队配置
        team_weights = db.query(ScoreWeightConfig).filter(
            and_(
                ScoreWeightConfig.team_id == team_id,
                ScoreWeightConfig.module_type == module_type,
                ScoreWeightConfig.is_enabled == 1
            )
        ).order_by(ScoreWeightConfig.sort_order).all()

        # 如果团队有配置，返回团队配置
        if team_weights:
            return team_weights

        # 否则返回系统默认配置
        return db.query(ScoreWeightConfig).filter(
            and_(
                ScoreWeightConfig.team_id.is_(None),
                ScoreWeightConfig.module_type == module_type,
                ScoreWeightConfig.is_enabled == 1
            )
        ).order_by(ScoreWeightConfig.sort_order).all()

    def get_all_weights(
        self,
        db: Session,
        team_id: int,
        module_type: str
    ) -> List[ScoreWeightConfig]:
        """获取所有权重配置（包括禁用的）

        Args:
            db: 数据库会话
            team_id: 团队ID
            module_type: 模块类型

        Returns:
            权重配置列表
        """
        # 先查询团队配置
        team_weights = db.query(ScoreWeightConfig).filter(
            and_(
                ScoreWeightConfig.team_id == team_id,
                ScoreWeightConfig.module_type == module_type
            )
        ).order_by(ScoreWeightConfig.sort_order).all()

        # 如果团队有配置，返回团队配置
        if team_weights:
            return team_weights

        # 否则返回系统默认配置
        return db.query(ScoreWeightConfig).filter(
            and_(
                ScoreWeightConfig.team_id.is_(None),
                ScoreWeightConfig.module_type == module_type
            )
        ).order_by(ScoreWeightConfig.sort_order).all()

    def has_team_weights(
        self,
        db: Session,
        team_id: int,
        module_type: str
    ) -> bool:
        """检查团队是否有自定义权重配置

        Args:
            db: 数据库会话
            team_id: 团队ID
            module_type: 模块类型

        Returns:
            是否有团队配置
        """
        count = db.query(ScoreWeightConfig).filter(
            and_(
                ScoreWeightConfig.team_id == team_id,
                ScoreWeightConfig.module_type == module_type
            )
        ).count()
        return count > 0

    def create_team_weights_from_system(
        self,
        db: Session,
        team_id: int,
        module_type: str,
        creator_id: str
    ) -> List[ScoreWeightConfig]:
        """从系统默认复制权重配置到团队

        Args:
            db: 数据库会话
            team_id: 团队ID
            module_type: 模块类型（可选，不传则复制所有）
            creator_id: 创建人ID

        Returns:
            新创建的权重配置列表
        """
        # 查询系统默认配置
        query = db.query(ScoreWeightConfig).filter(
            ScoreWeightConfig.team_id.is_(None)
        )

        if module_type:
            query = query.filter(ScoreWeightConfig.module_type == module_type)

        system_weights = query.all()

        # 复制到团队
        new_weights = []
        for weight in system_weights:
            team_weight = ScoreWeightConfig(
                team_id=team_id,
                module_type=weight.module_type,
                factor_key=weight.factor_key,
                factor_name=weight.factor_name,
                weight_value=weight.weight_value,
                is_enabled=weight.is_enabled,
                condition_rules=weight.condition_rules,
                sort_order=weight.sort_order,
                created_by=creator_id
            )
            db.add(team_weight)
            new_weights.append(team_weight)

        db.commit()

        # 刷新以获取ID
        for weight in new_weights:
            db.refresh(weight)

        return new_weights

    def get_by_id(
        self,
        db: Session,
        weight_id: int
    ) -> Optional[ScoreWeightConfig]:
        """按ID获取权重配置

        Args:
            db: 数据库会话
            weight_id: 权重配置ID

        Returns:
            权重配置对象或None
        """
        return db.query(ScoreWeightConfig).filter(
            ScoreWeightConfig.id == weight_id
        ).first()

    def update_weight(
        self,
        db: Session,
        weight_id: int,
        weight_value: Optional[int] = None,
        is_enabled: Optional[int] = None,
        condition_rules: Optional[str] = None,
        updated_by: str = None
    ) -> ScoreWeightConfig:
        """更新权重配置

        Args:
            db: 数据库会话
            weight_id: 权重配置ID
            weight_value: 新的权重值
            is_enabled: 是否启用
            condition_rules: 条件规则
            updated_by: 更新人ID

        Returns:
            更新后的权重配置

        Raises:
            ValueError: 权重配置不存在或为系统默认配置
        """
        weight = self.get_by_id(db, weight_id)
        if not weight:
            raise ValueError("权重配置不存在")

        # 系统默认配置不可直接编辑
        if weight.team_id is None:
            raise ValueError("系统默认配置不可直接编辑，请先复制到团队")

        if weight_value is not None:
            weight.weight_value = weight_value

        if is_enabled is not None:
            weight.is_enabled = is_enabled

        if condition_rules is not None:
            weight.condition_rules = condition_rules

        weight.updated_by = updated_by
        weight.updated_time = datetime.now()

        db.commit()
        db.refresh(weight)

        return weight

    def delete_team_weights(
        self,
        db: Session,
        team_id: int,
        module_type: str
    ) -> int:
        """删除团队的权重配置（恢复使用系统默认）

        Args:
            db: 数据库会话
            team_id: 团队ID
            module_type: 模块类型

        Returns:
            删除的数量
        """
        count = db.query(ScoreWeightConfig).filter(
            and_(
                ScoreWeightConfig.team_id == team_id,
                ScoreWeightConfig.module_type == module_type
            )
        ).delete()

        db.commit()
        return count


# 单例实例
score_weight_crud = ScoreWeightCRUD()
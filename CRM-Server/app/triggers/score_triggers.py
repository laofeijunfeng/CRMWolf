"""热力值触发器

定义热力值重新计算的触发时机。

触发场景：
- 线索：跟进记录创建、状态变更、公海操作
- 客户：客户创建、商机创建、合同创建、公海操作
"""
import logging
from sqlalchemy.orm import Session

from app.services.score_service import score_service

logger = logging.getLogger(__name__)


class ScoreTrigger:
    """热力值触发器

    在相关 CRUD 操作完成后触发热力值重新计算。
    """

    @staticmethod
    def on_lead_follow_up_created(
        db: Session,
        lead_id: int,
        team_id: int
    ) -> None:
        """线索跟进记录创建时触发

        Args:
            db: 数据库会话
            lead_id: 线索ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_lead_score(db, lead_id, team_id)
            logger.debug(f"触发线索热力值更新: lead_id={lead_id}")
        except Exception as e:
            logger.error(f"线索热力值计算失败: lead_id={lead_id}, error={str(e)}")

    @staticmethod
    def on_lead_status_changed(
        db: Session,
        lead_id: int,
        team_id: int
    ) -> None:
        """线索状态变更时触发

        Args:
            db: 数据库会话
            lead_id: 线索ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_lead_score(db, lead_id, team_id)
            logger.debug(f"触发线索热力值更新(状态变更): lead_id={lead_id}")
        except Exception as e:
            logger.error(f"线索热力值计算失败: lead_id={lead_id}, error={str(e)}")

    @staticmethod
    def on_lead_pool_operation(
        db: Session,
        lead_id: int,
        team_id: int
    ) -> None:
        """线索退回公海/领取时触发

        Args:
            db: 数据库会话
            lead_id: 线索ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_lead_score(db, lead_id, team_id)
            logger.debug(f"触发线索热力值更新(公海操作): lead_id={lead_id}")
        except Exception as e:
            logger.error(f"线索热力值计算失败: lead_id={lead_id}, error={str(e)}")

    @staticmethod
    def on_lead_created(
        db: Session,
        lead_id: int,
        team_id: int
    ) -> None:
        """线索创建时触发

        Args:
            db: 数据库会话
            lead_id: 线索ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_lead_score(db, lead_id, team_id)
            logger.debug(f"触发线索热力值初始计算: lead_id={lead_id}")
        except Exception as e:
            logger.error(f"线索热力值计算失败: lead_id={lead_id}, error={str(e)}")

    @staticmethod
    def on_customer_created(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """客户创建时触发

        Args:
            db: 数据库会话
            customer_id: 客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值初始计算: customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_customer_pool_operation(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """客户退回公海/领取时触发

        Args:
            db: 数据库会话
            customer_id: 客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(公海操作): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_customer_status_changed(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """客户状态变更时触发

        Args:
            db: 数据库会话
            customer_id: 客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(状态变更): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_opportunity_created(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """商机创建时触发

        Args:
            db: 数据库会话
            customer_id: 关联客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(商机创建): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_opportunity_status_changed(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """商机状态变更时触发

        Args:
            db: 数据库会话
            customer_id: 关联客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(商机状态变更): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_contract_created(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """合同创建时触发

        Args:
            db: 数据库会话
            customer_id: 关联客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(合同创建): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_contract_status_changed(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """合同状态变更时触发

        Args:
            db: 数据库会话
            customer_id: 关联客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(合同状态变更): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")

    @staticmethod
    def on_contact_changed(
        db: Session,
        customer_id: int,
        team_id: int
    ) -> None:
        """联系人变更时触发（决策人/主联系人变化）

        Args:
            db: 数据库会话
            customer_id: 客户ID
            team_id: 团队ID
        """
        try:
            score_service.calculate_customer_score(db, customer_id, team_id)
            logger.debug(f"触发客户热力值更新(联系人变更): customer_id={customer_id}")
        except Exception as e:
            logger.error(f"客户热力值计算失败: customer_id={customer_id}, error={str(e)}")


# 单例实例
score_trigger = ScoreTrigger()
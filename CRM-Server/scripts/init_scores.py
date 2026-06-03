"""热力值初始化脚本

用于首次上线时批量计算所有旧数据的热力值。

使用方法：
    cd CRM-Server
    python scripts/init_scores.py
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.crud.team import team_crud
from app.services.score_service import score_service
from app.core.logging import get_logger

logger = get_logger(__name__)


def init_all_scores():
    """初始化所有团队的热力值"""
    db = SessionLocal()

    try:
        # 获取所有团队
        teams = team_crud.get_multi(db, skip=0, limit=1000)

        logger.info(f"开始初始化热力值，共 {len(teams)} 个团队")

        total_leads = 0
        total_customers = 0

        for team in teams:
            logger.info(f"处理团队: {team.id} - {team.name}")

            # 批量刷新线索热力值
            lead_count = score_service.batch_update_lead_scores(db, team.id)
            total_leads += lead_count
            logger.info(f"  线索: {lead_count} 条已更新")

            # 批量刷新客户热力值
            customer_count = score_service.batch_update_customer_scores(db, team.id)
            total_customers += customer_count
            logger.info(f"  客户: {customer_count} 条已更新")

        logger.info(f"热力值初始化完成: 线索={total_leads}, 客户={total_customers}")

    except Exception as e:
        logger.error(f"热力值初始化失败: {str(e)}")
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    init_all_scores()
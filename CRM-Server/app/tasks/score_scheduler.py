"""热力值定时刷新任务

每日凌晨批量刷新所有团队的热力值，修正因"时间流逝"导致的分数变化。

使用 asyncio 实现定时调度。
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.core.database import SessionLocal
from app.services.score_service import score_service
from app.crud.team import team_crud

logger = logging.getLogger(__name__)


class ScoreScheduler:
    """热力值定时刷新调度器"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def daily_refresh_all_scores(self) -> dict:
        """每日批量刷新所有团队的热力值

        Returns:
            刷新统计信息
        """
        logger.info(f"[{datetime.now()}] 开始执行热力值每日刷新任务")

        db = SessionLocal()
        stats = {
            "start_time": datetime.now(),
            "teams_processed": 0,
            "leads_updated": 0,
            "customers_updated": 0,
            "errors": []
        }

        try:
            # 获取所有团队
            teams = team_crud.get_all_teams(db)

            for team in teams:
                try:
                    # 刷新线索热力值
                    lead_count = score_service.batch_update_lead_scores(db, team.id)
                    stats["leads_updated"] += lead_count

                    # 刷新客户热力值
                    customer_count = score_service.batch_update_customer_scores(db, team.id)
                    stats["customers_updated"] += customer_count

                    stats["teams_processed"] += 1
                    logger.info(f"团队 {team.id} ({team.name}) 热力值刷新完成: 线索={lead_count}, 客户={customer_count}")

                except Exception as e:
                    error_msg = f"团队 {team.id} 刷新失败: {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)

        except Exception as e:
            logger.error(f"热力值刷新任务执行失败: {str(e)}")
            stats["errors"].append(str(e))

        finally:
            db.close()

        stats["end_time"] = datetime.now()
        stats["duration_seconds"] = (stats["end_time"] - stats["start_time"]).total_seconds()

        logger.info(
            f"[{datetime.now()}] 热力值每日刷新任务完成: "
            f"处理团队={stats['teams_processed']}, "
            f"更新线索={stats['leads_updated']}, "
            f"更新客户={stats['customers_updated']}, "
            f"耗时={stats['duration_seconds']:.2f}秒"
        )

        return stats

    async def refresh_team_scores(self, team_id: int) -> dict:
        """刷新单个团队的热力值

        Args:
            team_id: 团队ID

        Returns:
            刷新统计信息
        """
        db = SessionLocal()
        stats = {
            "team_id": team_id,
            "leads_updated": 0,
            "customers_updated": 0
        }

        try:
            stats["leads_updated"] = score_service.batch_update_lead_scores(db, team_id)
            stats["customers_updated"] = score_service.batch_update_customer_scores(db, team_id)

        except Exception as e:
            logger.error(f"团队 {team_id} 热力值刷新失败: {str(e)}")
            stats["error"] = str(e)

        finally:
            db.close()

        return stats

    async def _run_daily_scheduler(self):
        """每日定时调度循环"""
        while self._running:
            now = datetime.now()

            # 每天凌晨 2 点执行
            if now.hour == 2 and now.minute == 0:
                try:
                    await self.daily_refresh_all_scores()
                except Exception as e:
                    logger.error(f"定时任务执行异常: {str(e)}")

                # 执行后等待到下一分钟，避免重复执行
                await asyncio.sleep(60)

            # 每分钟检查一次
            await asyncio.sleep(60)

    def start(self):
        """启动定时任务"""
        if self._running:
            logger.warning("热力值定时任务已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_daily_scheduler())
        logger.info("热力值定时刷新任务已启动")

    def stop(self):
        """停止定时任务"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                asyncio.get_event_loop().run_until_complete(self._task)
            except asyncio.CancelledError:
                pass

        logger.info("热力值定时刷新任务已停止")


# 单例实例
score_scheduler = ScoreScheduler()


def start_score_scheduler():
    """启动热力值定时刷新任务

    在应用启动时调用
    """
    score_scheduler.start()


def stop_score_scheduler():
    """停止热力值定时刷新任务

    在应用关闭时调用
    """
    score_scheduler.stop()
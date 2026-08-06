"""Backfill follow-up tasks from existing customer activities.

Usage:
  python scripts/backfill_follow_up_tasks.py --dry-run
  python scripts/backfill_follow_up_tasks.py --team-id 1 --days 90 --confirm
"""

import argparse
import json
import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.follow_up_task_backfill_service import follow_up_task_backfill_service


def main() -> None:
    parser = argparse.ArgumentParser(description="从历史客户活动回填跟进任务")
    parser.add_argument("--team-id", type=int, default=None, help="只回填指定团队；默认处理全部团队")
    parser.add_argument("--days", type=int, default=90, help="回填最近 N 天客户活动，默认 90")
    parser.add_argument("--limit", type=int, default=1000, help="本次最多扫描的客户活动数量，默认 1000")
    parser.add_argument("--actor-id", default="system", help="写入任务事件和投影运行的操作者 ID，默认 system")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入")
    parser.add_argument("--confirm", action="store_true", help="确认执行写入；未提供时默认 dry-run")
    args = parser.parse_args()

    dry_run = args.dry_run or not args.confirm
    db = SessionLocal()
    try:
        result = follow_up_task_backfill_service.backfill_customer_activities(
            db,
            team_id=args.team_id,
            days=args.days,
            limit=args.limit,
            dry_run=dry_run,
            actor_id=args.actor_id,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if dry_run:
            print("DRY RUN: 未写入数据；确认无误后加 --confirm 执行。")
    finally:
        db.close()


if __name__ == "__main__":
    main()

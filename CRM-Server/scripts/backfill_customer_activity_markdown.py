"""Backfill historical completed customer activities to structured Markdown (CRM-180).

Usage:
  python scripts/backfill_customer_activity_markdown.py --dry-run
  python scripts/backfill_customer_activity_markdown.py --team-id 1 --limit 500 --concurrency 2 --confirm
  python scripts/backfill_customer_activity_markdown.py --days 365 --limit 2000 --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.customer_activity_markdown_backfill_service import (
    customer_activity_markdown_backfill_service,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="将历史已完成客户活动统一升级为结构化 Markdown（幂等、不触发后置副作用）")
    parser.add_argument("--team-id", type=int, default=None, help="只升级指定团队；默认处理全部团队")
    parser.add_argument("--days", type=int, default=None, help="只升级最近 N 天的客户活动；默认不限时间处理全部历史记录")
    parser.add_argument("--limit", type=int, default=500, help="本次最多升级的候选客户活动数量，默认 500（传 0 表示不限制）")
    parser.add_argument("--concurrency", type=int, default=2, help="并发 LLM 整理数，默认 2（同时受 ai_generation_semaphore 限流）")
    parser.add_argument("--dry-run", action="store_true", help="只预览候选记录，不调用 LLM 也不写入")
    parser.add_argument("--confirm", action="store_true", help="确认执行写入；未提供时默认 dry-run")
    args = parser.parse_args()

    dry_run = args.dry_run or not args.confirm
    limit = None if args.limit == 0 else max(1, args.limit)
    result = asyncio.run(
        customer_activity_markdown_backfill_service.backfill_activities(
            session_factory=SessionLocal,
            team_id=args.team_id,
            days=args.days,
            limit=limit,
            concurrency=max(1, args.concurrency),
            dry_run=dry_run,
        )
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if dry_run:
        print("DRY RUN: 未写入数据；确认无误后加 --confirm 执行。")


if __name__ == "__main__":
    main()

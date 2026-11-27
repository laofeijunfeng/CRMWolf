"""Backfill historical completed customer activities to structured Markdown (CRM-180).

Usage:
  python scripts/backfill_customer_activity_markdown.py --dry-run
  python scripts/backfill_customer_activity_markdown.py --team-id 1 --limit 500 --concurrency 2 --confirm
  python scripts/backfill_customer_activity_markdown.py --activity-ids 39,137,142 --force --confirm
  python scripts/backfill_customer_activity_markdown.py --activity-ids-file /tmp/ids.txt --force --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.customer_activity_markdown_backfill_service import (
    customer_activity_markdown_backfill_service,
)


def _parse_activity_ids(raw_ids: str | None, ids_file: str | None) -> list[int] | None:
    tokens: list[str] = []
    if raw_ids:
        tokens.extend(part for part in re.split(r"[\s,]+", raw_ids.strip()) if part)
    if ids_file:
        content = Path(ids_file).read_text(encoding="utf-8")
        tokens.extend(part for part in re.split(r"[\s,]+", content.strip()) if part)
    if not tokens:
        return None
    parsed: list[int] = []
    seen: set[int] = set()
    for token in tokens:
        value = int(token)
        if value not in seen:
            seen.add(value)
            parsed.append(value)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="将历史已完成客户活动统一升级为结构化 Markdown（幂等、不触发后置副作用）")
    parser.add_argument("--team-id", type=int, default=None, help="只升级指定团队；默认处理全部团队")
    parser.add_argument("--days", type=int, default=None, help="只升级最近 N 天的客户活动；默认不限时间处理全部历史记录")
    parser.add_argument("--activity-ids", type=str, default=None, help="仅处理指定活动 ID（逗号或空格分隔）")
    parser.add_argument("--activity-ids-file", type=str, default=None, help="从文件读取活动 ID 列表（每行或逗号分隔）")
    parser.add_argument("--limit", type=int, default=500, help="本次最多升级的候选客户活动数量，默认 500（传 0 表示不限制）")
    parser.add_argument("--concurrency", type=int, default=2, help="并发 LLM 整理数，默认 2（同时受 ai_generation_semaphore 限流）")
    parser.add_argument(
        "--include-assistant-2",
        action="store_true",
        help="包含 ASSISTANT_2 来源活动；默认排除以保护销售助手确认冻结契约",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略 markdown_format_version 标记，强制重新整理匹配到的活动（用于定向修复历史误打标记录）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览候选记录，不调用 LLM 也不写入")
    parser.add_argument("--confirm", action="store_true", help="确认执行写入；未提供时默认 dry-run")
    args = parser.parse_args()

    dry_run = args.dry_run or not args.confirm
    activity_ids = _parse_activity_ids(args.activity_ids, args.activity_ids_file)
    limit = None if args.limit == 0 else max(1, args.limit)
    result = asyncio.run(
        customer_activity_markdown_backfill_service.backfill_activities(
            session_factory=SessionLocal,
            team_id=args.team_id,
            days=args.days,
            activity_ids=activity_ids,
            limit=limit,
            concurrency=max(1, args.concurrency),
            include_assistant_2=args.include_assistant_2,
            force=args.force,
            dry_run=dry_run,
        )
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if dry_run:
        print("DRY RUN: 未写入数据；确认无误后加 --confirm 执行。")


if __name__ == "__main__":
    main()

"""
Frontend Logs Query Tool

CLI 工具用于查询前端日志

Usage:
    python scripts/query_logs.py --date today
    python scripts/query_logs.py --context "[AIAssistant]"
    python scripts/query_logs.py --level error --date today
    python scripts/query_logs.py --user 16
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# 日志目录
LOG_DIR = Path(__file__).parent.parent / "logs"


def parse_date(date_str: str) -> str:
    """解析日期参数"""
    if date_str == "today":
        return datetime.now().strftime("%Y-%m-%d")
    elif date_str == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        return date_str  # 直接使用


def get_log_file(date_str: str) -> Path:
    """获取日志文件路径"""
    date = parse_date(date_str)
    return LOG_DIR / f"frontend-{date}.log"


def filter_logs(
    logs: list[dict],
    context: Optional[str] = None,
    level: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None
) -> list[dict]:
    """过滤日志"""
    filtered = logs

    if context:
        filtered = [log for log in filtered if log.get("context") == context]

    if level:
        filtered = [log for log in filtered if log.get("level") == level]

    if user_id:
        filtered = [log for log in filtered if log.get("userId") == user_id]

    if action:
        filtered = [log for log in filtered if log.get("action") == action]

    return filtered


def format_log(log: dict, show_data: bool = True) -> str:
    """格式化单条日志"""
    timestamp = datetime.fromtimestamp(log["timestamp"] / 1000).strftime("%H:%M:%S")
    level = log.get("level", "unknown")
    context = log.get("context", "")
    action = log.get("action", "")
    user_id = log.get("userId", "")

    base = f"{timestamp} | {level.upper():6} | {context} | {action}"

    if user_id:
        base += f" | user:{user_id}"

    if show_data and log.get("data"):
        data_str = json.dumps(log["data"], ensure_ascii=False)
        if len(data_str) > 100:
            data_str = data_str[:100] + "..."
        base += f"\n  data: {data_str}"

    return base


def main():
    parser = argparse.ArgumentParser(description="Query frontend logs")

    parser.add_argument("--date", default="today", help="Date to query (today, yesterday, or YYYY-MM-DD)")
    parser.add_argument("--context", help="Filter by context (e.g., '[AIAssistant]')")
    parser.add_argument("--level", help="Filter by level (debug, info, warn, error)")
    parser.add_argument("--user", type=int, help="Filter by user ID")
    parser.add_argument("--action", help="Filter by action")
    parser.add_argument("--no-data", action="store_true", help="Hide data field")
    parser.add_argument("--count", action="store_true", help="Only show count")

    args = parser.parse_args()

    # 获取日志文件
    log_file = get_log_file(args.date)

    if not log_file.exists():
        print(f"No log file found: {log_file}")
        sys.exit(1)

    # 读取日志
    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # 过滤
    filtered = filter_logs(
        logs,
        context=args.context,
        level=args.level,
        user_id=args.user,
        action=args.action
    )

    # 输出
    if args.count:
        print(f"Total: {len(filtered)} logs")
    else:
        print(f"=== Frontend Logs: {log_file.name} ===")
        print(f"Total: {len(filtered)} logs")
        print("-" * 80)

        for log in filtered[:100]:  # 限制输出 100 条
            print(format_log(log, show_data=not args.no_data))
            print()


if __name__ == "__main__":
    main()
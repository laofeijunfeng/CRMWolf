"""Inspect and enqueue customer-profile projection runs.

Usage:
  python scripts/diagnose_customer_profile.py [customer_id]
  python scripts/diagnose_customer_profile.py <customer_id> regenerate

The script reads only the versioned customer-profile projection and durable
refresh runs.  It does not inspect or mutate the retired customer profile
columns.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.customer import Customer
from app.models.customer_intelligence_run import CustomerIntelligenceRun
from app.models.customer_profile_projection import CustomerProfileCurrent
from app.services.customer_intelligence_refresh_service import CustomerIntelligenceRefreshService


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}\n")


def diagnose(customer_id: int | None = None) -> None:
    db = SessionLocal()
    try:
        print_section("客户档案投影状态")
        query = db.query(Customer, CustomerProfileCurrent).outerjoin(
            CustomerProfileCurrent,
            (CustomerProfileCurrent.team_id == Customer.team_id)
            & (CustomerProfileCurrent.customer_id == Customer.id),
        )
        if customer_id is not None:
            query = query.filter(Customer.id == customer_id)
        else:
            query = query.filter(
                (CustomerProfileCurrent.profile_status.in_(["NOT_READY", "STALE", "UPDATING", "FAILED"]))
                | CustomerProfileCurrent.id.is_(None)
            )
        rows = query.order_by(Customer.created_time.desc()).limit(20).all()
        if not rows:
            print("没有需要检查的客户档案投影")
            return

        for customer, current in rows:
            print(f"客户 #{customer.id}  {customer.account_name}")
            if current is None:
                print("  投影: NOT_READY（尚未建立）")
            else:
                print(f"  投影状态: {current.profile_status}")
                print(f"  当前版本: {current.last_successful_version or '无'}")
                print(f"  活跃运行: {current.active_run_id or '无'}")
                print(f"  状态说明: {current.stale_reason or '无'}")

            runs = (
                db.query(CustomerIntelligenceRun)
                .filter(
                    CustomerIntelligenceRun.team_id == customer.team_id,
                    CustomerIntelligenceRun.customer_id == customer.id,
                )
                .order_by(CustomerIntelligenceRun.id.desc())
                .limit(5)
                .all()
            )
            if runs:
                print("  最近运行:")
                for run in runs:
                    print(
                        f"    #{run.id} {run.status} {run.trigger_type} "
                        f"attempt={run.attempt_count}/{run.max_attempts} "
                        f"error={run.error_message or '无'}"
                    )
            print()
    finally:
        db.close()


async def regenerate(customer_id: int) -> None:
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.id == customer_id).one_or_none()
        if customer is None:
            print(f"客户 #{customer_id} 不存在")
            return
        service = CustomerIntelligenceRefreshService()
        request = await service.trigger_manual_refresh(
            db,
            team_id=int(customer.team_id),
            customer_id=int(customer.id),
            actor_id=None,
            scope="full",
        )
        print(f"已创建新版客户档案刷新运行: request_id={request.request_id}")
    finally:
        db.close()


if __name__ == "__main__":
    if not sys.argv[1:]:
        diagnose()
    elif len(sys.argv) > 2 and sys.argv[2] == "regenerate":
        asyncio.run(regenerate(int(sys.argv[1])))
    else:
        diagnose(int(sys.argv[1]))

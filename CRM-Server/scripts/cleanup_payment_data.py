"""
清理回款数据脚本

功能：
1. 删除所有 PAYMENT 类型的审批流程（Approval + ApprovalRecord）
2. 删除所有回款记录（PaymentRecord）
3. 重置回款计划状态为 PENDING（待回款）
4. 更新合同支付状态为 UNPAID

使用方法：
    python scripts/cleanup_payment_data.py --team-id <team_id> --confirm

注意：
    - 此操作不可逆，请先备份数据库
    - 需要指定 team_id 来限定清理范围
    - 必须添加 --confirm 参数才会真正执行
"""

import argparse
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.payment import PaymentPlan, PaymentRecord, PaymentPlanStatus
from app.models.approval import Approval, ApprovalRecord
from app.models.contract import Contract, PaymentStatus
from app.constants.business_types import BusinessType


def cleanup_payment_data(team_id: int, confirm: bool = False):
    """
    清理回款数据
    
    Args:
        team_id: 团队ID（限定清理范围）
        confirm: 是否真正执行（默认为 False，仅显示统计）
    """
    db: Session = SessionLocal()
    
    print(f"\n{'=' * 60}")
    print(f"回款数据清理脚本")
    print(f"团队ID: {team_id}")
    print(f"执行模式: {'确认执行' if confirm else '预览模式（仅统计）'}")
    print(f"{'=' * 60}\n")
    
    # 1. 统计 PAYMENT 类型的审批流程
    payment_approvals = db.query(Approval).filter(
        Approval.business_type == BusinessType.PAYMENT,
        Approval.team_id == team_id
    ).all()
    
    approval_records_count = 0
    for approval in payment_approvals:
        records = db.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == approval.id
        ).count()
        approval_records_count += records
    
    print(f"1. PAYMENT 类型审批流程:")
    print(f"   - Approval 实例数量: {len(payment_approvals)}")
    print(f"   - ApprovalRecord 数量: {approval_records_count}")
    
    # 2. 统计回款记录
    payment_records = db.query(PaymentRecord).filter(
        PaymentRecord.team_id == team_id
    ).all()
    
    print(f"\n2. 回款记录:")
    print(f"   - PaymentRecord 数量: {len(payment_records)}")
    
    # 3. 统计回款计划
    payment_plans = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id
    ).all()
    
    print(f"\n3. 回款计划:")
    print(f"   - PaymentPlan 数量: {len(payment_plans)}")
    print(f"   - 当前状态分布:")
    status_counts = {}
    for plan in payment_plans:
        status = plan.status.value if hasattr(plan.status, 'value') else plan.status
        status_counts[status] = status_counts.get(status, 0) + 1
    for status, count in status_counts.items():
        print(f"     - {status}: {count}")
    
    # 4. 统计受影响的合同
    contract_ids = set([plan.contract_id for plan in payment_plans])
    contracts = db.query(Contract).filter(
        Contract.id.in_(contract_ids),
        Contract.team_id == team_id
    ).all()
    
    print(f"\n4. 受影响的合同:")
    print(f"   - Contract 数量: {len(contracts)}")
    
    if not confirm:
        print(f"\n{'=' * 60}")
        print(f"预览模式：以上为将要清理的数据统计")
        print(f"如需执行清理，请添加 --confirm 参数")
        print(f"{'=' * 60}\n")
        db.close()
        return
    
    # 确认执行
    print(f"\n{'=' * 60}")
    print(f"开始执行清理...")
    print(f"{'=' * 60}\n")
    
    try:
        # Step 1: 删除 ApprovalRecord
        print("Step 1: 删除 ApprovalRecord...")
        for approval in payment_approvals:
            db.query(ApprovalRecord).filter(
                ApprovalRecord.approval_id == approval.id
            ).delete()
        print(f"   ✓ 已删除 {approval_records_count} 条 ApprovalRecord")
        
        # Step 2: 删除 Approval
        print("\nStep 2: 删除 Approval...")
        deleted_approvals = db.query(Approval).filter(
            Approval.business_type == BusinessType.PAYMENT,
            Approval.team_id == team_id
        ).delete()
        print(f"   ✓ 已删除 {deleted_approvals} 条 Approval")
        
        # Step 3: 删除 PaymentRecord
        print("\nStep 3: 删除 PaymentRecord...")
        deleted_records = db.query(PaymentRecord).filter(
            PaymentRecord.team_id == team_id
        ).delete()
        print(f"   ✓ 已删除 {deleted_records} 条 PaymentRecord")
        
        # Step 4: 重置 PaymentPlan 状态
        print("\nStep 4: 重置 PaymentPlan 状态...")
        for plan in payment_plans:
            plan.status = PaymentPlanStatus.PENDING
        print(f"   ✓ 已重置 {len(payment_plans)} 条 PaymentPlan 状态为 PENDING")
        
        # Step 5: 更新 Contract 支付状态
        print("\nStep 5: 更新 Contract 支付状态...")
        for contract in contracts:
            contract.payment_status = PaymentStatus.UNPAID
            contract.total_paid_amount = 0
        print(f"   ✓ 已更新 {len(contracts)} 条 Contract 支付状态为 UNPAID")
        
        # Commit
        db.commit()
        
        print(f"\n{'=' * 60}")
        print(f"✅ 清理完成！")
        print(f"{'=' * 60}\n")
        
        # 最终统计
        print(f"清理结果:")
        print(f"  - 删除 Approval: {deleted_approvals} 条")
        print(f"  - 删除 ApprovalRecord: {approval_records_count} 条")
        print(f"  - 删除 PaymentRecord: {deleted_records} 条")
        print(f"  - 重置 PaymentPlan: {len(payment_plans)} 条 → PENDING")
        print(f"  - 更新 Contract: {len(contracts)} 条 → UNPAID")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 清理失败！错误: {str(e)}")
        print(f"所有更改已回滚")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理回款数据")
    parser.add_argument("--team-id", type=int, required=True, help="团队ID（限定清理范围）")
    parser.add_argument("--confirm", action="store_true", help="确认执行清理（默认仅预览）")
    
    args = parser.parse_args()
    
    cleanup_payment_data(args.team_id, args.confirm)

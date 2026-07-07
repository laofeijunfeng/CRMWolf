"""
修复历史数据：PaymentRecord.approval_id 未关联已存在的 Approval

问题：之前 create_approval_generic 创建 Approval 后没有更新 PaymentRecord.approval_id
修复：根据 Approval.business_id 和 Approval.business_type=PAYMENT，更新 PaymentRecord.approval_id
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.approval import Approval, ApprovalStatus
from app.models.payment import PaymentRecord
from app.constants.business_types import BusinessType

def fix_payment_approval_id():
    db: Session = SessionLocal()
    
    # 查询所有 PAYMENT 类型的 Approval
    approvals = db.query(Approval).filter(
        Approval.business_type == BusinessType.PAYMENT
    ).all()
    
    fixed_count = 0
    for approval in approvals:
        # 查找对应的 PaymentRecord
        payment_record = db.query(PaymentRecord).filter(
            PaymentRecord.id == approval.business_id
        ).first()
        
        if payment_record and payment_record.approval_id is None:
            payment_record.approval_id = approval.id
            fixed_count += 1
            print(f"Fixed: PaymentRecord(id={payment_record.id}).approval_id = {approval.id}")
    
    db.commit()
    print(f"\nTotal fixed: {fixed_count} records")
    db.close()

if __name__ == "__main__":
    fix_payment_approval_id()

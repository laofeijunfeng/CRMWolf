"""
修复孤立的转化状态线索

当客户被删除后，线索状态可能仍为 CONVERTED（孤立状态）。
此脚本查找这些孤立线索并恢复为 FOLLOWING 状态。

运行方式：
  python scripts/fix_orphaned_leads.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.lead import Lead, LeadStatus
from app.models.customer import Customer
from sqlalchemy import text


def find_orphaned_leads(db):
    """查找孤立的转化状态线索（没有关联客户的 CONVERTED 状态线索）"""
    # 查询状态为 CONVERTED 的线索
    converted_leads = db.query(Lead).filter(Lead.status == LeadStatus.CONVERTED).all()

    orphaned = []
    for lead in converted_leads:
        # 检查是否有关联的客户
        customer = db.query(Customer).filter(Customer.source_lead_id == lead.id).first()
        if not customer:
            orphaned.append(lead)

    return orphaned


def fix_orphaned_leads(db):
    """修复孤立线索"""
    orphaned_leads = find_orphaned_leads(db)

    if not orphaned_leads:
        print("✓ 没有孤立的转化状态线索")
        return

    print(f"发现 {len(orphaned_leads)} 条孤立线索：")
    for lead in orphaned_leads:
        print(f"  - ID: {lead.id}, 名称: {lead.lead_name}")

    # 恢复状态
    for lead in orphaned_leads:
        lead.status = LeadStatus.FOLLOWING
        lead.version += 1

    db.commit()
    print(f"✓ 已修复 {len(orphaned_leads)} 条孤立线索，状态恢复为 FOLLOWING")


def main():
    db = SessionLocal()
    try:
        fix_orphaned_leads(db)
    except Exception as e:
        print(f"✗ 修复失败: {str(e)}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
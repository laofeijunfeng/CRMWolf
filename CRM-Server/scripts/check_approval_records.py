#!/usr/bin/env python3
"""检查审批记录"""

import sys
sys.path.append('/Users/eddie/Code/CRM')

from app.core.database import SessionLocal
from app.models.approval import Approval, ApprovalRecord
from app.models.contract import Contract

def check_approval_records():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("检查审批记录")
        print("=" * 60)

        # 检查合同 8 的信息
        contract = db.query(Contract).filter(Contract.id == 8).first()
        if contract:
            print(f"\n合同 ID: {contract.id}")
            print(f"合同编号: {contract.contract_number}")
            print(f"合同名称: {contract.contract_name}")
            print(f"合同状态: {contract.status}")
        else:
            print("\n合同 8 不存在")
            return

        # 检查审批记录
        print(f"\n查询合同 {contract.id} 的审批记录...")
        approvals = db.query(Approval).filter(Approval.contract_id == contract.id).all()
        
        if approvals:
            print(f"找到 {len(approvals)} 条审批记录：")
            for approval in approvals:
                print(f"\n审批 ID: {approval.id}")
                print(f"  状态: {approval.status}")
                print(f"  当前节点: {approval.current_node_id}")
                print(f"  提交人: {approval.submitter_name}")
                print(f"  创建时间: {approval.created_time}")
                
                # 查询审批记录
                records = db.query(ApprovalRecord).filter(ApprovalRecord.approval_id == approval.id).all()
                print(f"  审批记录数: {len(records)}")
                for record in records:
                    print(f"    - {record.action}: {record.approver_name} ({record.created_time})")
                    if record.comment:
                        print(f"      意见: {record.comment}")
        else:
            print("未找到审批记录")
            print("\n所有审批记录：")
            all_approvals = db.query(Approval).all()
            print(f"总共有 {len(all_approvals)} 条审批记录")
            for approval in all_approvals:
                print(f"  - ID: {approval.id}, 合同ID: {approval.contract_id}, 状态: {approval.status}")

    finally:
        db.close()

if __name__ == "__main__":
    check_approval_records()

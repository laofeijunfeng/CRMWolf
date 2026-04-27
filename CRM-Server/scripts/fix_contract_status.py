#!/usr/bin/env python3
"""修复合同状态，重置为草稿以便重新提交"""

import sys
sys.path.append('/Users/eddie/Code/CRM')

from app.core.database import SessionLocal
from app.models.contract import Contract, ContractStatus

def fix_contract_status(contract_id: int):
    db = SessionLocal()
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            print(f"合同 {contract_id} 不存在")
            return

        print(f"合同 ID: {contract.id}")
        print(f"当前状态: {contract.status}")
        print(f"合同名称: {contract.contract_name}")

        if contract.status == ContractStatus.DRAFT:
            print("\n合同状态已是草稿，无需修复")
        else:
            print(f"\n将合同状态重置为草稿...")
            contract.status = ContractStatus.DRAFT
            db.commit()
            print("✓ 合同状态已重置为草稿")
            print("\n请重新提交审批：")
            print(f"  POST /api/v1/approvals/contracts/{contract_id}/submit")

    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='修复合同状态')
    parser.add_argument('contract_id', type=int, help='合同ID')
    args = parser.parse_args()
    
    fix_contract_status(args.contract_id)

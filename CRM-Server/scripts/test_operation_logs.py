"""
测试统一操作记录审计服务

执行方式：
    PYTHONPATH=/Users/eddie/Code/CRM python scripts/test_operation_logs.py
"""

import sys
sys.path.insert(0, '/Users/eddie/Code/CRM')

from sqlalchemy.orm import Session
from app.core.database import get_db, engine
from app.schemas.operation_log import OperationLogCreate
from app.crud.operation_log import operation_log_crud

def test_create_operation_log():
    """测试创建操作记录"""
    db = next(get_db())
    
    try:
        print("=== 测试1: 创建线索操作记录 ===")
        
        log_data = OperationLogCreate(
            event_type="LEAD_CREATED",
            event_action="CREATE",
            primary_resource_type="LEAD",
            primary_resource_id=1,
            operator_id="ou_test001",
            operator_name="张三",
            content={
                "leadName": "某某公司",
                "source": "线上咨询",
                "city": "北京"
            }
        )
        
        log = operation_log_crud.create(db, log_data)
        print(f"✅ 创建成功: Event ID = {log.event_id}")
        
        print("\n=== 测试2: 创建客户跟进记录 ===")
        
        log_data2 = OperationLogCreate(
            event_type="MANUAL_FOLLOW_UP",
            event_action="CREATE",
            primary_resource_type="CUSTOMER",
            primary_resource_id=1,
            operator_id="ou_test001",
            operator_name="张三",
            content={
                "content": "电话沟通，需求明确",
                "method": "电话",
                "nextFollowTime": "2026-02-15"
            },
            remark="重要跟进"
        )
        
        log2 = operation_log_crud.create(db, log_data2)
        print(f"✅ 创建成功: Event ID = {log2.event_id}")
        
        print("\n=== 测试3: 创建线索转化记录 ===")
        
        log_data3 = OperationLogCreate(
            event_type="LEAD_CONVERTED",
            event_action="CONVERT",
            primary_resource_type="LEAD",
            primary_resource_id=1,
            secondary_resource_type="CUSTOMER",
            secondary_resource_id=10,
            operator_id="ou_test001",
            operator_name="张三",
            content={
                "originalLeadName": "某某公司",
                "newCustomerName": "某某科技有限公司",
                "newCustomerId": 10
            }
        )
        
        log3 = operation_log_crud.create(db, log_data3)
        print(f"✅ 创建成功: Event ID = {log3.event_id}")
        
        print("\n=== 测试4: 创建商机记录 ===")
        
        log_data4 = OperationLogCreate(
            event_type="OPPORTUNITY_CREATED",
            event_action="CREATE",
            primary_resource_type="OPPORTUNITY",
            primary_resource_id=5,
            operator_id="ou_test002",
            operator_name="李四",
            content={
                "opportunityName": "XX项目",
                "expectedAmount": 500000.00,
                "stage": "初步接触"
            }
        )
        
        log4 = operation_log_crud.create(db, log_data4)
        print(f"✅ 创建成功: Event ID = {log4.event_id}")
        
        print("\n=== 测试5: 创建合同状态变更记录 ===")
        
        log_data5 = OperationLogCreate(
            event_type="CONTRACT_STATUS_CHANGED",
            event_action="UPDATE",
            primary_resource_type="CONTRACT",
            primary_resource_id=8,
            operator_id="ou_test003",
            operator_name="王五",
            content={
                "previousStatus": "DRAFT",
                "currentStatus": "PENDING_REVIEW"
            }
        )
        
        log5 = operation_log_crud.create(db, log_data5)
        print(f"✅ 创建成功: Event ID = {log5.event_id}")
        
        print("\n=== 测试6: 按资源查询操作记录 ===")
        
        logs, total = operation_log_crud.get_by_resource(
            db=db,
            primary_resource_type="LEAD",
            primary_resource_id=1,
            skip=0,
            limit=10
        )
        
        print(f"✅ 查询成功: 共 {total} 条记录")
        for log in logs:
            print(f"   - {log.operated_at} | {log.event_type} | {log.operator_name}")
        
        print("\n=== 测试7: 按事件类型过滤查询 ===")
        
        logs2, total2 = operation_log_crud.get_by_resource(
            db=db,
            primary_resource_type="LEAD",
            primary_resource_id=1,
            skip=0,
            limit=10,
            event_types=["LEAD_CREATED", "LEAD_CONVERTED"]
        )
        
        print(f"✅ 查询成功: 共 {total2} 条记录（过滤后）")
        for log in logs2:
            print(f"   - {log.operated_at} | {log.event_type}")
        
        print("\n=== 测试8: 按操作人查询 ===")
        
        logs3, total3 = operation_log_crud.get_by_operator(
            db=db,
            operator_id="ou_test001",
            skip=0,
            limit=10
        )
        
        print(f"✅ 查询成功: ou_test001 的操作记录共 {total3} 条")
        for log in logs3:
            print(f"   - {log.operated_at} | {log.event_type} | {log.primary_resource_type}")
        
        print("\n✅ 所有测试通过！")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_create_operation_log()

"""
License 提交审批详细诊断脚本

检查 create_approval_generic 各环节是否正常。

运行方式：
python diagnose_license_approval_flow.py --application-id 7 --team-id 1
"""
import sys
import argparse
import traceback

sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.crud.crud_license_application import get_license_application
from app.crud.approval import approval_flow_crud
from app.services.approval_adapter import get_adapter
from app.constants.business_types import BusinessType
from app.models.approval import Approval, ApprovalRecord, ApprovalNode, ApprovalStatus, ApprovalAction


def diagnose(application_id: int, team_id: int):
    db: Session = SessionLocal()

    print(f"\n{'='*60}")
    print(f"License 提交审批详细诊断")
    print(f"申请ID: {application_id}, 团队ID: {team_id}")
    print(f"{'='*60}\n")

    try:
        # Step 1: 获取申请
        print("Step 1: 获取 License 申请")
        existing = get_license_application(db, team_id, application_id)
        if not existing:
            print(f"❌ 申请不存在")
            return

        print(f"✅ 申请存在")
        print(f"   - ID: {existing.id}")
        print(f"   - 状态: {existing.status}")
        print(f"   - applicant_id: '{existing.applicant_id}'")
        print(f"   - approval_id: {existing.approval_id}")

        # Step 2: 匹配审批流程
        print("\nStep 2: 匹配审批流程")
        adapter = get_adapter(BusinessType.LICENSE)
        match_kwargs = adapter.match_kwargs(existing)
        print(f"   匹配参数: {match_kwargs}")

        flow, err = approval_flow_crud.match_flow_generic(
            db, BusinessType.LICENSE, team_id, **match_kwargs
        )

        if err:
            print(f"❌ 匹配错误: {err}")
            return

        if flow is None:
            print("✅ 无审批流程，免审批直通")
            return

        print(f"✅ 匹配到流程: {flow.flow_name} (ID={flow.id})")

        # Step 3: 获取提交人信息
        print("\nStep 3: 获取提交人信息")
        submitter_id, submitter_name = adapter.get_submitter(existing)
        print(f"   submitter_id: '{submitter_id}' (类型: {type(submitter_id).__name__})")
        print(f"   submitter_name: '{submitter_name}'")

        # 关键检查：submitter_id 是否能转为 int
        print("\n   [关键检查] submitter_id 转 int:")
        try:
            submitter_id_int = int(submitter_id)
            print(f"   ✅ 可转 int: {submitter_id_int}")
        except ValueError as e:
            print(f"   ❌ 无法转 int: {e}")
            print(f"   ⚠️ 这会导致 create_approval_generic 第637行失败！")
            return

        # Step 4: 获取审批节点
        print("\nStep 4: 获取审批节点")
        first_node = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == flow.id,
            ApprovalNode.node_order == 1
        ).first()

        if first_node:
            print(f"✅ 首节点存在: {first_node.node_name} (ID={first_node.id})")
        else:
            print(f"⚠️ 无首节点（审批流程未配置节点）")

        # Step 5: 模拟 Approval 创建
        print("\nStep 5: 模拟 Approval 创建（不实际写入）")
        try:
            # 检查 Approval 表约束
            print("   检查 Approval 表字段:")
            print(f"   - business_type: '{BusinessType.LICENSE}' (长度: {len(BusinessType.LICENSE)})")
            print(f"   - business_id: {application_id}")
            print(f"   - flow_id: {flow.id}")
            print(f"   - team_id: {team_id}")
            print(f"   - submitter_id: '{submitter_id}'")
            print(f"   - current_node_id: {first_node.id if first_node else None}")

            # 创建 Approval 对象（不写入）
            test_approval = Approval(
                business_type=BusinessType.LICENSE,
                business_id=application_id,
                contract_id=None,  # LICENSE 无 contract_id
                flow_id=flow.id,
                team_id=team_id,
                current_node_id=first_node.id if first_node else None,
                status=ApprovalStatus.PENDING,
                submitter_id=submitter_id,
                submitter_name=submitter_name or "测试用户",
            )
            print(f"   ✅ Approval 对象创建成功")

        except Exception as e:
            print(f"   ❌ Approval 对象创建失败: {e}")
            traceback.print_exc()
            return

        # Step 6: 模拟 ApprovalRecord 创建
        print("\nStep 6: 模拟 ApprovalRecord 创建（不实际写入）")
        try:
            print("   检查 ApprovalRecord 表字段:")
            print(f"   - approver_id: '{submitter_id}' (nullable=False)")
            print(f"   - approver_name: '{submitter_name}'")
            print(f"   - action: '{ApprovalAction.SUBMIT}' (nullable=False)")

            # 创建 ApprovalRecord 对象（不写入）
            test_record = ApprovalRecord(
                approval_id=999,  # 模拟 ID
                node_id=first_node.id if first_node else None,
                approver_id=submitter_id,
                approver_name=submitter_name or "测试用户",
                action=ApprovalAction.SUBMIT,
                comment=None,
                team_id=team_id,
            )
            print(f"   ✅ ApprovalRecord 对象创建成功")

        except Exception as e:
            print(f"   ❌ ApprovalRecord 对象创建失败: {e}")
            traceback.print_exc()
            return

        # Step 7: 检查数据库外键约束
        print("\nStep 7: 检查数据库约束")
        try:
            # 查询 Approval 表最大 ID
            max_approval_id = db.query(Approval.id).order_by(Approval.id.desc()).first()
            print(f"   Approval 表最大 ID: {max_approval_id[0] if max_approval_id else '空表'}")

            # 查询 ApprovalRecord 表最大 ID
            max_record_id = db.query(ApprovalRecord.id).order_by(ApprovalRecord.id.desc()).first()
            print(f"   ApprovalRecord 表最大 ID: {max_record_id[0] if max_record_id else '空表'}")

            # 检查是否有 LICENSE 类型的 Approval
            license_approvals = db.query(Approval).filter(
                Approval.business_type == BusinessType.LICENSE
            ).all()
            print(f"   已有 LICENSE Approval 数量: {len(license_approvals)}")

        except Exception as e:
            print(f"   ❌ 数据库查询失败: {e}")
            traceback.print_exc()

        # Step 8: 检查 approval_id 外键约束
        print("\nStep 8: 检查 approval_id 外键约束")
        try:
            from sqlalchemy import text
            result = db.execute(text("""
                SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'crm_license_applications'
                AND COLUMN_NAME = 'approval_id'
            """)).fetchone()

            if result:
                print(f"   ✅ 外键约束存在:")
                print(f"      约束名: {result[0]}")
                print(f"      引用表: {result[2]}")
                print(f"      引用列: {result[3]}")
            else:
                print(f"   ⚠️ approval_id 无外键约束（迁移可能未执行）")

        except Exception as e:
            print(f"   ❌ 外键查询失败: {e}")

        # 总结
        print(f"\n{'='*60}")
        print("诊断总结")
        print(f"{'='*60}")
        print("""
如果所有检查都通过，理论上 create_approval_generic 应该成功。

如果实际失败，可能原因：
1. submitter_id 格式问题（非数字）
2. ApprovalRecord approver_id 约束问题
3. 数据库连接/权限问题
4. 其他隐藏约束

请查看服务器日志获取详细错误信息。
""")

    except Exception as e:
        print(f"\n❌ 诊断异常: {type(e).__name__}: {e}")
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="License 提交审批详细诊断")
    parser.add_argument("--application-id", type=int, required=True)
    parser.add_argument("--team-id", type=int, required=True)

    args = parser.parse_args()
    diagnose(args.application_id, args.team_id)
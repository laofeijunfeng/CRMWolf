"""
License 申请提交诊断脚本

用于排查 License 提交审批时 DATABASE_ERROR 的根本原因。

运行方式：
python diagnose_license_submit.py --application-id 7 --team-id 1
"""
import sys
import argparse
from sqlalchemy.orm import Session

# 添加项目路径
sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

from app.core.database import SessionLocal
from app.crud.crud_license_application import get_license_application
from app.crud.approval import approval_flow_crud, approval_crud
from app.services.approval_adapter import get_adapter
from app.constants.business_types import BusinessType
from app.models.license_application import LicenseApplicationStatus


def diagnose(application_id: int, team_id: int):
    """诊断 License 提交流程"""
    db: Session = SessionLocal()

    print(f"\n=== License 申请提交诊断 ===")
    print(f"申请ID: {application_id}, 团队ID: {team_id}\n")

    try:
        # Step 1: 检查申请是否存在
        print("Step 1: 检查 License 申请...")
        existing = get_license_application(db, team_id, application_id)
        if not existing:
            print(f"❌ 申请不存在: ID={application_id}")
            return
        print(f"✅ 申请存在: {existing.application_number}")
        print(f"   状态: {existing.status}")
        print(f"   License类型: {existing.license_type}")
        print(f"   Applicant ID: {existing.applicant_id}")

        # Step 2: 检查审批流程匹配
        print("\nStep 2: 检查审批流程匹配...")
        adapter = get_adapter(BusinessType.LICENSE)
        match_kwargs = adapter.match_kwargs(existing)
        print(f"   匹配参数: {match_kwargs}")

        flow, err = approval_flow_crud.match_flow_generic(
            db,
            BusinessType.LICENSE,
            team_id,
            **match_kwargs
        )

        if err:
            print(f"❌ 流程匹配错误: {err}")
            return

        if flow is None:
            print("✅ 未匹配到审批流程，将免审批直通")
            print("   提交应成功（状态从 DRAFT -> ISSUED）")
            return

        print(f"✅ 匹配到审批流程: {flow.flow_name} (ID={flow.id})")

        # Step 3: 检查审批节点
        print("\nStep 3: 检查审批流程节点...")
        from app.models.approval import ApprovalNode
        nodes = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == flow.id,
            ApprovalNode.team_id == team_id
        ).order_by(ApprovalNode.node_order).all()

        if not nodes:
            print("❌ 流程没有配置审批节点！")
            print("   这可能导致提交失败")
            return

        print(f"✅ 流程有 {len(nodes)} 个节点:")
        for node in nodes:
            print(f"   - {node.node_name} (order={node.node_order}, role={node.approve_role})")

        first_node = nodes[0] if nodes else None

        # Step 4: 检查提交人信息
        print("\nStep 4: 检查提交人信息...")
        submitter_id, submitter_name = adapter.get_submitter(existing)
        print(f"   submitter_id: '{submitter_id}'")
        print(f"   submitter_name: '{submitter_name}'")

        # 尝试转换 submitter_id 为 int
        try:
            user_id_int = int(submitter_id)
            print(f"   ✅ 可转换为 int: {user_id_int}")

            # 检查用户是否存在
            from app.crud.user import user_crud
            user = user_crud.get_by_id(db, user_id_int)
            if user:
                print(f"   ✅ 用户存在: {user.name}")
            else:
                print(f"   ⚠️ 用户不存在: ID={user_id_int}")
        except ValueError as e:
            print(f"   ❌ 无法转换为 int: {e}")
            print("   这可能导致 create_approval_generic 失败！")

        # Step 5: 模拟创建审批实例（不实际提交）
        print("\nStep 5: 检查 Approval 表结构...")
        from app.models.approval import Approval
        print(f"   Approval 表名: {Approval.__tablename__}")

        # 检查所有 LICENSE 类型的审批
        existing_approvals = db.query(Approval).filter(
            Approval.business_type == BusinessType.LICENSE
        ).all()
        print(f"   已有 LICENSE 审批数: {len(existing_approvals)}")

        # Step 6: 总结诊断结果
        print("\n=== 诊断总结 ===")
        if flow and nodes:
            print("✅ 流程配置完整，理论上提交应该成功")
            print("   如果实际失败，请检查服务器日志获取详细错误")
        elif flow and not nodes:
            print("❌ 问题根源：审批流程缺少节点配置")
            print("   解决方案：为流程添加审批节点")
        elif flow is None:
            print("✅ 无审批流程，应该免审批直通")
            print("   如果实际失败，可能其他问题")

    except Exception as e:
        print(f"\n❌ 诊断过程异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="License 申请提交诊断")
    parser.add_argument("--application-id", type=int, required=True, help="License 申请ID")
    parser.add_argument("--team-id", type=int, required=True, help="团队ID")

    args = parser.parse_args()
    diagnose(args.application_id, args.team_id)
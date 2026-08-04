"""
ApprovalTransactionManager 单元测试

测试目标：验证 ApprovalTransactionManager 核心方法的事务原子性和异常处理

测试覆盖：
1. create_with_approval 方法
2. submit_for_approval 方法
3. 异常处理分支
4. approval_phase 状态流转
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

import app.services.approval_transaction_manager as transaction_manager_module
from app.services.approval_transaction_manager import ApprovalTransactionManager
from app.constants.approval_phase import ApprovalPhase
from app.models.approval import Approval, ApprovalStatus, ApprovalFlow
from app.constants.business_types import BusinessType


class TestApprovalTransactionManager:
    """ApprovalTransactionManager 单元测试"""

    @pytest.fixture
    def transaction_manager(self):
        return ApprovalTransactionManager()

    @pytest.fixture
    def mock_db(self):
        """Mock 数据库会话"""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_flow(self):
        """Mock 审批流程"""
        flow = Mock(spec=ApprovalFlow)
        flow.id = 1
        flow.flow_name = "测试审批流程"
        return flow

    # ========================================================================
    # create_with_approval 测试用例
    # ========================================================================

    def test_create_with_approval_success(self, transaction_manager, mock_db, mock_flow):
        """
        测试：创建单据 + 审批成功

        验证点：
        - entity.approval_phase = PENDING_REVIEW
        - approval 实例正确创建
        - adapter.on_submit 正确调用
        - 事务正确 commit
        """
        # TODO: 实现测试逻辑
        pass

    def test_create_with_approval_no_flow(self, transaction_manager, mock_db):
        """
        测试：审批流程未匹配

        验证点：
        - 单据保留（approval_phase = DRAFT）
        - 返回错误提示："请先配置审批流程"
        - 事务正确 commit（保留单据）
        """
        # TODO: 实现测试逻辑
        pass

    def test_create_with_approval_flow_query_failure(self, transaction_manager, mock_db):
        """
        测试：审批流程查询失败（数据库异常）

        验证点：
        - rollback 事务
        - 返回错误提示："系统异常：审批流程查询失败"
        - entity 和 approval 都为 None
        """
        # TODO: 实现测试逻辑
        pass

    def test_create_with_approval_create_approval_failure(self, transaction_manager, mock_db, mock_flow):
        """
        测试：审批实例创建失败

        验证点：
        - rollback 事务
        - 返回错误提示："系统异常：审批创建失败"
        - entity 和 approval 都为 None
        """
        # TODO: 实现测试逻辑
        pass

    def test_create_with_approval_notification_failure(self, transaction_manager, mock_db, mock_flow):
        """
        测试：通知发送失败（不阻断业务流程）

        验证点：
        - approval_phase 正确切换为 PENDING_REVIEW
        - 事务正确 commit
        - 错误日志正确记录
        - 不阻断业务流程
        """
        # TODO: 实现测试逻辑
        pass

    @pytest.mark.asyncio
    async def test_send_notification_awaits_pending_notification_service(self, transaction_manager, mock_db):
        approval = Mock()
        approval.id = 86
        approval.business_type = BusinessType.OPPORTUNITY
        approval.business_id = 30
        approval.submitter_name = "张三"
        approval.flow = Mock(flow_name="商机审批")
        approval.current_node = Mock(
            approve_role="SALES_MANAGER",
            node_name="销售经理审批",
            notify_user_ids=["11"],
        )
        entity = Mock()

        sent_payload = {}

        class FakeAdapter:
            def get_name(self, entity):
                return "企业版采购"

        async def fake_notify_approval_pending(**kwargs):
            sent_payload.update(kwargs)
            return {"success": 1, "failed": 0, "skipped": 0}

        with patch.object(transaction_manager_module, "get_adapter", return_value=FakeAdapter()), \
            patch.object(transaction_manager_module, "get_approval_type_name", return_value="商机"), \
            patch.object(transaction_manager_module, "get_approval_customer_name", return_value="测试客户"), \
            patch.object(transaction_manager_module, "get_approval_card_fields", return_value={"商机": "企业版采购"}), \
            patch("app.crud.role.role_crud.get_by_code", return_value=Mock(id=7)), \
            patch(
                "app.crud.role.role_crud.get_role_users",
                return_value=[Mock(id=11), Mock(id=12)],
            ), \
            patch(
                "app.services.feishu_notification.feishu_notification_service.notify_approval_pending",
                side_effect=fake_notify_approval_pending,
            ):
            result = await transaction_manager.send_notification(mock_db, approval, entity, team_id=2)

        assert result == {"success": 1, "failed": 0, "skipped": 0}
        assert sent_payload["db"] is mock_db
        assert sent_payload["team_id"] == 2
        assert sent_payload["user_ids"] == [11]
        assert sent_payload["entity_type"] == BusinessType.OPPORTUNITY
        assert sent_payload["entity_name"] == "企业版采购"
        assert sent_payload["flow_name"] == "商机审批"
        assert sent_payload["node_name"] == "销售经理审批"

    # ========================================================================
    # submit_for_approval 测试用例
    # ========================================================================

    def test_submit_for_approval_success(self, transaction_manager, mock_db, mock_flow):
        """
        测试：手动提交审批成功（Invoice/License 场景）

        验证点：
        - approval_phase = PENDING_REVIEW
        - approval 实例正确创建
        - adapter.on_submit 正确调用
        - 事务正确 commit
        """
        # TODO: 实现测试逻辑
        pass

    def test_submit_for_approval_resubmit_after_rejected(self, transaction_manager, mock_db, mock_flow):
        """
        测试：驳回后重新提交审批

        验证点：
        - approval_phase = REJECTED → DRAFT → PENDING_REVIEW
        - 旧 Approval 实例被删除
        - 新 Approval 实例被创建
        - 事务正确 commit
        """
        entity = Mock()
        entity.id = 30
        entity.approval_phase = ApprovalPhase.REJECTED.value

        old_approval = Mock()
        old_approval.id = 88

        new_approval = Mock(spec=Approval)
        new_approval.id = 89

        class FakeAdapter:
            def get_entity(self, db, entity_id, team_id):
                assert db is mock_db
                assert entity_id == 30
                assert team_id == 2
                return entity

            def match_kwargs(self, entity):
                return {"amount": 1000, "license_type": None}

            def on_submit(self, db, entity):
                entity.on_submit_called = True

        with patch.object(transaction_manager_module, "get_adapter", return_value=FakeAdapter()), \
            patch.object(
                transaction_manager_module.approval_crud,
                "get_by_entity",
                return_value=old_approval,
            ) as mock_get_old, \
            patch.object(
                transaction_manager_module.approval_flow_crud,
                "match_flow_generic",
                return_value=(mock_flow, None),
            ) as mock_match_flow, \
            patch.object(
                transaction_manager_module.approval_crud,
                "create_approval_only",
                return_value=new_approval,
            ) as mock_create_approval:
            approval, error = transaction_manager.submit_for_approval(
                mock_db,
                business_type=BusinessType.OPPORTUNITY,
                entity_id=30,
                team_id=2,
                submitter_id="user-1",
                submitter_name="张三",
                send_notification=False,
            )

        assert error is None
        assert approval is new_approval
        mock_get_old.assert_called_once_with(mock_db, BusinessType.OPPORTUNITY, 30, 2)
        mock_db.delete.assert_called_once_with(old_approval)
        mock_match_flow.assert_called_once_with(
            mock_db,
            BusinessType.OPPORTUNITY,
            2,
            1000,
            None,
        )
        mock_create_approval.assert_called_once_with(
            mock_db,
            business_type=BusinessType.OPPORTUNITY,
            business_id=30,
            team_id=2,
            flow=mock_flow,
            submitter_id="user-1",
            submitter_name="张三",
        )
        assert entity.approval_phase == ApprovalPhase.PENDING_REVIEW.value
        assert entity.on_submit_called is True
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(new_approval)

    def test_submit_for_approval_invalid_phase(self, transaction_manager, mock_db):
        """
        测试：approval_phase 不允许提交（非 DRAFT 或 REJECTED）

        验证点：
        - 返回错误提示："单据状态不允许提交审批"
        - 不创建审批实例
        """
        # TODO: 实现测试逻辑
        pass

    def test_submit_for_approval_entity_not_found(self, transaction_manager, mock_db):
        """
        测试：业务单据不存在

        验证点：
        - 返回错误提示："业务单据不存在"
        - 不创建审批实例
        """
        # TODO: 实现测试逻辑
        pass

    # ========================================================================
    # Approval Engine 联动测试用例
    # ========================================================================

    def test_approve_phase_transition_last_node(self, mock_db):
        """
        测试：最后节点通过，approval_phase 流转

        验证点：
        - Approval.status = APPROVED
        - entity.approval_phase = APPROVED
        - adapter.on_approved 正确调用
        """
        # TODO: 实现测试逻辑
        pass

    def test_approve_phase_transition_middle_node(self, mock_db):
        """
        测试：多级审批中间节点通过，approval_phase 保持 PENDING_REVIEW

        验证点：
        - approval_phase 保持 PENDING_REVIEW
        - Approval.current_node_id 移动到下一节点
        """
        # TODO: 实现测试逻辑
        pass

    def test_reject_phase_transition(self, mock_db):
        """
        测试：审批拒绝，approval_phase 流转

        验证点：
        - Approval.status = REJECTED
        - entity.approval_phase = REJECTED
        - adapter.on_rejected 正确调用
        """
        # TODO: 实实现测试逻辑
        pass

    def test_cancel_phase_transition(self, mock_db):
        """
        测试：撤回审批，approval_phase 流转

        验证点：
        - Approval.status = CANCELLED
        - entity.approval_phase = DRAFT
        - adapter.on_cancelled 正确调用
        """
        # TODO: 实现测试逻辑
        pass

    # ========================================================================
    # Adapter 状态切换测试用例
    # ========================================================================

    def test_contract_adapter_on_rejected(self, mock_db):
        """
        测试：ContractAdapter.on_rejected 不切换原有 status

        验证点：
        - approval_phase 切换由 Approval Engine 管理
        - 原有 status 保持 PENDING_REVIEW（不变）
        """
        # TODO: 实现测试逻辑
        pass

    def test_payment_adapter_on_rejected(self, mock_db):
        """
        测试：PaymentRecordAdapter.on_rejected 不切换 confirmation_status

        验证点：
        - approval_phase 切换由 Approval Engine 管理
        - confirmation_status 保持 PENDING（不变）
        """
        # TODO: 实现测试逻辑
        pass

    def test_payment_adapter_on_cancelled(self, mock_db):
        """
        测试：PaymentRecordAdapter.on_cancelled 保持 confirmation_status 为 PENDING

        验证点：
        - approval_phase 切换由 Approval Engine 管理
        - confirmation_status 保持 PENDING（重新提交能力由 approval_phase=DRAFT 表达）
        """
        # TODO: 实现测试逻辑
        pass

    def test_license_adapter_on_submit(self, mock_db):
        """
        测试：LicenseApplicationAdapter.on_submit 使用 PENDING_REVIEW（统一命名）

        验证点：
        - entity.status = PENDING_REVIEW（不是 PENDING）
        """
        # TODO: 实现测试逻辑
        pass

    # ========================================================================
    # 数据迁移验证测试用例
    # ========================================================================

    def test_contract_migration_approval_phase_mapping(self, mock_db):
        """
        测试：Contract 历史数据 approval_phase 映射正确

        验证点：
        - DRAFT → draft
        - PENDING_REVIEW → pending_review
        - SIGNED/EXPIRED/TERMINATED → approved
        """
        # TODO: 实现测试逻辑
        pass

    def test_payment_migration_approval_phase_mapping(self, mock_db):
        """
        测试：Payment 历史数据 approval_phase 映射正确（包含驳回修复）

        验证点：
        - 未提交审批的 PENDING → draft
        - 审批中的 PENDING → pending_review
        - CONFIRMED → approved
        - 审批拒绝的 PENDING → rejected（关键修复）
        - DISPUTED → rejected
        """
        # TODO: 实现测试逻辑
        pass

    def test_invoice_migration_approval_phase_mapping(self, mock_db):
        """
        测试：Invoice 历史数据 approval_phase 映射正确

        验证点：
        - DRAFT → draft
        - PENDING_REVIEW → pending_review
        - APPROVED/ISSUED → approved
        - REJECTED → rejected
        """
        # TODO: 实现测试逻辑
        pass

    def test_license_migration_approval_phase_mapping(self, mock_db):
        """
        测试：License 历史数据 approval_phase 映射正确（包含审批拒绝修复）

        验证点：
        - DRAFT → draft
        - PENDING/PENDING_REVIEW → pending_review
        - APPROVED/ISSUED → approved
        - REJECTED → rejected
        """
        # TODO: 实现测试逻辑
        pass


# ========================================================================
# 集成测试建议
# ========================================================================

"""
建议编写以下集成测试：

1. 端到端审批流程测试
   - 创建合同 → 提交审批 → 审批通过 → 验证 approval_phase 流转
   - 创建回款 → 提交审批 → 审批拒绝 → 验证 approval_phase = rejected
   - 创建发票 → 提交审批 → 撤回审批 → 验证 approval_phase = draft

2. 多级审批测试
   - 3级审批流程 → 中间节点通过 → 验证 approval_phase 保持 pending_review
   - 最后节点通过 → 验证 approval_phase = approved

3. 驳回后重新提交测试
   - 审批拒绝 → 验证 approval_phase = rejected
   - 修改单据 → 重新提交 → 验证 approval_phase 流转正确
   - 验证旧 Approval 实例被删除

4. 数据迁移验证测试
   - 执行迁移后，查询历史数据 → 验证 approval_phase 映射正确
   - Payment 驳回状态修复验证
   - License 审批拒绝状态修复验证
"""


# ========================================================================
# 测试运行命令
# ========================================================================

"""
运行测试命令：

pytest tests/unit/approval/test_transaction_manager.py -v

覆盖率测试：

pytest tests/unit/approval/test_transaction_manager.py --cov=app.services.approval_transaction_manager --cov-report=html
"""

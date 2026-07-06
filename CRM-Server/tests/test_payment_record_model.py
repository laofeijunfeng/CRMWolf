"""
Tests for PaymentRecord model approval relationship.

Task 1.3: Add approval_id field and current_approver_name method to PaymentRecord.
"""
import pytest
from decimal import Decimal
from datetime import date

from app.models.payment import PaymentRecord, PaymentPlan
from app.models.approval import Approval, ApprovalNode, ApprovalStatus


class TestPaymentRecordApprovalRelationship:
    """Test PaymentRecord approval relationship and methods."""

    def test_payment_record_approval_id_field(self):
        """Test PaymentRecord has approval_id field."""
        record = PaymentRecord(
            id=1,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('5000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123',
            approval_id=1
        )
        assert record.approval_id == 1

    def test_payment_record_approval_id_nullable(self):
        """Test PaymentRecord approval_id is nullable."""
        record = PaymentRecord(
            id=2,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('3000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123',
            approval_id=None
        )
        assert record.approval_id is None

    def test_payment_record_approval_relationship(self):
        """Test PaymentRecord has approval relationship."""
        record = PaymentRecord(
            id=3,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('5000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123',
            approval_id=1
        )

        # Create approval and associate
        approval = Approval(
            id=1,
            team_id=1,
            business_type='PAYMENT',
            status=ApprovalStatus.PENDING,
            submitter_id='user_123'
        )

        # Set up relationship
        record.approval = approval

        assert record.approval is not None
        assert record.approval.status == ApprovalStatus.PENDING

    def test_payment_record_get_current_approver_name_with_pending_approval(self):
        """Test get_current_approver_name returns node name when approval is pending."""
        record = PaymentRecord(
            id=4,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('5000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123'
        )

        # Create approval with current_node
        approval = Approval(
            id=1,
            team_id=1,
            business_type='PAYMENT',
            status=ApprovalStatus.PENDING,
            submitter_id='user_123'
        )

        # Create current node
        current_node = ApprovalNode(
            id=1,
            team_id=1,
            flow_id=1,
            node_name='财务总监审批',
            node_code='FINANCE_DIRECTOR',
            node_order=1,
            approve_role='FINANCE_DIRECTOR'
        )

        # Set up relationships
        approval.current_node = current_node
        record.approval = approval

        # Should return the current node name
        result = record.get_current_approver_name()
        assert result == '财务总监审批'

    def test_payment_record_get_current_approver_name_no_approval(self):
        """Test get_current_approver_name returns None when no approval."""
        record = PaymentRecord(
            id=5,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('5000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123',
            approval_id=None
        )

        assert record.get_current_approver_name() is None

    def test_payment_record_get_current_approver_name_approved_status(self):
        """Test get_current_approver_name returns None when approval is already approved."""
        record = PaymentRecord(
            id=6,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('5000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123'
        )

        approval = Approval(
            id=1,
            team_id=1,
            business_type='PAYMENT',
            status=ApprovalStatus.APPROVED,  # Already approved
            submitter_id='user_123'
        )

        record.approval = approval

        assert record.get_current_approver_name() is None

    def test_payment_record_get_current_approver_name_no_current_node(self):
        """Test get_current_approver_name returns None when no current_node."""
        record = PaymentRecord(
            id=7,
            team_id=1,
            payment_plan_id=1,
            actual_amount=Decimal('5000.00'),
            payment_date=date(2026, 7, 6),
            creator_id='user_123'
        )

        approval = Approval(
            id=1,
            team_id=1,
            business_type='PAYMENT',
            status=ApprovalStatus.PENDING,
            submitter_id='user_123',
            current_node_id=None
        )

        record.approval = approval

        assert record.get_current_approver_name() is None
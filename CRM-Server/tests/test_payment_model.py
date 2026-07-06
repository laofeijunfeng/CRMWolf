"""Tests for PaymentPlan model computed properties."""
import pytest
from decimal import Decimal
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus


class TestPaymentPlanRemainingAmount:
    """Tests for remaining_amount computed property."""

    def test_remaining_amount_with_payment_records(self):
        """Test remaining_amount with payment records."""
        plan = PaymentPlan(
            planned_amount=Decimal('10000.00')
        )
        # Simulate payment_records relationship
        plan.payment_records = [
            PaymentRecord(actual_amount=Decimal('3000.00'), payment_date=None),
            PaymentRecord(actual_amount=Decimal('2000.00'), payment_date=None),
        ]
        assert plan.remaining_amount == Decimal('5000.00')

    def test_remaining_amount_fully_paid(self):
        """Test remaining_amount when fully paid."""
        plan = PaymentPlan(
            planned_amount=Decimal('10000.00')
        )
        plan.payment_records = [
            PaymentRecord(actual_amount=Decimal('10000.00'), payment_date=None),
        ]
        assert plan.remaining_amount == Decimal('0.00')

    def test_remaining_amount_no_records(self):
        """Test remaining_amount when no payment records yet."""
        plan = PaymentPlan(
            planned_amount=Decimal('10000.00')
        )
        plan.payment_records = []
        assert plan.remaining_amount == Decimal('10000.00')

    def test_remaining_amount_overpaid(self):
        """Test remaining_amount when paid more than planned (edge case)."""
        plan = PaymentPlan(
            planned_amount=Decimal('10000.00')
        )
        plan.payment_records = [
            PaymentRecord(actual_amount=Decimal('12000.00'), payment_date=None),
        ]
        # Should return negative amount when overpaid
        assert plan.remaining_amount == Decimal('-2000.00')


class TestPaymentPlanInvoicedAmount:
    """Tests for invoiced_amount computed property."""

    def test_invoiced_amount_with_issued_invoices(self):
        """Test invoiced_amount with ISSUED invoices."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        plan.invoice_applications = [
            InvoiceApplication(invoice_amount=Decimal('5000.00'), status=InvoiceApplicationStatus.ISSUED),
            InvoiceApplication(invoice_amount=Decimal('3000.00'), status=InvoiceApplicationStatus.PENDING_REVIEW),
            InvoiceApplication(invoice_amount=Decimal('2000.00'), status=InvoiceApplicationStatus.ISSUED),
        ]
        # Only ISSUED invoices count: 5000 + 2000 = 7000
        assert plan.invoiced_amount == Decimal('7000.00')

    def test_invoiced_amount_no_issued_invoices(self):
        """Test invoiced_amount when no ISSUED invoices."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        plan.invoice_applications = [
            InvoiceApplication(invoice_amount=Decimal('5000.00'), status=InvoiceApplicationStatus.DRAFT),
            InvoiceApplication(invoice_amount=Decimal('3000.00'), status=InvoiceApplicationStatus.PENDING_REVIEW),
        ]
        assert plan.invoiced_amount == Decimal('0.00')

    def test_invoiced_amount_empty_relationship(self):
        """Test invoiced_amount when no invoice applications."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        plan.invoice_applications = []
        assert plan.invoiced_amount == Decimal('0.00')

    def test_invoiced_amount_no_relationship_attribute(self):
        """Test invoiced_amount when relationship attribute not set (detached instance)."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        # Don't set invoice_applications - simulates detached instance
        assert plan.invoiced_amount == Decimal('0.00')


class TestPaymentPlanInvoiceCount:
    """Tests for invoice_count computed property."""

    def test_invoice_count_with_applications(self):
        """Test invoice_count with applications."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        plan.invoice_applications = [
            InvoiceApplication(invoice_amount=Decimal('5000.00'), status=InvoiceApplicationStatus.ISSUED),
            InvoiceApplication(invoice_amount=Decimal('3000.00'), status=InvoiceApplicationStatus.DRAFT),
        ]
        assert plan.invoice_count == 2

    def test_invoice_count_empty(self):
        """Test invoice_count when empty."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        plan.invoice_applications = []
        assert plan.invoice_count == 0

    def test_invoice_count_no_relationship_attribute(self):
        """Test invoice_count when relationship attribute not set (detached instance)."""
        plan = PaymentPlan(planned_amount=Decimal('10000.00'))
        # Don't set invoice_applications - simulates detached instance
        assert plan.invoice_count == 0
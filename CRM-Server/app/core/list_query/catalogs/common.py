from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Integer, String, and_, case, cast, exists, func, literal, or_, select

from app.constants.business_types import BusinessType
from app.core.list_query.catalog import ListQueryField
from app.core.list_query.hours import hours_between
from app.core.list_query.license_status import license_status_expression
from app.core.list_query.types import FilterCondition, ListQueryContext
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMember
from app.models.invoice import (
    InvoiceApplication,
    InvoiceRedOffset,
    InvoiceReissueApplication,
    InvoiceReissueApplicationStatus,
)
from app.models.license_application import LicenseApplication, LicenseApplicationStatus, LicenseType
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentRecord
from app.models.sales_commitment import (
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskStatus,
)
from app.models.user import User


def resolve_source_ids(values: list[Any], context: ListQueryContext) -> list[Any]:
    from app.services.acquisition_source_service import resolve_public_ids_to_ids

    if context.db is None or context.team_id is None:
        return []
    return resolve_public_ids_to_ids(context.db, context.team_id, values)


def source_field(*, filter_column, sort_column) -> ListQueryField:
    return ListQueryField(
        key="source",
        type="enum",
        expression=filter_column,
        sort_expression=sort_column,
        resolve_values=resolve_source_ids,
        neq_includes_null=True,
    )


def user_name_expression(user_id_expression):
    return (
        select(User.name)
        .where(User.id == cast(user_id_expression, Integer))
        .limit(1)
        .correlate_except(User)
        .scalar_subquery()
    )


def related_name_expression(model, fk_expression, column, *, team_id_expression=None):
    predicates = [model.id == fk_expression]
    if team_id_expression is not None:
        predicates.append(model.team_id == team_id_expression)
    return select(column).where(*predicates).limit(1).correlate_except(model).scalar_subquery()


def person_field(key: str, expression, *, sort_expression=None) -> ListQueryField:
    return ListQueryField(
        key=key,
        type="enum",
        expression=expression,
        sort_expression=sort_expression,
        resolve_person_aliases=True,
    )


def case_order(column, values: Sequence[Any]):
    return case(*[(column == value, index) for index, value in enumerate(values)], else_=99)


def latest_official_issued_license(column):
    return (
        select(column)
        .where(
            LicenseApplication.contract_id == Contract.id,
            LicenseApplication.team_id == Contract.team_id,
            LicenseApplication.license_type == LicenseType.OFFICIAL,
            LicenseApplication.status == LicenseApplicationStatus.ISSUED,
        )
        .order_by(LicenseApplication.last_modified_time.desc(), LicenseApplication.id.desc())
        .limit(1)
        .correlate_except(LicenseApplication)
        .scalar_subquery()
    )


def customer_license_status_expression(context: ListQueryContext):
    return license_status_expression(
        Customer.license_expiry_date,
        Customer.license_type,
        context.business_today(),
    )


def collaborators_name_expression():
    return (
        select(User.name)
        .where(
            CustomerMember.customer_id == Customer.id,
            CustomerMember.team_id == Customer.team_id,
            CustomerMember.is_active.is_(True),
            User.id == cast(CustomerMember.user_id, Integer),
        )
        .order_by(User.name.asc())
        .limit(1)
        .correlate_except(CustomerMember, User)
        .scalar_subquery()
    )


def collaborators_predicate(
    condition: FilterCondition, field: ListQueryField, context: ListQueryContext, parsed_value: Any
):
    member_match = and_(
        CustomerMember.customer_id == Customer.id,
        CustomerMember.team_id == Customer.team_id,
        CustomerMember.is_active.is_(True),
        User.id == cast(CustomerMember.user_id, Integer),
    )
    if condition.op == "is_empty":
        return ~exists().where(member_match)
    if condition.op == "is_not_empty":
        return exists().where(member_match)
    values = parsed_value if isinstance(parsed_value, list) else [parsed_value]
    name_clauses = []
    for value in values:
        if value is None or value == "":
            continue
        text = str(value)
        if condition.op in {"contains", "not_contains"}:
            name_clauses.append(User.name.ilike(f"%{text}%"))
        else:
            name_clauses.append(User.name == text)
    if not name_clauses:
        return None
    name_match = or_(*name_clauses)
    matched = exists().where(and_(member_match, name_match))
    if condition.op in {"eq", "contains"}:
        return matched
    return ~matched


def keyword_predicate(*expressions):
    def builder(condition: FilterCondition, field: ListQueryField, context: ListQueryContext, parsed_value: Any):
        if condition.op in {"is_empty", "is_not_empty"}:
            clauses = []
            for expression in expressions:
                if condition.op == "is_empty":
                    clauses.append(or_(expression.is_(None), expression == ""))
                else:
                    clauses.append(and_(expression.is_not(None), expression != ""))
            return and_(*clauses) if condition.op == "is_empty" else or_(*clauses)
        values = parsed_value if isinstance(parsed_value, list) else [parsed_value]
        clauses = []
        for value in values:
            if value is None or value == "":
                continue
            like = f"%{value}%"
            match = or_(*[expression.ilike(like) for expression in expressions])
            clauses.append(match)
        if not clauses:
            return None
        combined = or_(*clauses)
        if condition.op in {"eq", "contains"}:
            return combined
        return ~combined

    return builder


def invoice_keyword_predicate(
    condition: FilterCondition, field: ListQueryField, context: ListQueryContext, parsed_value: Any
):
    customer_name = related_name_expression(
        Customer,
        InvoiceApplication.customer_id,
        Customer.account_name,
        team_id_expression=InvoiceApplication.team_id,
    )
    contract_name = related_name_expression(
        Contract,
        InvoiceApplication.contract_id,
        Contract.contract_name,
        team_id_expression=InvoiceApplication.team_id,
    )
    return keyword_predicate(
        InvoiceApplication.application_number,
        InvoiceApplication.invoice_title_text,
        InvoiceApplication.invoice_taxpayer_id,
        InvoiceApplication.invoice_number,
        customer_name,
        contract_name,
    )(condition, field, context, parsed_value)


def invoice_effective_status_flags():
    completed_reissue = exists().where(
        and_(
            InvoiceReissueApplication.original_invoice_application_id == InvoiceApplication.id,
            InvoiceReissueApplication.team_id == InvoiceApplication.team_id,
            InvoiceReissueApplication.status == InvoiceReissueApplicationStatus.COMPLETED,
            InvoiceReissueApplication.new_invoice_file_path.isnot(None),
            InvoiceReissueApplication.new_invoice_file_path != "",
        )
    )
    red_offset = exists().where(
        and_(
            InvoiceRedOffset.invoice_application_id == InvoiceApplication.id,
            InvoiceRedOffset.team_id == InvoiceApplication.team_id,
        )
    )
    pending_reissue = exists().where(
        and_(
            InvoiceReissueApplication.original_invoice_application_id == InvoiceApplication.id,
            InvoiceReissueApplication.team_id == InvoiceApplication.team_id,
            InvoiceReissueApplication.status.in_(
                [
                    InvoiceReissueApplicationStatus.DRAFT,
                    InvoiceReissueApplicationStatus.PENDING_REVIEW,
                    InvoiceReissueApplicationStatus.APPROVED,
                ]
            ),
        )
    )
    return completed_reissue, red_offset, pending_reissue


def invoice_effective_status_expression(context: ListQueryContext):
    completed_reissue, red_offset, pending_reissue = invoice_effective_status_flags()
    return case(
        (completed_reissue, "REISSUED"),
        (and_(red_offset, ~completed_reissue), "RED_OFFSET"),
        (and_(~red_offset, ~completed_reissue, pending_reissue), "REISSUE_PENDING"),
        else_="ACTIVE",
    )


def payment_approval_status_expression(context: ListQueryContext):
    pending_approval = exists().where(
        and_(
            Approval.id == PaymentRecord.approval_id,
            Approval.team_id == PaymentRecord.team_id,
            Approval.status == ApprovalStatus.PENDING,
        )
    )
    rejected = exists().where(
        and_(
            Approval.id == PaymentRecord.approval_id,
            Approval.team_id == PaymentRecord.team_id,
            Approval.status == ApprovalStatus.REJECTED,
        )
    )
    return case(
        (PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED, "approved"),
        (rejected, "rejected"),
        (pending_approval, "pending_approval"),
        (
            and_(
                PaymentRecord.approval_id.is_(None),
                PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING,
            ),
            "pending_submit",
        ),
        else_=None,
    )


def payment_invoice_title_expression():
    return (
        select(InvoiceApplication.invoice_title_text)
        .where(
            InvoiceApplication.payment_record_id == PaymentRecord.id,
            InvoiceApplication.team_id == PaymentRecord.team_id,
        )
        .order_by(InvoiceApplication.created_time.desc(), InvoiceApplication.id.desc())
        .limit(1)
        .correlate_except(InvoiceApplication)
        .scalar_subquery()
    )


def payment_owner_name_expression():
    owner_id = func.coalesce(Opportunity.owner_id, Contract.owner_id)
    return user_name_expression(owner_id)


def follow_up_content_expression():
    return func.coalesce(func.nullif(FollowUpTask.title, ""), FollowUpTask.description)


def follow_up_status_label_expression():
    pending_confirmation = exists().where(
        and_(
            FollowUpTaskConfirmationCase.task_id == FollowUpTask.id,
            FollowUpTaskConfirmationCase.team_id == FollowUpTask.team_id,
            FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
        )
    )
    return case(
        (pending_confirmation, "需确认"),
        (FollowUpTask.status == FollowUpTaskStatus.OPEN, "待处理"),
        (FollowUpTask.status == FollowUpTaskStatus.COMPLETED, "已完成"),
        (FollowUpTask.status == FollowUpTaskStatus.CANCELLED, "已关闭"),
        else_=FollowUpTask.status,
    )


def follow_up_customer_name_expression():
    return (
        select(Customer.account_name)
        .where(
            Customer.id == FollowUpTask.customer_id,
            Customer.team_id == FollowUpTask.team_id,
        )
        .limit(1)
        .correlate_except(Customer)
        .scalar_subquery()
    )


def _approval_scalar(model, column, *extra):
    return (
        select(column)
        .where(model.id == Approval.business_id, model.team_id == Approval.team_id, *extra)
        .limit(1)
        .correlate_except(model)
        .scalar_subquery()
    )


def approval_application_number_expression():
    payment_number = func.coalesce(
        func.nullif(_approval_scalar(PaymentRecord, PaymentRecord.record_number), ""),
        literal("PAY-") + cast(Approval.business_id, String),
    )
    return case(
        (Approval.business_type == BusinessType.CONTRACT, _approval_scalar(Contract, Contract.contract_number)),
        (
            Approval.business_type == BusinessType.INVOICE,
            _approval_scalar(InvoiceApplication, InvoiceApplication.application_number),
        ),
        (
            Approval.business_type == BusinessType.INVOICE_REISSUE,
            _approval_scalar(InvoiceReissueApplication, InvoiceReissueApplication.application_number),
        ),
        (Approval.business_type == BusinessType.PAYMENT, payment_number),
        (
            Approval.business_type == BusinessType.LICENSE,
            _approval_scalar(LicenseApplication, LicenseApplication.application_number),
        ),
        (
            Approval.business_type == BusinessType.OPPORTUNITY,
            _approval_scalar(Opportunity, Opportunity.opportunity_number),
        ),
    )


def approval_payment_contract_name_expression():
    return (
        select(Contract.contract_name)
        .select_from(PaymentRecord)
        .join(PaymentPlan, PaymentPlan.id == PaymentRecord.payment_plan_id)
        .join(Contract, Contract.id == PaymentPlan.contract_id)
        .where(
            PaymentRecord.id == Approval.business_id,
            PaymentRecord.team_id == Approval.team_id,
            PaymentPlan.team_id == Approval.team_id,
            Contract.team_id == Approval.team_id,
        )
        .limit(1)
        .correlate_except(PaymentRecord, PaymentPlan, Contract)
        .scalar_subquery()
    )


def approval_entity_name_expression():
    return case(
        (Approval.business_type == BusinessType.CONTRACT, _approval_scalar(Contract, Contract.contract_name)),
        (
            Approval.business_type == BusinessType.INVOICE,
            _approval_scalar(InvoiceApplication, InvoiceApplication.invoice_title_text),
        ),
        (
            Approval.business_type == BusinessType.INVOICE_REISSUE,
            _approval_scalar(InvoiceReissueApplication, InvoiceReissueApplication.invoice_title_text),
        ),
        (Approval.business_type == BusinessType.PAYMENT, approval_payment_contract_name_expression()),
        (
            Approval.business_type == BusinessType.LICENSE,
            _approval_scalar(LicenseApplication, LicenseApplication.license_type),
        ),
        (
            Approval.business_type == BusinessType.OPPORTUNITY,
            _approval_scalar(Opportunity, Opportunity.opportunity_name),
        ),
    )


def approval_entity_amount_expression():
    return case(
        (Approval.business_type == BusinessType.CONTRACT, _approval_scalar(Contract, Contract.total_amount)),
        (
            Approval.business_type == BusinessType.INVOICE,
            _approval_scalar(InvoiceApplication, InvoiceApplication.invoice_amount),
        ),
        (
            Approval.business_type == BusinessType.INVOICE_REISSUE,
            _approval_scalar(InvoiceReissueApplication, InvoiceReissueApplication.invoice_amount),
        ),
        (Approval.business_type == BusinessType.PAYMENT, _approval_scalar(PaymentRecord, PaymentRecord.actual_amount)),
        (Approval.business_type == BusinessType.OPPORTUNITY, _approval_scalar(Opportunity, Opportunity.total_amount)),
    )


def approval_overdue_hours_expression(context: ListQueryContext):
    return case(
        (
            Approval.status == ApprovalStatus.PENDING,
            hours_between(Approval.created_time, context.business_now()),
        ),
        else_=None,
    )


def without_filter_field(filters: Iterable[Any] | None, field: str) -> list[Any] | None:
    if filters is None:
        return None
    return [
        item for item in filters if (item.field if isinstance(item, FilterCondition) else item.get("field")) != field
    ]


def has_filter_field(filters: Iterable[Any] | None, field: str) -> bool:
    if filters is None:
        return False
    for item in filters:
        key = item.field if isinstance(item, FilterCondition) else item.get("field")
        if key == field:
            return True
    return False

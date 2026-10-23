import math
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.contract_board import (
    ContractBoardColumn,
    ContractBoardItem,
    ContractBoardMetric,
    ContractBoardResponse,
    ContractCountMetric,
)
from app.schemas.customer_board import (
    CustomerBoardColumn,
    CustomerBoardItem,
    CustomerBoardMetric,
    CustomerBoardResponse,
    CustomerCountMetric,
    CustomerPercentageMetric,
)
from app.schemas.opportunity_board import (
    OpportunityAmountMetric,
    OpportunityBoardColumn,
    OpportunityBoardItem,
    OpportunityBoardMetric,
    OpportunityBoardResponse,
)
from app.schemas.payment_plan_board import (
    PaymentPlanAmountMetric,
    PaymentPlanBoardColumn,
    PaymentPlanBoardItem,
    PaymentPlanBoardMetric,
    PaymentPlanBoardResponse,
)
from app.schemas.payment_record_board import (
    PaymentRecordAmountMetric,
    PaymentRecordBoardColumn,
    PaymentRecordBoardItem,
    PaymentRecordBoardMetric,
    PaymentRecordBoardResponse,
)

CUSTOMER_STATUSES = ("not_started", "following", "repurchasing", "won", "lost")
CONTRACT_STATUSES = (
    "DRAFT",
    "PENDING_REVIEW",
    "SIGNED",
    "EFFECTIVE",
    "EXPIRED",
    "TERMINATED",
    "UNCLASSIFIED",
)
PAYMENT_PLAN_STATUSES = ("PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED")
PAYMENT_RECORD_STATUSES = (
    "pending_submit",
    "pending_approval",
    "rejected",
    "approved",
    "unclassified",
)


def _owner() -> dict[str, str]:
    return {"id": "user-1", "name": "Ada"}


def _customer_item(status: str = "following") -> dict[str, Any]:
    return {
        "id": "cust-1",
        "title": "Acme",
        "subtitle": "企业客户",
        "amount": "10.00",
        "date": "2026-09-30",
        "owner": _owner(),
        "status": status,
        "metadata": {
            "stage_hint": "跟进中",
            "industry": "软件",
            "city": "上海",
            "company_scale": "100-499",
            "license_type": "OFFICIAL",
            "license_expiry_date": "2026-12-31",
        },
        "action_state": {
            "can_edit": True,
            "can_delete": False,
            "can_assign": True,
            "can_create_opportunity": True,
        },
    }


def _opportunity_item(status: str = "active") -> dict[str, Any]:
    return {
        "id": "opp-1",
        "title": "续约",
        "subtitle": "Q4",
        "amount": "20.50",
        "date": "2026-10-01",
        "owner": _owner(),
        "status": status,
        "metadata": {
            "customer_name": "Acme",
            "purchase_type": "renewal",
            "license_type": "official",
            "expected_closing_date": "2026-11-15",
            "win_probability": 40.0,
            "stage_name": "方案",
            "stage_sort_order": 2,
            "procurement_method_name": "公开招标",
            "procurement_method_code": "OPEN",
            "procurement_stage_template_id": 8,
            "template_code": "proposal",
        },
        "action_state": {
            "can_edit": True,
            "can_delete": False,
            "can_move_stage": True,
            "can_mark_won": False,
            "can_mark_lost": True,
        },
    }


def _contract_item(status: str = "SIGNED") -> dict[str, Any]:
    return {
        "id": 11,
        "title": "主合同",
        "subtitle": "2026",
        "amount": "100.00",
        "date": "2026-08-01",
        "owner": _owner(),
        "status": status,
        "metadata": {
            "customer_name": "Acme",
            "opportunity_name": "续约",
            "license_type": "official",
            "purchase_type": "renewal",
            "signing_date": "2026-08-01",
            "effective_date": "2026-08-02",
            "expiry_date": "2027-08-01",
            "license_expiry_date": "2027-08-01",
            "authorized_users": 25,
        },
        "action_state": {
            "can_edit": False,
            "can_delete": False,
            "can_submit_approval": False,
            "can_approve": True,
            "can_reject": True,
        },
    }


def _payment_plan_item(status: str = "PENDING") -> dict[str, Any]:
    return {
        "id": 21,
        "title": "首期",
        "subtitle": "合同 A",
        "amount": "50.00",
        "planned_amount": "50.00",
        "paid_amount": "10.00",
        "remaining_amount": "40.00",
        "date": "2026-09-15",
        "owner": _owner(),
        "status": status,
        "metadata": {
            "customer_name": "Acme",
            "contract_name": "主合同",
            "opportunity_name": "续约",
            "paid_amount": "10.00",
            "remaining_amount": "40.00",
        },
        "action_state": {"can_edit": True, "can_delete": False, "can_view_detail": True},
    }


def _payment_record_item(status: str = "approved") -> dict[str, Any]:
    return {
        "id": 31,
        "title": "回款 31",
        "subtitle": "银行转账",
        "amount": "30.00",
        "actual_amount": "30.00",
        "date": "2026-09-20",
        "owner": _owner(),
        "status": status,
        "metadata": {
            "customer_name": "Acme",
            "contract_name": "主合同",
            "actual_payer_name": "Acme Finance",
            "creator_name": "Bea",
            "owner_name": "Ada",
            "commission_member_name": "Cid",
            "approval_phase": "finance",
            "approval_id": 9,
            "confirmation_status": "CONFIRMED",
        },
        "action_state": {"can_edit": False, "can_delete": False, "can_resubmit": False},
    }


def _column(
    key: str,
    *,
    count: int = 0,
    items: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
    amount: str | None = "0.00",
    preview: bool = False,
) -> dict[str, Any]:
    shown = items or []
    payload: dict[str, Any] = {
        "key": key,
        "label": key,
        "tone": "neutral",
        "count": count,
        "amount": amount,
        "items": shown,
        "has_more": count > len(shown) if preview else False,
        "remaining_count": count - len(shown) if preview else 0,
    }
    if extra:
        payload.update(extra)
    return payload


def _customer_columns(items_for: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    grouped = items_for or {}
    return [
        _column(
            key,
            count=6 if key == "following" and grouped else len(grouped.get(key, [])),
            items=grouped.get(key, []),
            amount="60.00" if key == "following" and grouped else None,
        )
        for key in CUSTOMER_STATUSES
    ]


def _opportunity_columns(items_for: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    grouped = items_for or {}
    active_key = "stage:3:8"
    columns = [
        (
            active_key,
            "active_stage",
            {
                "stage_name": "方案",
                "template_code": "proposal",
                "template_sort_order": 2,
                "procurement_method_id": 3,
                "procurement_stage_template_id": 8,
            },
        ),
        ("won", "won", {}),
        ("lost", "lost", {}),
        ("unset_stage", "unset_stage", {}),
    ]
    return [
        _column(
            key,
            count=6 if key == active_key and grouped else len(grouped.get(key, [])),
            items=grouped.get(key, []),
            extra={"column_kind": kind, **extra},
            amount="120.00" if key == active_key and grouped else "0.00",
        )
        for key, kind, extra in columns
    ]


def _fixed_columns(
    keys: tuple[str, ...],
    items_for: dict[str, list[dict[str, Any]]] | None,
    *,
    focus: str,
    extra_for: Callable[[str], dict[str, Any]] | None = None,
    preview: bool = False,
) -> list[dict[str, Any]]:
    grouped = items_for or {}
    return [
        _column(
            key,
            count=6 if key == focus and grouped else len(grouped.get(key, [])),
            items=grouped.get(key, []),
            extra=None if extra_for is None else extra_for(key),
            amount="180.00" if key == focus and grouped else "0.00",
            preview=preview,
        )
        for key in keys
    ]


def _customer_summary() -> list[dict[str, Any]]:
    return [
        {"key": "total_count", "label": "客户", "value_type": "count", "value": 6},
        {"key": "following_count", "label": "跟进", "value_type": "count", "value": 6},
        {"key": "repurchasing_count", "label": "复购", "value_type": "count", "value": 0},
        {"key": "won_count", "label": "成交", "value_type": "count", "value": 0},
        {
            "key": "recent_new_count",
            "label": "新增",
            "value_type": "count",
            "value": 1,
            "secondary_label": "上月",
            "secondary_value": 0,
        },
        {"key": "not_started_percentage", "label": "未开始占比", "value_type": "percentage", "value": 0.0},
        {"key": "following_percentage", "label": "跟进占比", "value_type": "percentage", "value": 100.0},
        {"key": "repurchasing_percentage", "label": "复购占比", "value_type": "percentage", "value": None},
        {"key": "won_percentage", "label": "成交占比", "value_type": "percentage", "value": 0.0},
        {"key": "lost_percentage", "label": "流失占比", "value_type": "percentage", "value": 0.0},
    ]


def _opportunity_summary() -> list[dict[str, Any]]:
    return [
        {"key": "total_count", "label": "商机", "value_type": "count", "value": 6},
        {"key": "won_count", "label": "赢单", "value_type": "count", "value": 0},
        {"key": "pipeline_amount", "label": "管道金额", "value_type": "amount", "value": "120.00"},
        {"key": "weighted_amount", "label": "加权金额", "value_type": "amount", "value": "48.00"},
        {
            "key": "won_amount",
            "label": "赢单金额",
            "value_type": "amount",
            "value": "0.00",
            "secondary_label": "上月",
            "secondary_value": "0.00",
        },
    ]


def _contract_summary() -> list[dict[str, Any]]:
    return [
        {"key": "total_count", "label": "合同", "value_type": "count", "value": 6},
        {"key": "pending_review_count", "label": "待审", "value_type": "count", "value": 0},
        {"key": "total_amount", "label": "合同金额", "value_type": "amount", "value": "180.00"},
        {"key": "signed_effective_amount", "label": "生效金额", "value_type": "amount", "value": "0.00"},
    ]


def _payment_plan_summary() -> list[dict[str, Any]]:
    return [
        {"key": "overdue_count", "label": "逾期", "value_type": "count", "value": 0},
        {"key": "planned_amount", "label": "计划", "value_type": "amount", "value": "180.00"},
        {"key": "paid_amount", "label": "已回", "value_type": "amount", "value": "0.00"},
        {"key": "remaining_amount", "label": "剩余", "value_type": "amount", "value": "180.00"},
        {"key": "overdue_remaining_amount", "label": "逾期剩余", "value_type": "amount", "value": "0.00"},
    ]


def _payment_record_summary() -> list[dict[str, Any]]:
    return [
        {"key": "total_count", "label": "回款", "value_type": "count", "value": 6},
        {"key": "rejected_count", "label": "驳回", "value_type": "count", "value": 0},
        {"key": "actual_total", "label": "实收", "value_type": "amount", "value": "180.00"},
        {"key": "confirmed_amount", "label": "已确认", "value_type": "amount", "value": "180.00"},
        {"key": "unconfirmed_amount", "label": "未确认", "value_type": "amount", "value": "0.00"},
    ]


def _zero_summary(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zeroed = []
    for metric in summary:
        item = dict(metric)
        item.pop("secondary_label", None)
        item.pop("secondary_value", None)
        if item["value_type"] == "count":
            item["value"] = 0
        elif item["value_type"] == "amount":
            item["value"] = "0.00"
        else:
            item["value"] = None
        zeroed.append(item)
    return zeroed


def _customer_payload(*, populated: bool) -> dict[str, Any]:
    items = [_customer_item() for _ in range(6)] if populated else []
    return {
        "summary": _customer_summary() if populated else _zero_summary(_customer_summary()),
        "columns": _customer_columns({"following": items} if populated else None),
        "trends": [{"date": "2026-09", "count": 6}] if populated else [],
    }


def _opportunity_payload(*, populated: bool) -> dict[str, Any]:
    items = [_opportunity_item() for _ in range(6)] if populated else []
    return {
        "summary": _opportunity_summary() if populated else _zero_summary(_opportunity_summary()),
        "columns": _opportunity_columns({"stage:3:8": items} if populated else None),
        "trends": [{"date": "2026-09", "count": 6, "amount": "120.00"}] if populated else [],
    }


def _contract_payload(*, populated: bool) -> dict[str, Any]:
    items = [_contract_item() for _ in range(6)] if populated else []
    return {
        "summary": _contract_summary() if populated else _zero_summary(_contract_summary()),
        "columns": _fixed_columns(CONTRACT_STATUSES, {"SIGNED": items} if populated else None, focus="SIGNED"),
        "trends": [{"date": "2026-08", "count": 6, "amount": "180.00"}] if populated else [],
    }


def _plan_amounts(key: str, *, populated: bool) -> dict[str, str]:
    active = populated and key == "PENDING"
    return {
        "planned_amount": "180.00" if active else "0.00",
        "paid_amount": "0.00",
        "remaining_amount": "180.00" if active else "0.00",
        "overdue_remaining_amount": "0.00",
    }


def _record_amounts(key: str, *, populated: bool) -> dict[str, str]:
    active = populated and key == "approved"
    return {
        "actual_amount": "180.00" if active else "0.00",
        "confirmed_amount": "180.00" if active else "0.00",
        "unconfirmed_amount": "0.00",
    }


def _payment_plan_payload(*, populated: bool) -> dict[str, Any]:
    items = [_payment_plan_item() for _ in range(6)] if populated else []
    return {
        "summary": _payment_plan_summary() if populated else _zero_summary(_payment_plan_summary()),
        "columns": _fixed_columns(
            PAYMENT_PLAN_STATUSES,
            {"PENDING": items} if populated else None,
            focus="PENDING",
            extra_for=lambda key: _plan_amounts(key, populated=populated),
        ),
        "trends": [
            {
                "date": "2026-09",
                "count": 6,
                "planned_amount": "180.00",
                "paid_amount": "0.00",
                "remaining_amount": "180.00",
            }
        ]
        if populated
        else [],
    }


def _payment_record_payload(*, populated: bool) -> dict[str, Any]:
    items = [_payment_record_item() for _ in range(5)] if populated else []
    return {
        "summary": _payment_record_summary() if populated else _zero_summary(_payment_record_summary()),
        "columns": _fixed_columns(
            PAYMENT_RECORD_STATUSES,
            {"approved": items} if populated else None,
            focus="approved",
            extra_for=lambda key: _record_amounts(key, populated=populated),
            preview=True,
        ),
        "trends": [
            {
                "date": "2026-09",
                "count": 6,
                "actual_amount": "180.00",
                "confirmed_amount": "180.00",
                "unconfirmed_amount": "0.00",
            }
        ]
        if populated
        else [],
    }


BOARDS: tuple[tuple[str, type, Callable[..., dict[str, Any]], tuple[str, ...]], ...] = (
    ("customer", CustomerBoardResponse, _customer_payload, CUSTOMER_STATUSES),
    ("opportunity", OpportunityBoardResponse, _opportunity_payload, ("stage:3:8", "won", "lost", "unset_stage")),
    ("contract", ContractBoardResponse, _contract_payload, CONTRACT_STATUSES),
    ("payment_plan", PaymentPlanBoardResponse, _payment_plan_payload, PAYMENT_PLAN_STATUSES),
    ("payment_record", PaymentRecordBoardResponse, _payment_record_payload, PAYMENT_RECORD_STATUSES),
)


@pytest.mark.parametrize(("name", "response_type", "payload_factory", "keys"), BOARDS)
def test_each_domain_accepts_empty_and_populated_responses(
    name: str,
    response_type: type,
    payload_factory: Callable[..., dict[str, Any]],
    keys: tuple[str, ...],
) -> None:
    empty = response_type.model_validate(payload_factory(populated=False))
    populated = response_type.model_validate(payload_factory(populated=True))

    assert [column.key for column in empty.columns] == list(keys)
    assert all(column.count == 0 and column.items == [] and column.remaining_count == 0 for column in empty.columns)
    assert all(column.has_more is False for column in empty.columns)
    assert empty.trends == []
    assert populated.trends
    focus = next(column for column in populated.columns if column.count == 6)
    assert focus.count == 6
    if name == "payment_record":
        assert len(focus.items) == 5
        assert focus.has_more is True
        assert focus.remaining_count == 1
    else:
        assert len(focus.items) == 6
        assert focus.has_more is False
        assert focus.remaining_count == 0
    if name == "opportunity":
        assert focus.key == "stage:3:8"
        assert focus.column_kind == "active_stage"
        assert focus.procurement_method_id == 3
        assert focus.procurement_stage_template_id == 8
        assert "unset_stage" in [column.key for column in populated.columns]
    if name in {"contract", "payment_plan"}:
        assert "UNCLASSIFIED" in [column.key for column in populated.columns]
    if name == "payment_record":
        assert "unclassified" in [column.key for column in populated.columns]


def test_exact_five_preview_rows_are_not_marked_as_having_more() -> None:
    payload = _customer_payload(populated=True)
    payload["columns"][1]["items"] = payload["columns"][1]["items"][:5]
    payload["columns"][1]["count"] = 5
    payload["columns"][1]["has_more"] = False
    payload["columns"][1]["remaining_count"] = 0

    column = CustomerBoardColumn.model_validate(payload["columns"][1])

    assert column.has_more is False
    assert column.remaining_count == 0


def test_full_column_returns_every_source_row() -> None:
    payload = _contract_payload(populated=True)
    column = ContractBoardColumn.model_validate(payload["columns"][CONTRACT_STATUSES.index("SIGNED")])

    assert len(column.items) == 6
    assert column.has_more is False
    assert column.remaining_count == 0


@pytest.mark.parametrize(
    ("response_type", "payload_factory"),
    [(response_type, factory) for _, response_type, factory, _ in BOARDS],
)
@pytest.mark.parametrize(
    "bad_count",
    [True, 1.5, -1, "1"],
)
def test_counts_reject_booleans_fractions_negatives_and_strings(
    response_type: type,
    payload_factory: Callable[..., dict[str, Any]],
    bad_count: object,
) -> None:
    payload = payload_factory(populated=False)
    payload["columns"][0]["count"] = bad_count

    with pytest.raises(ValidationError):
        response_type.model_validate(payload)


@pytest.mark.parametrize(
    ("response_type", "payload_factory"),
    [(response_type, factory) for _, response_type, factory, _ in BOARDS],
)
@pytest.mark.parametrize("amount", ["1", "1.2", "1.234", 10, True])
def test_amounts_reject_invalid_fixed_point_values(
    response_type: type,
    payload_factory: Callable[..., dict[str, Any]],
    amount: object,
) -> None:
    payload = payload_factory(populated=False)
    payload["columns"][0]["amount"] = amount

    with pytest.raises(ValidationError):
        response_type.model_validate(payload)


def test_percentages_reject_nonfinite_and_out_of_range_values() -> None:
    metric = {
        "key": "following_percentage",
        "label": "跟进占比",
        "value_type": "percentage",
        "value": 10.0,
    }
    for value in (math.nan, math.inf, -0.1, 100.1, True, "10"):
        with pytest.raises(ValidationError):
            CustomerPercentageMetric.model_validate({**metric, "value": value})

    opportunity = _opportunity_item()
    opportunity["metadata"]["win_probability"] = math.nan
    with pytest.raises(ValidationError):
        OpportunityBoardItem.model_validate(opportunity)


def test_undefined_percentage_may_be_null_but_required_fields_may_not() -> None:
    metric = CustomerPercentageMetric.model_validate(
        {
            "key": "lost_percentage",
            "label": "流失占比",
            "value_type": "percentage",
            "value": None,
        }
    )
    assert metric.value is None

    item = _customer_item()
    item["metadata"] = None
    with pytest.raises(ValidationError):
        CustomerBoardItem.model_validate(item)
    item = _customer_item()
    item["action_state"] = None
    with pytest.raises(ValidationError):
        CustomerBoardItem.model_validate(item)
    column = _customer_columns()[0]
    column["count"] = None
    with pytest.raises(ValidationError):
        CustomerBoardColumn.model_validate(column)


def test_secondary_labels_and_values_must_be_present_together() -> None:
    with pytest.raises(ValidationError, match="secondary value and label"):
        CustomerCountMetric.model_validate(
            {
                "key": "recent_new_count",
                "label": "新增",
                "value_type": "count",
                "value": 1,
                "secondary_value": 2,
            }
        )
    with pytest.raises(ValidationError, match="secondary value and label"):
        OpportunityAmountMetric.model_validate(
            {
                "key": "won_amount",
                "label": "赢单金额",
                "value_type": "amount",
                "value": "1.00",
                "secondary_label": "上月",
            }
        )
    with pytest.raises(ValidationError, match="secondary value and label"):
        PaymentPlanAmountMetric.model_validate(
            {
                "key": "paid_amount",
                "label": "已回",
                "value_type": "amount",
                "value": "1.00",
                "secondary_label": "上月",
            }
        )
    with pytest.raises(ValidationError, match="secondary value and label"):
        PaymentRecordAmountMetric.model_validate(
            {
                "key": "actual_total",
                "label": "实收",
                "value_type": "amount",
                "value": "1.00",
                "secondary_value": "0.00",
            }
        )


@pytest.mark.parametrize(
    ("response_type", "payload_factory"),
    [(response_type, factory) for _, response_type, factory, _ in BOARDS],
)
def test_unknown_fields_are_rejected(
    response_type: type,
    payload_factory: Callable[..., dict[str, Any]],
) -> None:
    payload = payload_factory(populated=False)
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        response_type.model_validate(payload)


@pytest.mark.parametrize(
    ("item_type", "factory", "bad_status"),
    [
        (CustomerBoardItem, _customer_item, "public"),
        (OpportunityBoardItem, _opportunity_item, "DRAFT"),
        (ContractBoardItem, _contract_item, "approved"),
        (PaymentPlanBoardItem, _payment_plan_item, "approved"),
        (PaymentRecordBoardItem, _payment_record_item, "CONFIRMED"),
    ],
)
def test_wrong_status_keys_are_rejected(
    item_type: type,
    factory: Callable[[], dict[str, Any]],
    bad_status: str,
) -> None:
    payload = factory()
    payload["status"] = bad_status

    with pytest.raises(ValidationError):
        item_type.model_validate(payload)


def test_cross_domain_metadata_is_rejected() -> None:
    customer = _customer_item()
    customer["metadata"] = _opportunity_item()["metadata"]
    with pytest.raises(ValidationError):
        CustomerBoardItem.model_validate(customer)

    opportunity = _opportunity_item()
    opportunity["metadata"] = _payment_plan_item()["metadata"]
    with pytest.raises(ValidationError):
        OpportunityBoardItem.model_validate(opportunity)

    contract = _contract_item()
    contract["metadata"] = _payment_record_item()["metadata"]
    with pytest.raises(ValidationError):
        ContractBoardItem.model_validate(contract)


def test_metric_unions_discriminate_domain_keys() -> None:
    customer = TypeAdapter(CustomerBoardMetric).validate_python(_customer_summary()[0])
    opportunity = TypeAdapter(OpportunityBoardMetric).validate_python(_opportunity_summary()[2])
    contract = TypeAdapter(ContractBoardMetric).validate_python(_contract_summary()[0])
    plan = TypeAdapter(PaymentPlanBoardMetric).validate_python(_payment_plan_summary()[1])
    record = TypeAdapter(PaymentRecordBoardMetric).validate_python(_payment_record_summary()[2])

    assert isinstance(customer, CustomerCountMetric)
    assert isinstance(opportunity, OpportunityAmountMetric)
    assert isinstance(contract, ContractCountMetric)
    assert isinstance(plan, PaymentPlanAmountMetric)
    assert isinstance(record, PaymentRecordAmountMetric)
    with pytest.raises(ValidationError):
        TypeAdapter(CustomerBoardMetric).validate_python(_opportunity_summary()[2])
    with pytest.raises(ValidationError):
        TypeAdapter(ContractBoardMetric).validate_python(
            {"key": "pipeline_amount", "label": "管道", "value_type": "amount", "value": "1.00"}
        )


def test_public_ids_keep_domain_types() -> None:
    assert CustomerBoardItem.model_validate(_customer_item()).id == "cust-1"
    assert OpportunityBoardItem.model_validate(_opportunity_item()).id == "opp-1"
    assert ContractBoardItem.model_validate(_contract_item()).id == 11
    assert PaymentPlanBoardItem.model_validate(_payment_plan_item()).id == 21
    assert PaymentRecordBoardItem.model_validate(_payment_record_item()).id == 31

    with pytest.raises(ValidationError):
        ContractBoardItem.model_validate({**_contract_item(), "id": "11"})
    with pytest.raises(ValidationError):
        PaymentPlanBoardItem.model_validate({**_payment_plan_item(), "id": 0})
    with pytest.raises(ValidationError):
        PaymentRecordBoardItem.model_validate({**_payment_record_item(), "id": True})
    with pytest.raises(ValidationError):
        CustomerBoardItem.model_validate({**_customer_item(), "id": 1})


def test_preview_invariants_reject_inconsistent_windows() -> None:
    column = _payment_record_payload(populated=True)["columns"][3]
    column["has_more"] = False

    with pytest.raises(ValidationError, match="inconsistent board preview counts"):
        PaymentRecordBoardColumn.model_validate(column)

    plan = _payment_plan_payload(populated=True)["columns"][0]
    plan["remaining_count"] = 2
    with pytest.raises(ValidationError, match="inconsistent board column counts"):
        PaymentPlanBoardColumn.model_validate(plan)

    opportunity = _opportunity_payload(populated=True)["columns"][0]
    opportunity["items"] = opportunity["items"][:4]
    with pytest.raises(ValidationError, match="inconsistent board column counts"):
        OpportunityBoardColumn.model_validate(opportunity)

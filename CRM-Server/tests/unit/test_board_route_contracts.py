"""The five board routes share one non-paginated contract and stay domain-specific."""

from __future__ import annotations

import inspect
from datetime import date, datetime

import pytest
from sqlalchemy.schema import CreateTable

from app.api.contracts import get_contract_board
from app.api.customers import get_customer_board
from app.api.opportunities import get_opportunity_board
from app.api.payments import get_payment_plan_board, get_payment_record_board
from app.models.approval import ApprovalNode
from app.models.customer import Contact
from app.models.payment import PaymentConfirmationStatus
from app.schemas.contract_board import ContractBoardResponse
from app.schemas.customer_board import CustomerBoardResponse
from app.schemas.opportunity_board import OpportunityBoardResponse
from app.schemas.payment_plan_board import PaymentPlanBoardResponse
from app.schemas.payment_record_board import PaymentRecordBoardResponse
from tests.unit import test_contract_board_api as contract_api
from tests.unit import test_customer_board_api as customer_api
from tests.unit import test_opportunity_board_api as opportunity_api
from tests.unit import test_payment_plan_board_api as plan_api
from tests.unit import test_payment_record_board_api as record_api

customer_api_env = customer_api.api_env
opportunity_api_env = opportunity_api.api_env
contract_api_env = contract_api.api_env
payment_plan_api_env = plan_api.api_env
payment_record_api_env = record_api.api_env

PAGINATION_NAMES = {"page", "page_size", "skip", "limit"}

ROUTE_CONTRACTS = (
    {
        "name": "customer",
        "callable": get_customer_board,
        "model": CustomerBoardResponse,
        "list_path": "/v1/customers/",
        "parameters": (
            "customer_status",
            "status_exclude",
            "industry",
            "industry_exclude",
            "city",
            "source_public_id",
            "source_public_id_exclude",
            "company_scale",
            "company_scale_exclude",
            "owner_id",
            "owner_id_exclude",
            "keyword",
            "search",
            "created_time_start",
            "created_time_end",
            "order_by",
            "order_dir",
            "scope",
            "filters",
            "sorts",
            "chart_question",
            "chart_bucket",
            "team_id",
            "current_user",
            "db",
        ),
        "forbidden_detail": "只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据",
        "own_permission": "customer:view:own",
        "view_all_permission": "customer:view:all",
        "list_page": ("skip", "limit"),
        "sort": {"sorts": '[{"field":"account_name","dir":"asc"}]'},
        "foreign_marker": "别人的客户",
    },
    {
        "name": "opportunity",
        "callable": get_opportunity_board,
        "model": OpportunityBoardResponse,
        "list_path": "/v1/opportunities/",
        "parameters": (
            "opportunity_status",
            "status_exclude",
            "stage_id",
            "owner_id",
            "owner_id_exclude",
            "customer_public_id",
            "keyword",
            "customer_keyword",
            "search",
            "license_type",
            "license_type_exclude",
            "purchase_type",
            "purchase_type_exclude",
            "stage_name",
            "expected_closing_date_start",
            "expected_closing_date_end",
            "order_by",
            "order_dir",
            "filters",
            "sorts",
            "team_id",
            "current_user",
            "db",
        ),
        "forbidden_detail": "只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据",
        "own_permission": "opportunity:view:own",
        "view_all_permission": "opportunity:view:all",
        "list_page": ("skip", "limit"),
        "sort": {"order_by": "opportunity_name", "order_dir": "desc"},
        "foreign_marker": "别人的商机",
    },
    {
        "name": "contract",
        "callable": get_contract_board,
        "model": ContractBoardResponse,
        "list_path": "/v1/contracts/",
        "parameters": (
            "customer_public_id",
            "status",
            "status_exclude",
            "contract_number",
            "license_type",
            "license_type_exclude",
            "purchase_type",
            "purchase_type_exclude",
            "subscription_years",
            "subscription_years_exclude",
            "license_authorized_users",
            "license_authorized_users_exclude",
            "standard_unit_price",
            "standard_unit_price_exclude",
            "keyword",
            "customer_keyword",
            "opportunity_keyword",
            "search",
            "owner_id",
            "owner_id_exclude",
            "signing_date_start",
            "signing_date_end",
            "effective_date_start",
            "effective_date_end",
            "expiry_date_start",
            "expiry_date_end",
            "license_expiry_date_start",
            "license_expiry_date_end",
            "order_by",
            "order_dir",
            "filters",
            "sorts",
            "team_id",
            "current_user",
            "db",
        ),
        "forbidden_detail": "只能查看自己负责的合同，或需要 contract:view:all 权限查看他人数据",
        "own_permission": "contract:view:own",
        "view_all_permission": "contract:view:all",
        "list_page": ("skip", "limit"),
        "sort": {"sorts": '[{"field":"total_amount","dir":"asc"}]'},
        "foreign_marker": "别人的合同",
    },
    {
        "name": "payment_plan",
        "callable": get_payment_plan_board,
        "model": PaymentPlanBoardResponse,
        "list_path": "/v1/payments/payment-plans",
        "parameters": (
            "plan_status",
            "status_exclude",
            "owner_id",
            "keyword",
            "search",
            "me",
            "due_date_start",
            "due_date_end",
            "sort",
            "order_by",
            "order_dir",
            "filters",
            "sorts",
            "team_id",
            "current_user",
            "db",
        ),
        "forbidden_detail": "没有查看回款计划的权限",
        "own_permission": "payment:view:own",
        "view_all_permission": "payment:view:all",
        "list_page": ("page", "page_size"),
        "sort": {"order_by": "planned_amount", "order_dir": "desc"},
        "foreign_marker": "他人计划",
    },
    {
        "name": "payment_record",
        "callable": get_payment_record_board,
        "model": PaymentRecordBoardResponse,
        "list_path": "/v1/payments/payment-records",
        "parameters": (
            "contract_id",
            "payment_plan_id",
            "payment_date_start",
            "payment_date_end",
            "min_amount",
            "actual_amount",
            "creator_id",
            "keyword",
            "search",
            "record_number",
            "record_number_exclude",
            "customer_name",
            "customer_name_exclude",
            "actual_payer_name",
            "actual_payer_name_exclude",
            "invoice_title_text",
            "invoice_title_text_exclude",
            "contract_name",
            "contract_name_exclude",
            "owner_name",
            "owner_name_exclude",
            "commission_member_name",
            "commission_member_name_exclude",
            "confirmation_status",
            "confirmation_status_exclude",
            "created_time_start",
            "created_time_end",
            "me",
            "approval_status",
            "approval_status_exclude",
            "sort",
            "order_by",
            "order_dir",
            "filters",
            "sorts",
            "team_id",
            "current_user",
            "db",
        ),
        "forbidden_detail": "没有查看回款记录的权限",
        "own_permission": "payment:view:own",
        "view_all_permission": "payment:view:all",
        "list_page": ("page", "page_size"),
        "sort": {"sorts": '[{"field":"payment_date","dir":"asc"}]'},
        "foreign_marker": "他人记录",
    },
)


def _explicit_parameters(route) -> tuple[str, ...]:
    return tuple(inspect.signature(route).parameters)


def _structural_totals(body: dict) -> dict:
    return {
        "summary": [
            {
                "key": metric["key"],
                "value": metric["value"],
                "secondary_value": metric.get("secondary_value"),
            }
            for metric in body["summary"]
        ],
        "columns": [
            {
                "key": column["key"],
                "count": column["count"],
                "amount": column.get("amount"),
                "planned_amount": column.get("planned_amount"),
                "paid_amount": column.get("paid_amount"),
                "remaining_amount": column.get("remaining_amount"),
                "overdue_remaining_amount": column.get("overdue_remaining_amount"),
                "actual_amount": column.get("actual_amount"),
                "confirmed_amount": column.get("confirmed_amount"),
                "unconfirmed_amount": column.get("unconfirmed_amount"),
            }
            for column in body["columns"]
        ],
        "trends": body["trends"],
    }


def _ensure_table(api_env, model) -> None:
    with api_env.db.bind.begin() as connection:
        connection.execute(CreateTable(model.__table__))


def _seed_customer(api_env, *, count: int, include_other: bool) -> None:
    rows = [
        customer_api._customer(
            index,
            name=f"客户{chr(64 + index)}",
            owner_id="7",
            created_time=datetime(2026, 5, index),
            public_id=f"cus_{index:02d}",
        )
        for index in range(1, count + 1)
    ]
    if include_other:
        rows.append(customer_api._customer(
            count + 1,
            name="别人的客户",
            owner_id="8",
            created_time=datetime(2026, 6, 2),
            public_id="cus_other",
        ))
    api_env.db.add_all(rows)
    api_env.db.commit()


def _seed_opportunity(api_env, *, count: int, include_other: bool) -> None:
    rows = []
    for index in range(1, count + 1):
        rows.append(opportunity_api._snapshot(
            index,
            opportunity_id=index,
            template_id=8,
            name="方案",
            sort_order=20,
            code="proposal",
        ))
        rows.append(opportunity_api._opportunity(
            index,
            name=f"商机{chr(64 + index)}",
            customer_id=1,
            total_amount=f"{index * 10}.00",
            expected_closing_date=date(2026, 9, min(index, 28)),
            created_time=datetime(2026, 5, index),
            snapshot_id=index,
            stage_name="方案",
            public_id=f"opp_{index:02d}",
        ))
    if include_other:
        rows.append(opportunity_api._opportunity(
            count + 1,
            name="别人的商机",
            customer_id=2,
            owner_id="8",
            total_amount="90.00",
            created_time=datetime(2026, 6, 2),
            public_id="opp_other",
        ))
    api_env.db.add_all(rows)
    api_env.db.commit()


def _seed_contract(api_env, *, count: int, include_other: bool) -> None:
    rows = [
        contract_api._contract(
            index,
            name=f"合同{index:02d}",
            status="SIGNED",
            total_amount=f"{index * 10}.00",
            signing_date=date(2026, 6, index),
            effective_date=date(2026, 7, 1),
        )
        for index in range(1, count + 1)
    ]
    if include_other:
        rows.append(contract_api._contract(
            count + 1,
            name="别人的合同",
            customer_id=2,
            opportunity_id=2,
            owner_id="8",
            status="SIGNED",
            total_amount="90.00",
            signing_date=date(2026, 6, 2),
        ))
    for row in rows:
        row.signing_contact_id = row.id
    api_env.db.add_all(rows)
    api_env.db.commit()


def _seed_payment_plan(api_env, *, count: int, include_other: bool) -> None:
    rows = [plan_api._contract(1, name="甲合同", owner_id="7", creator_id="8")]
    rows.extend(
        plan_api._plan(
            index,
            contract_id=1,
            name=f"本人计划{index:02d}",
            amount=f"{index}.00",
            due_date=date(2026, 6, index),
        )
        for index in range(1, count + 1)
    )
    if include_other:
        rows.extend([
            plan_api._contract(2, name="乙合同", customer_id=2, opportunity_id=2, owner_id="8", creator_id="7"),
            plan_api._plan(
                count + 1,
                contract_id=2,
                name="他人计划",
                amount="90.00",
                status="OVERDUE",
                due_date=date(2026, 6, 3),
            ),
            plan_api._record(
                1,
                plan_id=count + 1,
                amount="40.00",
                payment_date=date(2026, 5, 1),
                approval_phase="approved",
            ),
        ])
    api_env.db.add_all(rows)
    api_env.db.commit()


def _seed_payment_record(api_env, *, count: int, include_other: bool) -> None:
    rows = [
        record_api._contract(1, name="甲合同", owner_id="8", creator_id="7"),
        record_api._plan(1, contract_id=1),
    ]
    rows.extend(
        record_api._record(
            index,
            plan_id=1,
            amount=f"{index}.00",
            payment_date=date(2026, 6, count + 1 - index),
            confirmation_status=(
                PaymentConfirmationStatus.CONFIRMED if index == 1 else PaymentConfirmationStatus.PENDING
            ),
            creator_id="8",
            payer=f"本人记录{index:02d}",
        )
        for index in range(1, count + 1)
    )
    if include_other:
        rows.extend([
            record_api._contract(2, name="乙合同", customer_id=2, opportunity_id=2, owner_id="7", creator_id="8"),
            record_api._plan(2, contract_id=2),
            record_api._record(
                count + 1,
                plan_id=2,
                amount="90.00",
                payment_date=date(2026, 6, 3),
                approval_phase="rejected",
                confirmation_status=PaymentConfirmationStatus.CONFIRMED,
                creator_id="7",
                payer="他人记录",
            ),
        ])
    api_env.db.add_all(rows)
    api_env.db.commit()


SEEDERS = {
    "customer": _seed_customer,
    "opportunity": _seed_opportunity,
    "contract": _seed_contract,
    "payment_plan": _seed_payment_plan,
    "payment_record": _seed_payment_record,
}

MODULES = {
    "customer": customer_api,
    "opportunity": opportunity_api,
    "contract": contract_api,
    "payment_plan": plan_api,
    "payment_record": record_api,
}


def _prepare_list_dependencies(contract, api_env) -> None:
    if contract["name"] in {"customer", "contract"}:
        _ensure_table(api_env, Contact)
    if contract["name"] == "contract":
        api_env.db.add_all([
            Contact(
                id=index,
                team_id=1,
                customer_id=1,
                name=f"签约人{index}",
                mobile=f"138000000{index:02d}",
                is_primary=0,
            )
            for index in range(1, 9)
        ])
        api_env.db.commit()
    if contract["name"] == "payment_record":
        _ensure_table(api_env, ApprovalNode)


@pytest.mark.parametrize("contract", ROUTE_CONTRACTS, ids=lambda item: item["name"])
def test_board_routes_expose_exact_non_pagination_parameters(contract) -> None:
    parameters = _explicit_parameters(contract["callable"])

    assert parameters == contract["parameters"]
    assert PAGINATION_NAMES.isdisjoint(parameters)
    if contract["name"] in {"payment_plan", "payment_record"}:
        assert "me" in parameters
    else:
        assert "me" not in parameters


def test_board_response_models_are_distinct() -> None:
    models = [contract["model"] for contract in ROUTE_CONTRACTS]
    assert len(set(models)) == len(models)


@pytest.mark.parametrize("contract", ROUTE_CONTRACTS, ids=lambda item: item["name"])
def test_valid_board_response_validates_through_its_own_model(contract, request) -> None:
    api_env = request.getfixturevalue(f"{contract['name']}_api_env")
    module = MODULES[contract["name"]]
    if contract["name"] in {"payment_plan", "payment_record"}:
        module._freeze(request.getfixturevalue("monkeypatch"), date(2026, 10, 12))
    SEEDERS[contract["name"]](api_env, count=1, include_other=False)
    module._grant(api_env.db, 7, contract["view_all_permission"])

    response = module._board(api_env.client)

    assert response.status_code == 200, response.text
    parsed = contract["model"].model_validate(response.json())
    assert parsed.columns
    for other in ROUTE_CONTRACTS:
        if other["model"] is contract["model"]:
            continue
        with pytest.raises(ValueError):
            other["model"].model_validate(response.json())


@pytest.mark.parametrize("contract", ROUTE_CONTRACTS, ids=lambda item: item["name"])
def test_missing_view_permission_returns_route_specific_403(contract, request) -> None:
    api_env = request.getfixturevalue(f"{contract['name']}_api_env")
    module = MODULES[contract["name"]]
    SEEDERS[contract["name"]](api_env, count=1, include_other=False)

    if contract["name"] in {"customer", "opportunity", "contract"}:
        response = module._board(api_env.client, owner_id="8")
    else:
        response = module._board(api_env.client)

    assert response.status_code == 403
    assert response.json()["detail"] == contract["forbidden_detail"]


@pytest.mark.parametrize("contract", ROUTE_CONTRACTS, ids=lambda item: item["name"])
def test_own_only_scope_excludes_other_user_from_summary_trends_counts_and_previews(contract, request) -> None:
    api_env = request.getfixturevalue(f"{contract['name']}_api_env")
    module = MODULES[contract["name"]]
    if contract["name"] in {"customer", "opportunity", "contract"}:
        class _FrozenDate(date):
            @classmethod
            def today(cls) -> date:
                return date(2026, 10, 12)

        if contract["name"] == "customer":
            module_date = customer_api.customers_api
        elif contract["name"] == "opportunity":
            module_date = opportunity_api.opportunities_api
        else:
            module_date = contract_api.contracts_api
        request.getfixturevalue("monkeypatch").setattr(module_date, "date", _FrozenDate)
    if contract["name"] in {"payment_plan", "payment_record"}:
        module._freeze(request.getfixturevalue("monkeypatch"), date(2026, 10, 12))
    SEEDERS[contract["name"]](api_env, count=1, include_other=True)
    if contract["name"] in {"payment_plan", "payment_record"}:
        module._grant(api_env.db, 7, contract["own_permission"])

    response = module._board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    rendered = str(body)
    assert contract["foreign_marker"] not in rendered
    totals = _structural_totals(body)
    populated = [column for column in totals["columns"] if column["count"]]
    assert len(populated) == 1
    assert populated[0]["count"] == 1
    assert sum(point["count"] for point in totals["trends"]) == 1
    if contract["name"] in {"customer", "opportunity"}:
        assert "2026-06" in {point["date"] for point in totals["trends"]}
    if contract["name"] == "contract":
        june = next(point for point in totals["trends"] if point["date"] == "2026-06")
        assert june["count"] == 1


@pytest.mark.parametrize("contract", ROUTE_CONTRACTS, ids=lambda item: item["name"])
def test_list_pagination_does_not_change_board_totals(contract, request) -> None:
    api_env = request.getfixturevalue(f"{contract['name']}_api_env")
    module = MODULES[contract["name"]]
    if contract["name"] in {"payment_plan", "payment_record"}:
        module._freeze(request.getfixturevalue("monkeypatch"), date(2026, 10, 12))
    SEEDERS[contract["name"]](api_env, count=7, include_other=False)
    module._grant(api_env.db, 7, contract["view_all_permission"])
    _prepare_list_dependencies(contract, api_env)
    page_name, size_name = contract["list_page"]

    first_list = api_env.client.get(
        contract["list_path"],
        params={page_name: 0 if page_name == "skip" else 1, size_name: 2},
    )
    second_list = api_env.client.get(
        contract["list_path"],
        params={page_name: 2, size_name: 2},
    )
    board = module._board(api_env.client)
    repeated = module._board(api_env.client)

    assert first_list.status_code == 200, first_list.text
    assert second_list.status_code == 200, second_list.text
    assert first_list.json()["total"] == second_list.json()["total"] == 7
    assert len(first_list.json()["items"]) == len(second_list.json()["items"]) == 2
    assert [item["id"] for item in first_list.json()["items"]] != [
        item["id"] for item in second_list.json()["items"]
    ]
    assert board.status_code == 200, board.text
    assert repeated.status_code == 200, repeated.text
    board_body = board.json()
    repeated_body = repeated.json()
    contract["model"].model_validate(board_body)
    assert _structural_totals(board_body) == _structural_totals(repeated_body)
    assert sum(column["count"] for column in board_body["columns"]) == 7
    assert max(len(column["items"]) for column in board_body["columns"]) == 5


@pytest.mark.parametrize("contract", ROUTE_CONTRACTS, ids=lambda item: item["name"])
def test_sort_changes_preview_order_without_changing_totals_or_trends(contract, request) -> None:
    api_env = request.getfixturevalue(f"{contract['name']}_api_env")
    module = MODULES[contract["name"]]
    if contract["name"] in {"payment_plan", "payment_record"}:
        module._freeze(request.getfixturevalue("monkeypatch"), date(2026, 10, 12))
    SEEDERS[contract["name"]](api_env, count=7, include_other=False)
    module._grant(api_env.db, 7, contract["view_all_permission"])

    default_response = module._board(api_env.client)
    sorted_response = module._board(api_env.client, **contract["sort"])

    assert default_response.status_code == 200, default_response.text
    assert sorted_response.status_code == 200, sorted_response.text
    default_body = default_response.json()
    sorted_body = sorted_response.json()
    default_preview = [item["id"] for column in default_body["columns"] for item in column["items"]]
    sorted_preview = [item["id"] for column in sorted_body["columns"] for item in column["items"]]
    assert default_preview != sorted_preview
    assert _structural_totals(default_body) == _structural_totals(sorted_body)

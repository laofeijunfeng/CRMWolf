"""Opportunity board aggregation uses the complete authorized population."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.api import opportunities as opportunities_api
from app.core import database, deps
from app.models.customer import Customer, CustomerProduct
from app.models.opportunity import Opportunity, OpportunityProductModule, OpportunityStatus
from app.models.product import Product, ProductModule
from app.models.permission import Permission
from app.models.procurement import OpportunityStageSnapshot, ProcurementMethod, ProcurementStageTemplate
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User, UserStatus
from app.models.user_role import UserRole


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


TERMINAL_KEYS = ("won", "lost", "unset_stage")
TERMINAL_LABELS = {"won": "已赢单", "lost": "已输单", "unset_stage": "未设置阶段"}
TERMINAL_TONES = {"won": "success", "lost": "danger", "unset_stage": "muted"}
COUNT_LABELS = {"total_count": "商机", "won_count": "赢单"}
AMOUNT_LABELS = {
    "pipeline_amount": "预计金额",
    "weighted_amount": "加权金额",
    "won_amount": "赢单金额",
}


def _customer(customer_id: int, *, name: str, owner_id: str = "7") -> Customer:
    return Customer(
        id=customer_id,
        public_id=f"cus_{customer_id}",
        team_id=1,
        account_name=name,
        city="上海",
        status=0,
        owner_id=owner_id,
        creator_id=owner_id,
        created_time=datetime(2026, 4, 1),
        last_modified_time=datetime(2026, 4, 1),
    )


def _method(method_id: int, *, name: str, code: str) -> ProcurementMethod:
    return ProcurementMethod(
        id=method_id,
        team_id=1,
        code=code,
        name=name,
        is_active=1,
        sort_order=method_id,
        created_by="7",
    )


def _template(
    template_id: int,
    *,
    method_id: int,
    name: str,
    code: str,
    sort_order: int,
) -> ProcurementStageTemplate:
    return ProcurementStageTemplate(
        id=template_id,
        team_id=1,
        procurement_method_id=method_id,
        template_code=code,
        stage_name=name,
        win_probability=40,
        sort_order=sort_order,
        version=1,
        created_by="7",
    )


def _snapshot(
    snapshot_id: int,
    *,
    opportunity_id: int,
    template_id: int,
    name: str,
    sort_order: int,
    code: str,
) -> OpportunityStageSnapshot:
    return OpportunityStageSnapshot(
        id=snapshot_id,
        team_id=1,
        opportunity_id=opportunity_id,
        procurement_stage_template_id=template_id,
        stage_name=name,
        win_probability=40,
        template_sort_order=sort_order,
        template_code=code,
        snapshot_version=1,
        entered_at=datetime(2026, 4, 1),
    )


def _opportunity(
    opportunity_id: int,
    *,
    name: str,
    customer_id: int,
    status: OpportunityStatus = OpportunityStatus.FOLLOWING,
    total_amount: str = "100.00",
    actual_amount: str | None = None,
    win_probability: int = 50,
    expected_closing_date: date | None = date(2026, 9, 1),
    created_time: datetime = datetime(2026, 5, 1),
    owner_id: str = "7",
    snapshot_id: int | None = None,
    stage_name: str | None = None,
    team_id: int = 1,
    public_id: str | None = None,
    approval_phase: str = "approved",
    **extra,
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        public_id=public_id or f"opp_{opportunity_id:02d}",
        team_id=team_id,
        opportunity_number=f"OPP-{opportunity_id:04d}",
        opportunity_name=name,
        customer_id=customer_id,
        total_amount=Decimal(total_amount),
        user_count=10,
        unit_price=Decimal("10.00"),
        license_type=extra.pop("license_type", "SUBSCRIPTION"),
        subscription_years=1,
        purchase_type=extra.pop("purchase_type", "NEW"),
        expected_closing_date=expected_closing_date or date(2026, 9, 1),
        current_stage_snapshot_id=snapshot_id,
        current_stage_name=stage_name,
        win_probability=win_probability,
        owner_id=owner_id,
        creator_id=owner_id,
        status=status.value,
        approval_phase=approval_phase,
        actual_amount=None if actual_amount is None else Decimal(actual_amount),
        created_time=created_time,
        last_modified_time=created_time,
        **extra,
    )


@pytest.fixture
def api_env():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        Product.__table__,
        ProductModule.__table__,
        ProcurementMethod.__table__,
        ProcurementStageTemplate.__table__,
        Opportunity.__table__,
        OpportunityProductModule.__table__,
        OpportunityStageSnapshot.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    current_user = SimpleNamespace(id=7, name="销售张", status="active")
    session.add(User(id=7, email="owner@example.com", name="销售张", avatar_url="https://cdn.example/ada.png", status=UserStatus.ACTIVE))
    session.add(User(id=8, email="other@example.com", name="销售李", status=UserStatus.ACTIVE))
    session.add(_customer(1, name="甲客户"))
    session.add(_customer(2, name="乙客户", owner_id="8"))
    session.add_all([
        _method(3, name="公开招标", code="OPEN"),
        _method(4, name="邀请招标", code="INVITE"),
        _template(8, method_id=3, name="方案", code="proposal", sort_order=20),
        _template(9, method_id=3, name="报价", code="quote", sort_order=10),
        _template(11, method_id=4, name="方案", code="proposal", sort_order=20),
    ])
    session.commit()

    app = FastAPI()
    app.include_router(opportunities_api.router)
    app.dependency_overrides[database.get_db] = lambda: session
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[opportunities_api.get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[opportunities_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[opportunities_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=session, current_user=current_user, app=app)

    session.close()
    engine.dispose()


def _grant(db, user_id: int, *codes: str) -> None:
    role = Role(name=f"角色{user_id}-{'-'.join(codes)}", code=f"role-{user_id}-{len(codes)}-{codes[0]}")
    db.add(role)
    db.flush()
    for code in codes:
        permission = db.query(Permission).filter(Permission.code == code).one_or_none()
        if permission is None:
            permission = Permission(
                name=code,
                code=code,
                resource=code.split(":")[0],
                action=code.split(":")[1],
            )
            db.add(permission)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.add(UserRole(user_id=user_id, role_id=role.id, team_id=1))
    db.commit()


def _board(client: TestClient, **params):
    return client.get("/v1/opportunities/board", params=params)


def _columns(body: dict) -> dict[str, dict]:
    return {column["key"]: column for column in body["columns"]}


def _metric(body: dict, key: str) -> dict:
    return next(metric for metric in body["summary"] if metric["key"] == key)


def _seed_stage_population(db) -> None:
    db.add_all([
        _snapshot(101, opportunity_id=1, template_id=8, name="方案", sort_order=20, code="proposal"),
        _snapshot(102, opportunity_id=2, template_id=9, name="报价", sort_order=10, code="quote"),
        _snapshot(103, opportunity_id=3, template_id=11, name="方案", sort_order=20, code="proposal"),
        _snapshot(104, opportunity_id=4, template_id=8, name="方案", sort_order=20, code="proposal"),
        _snapshot(105, opportunity_id=6, template_id=8, name="   ", sort_order=20, code="blank"),
        _opportunity(
            1,
            name="方案甲",
            customer_id=1,
            total_amount="100.10",
            win_probability=33,
            expected_closing_date=date(2026, 10, 2),
            created_time=datetime(2026, 5, 2),
            snapshot_id=101,
            stage_name="方案",
            purchase_type="RENEWAL",
            license_type="SUBSCRIPTION",
        ),
        _opportunity(
            2,
            name="报价甲",
            customer_id=1,
            total_amount="200.00",
            win_probability=50,
            expected_closing_date=date(2026, 8, 1),
            created_time=datetime(2026, 6, 3),
            snapshot_id=102,
            stage_name="报价",
        ),
        _opportunity(
            3,
            name="邀请方案",
            customer_id=1,
            total_amount="300.00",
            win_probability=25,
            expected_closing_date=date(2026, 9, 1),
            created_time=datetime(2026, 7, 4),
            snapshot_id=103,
            stage_name="方案",
        ),
        _opportunity(
            4,
            name="已赢有实收",
            customer_id=1,
            status=OpportunityStatus.WON,
            total_amount="400.00",
            actual_amount="410.25",
            created_time=datetime(2026, 8, 5),
            snapshot_id=104,
            stage_name="方案",
        ),
        _opportunity(
            5,
            name="已赢回退总额",
            customer_id=1,
            status=OpportunityStatus.WON,
            total_amount="50.00",
            actual_amount=None,
            created_time=datetime(2026, 8, 6),
        ),
        _opportunity(
            6,
            name="空白阶段",
            customer_id=1,
            total_amount="10.00",
            created_time=datetime(2026, 4, 7),
            snapshot_id=105,
            stage_name="   ",
        ),
        _opportunity(
            7,
            name="缺失快照",
            customer_id=1,
            total_amount="20.00",
            created_time=datetime(2026, 4, 8),
        ),
        _opportunity(
            8,
            name="已输单",
            customer_id=1,
            status=OpportunityStatus.LOST,
            total_amount="999.00",
            actual_amount="1.00",
            created_time=datetime(2026, 9, 9),
            snapshot_id=101,
            stage_name="方案",
        ),
        _opportunity(
            9,
            name="其他团队",
            customer_id=1,
            total_amount="1000.00",
            team_id=2,
            snapshot_id=101,
            stage_name="方案",
        ),
    ])
    db.commit()
    template = db.get(ProcurementStageTemplate, 8)
    template.stage_name = "改名后的方案"
    template.sort_order = 1
    db.commit()


def test_board_route_precedes_dynamic_opportunity_route() -> None:
    board_route = next(route for route in opportunities_api.router.routes if getattr(route, "path", None) == "/v1/opportunities/board")
    detail_route = next(route for route in opportunities_api.router.routes if getattr(route, "path", None) == "/v1/opportunities/{opportunity_id}")
    assert opportunities_api.router.routes.index(board_route) < opportunities_api.router.routes.index(detail_route)
    assert "skip" not in board_route.dependant.query_params
    assert "limit" not in board_route.dependant.query_params
    assert "page" not in board_route.dependant.query_params
    assert "page_size" not in board_route.dependant.query_params


def test_board_groups_stable_stage_identity_and_terminal_overrides(api_env) -> None:
    _seed_stage_population(api_env.db)
    _grant(
        api_env.db,
        7,
        "opportunity:view:all",
        "opportunity:edit:own",
        "opportunity:delete:own",
        "opportunity:win",
        "opportunity:lose",
    )

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == ["stage:3:9", "stage:3:8", "stage:4:11", *TERMINAL_KEYS]
    assert columns["stage:3:8"]["label"] == "方案"
    assert columns["stage:3:8"]["column_kind"] == "active_stage"
    assert columns["stage:3:8"]["tone"] == "info"
    assert columns["stage:3:8"]["stage_name"] == "方案"
    assert columns["stage:3:8"]["template_code"] == "proposal"
    assert columns["stage:3:8"]["template_sort_order"] == 20
    assert columns["stage:3:8"]["procurement_method_id"] == 3
    assert columns["stage:3:8"]["procurement_stage_template_id"] == 8
    assert columns["stage:3:8"]["count"] == 1
    assert columns["stage:3:8"]["amount"] == "100.10"
    assert columns["stage:4:11"]["label"] == "方案"
    assert columns["stage:4:11"]["procurement_method_id"] == 4
    assert columns["stage:4:11"]["procurement_stage_template_id"] == 11
    assert columns["stage:3:9"]["template_sort_order"] == 10
    assert {key: columns[key]["label"] for key in TERMINAL_KEYS} == TERMINAL_LABELS
    assert {key: columns[key]["tone"] for key in TERMINAL_KEYS} == TERMINAL_TONES
    assert columns["won"]["count"] == 2
    assert columns["won"]["amount"] == "450.00"
    assert columns["lost"]["count"] == 1
    assert columns["lost"]["amount"] == "999.00"
    assert columns["unset_stage"]["count"] == 2
    assert columns["unset_stage"]["amount"] == "30.00"
    assert "opp_09" not in {item["id"] for column in columns.values() for item in column["items"]}

    proposal = columns["stage:3:8"]["items"][0]
    assert proposal["id"] == "opp_01"
    assert proposal["title"] == "方案甲"
    assert proposal["subtitle"] == "甲客户"
    assert proposal["amount"] == "100.10"
    assert proposal["date"] == "2026-10-02"
    assert proposal["owner"] == {"id": "7", "name": "销售张", "avatar_url": "https://cdn.example/ada.png"}
    assert proposal["status"] == "active"
    assert proposal["metadata"] == {
        "customer_name": "甲客户",
        "purchase_type": "RENEWAL",
        "license_type": "SUBSCRIPTION",
        "expected_closing_date": "2026-10-02",
        "win_probability": 33.0,
        "stage_name": "方案",
        "stage_sort_order": 20,
        "procurement_method_name": "公开招标",
        "procurement_method_code": "OPEN",
        "procurement_stage_template_id": 8,
        "template_code": "proposal",
    }
    assert proposal["action_state"] == {
        "can_edit": True,
        "can_delete": True,
        "can_move_stage": True,
        "can_mark_won": True,
        "can_mark_lost": True,
    }
    assert columns["won"]["items"][0]["status"] == "won"
    assert columns["won"]["items"][0]["action_state"]["can_move_stage"] is False
    assert columns["lost"]["items"][0]["status"] == "lost"
    assert columns["unset_stage"]["items"][0]["status"] == "unset_stage"
    assert columns["unset_stage"]["items"][0]["metadata"]["stage_name"] is None

    assert [metric["key"] for metric in body["summary"]] == [
        "total_count",
        "pipeline_amount",
        "weighted_amount",
        "won_count",
        "won_amount",
    ]
    assert [metric["label"] for metric in body["summary"]] == [
        "商机",
        "预计金额",
        "加权金额",
        "赢单",
        "赢单金额",
    ]
    assert _metric(body, "pipeline_amount")["value"] == "630.10"
    assert _metric(body, "weighted_amount")["value"] == "223.03"
    assert _metric(body, "won_count")["value"] == 2
    assert _metric(body, "won_amount")["value"] == "460.25"
    assert {point["date"]: (point["count"], point["amount"]) for point in body["trends"]} == {
        "2026-04": (2, "30.00"),
        "2026-05": (1, "100.10"),
        "2026-06": (1, "200.00"),
        "2026-07": (1, "300.00"),
        "2026-08": (2, "450.00"),
        "2026-09": (1, "999.00"),
    }


def test_board_preview_keeps_full_column_totals_and_empty_terminal_columns(api_env) -> None:
    rows = []
    for index in range(1, 8):
        rows.append(_snapshot(index, opportunity_id=index, template_id=8, name="方案", sort_order=20, code="proposal"))
        rows.append(_opportunity(
            index,
            name=f"商机{index:02d}",
            customer_id=1,
            total_amount=f"{index}.00",
            expected_closing_date=date(2026, 9, index),
            created_time=datetime(2026, 5, index),
            snapshot_id=index,
            stage_name="方案",
            public_id=f"opp_{index:02d}",
        ))
    api_env.db.add_all(rows)
    api_env.db.commit()
    _grant(api_env.db, 7, "opportunity:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    column = columns["stage:3:8"]
    assert column["count"] == 7
    assert [item["id"] for item in column["items"]] == ["opp_01", "opp_02", "opp_03", "opp_04", "opp_05"]
    assert column["has_more"] is True
    assert column["remaining_count"] == 2
    assert column["amount"] == "28.00"
    assert _metric(body, "total_count")["value"] == 7
    assert _metric(body, "pipeline_amount")["value"] == "28.00"
    for key in TERMINAL_KEYS:
        assert columns[key]["count"] == 0
        assert columns[key]["items"] == []
        assert columns[key]["has_more"] is False
        assert columns[key]["remaining_count"] == 0
        assert columns[key]["amount"] == "0.00"


def test_empty_authorized_population_returns_terminal_columns_and_zero_summary(api_env) -> None:
    api_env.db.add(_opportunity(1, name="其他团队", customer_id=1, team_id=2))
    api_env.db.commit()
    _grant(api_env.db, 7, "opportunity:view:all")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert list(columns) == list(TERMINAL_KEYS)
    assert all(column["count"] == 0 and column["items"] == [] and column["amount"] == "0.00" for column in columns.values())
    assert _metric(body, "total_count")["value"] == 0
    assert _metric(body, "pipeline_amount")["value"] == "0.00"
    assert _metric(body, "weighted_amount")["value"] == "0.00"
    assert _metric(body, "won_count")["value"] == 0
    assert _metric(body, "won_amount")["value"] == "0.00"
    assert body["trends"] == []


def test_stage_date_and_search_filters_use_complete_population(api_env) -> None:
    _seed_stage_population(api_env.db)
    _grant(api_env.db, 7, "opportunity:view:all")

    response = _board(
        api_env.client,
        search="方案甲",
        stage_name="方案",
        status="0",
        expected_closing_date_start="2026-09-01",
        expected_closing_date_end="2026-10-31",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    columns = _columns(body)
    assert columns["stage:3:8"]["count"] == 1
    assert columns["stage:3:8"]["items"][0]["id"] == "opp_01"
    assert "stage:4:11" not in columns
    assert "stage:3:9" not in columns
    assert _metric(body, "total_count")["value"] == 1
    assert _metric(body, "pipeline_amount")["value"] == "100.10"


def test_unified_created_date_bounds_ignore_legacy_dates(api_env, monkeypatch) -> None:
    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 12)

    monkeypatch.setattr(opportunities_api, "date", _FrozenDate)
    api_env.db.add_all([
        _opportunity(1, name="窗口内", customer_id=1, total_amount="10.00", created_time=datetime(2026, 6, 15)),
        _opportunity(2, name="窗口外", customer_id=1, total_amount="20.00", created_time=datetime(2026, 8, 15)),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "opportunity:view:all")

    response = _board(
        api_env.client,
        created_time_start="2026-08-01",
        created_time_end="2026-08-31",
        filters='[{"field":"created_time","op":"after","value":"2026-06-01"},{"field":"created_time","op":"before","value":"2026-06-30"}]',
        sorts="[]",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _columns(body)["unset_stage"]["count"] == 1
    assert _columns(body)["unset_stage"]["items"][0]["id"] == "opp_01"
    assert _metric(body, "total_count")["value"] == 1
    assert body["trends"] == [{"date": "2026-06", "count": 1, "amount": "10.00"}]


def test_sorting_changes_preview_order_only(api_env) -> None:
    rows = []
    closings = [
        date(2026, 9, 3),
        date(2026, 9, 1),
        date(2026, 9, 1),
        date(2026, 9, 9),
        date(2026, 9, 2),
        date(2026, 9, 4),
        date(2026, 9, 5),
    ]
    amounts = ["10.00", "30.00", "40.00", "99.00", "20.00", "5.00", "4.00"]
    for index, (closing, amount) in enumerate(zip(closings, amounts, strict=True), start=1):
        rows.append(_snapshot(index, opportunity_id=index, template_id=8, name="方案", sort_order=20, code="proposal"))
        rows.append(_opportunity(
            index,
            name=f"商机{index}",
            customer_id=1,
            total_amount=amount,
            expected_closing_date=closing,
            created_time=datetime(2026, 5, index),
            snapshot_id=index,
            stage_name="方案",
            public_id=f"opp_{index:02d}",
        ))
    api_env.db.add_all(rows)
    api_env.db.commit()
    _grant(api_env.db, 7, "opportunity:view:all")

    default_response = _board(api_env.client)
    sorted_response = _board(api_env.client, order_by="opportunity_name", order_dir="desc")

    assert default_response.status_code == 200, default_response.text
    assert sorted_response.status_code == 200, sorted_response.text
    default_body = default_response.json()
    sorted_body = sorted_response.json()
    assert [item["id"] for item in _columns(default_body)["stage:3:8"]["items"]] == [
        "opp_03", "opp_02", "opp_05", "opp_01", "opp_06",
    ]
    assert [item["id"] for item in _columns(sorted_body)["stage:3:8"]["items"]] == [
        "opp_07", "opp_06", "opp_05", "opp_04", "opp_03",
    ]
    assert [metric["value"] for metric in default_body["summary"]] == [
        metric["value"] for metric in sorted_body["summary"]
    ]
    assert default_body["trends"] == sorted_body["trends"]
    assert _columns(default_body)["stage:3:8"]["count"] == 7
    assert _columns(default_body)["stage:3:8"]["amount"] == _columns(sorted_body)["stage:3:8"]["amount"]


def test_owner_permission_uses_opportunity_view_scope(api_env) -> None:
    api_env.db.add_all([
        _opportunity(1, name="自己的商机", customer_id=1, owner_id="7"),
        _opportunity(2, name="别人的商机", customer_id=2, owner_id="8"),
    ])
    api_env.db.commit()

    forbidden = _board(api_env.client, owner_id="8")
    own = _board(api_env.client)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据"
    assert own.status_code == 200, own.text
    assert _columns(own.json())["unset_stage"]["count"] == 1
    assert _columns(own.json())["unset_stage"]["items"][0]["id"] == "opp_01"


def test_customer_filter_resolves_public_id_before_population_query(api_env) -> None:
    api_env.db.add_all([
        _opportunity(1, name="甲的商机", customer_id=1, owner_id="7"),
        _opportunity(2, name="乙的商机", customer_id=2, owner_id="8"),
    ])
    api_env.db.commit()
    _grant(api_env.db, 7, "customer:view:all")

    response = _board(api_env.client, customer_id="cus_2")

    assert response.status_code == 200, response.text
    column = _columns(response.json())["unset_stage"]
    assert column["count"] == 1
    assert column["items"][0]["id"] == "opp_02"
    assert column["items"][0]["action_state"]["can_edit"] is False


def test_pending_approval_disables_stage_and_terminal_actions(api_env) -> None:
    api_env.db.add(_opportunity(
        1,
        name="审批中",
        customer_id=1,
        approval_phase="pending_review",
        snapshot_id=None,
    ))
    api_env.db.commit()
    _grant(api_env.db, 7, "opportunity:view:all", "opportunity:edit:all", "opportunity:win", "opportunity:lose")

    response = _board(api_env.client)

    assert response.status_code == 200, response.text
    actions = _columns(response.json())["unset_stage"]["items"][0]["action_state"]
    assert actions["can_edit"] is True
    assert actions["can_move_stage"] is False
    assert actions["can_mark_won"] is False
    assert actions["can_mark_lost"] is False

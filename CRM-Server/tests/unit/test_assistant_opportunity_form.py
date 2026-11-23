"""Behavioral coverage for the read-only opportunity-create form boundary."""

# ruff: noqa: RUF001
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.assistant import AssistantTask, AssistantTaskStatus
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.models.permission import Permission
from app.models.procurement import ProcurementMethod, ProcurementStageTemplate
from app.models.product import Product, ProductModule
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.team import Team, UserTeam
from app.models.user import User
from app.models.user_role import UserRole
from app.services.assistant.opportunity_form import (
    OpportunityFormError,
    prepare_opportunity_form,
    validate_opportunity_form,
)

_QUOTE = "客户确认采购120个账号，预算12.5万元，预计2027年3月15日签约"


def _product(id_, team_id=1, *, is_active=True):
    return Product(id=id_, public_id=f"prd_{id_}", team_id=team_id, code=f"P{id_}", name=f"产品{id_}",
                   created_by="2", is_active=is_active)


def _module(id_, product_id, team_id=1, *, is_active=True):
    return ProductModule(id=id_, public_id=f"prm_{id_}", team_id=team_id, product_id=product_id, code=f"M{id_}",
                         name=f"模块{id_}", created_by="2", sort_order=id_, is_active=is_active)


def _method(id_, team_id):
    return ProcurementMethod(id=id_, team_id=team_id, code=f"P{id_}", name=f"采购{id_}", sort_order=id_, created_by="2")


def _stage(id_, parent, team_id, *, default=True):
    return ProcurementStageTemplate(id=id_, team_id=team_id, procurement_method_id=parent, template_code=f"S{id_}",
                                    stage_name=f"初始阶段{id_}", win_probability=10, sort_order=id_,
                                    is_default_start=int(default), created_by="2")


@pytest.fixture
def form_context():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    models = (User, Team, UserTeam, Role, Permission, RolePermission, UserRole, Customer, CustomerMember,
              Product, ProductModule, CustomerProduct, CustomerActivity, ProcurementMethod, ProcurementStageTemplate,
              Opportunity)
    Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
    try:
        with Session(engine) as db:
            activity = CustomerActivity(id=10, team_id=1, customer_id=7, activity_kind="FOLLOW_UP",
                                        source_content=_QUOTE, creator_id="2", owner_id="2", activity_revision=3)
            activity.content_json = json.dumps({"source_records": [{"segment_id": "seg_1", "text": _QUOTE}]})
            task = AssistantTask(id=1, public_id="ast_1", team_id=1, user_id=2, status=AssistantTaskStatus.ACTIVE,
                                 goal="记录跟进", authority_json={"customer_public_id": "cus_7", "activity_public_id": "10"},
                                 committed_json=[{"kind": "customer_activity", "public_id": "10"}])
            db.add_all([
                activity, User(id=2, name="小李", email="li@example.com"),
                User(id=3, name="同事", email="peer@example.com"),
                User(id=4, name="其他团队", email="other@example.com"),
                Team(id=1, name="一队", code="A0001", owner_id=2), Team(id=2, name="二队", code="A0002", owner_id=4),
                UserTeam(user_id=2, team_id=1), UserTeam(user_id=3, team_id=1), UserTeam(user_id=4, team_id=2),
                Role(id=1, name="销售", code="sales"), UserRole(user_id=2, team_id=1, role_id=1),
                Permission(id=1, name="创建商机", code="opportunity:create", resource="opportunity", action="create"),
                Permission(id=2, name="负责的客户", code="customer:edit:own", resource="customer", action="edit"),
                RolePermission(role_id=1, permission_id=1), RolePermission(role_id=1, permission_id=2),
                Customer(id=7, public_id="cus_7", team_id=1, account_name="北方科技", city="北京", owner_id="2",
                         creator_id="2", default_procurement_method_id=11),
                _method(11, 1), _method(12, 1), _method(13, 2), _stage(21, 11, 1), _stage(22, 12, 1), _stage(23, 13, 2),
                _product(1), _product(2), _product(3, 2), _product(4, is_active=False),
                _module(1, 1), _module(2, 2), _module(3, 3, 2), _module(4, 4), _module(5, 1, is_active=False),
            ])
            db.commit()
            candidate = {"key": "candidate_1", "kind": "opportunity_create", "activity_id": 10, "customer_id": 7,
                         "source_revision": 3, "segment_id": "seg_1", "evidence_quote": _QUOTE,
                         "payload": {"total_amount": 1, "user_count": 2, "expected_closing_date": "2000-01-01"}}
            yield db, task, activity, candidate
    finally:
        engine.dispose()


def test_prepare_and_validate_use_source_and_crm_authority_without_writing(form_context):
    db, task, _, candidate = form_context
    # An unrelated pending write must not autoflush through a read helper.
    pending = Role(name="未保存", code="unsaved")
    db.add(pending)
    spec = prepare_opportunity_form(db, task, candidate)
    for field, value in {"user_count": 120, "total_amount": 125000, "expected_closing_date": "2027-03-15"}.items():
        assert spec["defaults"][field] == value
        assert spec["sources"][field]["label"] == "来自原文"
    assert spec["defaults"]["opportunity_name"] == "北方科技-120人-订阅1年"
    assert spec["defaults"]["procurement_method_id"] == "11"
    assert spec["defaults"]["stage_id"] == "21"
    assert spec["defaults"]["owner_id"] == "2"
    values = {"product_public_id": "prd_2", "product_module_public_ids": ["prm_2", "prm_2"], "user_count": 40,
              "license_type": "PERPETUAL", "procurement_method_id": "12", "owner_id": "3"}
    data = validate_opportunity_form(db, task, candidate, json.loads(json.dumps(spec)), values)
    assert data["customer_id"] == "cus_7"
    assert data["product_module_public_ids"] == ["prm_2"]
    assert data["opportunity_name"] == "北方科技-40人-买断"
    assert data["subscription_years"] is None
    assert data["procurement_method_id"] == 12 and data["stage_id"] == 22 and data["owner_id"] == "3"
    assert pending in db.new
    with db.no_autoflush:
        assert db.query(Opportunity.id).count() == 0


def test_ambiguous_original_values_are_left_empty_and_wrong_segment_is_rejected(form_context):
    db, task, activity, candidate = form_context
    quote = "客户希望采购100至120个账号，预算不超过12万元，预计2027年2月30日签约"
    activity.source_content = quote
    activity.content_json = json.dumps({"source_records": [{"segment_id": "seg_2", "text": quote}]})
    db.commit()
    candidate["evidence_quote"] = quote
    with pytest.raises(OpportunityFormError) as error:
        prepare_opportunity_form(db, task, candidate)
    assert "form" in error.value.field_errors
    candidate["segment_id"] = "seg_2"
    assert not {"user_count", "total_amount", "expected_closing_date"} & prepare_opportunity_form(
        db, task, candidate
    )["defaults"].keys()


def test_truncated_quote_cannot_hide_qualification_or_bind_uncommitted_text(form_context):
    db, task, activity, candidate = form_context
    quote = "客户确认采购120个账号，预算12.5万元"
    source = "客户确认采购约120个账号，预算约12.5万元"
    activity.source_content = source
    activity.content_json = json.dumps({"source_records": [{"segment_id": "seg_1", "text": quote}]})
    db.commit()
    with pytest.raises(OpportunityFormError):
        prepare_opportunity_form(db, task, {**candidate, "evidence_quote": "120个账号"})
    activity.content_json = json.dumps({"source_records": [{"segment_id": "seg_1", "text": source}]})
    db.commit()
    spec = prepare_opportunity_form(db, task, {**candidate, "evidence_quote": "120个账号，预算约12.5万元"})
    assert not {"user_count", "total_amount"} & spec["defaults"].keys()


def test_stage_uses_current_configured_default_but_rejects_new_explicit_option(form_context):
    db, task, _, candidate = form_context
    spec = prepare_opportunity_form(db, task, candidate)
    db.query(ProcurementStageTemplate).filter_by(id=21).update({"is_default_start": 0})
    db.commit()
    with pytest.raises(OpportunityFormError) as error:
        validate_opportunity_form(db, task, candidate, spec, {})
    assert "stage_id" in error.value.field_errors
    assert validate_opportunity_form(db, task, candidate, spec, {"stage_id": "21"})["stage_id"] == 21

    db.add(_stage(24, 11, 1))
    db.commit()
    assert validate_opportunity_form(db, task, candidate, spec, {})["stage_id"] == 24
    with pytest.raises(OpportunityFormError) as error:
        validate_opportunity_form(db, task, candidate, spec, {"stage_id": "24"})
    assert "stage_id" in error.value.field_errors


def test_submit_rejects_wrong_identity_and_field_types(form_context):
    db, task, _, candidate = form_context
    spec = prepare_opportunity_form(db, task, candidate)
    with pytest.raises(OpportunityFormError) as error:
        validate_opportunity_form(db, task, {**candidate, "key": "different"}, spec, {})
    assert "form" in error.value.field_errors
    with pytest.raises(OpportunityFormError) as error:
        validate_opportunity_form(db, task, candidate, spec, {
            "customer_id": "cus_other", "total_amount": True, "user_count": 2.5, "expected_closing_date": 0,
            "product_public_id": "prd_1", "product_module_public_ids": "prm_1",
        })
    assert {"customer_id", "total_amount", "user_count", "expected_closing_date", "product_module_public_ids"} <= (
        error.value.field_errors.keys()
    )


def test_options_exclude_other_team_and_submission_rechecks_frozen_and_live_catalog(form_context):
    db, task, _, candidate = form_context
    spec = prepare_opportunity_form(db, task, candidate)
    assert {item["value"] for item in spec["options"]["product_public_id"]} == {"prd_1", "prd_2"}
    assert {item["value"] for item in spec["options"]["product_module_public_ids"]} == {"prm_1", "prm_2"}
    db.add(_module(6, 1))
    db.query(ProductModule).filter_by(public_id="prm_1").update({"is_active": False})
    db.commit()
    for module in ("prm_1", "prm_2", "prm_3", "prm_6"):
        with pytest.raises(OpportunityFormError) as error:
            validate_opportunity_form(db, task, candidate, spec, {
                "product_public_id": "prd_1", "product_module_public_ids": [module],
                "stage_id": "22", "owner_id": "4",
            })
        assert {"product_module_public_ids", "stage_id", "owner_id"} <= error.value.field_errors.keys()


def test_cap_keeps_each_offered_product_selectable(form_context):
    db, task, _, candidate = form_context
    db.add_all(_module(i, 1) for i in range(10, 80))
    db.commit()
    spec = prepare_opportunity_form(db, task, candidate)
    modules = spec["options"]["product_module_public_ids"]
    assert len(modules) == 50
    assert {item["product_public_id"] for item in modules} == {"prd_1", "prd_2"}
    assert "prm_79" not in {item["value"] for item in modules}


def test_permission_revocation_makes_frozen_form_unusable(form_context):
    db, task, _, candidate = form_context
    spec = prepare_opportunity_form(db, task, candidate)
    db.query(RolePermission).filter_by(permission_id=2).delete()
    db.commit()
    with pytest.raises(OpportunityFormError) as error:
        validate_opportunity_form(db, task, candidate, spec, {
            "product_public_id": "prd_1", "product_module_public_ids": ["prm_1"],
        })
    assert "customer_id" in error.value.field_errors

"""Authorized customer identity resolution application behavior."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.customer_identity_resolution_application_service import (
    CustomerIdentityResolutionApplicationService,
)
from app.services.customer_identity_resolution_service import (
    CustomerIdentityResolution,
    CustomerIdentityResolutionService,
)
from app.services.customer_knowledge_candidate_service import CustomerKnowledgeCandidateResult


class CapturingKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def recall(self, db: object, **kwargs: object) -> CustomerKnowledgeCandidateResult:
        self.calls.append({"db": db, **kwargs})
        return CustomerKnowledgeCandidateResult(
            candidates=[
                {
                    "id": "cus_semantic_related",
                    "account_name": "语义相关客户",
                    "city": "上海",
                    "match": {"score": 0.91, "source": "customer_knowledge"},
                }
            ],
            retrieval_event={"status": "ok"},
        )


class CapturingIdentityService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def resolve(self, db: object, **kwargs: object) -> CustomerIdentityResolution:
        self.calls.append({"db": db, **kwargs})
        return CustomerIdentityResolution(
            items=list(kwargs["lexical_items"]),
            related_customers=list(kwargs["semantic_items"]),
            metadata={"identity_decision": "auto_select"},
        )


def test_application_service_builds_authorized_lexical_and_semantic_identity_evidence(monkeypatch) -> None:
    visible_customer = SimpleNamespace(
        id=11,
        public_id="cus_fanya_001",
        account_name="广州凡亚信息科技有限公司",
        city="广州",
        owner_id="2",
    )
    get_multi_calls: list[dict[str, object]] = []

    def fake_get_multi(**kwargs: object):
        get_multi_calls.append(kwargs)
        return [visible_customer], 1

    monkeypatch.setattr(
        "app.services.customer_identity_resolution_application_service.customer_crud.get_multi",
        fake_get_multi,
    )
    identity_service = CapturingIdentityService()
    knowledge_service = CapturingKnowledgeService()
    service = CustomerIdentityResolutionApplicationService(
        identity_service=identity_service,
        knowledge_service=knowledge_service,
    )
    db = object()

    result = service.resolve(
        db,
        team_id=1,
        user_id=2,
        permission_codes={"customer:view:own"},
        query_text="凡亚信息",
        limit=10,
    )

    assert result.metadata["identity_decision"] == "auto_select"
    assert get_multi_calls == [
        {
            "db": db,
            "team_id": 1,
            "skip": 0,
            "limit": 10,
            "keyword": "凡亚信息",
            "scope": "accessible",
            "current_user_id": "2",
            "include_collaborated": True,
        }
    ]
    assert identity_service.calls[0]["lexical_items"] == [
        {
            "id": "cus_fanya_001",
            "account_name": "广州凡亚信息科技有限公司",
            "city": "广州",
        }
    ]
    assert identity_service.calls[0]["semantic_items"][0]["id"] == "cus_semantic_related"
    visibility = identity_service.calls[0]["visibility_predicate"]
    assert callable(visibility)
    assert visibility(visible_customer) is True


def test_application_service_visibility_allows_owner_or_active_member_only(monkeypatch) -> None:
    service = CustomerIdentityResolutionApplicationService()
    owner = SimpleNamespace(id=1, owner_id="2")
    member_customer = SimpleNamespace(id=2, owner_id="9")
    hidden = SimpleNamespace(id=3, owner_id="9")
    member_calls: list[int] = []

    def fake_get_active_member(db: object, *, team_id: int, customer_id: int, user_id: str):
        assert team_id == 1
        assert user_id == "2"
        member_calls.append(customer_id)
        return object() if customer_id == 2 else None

    monkeypatch.setattr(
        "app.services.customer_identity_resolution_application_service.customer_member_crud.get_active_member",
        fake_get_active_member,
    )
    visibility = service._visibility_predicate(
        object(),
        team_id=1,
        user_id=2,
        permission_codes={"customer:view:own"},
    )

    assert visibility(owner) is True
    assert visibility(member_customer) is True
    assert visibility(hidden) is False
    assert member_calls == [2, 3]


def test_semantic_only_customer_evidence_is_never_promoted_to_authoritative_identity() -> None:
    engine = create_engine("sqlite:///:memory:")
    db = sessionmaker(bind=engine)()
    try:
        resolution = CustomerIdentityResolutionService().resolve(
            db,
            team_id=1,
            query_text="凡亚信息",
            lexical_items=[],
            semantic_items=[
                {
                    "id": "cus_semantic_only",
                    "account_name": "语义高度相关但没有身份词匹配的客户",
                    "city": "上海",
                    "match": {"score": 0.99, "source": "customer_knowledge"},
                }
            ],
            limit=10,
        )

        assert resolution.items == []
        assert resolution.related_customers[0]["id"] == "cus_semantic_only"
        assert resolution.metadata["identity_decision"] == "semantic_related_only"
    finally:
        db.close()
        engine.dispose()


def test_semantic_related_customer_is_projected_to_identity_contract() -> None:
    engine = create_engine("sqlite:///:memory:")
    db = sessionmaker(bind=engine)()
    try:
        resolution = CustomerIdentityResolutionService().resolve(
            db,
            team_id=1,
            query_text="凡亚信息",
            lexical_items=[],
            semantic_items=[
                {
                    "id": "cus_semantic_only",
                    "account_name": "语义相关客户",
                    "city": "上海",
                    "owner_info": {"id": "user_1", "name": "不应泄漏到身份契约"},
                    "collaborator_infos": [],
                    "match": {"score": 0.99, "source": "customer_knowledge"},
                }
            ],
            limit=10,
        )

        assert resolution.related_customers == [
            {
                "id": "cus_semantic_only",
                "account_name": "语义相关客户",
                "city": "上海",
                "match": {"score": 0.99, "source": "customer_knowledge"},
            }
        ]
    finally:
        db.close()
        engine.dispose()


def test_identity_resolution_endpoint_uses_static_route_and_closed_response_contract(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import customers
    from app.core.database import get_db
    from app.core.deps import get_current_active_user, get_current_user_team

    captured: dict[str, object] = {}

    def fake_resolve(db: object, **kwargs: object) -> CustomerIdentityResolution:
        captured.update({"db": db, **kwargs})
        return CustomerIdentityResolution(
            items=[
                {
                    "id": "cus_fanya_001",
                    "account_name": "广州凡亚信息科技有限公司",
                    "city": "广州",
                    "match": {"score": 0.99, "source": "generated_match_term"},
                }
            ],
            related_customers=[],
            metadata={"identity_decision": "auto_select"},
        )

    monkeypatch.setattr(
        customers.customer_identity_resolution_application_service,
        "resolve",
        fake_resolve,
    )
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda db, user_id, team_id: [SimpleNamespace(code="customer:view:own")],
    )
    fake_db = object()
    app = FastAPI()
    app.include_router(customers.router)
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user_team] = lambda: 1
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=2)

    with TestClient(app) as client:
        response = client.get(
            "/v1/customers/identity-resolution",
            params={"query": "凡亚信息", "limit": 10},
        )

    assert response.status_code == 200
    assert response.json() == {
        "decision": "auto_select",
        "items": [
            {
                "id": "cus_fanya_001",
                "account_name": "广州凡亚信息科技有限公司",
                "city": "广州",
                "match": {"score": 0.99, "source": "generated_match_term"},
            }
        ],
        "related_customers": [],
        "metadata": {"identity_decision": "auto_select"},
    }
    assert captured == {
        "db": fake_db,
        "team_id": 1,
        "user_id": 2,
        "permission_codes": {"customer:view:own"},
        "query_text": "凡亚信息",
        "limit": 10,
    }

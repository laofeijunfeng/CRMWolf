import pytest
from app.schemas.customer_profile import CustomerProfileSections
from app.services.customer_profile_claim_grounding import (
    PROFILE_CLAIM_UNGROUNDED,
    assert_claims_grounded,
)
from app.services.customer_profile_projection_service import (
    CustomerProfileProjectionDraft,
    CustomerProfileProjectionError,
    CustomerProfileProjectionService,
)
from app.services.customer_profile_projection_validator import (
    CustomerProfileProjectionValidationError,
)

OLD = "客户正在重新评估 Apifox 私有化部署方案，需要私有环境安装包和试用方案。"
QUOTE = "今天看到了 Hifox，需要私有化部署。"
BOUND_STATEMENT = "客户正在评估 Apifox 私有化部署。"


def test_assert_claims_grounded_rejects_apifox_template():
    sections = CustomerProfileSections(
        current_situation={
            "summary": OLD,
            "demand_background": {
                "summary": OLD,
                "items": [{
                    "statement": OLD,
                    "evidence_refs": ["activity:1"],
                    "product_names": [],
                }],
            },
        },
        current_journeys=[],
        important_changes=[],
        long_term_context={},
        follow_up_process=[],
        recorded_follow_ups=[],
    )
    with pytest.raises(CustomerProfileProjectionValidationError) as exc:
        assert_claims_grounded(
            sections,
            evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
            product_catalog_names=["Hifox", "Apifox"],
        )
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_validate_draft_rejects_ungrounded_demand_statement():
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={
                "demand_background": {
                    "summary": OLD,
                    "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
                }
            },
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.validate_draft(draft)
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_xiexin_draft_passes_grounding():
    service = CustomerProfileProjectionService()
    text = (
        "联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，"
        "在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，"
        "会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，"
        "客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。"
    )
    draft = service.draft_from_context(
        context={
            "product_catalog": [
                {"public_id": "prd_hifox", "name": "Hifox", "is_active": True},
                {"public_id": "prd_apifox", "name": "Apifox", "is_active": True},
            ],
            "strong_context": {
                "customer": {"account_name": "成都协鑫数智科技有限责任公司", "products": []},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [{
                    "id": 1,
                    "content": text,
                    "source_content": text,
                    "occurred_at": "2026-09-16T10:00:00",
                    "title": "电话跟进",
                }],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
        },
        source_event_key="repro",
    )
    service.validate_draft(draft)
    item = draft.sections.current_situation["demand_background"]["items"][0]
    assert "Hifox" in item["statement"]
    assert "Apifox" not in item["statement"]
    assert draft.evidence_refs[0]["snippet"]


def _apifox_claim_sections(*, product_names, product_public_ids=None):
    item = {
        "statement": BOUND_STATEMENT,
        "evidence_refs": ["activity:1"],
        "product_names": product_names,
    }
    if product_public_ids is not None:
        item["product_public_ids"] = product_public_ids
    return CustomerProfileSections(
        current_situation={
            "summary": BOUND_STATEMENT,
            "demand_background": {
                "summary": BOUND_STATEMENT,
                "items": [item],
            },
        },
        current_journeys=[],
        important_changes=[],
        long_term_context={},
        follow_up_process=[],
        recorded_follow_ups=[],
    )


def test_assert_claims_grounded_rejects_unbound_product_names():
    sections = _apifox_claim_sections(product_names=["Apifox"])
    with pytest.raises(CustomerProfileProjectionValidationError) as exc:
        assert_claims_grounded(
            sections,
            evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
            product_catalog_names=["Hifox", "Apifox"],
        )
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_assert_claims_grounded_allows_bound_product_names():
    sections = _apifox_claim_sections(
        product_names=["Apifox"],
        product_public_ids=["prd_apifox"],
    )
    assert_claims_grounded(
        sections,
        evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
        product_catalog_names=["Hifox", "Apifox"],
    )


def test_semantic_evidence_activity_key_collision_keeps_activity_snippet():
    service = CustomerProfileProjectionService()
    text = (
        "联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，"
        "在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，"
        "会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，"
        "客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。"
    )
    draft = service.draft_from_context(
        context={
            "product_catalog": [
                {"public_id": "prd_hifox", "name": "Hifox", "is_active": True},
                {"public_id": "prd_apifox", "name": "Apifox", "is_active": True},
            ],
            "semantic_evidence": [
                {
                    "evidence_key": "activity:1",
                    "source_type": "semantic_evidence",
                    "source_id": "1",
                    "title": "语义召回",
                }
            ],
            "strong_context": {
                "customer": {"account_name": "成都协鑫数智科技有限责任公司", "products": []},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [{
                    "id": 1,
                    "content": text,
                    "source_content": text,
                    "occurred_at": "2026-09-16T10:00:00",
                    "title": "电话跟进",
                }],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
        },
        source_event_key="collision",
    )
    activity_rows = [row for row in draft.evidence_refs if row.get("evidence_key") == "activity:1"]
    assert len(activity_rows) == 1
    row = activity_rows[0]
    snippet = row.get("snippet") or ""
    assert snippet
    assert "Hifox" in snippet
    assert "私有化部署" in snippet
    assert row["source_type"] == "customer_activity"
    assert row["title"] == "电话跟进"
    service.validate_draft(draft)
    item = draft.sections.current_situation["demand_background"]["items"][0]
    assert "Hifox" in item["statement"]
    assert_claims_grounded(
        draft.sections,
        evidence_refs=draft.evidence_refs,
        product_catalog_names=["Hifox", "Apifox"],
    )

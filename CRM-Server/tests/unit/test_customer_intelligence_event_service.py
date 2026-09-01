from datetime import datetime

from app.models.customer import Contact
from app.models.customer_activity import CustomerActivity
from app.models.deal_journey import CustomerDealJourneyEvent, DealJourneyEventType
from app.services.customer_intelligence_event_service import customer_intelligence_event_service


def test_customer_activity_event_is_stable_and_business_readable() -> None:
    activity = CustomerActivity(
        id=701,
        team_id=2,
        customer_id=101,
        activity_kind="PHONE_FOLLOW_UP",
        title="电话跟进",
        source_content="张总说本周开始 POC。",
        summary="客户进入 POC。",
        next_action="准备试用环境",
        occurred_at=datetime(2026, 8, 2, 10, 0, 0),
        creator_id="9",
        owner_id="9",
    )

    first = customer_intelligence_event_service.from_customer_activity(activity)
    second = customer_intelligence_event_service.from_customer_activity(activity)

    assert first is not None
    assert second is not None
    assert first.event_key == second.event_key
    assert first.trigger_type == "customer_activity_created"
    assert first.source.business_object_type == "customer_activity"
    assert first.summary == "客户进入 POC。"
    assert first.thread_id() == f"customer_intelligence:2:{first.event_key}"


def test_deleted_customer_activity_event_keeps_negative_recompute_snapshot() -> None:
    activity = CustomerActivity(
        id=702,
        team_id=2,
        customer_id=101,
        activity_kind="MEETING",
        title="需求沟通",
        source_content="客户需要支持国产化服务器部署。",
        content_json='{"需求背景":"支持国产化服务器部署"}',
        summary="确认服务器部署要求。",
        next_action="补充部署环境清单",
        next_follow_time=datetime(2026, 8, 4, 10, 0, 0),
        occurred_at=datetime(2026, 8, 2, 10, 0, 0),
        creator_id="9",
        owner_id="9",
    )

    event = customer_intelligence_event_service.from_customer_activity(
        activity,
        trigger_type="customer_activity_deleted",
    )

    assert event is not None
    snapshot = event.payload["deleted_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["source_content"] == "客户需要支持国产化服务器部署。"
    assert snapshot["content_json"] == {"需求背景": "支持国产化服务器部署"}
    assert snapshot["next_action"] == "补充部署环境清单"


def test_deal_journey_event_normalizes_business_flow_source() -> None:
    journey_event = CustomerDealJourneyEvent(
        id=901,
        team_id=2,
        deal_journey_id=801,
        customer_id=101,
        event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
        event_time=datetime(2026, 8, 2, 12, 0, 0),
        source_type="opportunity_stage_snapshot",
        source_id=301,
        actor_id="9",
        summary="商机阶段推进到 POC",
        metadata_json='{"stage_name":"POC","win_probability":60}',
    )

    event = customer_intelligence_event_service.from_deal_journey_event(journey_event)

    assert event is not None
    assert event.trigger_type == "deal_journey_event_recorded"
    assert event.source.source_type == "deal_journey_event"
    assert event.source.business_object_type == "opportunity_stage_snapshot"
    assert event.source.business_object_id == "301"
    assert event.payload["metadata"] == {"stage_name": "POC", "win_probability": 60}


def test_contact_event_normalizes_customer_contact_without_sensitive_ids_in_summary() -> None:
    contact = Contact(
        id=601,
        team_id=2,
        customer_id=101,
        name="张总",
        mobile="13800138000",
        position="总经理",
        is_decision_maker=1,
        is_primary=0,
        created_time=datetime(2026, 8, 2, 12, 30, 0),
    )

    event = customer_intelligence_event_service.from_contact(contact)

    assert event is not None
    assert event.trigger_type == "customer_contact_created"
    assert event.source.business_object_type == "contact"
    assert event.customer_id == 101
    assert event.summary == "客户联系人已新增: 张总"
    assert event.payload["position"] == "总经理"
    assert event.payload["is_decision_maker"] is True

    updated_event = customer_intelligence_event_service.from_contact(
        contact,
        trigger_type="customer_contact_updated",
        actor_id="9",
    )
    deleted_event = customer_intelligence_event_service.from_contact(
        contact,
        trigger_type="customer_contact_deleted",
        actor_id="9",
    )

    assert updated_event is not None
    assert deleted_event is not None
    assert updated_event.summary == "客户联系人已更新: 张总"
    assert deleted_event.summary == "客户联系人已删除: 张总"
    assert event.source.source_version == updated_event.source.source_version == deleted_event.source.source_version


def test_contact_event_identity_changes_when_contact_facts_change() -> None:
    contact = Contact(
        id=602,
        team_id=2,
        customer_id=101,
        name="李总",
        mobile="13800138001",
        position="采购负责人",
        is_decision_maker=0,
        is_primary=0,
        remark="负责服务器采购",
        created_time=datetime(2026, 8, 2, 12, 30, 0),
        updated_time=datetime(2026, 8, 2, 13, 0, 0),
    )

    first = customer_intelligence_event_service.from_contact(contact, trigger_type="customer_contact_updated")
    repeated = customer_intelligence_event_service.from_contact(contact, trigger_type="customer_contact_updated")

    contact.position = "信息中心主任"
    contact.post_commit_revision = 2
    changed = customer_intelligence_event_service.from_contact(contact, trigger_type="customer_contact_updated")

    assert first is not None
    assert repeated is not None
    assert changed is not None
    assert first.event_key == repeated.event_key
    assert first.source.source_version == repeated.source.source_version
    assert first.occurred_at == datetime(2026, 8, 2, 13, 0, 0)
    assert first.event_key != changed.event_key
    assert first.source.source_version != changed.source.source_version
    assert changed.source.source_version == 2

    contact.position = "采购负责人"
    contact.post_commit_revision = 3
    reverted = customer_intelligence_event_service.from_contact(contact, trigger_type="customer_contact_updated")

    assert reverted is not None
    assert reverted.event_key != first.event_key
    assert reverted.source.source_version == 3


def test_contact_event_identity_includes_profile_relevant_relationship_fields() -> None:
    contact = Contact(
        id=603,
        team_id=2,
        customer_id=101,
        name="王工",
        mobile="13800138002",
        position="技术负责人",
        is_decision_maker=0,
        is_primary=0,
        reports_to=601,
        created_time=datetime(2026, 8, 2, 12, 30, 0),
    )

    first = customer_intelligence_event_service.from_contact(contact, trigger_type="customer_contact_updated")
    contact.reports_to = 602
    contact.post_commit_revision = 2
    changed = customer_intelligence_event_service.from_contact(contact, trigger_type="customer_contact_updated")

    assert first is not None
    assert changed is not None
    assert first.event_key != changed.event_key


def test_business_object_change_event_carries_source_version_and_is_idempotent() -> None:
    first = customer_intelligence_event_service.business_object_changed(
        team_id=2,
        customer_id=101,
        actor_id="9",
        trigger_type="customer_business_object_updated",
        source_type="opportunity",
        source_id=301,
        source_version=7,
        change_id="transport-attempt-a",
        summary="商机已更新",
    )
    second = customer_intelligence_event_service.business_object_changed(
        team_id=2,
        customer_id=101,
        actor_id="10",
        trigger_type="customer_business_object_updated",
        source_type="opportunity",
        source_id=301,
        source_version=7,
        change_id="transport-attempt-b",
        summary="商机已更新",
    )

    assert first.event_key == second.event_key
    assert first.source.source_version == 7
    assert first.source.source_object_id == "301"


def test_business_object_change_event_uses_stable_key_and_business_summary() -> None:
    first = customer_intelligence_event_service.business_object_changed(
        team_id=2,
        customer_id=101,
        actor_id="9",
        trigger_type="customer_business_object_updated",
        source_type="opportunity",
        source_id=301,
        change_id="change-1",
        summary="商机已更新: 企业版采购",
        payload={"object_name": "企业版采购", "amount": 120000},
        occurred_at=datetime(2026, 8, 2, 12, 40, 0),
    )
    second = customer_intelligence_event_service.business_object_changed(
        team_id=2,
        customer_id=101,
        actor_id="9",
        trigger_type="customer_business_object_updated",
        source_type="opportunity",
        source_id=301,
        change_id="change-1",
        summary="商机已更新: 企业版采购",
        payload={"object_name": "企业版采购", "amount": 120000},
        occurred_at=datetime(2026, 8, 2, 12, 40, 0),
    )

    assert first.event_key == second.event_key
    assert first.trigger_type == "customer_business_object_updated"
    assert first.source.business_object_type == "opportunity"
    assert first.source.business_object_id == "301"
    assert first.summary == "商机已更新: 企业版采购"
    assert "301" not in (first.summary or "")
    assert first.payload["object_name"] == "企业版采购"


def test_manual_and_agent_events_do_not_require_internal_user_input_ids() -> None:
    manual_event = customer_intelligence_event_service.manual_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="refresh-1",
        refresh_scope="partial",
        occurred_at=datetime(2026, 8, 2, 13, 0, 0),
    )
    question_event = customer_intelligence_event_service.agent_customer_question(
        team_id=2,
        customer_id=101,
        actor_id="9",
        session_id=77,
        message_id=88,
        question="总结一下这个客户现在什么情况",
    )

    assert manual_event.source.business_object_type == "customer"
    assert manual_event.payload["refresh_scope"] == "partial"
    assert question_event.source.source_type == "agent_message"
    assert question_event.summary == "总结一下这个客户现在什么情况"


def test_batch_rebuild_event_groups_runs_without_internal_object_ids_in_summary() -> None:
    event = customer_intelligence_event_service.batch_rebuild_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="batch-rebuild-1",
        refresh_scope="full",
        occurred_at=datetime(2026, 8, 2, 13, 30, 0),
    )

    assert event.trigger_type == "customer_intelligence_batch_rebuild_requested"
    assert event.source.source_type == "batch_rebuild"
    assert event.source.source_object_id == "batch-rebuild-1"
    assert event.source.business_object_type == "customer"
    assert event.source.business_object_id == "101"
    assert event.summary == "批量重建客户智能档案"
    assert event.payload["refresh_scope"] == "full"
    assert event.payload["request_id"] == "batch-rebuild-1"


def test_customer_lifecycle_event_requests_full_profile_refresh() -> None:
    event = customer_intelligence_event_service.customer_lifecycle_refresh_requested(
        team_id=2,
        customer_id=101,
        actor_id="9",
        request_id="customer-created-1",
        trigger_type="customer_converted_from_lead",
        source_lead_id=501,
        occurred_at=datetime(2026, 8, 2, 14, 0, 0),
    )

    assert event.trigger_type == "customer_converted_from_lead"
    assert event.source.source_type == "lead_conversion"
    assert event.source.source_object_id == "501"
    assert event.source.business_object_type == "customer"
    assert event.source.business_object_id == "101"
    assert event.payload["refresh_scope"] == "full"
    assert event.payload["source_lead_id"] == 501


def test_deal_journey_association_event_gets_dedicated_trigger_and_keeps_transition_evidence() -> None:
    journey_event = CustomerDealJourneyEvent(
        id=902,
        team_id=2,
        deal_journey_id=802,
        customer_id=101,
        event_type=DealJourneyEventType.ASSOCIATION_CHANGED,
        event_time=datetime(2026, 8, 2, 12, 0, 0),
        source_type="opportunity",
        source_id=302,
        actor_id="9",
        summary="商机已关联业务旅程: 气象装备采购",
        metadata_json=(
            '{"association_reason":"ENSURE_FOR_OPPORTUNITY",'
            '"new_deal_journey_id":802,"opportunity_id":302,'
            '"previous_deal_journey_id":null}'
        ),
    )

    event = customer_intelligence_event_service.from_deal_journey_event(journey_event)

    assert event is not None
    assert event.trigger_type == "deal_journey_association_changed"
    assert event.deal_journey_id == 802
    assert event.payload["metadata"]["new_deal_journey_id"] == 802
    assert event.source.business_object_type == "opportunity"


def test_sales_commitment_event_uses_transition_revision_in_source_and_key() -> None:
    first = customer_intelligence_event_service.sales_commitment_changed(
        team_id=2,
        customer_id=101,
        actor_id="9",
        trigger_type="sales_commitment_updated",
        commitment_id=701,
        change_id=1,
        deal_journey_id=None,
        summary="承诺更新",
    )
    second = customer_intelligence_event_service.sales_commitment_changed(
        team_id=2,
        customer_id=101,
        actor_id="9",
        trigger_type="sales_commitment_updated",
        commitment_id=701,
        change_id=2,
        deal_journey_id=None,
        summary="承诺更新",
    )

    assert first.source.source_version == 1
    assert second.source.source_version == 2
    assert first.event_key != second.event_key

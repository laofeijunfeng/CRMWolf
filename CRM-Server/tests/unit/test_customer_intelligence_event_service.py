from datetime import datetime

from app.models.customer import Contact, Customer
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


def test_customer_profile_and_brief_events_keep_generated_content_as_payload() -> None:
    customer = Customer(
        id=101,
        team_id=2,
        account_name="越秀金融",
        industry="金融",
        creator_id="9",
        company_background="地方金融控股集团。",
        main_business="金融控股与投资管理。",
        project_background="希望规范采购流程。",
        profile_generated_time=datetime(2026, 8, 2, 11, 0, 0),
        customer_brief_json='{"overview":{"progress":"POC"}}',
        customer_brief_markdown="客户进入 POC。",
        customer_brief_generated_time=datetime(2026, 8, 2, 11, 30, 0),
    )

    profile_event = customer_intelligence_event_service.from_customer_profile(customer)
    brief_event = customer_intelligence_event_service.from_customer_brief(customer)

    assert profile_event is not None
    assert brief_event is not None
    assert profile_event.trigger_type == "customer_profile_generated"
    assert profile_event.payload["company_background"] == "地方金融控股集团。"
    assert brief_event.trigger_type == "customer_brief_generated"
    assert brief_event.payload["customer_brief_json"] == {"overview": {"progress": "POC"}}


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
        refresh_scope="dynamic_brief",
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
    assert manual_event.payload["refresh_scope"] == "dynamic_brief"
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

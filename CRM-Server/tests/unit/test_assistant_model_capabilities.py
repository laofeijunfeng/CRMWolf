"""Assistant readiness is certified only after all contracts pass for one saved config."""

from copy import deepcopy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.ai_config import AIConfig
from app.schemas.assistant_conversation import ConversationDecision
from app.services.assistant.failure_contract import AssistantFailureCode
from app.services.assistant.llm_contracts import StructuredMeeting
from app.services.assistant.model_capabilities import (
    CAPABILITY_SAMPLE,
    AssistantModelCapabilities,
    assistant_verification_is_current,
)
from app.services.assistant.model_transport import AssistantLLMError
from app.services.assistant.quality_gate import AssistantQualityResponse
from app.services.customer_activity_ai.schemas import MeetingContent


@pytest.fixture
def configured_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[AIConfig.__table__])
    with Session(engine) as db:
        db.add(AIConfig(
            id=1, team_id=1, api_host="https://model.example/v1",
            api_key_encrypted=AIConfig.encrypt_api_key("sk-test"), model_name="assistant-model",
            temperature=0.1, max_tokens=1024, structured_output_mode="json_object",
        ))
        db.commit()
        yield db
    engine.dispose()


def _meeting() -> StructuredMeeting:
    mentions = []
    for raw_text, kind, role, owner in (
        ("11月", "FULL_MONTH", "CUSTOMER_COMMITMENT", "客户王经理"),
        ("下周三", "RELATIVE_WEEKDAY", "SALES_FOLLOW_UP", "我方李经理"),
    ):
        start = CAPABILITY_SAMPLE.index(raw_text)
        mentions.append({
            "raw_text": raw_text, "quote_start": start, "quote_end": start + len(raw_text),
            "kind": kind, "role": role, "owner": owner, "confidence": 1,
        })
    content = MeetingContent(
        meeting_subject="产品评估", meeting_background="客户评估产品", communication_context="线上会议",
        participants={"internal": ["李经理"], "customer": ["王经理"]},
        key_minutes=["客户承诺11月完成评估"], qa_items=[], requirements=["产品评估"],
        concerns_or_objections=[], risks=[], decisions_or_commitments=["11月完成评估"],
        action_items=[], next_step_summary="李经理下周三发送方案", next_action_absence_reason="",
    )
    return StructuredMeeting(
        customer_name="示例客户", meeting_subject="产品评估", content=CAPABILITY_SAMPLE,
        participants="客户王经理、我方李经理", next_action="李经理下周三发送方案",
        next_follow_time_text="下周三", temporal_mentions=mentions, actions=[], content_json=content,
    )


class CapabilityTransport:
    def __init__(self, *, quality=None, failure=None, on_quality=None, plan_confidence=1):
        self.quality = quality or {
            "score": 82, "reason": "事实完整",
            "principle_scores": [{"name": "客户反馈", "score": 18, "max_score": 20, "comment": "清晰"}],
            "supplement_question": None,
        }
        self.failure = failure
        self.on_quality = on_quality
        self.plan_confidence = plan_confidence
        self.modes = []

    async def ainvoke_structured(self, **kwargs):
        self.modes.append(kwargs["output_mode"])
        if self.failure is not None:
            failure, self.failure = self.failure, None
            raise failure
        if kwargs["response_model"] is ConversationDecision:
            return ConversationDecision.model_validate({
                "semantic_plan": {
                    "speech_act": "ASSERT_EVENT", "business_object": "CUSTOMER_ACTIVITY", "operation": "CREATE",
                    "confidence": self.plan_confidence,
                },
                "task_relation": "NEW_TASK", "route": "WORKFLOW", "boundary": "NEW", "confidence": 1,
            })
        if kwargs["response_model"] is StructuredMeeting:
            return _meeting()
        if self.on_quality:
            self.on_quality()
        return deepcopy(self.quality)


async def test_schema_fallback_is_explicit_and_certifies_the_actual_protocol(configured_db):
    transport = CapabilityTransport(failure=AssistantLLMError(
        "unsupported", code=AssistantFailureCode.REQUEST_PROTOCOL_ERROR, schema_protocol_rejected=True,
    ))
    result = await AssistantModelCapabilities(transport).verify(configured_db, team_id=1)
    saved = configured_db.get(AIConfig, 1)
    assert result.success
    assert transport.modes == ["json_schema", "json_object", "json_object", "json_object"]
    assert saved.structured_output_mode == "json_object"
    assert assistant_verification_is_current(saved, "sk-test")


async def test_authentication_failure_never_falls_back_or_certifies(configured_db):
    transport = CapabilityTransport(failure=AssistantLLMError(
        "provider secret body", code=AssistantFailureCode.AUTHENTICATION_ERROR,
    ))
    result = await AssistantModelCapabilities(transport).verify(configured_db, team_id=1)
    assert not result.success
    assert result.code == "AUTHENTICATION_ERROR"
    assert transport.modes == ["json_schema"]
    assert "provider secret body" not in result.message
    assert not assistant_verification_is_current(configured_db.get(AIConfig, 1), "sk-test")


async def test_low_confidence_root_plan_is_not_certified(configured_db):
    # Production routing refuses this decision, so the capability check must too.
    transport = CapabilityTransport(plan_confidence=0.5)
    result = await AssistantModelCapabilities(transport).verify(configured_db, team_id=1)
    assert not result.success
    assert result.stage == "ROOT_DECISION"
    assert result.code == "MODEL_OUTPUT_INVALID"
    assert not assistant_verification_is_current(configured_db.get(AIConfig, 1), "sk-test")


async def test_invalid_quality_prevents_false_readiness(configured_db):
    duplicate = {"name": "客户反馈", "score": 18, "max_score": 20, "comment": "清晰"}
    transport = CapabilityTransport(quality={
        "score": 82, "reason": "完整", "principle_scores": [duplicate, duplicate], "supplement_question": None,
    })
    result = await AssistantModelCapabilities(transport).verify(configured_db, team_id=1)
    assert not result.success
    assert result.stage == "QUALITY_STREAM"
    assert result.code == "MODEL_OUTPUT_INVALID"
    assert configured_db.get(AIConfig, 1).assistant_verified_fingerprint is None


async def test_configuration_changed_during_probe_cannot_be_certified(configured_db):
    def change_model():
        config = configured_db.get(AIConfig, 1)
        config.model_name = "different-model"
        configured_db.commit()

    capabilities = AssistantModelCapabilities(CapabilityTransport(on_quality=change_model))
    result = await capabilities.verify(configured_db, team_id=1)
    assert not result.success
    assert result.code == "CONFIGURATION_CHANGED"
    saved = configured_db.get(AIConfig, 1)
    assert saved.model_name == "different-model"
    assert saved.assistant_verified_fingerprint is None


def test_quality_wire_response_normalizes_open_consumer_map():
    result = AssistantQualityResponse.model_validate({
        "score": 82, "reason": "事实完整",
        "principle_scores": [{"name": "客户反馈", "score": 18, "max_score": 20, "comment": "清晰"}],
        "supplement_question": None,
    }).to_activity_score()
    assert result.principle_scores["客户反馈"].max_score == 20

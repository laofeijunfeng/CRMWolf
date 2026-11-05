"""Read-only, end-to-end capability verification of the team's assistant model."""
# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING

from cryptography.fernet import InvalidToken
from pydantic import ValidationError

from app.crud.ai_config import ai_config_crud
from app.models.ai_config import AIConfig
from app.schemas.ai_config import AssistantCapabilityResponse, AssistantVerificationStage, StructuredOutputMode
from app.schemas.assistant_conversation import ConversationDecision
from app.services.assistant.conversation_router import ROOT_SYSTEM_PROMPT
from app.services.assistant.failure_contract import AssistantFailureCode, root_failure_presentation
from app.services.assistant.llm import STRUCTURE_MEETING_PROMPT, _require_complete_content
from app.services.assistant.llm_contracts import StructuredMeeting
from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport
from app.services.assistant.quality_gate import AssistantQualityResponse, quality_system_prompt
from app.services.assistant.temporal_evidence import validate_temporal_quotes
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

CAPABILITY_SAMPLE = (
    "与示例客户开线上会议，客户王经理与我方李经理参加，讨论产品评估。"
    "客户王经理承诺11月完成评估，我方李经理下周三发送方案。"
)
_CAPABILITY_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class _ConfigSnapshot:
    api_host: str
    api_key: str = field(repr=False)
    model: str
    output_mode: StructuredOutputMode
    fingerprint: str = field(repr=False)


@dataclass(frozen=True)
class _ProbeSuccess:
    output_mode: StructuredOutputMode
    tested_fingerprint: str = field(repr=False)


def assistant_verification_is_current(config: AIConfig, api_key: str) -> bool:
    fingerprint = AIConfig.capability_fingerprint(
        config.api_host, api_key, config.model_name, config.structured_output_mode or "json_object",
    )
    return bool(config.assistant_verified_at and config.assistant_verified_fingerprint == fingerprint)


class AssistantModelCapabilities:
    def __init__(self, transport: AssistantModelTransport | None = None) -> None:
        self.transport = transport or AssistantModelTransport()

    async def verify(self, db: Session, *, team_id: int) -> AssistantCapabilityResponse:
        config = ai_config_crud.get_config(db, team_id)
        if config is None:
            return self._failure("CONFIGURATION", AssistantFailureCode.CONFIGURATION_ERROR)
        # Snapshot before releasing the DB transaction: no live ORM state may change what was tested.
        try:
            api_key = AIConfig.decrypt_api_key(config.api_key_encrypted)
            mode: StructuredOutputMode = config.structured_output_mode or "json_object"
            snapshot = _ConfigSnapshot(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                output_mode=mode,
                fingerprint=AIConfig.capability_fingerprint(config.api_host, api_key, config.model_name, mode),
            )
        except (InvalidToken, ValueError, TypeError):
            ai_config_crud.mark_assistant_unverified(db, team_id=team_id)
            return self._failure("CONFIGURATION", AssistantFailureCode.CONFIGURATION_ERROR)
        # A failed recheck must never leave an old successful readiness claim behind.
        ai_config_crud.mark_assistant_unverified(db, team_id=team_id)
        stage: AssistantVerificationStage = "ROOT_DECISION"
        deadline = monotonic() + _CAPABILITY_TIMEOUT_SECONDS
        output_mode: StructuredOutputMode = "json_schema"
        try:
            async with asyncio.timeout(_CAPABILITY_TIMEOUT_SECONDS):
                while True:
                    try:
                        stage = "ROOT_DECISION"
                        await self._verify_root(snapshot, output_mode, deadline)
                        stage = "MEETING_STREAM"
                        meeting = await self._verify_meeting(snapshot, output_mode, deadline)
                        stage = "QUALITY_STREAM"
                        await self._verify_quality(snapshot, output_mode, deadline, meeting)
                        break
                    except AssistantLLMError as exc:
                        # Only explicit upstream rejection authorizes changing the protocol. Invalid
                        # JSON, schema failures, auth failures and timeouts fail closed without fallback.
                        if output_mode == "json_schema" and exc.schema_protocol_rejected:
                            output_mode = "json_object"
                            continue
                        raise
            probe = _ProbeSuccess(
                output_mode=output_mode,
                tested_fingerprint=AIConfig.capability_fingerprint(
                    snapshot.api_host, snapshot.api_key, snapshot.model, output_mode,
                ),
            )
        except AssistantLLMError as exc:
            return self._failure(stage, exc.code, output_mode)
        except TimeoutError:
            return self._failure(stage, AssistantFailureCode.UPSTREAM_TIMEOUT, output_mode)
        except (ValidationError, ValueError, TypeError):
            return self._failure(stage, AssistantFailureCode.MODEL_OUTPUT_INVALID, output_mode)
        except Exception:
            return self._failure(stage, AssistantFailureCode.INTERNAL_ERROR, output_mode)
        verified_at = business_now()
        saved = ai_config_crud.mark_assistant_verified(
            db,
            team_id=team_id,
            expected_fingerprint=snapshot.fingerprint,
            tested_fingerprint=probe.tested_fingerprint,
            output_mode=probe.output_mode,
            verified_at=verified_at,
        )
        if not saved:
            return AssistantCapabilityResponse(
                success=False,
                stage="SAVE_VERIFICATION",
                code="CONFIGURATION_CHANGED",
                message="验证期间配置已变化，未保存验证结果，请针对当前配置重新验证。",
                output_mode=output_mode,
            )
        return AssistantCapabilityResponse(
            success=True,
            stage="COMPLETE",
            message="销售助手能力验证通过：根决策、完整会议流式结构化与质量评估均已通过校验。未写入 CRM。",
            output_mode=probe.output_mode,
            verified_at=verified_at,
        )

    async def _verify_root(self, snapshot: _ConfigSnapshot, mode: StructuredOutputMode, deadline: float) -> None:
        decision = await self.transport.ainvoke_structured(
            api_host=snapshot.api_host, api_key=snapshot.api_key, model=snapshot.model,
            temperature=0.0, system_prompt=ROOT_SYSTEM_PROMPT,
            user_prompt=json.dumps({
                "text": CAPABILITY_SAMPLE, "focused_task_public_id": None,
                "tasks": [], "recent_messages": [],
            }, ensure_ascii=False),
            response_model=ConversationDecision, error_prefix="销售助手根决策验证",
            timeout_seconds=min(150, max(0.001, deadline - monotonic())),
            stream=False, retry_timeouts=False, output_mode=mode,
        )
        decision = ConversationDecision.model_validate(decision)
        if (
            # Production routing (conversation._route) rejects decisions below this confidence.
            min(decision.confidence, decision.semantic_plan.confidence) < 0.8
            or decision.route != "WORKFLOW" or decision.boundary != "NEW"
            or decision.task_relation != "NEW_TASK"
            or decision.semantic_plan.speech_act != "ASSERT_EVENT"
            or decision.semantic_plan.business_object != "CUSTOMER_ACTIVITY"
            or decision.semantic_plan.operation != "CREATE"
        ):
            raise AssistantLLMError("根决策未通过样例校验", code=AssistantFailureCode.MODEL_OUTPUT_INVALID)

    async def _verify_meeting(
        self, snapshot: _ConfigSnapshot, mode: StructuredOutputMode, deadline: float,
    ) -> StructuredMeeting:
        result = await self.transport.ainvoke_structured(
            api_host=snapshot.api_host, api_key=snapshot.api_key, model=snapshot.model,
            temperature=0.0, system_prompt=STRUCTURE_MEETING_PROMPT, user_prompt=CAPABILITY_SAMPLE,
            response_model=StructuredMeeting, error_prefix="销售助手会议流式验证",
            timeout_seconds=min(120, max(0.001, deadline - monotonic())),
            stream=True, retry_timeouts=False, output_mode=mode,
        )
        result = StructuredMeeting.model_validate(result)
        try:
            _require_complete_content(result.content_json)
            validate_temporal_quotes(CAPABILITY_SAMPLE, result.temporal_mentions)
        except (AssistantLLMError, ValueError, TypeError) as exc:
            raise AssistantLLMError("会议结构或时间证据无效", code=AssistantFailureCode.MODEL_OUTPUT_INVALID) from exc
        mentions = {item.raw_text for item in result.temporal_mentions}
        if not {"11月", "下周三"}.issubset(mentions) or not result.content.strip():
            raise AssistantLLMError("会议缺少样例时间证据或正文", code=AssistantFailureCode.MODEL_OUTPUT_INVALID)
        return result

    async def _verify_quality(
        self, snapshot: _ConfigSnapshot, mode: StructuredOutputMode, deadline: float, meeting: StructuredMeeting,
    ) -> None:
        if meeting.content_json is None:
            raise AssistantLLMError("会议缺少完整正文", code=AssistantFailureCode.MODEL_OUTPUT_INVALID)
        result = await self.transport.ainvoke_structured(
            api_host=snapshot.api_host, api_key=snapshot.api_key, model=snapshot.model,
            temperature=0.0, system_prompt=quality_system_prompt("ONLINE_MEETING"),
            user_prompt=json.dumps({
                "activity_kind": "ONLINE_MEETING", "source_content": CAPABILITY_SAMPLE,
                "content_json": meeting.content_json.model_dump(mode="json"), "next_action": meeting.next_action,
            }, ensure_ascii=False),
            response_model=AssistantQualityResponse, error_prefix="销售助手质量流式验证",
            timeout_seconds=min(120, max(0.001, deadline - monotonic())),
            stream=True, retry_timeouts=False, output_mode=mode,
        )
        # Includes non-empty dimensions and duplicate-name rejection used by production quality scoring.
        AssistantQualityResponse.model_validate(result).to_activity_score()

    @staticmethod
    def _failure(
        stage: AssistantVerificationStage,
        code: AssistantFailureCode,
        mode: StructuredOutputMode | None = None,
    ) -> AssistantCapabilityResponse:
        # Only stable, pre-approved copy crosses the API boundary, never provider bodies.
        return AssistantCapabilityResponse(
            success=False, stage=stage, code=code.value,
            message=root_failure_presentation(code).message, output_mode=mode,
        )


assistant_model_capabilities = AssistantModelCapabilities()

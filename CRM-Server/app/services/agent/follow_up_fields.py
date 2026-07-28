"""Agent follow-up field collection and quality staging."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.models.agent import AgentTaskStatus
from app.schemas.agent import AgentTaskCreate, AgentTaskUpdate
from app.services.agent.quality import AgentFollowUpQualityEvaluatorError, agent_follow_up_quality_evaluator
from app.services.agent.schemas import AgentHITLPolicy, AgentMemorySnapshot, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParserError
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.field_common import _drop_empty_values, _parse_task_field_supplement
from app.services.agent.session_state import _remember_pending_task
from app.services.agent.task_factory import _new_task_key

def _is_follow_up_quality_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_follow_up_quality_fields"

def _is_lead_follow_up_quality_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_lead_follow_up_quality_fields"

def _merge_lead_follow_up_fields(existing_follow_up: dict, semantic_result: AgentSemanticParseResult) -> dict:
    next_follow_time_iso = agent_temporal_resolver.resolve_follow_up_time(semantic_result.lead.next_follow_time)
    return {
        **existing_follow_up,
        **_drop_empty_values({
            "content": semantic_result.lead.follow_up_content,
            "method": semantic_result.lead.follow_up_method,
            "next_action": semantic_result.lead.next_action,
            "next_follow_time_text": semantic_result.lead.next_follow_time_text,
            "next_follow_time_iso": next_follow_time_iso,
        }),
    }

def _merge_customer_follow_up_fields(existing_follow_up: dict, semantic_result: AgentSemanticParseResult) -> dict:
    customer = semantic_result.customer_create
    next_follow_time_iso = agent_temporal_resolver.resolve_follow_up_time(customer.next_follow_time)
    return {
        **existing_follow_up,
        **_drop_empty_values({
            "content": customer.follow_up_content,
            "method": customer.follow_up_method,
            "next_action": customer.next_action,
            "next_follow_time_text": customer.next_follow_time_text,
            "next_follow_time_iso": next_follow_time_iso,
        }),
    }

def _merge_follow_up_fields(existing_payload: dict, semantic_result: AgentSemanticParseResult, supplement: str) -> dict:
    follow_up = semantic_result.follow_up
    next_follow_time_iso = agent_temporal_resolver.resolve_follow_up_time(follow_up.next_follow_time)
    existing_content = str(existing_payload.get("content") or "").strip()
    supplement_content = (follow_up.content or supplement or "").strip()
    if existing_content and supplement_content and supplement_content not in existing_content:
        content = f"{existing_content}\n补充：{supplement_content}"
    else:
        content = existing_content or supplement_content
    return {
        **existing_payload,
        "content": content,
        **_drop_empty_values({
            "method": follow_up.method,
            "next_action": follow_up.next_action,
            "next_follow_time_text": follow_up.next_follow_time_text,
            "next_follow_time_iso": next_follow_time_iso,
        }),
    }

def _follow_up_content_for_create(payload: dict, quality: Any = None) -> str:
    revision = (getattr(quality, "suggested_revision", None) or "").strip() if quality else ""
    return revision or payload.get("content") or ""

def _lead_follow_up_semantic_result(follow_up: dict) -> AgentSemanticParseResult:
    return AgentSemanticParseResult.model_validate({
        "intent": "CREATE_LEAD",
        "intent_confidence": 0.95,
        "customer": {"name_text": None, "confidence": 0.0, "resolution_source": "NONE"},
        "follow_up": {
            "content": follow_up.get("content"),
            "method": follow_up.get("method") or "其他",
            "next_action": follow_up.get("next_action"),
            "next_follow_time_text": follow_up.get("next_follow_time_text"),
        },
        "lead": {
            "follow_up_content": follow_up.get("content"),
            "follow_up_method": follow_up.get("method") or "其他",
            "next_action": follow_up.get("next_action"),
            "next_follow_time_text": follow_up.get("next_follow_time_text"),
        },
        "business_signals": [],
        "requested_actions": [{"action": "CREATE_LEAD_FOLLOW_UP", "requires_confirmation": True}],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": [follow_up.get("content") or ""],
    })

async def _evaluate_lead_follow_up_quality(db: Session, task, follow_up: dict):
    return await agent_follow_up_quality_evaluator.evaluate_with_metadata(
        db,
        team_id=task.team_id,
        user_message=follow_up.get("content") or "",
        semantic_result=_lead_follow_up_semantic_result(follow_up),
        memory=AgentMemorySnapshot(
            pending_task={
                "id": task.id,
                "intent": task.intent,
                "target_type": task.target_type,
                "target_id": task.target_id,
                "summary": task.summary,
                "state": task.state_json or {},
            },
        ),
        current_date=agent_temporal_resolver.now().date(),
    )

def _lead_follow_up_create_payload(lead_id: int, follow_up: dict, quality: Any = None) -> dict:
    return {
        "lead_id": lead_id,
        "content": _follow_up_content_for_create(follow_up, quality),
        "method": follow_up.get("method") or "其他",
        "next_action": follow_up.get("next_action"),
        "next_follow_time": follow_up.get("next_follow_time_iso") or follow_up.get("next_follow_time"),
    }

def _customer_follow_up_semantic_result(customer: dict, follow_up: dict) -> AgentSemanticParseResult:
    return AgentSemanticParseResult.model_validate({
        "intent": "CUSTOMER_FOLLOW_UP",
        "intent_confidence": 0.95,
        "customer": {
            "name_text": customer.get("account_name"),
            "confidence": 1.0,
            "resolution_source": "EXPLICIT",
        },
        "follow_up": {
            "content": follow_up.get("content"),
            "method": follow_up.get("method") or "AI录入",
            "next_action": follow_up.get("next_action"),
            "next_follow_time_text": follow_up.get("next_follow_time_text"),
        },
        "business_signals": [],
        "requested_actions": [{"action": "CREATE_CUSTOMER_FOLLOW_UP", "requires_confirmation": True}],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": [follow_up.get("content") or ""],
    })

async def _evaluate_customer_follow_up_quality(db: Session, task, customer: dict, follow_up: dict):
    return await agent_follow_up_quality_evaluator.evaluate_with_metadata(
        db,
        team_id=task.team_id,
        user_message=follow_up.get("content") or "",
        semantic_result=_customer_follow_up_semantic_result(customer, follow_up),
        memory=AgentMemorySnapshot(
            pending_task={
                "id": task.id,
                "intent": task.intent,
                "target_type": task.target_type,
                "target_id": task.target_id,
                "summary": task.summary,
                "state": task.state_json or {},
            },
        ),
        current_date=agent_temporal_resolver.now().date(),
    )

def _customer_follow_up_create_payload(customer_id: int, follow_up: dict, quality: Any = None) -> dict:
    return {
        "customer_id": customer_id,
        "content": _follow_up_content_for_create(follow_up, quality),
        "method": follow_up.get("method") or "AI录入",
        "next_action": follow_up.get("next_action"),
        "next_follow_time_text": follow_up.get("next_follow_time_text"),
        "next_follow_time_iso": follow_up.get("next_follow_time_iso"),
    }

def _create_customer_follow_up_task(
    db: Session,
    session,
    *,
    team_id: int,
    user_id: int,
    customer: dict,
    follow_up: dict,
    action: str,
    summary: str,
    required_tools: list[str],
    confirmation_summary: str,
):
    customer_id = customer.get("id")
    payload = dict(follow_up)
    payload["customer_id"] = customer_id
    next_task = agent_task_crud.create(
        db,
        AgentTaskCreate(
            task_key=_new_task_key(),
            team_id=team_id,
            user_id=user_id,
            session_id=session.id,
            intent="CUSTOMER_FOLLOW_UP",
            status=AgentTaskStatus.WAITING_USER,
            target_type="customer",
            target_id=customer_id,
            summary=summary,
            input_json=payload,
            state_json={
                "action": action,
                "payload": payload,
                "customer": customer,
                "hitl": AgentHITLPolicy(
                    required_for_tools=required_tools,
                    confirmation_summary=confirmation_summary,
                ).model_dump(exclude_none=True),
            },
        ),
    )
    _remember_pending_task(db, session, next_task)
    return next_task

async def _stage_customer_follow_up_after_create(
    db: Session,
    session,
    task,
    *,
    team_id: int,
    user_id: int,
    customer: dict,
    follow_up: dict,
) -> str:
    try:
        envelope = await _evaluate_customer_follow_up_quality(db, task, customer, follow_up)
    except AgentFollowUpQualityEvaluatorError as exc:
        _create_customer_follow_up_task(
            db,
            session,
            team_id=team_id,
            user_id=user_id,
            customer=customer,
            follow_up={**follow_up, "quality_error": str(exc)},
            action="collect_follow_up_quality_fields",
            summary="等待补充客户跟进信息",
            required_tools=[],
            confirmation_summary="补充客户跟进信息",
        )
        return f"客户已创建，但我没有可靠评估客户跟进记录。请补充一下跟进信息。原因：{str(exc)}"

    quality = envelope.result
    follow_up = {**follow_up, "quality": quality.model_dump(exclude_none=True)}
    if not quality.passed:
        _create_customer_follow_up_task(
            db,
            session,
            team_id=team_id,
            user_id=user_id,
            customer=customer,
            follow_up=follow_up,
            action="collect_follow_up_quality_fields",
            summary="等待补充客户跟进信息",
            required_tools=[],
            confirmation_summary="补充客户跟进信息",
        )
        question = quality.supplement_question or "这条客户跟进还差一点关键信息，请继续补充。"
        return f"客户已创建。{question}"

    next_payload = _customer_follow_up_create_payload(customer["id"], follow_up, quality)
    _create_customer_follow_up_task(
        db,
        session,
        team_id=team_id,
        user_id=user_id,
        customer=customer,
        follow_up=next_payload,
        action="create_customer_follow_up",
        summary="等待确认执行：create_customer_follow_up",
        required_tools=["create_customer_follow_up"],
        confirmation_summary=f"为「{customer.get('account_name')}」创建跟进记录",
    )
    return "客户已创建。请确认是否同步创建客户跟进记录？"

def _create_lead_follow_up_task(
    db: Session,
    session,
    *,
    team_id: int,
    user_id: int,
    lead_id: int,
    follow_up: dict,
    action: str,
    summary: str,
    required_tools: list[str],
    confirmation_summary: str,
):
    payload = dict(follow_up)
    payload["lead_id"] = lead_id
    next_task = agent_task_crud.create(
        db,
        AgentTaskCreate(
            task_key=_new_task_key(),
            team_id=team_id,
            user_id=user_id,
            session_id=session.id,
            intent="CREATE_LEAD",
            status=AgentTaskStatus.WAITING_USER,
            target_type="lead",
            target_id=lead_id,
            summary=summary,
            input_json=payload,
            state_json={
                "action": action,
                "payload": payload,
                "hitl": AgentHITLPolicy(
                    required_for_tools=required_tools,
                    confirmation_summary=confirmation_summary,
                ).model_dump(exclude_none=True),
            },
        ),
    )
    _remember_pending_task(db, session, next_task)
    return next_task

async def _stage_lead_follow_up_after_create(
    db: Session,
    session,
    task,
    *,
    team_id: int,
    user_id: int,
    lead_id: int,
    follow_up: dict,
) -> str:
    try:
        envelope = await _evaluate_lead_follow_up_quality(db, task, follow_up)
    except AgentFollowUpQualityEvaluatorError as exc:
        _create_lead_follow_up_task(
            db,
            session,
            team_id=team_id,
            user_id=user_id,
            lead_id=lead_id,
            follow_up={**follow_up, "quality_error": str(exc)},
            action="collect_lead_follow_up_quality_fields",
            summary="等待补充线索跟进信息",
            required_tools=[],
            confirmation_summary="补充线索跟进信息",
        )
        return f"线索已创建，但我没有可靠评估线索跟进记录。请补充一下跟进信息。原因：{str(exc)}"

    quality = envelope.result
    follow_up = {**follow_up, "quality": quality.model_dump(exclude_none=True)}
    if not quality.passed:
        _create_lead_follow_up_task(
            db,
            session,
            team_id=team_id,
            user_id=user_id,
            lead_id=lead_id,
            follow_up=follow_up,
            action="collect_lead_follow_up_quality_fields",
            summary="等待补充线索跟进信息",
            required_tools=[],
            confirmation_summary="补充线索跟进信息",
        )
        question = quality.supplement_question or "这条线索跟进还差一点关键信息，请继续补充。"
        return f"线索已创建。{question}"

    next_payload = _lead_follow_up_create_payload(lead_id, follow_up, quality)
    _create_lead_follow_up_task(
        db,
        session,
        team_id=team_id,
        user_id=user_id,
        lead_id=lead_id,
        follow_up=next_payload,
        action="create_lead_follow_up",
        summary="等待确认执行：create_lead_follow_up",
        required_tools=["create_lead_follow_up"],
        confirmation_summary="创建线索跟进记录",
    )
    return "线索已创建。请确认是否同步创建线索跟进记录？"

async def _apply_follow_up_quality_fields(db: Session, task, content: str):
    state = deepcopy(task.state_json or {})
    customer = state.get("customer") or {}
    payload = deepcopy(state.get("payload") or {})
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的跟进信息，请换一种说法补充。原因：{str(exc)}"

    payload = _merge_follow_up_fields(payload, semantic_result, content)
    payload["customer_id"] = payload.get("customer_id") or customer.get("id")
    state = {**state, "payload": payload}
    try:
        envelope = await agent_follow_up_quality_evaluator.evaluate_with_metadata(
            db,
            team_id=task.team_id,
            user_message=payload.get("content") or content,
            semantic_result=semantic_result,
            memory=AgentMemorySnapshot(
                pending_task={
                    "id": task.id,
                    "intent": task.intent,
                    "target_type": task.target_type,
                    "target_id": task.target_id,
                    "summary": task.summary,
                    "state": state,
                },
            ),
            current_date=agent_temporal_resolver.now().date(),
        )
    except AgentFollowUpQualityEvaluatorError as exc:
        return False, f"我没有可靠评估这条跟进记录，请再补充一下。原因：{str(exc)}"

    quality = envelope.result
    payload["quality"] = quality.model_dump(exclude_none=True)
    state = {**state, "payload": payload}
    if not quality.passed:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, quality.supplement_question or "还差一点关键信息，请继续补充这条跟进记录。"

    next_payload = {
        "customer_id": payload.get("customer_id"),
        "content": _follow_up_content_for_create(payload, quality),
        "method": payload.get("method") or "AI录入",
        "next_action": payload.get("next_action"),
        "next_follow_time_text": payload.get("next_follow_time_text"),
        "next_follow_time_iso": payload.get("next_follow_time_iso"),
    }
    new_state = {
        "action": "create_customer_follow_up",
        "payload": next_payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_customer_follow_up"],
            confirmation_summary=f"为「{customer.get('account_name')}」创建跟进记录",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_customer_follow_up",
            input_json=next_payload,
            state_json=new_state,
        ),
    )
    return True, f"跟进内容已补齐。请确认是否为「{customer.get('account_name')}」创建这条跟进记录？"

async def _apply_lead_follow_up_quality_fields(db: Session, task, content: str):
    state = deepcopy(task.state_json or {})
    payload = deepcopy(state.get("payload") or {})
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的线索跟进信息，请换一种说法补充。原因：{str(exc)}"

    lead_id = payload.get("lead_id") or task.target_id
    follow_up = _merge_lead_follow_up_fields(payload, semantic_result)
    follow_up["lead_id"] = lead_id
    state = {**state, "payload": follow_up}

    try:
        envelope = await _evaluate_lead_follow_up_quality(db, task, follow_up)
    except AgentFollowUpQualityEvaluatorError as exc:
        return False, f"我没有可靠评估这条线索跟进记录，请再补充一下。原因：{str(exc)}"

    quality = envelope.result
    follow_up["quality"] = quality.model_dump(exclude_none=True)
    state = {**state, "payload": follow_up}
    if not quality.passed:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=follow_up, state_json=state))
        return False, quality.supplement_question or "这条线索跟进还差一点关键信息，请继续补充。"

    next_payload = _lead_follow_up_create_payload(lead_id, follow_up, quality)
    new_state = {
        "action": "create_lead_follow_up",
        "payload": next_payload,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_lead_follow_up"],
            confirmation_summary="创建线索跟进记录",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_lead_follow_up",
            input_json=next_payload,
            state_json=new_state,
        ),
    )
    return True, "线索跟进内容已补齐。请确认是否创建这条线索跟进记录？"

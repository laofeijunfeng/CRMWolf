from __future__ import annotations

import re
from uuid import uuid4

ACQUISITION_SOURCE_PUBLIC_ID_PATTERN = re.compile(r"^acq_[0-9a-f]{32}$")
OPPORTUNITY_PUBLIC_ID_PATTERN = re.compile(r"^opp_[0-9a-f]{32}$")
SALES_COMMITMENT_PUBLIC_ID_PATTERN = re.compile(r"^scm_[0-9a-f]{32}$")
FOLLOW_UP_TASK_PUBLIC_ID_PATTERN = re.compile(r"^fut_[0-9a-f]{32}$")
FOLLOW_UP_TASK_EVENT_PUBLIC_ID_PATTERN = re.compile(r"^fte_[0-9a-f]{32}$")
FOLLOW_UP_TASK_PROJECTION_RUN_PUBLIC_ID_PATTERN = re.compile(r"^tpr_[0-9a-f]{32}$")
FOLLOW_UP_TASK_CONFIRMATION_CASE_PUBLIC_ID_PATTERN = re.compile(r"^fuc_[0-9a-f]{32}$")
FOLLOW_UP_TASK_TRANSITION_POLICY_DECISION_PUBLIC_ID_PATTERN = re.compile(r"^tpd_[0-9a-f]{32}$")
FOLLOW_UP_TASK_RECONCILIATION_RUN_PUBLIC_ID_PATTERN = re.compile(r"^trr_[0-9a-f]{32}$")
FOLLOW_UP_TASK_LLM_MATCHER_RUN_PUBLIC_ID_PATTERN = re.compile(r"^tlm_[0-9a-f]{32}$")
FOLLOW_UP_TASK_RECONCILIATION_EVALUATION_RUN_PUBLIC_ID_PATTERN = re.compile(r"^ter_[0-9a-f]{32}$")


def generate_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"



def is_acquisition_source_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(ACQUISITION_SOURCE_PUBLIC_ID_PATTERN.fullmatch(value))

def is_opportunity_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(OPPORTUNITY_PUBLIC_ID_PATTERN.fullmatch(value))


def is_sales_commitment_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(SALES_COMMITMENT_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_event_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_EVENT_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_projection_run_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_PROJECTION_RUN_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_confirmation_case_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_CONFIRMATION_CASE_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_transition_policy_decision_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_TRANSITION_POLICY_DECISION_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_reconciliation_run_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_RECONCILIATION_RUN_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_llm_matcher_run_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_LLM_MATCHER_RUN_PUBLIC_ID_PATTERN.fullmatch(value))


def is_follow_up_task_reconciliation_evaluation_run_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(FOLLOW_UP_TASK_RECONCILIATION_EVALUATION_RUN_PUBLIC_ID_PATTERN.fullmatch(value))

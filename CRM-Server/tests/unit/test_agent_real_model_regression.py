"""Opt-in real-model regression scenarios for Agent semantic and routing behavior.

Run manually with:
CRMWOLF_AGENT_REAL_MODEL_REGRESSION=1 OPENAI_API_KEY=... pytest tests/unit/test_agent_real_model_regression.py -q --no-cov
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from app.services.agent.langchain_runtime import AgentLangChainRuntime
from app.services.agent.prompts import (
    build_semantic_messages,
    build_turn_relation_messages,
)
from app.services.agent.schemas import AgentMemorySnapshot, AgentSemanticParseResult, AgentTurnRelationDecision


pytestmark = pytest.mark.skipif(
    os.getenv("CRMWOLF_AGENT_REAL_MODEL_REGRESSION") != "1",
    reason="real-model Agent regression is opt-in",
)


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_HOST = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "")
RUN_DATE = date(2026, 7, 29)


SEMANTIC_SCENARIOS = [
    ("今天微信跟进了东风康明斯，张总说本月底让采购拉会", "CUSTOMER_ACTIVITY", "东风康明斯"),
    ("中移动信息那边已经到账 30 万，备注首款", "PAYMENT_RECORD", "中移动信息"),
    ("给汇川技术建一个 200 人订阅 1 年的新购商机，预计 9 月底成交", "CREATE_OPPORTUNITY", "汇川技术"),
    ("新增线索：深圳云图，联系人李雷 13800138000，展会来的", "CREATE_LEAD", None),
    ("给越秀金融添加联系人王敏，财务负责人，手机号 13900139000", "CREATE_CONTACT", "越秀金融"),
    ("给凡亚信息录入开票抬头：凡亚信息技术有限公司，税号 9144xx", "CREATE_INVOICE_TITLE", "凡亚信息"),
    ("给蓝海科技新增部署信息，生产环境，服务器 10.0.0.8，授权 50 人", "CREATE_DEPLOYMENT_INFO", "蓝海科技"),
    ("把陈工加到东风康明斯的售前协作成员，可跟进", "CREATE_CUSTOMER_MEMBER", "东风康明斯"),
    ("查一下广州睿狐最近有哪些商机和合同", "CUSTOMER_QUERY", "广州睿狐"),
    ("今天拜访了海信，客户担心安全审计，下周三我带售前再沟通", "CUSTOMER_ACTIVITY", "海信"),
    ("中铁建今天说预算批了，先买断 100 人，预计 10 月 15 号走完采购", "CUSTOMER_ACTIVITY", "中铁建"),
    ("创建客户：杭州启明科技，杭州，制造业，联系人赵总 13700137000", "CREATE_CUSTOMER", None),
    ("南方电网回款了，但是金额财务还没给我", "PAYMENT_RECORD", "南方电网"),
    ("给白云机场申请试用 license，他们已有部署环境", "CUSTOMER_ACTIVITY", "白云机场"),
]


TURN_RELATION_SCENARIOS = [
    (
        "预计 9 月底成交，采购方式公开招标",
        [{"id": 201, "summary": "东风康明斯商机草稿", "customer_name": "东风康明斯", "action": "collect_opportunity_fields", "missing_fields": ["expected_closing_date", "procurement_method"]}],
        "RESUME_SUSPENDED_DRAFT",
        201,
    ),
    (
        "汇川技术那边改成增购 20 个，还是订阅一年",
        [{"id": 201, "summary": "东风康明斯商机草稿", "customer_name": "东风康明斯", "action": "collect_opportunity_fields", "missing_fields": ["purchase_type"]}],
        "START_NEW_FLOW",
        None,
    ),
    (
        "改成增购 20 个",
        [
            {"id": 201, "summary": "东风康明斯商机草稿", "customer_name": "东风康明斯", "action": "collect_opportunity_fields", "missing_fields": ["purchase_type"]},
            {"id": 202, "summary": "中移动信息商机草稿", "customer_name": "中移动信息", "action": "collect_opportunity_fields", "missing_fields": ["purchase_type"]},
        ],
        "ASK_USER",
        None,
    ),
    (
        "中移动信息改成增购 20 个",
        [
            {"id": 201, "summary": "东风康明斯商机草稿", "customer_name": "东风康明斯", "action": "collect_opportunity_fields", "missing_fields": ["purchase_type"]},
            {"id": 202, "summary": "中移动信息商机草稿", "customer_name": "中移动信息", "action": "collect_opportunity_fields", "missing_fields": ["purchase_type"]},
        ],
        "RESUME_SUSPENDED_DRAFT",
        202,
    ),
    (
        "好嘞",
        [{"id": 201, "summary": "东风康明斯商机草稿", "customer_name": "东风康明斯", "action": "collect_opportunity_fields"}],
        "CHITCHAT",
        None,
    ),
    (
        "先查一下这个客户最近合同",
        [{"id": 201, "summary": "东风康明斯商机草稿", "customer_name": "东风康明斯", "action": "collect_opportunity_fields"}],
        "START_NEW_FLOW",
        None,
    ),
]


def _runtime() -> AgentLangChainRuntime:
    if not API_KEY:
        pytest.skip("OPENAI_API_KEY is required for real-model Agent regression")
    return AgentLangChainRuntime()


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected_intent,expected_customer", SEMANTIC_SCENARIOS)
async def test_real_model_semantic_business_scenarios(message, expected_intent, expected_customer):
    messages = build_semantic_messages(
        message,
        AgentMemorySnapshot().model_dump_json(exclude_none=True),
        current_date=RUN_DATE,
    )
    result = await _runtime().ainvoke_structured(
        api_host=API_HOST,
        api_key=API_KEY,
        model=MODEL,
        temperature=0.0,
        system_prompt=messages[0]["content"],
        user_prompt=messages[1]["content"],
        response_model=AgentSemanticParseResult,
        error_prefix="real model semantic regression",
    )

    assert result is not None
    assert result.intent == expected_intent
    if expected_customer:
        assert expected_customer in (result.customer.name_text or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("message,suspended_tasks,expected_relation,expected_target_task_id", TURN_RELATION_SCENARIOS)
async def test_real_model_turn_relation_scenarios(
    message,
    suspended_tasks,
    expected_relation,
    expected_target_task_id,
):
    messages = build_turn_relation_messages(
        message,
        "null",
        json.dumps(suspended_tasks, ensure_ascii=False),
        AgentMemorySnapshot().model_dump_json(exclude_none=True),
        current_date=RUN_DATE,
    )
    result = await _runtime().ainvoke_structured(
        api_host=API_HOST,
        api_key=API_KEY,
        model=MODEL,
        temperature=0.0,
        system_prompt=messages[0]["content"],
        user_prompt=messages[1]["content"],
        response_model=AgentTurnRelationDecision,
        error_prefix="real model turn relation regression",
    )

    assert result is not None
    assert result.relation == expected_relation
    assert result.target_task_id == expected_target_task_id

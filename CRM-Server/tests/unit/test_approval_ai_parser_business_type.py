"""Task B3: AI 审批流解析器支持 business_type 识别（回款/发票/合同）。

测试三层：
1. system prompt 含 business_type 识别指引 + JSON 模板字段
2. parser 从 AI 返回 JSON 中提取 business_type 字段并落入 ApprovalAIParsedFlow
3. 缺失/非法 business_type 时回退默认 CONTRACT（防 AI 漏字段）
"""
import json
from unittest.mock import MagicMock

import pytest

from app.constants.business_types import BusinessType
from app.crud import ai_config
from app.schemas.approval_ai import ApprovalAIParsedFlow, ApprovalAIParsedNode
from app.services import approval_ai_parser as parser_module
from app.services.approval_ai_parser import (
    PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE,
    approval_ai_parser_service,
)


# -------------------- 辅助：构造 fake httpx 流式响应 --------------------

def _sse_chunk(content: str) -> str:
    """构造 OpenAI 风格 SSE 数据行（单 chunk 包含全部 content）。"""
    payload = {"choices": [{"delta": {"content": content}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\ndata: [DONE]\n\n"


class _FakeResponse:
    def __init__(self, stream_text: str):
        self._stream_text = stream_text
        self.status_code = 200
        self.text = ""

    def raise_for_status(self):
        return None

    async def aiter_text(self):
        yield self._stream_text


class _StreamCM:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, stream_text: str):
        self._stream_text = stream_text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, *args, **kwargs):
        return _StreamCM(_FakeResponse(self._stream_text))


def _build_flow_json(business_type):
    """构造 AI 返回的完整 flow JSON（含 business_type 字段）。"""
    flow = {
        "flow_name": "测试流程",
        "flow_code": "TEST",
        "description": "测试",
        "min_amount": None,
        "max_amount": None,
        "license_type": None,
        "business_type": business_type,
        "nodes": [
            {
                "node_name": "财务审批",
                "node_code": "FINANCE_CHECK",
                "node_order": 1,
                "approve_role": "FINANCE",
                "description": "财务审核",
                "is_required": 1,
            }
        ],
    }
    return json.dumps(
        {"flow": flow, "thinking_process": "测试思考"},
        ensure_ascii=False,
    )


def _patch_httpx(monkeypatch, content_json: str):
    """patch httpx.AsyncClient 返回固定 content 的流式响应。"""
    stream_text = _sse_chunk(content_json)
    monkeypatch.setattr(
        parser_module.httpx, "AsyncClient", lambda *a, **k: _FakeClient(stream_text)
    )


def _patch_ai_config(monkeypatch):
    monkeypatch.setattr(
        ai_config.ai_config_crud,
        "get_config",
        lambda db, tid: MagicMock(api_host="http://x", model_name="m"),
    )
    monkeypatch.setattr(
        ai_config.ai_config_crud, "get_decrypted_api_key", lambda db, tid: "key"
    )


async def _collect_business_type(monkeypatch, content_json: str) -> str:
    """跑流式解析，返回 parsed 事件里 flow.business_type。"""
    _patch_ai_config(monkeypatch)
    _patch_httpx(monkeypatch, content_json)

    events = []
    async for ev in approval_ai_parser_service.parse_approval_flow_stream(
        db=None, user_message="dummy", team_id=1
    ):
        events.append(ev)

    parsed_ev = next((e for e in events if e.get("event") == "parsed"), None)
    assert parsed_ev is not None, f"未产生 parsed 事件，events={events}"
    return parsed_ev["flow"]["business_type"]


# -------------------- 测试 1: system prompt 含 business_type 指引 --------------------

def test_prompt_contains_business_type_guidance():
    """system prompt 必须含单据类型识别规则 + JSON 模板中的 business_type 字段。"""
    prompt = PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date="2026-07-02")

    # 识别规则关键词
    assert "business_type" in prompt
    assert "PAYMENT" in prompt
    assert "INVOICE" in prompt
    assert "CONTRACT" in prompt
    # 自然语言触发词指引（回款 / 发票 / 合同）
    assert "回款" in prompt or "收款" in prompt
    assert "发票" in prompt
    # JSON 输出模板里得有 business_type 字段
    assert '"business_type"' in prompt


# -------------------- 测试 2: 解析回款 → PAYMENT --------------------

async def test_parse_payment_business_type(monkeypatch):
    """用户说"金额超 5 万的回款需财务审批" → flow.business_type == PAYMENT。"""
    content = _build_flow_json(BusinessType.PAYMENT)
    business_type = await _collect_business_type(monkeypatch, content)
    assert business_type == BusinessType.PAYMENT


# -------------------- 测试 3: 解析发票 → INVOICE --------------------

async def test_parse_invoice_business_type(monkeypatch):
    """用户说"发票审批 10 万以上总监审" → flow.business_type == INVOICE。"""
    content = _build_flow_json(BusinessType.INVOICE)
    business_type = await _collect_business_type(monkeypatch, content)
    assert business_type == BusinessType.INVOICE


# -------------------- 测试 4: 解析合同 → CONTRACT（明确）--------------------

async def test_parse_contract_business_type(monkeypatch):
    """用户说"合同 50 万销售总监审" → flow.business_type == CONTRACT。"""
    content = _build_flow_json(BusinessType.CONTRACT)
    business_type = await _collect_business_type(monkeypatch, content)
    assert business_type == BusinessType.CONTRACT


# -------------------- 测试 5: 缺失 business_type → 默认 CONTRACT --------------------

async def test_parse_default_contract_when_missing(monkeypatch):
    """AI 漏输出 business_type 时回退默认 CONTRACT（防字段缺失）。"""
    flow_json = json.dumps(
        {
            "flow": {
                "flow_name": "测试",
                "flow_code": "TEST",
                "description": None,
                "min_amount": None,
                "max_amount": None,
                "license_type": None,
                # 故意不写 business_type
                "nodes": [
                    {
                        "node_name": "财务审批",
                        "node_code": "FINANCE_CHECK",
                        "node_order": 1,
                        "approve_role": "FINANCE",
                        "description": "",
                        "is_required": 1,
                    }
                ],
            },
            "thinking_process": "测试",
        },
        ensure_ascii=False,
    )
    business_type = await _collect_business_type(monkeypatch, flow_json)
    assert business_type == BusinessType.CONTRACT


# -------------------- 测试 6: schema 字段默认值 CONTRACT --------------------

def test_parsed_flow_business_type_default():
    """ApprovalAIParsedFlow 不传 business_type 时默认 CONTRACT。"""
    flow = ApprovalAIParsedFlow(
        flow_name="测试",
        flow_code="TEST",
        nodes=[
            ApprovalAIParsedNode(
                node_name="节点",
                node_code="N1",
                node_order=1,
                approve_role="SALES_DIRECTOR",
            )
        ],
    )
    assert flow.business_type == BusinessType.CONTRACT
    # to_sse_dict 必须带 business_type
    sse = flow.to_sse_dict()
    assert "business_type" in sse
    assert sse["business_type"] == BusinessType.CONTRACT
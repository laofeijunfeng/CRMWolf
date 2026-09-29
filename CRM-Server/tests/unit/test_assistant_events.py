"""SSE event layer contracts: encoding, reporter ordering, error payload."""

import asyncio

import pytest

from app.services.assistant.events import (
    AssistantDomainError,
    DomainErrorCode,
    NullProgressReporter,
    SSEProgressReporter,
    encode_sse,
    stage,
)


def test_encode_sse_frame_shape():
    frame = encode_sse("accepted", {"turn_id": "t_1"})
    assert frame.startswith("event: accepted\ndata: ")
    assert frame.endswith("\n\n")
    assert '"turn_id": "t_1"' in frame or '"turn_id":"t_1"' in frame


def test_encode_sse_keeps_chinese_unescaped():
    frame = encode_sse("error", {"message": "AI 服务暂时不可用"})
    assert "AI 服务暂时不可用" in frame


def test_stage_rejects_unknown_name():
    with pytest.raises(ValueError):
        stage("explode")


def test_reporter_preserves_order_and_payloads():
    reporter = SSEProgressReporter()
    s = stage("classify")
    reporter.stage_start(s)
    reporter.stage_done(s, ms=8120)
    reporter.stage("structure") if False else None
    st = stage("structure")
    reporter.stage_start(st)
    reporter.stage_done(st, ms=2100)
    reporter.stage_done(stage("quality_gate"), ms=500, score=81)

    items = reporter.drain()
    assert [item[1]["stage"] for item in items] == ["classify", "classify", "structure", "structure", "quality_gate"]
    done_gate = items[-1][1]
    assert done_gate["score"] == 81
    assert done_gate["ms"] == 500


def test_mark_done_unblocks_and_keeps_finished():
    reporter = SSEProgressReporter()
    reporter.mark_done()
    assert reporter.drain() == []
    assert reporter.finished


def test_null_reporter_never_raises():
    null = NullProgressReporter()
    null.stage_start(stage("write"))
    null.stage_done(stage("write"), ms=1, score=99)


def test_domain_error_event_payload():
    exc = AssistantDomainError(
        DomainErrorCode.AI_UNAVAILABLE, "AI 服务暂时不可用", retryable=True
    )
    data = exc.as_event_data()
    assert data == {
        "code": "AI_UNAVAILABLE",
        "retryable": True,
        "message": "AI 服务暂时不可用",
    }


@pytest.mark.asyncio
async def test_queue_is_loop_safe():
    reporter = SSEProgressReporter()
    reporter.stage_start(stage("classify"))
    await asyncio.sleep(0)
    items = reporter.drain()
    assert len(items) == 1

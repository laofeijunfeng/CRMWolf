"""A transcript over 20k characters is organized segment by segment and merged (CRM-167)."""

import pytest
from pydantic import ValidationError

from app.models.assistant import AssistantTask
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.events import SSEProgressReporter
from app.services.assistant.failure_contract import AssistantStageFailure
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.llm_contracts import ModelDraftAction, StructureDraftResult
from app.services.assistant.segmented_structure import SEGMENT_SIZE, merge_structured, split_transcript
from tests.unit.test_assistant_stage_events import Chooser, PassGate, Structurer, _task, db_session  # noqa: F401

# ruff: noqa: RUF001


def _transcript(chars: int) -> str:
    lines = []
    index = 0
    while sum(len(line) for line in lines) < chars:
        index += 1
        lines.append(f"第{index}句：广州睿狐科技有限公司确认 POC 可行，预算在走审批，我们下周三确认批复。\n")
    # Accepted input is stripped before it becomes a source record.
    return "".join(lines).rstrip()


class SegmentStructurer(Structurer):
    """Reports each chunk it saw; fails once on the configured call."""

    def __init__(self, fail_on: int | None = None) -> None:
        self.chunks: list[str] = []
        self.fail_on = fail_on

    async def structure(self, db, *, team_id, kind, user_text):
        self.chunks.append(user_text)
        if len(self.chunks) == self.fail_on:
            self.fail_on = None
            raise AssistantLLMError("模型服务响应超时")
        head = user_text.split("：", 1)[0]
        return StructureDraftResult(
            kind_confirmed=kind,
            content=f"{head}要点",
            customer_name="广州睿狐科技有限公司" if len(self.chunks) == 1 else "",
            next_action=f"{head}后确认批复",
        )


def test_split_covers_the_text_exactly_on_line_boundaries():
    text = _transcript(60_000)
    chunks = split_transcript(text)

    assert "".join(chunk for _, chunk in chunks) == text
    assert all(text[offset : offset + len(chunk)] == chunk for offset, chunk in chunks)
    assert all(len(chunk) <= SEGMENT_SIZE for _, chunk in chunks)
    assert all(chunk.endswith("\n") for _, chunk in chunks[:-1])
    assert split_transcript(text[:20_000]) == [(0, text[:20_000])]


def test_split_cuts_hard_when_a_window_has_no_boundary():
    text = "呢" * 20_001
    chunks = split_transcript(text)

    assert "".join(chunk for _, chunk in chunks) == text
    assert [len(chunk) for _, chunk in chunks] == [6000, 6000, 6000, 2001]


def test_merge_moves_quotes_to_full_text_and_keeps_action_refs_unique():
    text = _transcript(30_000)
    chunks = split_transcript(text)
    parts = []
    for offset, chunk in chunks:
        quote = chunk[:6]
        parts.append((offset, StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content=quote,
            next_action="确认批复" if offset == 0 else "",
            actions=[ModelDraftAction(
                action_ref="a1", owner_role="SALES", action_text="确认批复", action_status="PLANNED",
                evidence_quote=quote, quote_start=0, quote_end=len(quote),
            )],
        )))

    merged = merge_structured("FOLLOW_UP", parts)

    assert [text[a.quote_start : a.quote_end] for a in merged.actions] == [a.evidence_quote for a in merged.actions]
    assert len({a.action_ref for a in merged.actions}) == len(chunks)
    assert merged.content == "\n".join(chunk[:6] for _, chunk in chunks)
    # An empty later next step does not erase the one stated earlier.
    assert merged.next_action == "确认批复"


async def test_long_transcript_is_organized_in_segments_with_real_progress(db_session):  # noqa: F811
    text = _transcript(60_000)
    total = len(split_transcript(text))
    structurer = SegmentStructurer()
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=structurer, quality_gate=PassGate())
    task = _task(db_session)

    task = (await coordinator.handle_task(
        db_session, task, AssistantInput(kind="text", text=text), reporter=reporter
    )).task

    assert "".join(structurer.chunks) == text
    content = task.draft_json["content"]["value"]
    assert all(f"第{chunk.split('：', 1)[0][1:]}" in content for chunk in structurer.chunks)
    assert task.draft_json["next_action"]["value"] == structurer.chunks[-1].split("：", 1)[0] + "后确认批复"
    segments = [
        (data["phase"], data["segment"]["index"], data["segment"]["total"])
        for _, data in reporter.drain()
        if data.get("stage") == "structure"
    ]
    assert segments == [(phase, i, total) for i in range(1, total + 1) for phase in ("start", "done")]


async def test_failed_segment_resumes_without_reorganizing_saved_ones(db_session):  # noqa: F811
    text = _transcript(60_000)
    total = len(split_transcript(text))
    structurer = SegmentStructurer(fail_on=3)
    coordinator = AssistantCoordinator(Chooser(), structurer=structurer, quality_gate=PassGate())
    task = _task(db_session)

    reporter = SSEProgressReporter()
    with pytest.raises(AssistantStageFailure):
        await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text=text), reporter=reporter)
    assert ("failed", 3) in [
        (data["phase"], data["segment"]["index"]) for _, data in reporter.drain() if data.get("stage") == "structure"
    ]
    db_session.rollback()
    task = db_session.get(AssistantTask, task.id)

    task = (await coordinator.handle_task(db_session, task, AssistantInput(kind="text", text=text))).task

    # Two saved segments, one failed call, then the remaining total - 2 segments.
    assert len(structurer.chunks) == 3 + total - 2
    assert "".join(structurer.chunks[3:]) == text[len("".join(structurer.chunks[:2])) :]
    assert task.draft_json["content"]["status"] != "MISSING"


async def test_input_within_one_call_is_organized_once(db_session):  # noqa: F811
    structurer = SegmentStructurer()
    reporter = SSEProgressReporter()
    coordinator = AssistantCoordinator(Chooser(), structurer=structurer, quality_gate=PassGate())
    text = _transcript(19_000)

    await coordinator.handle_task(
        db_session, _task(db_session), AssistantInput(kind="text", text=text), reporter=reporter
    )

    assert structurer.chunks == [text]
    assert all("segment" not in data for _, data in reporter.drain())


def test_input_over_100k_is_refused():
    AssistantInput(kind="text", text="呢" * 100_000)
    with pytest.raises(ValidationError):
        AssistantInput(kind="text", text="呢" * 100_001)

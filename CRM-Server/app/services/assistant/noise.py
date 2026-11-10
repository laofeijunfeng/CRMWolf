"""Server boundary for model-labelled input noise.

The classify model labels speaker timestamps and mentioned-only channels. This
module never recognises noise itself: it keeps a label only when its quote is
located in the source segment and it cannot hide a business time or the quoted
channel evidence. Verified labels may only remove questions; source text and
offsets are never changed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.assistant.contracts import VerifiedNoiseSpan
from app.services.assistant.temporal_evidence import TemporalContractError, find_time_spans, locate_quote

if TYPE_CHECKING:
    from app.services.assistant.contracts import TaskDraft
    from app.services.assistant.llm_contracts import KindDecision


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < right and left < end for left, right in spans)


def _touches(text: str, start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """Overlapping, or separated from a span only by whitespace (今天下午 13:45)."""

    return any(not text[min(end, right) : max(start, left)].strip() for left, right in spans)


def _occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    index = text.find(quote) if quote else -1
    while index >= 0:
        found.append((index, index + len(quote)))
        index = text.find(quote, index + 1)
    return found


def verify_noise(segment_id: str, text: str, decision: KindDecision) -> list[VerifiedNoiseSpan]:
    """Keep only labels that are located verbatim and cannot hide business evidence."""

    business = [(span.start, span.end) for span in find_time_spans(text)]
    evidence = _occurrences(text, decision.evidence_quote.strip())
    verified: list[VerifiedNoiseSpan] = []
    seen: set[tuple[str, int, int]] = set()
    for label in decision.noise_spans:
        try:
            start, end = locate_quote(
                text, label.quote_start, label.quote_end, label.raw_text, None, TemporalContractError, "noise"
            )
        except TemporalContractError:
            continue
        if label.kind == "SPEAKER_TIMESTAMP" and _touches(text, start, end, business):
            continue
        if label.kind == "CHANNEL_MENTION" and _overlaps(start, end, evidence):
            continue
        if (label.kind, start, end) in seen:
            continue
        seen.add((label.kind, start, end))
        verified.append(
            VerifiedNoiseSpan(segment_id=segment_id, kind=label.kind, start=start, end=end, raw_text=label.raw_text)
        )
    return verified


def record_noise(draft: TaskDraft, user_text: str, decision: KindDecision) -> str:
    """Store verified labels for this input's segment; return the text channel rules should read.

    Mentioned-only channel words become same-length spaces so keyword checks
    ignore them. Without a matching source segment no label is kept.
    """

    text = user_text.strip()
    record = next((item for item in reversed(draft.source_records) if item.text == text), None)
    if record is None:
        return user_text
    spans = verify_noise(record.segment_id, text, decision)
    draft.input_noise = [item for item in draft.input_noise if item.segment_id != record.segment_id] + spans
    masked = list(text)
    for span in spans:
        if span.kind == "CHANNEL_MENTION":
            masked[span.start : span.end] = " " * (span.end - span.start)
    return "".join(masked)


def ignored_noise_summary(draft: TaskDraft) -> str | None:
    """Card copy for every verified label; empty categories are hidden."""

    timestamps = sum(1 for item in draft.input_noise if item.kind == "SPEAKER_TIMESTAMP")
    channels = sum(1 for item in draft.input_noise if item.kind == "CHANNEL_MENTION")
    parts = [
        f"{count} 处{label}"
        for count, label in ((timestamps, "发言时间"), (channels, "渠道提及"))
        if count
    ]
    return f"已忽略 {'、'.join(parts)}" if parts else None

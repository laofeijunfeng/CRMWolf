"""Server-side binding of an LLM-authorized pending confirmation Case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.agent.orchestrator.risk import extract_case_public_id

if TYPE_CHECKING:
    from app.services.agent.orchestrator.contracts import PendingCaseContext


def is_explicit_pending_case_reference(text: str) -> bool:
    """Return whether text contains a structurally valid Case public ID.

    This helper intentionally does not inspect verbs such as "完成" or nouns
    such as "待办". Whether the turn concerns a pending Case belongs to the
    Root LLM decision.
    """

    return extract_case_public_id(text) is not None


@dataclass(frozen=True)
class PendingCaseMatch:
    status: str
    case: PendingCaseContext | None = None
    candidates: tuple[PendingCaseContext, ...] = ()
    reference: str | None = None


def match_pending_case(
    text: str,
    cases: list[PendingCaseContext],
    *,
    semantic_reference_authorized: bool = False,
) -> PendingCaseMatch:
    """Bind an LLM-authorized reference to owned server-side candidates.

    The Root classifier authorizes the semantic relationship. This function
    only performs identifier validation and candidate/entity binding; it never
    decides from natural-language action keywords whether the user meant a
    pending Case.
    """

    case_id = extract_case_public_id(text)
    if case_id is not None:
        exact = tuple(case for case in cases if case.case_public_id.lower() == case_id)
        if len(exact) == 1:
            return PendingCaseMatch(status="MATCHED", case=exact[0], reference=case_id)
        return PendingCaseMatch(
            status="AMBIGUOUS" if len(exact) > 1 else "NOT_FOUND",
            reference=case_id,
        )

    if not semantic_reference_authorized:
        return PendingCaseMatch(status="NONE")
    if not cases:
        return PendingCaseMatch(status="NOT_FOUND", reference=text.strip()[:255])

    # The Root model has already authorized that this turn concerns a pending
    # Case. Do not let a substring score silently bind one of several cases:
    # phrases such as a customer alias or a generic task title are not an
    # authoritative identity. Keep the complete owned candidate set so the
    # semantic selector can compare the user's whole utterance and context.
    # A single candidate remains safe to reuse and avoids an unnecessary
    # confirmation round.
    if len(cases) == 1:
        return PendingCaseMatch(status="MATCHED", case=cases[0], reference=text.strip()[:255])
    return PendingCaseMatch(
        status="AMBIGUOUS",
        candidates=tuple(cases),
        reference=text.strip()[:255],
    )

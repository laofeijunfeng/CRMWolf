"""Removed customer-fact proposal types never reach CRM commands."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.assistant.crm_proposal_commands import validate_candidate
from app.services.assistant.proposals import _candidate_hints

REMOVED_FACT_TYPES = (
    "need",
    "budget",
    "risk",
    "stage",
    "stakeholder_attitude",
    "competitor",
    "next_step",
    "preference",
    "summary",
)


class _Query:
    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return SimpleNamespace(
            id=11,
            team_id=2,
            customer_id=101,
            source_content="客户预算为十万元",
            status="ACTIVE",
        )


class _DB:
    def query(self, _model):
        return _Query()


def test_removed_fact_types_do_not_validate() -> None:
    task = SimpleNamespace(
        team_id=2,
        user_id=9,
        committed_json=[{"kind": "customer_activity", "public_id": "11"}],
        authority_json={},
    )
    for fact_type in REMOVED_FACT_TYPES:
        candidate = {
            "kind": "customer_fact",
            "evidence_quote": "客户预算为十万元",
            "payload": {"fact_type": fact_type, "content": "客户预算为十万元"},
        }
        assert validate_candidate(_DB(), task, candidate) is None


def test_removed_fact_hints_are_not_generated() -> None:
    activity = SimpleNamespace(
        content_json='{"customer_facts":[{"fact_type":"budget","content":"预算","evidence_quote":"预算"}]}'
    )
    task = SimpleNamespace(
        team_id=2,
        user_id=9,
        committed_json=[{"kind": "customer_activity", "public_id": "11"}],
        authority_json={},
    )

    class _HintDB:
        def query(self, _model):
            class _ActivityQuery:
                def filter(self, *_args, **_kwargs):
                    return self

                def one_or_none(self):
                    return activity

            return _ActivityQuery()

    assert _candidate_hints(_HintDB(), task) == []

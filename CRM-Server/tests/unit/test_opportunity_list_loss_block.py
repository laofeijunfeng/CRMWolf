"""Loss blocking is summary data: it must not leak into contract eligibility.

`contract_unavailable_reason` drives the new-contract picker, so reusing it for
loss blocking would silently hide WON opportunities from contract creation.
"""

from app.models.opportunity import OpportunityStatus


def test_won_opportunity_with_contract_reports_loss_block_reason():
    from app.api import opportunities
    from app.constants.opportunity_loss import CONTRACT_LOSS_BLOCK_REASON

    assert opportunities._loss_unavailable_reason(
        OpportunityStatus.WON.value, 7, {7},
    ) == CONTRACT_LOSS_BLOCK_REASON


def test_won_opportunity_without_contract_can_be_lost():
    from app.api import opportunities

    assert opportunities._loss_unavailable_reason(OpportunityStatus.WON.value, 7, set()) is None


def test_following_opportunity_is_never_loss_blocked_by_a_contract():
    from app.api import opportunities

    assert opportunities._loss_unavailable_reason(OpportunityStatus.FOLLOWING.value, 7, {7}) is None

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from app.models.contract import Contract, ContractStatus, PaymentStatus
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.invoice import (
    InvoiceApplication,
    InvoiceApplicationStatus,
    InvoiceRedOffset,
    InvoiceReissueApplication,
    InvoiceReissueApplicationStatus,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.orm import Session


_PROGRESS_MILESTONE_PERCENT = 25
_ACTIVE_REISSUE_STATUSES = frozenset(
    {
        InvoiceReissueApplicationStatus.DRAFT,
        InvoiceReissueApplicationStatus.PENDING_REVIEW,
        InvoiceReissueApplicationStatus.APPROVED,
    }
)


def invoice_application_is_currently_valid(
    application: InvoiceApplication,
    reissues: Sequence[InvoiceReissueApplication],
    red_offsets: Sequence[InvoiceRedOffset],
) -> bool:
    """Return whether one invoice application currently represents a valid invoice."""
    if any(reissue.status in _ACTIVE_REISSUE_STATUSES for reissue in reissues):
        return False
    if any(
        reissue.status == InvoiceReissueApplicationStatus.COMPLETED
        and bool(reissue.new_invoice_file_path)
        for reissue in reissues
    ):
        return True
    if red_offsets:
        return False
    return application.status == InvoiceApplicationStatus.ISSUED


def calculate_cumulative_progress_percent(
    *,
    journey_status: str,
    primary_opportunity_won: bool,
    contracts: Sequence[Contract],
    invoice_applications: Sequence[InvoiceApplication],
    invoice_validity: Sequence[bool] | None = None,
) -> int:
    if journey_status == DealJourneyStatus.COMPLETED:
        return 100

    signed = bool(contracts) and all(
        contract.status in {ContractStatus.SIGNED, ContractStatus.EFFECTIVE}
        for contract in contracts
    )
    paid = bool(contracts) and all(
        contract.payment_status == PaymentStatus.COMPLETED
        for contract in contracts
    )
    if invoice_validity is None:
        invoices_valid = bool(invoice_applications) and all(
            application.status == InvoiceApplicationStatus.ISSUED
            for application in invoice_applications
        )
    else:
        invoices_valid = (
            bool(invoice_applications)
            and len(invoice_validity) == len(invoice_applications)
            and all(invoice_validity)
        )
    return _PROGRESS_MILESTONE_PERCENT * sum(
        (primary_opportunity_won, signed, paid, invoices_valid)
    )


def load_cumulative_progress_percentages(
    db: Session,
    team_id: int,
    journeys: Sequence[CustomerDealJourney],
    *,
    opportunity_won_by_journey: Mapping[int, bool],
) -> dict[int, int]:
    """Batch-load current facts and calculate cumulative progress per journey.

    ``opportunity_won_by_journey`` is supplied by callers that already selected
    the primary opportunity.  The journey model does not expose a reliable
    ``primary_opportunity`` relationship, so progress must not lazy-load one.
    """
    if not journeys:
        return {}

    journey_ids = [int(journey.id) for journey in journeys]
    contracts_by_journey: dict[int, list[Contract]] = defaultdict(list)
    for contract in (
        db.query(Contract)
        .filter(
            Contract.team_id == team_id,
            Contract.deleted_at.is_(None),
            Contract.deal_journey_id.in_(journey_ids),
        )
        .all()
    ):
        if contract.deal_journey_id is not None:
            contracts_by_journey[int(contract.deal_journey_id)].append(contract)

    applications_by_journey: dict[int, list[InvoiceApplication]] = defaultdict(list)
    applications = (
        db.query(InvoiceApplication)
        .filter(
            InvoiceApplication.team_id == team_id,
            InvoiceApplication.deal_journey_id.in_(journey_ids),
        )
        .all()
    )
    application_ids = [int(application.id) for application in applications]
    for application in applications:
        if application.deal_journey_id is not None:
            applications_by_journey[int(application.deal_journey_id)].append(application)

    reissues_by_application: dict[int, list[InvoiceReissueApplication]] = defaultdict(list)
    red_offsets_by_application: dict[int, list[InvoiceRedOffset]] = defaultdict(list)
    if application_ids:
        for reissue in (
            db.query(InvoiceReissueApplication)
            .filter(
                InvoiceReissueApplication.team_id == team_id,
                InvoiceReissueApplication.original_invoice_application_id.in_(application_ids),
            )
            .all()
        ):
            reissues_by_application[int(reissue.original_invoice_application_id)].append(reissue)
    if application_ids:
        for red_offset in (
            db.query(InvoiceRedOffset)
            .filter(
                InvoiceRedOffset.team_id == team_id,
                InvoiceRedOffset.invoice_application_id.in_(application_ids),
            )
            .all()
        ):
            red_offsets_by_application[int(red_offset.invoice_application_id)].append(red_offset)

    progress: dict[int, int] = {}
    for journey in journeys:
        journey_id = int(journey.id)
        applications_for_journey = applications_by_journey.get(journey_id, [])
        invoice_validity = [
            invoice_application_is_currently_valid(
                application,
                reissues_by_application.get(int(application.id), []),
                red_offsets_by_application.get(int(application.id), []),
            )
            for application in applications_for_journey
        ]
        opportunity_won = opportunity_won_by_journey.get(journey_id, False)
        progress[journey_id] = calculate_cumulative_progress_percent(
            journey_status=journey.status,
            primary_opportunity_won=opportunity_won,
            contracts=contracts_by_journey.get(journey_id, []),
            invoice_applications=applications_for_journey,
            invoice_validity=invoice_validity,
        )
    return progress


__all__ = [
    "calculate_cumulative_progress_percent",
    "invoice_application_is_currently_valid",
    "load_cumulative_progress_percentages",
]

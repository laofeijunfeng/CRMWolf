"""Transport-neutral triggers for the customer intelligence graph.

This module converts already-structured Agent runtime events and committed CRM
write results into the customer intelligence event contract. It deliberately
does not parse raw user text with keywords; semantic parsing and business
execution happen upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.crud.customer import contact_crud
from app.crud.customer_activity import customer_activity_crud
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneySourceType,
)
from app.models.opportunity import Opportunity
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceEventService,
    customer_intelligence_event_service,
)
from app.utils.public_id import is_opportunity_public_id

from .types import JSONDict, coerce_json_dict


@dataclass(frozen=True)
class AgentCustomerIntelligenceTurn:
    team_id: int
    user_id: int
    session_id: int
    message_id: int
    content: str


class CustomerIntelligenceTriggerPolicy:
    """Build customer intelligence events from stable Agent/business signals."""

    def __init__(
        self,
        *,
        event_service: CustomerIntelligenceEventService | None = None,
    ) -> None:
        self.event_service = event_service or customer_intelligence_event_service

    def from_new_flow_events(
        self,
        events: list[JSONDict],
        *,
        turn: AgentCustomerIntelligenceTurn,
    ) -> CustomerIntelligenceEvent | None:
        intent = _first_intent(events)
        if intent != "CUSTOMER_QUERY":
            return None
        customer_id = _latest_customer_id(events)
        if customer_id is None:
            return None
        return self.event_service.agent_customer_question(
            team_id=turn.team_id,
            customer_id=customer_id,
            actor_id=str(turn.user_id),
            session_id=turn.session_id,
            message_id=turn.message_id,
            question=turn.content,
        )

    def from_confirmed_tool_result(
        self,
        db: Session | None,
        tool_result: JSONDict,
        *,
        team_id: int,
    ) -> CustomerIntelligenceEvent | None:
        if db is None or not tool_result.get("success"):
            return None
        event = self._activity_event_from_tool_result(db, tool_result, team_id=team_id)
        if event is not None:
            return event
        event = self._contact_event_from_tool_result(db, tool_result, team_id=team_id)
        if event is not None:
            return event
        return self._deal_journey_event_from_tool_result(db, tool_result, team_id=team_id)

    def _activity_event_from_tool_result(
        self,
        db: Session,
        tool_result: JSONDict,
        *,
        team_id: int,
    ) -> CustomerIntelligenceEvent | None:
        if tool_result.get("tool_name") != "create_customer_activity":
            return None
        data = coerce_json_dict(tool_result.get("data"))
        activity_id = _positive_int(data.get("id"))
        if activity_id is None:
            return None
        activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
        if activity is None:
            return None
        return self.event_service.from_customer_activity(activity)

    def _contact_event_from_tool_result(
        self,
        db: Session,
        tool_result: JSONDict,
        *,
        team_id: int,
    ) -> CustomerIntelligenceEvent | None:
        if tool_result.get("tool_name") != "create_contact":
            return None
        data = coerce_json_dict(tool_result.get("data"))
        contact_id = _positive_int(data.get("id"))
        if contact_id is None:
            return None
        contact = contact_crud.get_by_id(db, contact_id, team_id)
        if contact is None:
            return None
        return self.event_service.from_contact(contact)

    def _deal_journey_event_from_tool_result(
        self,
        db: Session,
        tool_result: JSONDict,
        *,
        team_id: int,
    ) -> CustomerIntelligenceEvent | None:
        selector = _deal_journey_event_selector(db, team_id=team_id, tool_result=tool_result)
        if selector is None:
            return None
        event = _find_deal_journey_event(db, team_id=team_id, selector=selector)
        if event is None:
            return None
        return self.event_service.from_deal_journey_event(event)


@dataclass(frozen=True)
class DealJourneyEventSelector:
    source_type: str
    source_id: int | None = None
    opportunity_id: int | None = None
    event_type: str | None = None


def _deal_journey_event_selector(db: Session, *, team_id: int, tool_result: JSONDict) -> DealJourneyEventSelector | None:
    tool_name = tool_result.get("tool_name")
    data = coerce_json_dict(tool_result.get("data"))
    if tool_name == "create_opportunity":
        opportunity_id = _resolve_opportunity_db_id(db, team_id=team_id, value=data.get("id"))
        if opportunity_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.OPPORTUNITY,
            source_id=opportunity_id,
            event_type=DealJourneyEventType.OPPORTUNITY_CREATED,
        )
    if tool_name in {"create_contract", "create_contract_from_opportunity"}:
        contract_id = _positive_int(data.get("id"))
        if contract_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.CONTRACT,
            source_id=contract_id,
            event_type=DealJourneyEventType.CONTRACT_CREATED,
        )
    if tool_name == "move_opportunity_stage":
        opportunity_id = _resolve_opportunity_db_id(db, team_id=team_id, value=data.get("id"))
        if opportunity_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.OPPORTUNITY_STAGE_SNAPSHOT,
            opportunity_id=opportunity_id,
            event_type=DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
        )
    if tool_name == "create_payment_plan":
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return None
        first_item = coerce_json_dict(items[0])
        plan_id = _positive_int(first_item.get("id"))
        if plan_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.PAYMENT_PLAN,
            source_id=plan_id,
            event_type=DealJourneyEventType.PAYMENT_PLAN_CREATED,
        )
    if tool_name == "create_payment_record":
        record_id = _positive_int(data.get("id"))
        if record_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.PAYMENT_RECORD,
            source_id=record_id,
            event_type=DealJourneyEventType.PAYMENT_RECEIVED,
        )
    if tool_name == "create_invoice_application":
        application_id = _positive_int(data.get("id"))
        if application_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.INVOICE_APPLICATION,
            source_id=application_id,
            event_type=DealJourneyEventType.INVOICE_APPLIED,
        )
    if tool_name == "issue_invoice":
        application_id = _positive_int(data.get("id"))
        if application_id is None:
            return None
        return DealJourneyEventSelector(
            source_type=DealJourneySourceType.INVOICE_APPLICATION,
            source_id=application_id,
            event_type=DealJourneyEventType.INVOICE_ISSUED,
        )
    return None


def _find_deal_journey_event(
    db: Session,
    *,
    team_id: int,
    selector: DealJourneyEventSelector,
) -> CustomerDealJourneyEvent | None:
    query = db.query(CustomerDealJourneyEvent).filter(
        CustomerDealJourneyEvent.team_id == team_id,
        CustomerDealJourneyEvent.source_type == selector.source_type,
    )
    if selector.source_id is not None:
        query = query.filter(CustomerDealJourneyEvent.source_id == selector.source_id)
    if selector.event_type is not None:
        query = query.filter(CustomerDealJourneyEvent.event_type == selector.event_type)
    if selector.opportunity_id is not None:
        query = query.join(
            CustomerDealJourney,
            CustomerDealJourney.id == CustomerDealJourneyEvent.deal_journey_id,
        ).filter(CustomerDealJourney.primary_opportunity_id == selector.opportunity_id)
    return query.order_by(CustomerDealJourneyEvent.event_time.desc(), CustomerDealJourneyEvent.id.desc()).first()


def _resolve_opportunity_db_id(db: Session, *, team_id: int, value: object) -> int | None:
    opportunity_id = _positive_int(value)
    if opportunity_id is not None:
        return opportunity_id
    if not is_opportunity_public_id(value):
        return None
    opportunity = (
        db.query(Opportunity.id)
        .filter(Opportunity.public_id == value, Opportunity.team_id == team_id)
        .first()
    )
    return int(opportunity.id) if opportunity is not None else None


def _first_intent(events: list[JSONDict]) -> str | None:
    for event in events:
        if event.get("event") == "intent":
            intent = event.get("intent")
            if isinstance(intent, str) and intent:
                return intent
    return None


def _latest_customer_id(events: list[JSONDict]) -> int | None:
    for event in reversed(events):
        if event.get("event") != "business_context_loaded":
            continue
        customer_id = _positive_int(event.get("customer_id"))
        if customer_id is not None:
            return customer_id
        customer = coerce_json_dict(event.get("customer"))
        customer_id = _positive_int(customer.get("id"))
        if customer_id is not None:
            return customer_id
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


customer_intelligence_trigger_policy = CustomerIntelligenceTriggerPolicy()

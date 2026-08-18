"""Convert semantic parse results into CRM agent payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.services.acquisition_source_service import resolve_write_fields_for_ai
from app.services.agent import business_rules
from app.services.agent.schemas import AgentSemanticParseResult


def parsed_from_semantic(
    semantic_result: AgentSemanticParseResult,
    original_content: str,
    *,
    temporal_resolver: object,
    base_datetime: Optional[datetime] = None,
    db: Optional[Session] = None,
    team_id: Optional[int] = None,
) -> Dict[str, object]:
    contact = dict(semantic_result.contact or {})
    invoice_title = dict(semantic_result.invoice_title or {})
    deployment_info = dict(semantic_result.deployment_info or {})
    customer_member = dict(semantic_result.customer_member or {})
    payment = semantic_result.payment
    opportunity = semantic_result.opportunity
    lead = semantic_result.lead
    customer_create = semantic_result.customer_create
    follow_up_task_transition = semantic_result.follow_up_task_transition

    next_follow_time_iso = _resolve_follow_up_time_with_text_fallback(
        temporal_resolver,
        semantic_result.follow_up.next_follow_time,
        semantic_result.follow_up.next_follow_time_text,
        base_datetime=base_datetime,
    )
    payment_date_iso = (
        temporal_resolver.resolve_date(payment.payment_date, base_datetime=base_datetime)
        if hasattr(temporal_resolver, "resolve_date")
        else None
    )
    lead_next_follow_time_iso = _resolve_follow_up_time_with_text_fallback(
        temporal_resolver,
        lead.next_follow_time,
        lead.next_follow_time_text,
        base_datetime=base_datetime,
    )
    customer_next_follow_time_iso = _resolve_follow_up_time_with_text_fallback(
        temporal_resolver,
        customer_create.next_follow_time,
        customer_create.next_follow_time_text,
        base_datetime=base_datetime,
    )
    expected_closing_date_iso = (
        temporal_resolver.resolve_date(opportunity.expected_closing_date, base_datetime=base_datetime)
        if hasattr(temporal_resolver, "resolve_date")
        else None
    )
    follow_up_task_transition_due_at_iso = _resolve_follow_up_time_with_text_fallback(
        temporal_resolver,
        follow_up_task_transition.proposed_due_at,
        follow_up_task_transition.proposed_due_at_text,
        base_datetime=base_datetime,
    )
    computed_missing_opportunity_fields = business_rules.missing_opportunity_fields({
        "procurement_method_id": opportunity.procurement_method_id,
        "total_amount": opportunity.total_amount,
        "user_count": opportunity.user_count,
        "license_type": opportunity.license_type,
        "subscription_years": opportunity.subscription_years,
        "purchase_type": opportunity.purchase_type,
        "expected_closing_date": expected_closing_date_iso,
    })

    return {
        "customer_name": semantic_result.customer.name_text or semantic_result.read_query.customer_name_text,
        "original_content": original_content,
        "follow_up_content": semantic_result.follow_up.content or original_content,
        "method": semantic_result.follow_up.method or "AI录入",
        "payment": {
            "actual_amount": payment.actual_amount,
            "actual_payer_name": payment.actual_payer_name,
            "payment_date_text": payment.payment_date_text,
            "payment_date_iso": payment_date_iso,
            "notes": payment.notes,
        },
        "lead": resolve_write_fields_for_ai(
            business_rules.drop_empty_values({
                "lead_name": lead.lead_name,
                "source": lead.source,
                "city": lead.city,
                "contact_name": lead.contact_name,
                "contact_phone": lead.contact_phone,
                "company_scale": lead.company_scale,
            }),
            db,
            team_id,
        ),
        "lead_follow_up": business_rules.drop_empty_values({
            "content": lead.follow_up_content,
            "method": lead.follow_up_method or "其他",
            "next_action": lead.next_action,
            "next_follow_time_text": lead.next_follow_time_text,
            "next_follow_time_iso": lead_next_follow_time_iso,
        }),
        "customer_create": resolve_write_fields_for_ai(
            business_rules.drop_empty_values({
                "account_name": customer_create.account_name,
                "source": customer_create.source,
                "city": customer_create.city,
                "industry": customer_create.industry,
                "company_scale": customer_create.company_scale,
                "contact_name": customer_create.contact_name,
                "contact_phone": customer_create.contact_phone,
                "contact_position": customer_create.contact_position,
                "contact_gender": customer_create.contact_gender,
                "contact_email": customer_create.contact_email,
            }),
            db,
            team_id,
        ),
        "customer_activity": business_rules.drop_empty_values({
            "content": customer_create.follow_up_content,
            "source_content": original_content if customer_create.follow_up_content else None,
            "method": customer_create.follow_up_method or "AI录入",
            "next_action": customer_create.next_action,
            "next_follow_time_text": customer_create.next_follow_time_text,
            "next_follow_time_iso": customer_next_follow_time_iso,
        }),
        "missing_customer_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "CREATE_CUSTOMER" and semantic_result.missing_fields
            else business_rules.missing_customer_fields({
                "account_name": customer_create.account_name,
                "city": customer_create.city,
                "contact_name": customer_create.contact_name,
                "contact_phone": customer_create.contact_phone,
                "contact_position": customer_create.contact_position,
                "contact_gender": customer_create.contact_gender,
            })
            if semantic_result.intent == "CREATE_CUSTOMER"
            else []
        ),
        "missing_lead_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "CREATE_LEAD" and semantic_result.missing_fields
            else business_rules.missing_lead_fields({
                "lead_name": lead.lead_name,
                "city": lead.city,
                "contact_name": lead.contact_name,
                "contact_phone": lead.contact_phone,
            })
            if semantic_result.intent == "CREATE_LEAD"
            else []
        ),
        "opportunity": {
            "procurement_method_id": opportunity.procurement_method_id,
            "total_amount": opportunity.total_amount,
            "user_count": opportunity.user_count,
            "license_type": opportunity.license_type,
            "subscription_years": opportunity.subscription_years,
            "purchase_type": opportunity.purchase_type,
            "decision_maker_count": opportunity.decision_maker_count,
            "expected_closing_date_text": opportunity.expected_closing_date_text,
            "expected_closing_date": expected_closing_date_iso,
        },
        "missing_opportunity_fields": computed_missing_opportunity_fields
        if semantic_result.intent == "CREATE_OPPORTUNITY"
        else [],
        "missing_payment_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "PAYMENT_RECORD" and semantic_result.missing_fields
            else business_rules.missing_payment_fields(payment.actual_amount, payment_date_iso)
            if semantic_result.intent == "PAYMENT_RECORD"
            else []
        ),
        "contact": business_rules.drop_empty_values(contact),
        "missing_contact_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "CREATE_CONTACT" and semantic_result.missing_fields
            else business_rules.missing_contact_fields(contact)
            if semantic_result.intent == "CREATE_CONTACT"
            else []
        ),
        "invoice_title": business_rules.drop_empty_values(invoice_title),
        "missing_invoice_title_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "CREATE_INVOICE_TITLE" and semantic_result.missing_fields
            else business_rules.missing_invoice_title_fields(invoice_title)
            if semantic_result.intent == "CREATE_INVOICE_TITLE"
            else []
        ),
        "deployment_info": business_rules.drop_empty_values(deployment_info),
        "missing_deployment_info_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "CREATE_DEPLOYMENT_INFO" and semantic_result.missing_fields
            else business_rules.missing_deployment_info_fields(deployment_info)
            if semantic_result.intent == "CREATE_DEPLOYMENT_INFO"
            else []
        ),
        "customer_member": business_rules.drop_empty_values(customer_member),
        "missing_customer_member_fields": (
            semantic_result.missing_fields
            if semantic_result.intent == "CREATE_CUSTOMER_MEMBER" and semantic_result.missing_fields
            else business_rules.missing_customer_member_fields(customer_member)
            if semantic_result.intent == "CREATE_CUSTOMER_MEMBER"
            else []
        ),
        "follow_up_task_transition": business_rules.drop_empty_values({
            "action": follow_up_task_transition.action,
            "task_id": follow_up_task_transition.task_id,
            "task_reference_text": follow_up_task_transition.task_reference_text,
            "proposed_due_at_text": follow_up_task_transition.proposed_due_at_text,
            "proposed_due_at_iso": follow_up_task_transition_due_at_iso,
            "reason": follow_up_task_transition.reason,
        }),
        "next_action": semantic_result.follow_up.next_action,
        "next_follow_time_text": semantic_result.follow_up.next_follow_time_text,
        "next_follow_time_iso": next_follow_time_iso,
    }


def _resolve_follow_up_time_with_text_fallback(
    temporal_resolver: object,
    expression: object,
    raw_text: Optional[str],
    *,
    base_datetime: Optional[datetime],
) -> Optional[str]:
    resolved = temporal_resolver.resolve_follow_up_time(
        expression,
        base_datetime=base_datetime,
    )
    if resolved:
        return resolved
    if not raw_text or not hasattr(temporal_resolver, "resolve_follow_up_time_text"):
        return None
    return temporal_resolver.resolve_follow_up_time_text(
        raw_text,
        base_datetime=base_datetime,
    )

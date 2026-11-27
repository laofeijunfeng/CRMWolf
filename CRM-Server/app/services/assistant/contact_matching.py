"""Deterministic matching and incremental delta calculation for existing customer contacts (CRM-176)."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.assistant.entity_forms.contact import _TITLE_ONLY, MOBILE, normalize_phone
from app.utils.dedupe_normalizer import mobile_dedupe_key

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.models.customer import Contact
    from app.services.assistant.contracts import EntityQuote

MatchStatus = Literal["MATCHED", "NO_MATCH", "AMBIGUOUS_NAME", "MOBILE_CONFLICT"]


@dataclass(frozen=True)
class ContactSignals:
    """Normalized contact attributes extracted from user text or proposal quotes."""

    name: str | None = None
    mobiles: tuple[str, ...] = ()
    email: str | None = None
    wechat_id: str | None = None
    wechat_same_as_mobile: bool = False
    wechat_phrase: str | None = None
    reports_to_name: str | None = None
    remarks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContactMatchResult:
    """Deterministic match outcome against a customer's existing contacts."""

    status: MatchStatus
    contact: Contact | None = None
    candidates: tuple[Contact, ...] = ()
    matched_by: Literal["mobile", "name"] | None = None
    conflict_mobile: str | None = None


@dataclass(frozen=True)
class ContactDelta:
    """Controlled incremental supplement delta for an existing contact."""

    remark_append: str | None = None
    wechat_id: str | None = None
    wechat_phrase: str | None = None
    email: str | None = None
    reports_to_id: int | None = None
    reports_to_name: str | None = None

    @property
    def has_delta(self) -> bool:
        return any(
            value is not None
            for value in (self.remark_append, self.wechat_id, self.email, self.reports_to_id)
        )

    def summary_parts(self) -> list[str]:
        parts: list[str] = []
        if self.remark_append is not None:
            parts.append("新备注")
        if self.email is not None:
            parts.append("邮箱")
        if self.wechat_id is not None:
            parts.append("微信")
        if self.reports_to_id is not None:
            parts.append("汇报对象")
        return parts


def mask_mobile(mobile: str | None) -> str:
    """Return a masked mobile number such as ``138****5678`` for safe UI display."""

    raw = (mobile or "").strip()
    if not raw:
        return ""
    digits = normalize_phone(raw)
    if len(digits) == 11 and digits.isdigit():
        return f"{digits[:3]}****{digits[-4:]}"
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-2:]}"
    return raw


def is_honorific_name(name: str | None) -> bool:
    """Return True for blank names or title-only abbreviations like ``孙总`` / ``王工``."""

    cleaned = (name or "").strip()
    if not cleaned:
        return True
    return bool(_TITLE_ONLY.match(cleaned))


def list_customer_contacts(db: Session, *, team_id: int, customer_id: int) -> list[Contact]:
    """Load all contacts under one customer without the form dropdown row cap."""

    from app.models.customer import Contact

    return (
        db.query(Contact)
        .filter(Contact.team_id == team_id, Contact.customer_id == customer_id)
        .order_by(Contact.id)
        .all()
    )


def extract_contact_signals(extracted: Sequence[EntityQuote]) -> ContactSignals:
    """Extract normalized matching and supplement signals from verified quotes."""

    name: str | None = None
    mobiles: list[str] = []
    landlines: list[str] = []
    email: str | None = None
    wechat_id: str | None = None
    wechat_same = False
    wechat_phrase: str | None = None
    reports_to_name: str | None = None
    remarks: list[str] = []

    for item in extracted:
        val = item.value.strip()
        if not val:
            continue
        if item.key == "name" and name is None:
            name = val
        elif item.key == "mobile":
            digits = normalize_phone(val)
            if MOBILE.match(digits):
                if digits not in mobiles:
                    mobiles.append(digits)
            elif not (len(digits) == 10 and digits.startswith("1")):
                if val not in landlines:
                    landlines.append(val)
        elif item.key == "email" and email is None:
            email = val
        elif item.key == "wechat_id":
            if "同号" in val:
                wechat_same = True
                wechat_phrase = item.quote[:200]
            elif wechat_id is None:
                wechat_id = val
        elif item.key == "reports_to" and reports_to_name is None:
            reports_to_name = val
        elif item.key in {"remark", "remark_append"}:
            remarks.append(val)

    if landlines:
        remarks.append("座机：" + "、".join(landlines))

    return ContactSignals(
        name=name,
        mobiles=tuple(mobiles),
        email=email,
        wechat_id=wechat_id,
        wechat_same_as_mobile=wechat_same,
        wechat_phrase=wechat_phrase,
        reports_to_name=reports_to_name,
        remarks=tuple(remarks),
    )


def match_existing_contact(
    contacts: Sequence[Contact],
    signals: ContactSignals,
) -> ContactMatchResult:
    """Match extracted contact signals deterministically against existing contacts.

    Priority 1: exact ``mobile_dedupe_key`` match.
    Priority 2: exact ``name.strip()`` match (refuses honorifics/abbreviations such as ``孙总``).
    """

    by_mobile: dict[str, Contact] = {}
    for contact in contacts:
        key = contact.mobile_dedupe_key or mobile_dedupe_key(contact.mobile)
        if key and key not in by_mobile:
            by_mobile[key] = contact

    for candidate_mobile in signals.mobiles:
        key = mobile_dedupe_key(candidate_mobile)
        if key and key in by_mobile:
            matched = by_mobile[key]
            return ContactMatchResult(
                status="MATCHED",
                contact=matched,
                candidates=(matched,),
                matched_by="mobile",
            )

    if signals.name and not is_honorific_name(signals.name):
        cleaned = signals.name.strip()
        name_matches = [c for c in contacts if (c.name or "").strip() == cleaned]
        if len(name_matches) > 1:
            return ContactMatchResult(
                status="AMBIGUOUS_NAME",
                candidates=tuple(name_matches),
            )
        if len(name_matches) == 1:
            target = name_matches[0]
            target_key = target.mobile_dedupe_key or mobile_dedupe_key(target.mobile)
            if signals.mobiles and target_key:
                signal_keys = {mobile_dedupe_key(m) for m in signals.mobiles}
                if target_key not in signal_keys:
                    return ContactMatchResult(
                        status="MOBILE_CONFLICT",
                        contact=target,
                        candidates=(target,),
                        matched_by="name",
                        conflict_mobile=signals.mobiles[0],
                    )
            return ContactMatchResult(
                status="MATCHED",
                contact=target,
                candidates=(target,),
                matched_by="name",
            )

    return ContactMatchResult(status="NO_MATCH")


def _filter_new_remark_lines(existing: str | None, addition: str | None) -> list[str]:
    existing_clean = (existing or "").strip()
    addition_clean = (addition or "").strip()
    if not addition_clean:
        return []
    new_lines: list[str] = []
    for raw_line in addition_clean.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if existing_clean and line in existing_clean:
            continue
        if line in new_lines:
            continue
        new_lines.append(line)
    return new_lines


def merge_contact_remark(existing: str | None, addition: str | None) -> tuple[str | None, bool]:
    """Append non-duplicate lines to ``existing`` with a newline separator.

    Returns ``(merged_text, changed)``.
    """

    existing_clean = (existing or "").strip()
    new_lines = _filter_new_remark_lines(existing_clean, addition)
    if not new_lines:
        return (existing_clean or None, False)
    chunk = "\n".join(new_lines)
    if existing_clean:
        return (f"{existing_clean}\n{chunk}", True)
    return (chunk, True)


def compute_contact_delta(
    contact: Contact,
    signals: ContactSignals,
    *,
    contacts: Sequence[Contact],
    extra_remark: str | None = None,
) -> ContactDelta:
    """Compute incremental-only supplement fields for ``contact``.

    Never proposes overwriting non-empty optional fields; deduplicates remark lines against
    ``contact.remark``.
    """

    raw_remark_parts = list(signals.remarks)
    if extra_remark and extra_remark.strip():
        raw_remark_parts.append(extra_remark.strip())
    combined_addition = "\n".join(raw_remark_parts) if raw_remark_parts else None
    new_remark_lines = _filter_new_remark_lines(contact.remark, combined_addition)
    remark_append = "\n".join(new_remark_lines) if new_remark_lines else None

    wechat_id: str | None = None
    wechat_phrase: str | None = None
    if not (contact.wechat_id or "").strip():
        if signals.wechat_id:
            wechat_id = signals.wechat_id
        elif signals.wechat_same_as_mobile:
            fallback_mobile = (contact.mobile or "").strip() or (signals.mobiles[0] if signals.mobiles else "")
            if fallback_mobile:
                wechat_id = fallback_mobile
                wechat_phrase = signals.wechat_phrase

    email: str | None = None
    if not (contact.email or "").strip() and signals.email:
        email = signals.email

    reports_to_id: int | None = None
    reports_to_name: str | None = None
    if contact.reports_to is None and signals.reports_to_name:
        target_name = signals.reports_to_name.strip()
        matches = [
            c for c in contacts
            if c.id != contact.id and (c.name or "").strip() == target_name
        ]
        if len(matches) == 1:
            reports_to_id = matches[0].id
            reports_to_name = matches[0].name

    return ContactDelta(
        remark_append=remark_append,
        wechat_id=wechat_id,
        wechat_phrase=wechat_phrase,
        email=email,
        reports_to_id=reports_to_id,
        reports_to_name=reports_to_name,
    )

"""Controlled incremental supplement form for an existing customer contact (CRM-176)."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.assistant.contact_matching import (
    compute_contact_delta,
    extract_contact_signals,
    list_customer_contacts,
    merge_contact_remark,
)
from app.services.assistant.entity_forms import (
    Canonical,
    EntityFormError,
    FieldSpec,
    FormContext,
    Submitted,
    WriteResult,
    refresh_after_commit,
    value,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.models.customer import Contact
    from app.services.assistant.contracts import EntityFieldValue, EntityQuote

_MAX_REPORTS_TO_OPTIONS = 50

EXISTING_REMARK = FieldSpec("existing_remark", "已有备注", "textarea", max_length=10_000, read_only=True)
REMARK_APPEND = FieldSpec(
    "remark_append",
    "追加备注",
    "textarea",
    max_length=500,
    placeholder="将换行追加到原备注末尾，不覆盖已有内容",
)
WECHAT = FieldSpec("wechat_id", "微信", max_length=50)
EMAIL = FieldSpec("email", "邮箱", max_length=100)
REPORTS_TO = FieldSpec("reports_to", "汇报对象", "select")


def _load_target(ctx: FormContext) -> Contact | None:
    from app.models.customer import Contact

    if ctx.customer is None or ctx.draft.target_contact_id is None:
        return None
    return (
        ctx.db.query(Contact)
        .filter(
            Contact.id == ctx.draft.target_contact_id,
            Contact.team_id == ctx.team_id,
            Contact.customer_id == ctx.customer.id,
        )
        .first()
    )


class ContactSupplementForm:
    KIND = "contact_supplement"
    LABEL = "联系人资料"
    TARGET_PREFIX = "contact"
    EXTRACT_KEYS: Mapping[str, str] = {
        "name": "联系人姓名，原样保留",
        "mobile": "原文中提到的手机号（如与库内不同仅用于识别，不会覆盖已有手机号）",
        "email": "要补充的邮箱",
        "wechat_id": "要补充的微信号；若原文说“微信同号”则 value 填“同号”，quote 填“微信同号”",
        "reports_to": "要补充的上级姓名",
        "remark": "要追加到备注的新内容",
    }
    FIELD_KEYS = frozenset({"existing_remark", "remark_append", "wechat_id", "email", "reports_to"})

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]:
        target = _load_target(ctx)
        if target is None or ctx.customer is None:
            return {}
        ctx.draft.target_contact_revision = int(getattr(target, "post_commit_revision", None) or 1)
        ctx.draft.target_contact_name = target.name
        ctx.draft.target_contact_mobile = target.mobile
        ctx.draft.target_existing_remark = target.remark

        contacts = list_customer_contacts(ctx.db, team_id=ctx.team_id, customer_id=ctx.customer.id)
        signals = extract_contact_signals(extracted)
        extra_remark = f"新提手机号：{ctx.draft.conflict_mobile}" if ctx.draft.conflict_mobile else None
        delta = compute_contact_delta(target, signals, contacts=contacts, extra_remark=extra_remark)

        out: dict[str, EntityFieldValue] = {}
        if delta.remark_append is not None:
            out["remark_append"] = value("ORIGINAL", delta.remark_append[:2000])
        if delta.wechat_id is not None:
            if delta.wechat_phrase:
                out["wechat_id"] = value("DERIVED", delta.wechat_id[:2000], phrase=delta.wechat_phrase)
            else:
                out["wechat_id"] = value("ORIGINAL", delta.wechat_id[:2000])
        if delta.email is not None:
            out["email"] = value("ORIGINAL", delta.email[:2000])
        if delta.reports_to_id is not None:
            out["reports_to"] = value("ORIGINAL", str(delta.reports_to_id))
        return out

    def fields(
        self,
        ctx: FormContext,
        values: Mapping[str, EntityFieldValue],
        submitted: Submitted | None,
        errors: Mapping[str, str],
    ) -> list[dict[str, object]]:
        target = _load_target(ctx)
        existing_remark = (
            target.remark
            if target is not None
            else ctx.draft.target_existing_remark
        )
        rendered: list[dict[str, object]] = []
        if existing_remark and existing_remark.strip():
            rendered.append(
                EXISTING_REMARK.render(
                    {"existing_remark": value("ORIGINAL", existing_remark.strip()[:10_000])},
                    None,
                    {},
                )
            )
        rendered.append(REMARK_APPEND.render(values, submitted, errors))

        if target is None or not (target.wechat_id or "").strip() or "wechat_id" in errors:
            rendered.append(WECHAT.render(values, submitted, errors))
        if target is None or not (target.email or "").strip() or "email" in errors:
            rendered.append(EMAIL.render(values, submitted, errors))

        if (target is None or target.reports_to is None or "reports_to" in errors) and ctx.customer is not None:
            contacts = list_customer_contacts(ctx.db, team_id=ctx.team_id, customer_id=ctx.customer.id)
            target_id = target.id if target is not None else ctx.draft.target_contact_id
            options = [
                {"value": str(c.id), "label": f"{c.name}（{c.position}）" if c.position else c.name}
                for c in contacts
                if c.id != target_id
            ][:_MAX_REPORTS_TO_OPTIONS]
            if options:
                rendered.append(REPORTS_TO.render(values, submitted, errors, options=options))
        return rendered

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]:
        if ctx.draft.conflict_mobile:
            return ["不会自动修改已有手机号，新提到的手机号已放入追加备注。"]
        return []

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]:
        errors: dict[str, str] = {}
        remark_append = REMARK_APPEND.text(submitted, errors)
        wechat_id = WECHAT.text(submitted, errors)
        email = EMAIL.text(submitted, errors)

        reports_to: int | None = None
        raw_reports_to = submitted.get("reports_to")
        if isinstance(raw_reports_to, str) and raw_reports_to.strip():
            if not raw_reports_to.strip().isdigit():
                errors["reports_to"] = "请从已有联系人中选择汇报对象"
            elif ctx.customer is not None:
                candidate_id = int(raw_reports_to.strip())
                if candidate_id == ctx.draft.target_contact_id:
                    errors["reports_to"] = "汇报对象不能选择联系人本人"
                else:
                    contacts = list_customer_contacts(ctx.db, team_id=ctx.team_id, customer_id=ctx.customer.id)
                    if not any(c.id == candidate_id for c in contacts):
                        errors["reports_to"] = "该汇报对象不在当前客户联系人中"
                    else:
                        reports_to = candidate_id

        if not any(val is not None for val in (remark_append, wechat_id, email, reports_to)) and not errors:
            errors["remark_append"] = "请至少填写一项要补充的内容"

        canonical: Canonical = {
            "remark_append": remark_append,
            "wechat_id": wechat_id,
            "email": email,
            "reports_to": reports_to,
        }
        return canonical, errors

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult:
        from app.crud.customer import contact_crud
        from app.schemas.customer import ContactUpdate

        assert ctx.customer is not None
        target = _load_target(ctx)
        if target is None:
            raise EntityFormError({"remark_append": "该联系人已不存在或无权操作"})

        locked = contact_crud._locked_contact(ctx.db, target)
        actual_rev = int(getattr(locked, "post_commit_revision", None) or 1)
        expected_rev = ctx.draft.target_contact_revision

        conflict_errors: dict[str, str] = {}
        wechat_val = values.get("wechat_id")
        if isinstance(wechat_val, str) and (locked.wechat_id or "").strip() and (locked.wechat_id or "").strip() != wechat_val:
            conflict_errors["wechat_id"] = f"微信已被他人填写为「{locked.wechat_id}」，未覆盖"
        email_val = values.get("email")
        if isinstance(email_val, str) and (locked.email or "").strip() and (locked.email or "").strip() != email_val:
            conflict_errors["email"] = f"邮箱已被他人填写为「{locked.email}」，未覆盖"
        reports_to_val = values.get("reports_to")
        if isinstance(reports_to_val, int) and locked.reports_to is not None and locked.reports_to != reports_to_val:
            conflict_errors["reports_to"] = "汇报对象已被他人填写，未覆盖"

        if conflict_errors:
            ctx.draft.target_contact_revision = actual_rev
            ctx.draft.target_existing_remark = locked.remark
            raise EntityFormError(conflict_errors)

        if expected_rev is not None and actual_rev != expected_rev:
            ctx.draft.target_contact_revision = actual_rev
            ctx.draft.target_existing_remark = locked.remark
            raise EntityFormError(
                {"remark_append": "联系人资料刚刚已被他人更新，已刷新最新备注；你填写的内容已保留，请核对后重新提交"}
            )

        update_payload: dict[str, object] = {}
        summary_parts: list[str] = []

        remark_append = values.get("remark_append")
        if isinstance(remark_append, str) and remark_append.strip():
            merged, changed = merge_contact_remark(locked.remark, remark_append)
            if changed and merged is not None:
                update_payload["remark"] = merged
                summary_parts.append("追加备注")

        if isinstance(wechat_val, str) and not (locked.wechat_id or "").strip():
            update_payload["wechat_id"] = wechat_val
            summary_parts.append(f"补全微信 {wechat_val}")
        if isinstance(email_val, str) and not (locked.email or "").strip():
            update_payload["email"] = email_val
            summary_parts.append(f"补全邮箱 {email_val}")
        if isinstance(reports_to_val, int) and locked.reports_to is None:
            update_payload["reports_to"] = reports_to_val
            summary_parts.append("补全汇报对象")

        if not update_payload:
            return WriteResult(
                target_public_id=f"contact:{locked.id}",
                name=locked.name,
                customer_public_id=ctx.customer.public_id,
                outcome="existing",
                summary="所填内容已存在，未重复写入",
            )

        updated = contact_crud.update(
            ctx.db,
            locked,
            ContactUpdate(**update_payload),
            commit=False,
        )
        ctx.draft.target_contact_revision = int(getattr(updated, "post_commit_revision", None) or actual_rev + 1)
        ctx.draft.target_existing_remark = updated.remark

        return WriteResult(
            target_public_id=f"contact:{updated.id}",
            name=updated.name,
            customer_public_id=ctx.customer.public_id,
            outcome="supplemented",
            summary="已" + "、".join(summary_parts),
            after_commit=refresh_after_commit("contact", updated, str(ctx.user.id), change_type="updated"),
        )

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None:
        return None


FORM = ContactSupplementForm()

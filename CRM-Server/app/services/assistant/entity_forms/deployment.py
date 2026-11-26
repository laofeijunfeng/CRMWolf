"""部署信息 form: credentials and authorized users are never stored here."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import re
from typing import TYPE_CHECKING

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

    from app.services.assistant.contracts import EntityFieldValue, EntityQuote

NAME = FieldSpec("deployment_name", "部署名称", required=True, max_length=100)
ADDRESS = FieldSpec("server_address", "服务器地址", required=True, max_length=500,
                    placeholder="https://")
DEFAULT = FieldSpec("is_default", "设为默认部署", "boolean")
NAME_SUGGESTIONS = ["生产环境", "测试环境", "POC 环境"]
_ENVIRONMENTS = (("生产", "生产环境"), ("测试", "测试环境"), ("POC", "POC 环境"))
_SCHEME = re.compile(r"^https?://", re.IGNORECASE)


def clean_address(raw: str) -> str:
    return re.sub(r"\s+", "", raw).rstrip("/")


class DeploymentForm:
    KIND = "deployment_create"
    LABEL = "部署信息"
    TARGET_PREFIX = "deployment"
    EXTRACT_KEYS: Mapping[str, str] = {
        "deployment_name": "只有原文明确说是生产/测试/POC 环境或给了部署名称时填",
        "server_address": "服务器地址/域名/IP加端口，原样照抄，不要补协议",
        "is_default": "只有原文说“这是主环境/默认用这个”时填“是”",
        "authorized_users": "原文提到的授权人数（只用于提示，不会保存）",
    }
    FIELD_KEYS = frozenset({"deployment_name", "server_address", "is_default"})

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]:  # noqa: ARG002
        out: dict[str, EntityFieldValue] = {}
        for item in extracted:
            text = item.value.strip()
            if item.key == "deployment_name" and "deployment_name" not in out:
                named = next((label for word, label in _ENVIRONMENTS if word.lower() in text.lower()), None)
                out["deployment_name"] = (
                    value("DERIVED", named, phrase=item.quote[:200]) if named and named != text
                    else value("ORIGINAL", text[:2000])
                )
            elif item.key == "server_address" and "server_address" not in out:
                address = clean_address(text)
                if _SCHEME.match(address):
                    out["server_address"] = value("ORIGINAL" if address == text else "NORMALIZED", address[:2000])
                else:
                    out["server_address"] = value(
                        "ORIGINAL", None, choices=[f"https://{address}", f"http://{address}"],
                        warning="原文没有写 http:// 或 https://，请选一个",
                    )
            elif item.key == "is_default" and text in {"是", "true"}:
                out["is_default"] = value("DERIVED", "true", phrase=item.quote[:200])
            elif item.key == "authorized_users":
                out["_authorized_users"] = value("ORIGINAL", text[:2000])
        if "deployment_name" not in out:
            out["deployment_name"] = value("ORIGINAL", None, choices=NAME_SUGGESTIONS)
        return out

    def fields(
        self, ctx: FormContext, values: Mapping[str, EntityFieldValue],  # noqa: ARG002
        submitted: Submitted | None, errors: Mapping[str, str],
    ) -> list[dict[str, object]]:
        return [
            NAME.render(values, submitted, errors, suggestions=NAME_SUGGESTIONS),
            ADDRESS.render(values, submitted, errors),
            DEFAULT.render(values, submitted, errors),
        ]

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]:  # noqa: ARG002
        return ["授权人数不在这里保存，请到 License 申请"] if "_authorized_users" in values else []

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]:  # noqa: ARG002
        errors: dict[str, str] = {}
        name = NAME.text(submitted, errors)
        raw = ADDRESS.text(submitted, errors)
        address = clean_address(raw) if raw else None
        if address is not None and not _SCHEME.match(address):
            errors["server_address"] = "服务器地址要以 http:// 或 https:// 开头"
        return {"deployment_name": name, "server_address": address, "is_default": DEFAULT.flag(submitted)}, errors

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult:
        from pydantic import ValidationError

        from app.crud.crud_deployment import deployment_info_crud
        from app.schemas.deployment import DeploymentInfoInternalCreate

        assert ctx.customer is not None
        try:
            obj_in = DeploymentInfoInternalCreate.model_validate({**values, "customer_id": ctx.customer.id})
        except ValidationError as exc:
            raise EntityFormError({"server_address": "部署资料不完整，请核对"}) from exc
        deployment = deployment_info_crud.create(ctx.db, ctx.team_id, obj_in, commit=False)
        return WriteResult(
            target_public_id=f"deployment:{deployment.id}",
            name=str(deployment.deployment_name)[:200],
            customer_public_id=ctx.customer.public_id,
            after_commit=refresh_after_commit("deployment_info", deployment, str(ctx.user.id)),
        )

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None:  # noqa: ARG002
        return "这个服务器地址已登记，如需修改请到客户详情"


FORM = DeploymentForm()

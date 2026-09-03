"""Authoritative CRM resource resolution used while planning Workflow commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError, model_validator

from app.services.agent.tools.api_client import CRMAPIClientError, InternalCRMAPIClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.services.agent.query.schemas import EntityRef


class WorkflowResourceResolutionError(RuntimeError):
    """An authoritative CRM planning resource could not be read safely."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class CustomerMemberCandidatePayload(BaseModel):
    """Closed-world response contract for the member-candidates endpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2000)
    roles: list[str] = Field(default_factory=list, max_length=100)
    already_member: bool = False


_customer_member_candidates_adapter = TypeAdapter(list[CustomerMemberCandidatePayload])


class WorkflowCustomerIdentityItemPayload(BaseModel):
    """Closed projection of one authoritative customer identity candidate."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^cus_[A-Za-z0-9_-]+$", min_length=5, max_length=100)
    account_name: str = Field(min_length=1, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    match: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowCustomerIdentityPayload(BaseModel):
    """Closed response contract for authorized customer identity resolution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decision: Literal[
        "auto_select",
        "ranked_auto_selectable",
        "requires_confirmation",
        "no_match",
        "semantic_related_only",
    ]
    items: list[WorkflowCustomerIdentityItemPayload] = Field(max_length=50)
    related_customers: list[WorkflowCustomerIdentityItemPayload] = Field(default_factory=list, max_length=50)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CustomerDefaultProcurementMethodPayload(BaseModel):
    """Closed-world response contract for one customer's procurement default."""

    model_config = ConfigDict(extra="forbid", strict=True)

    procurement_method_id: int | None
    code: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    message: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_shape(self) -> CustomerDefaultProcurementMethodPayload:
        if self.procurement_method_id is None:
            if self.message is None or any(value is not None for value in (self.code, self.name, self.description)):
                raise ValueError("empty customer procurement default has an invalid shape")
            return self
        if self.procurement_method_id <= 0 or self.code is None or self.name is None:
            raise ValueError("customer procurement default is incomplete")
        if self.message is not None:
            raise ValueError("resolved customer procurement default cannot include a message")
        return self


class ProcurementMethodOptionPayload(BaseModel):
    """Closed-world response contract for active procurement method options."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


_procurement_method_options_adapter = TypeAdapter(list[ProcurementMethodOptionPayload])


class OpportunityCurrentStageProjectionPayload(BaseModel):
    """Strict fields consumed from the larger opportunity-list stage projection."""

    model_config = ConfigDict(extra="ignore", strict=True)

    stage_name: str = Field(min_length=1, max_length=200)


class OpportunityListProjectionPayload(BaseModel):
    """Read-only projection of fields needed to authorize one stage transition."""

    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1, max_length=100)
    public_id: str = Field(min_length=1, max_length=100)
    opportunity_name: str = Field(min_length=1, max_length=255)
    customer_id: str = Field(min_length=1, max_length=100)
    status: int = Field(ge=0, le=2)
    approval_phase: Literal["draft", "pending_review", "approved", "rejected"]
    stage: OpportunityCurrentStageProjectionPayload | None = None

    @model_validator(mode="after")
    def validate_public_identity(self) -> OpportunityListProjectionPayload:
        if self.id != self.public_id:
            raise ValueError("opportunity public identity is inconsistent")
        return self


class OpportunityListPagePayload(BaseModel):
    """Closed paginated contract for the opportunity-list endpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[OpportunityListProjectionPayload]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_pages: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_pagination(self) -> OpportunityListPagePayload:
        expected_total_pages = (self.total + self.page_size - 1) // self.page_size if self.total else 0
        if self.total_pages != expected_total_pages:
            raise ValueError("opportunity pagination total_pages is inconsistent")
        if self.page > max(self.total_pages, 1):
            raise ValueError("opportunity pagination page is out of range")
        if len(self.items) > self.page_size or len(self.items) > self.total:
            raise ValueError("opportunity pagination item count is inconsistent")
        return self


class OpportunityStagePayload(BaseModel):
    """Closed-world contract for one authoritative procurement stage."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: int = Field(gt=0)
    stage_name: str = Field(min_length=1, max_length=200)
    win_probability: int = Field(ge=0, le=100)
    sort_order: int = Field(ge=0)
    is_current: bool
    is_default_start: bool
    can_skip: bool


_opportunity_stages_adapter = TypeAdapter(list[OpportunityStagePayload])


class FollowUpTaskCustomerPayload(BaseModel):
    """Strict customer identity embedded in a follow-up task projection."""

    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1, max_length=100)
    public_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    account_name: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_identity(self) -> FollowUpTaskCustomerPayload:
        if self.id != self.public_id or self.name != self.account_name:
            raise ValueError("follow-up task customer identity is inconsistent")
        return self


class FollowUpTaskProjectionPayload(BaseModel):
    """Read-only fields required to authorize one follow-up task transition."""

    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1, max_length=100, pattern=r"^fut_[0-9a-f]{32}$")
    public_id: str = Field(min_length=1, max_length=100, pattern=r"^fut_[0-9a-f]{32}$")
    customer: FollowUpTaskCustomerPayload | None = None
    owner_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=20)
    due_at: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_identity(self) -> FollowUpTaskProjectionPayload:
        if self.id != self.public_id:
            raise ValueError("follow-up task public identity is inconsistent")
        return self


class FollowUpTaskListPayload(BaseModel):
    """Closed pagination facts consumed from the follow-up task list endpoint."""

    model_config = ConfigDict(extra="ignore", strict=True)

    items: list[FollowUpTaskProjectionPayload]
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_page(self) -> FollowUpTaskListPayload:
        if len(self.items) > self.total:
            raise ValueError("follow-up task list item count exceeds total")
        return self


class FollowUpConfirmationCustomerPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1, max_length=100)
    public_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_identity(self) -> FollowUpConfirmationCustomerPayload:
        if self.id != self.public_id:
            raise ValueError("customer public identity is inconsistent")
        return self


class FollowUpConfirmationTaskPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(pattern=r"^fut_[0-9a-f]{32}$")
    public_id: str = Field(pattern=r"^fut_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def validate_identity(self) -> FollowUpConfirmationTaskPayload:
        if self.id != self.public_id:
            raise ValueError("follow-up task public identity is inconsistent")
        return self


class FollowUpTaskConfirmationCasePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(pattern=r"^fuc_[0-9a-f]{32}$")
    public_id: str = Field(pattern=r"^fuc_[0-9a-f]{32}$")
    status: Literal["PENDING"]
    owner_id: str = Field(min_length=1, max_length=100)
    question_text: str = Field(min_length=1, max_length=10_000)
    suggested_action: str = Field(min_length=1, max_length=50)
    customer: FollowUpConfirmationCustomerPayload
    task: FollowUpConfirmationTaskPayload
    expires_at: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_identity(self) -> FollowUpTaskConfirmationCasePayload:
        if self.id != self.public_id:
            raise ValueError("confirmation case public identity is inconsistent")
        return self


@dataclass(frozen=True)
class WorkflowCustomerCandidate:
    customer_id: str
    customer_name: str
    city: str | None = None


@dataclass(frozen=True)
class WorkflowCustomerResolution:
    status: Literal["RESOLVED", "SELECTION_REQUIRED", "NOT_FOUND", "MISSING"]
    customer: WorkflowCustomerCandidate | None = None
    candidates: tuple[WorkflowCustomerCandidate, ...] = ()


@dataclass(frozen=True)
class CustomerMemberCandidate:
    user_id: str
    user_name: str
    roles: tuple[str, ...]
    already_member: bool


@dataclass(frozen=True)
class CustomerMemberResolution:
    status: Literal["RESOLVED", "ALREADY_MEMBER", "NOT_FOUND", "AMBIGUOUS"]
    user_id: str | None = None
    user_name: str | None = None
    candidates: tuple[CustomerMemberCandidate, ...] = ()


@dataclass(frozen=True)
class FollowUpTaskCandidate:
    task_id: str
    title: str
    customer_id: str | None
    customer_name: str | None
    owner_id: str
    status: str
    due_at: str | None = None


@dataclass(frozen=True)
class FollowUpTaskResolution:
    status: Literal["RESOLVED", "SELECTION_REQUIRED", "NOT_FOUND"]
    task: FollowUpTaskCandidate | None = None
    candidates: tuple[FollowUpTaskCandidate, ...] = ()


@dataclass(frozen=True)
class FollowUpTaskConfirmationCaseCandidate:
    case_id: str
    status: str
    owner_id: str
    question_text: str
    suggested_action: str
    customer_id: str | None
    task_id: str | None
    expires_at: str | None = None


@dataclass(frozen=True)
class FollowUpTaskConfirmationCaseResolution:
    status: Literal["RESOLVED", "NOT_FOUND"]
    case: FollowUpTaskConfirmationCaseCandidate | None = None


@dataclass(frozen=True)
class ProcurementMethodCandidate:
    method_id: int
    method_code: str
    method_name: str


@dataclass(frozen=True)
class ProcurementMethodResolution:
    status: Literal["RESOLVED", "SELECTION_REQUIRED", "NOT_FOUND"]
    method_id: int | None = None
    method_name: str | None = None
    candidates: tuple[ProcurementMethodCandidate, ...] = ()


@dataclass(frozen=True)
class OpportunityStageCandidate:
    opportunity_id: str
    opportunity_name: str
    current_stage_name: str | None = None


@dataclass(frozen=True)
class OpportunityStageTransitionStep:
    stage_template_id: int
    stage_name: str


@dataclass(frozen=True)
class OpportunityStageResolution:
    status: Literal[
        "RESOLVED",
        "OPPORTUNITY_SELECTION_REQUIRED",
        "STAGE_SELECTION_REQUIRED",
        "NOT_FOUND",
    ]
    opportunity: OpportunityStageCandidate | None = None
    target_stage: OpportunityStageTransitionStep | None = None
    steps: tuple[OpportunityStageTransitionStep, ...] = ()
    opportunity_candidates: tuple[OpportunityStageCandidate, ...] = ()
    stage_candidates: tuple[OpportunityStageTransitionStep, ...] = ()


class CustomerMemberResolver(Protocol):
    async def resolve(
        self,
        *,
        customer_id: str,
        user_name: str,
        authorization: str,
        selected_user_id: str | None = None,
    ) -> CustomerMemberResolution: ...


class WorkflowCustomerResolver(Protocol):
    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> WorkflowCustomerResolution: ...


class FollowUpTaskResolver(Protocol):
    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        task_id: str | None = None,
        task_reference_text: str | None = None,
        selected_task_id: str | None = None,
    ) -> FollowUpTaskResolution: ...


class FollowUpTaskConfirmationCaseResolver(Protocol):
    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        case_id: str,
    ) -> FollowUpTaskConfirmationCaseResolution: ...


class OpportunityProcurementMethodResolver(Protocol):
    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        selected_method_id: int | None = None,
    ) -> ProcurementMethodResolution: ...


class OpportunityStageResolver(Protocol):
    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None = None,
        opportunity_reference_text: str | None = None,
        target_stage_name: str | None = None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution: ...


class CRMWorkflowCustomerResolver:
    """Resolve user language or page context to one authorized CRM customer."""

    async def validate_cached(
        self,
        *,
        customer_id: str,
        authorization: str,
    ) -> WorkflowCustomerResolution:
        """Revalidate a checkpoint identity without running name search."""

        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/customers/{customer_id}",
                authorization,
            )
        except CRMAPIClientError as exc:
            if exc.status_code == 404:
                return WorkflowCustomerResolution(status="NOT_FOUND")
            retryable = exc.status_code is None or exc.status_code in {408, 429} or exc.status_code >= 500
            raise WorkflowResourceResolutionError(
                "客户信息暂时无法读取。" if retryable else exc.message,
                retryable=retryable,
            ) from exc
        if not isinstance(payload, dict):
            raise WorkflowResourceResolutionError("客户查询结果无效。", retryable=False)
        public_id = payload.get("public_id") or payload.get("id")
        account_name = payload.get("account_name")
        if str(public_id) != customer_id or not isinstance(account_name, str) or not account_name.strip():
            raise WorkflowResourceResolutionError("客户查询结果无效。", retryable=False)
        return WorkflowCustomerResolution(
            status="RESOLVED",
            customer=WorkflowCustomerCandidate(
                customer_id=customer_id,
                customer_name=account_name.strip(),
            ),
        )

    def __init__(self, *, api_client: InternalCRMAPIClient | None = None) -> None:
        self._api_client = api_client or InternalCRMAPIClient()

    async def resolve(
        self,
        *,
        customer_lookup_name: str | None,
        trusted_context_customer: EntityRef | None,
        selected_customer_id: str | None,
        authorization: str,
    ) -> WorkflowCustomerResolution:
        if customer_lookup_name is None:
            if trusted_context_customer is None or trusted_context_customer.resource != "customer":
                return WorkflowCustomerResolution(status="MISSING")
            return WorkflowCustomerResolution(
                status="RESOLVED",
                customer=WorkflowCustomerCandidate(
                    customer_id=trusted_context_customer.public_id,
                    customer_name=trusted_context_customer.display_name,
                ),
            )

        try:
            payload = await self._api_client.request(
                "GET",
                "/v1/customers/identity-resolution",
                authorization,
                params={
                    "query": customer_lookup_name,
                    "limit": 10,
                },
            )
            parsed = WorkflowCustomerIdentityPayload.model_validate(payload)
        except CRMAPIClientError as exc:
            retryable = exc.status_code is None or exc.status_code in {408, 429} or exc.status_code >= 500
            raise WorkflowResourceResolutionError(
                "客户信息暂时无法读取。" if retryable else exc.message,
                retryable=retryable,
            ) from exc
        except ValidationError as exc:
            raise WorkflowResourceResolutionError(
                "客户查询结果无效。",
                retryable=False,
            ) from exc

        candidates = tuple(
            WorkflowCustomerCandidate(
                customer_id=item.id,
                customer_name=item.account_name,
                city=item.city,
            )
            for item in parsed.items
        )
        if selected_customer_id is not None:
            selected = next(
                (candidate for candidate in candidates if candidate.customer_id == selected_customer_id),
                None,
            )
            if selected is None:
                return WorkflowCustomerResolution(
                    status="SELECTION_REQUIRED" if candidates else "NOT_FOUND",
                    candidates=candidates,
                )
            return WorkflowCustomerResolution(status="RESOLVED", customer=selected)
        if parsed.decision in {"no_match", "semantic_related_only"} or not candidates:
            return WorkflowCustomerResolution(status="NOT_FOUND")
        if parsed.decision in {"auto_select", "ranked_auto_selectable"}:
            return WorkflowCustomerResolution(status="RESOLVED", customer=candidates[0])
        return WorkflowCustomerResolution(
            status="SELECTION_REQUIRED",
            candidates=candidates,
        )


class CRMCustomerMemberResolver:
    """Resolve a user-facing member name to one authorized team user."""

    def __init__(self, *, api_client: InternalCRMAPIClient | None = None) -> None:
        self._api_client = api_client or InternalCRMAPIClient()

    async def resolve(
        self,
        *,
        customer_id: str,
        user_name: str,
        authorization: str,
        selected_user_id: str | None = None,
    ) -> CustomerMemberResolution:
        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/customers/{customer_id}/member-candidates",
                authorization,
            )
            parsed = _customer_member_candidates_adapter.validate_python(payload)
        except CRMAPIClientError as exc:
            retryable = exc.status_code is None or exc.status_code in {408, 429} or exc.status_code >= 500
            raise WorkflowResourceResolutionError(
                "客户成员候选人暂时无法读取。" if retryable else exc.message,
                retryable=retryable,
            ) from exc
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "客户成员候选人暂时无法读取。",
                retryable=True,
            ) from exc
        except ValidationError as exc:
            raise WorkflowResourceResolutionError(
                "客户成员候选人数据无效。",
                retryable=False,
            ) from exc

        candidates = tuple(
            CustomerMemberCandidate(
                user_id=item.id,
                user_name=item.name.strip(),
                roles=tuple(item.roles),
                already_member=item.already_member,
            )
            for item in parsed
        )
        if selected_user_id is not None:
            selected = next(
                (candidate for candidate in candidates if candidate.user_id == selected_user_id),
                None,
            )
            if selected is None:
                return CustomerMemberResolution(status="NOT_FOUND")
            if selected.already_member:
                return CustomerMemberResolution(
                    status="ALREADY_MEMBER",
                    user_id=selected.user_id,
                    user_name=selected.user_name,
                )
            return CustomerMemberResolution(
                status="RESOLVED",
                user_id=selected.user_id,
                user_name=selected.user_name,
            )

        normalized_name = _normalize_name(user_name)
        exact_matches = tuple(
            candidate for candidate in candidates if _normalize_name(candidate.user_name) == normalized_name
        )
        matches = exact_matches or tuple(
            candidate for candidate in candidates if normalized_name in _normalize_name(candidate.user_name)
        )
        if not matches:
            return CustomerMemberResolution(status="NOT_FOUND")
        if len(matches) > 1:
            available = tuple(candidate for candidate in matches if not candidate.already_member)
            if not available:
                return CustomerMemberResolution(status="ALREADY_MEMBER")
            return CustomerMemberResolution(status="AMBIGUOUS", candidates=available)

        matched = matches[0]
        if matched.already_member:
            return CustomerMemberResolution(
                status="ALREADY_MEMBER",
                user_id=matched.user_id,
                user_name=matched.user_name,
            )
        return CustomerMemberResolution(
            status="RESOLVED",
            user_id=matched.user_id,
            user_name=matched.user_name,
        )


class CRMOpportunityStageResolver:
    """Resolve one authorized opportunity and its sequential future stages."""

    def __init__(self, *, api_client: InternalCRMAPIClient | None = None) -> None:
        self._api_client = api_client or InternalCRMAPIClient()

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        opportunity_id: str | None,
        opportunity_reference_text: str | None,
        target_stage_name: str | None,
        selected_opportunity_id: str | None = None,
        selected_stage_id: int | None = None,
    ) -> OpportunityStageResolution:
        opportunities = await self._load_opportunities(
            customer_id=customer_id,
            authorization=authorization,
        )
        candidates = tuple(
            OpportunityStageCandidate(
                opportunity_id=item.public_id,
                opportunity_name=item.opportunity_name.strip(),
                current_stage_name=item.stage.stage_name.strip() if item.stage is not None else None,
            )
            for item in opportunities
            if item.customer_id == customer_id and item.status == 0 and item.approval_phase == "approved"
        )
        selected_opportunity = self._select_opportunity(
            candidates,
            opportunity_id=opportunity_id,
            opportunity_reference_text=opportunity_reference_text,
            selected_opportunity_id=selected_opportunity_id,
        )
        if isinstance(selected_opportunity, OpportunityStageResolution):
            return selected_opportunity

        stages = await self._load_stages(
            opportunity_id=selected_opportunity.opportunity_id,
            authorization=authorization,
        )
        future_steps = self._future_steps(stages)
        if not future_steps:
            return OpportunityStageResolution(
                status="NOT_FOUND",
                opportunity=selected_opportunity,
            )

        selected_target = self._select_target_stage(
            future_steps,
            all_stages=stages,
            target_stage_name=target_stage_name,
            selected_stage_id=selected_stage_id,
            opportunity=selected_opportunity,
        )
        if isinstance(selected_target, OpportunityStageResolution):
            return selected_target

        target_index = next(
            index
            for index, step in enumerate(future_steps)
            if step.stage_template_id == selected_target.stage_template_id
        )
        return OpportunityStageResolution(
            status="RESOLVED",
            opportunity=selected_opportunity,
            target_stage=selected_target,
            steps=future_steps[: target_index + 1],
        )

    async def _load_opportunities(
        self,
        *,
        customer_id: str,
        authorization: str,
    ) -> tuple[OpportunityListProjectionPayload, ...]:
        items: list[OpportunityListProjectionPayload] = []
        next_page = 1
        total: int | None = None
        page_size: int | None = None
        total_pages: int | None = None
        try:
            while total_pages is None or next_page <= total_pages:
                params: dict[str, object] = {
                    "customer_id": customer_id,
                    "status": 0,
                    "limit": 100,
                }
                if next_page > 1:
                    params["skip"] = (next_page - 1) * 100
                payload = await self._api_client.request(
                    "GET",
                    "/v1/opportunities/",
                    authorization,
                    params=params,
                )
                page = OpportunityListPagePayload.model_validate(payload)
                if page.page != next_page:
                    raise ValueError("opportunity pagination returned an unexpected page")
                if total is not None and page.total != total:
                    raise ValueError("opportunity pagination total changed between pages")
                if page_size is not None and page.page_size != page_size:
                    raise ValueError("opportunity pagination page_size changed between pages")
                if total_pages is not None and page.total_pages != total_pages:
                    raise ValueError("opportunity pagination total_pages changed between pages")
                total = page.total
                page_size = page.page_size
                total_pages = page.total_pages
                items.extend(page.items)
                next_page += 1
        except CRMAPIClientError as exc:
            self._raise_api_error(exc, unavailable_message="商机列表暂时无法读取。")
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "商机列表暂时无法读取。",
                retryable=True,
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise WorkflowResourceResolutionError(
                "商机列表数据无效。",
                retryable=False,
            ) from exc

        opportunity_ids = [item.public_id for item in items]
        if total is None or len(items) != total or len(opportunity_ids) != len(set(opportunity_ids)):
            raise WorkflowResourceResolutionError(
                "商机列表数据无效。",
                retryable=False,
            )
        return tuple(items)

    async def _load_stages(
        self,
        *,
        opportunity_id: str,
        authorization: str,
    ) -> tuple[OpportunityStagePayload, ...]:
        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/opportunities/{opportunity_id}/procurement-stages",
                authorization,
            )
            parsed = tuple(_opportunity_stages_adapter.validate_python(payload))
            stage_ids = [stage.id for stage in parsed]
            sort_orders = [stage.sort_order for stage in parsed]
            if len(stage_ids) != len(set(stage_ids)) or len(sort_orders) != len(set(sort_orders)):
                raise ValueError("opportunity stages contain duplicate identities or ordering")
            if sum(stage.is_current for stage in parsed) > 1:
                raise ValueError("opportunity stages contain multiple current stages")
            if sum(stage.is_default_start for stage in parsed) > 1:
                raise ValueError("opportunity stages contain multiple default stages")
            return tuple(sorted(parsed, key=lambda stage: stage.sort_order))
        except CRMAPIClientError as exc:
            self._raise_api_error(exc, unavailable_message="商机采购阶段暂时无法读取。")
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "商机采购阶段暂时无法读取。",
                retryable=True,
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise WorkflowResourceResolutionError(
                "商机采购阶段数据无效。",
                retryable=False,
            ) from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _select_opportunity(
        candidates: tuple[OpportunityStageCandidate, ...],
        *,
        opportunity_id: str | None,
        opportunity_reference_text: str | None,
        selected_opportunity_id: str | None,
    ) -> OpportunityStageCandidate | OpportunityStageResolution:
        if not candidates:
            return OpportunityStageResolution(status="NOT_FOUND")
        if selected_opportunity_id is not None:
            selected = next(
                (candidate for candidate in candidates if candidate.opportunity_id == selected_opportunity_id),
                None,
            )
            if selected is not None:
                return selected
            return OpportunityStageResolution(
                status="OPPORTUNITY_SELECTION_REQUIRED",
                opportunity_candidates=candidates,
            )
        if opportunity_id is not None:
            selected = next(
                (candidate for candidate in candidates if candidate.opportunity_id == opportunity_id),
                None,
            )
            if selected is not None:
                return selected
            return OpportunityStageResolution(status="NOT_FOUND")
        if opportunity_reference_text is not None:
            matches = _name_matches(candidates, opportunity_reference_text, name=lambda item: item.opportunity_name)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return OpportunityStageResolution(
                    status="OPPORTUNITY_SELECTION_REQUIRED",
                    opportunity_candidates=matches,
                )
            if opportunity_id is not None:
                return OpportunityStageResolution(status="NOT_FOUND")
            # Keep all authorized opportunities available for semantic
            # ranking. A failed substring match is not proof that no
            # opportunity exists.
            return OpportunityStageResolution(
                status="OPPORTUNITY_SELECTION_REQUIRED",
                opportunity_candidates=candidates,
            )
        if len(candidates) == 1:
            return candidates[0]
        return OpportunityStageResolution(
            status="OPPORTUNITY_SELECTION_REQUIRED",
            opportunity_candidates=candidates,
        )

    @staticmethod
    def _future_steps(
        stages: tuple[OpportunityStagePayload, ...],
    ) -> tuple[OpportunityStageTransitionStep, ...]:
        if not stages:
            return ()
        current_index = next(
            (index for index, stage in enumerate(stages) if stage.is_current),
            None,
        )
        if current_index is None:
            start_index = next(
                (index for index, stage in enumerate(stages) if stage.is_default_start),
                0,
            )
        else:
            start_index = current_index + 1
        return tuple(
            OpportunityStageTransitionStep(
                stage_template_id=stage.id,
                stage_name=stage.stage_name.strip(),
            )
            for stage in stages[start_index:]
        )

    @staticmethod
    def _select_target_stage(
        future_steps: tuple[OpportunityStageTransitionStep, ...],
        *,
        all_stages: tuple[OpportunityStagePayload, ...],
        target_stage_name: str | None,
        selected_stage_id: int | None,
        opportunity: OpportunityStageCandidate,
    ) -> OpportunityStageTransitionStep | OpportunityStageResolution:
        if selected_stage_id is not None:
            selected = next(
                (step for step in future_steps if step.stage_template_id == selected_stage_id),
                None,
            )
            if selected is not None:
                return selected
            return OpportunityStageResolution(
                status="STAGE_SELECTION_REQUIRED",
                opportunity=opportunity,
                stage_candidates=future_steps,
            )
        if target_stage_name is None:
            return future_steps[0]

        # A natural-language paraphrase should be ranked against future
        # stages, but an explicit name (or unambiguous fragment) of the
        # current/previous stage must never be silently redirected to a later
        # stage. Keep this no-op guard deterministic and independent of the
        # model's ranking.
        all_matches = _name_matches(
            all_stages,
            target_stage_name,
            name=lambda item: item.stage_name,
        )
        future_stage_ids = {step.stage_template_id for step in future_steps}
        non_future_stages = tuple(stage for stage in all_stages if stage.id not in future_stage_ids)
        if all_matches and all(stage.id not in future_stage_ids for stage in all_matches):
            return OpportunityStageResolution(
                status="NOT_FOUND",
                opportunity=opportunity,
            )
        # A short, unambiguous fragment that can only describe the current or
        # a previous stage is also a no-op request. This check is a safety
        # rejection only; it never selects a stage and never routes a task.
        normalized_target = _normalize_name(target_stage_name)
        if normalized_target and any(
            normalized_target in _normalize_name(stage.stage_name)
            or _normalize_name(stage.stage_name) in normalized_target
            for stage in non_future_stages
        ):
            return OpportunityStageResolution(
                status="NOT_FOUND",
                opportunity=opportunity,
            )

        matches = _name_matches(future_steps, target_stage_name, name=lambda item: item.stage_name)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return OpportunityStageResolution(
                status="STAGE_SELECTION_REQUIRED",
                opportunity=opportunity,
                stage_candidates=matches,
            )
        # The stage name came from natural language and did not exactly bind
        # to an authorized stage. Preserve the full future-stage set for the
        # semantic selector instead of treating a paraphrase as non-existent.
        return OpportunityStageResolution(
            status="STAGE_SELECTION_REQUIRED",
            opportunity=opportunity,
            stage_candidates=future_steps,
        )

    @staticmethod
    def _raise_api_error(exc: CRMAPIClientError, *, unavailable_message: str) -> None:
        retryable = exc.status_code is None or exc.status_code in {408, 429} or exc.status_code >= 500
        raise WorkflowResourceResolutionError(
            unavailable_message if retryable else exc.message,
            retryable=retryable,
        ) from exc


class CRMOpportunityProcurementMethodResolver:
    """Resolve an opportunity procurement method from authorized CRM resources."""

    def __init__(self, *, api_client: InternalCRMAPIClient | None = None) -> None:
        self._api_client = api_client or InternalCRMAPIClient()

    async def resolve(
        self,
        *,
        customer_id: str,
        authorization: str,
        selected_method_id: int | None = None,
    ) -> ProcurementMethodResolution:
        try:
            default_payload = await self._api_client.request(
                "GET",
                f"/v1/customers/{customer_id}/default-procurement-method",
                authorization,
            )
            options_payload = await self._api_client.request(
                "GET",
                "/v1/procurement-methods/options",
                authorization,
            )
            customer_default = CustomerDefaultProcurementMethodPayload.model_validate(default_payload)
            parsed_options = _procurement_method_options_adapter.validate_python(options_payload)
        except CRMAPIClientError as exc:
            retryable = exc.status_code is None or exc.status_code in {408, 429} or exc.status_code >= 500
            raise WorkflowResourceResolutionError(
                "商机采购方式暂时无法读取。" if retryable else exc.message,
                retryable=retryable,
            ) from exc
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "商机采购方式暂时无法读取。",
                retryable=True,
            ) from exc
        except ValidationError as exc:
            raise WorkflowResourceResolutionError(
                "商机采购方式数据无效。",
                retryable=False,
            ) from exc

        candidates = tuple(
            ProcurementMethodCandidate(
                method_id=item.id,
                method_code=item.code.strip(),
                method_name=item.name.strip(),
            )
            for item in parsed_options
        )
        if selected_method_id is not None:
            selected = next(
                (candidate for candidate in candidates if candidate.method_id == selected_method_id),
                None,
            )
            if selected is None:
                return ProcurementMethodResolution(
                    status="NOT_FOUND",
                    candidates=candidates,
                )
            return ProcurementMethodResolution(
                status="RESOLVED",
                method_id=selected.method_id,
                method_name=selected.method_name,
            )

        default_method_id = customer_default.procurement_method_id
        if default_method_id is not None:
            default_method = next(
                (candidate for candidate in candidates if candidate.method_id == default_method_id),
                None,
            )
            if default_method is not None:
                return ProcurementMethodResolution(
                    status="RESOLVED",
                    method_id=default_method.method_id,
                    method_name=default_method.method_name,
                )
        if len(candidates) == 1:
            only_method = candidates[0]
            return ProcurementMethodResolution(
                status="RESOLVED",
                method_id=only_method.method_id,
                method_name=only_method.method_name,
            )
        if not candidates:
            return ProcurementMethodResolution(status="NOT_FOUND")
        return ProcurementMethodResolution(
            status="SELECTION_REQUIRED",
            candidates=candidates,
        )


class CRMFollowUpTaskConfirmationCaseResolver:
    """Resolve one pending current-user-owned confirmation Case from CRM APIs."""

    def __init__(self, *, api_client: InternalCRMAPIClient | None = None) -> None:
        self._api_client = api_client or InternalCRMAPIClient()

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        case_id: str,
    ) -> FollowUpTaskConfirmationCaseResolution:
        if re.fullmatch(r"fuc_[0-9a-f]{32}", case_id) is None:
            return FollowUpTaskConfirmationCaseResolution(status="NOT_FOUND")
        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/follow-up-tasks/confirmation-cases/{case_id}",
                authorization,
            )
            parsed = FollowUpTaskConfirmationCasePayload.model_validate(payload)
        except CRMAPIClientError as exc:
            if exc.status_code in {403, 404}:
                return FollowUpTaskConfirmationCaseResolution(status="NOT_FOUND")
            _raise_follow_up_task_api_error(exc)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "待确认事项暂时无法读取。",
                retryable=True,
            ) from exc
        except ValidationError as exc:
            raise WorkflowResourceResolutionError(
                "待确认事项数据无效。",
                retryable=False,
            ) from exc
        if parsed.public_id != case_id or parsed.owner_id != str(user_id):
            return FollowUpTaskConfirmationCaseResolution(status="NOT_FOUND")
        return FollowUpTaskConfirmationCaseResolution(
            status="RESOLVED",
            case=FollowUpTaskConfirmationCaseCandidate(
                case_id=parsed.public_id,
                status=parsed.status,
                owner_id=parsed.owner_id,
                question_text=parsed.question_text,
                suggested_action=parsed.suggested_action,
                customer_id=parsed.customer.public_id,
                task_id=parsed.task.public_id,
                expires_at=parsed.expires_at,
            ),
        )


class CRMFollowUpTaskResolver:
    """Resolve one open, current-user-owned task from authoritative CRM APIs."""

    def __init__(self, *, api_client: InternalCRMAPIClient | None = None) -> None:
        self._api_client = api_client or InternalCRMAPIClient()

    async def resolve(
        self,
        *,
        authorization: str,
        user_id: int,
        task_id: str | None = None,
        task_reference_text: str | None = None,
        selected_task_id: str | None = None,
    ) -> FollowUpTaskResolution:
        authoritative_id = selected_task_id or task_id
        if authoritative_id is not None:
            task = await self._load_task(
                task_id=authoritative_id,
                authorization=authorization,
                user_id=user_id,
            )
            if task is None:
                return FollowUpTaskResolution(status="NOT_FOUND")
            return FollowUpTaskResolution(status="RESOLVED", task=task)

        candidates = await self._load_open_tasks(
            authorization=authorization,
            user_id=user_id,
        )
        if task_reference_text:
            matched = _follow_up_task_matches(candidates, task_reference_text)
            if matched:
                candidates = matched
            # A natural-language reference that is not an exact identity must
            # remain a candidate-selection problem. Returning NOT_FOUND here
            # discarded valid tasks before the Agent could understand the
            # user's context.
        if len(candidates) == 1:
            return FollowUpTaskResolution(status="RESOLVED", task=candidates[0])
        if not candidates:
            return FollowUpTaskResolution(status="NOT_FOUND")
        return FollowUpTaskResolution(
            status="SELECTION_REQUIRED",
            candidates=candidates,
        )

    async def _load_task(
        self,
        *,
        task_id: str,
        authorization: str,
        user_id: int,
    ) -> FollowUpTaskCandidate | None:
        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/follow-up-tasks/{task_id}",
                authorization,
            )
            parsed = FollowUpTaskProjectionPayload.model_validate(payload)
        except CRMAPIClientError as exc:
            if exc.status_code in {403, 404}:
                return None
            _raise_follow_up_task_api_error(exc)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "跟进任务暂时无法读取。",
                retryable=True,
            ) from exc
        except ValidationError as exc:
            raise WorkflowResourceResolutionError(
                "跟进任务数据无效。",
                retryable=False,
            ) from exc
        candidate = _follow_up_task_candidate(parsed)
        if candidate.owner_id != str(user_id) or candidate.status != "open":
            return None
        return candidate

    async def _load_open_tasks(
        self,
        *,
        authorization: str,
        user_id: int,
    ) -> tuple[FollowUpTaskCandidate, ...]:
        items: list[FollowUpTaskProjectionPayload] = []
        expected_total: int | None = None
        try:
            while expected_total is None or len(items) < expected_total:
                payload = await self._api_client.request(
                    "GET",
                    "/v1/follow-up-tasks",
                    authorization,
                    params={
                        "status": "open",
                        "owner_scope": "mine",
                        "skip": len(items),
                        "limit": 100,
                    },
                )
                page = FollowUpTaskListPayload.model_validate(payload)
                if expected_total is None:
                    expected_total = page.total
                elif page.total != expected_total:
                    raise ValueError("follow-up task total changed between pages")
                if not page.items and len(items) < expected_total:
                    raise ValueError("follow-up task pagination stopped before total")
                items.extend(page.items)
        except CRMAPIClientError as exc:
            _raise_follow_up_task_api_error(exc)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise WorkflowResourceResolutionError(
                "跟进任务暂时无法读取。",
                retryable=True,
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise WorkflowResourceResolutionError(
                "跟进任务列表数据无效。",
                retryable=False,
            ) from exc

        task_ids = [item.public_id for item in items]
        if expected_total is None or len(items) != expected_total or len(task_ids) != len(set(task_ids)):
            raise WorkflowResourceResolutionError(
                "跟进任务列表数据无效。",
                retryable=False,
            )
        candidates = tuple(_follow_up_task_candidate(item) for item in items)
        if any(candidate.owner_id != str(user_id) or candidate.status != "open" for candidate in candidates):
            raise WorkflowResourceResolutionError(
                "跟进任务列表数据无效。",
                retryable=False,
            )
        return candidates


def _follow_up_task_candidate(payload: FollowUpTaskProjectionPayload) -> FollowUpTaskCandidate:
    customer = payload.customer
    return FollowUpTaskCandidate(
        task_id=payload.public_id,
        title=payload.title.strip(),
        customer_id=customer.public_id if customer is not None else None,
        customer_name=customer.account_name.strip() if customer is not None else None,
        owner_id=payload.owner_id,
        status=payload.status,
        due_at=payload.due_at,
    )


def _follow_up_task_matches(
    candidates: tuple[FollowUpTaskCandidate, ...],
    query: str,
) -> tuple[FollowUpTaskCandidate, ...]:
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return ()
    # Only exact task identity is safe to bind here. Fragments, aliases and
    # business descriptions go through semantic candidate ranking.
    return tuple(
        candidate
        for candidate in candidates
        if normalized_query in {
            _normalize_name(candidate.task_id),
            _normalize_name(candidate.title),
        }
    )


def _raise_follow_up_task_api_error(exc: CRMAPIClientError) -> None:
    retryable = exc.status_code is None or exc.status_code in {408, 429} or exc.status_code >= 500
    raise WorkflowResourceResolutionError(
        "跟进任务暂时无法读取。" if retryable else exc.message,
        retryable=retryable,
    ) from exc


TNameMatched = TypeVar("TNameMatched")


def _name_matches(
    candidates: tuple[TNameMatched, ...],
    query: str,
    *,
    name: Callable[[TNameMatched], str],
) -> tuple[TNameMatched, ...]:
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return ()
    # Approximate identity is an Agent responsibility, not a resolver
    # shortcut. Exact normalized names remain a safe deterministic binding.
    return tuple(candidate for candidate in candidates if _normalize_name(name(candidate)) == normalized_query)


def _normalize_name(value: str) -> str:
    return "".join(value.split()).casefold()

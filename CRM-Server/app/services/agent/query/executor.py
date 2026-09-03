"""Public deterministic execution seam for CRM Query Agent tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.schemas.sales_commitment import FollowUpTaskDetailResponse
from app.services.agent.query.adapters import (
    CompletedWorkAPIAdapter,
    CRMQueryAdapter,
    CRMQueryAdapterResponseError,
    CustomerActivitiesAPIAdapter,
    CustomerContactsAPIAdapter,
    CustomersAPIAdapter,
    DeploymentInfosAPIAdapter,
    FollowUpTasksAPIAdapter,
)
from app.services.agent.query.registry import FollowUpTaskDetailRequest
from app.services.agent.query.catalog import CRMQueryCatalog
from app.services.agent.query.cursor import CRMQueryCursorError
from app.services.agent.query.policy import QueryPolicyError, QueryPolicyValidator
from app.services.agent.query.schemas import CRMQueryResult, CRMQuerySpec, EntityRef, GroundedFact, QueryError
from app.services.agent.tools.api_client import CRMAPIClientError, InternalCRMAPIClient

if TYPE_CHECKING:
    from app.services.agent.tools.base import AgentToolContext


class CRMQueryExecutor(Protocol):
    async def execute(
        self,
        spec: CRMQuerySpec,
        context: AgentToolContext,
    ) -> CRMQueryResult: ...


class CRMQueryExecutionError(RuntimeError):
    """Typed failure returned by the deterministic executor boundary."""

    def __init__(self, error: QueryError) -> None:
        super().__init__(error.message)
        self.error = error


class FollowUpTaskDetailAPIAdapter:
    """Read one server-authorized task through the existing detail endpoint."""

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def read(
        self,
        request: FollowUpTaskDetailRequest,
        context: AgentToolContext,
    ) -> CRMQueryResult:
        task_ref = request.task_ref
        query_id = f"qry_{uuid4().hex}"
        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/follow-up-tasks/{task_ref.public_id}",
                context.authorization,
            )
            detail = FollowUpTaskDetailResponse.model_validate(payload)
        except CRMAPIClientError as exc:
            if exc.status_code == 404:
                return CRMQueryResult(
                    query_id=query_id,
                    resource="follow_up_task",
                    status="EMPTY",
                    rows=[],
                    entity_refs=[],
                    total=0,
                )
            if exc.status_code == 403:
                raise CRMQueryExecutionError(
                    QueryError(
                        code="PERMISSION_DENIED",
                        message="无权查看该待办，或待办已不在当前权限范围内。",
                        retryable=False,
                    )
                ) from exc
            if exc.status_code == 408 or exc.status_code == 504:
                raise CRMQueryExecutionError(
                    QueryError(code="UPSTREAM_TIMEOUT", message="CRM API query timed out", retryable=True)
                ) from exc
            if exc.status_code == 429 or (exc.status_code is not None and exc.status_code >= 500):
                raise CRMQueryExecutionError(
                    QueryError(
                        code="UPSTREAM_UNAVAILABLE",
                        message="CRM API is temporarily unavailable",
                        retryable=True,
                    )
                ) from exc
            raise CRMQueryExecutionError(
                QueryError(code="INTERNAL_ERROR", message="CRM API query failed", retryable=False)
            ) from exc
        except ValidationError as exc:
            raise CRMQueryExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="CRM API returned an invalid response",
                    retryable=False,
                )
            ) from exc

        row = detail.model_dump(mode="json")
        entity_ref = EntityRef(
            ref_id=task_ref.ref_id,
            resource="follow_up_task",
            public_id=task_ref.public_id,
            display_name=detail.title,
        )
        return CRMQueryResult(
            query_id=query_id,
            resource="follow_up_task",
            status="SUCCESS",
            rows=[row],
            entity_refs=[entity_ref],
            total=1,
            facts=[
                GroundedFact(
                    fact_id=f"fact_{task_ref.public_id}",
                    label=detail.title,
                    value=row,
                    source="CRM_API",
                    source_ref=task_ref.public_id,
                    entity_ref=entity_ref,
                )
            ],
        )


class DefaultCRMQueryExecutor:
    """Validate, dispatch, and normalize CRM queries without model-side transport logic."""

    def __init__(
        self,
        *,
        api_client: InternalCRMAPIClient | None = None,
        catalog: CRMQueryCatalog | None = None,
        validator: QueryPolicyValidator | None = None,
    ) -> None:
        resolved_catalog = catalog or CRMQueryCatalog()
        client = api_client or InternalCRMAPIClient()
        self._catalog = resolved_catalog
        self._validator = validator or QueryPolicyValidator(resolved_catalog)
        self._adapters: dict[str, CRMQueryAdapter] = {
            "customers_api": CustomersAPIAdapter(client),
            "customer_contacts_api": CustomerContactsAPIAdapter(client),
            "customer_activities_api": CustomerActivitiesAPIAdapter(client),
            "deployment_infos_api": DeploymentInfosAPIAdapter(client),
            "follow_up_tasks_api": FollowUpTasksAPIAdapter(client),
            "completed_work_api": CompletedWorkAPIAdapter(client),
        }

    async def execute(
        self,
        spec: CRMQuerySpec,
        context: AgentToolContext,
    ) -> CRMQueryResult:
        try:
            validated = self._validator.validate(spec, context)
            definition = self._catalog.resolve(validated.resource)
            adapter = self._adapters.get(definition.adapter_key)
            if adapter is None:
                raise CRMQueryExecutionError(
                    QueryError(
                        code="QUERY_UNSUPPORTED",
                        message=f"query adapter is not implemented: {definition.adapter_key}",
                        retryable=False,
                    )
                )
            page = await adapter.execute(validated, context)
        except CRMQueryExecutionError:
            raise
        except QueryPolicyError as exc:
            raise CRMQueryExecutionError(exc.error) from exc
        except CRMQueryCursorError as exc:
            raise CRMQueryExecutionError(QueryError(code="QUERY_INVALID", message=str(exc), retryable=False)) from exc
        except CRMAPIClientError as exc:
            raise CRMQueryExecutionError(self._map_api_error(exc, spec)) from exc
        except httpx.TimeoutException as exc:
            raise CRMQueryExecutionError(
                QueryError(code="UPSTREAM_TIMEOUT", message="CRM API query timed out", retryable=True)
            ) from exc
        except CRMQueryAdapterResponseError as exc:
            raise CRMQueryExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="CRM API returned an invalid response",
                    retryable=False,
                )
            ) from exc
        except ValueError as exc:
            raise CRMQueryExecutionError(QueryError(code="QUERY_INVALID", message=str(exc), retryable=False)) from exc
        except Exception as exc:
            raise CRMQueryExecutionError(
                QueryError(code="INTERNAL_ERROR", message="CRM query failed", retryable=False)
            ) from exc

        status: Literal["SUCCESS", "EMPTY", "PARTIAL"] = (
            "EMPTY" if not page.rows else "PARTIAL" if page.next_cursor else "SUCCESS"
        )
        return CRMQueryResult(
            query_id=f"qry_{uuid4().hex}",
            resource=validated.resource,
            status=status,
            executed_query=validated,
            rows=page.rows,
            entity_refs=page.entity_refs,
            total=page.total,
            next_cursor=page.next_cursor,
            applied_filters=validated.filters,
            applied_sorts=validated.sorts,
            facts=page.facts,
            warnings=page.warnings,
        )

    @staticmethod
    def _map_api_error(error: CRMAPIClientError, spec: CRMQuerySpec) -> QueryError:
        if error.status_code == 403:
            return QueryError(
                code="PERMISSION_DENIED",
                message=DefaultCRMQueryExecutor._safe_api_error_message(error, "permission denied"),
                retryable=False,
            )
        if error.status_code == 404 and DefaultCRMQueryExecutor._is_exact_customer_lookup(spec):
            return QueryError(
                code="PERMISSION_DENIED",
                message="客户不存在或不在当前权限范围内",
                retryable=False,
            )
        if error.status_code in {400, 404, 422}:
            return QueryError(
                code="QUERY_INVALID",
                message=DefaultCRMQueryExecutor._safe_api_error_message(error, "invalid CRM query"),
                retryable=False,
            )
        if error.status_code == 408:
            return QueryError(code="UPSTREAM_TIMEOUT", message="CRM API query timed out", retryable=True)
        if error.status_code == 429 or (error.status_code is not None and error.status_code >= 500):
            return QueryError(
                code="UPSTREAM_UNAVAILABLE",
                message="CRM API is temporarily unavailable",
                retryable=True,
            )
        return QueryError(code="INTERNAL_ERROR", message="CRM API query failed", retryable=False)

    @staticmethod
    def _is_exact_customer_lookup(spec: CRMQuerySpec) -> bool:
        return spec.resource == "customer" and any(
            condition.field == "public_id" and condition.operator == "eq"
            for condition in spec.filters
        )

    @staticmethod
    def _safe_api_error_message(error: CRMAPIClientError, default_message: str) -> str:
        payload = error.response_json
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail
            if isinstance(detail, dict):
                nested_detail = detail.get("detail")
                if isinstance(nested_detail, str) and nested_detail.strip():
                    return nested_detail
        if isinstance(error.message, str) and error.message.strip():
            return error.message
        return default_message

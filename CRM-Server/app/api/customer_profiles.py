"""Stable tombstones for the removed customer-profile API."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1/customers", tags=["客户档案"])


def customer_profile_removed() -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={"code": "CUSTOMER_PROFILE_REMOVED", "message": "客户档案能力已移除"},
    )


@router.api_route("/{customer_public_id}/profile", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/{customer_public_id}/profile/{subpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def removed_customer_profile(customer_public_id: str, subpath: str = "") -> JSONResponse:
    del customer_public_id, subpath
    return customer_profile_removed()

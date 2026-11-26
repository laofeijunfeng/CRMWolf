"""Customer name uniqueness rule shared by the customer API and the sales assistant."""

from sqlalchemy.orm import Session

from app.crud.customer import customer_crud
from app.crud.lead import lead_crud


def customer_name_conflict_error(
    db: Session,
    account_name: str,
    team_id: int,
    exclude_customer_id: int | None = None,
    allowed_source_lead_id: int | None = None,
) -> str | None:
    existing_customer = customer_crud.get_by_name(db, account_name, team_id)
    if existing_customer and existing_customer.id != exclude_customer_id:
        return "客户名称已存在"
    existing_lead = lead_crud.get_by_name(db, account_name, team_id)
    excluded_customer = customer_crud.get_by_id(db, exclude_customer_id, team_id) if exclude_customer_id else None
    if existing_lead and existing_lead.id != allowed_source_lead_id and not (
        excluded_customer and excluded_customer.source_lead_id == existing_lead.id
    ):
        return "该名称已存在线索\uff0c请先处理或转化线索"
    return None

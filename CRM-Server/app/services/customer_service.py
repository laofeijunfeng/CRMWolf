"""Compatibility service layer for customer operations."""
from __future__ import annotations

from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.crud.customer import customer_crud
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:
    """Thin customer service wrapper around the existing CustomerCRUD."""

    @staticmethod
    def get_multi(
        db: Session,
        *,
        team_id: int = 0,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Tuple[list[Customer], int]:
        return customer_crud.get_multi(
            db,
            team_id=team_id,
            skip=skip,
            limit=limit,
            **filters,
        )

    @classmethod
    def get_list(
        cls,
        db: Session,
        *,
        team_id: int = 0,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Tuple[list[Customer], int]:
        return cls.get_multi(
            db,
            team_id=team_id,
            skip=skip,
            limit=limit,
            **filters,
        )

    @staticmethod
    def get(db: Session, customer_id: int, team_id: Optional[int] = None) -> Optional[Customer]:
        return customer_crud.get_by_id(db, customer_id, team_id)

    @classmethod
    def get_by_id(cls, db: Session, customer_id: int, team_id: Optional[int] = None) -> Customer:
        customer = cls.get(db, customer_id, team_id)
        if customer is None:
            raise NotFoundException(f"客户 {customer_id} 不存在")
        return customer

    @staticmethod
    def get_by_name(db: Session, account_name: str, team_id: Optional[int] = None) -> Optional[Customer]:
        return customer_crud.get_by_name(db, account_name, team_id)

    @staticmethod
    def create_with_owner(
        db: Session,
        obj_in: CustomerCreate,
        owner_id: str,
        *,
        team_id: int = 0,
        operator_name: Optional[str] = None,
    ) -> Customer:
        return customer_crud.create(
            db,
            obj_in,
            creator_id=owner_id,
            team_id=team_id,
            operator_name=operator_name,
        )

    @classmethod
    def create(
        cls,
        db: Session,
        obj_in: CustomerCreate,
        owner_id: str,
        *,
        team_id: int = 0,
        operator_name: Optional[str] = None,
    ) -> Customer:
        existing = cls.get_by_name(db, obj_in.account_name, team_id)
        if existing is not None:
            raise ConflictException(f"客户「{obj_in.account_name}」已存在")
        return cls.create_with_owner(
            db,
            obj_in,
            owner_id,
            team_id=team_id,
            operator_name=operator_name,
        )

    @staticmethod
    def update(db: Session, customer_id: int, obj_in: CustomerUpdate, team_id: Optional[int] = None) -> Customer:
        customer = CustomerService.get_by_id(db, customer_id, team_id)
        return customer_crud.update(db, customer, obj_in)

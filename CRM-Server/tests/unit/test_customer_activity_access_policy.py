"""Shared customer-activity authorization policy behavior."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.customer import Customer, CustomerMember
from app.services.customer_activity_access_policy import (
    CustomerActivityAccessDeniedError,
    CustomerActivityAccessPolicy,
    CustomerActivityCustomerNotFoundError,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[Customer.__table__, CustomerMember.__table__],
    )
    return engine, sessionmaker(bind=engine)()


def _seed_customer(db, *, owner_id: str = "99") -> Customer:
    customer = Customer(
        public_id="cus_activity_policy",
        team_id=1,
        account_name="上海星云科技",
        city="上海",
        owner_id=owner_id,
        creator_id="2",
    )
    db.add(customer)
    db.flush()
    return customer


def test_policy_authorizes_team_wide_editor() -> None:
    engine, db = _db_session()
    try:
        customer = _seed_customer(db)

        resolved = CustomerActivityAccessPolicy().resolve_customer(
            db,
            customer_identifier=customer.public_id,
            team_id=1,
            user_id=2,
            permission_codes=frozenset({"customer:edit:all"}),
        )

        assert resolved.id == customer.id
    finally:
        db.close()
        engine.dispose()


def test_policy_authorizes_active_follow_up_member_without_owner_permission() -> None:
    engine, db = _db_session()
    try:
        customer = _seed_customer(db)
        db.add(
            CustomerMember(
                team_id=1,
                customer_id=customer.id,
                user_id="2",
                member_role="COLLABORATOR",
                access_level="FOLLOW_UP",
                is_active=True,
                created_by="2",
            )
        )
        db.commit()

        resolved = CustomerActivityAccessPolicy().resolve_customer(
            db,
            customer_identifier=customer.public_id,
            team_id=1,
            user_id=2,
            permission_codes=frozenset(),
        )

        assert resolved.id == customer.id
    finally:
        db.close()
        engine.dispose()


def test_policy_authorizes_owner_with_activity_permission() -> None:
    engine, db = _db_session()
    try:
        customer = _seed_customer(db, owner_id="2")

        resolved = CustomerActivityAccessPolicy().resolve_customer(
            db,
            customer_identifier=customer.public_id,
            team_id=1,
            user_id=2,
            permission_codes=frozenset({"customer:activity:create"}),
        )

        assert resolved.id == customer.id
    finally:
        db.close()
        engine.dispose()


def test_policy_denies_unrelated_user() -> None:
    engine, db = _db_session()
    try:
        customer = _seed_customer(db)

        with pytest.raises(CustomerActivityAccessDeniedError):
            CustomerActivityAccessPolicy().resolve_customer(
                db,
                customer_identifier=customer.public_id,
                team_id=1,
                user_id=2,
                permission_codes=frozenset({"customer:activity:create"}),
            )
    finally:
        db.close()
        engine.dispose()


def test_policy_hides_cross_team_customer_as_not_found() -> None:
    engine, db = _db_session()
    try:
        customer = _seed_customer(db)

        with pytest.raises(CustomerActivityCustomerNotFoundError):
            CustomerActivityAccessPolicy().resolve_customer(
                db,
                customer_identifier=customer.public_id,
                team_id=2,
                user_id=2,
                permission_codes=frozenset({"customer:edit:all"}),
            )
    finally:
        db.close()
        engine.dispose()

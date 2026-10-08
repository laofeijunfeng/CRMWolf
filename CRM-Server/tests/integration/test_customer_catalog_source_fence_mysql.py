"""Customer catalog writes serialize with customer creation and updates on isolated MySQL."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.crud.customer import customer_crud
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.crud.product_intent import ProductNotFoundError
from app.crud.product import product_crud
from app.models.customer import Customer, CustomerProduct
from app.models.product import Product
from app.models.team import Team
from app.schemas.product import ProductCreate, ProductUpdate

pytestmark = pytest.mark.integration


def _isolated_mysql() -> bool:
    url = engine.url
    return (
        os.getenv("RUN_MYSQL_INTEGRATION") == "1"
        and url.host == "127.0.0.1"
        and url.port == 3308
        and url.database == "crm_assistant_acceptance"
    )


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_customer_create_waits_for_catalog_team_before_product_resolution() -> None:
    started = Event()
    finished = Event()
    result: list[Exception | None] = []

    def create_customer() -> None:
        with SessionLocal() as db:
            started.set()
            try:
                customer_crud.create(
                    db,
                    CustomerCreate(
                        account_name=f"CATALOG_FENCE_{uuid4().hex}",
                        city="深圳",
                        product_public_id="prd_accept_990126030",
                    ),
                    "990126011",
                    990126010,
                    commit=False,
                )
                result.append(None)
            except Exception as exc:
                result.append(exc)
            finally:
                db.rollback()
                finished.set()

    with SessionLocal() as locker, ThreadPoolExecutor(max_workers=1) as pool:
        assert locker.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        locker.execute(text("SELECT id FROM teams WHERE id=990126010 FOR UPDATE")).one()
        worker = pool.submit(create_customer)
        try:
            assert started.wait(3)
            assert not finished.wait(1), "customer inserted before the catalog Team lock released"
        finally:
            locker.rollback()
        worker.result(timeout=15)

    assert result == [None]

@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_customer_create_rejects_product_deactivated_after_stale_repeatable_read() -> None:
    name = f"CATALOG_RR_{uuid4().hex[:12]}"
    with SessionLocal() as seed:
        team = Team(name=name, code=uuid4().hex[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        team_id = team.id
        product = Product(
            team_id=team_id,
            public_id=f"prd_{uuid4().hex}",
            code=f"CODE_{uuid4().hex[:12]}",
            name="可停用产品",
            is_active=True,
            created_by="990126011",
        )
        seed.add(product)
        seed.commit()
        product_id = product.id
        public_id = product.public_id

    try:
        with SessionLocal() as stale, SessionLocal() as updater:
            assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
            stale_product = product_crud.get_by_public_id(stale, public_id, team_id)
            assert stale_product is not None and stale_product.is_active
            current_product = product_crud.get_by_public_id(updater, public_id, team_id)
            assert current_product is not None
            product_crud.update(updater, current_product, ProductUpdate(is_active=False), "990126011")

            with pytest.raises(ValueError, match="可用产品|启用中的产品"):
                customer_crud.create(
                    stale,
                    CustomerCreate(
                        account_name=f"{name}_CUSTOMER",
                        city="深圳",
                        product_public_id=public_id,
                    ),
                    "990126011",
                    team_id,
                    commit=False,
                )
            stale.rollback()
    finally:
        # Only rows created by this test are removed; acceptance fixtures remain untouched.
        with SessionLocal() as cleanup:
            cleanup.execute(text("DELETE FROM crm_products WHERE id=:id AND team_id=:team"), {"id": product_id, "team": team_id})
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), {"team": team_id})
            cleanup.commit()

@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_customer_create_sees_product_added_after_repeatable_read_snapshot() -> None:
    name = f"CATALOG_NEW_{uuid4().hex[:12]}"
    with SessionLocal() as seed:
        team = Team(name=name, code=uuid4().hex[:12], owner_id=990126011)
        seed.add(team)
        seed.commit()
        team_id = team.id

    product_id: int | None = None
    try:
        with SessionLocal() as stale, SessionLocal() as creator:
            assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
            assert stale.execute(text("SELECT id FROM crm_products WHERE team_id=:team"), {"team": team_id}).all() == []
            product = product_crud.create(creator, team_id, ProductCreate(name="新上架产品"), "990126011")
            product_id = product.id

            customer = customer_crud.create(
                stale,
                CustomerCreate(account_name=f"{name}_CUSTOMER", city="深圳", product_public_id=product.public_id),
                "990126011", team_id, commit=False,
            )
            assert customer.product_links[0].product_id == product.id
            stale.rollback()
    finally:
        with SessionLocal() as cleanup:
            if product_id is not None:
                cleanup.execute(text("DELETE FROM crm_product_modules WHERE product_id=:id AND team_id=:team"), {"id": product_id, "team": team_id})
                cleanup.execute(text("DELETE FROM crm_products WHERE id=:id AND team_id=:team"), {"id": product_id, "team": team_id})
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), {"team": team_id})
            cleanup.commit()

@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_customer_product_update_takes_team_lock_before_customer_row() -> None:
    started = Event()
    finished = Event()
    result: list[Exception] = []

    def update_customer() -> None:
        with SessionLocal() as db:
            customer = customer_crud.get_by_id(db, 990126020, 990126010)
            assert customer is not None
            started.set()
            try:
                customer_crud.update_with_audit(
                    db, customer, CustomerUpdate(product_public_id="prd_probe_absent"),
                )
            except Exception as exc:
                result.append(exc)
            finally:
                db.rollback()
                finished.set()

    with SessionLocal() as locker, ThreadPoolExecutor(max_workers=1) as pool:
        locker.execute(text("SELECT id FROM teams WHERE id=990126010 FOR UPDATE")).one()
        worker = pool.submit(update_customer)
        try:
            assert started.wait(3)
            assert not finished.wait(1), "customer product update bypassed catalog Team fence"
        finally:
            locker.rollback()
        worker.result(timeout=15)

    assert len(result) == 1 and isinstance(result[0], ProductNotFoundError)


@pytest.mark.parametrize("catalog_edit", ["deactivate", "delete"])
@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_customer_product_update_rejects_catalog_edit_after_stale_repeatable_read(catalog_edit: str) -> None:
    name = f"CATALOG_UPDATE_RR_{uuid4().hex[:12]}"
    actor_id = "990126011"
    with SessionLocal() as seed:
        team = Team(name=name, code=uuid4().hex[:12], owner_id=int(actor_id))
        seed.add(team)
        seed.commit()
        team_id = team.id
        original = product_crud.create(seed, team_id, ProductCreate(name="原意向产品"), actor_id)
        target = product_crud.create(seed, team_id, ProductCreate(name="待变更产品"), actor_id)
        original_id, target_id = original.id, target.id
        target_public_id = target.public_id
        customer = Customer(
            team_id=team_id, account_name=f"{name}_CUSTOMER", city="深圳", creator_id=actor_id,
        )
        seed.add(customer)
        seed.flush()
        customer_id = customer.id
        seed.add(CustomerProduct(customer_id=customer_id, product_id=original_id, team_id=team_id))
        seed.commit()

    snapshot_ready = Event()
    begin_update = Event()
    invoking_update = Event()
    finished = Event()

    def update_customer() -> ValueError | None:
        with SessionLocal() as stale:
            try:
                assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
                loaded_customer = customer_crud.get_by_id(stale, customer_id, team_id)
                assert loaded_customer is not None
                assert [link.product_id for link in loaded_customer.product_links] == [original_id]
                loaded_target = product_crud.get_by_public_id(stale, target_public_id, team_id)
                assert loaded_target is not None and loaded_target.is_active
                snapshot_ready.set()
                assert begin_update.wait(10)
                invoking_update.set()
                try:
                    customer_crud.update_with_audit(
                        stale, loaded_customer, CustomerUpdate(product_public_id=target_public_id),
                    )
                except ValueError as exc:
                    return exc
                return None
            finally:
                stale.rollback()
                finished.set()

    try:
        with SessionLocal() as editor, ThreadPoolExecutor(max_workers=1) as pool:
            editor.execute(text("SELECT id FROM teams WHERE id=:team FOR UPDATE"), {"team": team_id}).one()
            worker = pool.submit(update_customer)
            try:
                assert snapshot_ready.wait(5), "customer session did not establish its stale RR snapshot"
                begin_update.set()
                assert invoking_update.wait(5)
                assert not finished.wait(1), "customer update bypassed the catalog Team fence"
                current_target = product_crud.get_by_public_id(editor, target_public_id, team_id)
                assert current_target is not None
                if catalog_edit == "deactivate":
                    product_crud.update(editor, current_target, ProductUpdate(is_active=False), actor_id)
                else:
                    product_crud.delete(editor, current_target)
            finally:
                editor.rollback()  # Product CRUD commits its edit; release the fence on setup failure too.
            error = worker.result(timeout=15)

        if catalog_edit == "deactivate":
            assert isinstance(error, ValueError) and "启用中的产品" in str(error)
        else:
            assert isinstance(error, ProductNotFoundError)

        with SessionLocal() as observed:
            product_state = observed.execute(
                text("SELECT is_active FROM crm_products WHERE team_id=:team AND id=:product"),
                {"team": team_id, "product": target_id},
            ).scalar_one_or_none()
            assert product_state == (0 if catalog_edit == "deactivate" else None)
            assert observed.execute(
                text("SELECT product_id FROM crm_customer_products WHERE team_id=:team AND customer_id=:customer"),
                {"team": team_id, "customer": customer_id},
            ).scalars().all() == [original_id]
            progress = observed.execute(
                text("SELECT eligible_revision, deletion_revision FROM crm_customer_legacy_source_progress "
                     "WHERE team_id=:team AND customer_id=:customer"),
                {"team": team_id, "customer": customer_id},
            ).one()
            assert tuple(progress) == (1, int(catalog_edit == "delete"))
    finally:
        with SessionLocal() as cleanup:
            owned = {"team": team_id, "customer": customer_id, "original": original_id, "target": target_id}
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress "
                                 "WHERE team_id=:team AND customer_id=:customer"), owned)
            cleanup.execute(text("DELETE FROM crm_customer_products "
                                 "WHERE team_id=:team AND customer_id=:customer"), owned)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), owned)
            cleanup.execute(text("DELETE FROM crm_product_modules "
                                 "WHERE team_id=:team AND product_id IN (:original, :target)"), owned)
            cleanup.execute(text("DELETE FROM crm_products "
                                 "WHERE team_id=:team AND id IN (:original, :target)"), owned)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), owned)
            cleanup.commit()

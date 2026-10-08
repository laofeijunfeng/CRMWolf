"""Opportunity product binding uses current catalog state under its Team fence."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.crud.opportunity import opportunity_crud
from app.crud.product import product_crud
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.opportunity import Opportunity
from app.models.team import Team
from app.schemas.product import ProductCreate, ProductModuleCreate, ProductModuleUpdate, ProductUpdate

pytestmark = pytest.mark.integration

def _isolated_mysql() -> bool:
    url = engine.url
    return (
        os.getenv("RUN_MYSQL_INTEGRATION") == "1"
        and url.drivername == "mysql+pymysql"
        and url.username == "root"
        and url.password == "assistant-test-only"
        and url.host == "127.0.0.1"
        and url.port == 3308
        and url.database == "crm_assistant_acceptance"
    )


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
@pytest.mark.parametrize("deactivated", ["product", "module"])
def test_stale_catalog_identity_cannot_assign_deactivated_product_or_module(deactivated: str) -> None:
    suffix = uuid4().hex
    actor_id = "990126011"
    with SessionLocal() as seed:
        team = Team(name=f"OPP_CATALOG_{suffix[:12]}", code=suffix[:12], owner_id=int(actor_id))
        seed.add(team)
        seed.commit()
        team_id = int(team.id)
        product = product_crud.create(seed, team_id, ProductCreate(name="当前可用产品"), actor_id)
        product_id, product_public_id = int(product.id), str(product.public_id)
        module = product_crud.create_module(seed, product, ProductModuleCreate(name="扩展模块"), actor_id)
        module_id, module_public_id = int(module.id), str(module.public_id)
        customer = Customer(team_id=team_id, account_name=f"客户 {suffix}", city="深圳", creator_id=actor_id)
        seed.add(customer)
        seed.flush()
        opportunity = Opportunity(
            team_id=team_id, opportunity_number=f"OPP{suffix[:32]}", opportunity_name=f"商机 {suffix}",
            customer_id=customer.id, total_amount=Decimal("100.00"), user_count=1,
            unit_price=Decimal("100.00"), license_type="PERPETUAL", purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31), owner_id=actor_id, creator_id=actor_id,
        )
        seed.add(opportunity)
        seed.commit()
        customer_id, opportunity_id = int(customer.id), int(opportunity.id)

    try:
        with SessionLocal() as stale, SessionLocal() as editor:
            assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
            old_opportunity = stale.query(Opportunity).filter_by(id=opportunity_id, team_id=team_id).one()
            old_product = product_crud.get_by_public_id(stale, product_public_id, team_id)
            old_module = product_crud.get_module_by_public_id(stale, module_public_id, team_id, product_id)
            assert old_product is not None and old_product.is_active
            assert old_module is not None and old_module.is_active

            if deactivated == "product":
                current_product = product_crud.get_by_public_id(editor, product_public_id, team_id)
                assert current_product is not None
                product_crud.update(editor, current_product, ProductUpdate(is_active=False), actor_id)
            else:
                current_module = product_crud.get_module_by_public_id(editor, module_public_id, team_id, product_id)
                assert current_module is not None
                product_crud.update_module(
                    editor, current_module, ProductModuleUpdate(is_active=False), actor_id,
                )
            with SessionLocal() as observed:
                before = observed.query(CustomerLegacySourceProgress).filter_by(
                    team_id=team_id, customer_id=customer_id,
                ).one_or_none()
                revision_before = int(before.eligible_revision) if before is not None else 0

            with pytest.raises(ValueError, match="产品不存在|产品模块已停用"):
                opportunity_crud.assign_product(
                    stale, old_opportunity, team_id=team_id,
                    product_public_id=product_public_id, module_public_ids=[module_public_id],
                )
            stale.rollback()

        with SessionLocal() as observed:
            saved = observed.query(Opportunity).filter_by(id=opportunity_id, team_id=team_id).one()
            assert saved.product_id is None
            assert saved.module_links == []
            progress = observed.query(CustomerLegacySourceProgress).filter_by(
                team_id=team_id, customer_id=customer_id,
            ).one_or_none()
            assert (int(progress.eligible_revision) if progress is not None else 0) == revision_before
    finally:
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "opportunity": opportunity_id,
                      "product": product_id, "module": module_id}
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_opportunity_product_modules WHERE team_id=:team AND opportunity_id=:opportunity"), params)
            cleanup.execute(text("DELETE FROM crm_opportunities WHERE team_id=:team AND id=:opportunity"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_product_modules WHERE team_id=:team AND product_id=:product"), params)
            cleanup.execute(text("DELETE FROM crm_products WHERE team_id=:team AND id=:product"), params)
            cleanup.commit()

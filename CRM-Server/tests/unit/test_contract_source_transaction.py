"""Contract creation's post-commit file transactions retain legacy source progress."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from app.api import contracts as contracts_api
from app.core.database import Base
from app.models.approval import Approval
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.invoice import InvoiceApplication
from app.models.license_application import LicenseApplication
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.file_storage import FileStorageError
from app.services.legacy_profile_source import advance_eligible_progress
from tests.unit.test_customer_intelligence_context_service import _seed_customer_context, _session


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kwargs):
    return "INTEGER"


class _Upload:
    filename = "contract.pdf"
    content_type = "application/pdf"

    async def read(self):
        return b"contract"


class _Request(SimpleNamespace):
    def model_copy(self, *, update):
        return _Request(**{**vars(self), **update})


def _watermark(db):
    customer = db.query(Customer).filter_by(id=101, team_id=2).one()
    return CustomerIntelligenceContextService()._build_strong_context(
        db, customer=customer, team_id=2,
    ).source_watermarks


@pytest.mark.asyncio
@pytest.mark.parametrize("from_opportunity", [False, True], ids=["manual", "won-opportunity"])
@pytest.mark.parametrize("storage_failure", [False, True], ids=["stored", "storage-error"])
async def test_contract_file_second_transaction_fences_source(
    monkeypatch, from_opportunity, storage_failure,
):
    engine, db = _session()
    try:
        Base.metadata.create_all(engine, tables=[
            InvoiceApplication.__table__, LicenseApplication.__table__, Approval.__table__,
        ])
        _seed_customer_context(db)
        db.add_all([
            Customer(id=202, team_id=3, account_name="其他团队", city="北京", creator_id="19"),
            CustomerLegacySourceProgress(
                team_id=3, customer_id=202, eligible_revision=11, deletion_revision=4,
            ),
        ])
        db.commit()
        before = _watermark(db)
        after_create = []
        # Use an actual committed contract/progress pair rather than the CRUD's
        # independent contract-number and operation-log dependencies.
        def create_contract(**kwargs):
            row = Contract(
                id=402, team_id=2, customer_id=101, opportunity_id=301,
                contract_number="HT-002", contract_name="新合同", user_count=10,
                total_amount=Decimal("1000"), license_type="SUBSCRIPTION",
                subscription_years=1, standard_unit_price=Decimal("100"),
                signing_contact_id=201,
                owner_id="9", creator_id="9",
            )
            db.add(row)
            advance_eligible_progress(db, team_id=2, customer_id=101)
            db.commit()
            db.refresh(row)
            return row

        def save_file(**kwargs):
            after_create.append(_watermark(db))
            if storage_failure:
                raise FileStorageError("文件保存失败")
            return "contracts/2/402/contract.pdf"

        monkeypatch.setattr(contracts_api.contract_crud, "create", create_contract)
        monkeypatch.setattr(contracts_api.contract_crud, "create_from_opportunity", create_contract)
        monkeypatch.setattr(contracts_api.file_storage_service, "save_contract_file", save_file)
        monkeypatch.setattr(
            contracts_api, "_get_opportunity_by_public_id_or_404",
            lambda db, opportunity_id, team_id: SimpleNamespace(id=301, customer_id=101, status=1),
        )
        monkeypatch.setattr(
            contracts_api, "check_customer_edit_permission",
            lambda customer_id, team_id, current_user, db: SimpleNamespace(id=101),
        )
        monkeypatch.setattr(
            contracts_api.contact_crud, "get_by_id",
            lambda db, contact_id, team_id: SimpleNamespace(customer_id=101),
        )
        monkeypatch.setattr(
            contracts_api, "_parse_contract_payload",
            lambda payload: _Request(customer_id=101, opportunity_id="opp_301", signing_contact_id=201),
        )
        monkeypatch.setattr(contracts_api.ApprovalService, "submit_for_approval", lambda db, id: None)

        async def ignore_refresh(db, change):
            pass

        monkeypatch.setattr(contracts_api, "_trigger_contract_intelligence_refresh", ignore_refresh)
        route_kwargs = dict(file=_Upload(), team_id=2, current_user=SimpleNamespace(id=9), db=db)
        if from_opportunity:
            route = contracts_api.create_contract_from_opportunity
            route_kwargs.update(opportunity_id="opp_301", contract_name="新合同", signing_contact_id=201)
        else:
            route = contracts_api.create_contract
            route_kwargs.update(contract_payload="{}")

        if storage_failure:
            with pytest.raises(contracts_api.HTTPException) as exc:
                await route(**route_kwargs)
            assert exc.value.status_code == 400
            assert exc.value.detail == "文件保存失败"
        else:
            result = await route(**route_kwargs)
            assert result.id == 402

        assert len(after_create) == 1
        assert after_create[0]["eligible_revision"] == before["eligible_revision"] + 1
        assert after_create[0]["source_snapshot_hash"] != before["source_snapshot_hash"]
        db.expire_all()
        row = db.query(Contract).filter_by(id=402, team_id=2).one_or_none()
        after = _watermark(db)
        assert after["eligible_revision"] == before["eligible_revision"] + 2
        if storage_failure:
            assert row is None
            assert after["deletion_revision"] == before["deletion_revision"] + 1
            assert after["source_snapshot_hash"] == before["source_snapshot_hash"]
        else:
            assert row.contract_file_path == "contracts/2/402/contract.pdf"
            assert row.contract_file_name == "contract.pdf"
            assert row.contract_file_size == len(b"contract")
            assert after["deletion_revision"] == before["deletion_revision"]
            assert after["source_snapshot_hash"] != after_create[0]["source_snapshot_hash"]
        other_team = db.query(CustomerLegacySourceProgress).filter_by(team_id=3, customer_id=202).one()
        assert (other_team.eligible_revision, other_team.deletion_revision) == (11, 4)
    finally:
        db.close()
        engine.dispose()

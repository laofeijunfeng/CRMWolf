from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.contract import ContractInternalCreate, LicenseTypeEnum
from app.schemas.deployment import DeploymentInfoInternalCreate
from app.schemas.license_application import LicenseApplicationInternalCreate, LicenseType


def test_internal_create_schemas_accept_integer_foreign_keys():
    license_input = LicenseApplicationInternalCreate(
        customer_id=230,
        deployment_info_id=50,
        contract_id=74,
        license_type=LicenseType.OFFICIAL,
        authorized_users=10,
        expiry_date=date(2027, 12, 31),
    )
    deployment_input = DeploymentInfoInternalCreate(
        customer_id=230,
        deployment_name="生产环境",
        server_address="https://crm.example.com",
    )
    contract_input = ContractInternalCreate(
        customer_id=230,
        opportunity_id=301,
        signing_contact_id=201,
        contract_name="企业版采购合同",
        user_count=10,
        total_amount=Decimal("1000"),
        license_type=LicenseTypeEnum.SUBSCRIPTION,
        subscription_years=1,
    )

    assert license_input.customer_id == 230
    assert deployment_input.customer_id == 230
    assert contract_input.customer_id == 230
    assert contract_input.opportunity_id == 301


@pytest.mark.parametrize(
    "model, payload",
    [
        (
            LicenseApplicationInternalCreate,
            {
                "customer_id": "cus_230",
                "deployment_info_id": 50,
                "contract_id": 74,
                "license_type": LicenseType.OFFICIAL,
                "authorized_users": 10,
                "expiry_date": date(2027, 12, 31),
            },
        ),
        (
            DeploymentInfoInternalCreate,
            {
                "customer_id": "cus_230",
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
            },
        ),
        (
            ContractInternalCreate,
            {
                "customer_id": "cus_230",
                "opportunity_id": "opp_301",
                "signing_contact_id": 201,
                "contract_name": "企业版采购合同",
                "user_count": 10,
                "total_amount": Decimal("1000"),
                "license_type": LicenseTypeEnum.SUBSCRIPTION,
                "subscription_years": 1,
            },
        ),
    ]
)
def test_internal_create_schemas_reject_public_foreign_keys(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_internal_license_schema_preserves_official_contract_validation():
    with pytest.raises(ValidationError, match="正式版 License 必须关联合同"):
        LicenseApplicationInternalCreate(
            customer_id=230,
            license_type=LicenseType.OFFICIAL,
            authorized_users=10,
            expiry_date=date(2027, 12, 31),
        )


def test_internal_deployment_schema_preserves_existing_validators():
    with pytest.raises(ValidationError, match="部署名称不能为空"):
        DeploymentInfoInternalCreate(
            customer_id=230,
            deployment_name="   ",
            server_address="https://crm.example.com",
        )

    with pytest.raises(ValidationError, match="服务器地址必须以 http:// 或 https:// 开头"):
        DeploymentInfoInternalCreate(
            customer_id=230,
            deployment_name="生产环境",
            server_address="crm.example.com",
        )


def test_internal_contract_schema_preserves_existing_validators():
    with pytest.raises(ValidationError, match="合同名称不能为空"):
        ContractInternalCreate(
            customer_id=230,
            opportunity_id=301,
            signing_contact_id=201,
            contract_name="   ",
            user_count=10,
            total_amount=Decimal("1000"),
            license_type=LicenseTypeEnum.PERPETUAL,
        )

    with pytest.raises(ValidationError, match="订阅制下订阅年限必须大于0"):
        ContractInternalCreate(
            customer_id=230,
            opportunity_id=301,
            signing_contact_id=201,
            contract_name="企业版采购合同",
            user_count=10,
            total_amount=Decimal("1000"),
            license_type=LicenseTypeEnum.SUBSCRIPTION,
            subscription_years=None,
        )

"""License 文档导出服务测试"""
from datetime import date
from pathlib import Path

from docx import Document

from app.models.customer import Customer
from app.models.deployment import DeploymentInfo
from app.models.license_application import LicenseApplication, LicenseType
from app.services.license_export_service import export_license_document


def test_export_license_document_omits_enterprise_id_line():
    customer = Customer(account_name="测试客户")
    deployment_info = DeploymentInfo(
        authorized_users=50,
        server_address="https://license.example.com",
    )
    application = LicenseApplication(
        customer=customer,
        deployment_info=deployment_info,
        authorized_users=80,
        expiry_date=date(2026, 12, 31),
        license_type=LicenseType.TRIAL,
        enterprise_id="15739",
        supported_modules="desktop,web,branch",
        server_license_code="server-license-code",
        client_license_code="client-license-code",
    )

    file_path = export_license_document(application)
    try:
        paragraph_text = "\n".join(
            paragraph.text for paragraph in Document(file_path).paragraphs
        )
    finally:
        Path(file_path).unlink(missing_ok=True)

    assert "企业名称: 测试客户" in paragraph_text
    assert "授权人数: 80" in paragraph_text
    assert "试用 License（80人）" in paragraph_text
    assert "企业编号" not in paragraph_text
    assert "15739" not in paragraph_text



def _export_title(product_name: str | None) -> str:
    application = LicenseApplication(
        customer=Customer(account_name="测试客户"),
        authorized_users=10,
        expiry_date=date(2027, 12, 31),
        license_type=LicenseType.TRIAL,
        product_name=product_name,
    )
    file_path = export_license_document(application)
    try:
        return Document(file_path).paragraphs[0].text
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_export_title_uses_application_product_name():
    assert _export_title("IDP 平台") == "IDP 平台私有化授权文件"


def test_export_title_without_product_is_generic():
    assert _export_title(None) == "私有化授权文件"
    assert _export_title("   ") == "私有化授权文件"
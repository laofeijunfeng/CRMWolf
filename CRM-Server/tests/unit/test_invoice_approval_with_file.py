"""发票审批文件上传端到端测试（Task 8）。

测试覆盖：
1. 文件存储服务（FileStorageService）
2. 发票适配器 on_approved_with_file 方法
3. 完整审批+文件上传流程
4. 可选发票号码处理
5. 路径安全校验
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime

from app.services.file_storage import FileStorageService, FileStorageError, ALLOWED_EXTENSIONS
from app.services.approval_adapter import get_adapter, InvoiceApplicationAdapter
from app.constants.business_types import BusinessType
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_upload_dir():
    """临时上传目录，测试后自动清理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def storage_service(temp_upload_dir):
    """使用临时目录的存储服务"""
    return FileStorageService(base_dir=temp_upload_dir)


@pytest.fixture
def db_session():
    """最小 Mock 会话；on_* 仅改实体属性，不真正访问 DB。"""
    return Mock()


@pytest.fixture
def invoice_pending():
    """提供一个内存中的 PENDING_REVIEW 发票申请（不持久化）"""
    invoice = InvoiceApplication()
    invoice.id = 100
    invoice.team_id = 1
    invoice.status = InvoiceApplicationStatus.PENDING_REVIEW
    invoice.applicant_id = "ou_test_user"
    invoice.invoice_amount = 10000.00
    invoice.invoice_type = "VAT_SPECIAL"
    invoice.application_number = "INV-2024-001"
    invoice.invoice_file_path = None
    invoice.invoice_number = None
    invoice.issued_time = None
    invoice.reviewed_time = None
    return invoice


# =============================================================================
# Task 1: FileStorageService 基础测试
# =============================================================================

class TestFileStorageServiceBasics:
    """文件存储服务基础功能测试"""

    def test_save_invoice_file_success(self, storage_service, temp_upload_dir):
        """测试成功保存发票文件"""
        file_content = b"test invoice pdf content"
        filename = "INV-001.pdf"

        relative_path = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename=filename,
            content=file_content
        )

        # 验证返回路径格式
        assert relative_path.startswith("invoices/1/100/")
        assert "/100_" in relative_path
        assert relative_path.endswith(".pdf")

        # 验证文件实际存在
        full_path = os.path.join(temp_upload_dir, relative_path)
        assert os.path.exists(full_path)

        # 验证内容正确
        with open(full_path, "rb") as f:
            assert f.read() == file_content

    def test_save_invoice_file_all_allowed_extensions(self, storage_service, temp_upload_dir):
        """测试所有允许的扩展名"""
        for ext in ALLOWED_EXTENSIONS:
            filename = f"test{ext}"
            content = b"test content"

            relative_path = storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename=filename,
                content=content
            )

            assert relative_path.endswith(ext)

    def test_save_invoice_file_max_size(self, storage_service):
        """测试文件大小限制（10MB）"""
        # 10MB + 1 字节
        oversized_content = b"x" * (10 * 1024 * 1024 + 1)

        with pytest.raises(FileStorageError) as exc_info:
            storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename="large.pdf",
                content=oversized_content
            )

        assert "文件过大" in str(exc_info.value)

    def test_save_invoice_file_exact_max_size(self, storage_service, temp_upload_dir):
        """测试正好 10MB 的文件可以上传"""
        # 正好 10MB
        exact_max_content = b"x" * (10 * 1024 * 1024)

        relative_path = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename="exact_max.pdf",
            content=exact_max_content
        )

        full_path = os.path.join(temp_upload_dir, relative_path)
        assert os.path.exists(full_path)


# =============================================================================
# Task 1: 文件安全校验
# =============================================================================

class TestFileStorageSecurity:
    """文件存储安全校验测试"""

    def test_path_traversal_blocked_double_dot(self, storage_service):
        """测试路径穿越攻击（../）被阻止"""
        with pytest.raises(FileStorageError) as exc_info:
            storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename="../../../etc/passwd",
                content=b"malicious"
            )
        assert "非法文件名" in str(exc_info.value)

    def test_path_traversal_blocked_slash(self, storage_service):
        """测试路径穿越攻击（/）被阻止"""
        with pytest.raises(FileStorageError) as exc_info:
            storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename="/etc/passwd",
                content=b"malicious"
            )
        assert "非法文件名" in str(exc_info.value)

    def test_path_traversal_blocked_backslash(self, storage_service):
        """测试路径穿越攻击（\\）被阻止"""
        with pytest.raises(FileStorageError) as exc_info:
            storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename="..\\..\\windows\\system32",
                content=b"malicious"
            )
        assert "非法文件名" in str(exc_info.value)

    def test_invalid_extension_exe(self, storage_service):
        """测试可执行文件扩展名被拒绝"""
        with pytest.raises(FileStorageError) as exc_info:
            storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename="virus.exe",
                content=b"malicious"
            )
        assert "不允许的文件类型" in str(exc_info.value)

    def test_invalid_extension_script(self, storage_service):
        """测试脚本文件扩展名被拒绝"""
        with pytest.raises(FileStorageError) as exc_info:
            storage_service.save_invoice_file(
                team_id=1,
                invoice_id=100,
                filename="script.sh",
                content=b"malicious"
            )
        assert "不允许的文件类型" in str(exc_info.value)

    def test_get_full_path_traversal_blocked(self, storage_service):
        """测试 get_full_path 阻止路径穿越"""
        with pytest.raises(FileStorageError):
            storage_service.get_full_path("../../etc/passwd")


# =============================================================================
# Task 3: InvoiceApplicationAdapter.on_approved_with_file
# =============================================================================

class TestInvoiceAdapterOnApprovedWithFile:
    """发票适配器 on_approved_with_file 方法测试"""

    def test_on_approved_with_file_basic(self, db_session, invoice_pending):
        """测试基本审批通过+文件上传"""
        adapter = get_adapter(BusinessType.INVOICE)
        file_path = "invoices/1/100/100_20240704_abc123.pdf"

        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice_pending,
            file_path=file_path,
            invoice_number="INV-001"
        )

        # 验证状态变化
        assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
        assert invoice_pending.invoice_file_path == file_path
        assert invoice_pending.invoice_number == "INV-001"

    def test_on_approved_with_file_optional_invoice_number(self, db_session, invoice_pending):
        """测试发票号码可选"""
        adapter = get_adapter(BusinessType.INVOICE)
        file_path = "invoices/1/100/100_20240704_abc123.pdf"

        # 不传发票号码
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice_pending,
            file_path=file_path,
            invoice_number=None
        )

        assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
        assert invoice_pending.invoice_file_path == file_path
        assert invoice_pending.invoice_number is None

    def test_on_approved_with_file_empty_invoice_number(self, db_session, invoice_pending):
        """测试空字符串发票号码"""
        adapter = get_adapter(BusinessType.INVOICE)
        file_path = "invoices/1/100/100_20240704_abc123.pdf"

        # 空字符串
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice_pending,
            file_path=file_path,
            invoice_number=""
        )

        assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
        assert invoice_pending.invoice_file_path == file_path
        # 空字符串也应该被正确设置
        assert invoice_pending.invoice_number == ""

    def test_on_approved_with_file_none_entity(self, db_session):
        """测试 E4 守卫：entity=None 时不抛异常"""
        adapter = get_adapter(BusinessType.INVOICE)

        # 不应抛异常
        adapter.on_approved_with_file(
            db=db_session,
            entity=None,
            file_path="test.pdf",
            invoice_number="INV-001"
        )

    def test_on_approved_with_file_various_file_types(self, db_session, invoice_pending):
        """测试各种允许的文件类型"""
        adapter = get_adapter(BusinessType.INVOICE)

        for ext in [".pdf", ".jpg", ".jpeg", ".png", ".ofd"]:
            invoice_pending.status = InvoiceApplicationStatus.PENDING_REVIEW
            invoice_pending.invoice_file_path = None

            file_path = f"invoices/1/100/100_20240704_test{ext}"

            adapter.on_approved_with_file(
                db=db_session,
                entity=invoice_pending,
                file_path=file_path,
                invoice_number=f"INV-{ext}"
            )

            assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
            assert invoice_pending.invoice_file_path == file_path


# =============================================================================
# 端到端测试：完整审批+文件上传流程
# =============================================================================

class TestEndToEndApprovalWithFile:
    """端到端测试：完整审批+文件上传流程"""

    def test_complete_flow_save_and_adapter_callback(
        self, storage_service, temp_upload_dir, db_session, invoice_pending
    ):
        """测试完整流程：保存文件 -> 适配器回调 -> 状态变更"""
        # 1. 模拟上传文件
        file_content = b"test invoice pdf content"
        filename = "INV-001.pdf"

        file_path = storage_service.save_invoice_file(
            team_id=invoice_pending.team_id,
            invoice_id=invoice_pending.id,
            filename=filename,
            content=file_content
        )

        # 2. 验证文件已保存
        assert storage_service.file_exists(file_path)

        # 3. 模拟适配器回调
        adapter = get_adapter(BusinessType.INVOICE)
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice_pending,
            file_path=file_path,
            invoice_number="INV-001"
        )

        # 4. 验证状态变化
        assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
        assert invoice_pending.invoice_file_path == file_path
        assert invoice_pending.invoice_number == "INV-001"

        # 5. 验证文件仍存在
        assert storage_service.file_exists(invoice_pending.invoice_file_path)

    def test_complete_flow_team_isolation(self, storage_service, db_session):
        """测试团队隔离：不同团队的发票文件不互相影响"""
        # 团队 1 的发票
        invoice1 = InvoiceApplication()
        invoice1.id = 101
        invoice1.team_id = 1
        invoice1.status = InvoiceApplicationStatus.PENDING_REVIEW
        invoice1.applicant_id = "ou_user1"
        invoice1.invoice_amount = 5000.00
        invoice1.invoice_type = "VAT_SPECIAL"
        invoice1.application_number = "INV-2024-001"

        # 团队 2 的发票
        invoice2 = InvoiceApplication()
        invoice2.id = 102
        invoice2.team_id = 2
        invoice2.status = InvoiceApplicationStatus.PENDING_REVIEW
        invoice2.applicant_id = "ou_user2"
        invoice2.invoice_amount = 8000.00
        invoice2.invoice_type = "VAT_NORMAL"
        invoice2.application_number = "INV-2024-002"

        # 保存文件
        file_path1 = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=101,
            filename="invoice1.pdf",
            content=b"team1 invoice"
        )

        file_path2 = storage_service.save_invoice_file(
            team_id=2,
            invoice_id=102,
            filename="invoice2.pdf",
            content=b"team2 invoice"
        )

        # 验证路径在不同目录
        assert file_path1.startswith("invoices/1/")
        assert file_path2.startswith("invoices/2/")

        # 适配器回调
        adapter = get_adapter(BusinessType.INVOICE)
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice1,
            file_path=file_path1,
            invoice_number="INV-TEAM1"
        )
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice2,
            file_path=file_path2,
            invoice_number="INV-TEAM2"
        )

        # 验证各自的状态
        assert invoice1.status == InvoiceApplicationStatus.ISSUED
        assert invoice1.invoice_file_path.startswith("invoices/1/")

        assert invoice2.status == InvoiceApplicationStatus.ISSUED
        assert invoice2.invoice_file_path.startswith("invoices/2/")

    def test_complete_flow_without_invoice_number(
        self, storage_service, db_session, invoice_pending
    ):
        """测试完整流程：不填发票号码（财务可从文件中查看）"""
        # 保存文件
        file_path = storage_service.save_invoice_file(
            team_id=invoice_pending.team_id,
            invoice_id=invoice_pending.id,
            filename="scanned_invoice.pdf",
            content=b"scanned content"
        )

        # 适配器回调（不传发票号码）
        adapter = get_adapter(BusinessType.INVOICE)
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice_pending,
            file_path=file_path,
            invoice_number=None
        )

        # 验证状态已变更，但发票号码为空
        assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
        assert invoice_pending.invoice_file_path == file_path
        assert invoice_pending.invoice_number is None


# =============================================================================
# 边界情况测试
# =============================================================================

class TestEdgeCases:
    """边界情况测试"""

    def test_file_exists_method(self, storage_service, temp_upload_dir):
        """测试 file_exists 方法"""
        # 文件不存在时返回 False
        assert not storage_service.file_exists("nonexistent/file.pdf")

        # 保存文件
        file_path = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename="test.pdf",
            content=b"content"
        )

        # 文件存在时返回 True
        assert storage_service.file_exists(file_path)

    def test_delete_file_method(self, storage_service, temp_upload_dir):
        """测试 delete_file 方法"""
        # 保存文件
        file_path = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename="test.pdf",
            content=b"content"
        )

        # 文件存在
        assert storage_service.file_exists(file_path)

        # 删除文件
        result = storage_service.delete_file(file_path)
        assert result is True

        # 文件已不存在
        assert not storage_service.file_exists(file_path)

        # 再次删除返回 False
        result = storage_service.delete_file(file_path)
        assert result is False

    def test_delete_file_path_traversal_blocked(self, storage_service):
        """测试 delete_file 阻止路径穿越"""
        result = storage_service.delete_file("../../etc/passwd")
        assert result is False

    def test_adapter_on_approved_vs_on_approved_with_file(self, db_session, invoice_pending):
        """测试 on_approved 和 on_approved_with_file 的区别

        on_approved: 状态变为 APPROVED，无文件路径
        on_approved_with_file: 状态变为 ISSUED，有文件路径
        """
        adapter = get_adapter(BusinessType.INVOICE)

        # on_approved -> APPROVED
        invoice_pending.status = InvoiceApplicationStatus.PENDING_REVIEW
        adapter.on_approved(db_session, invoice_pending)
        assert invoice_pending.status == InvoiceApplicationStatus.APPROVED
        assert invoice_pending.invoice_file_path is None
        assert invoice_pending.issued_time is None

        # 重置
        invoice_pending.status = InvoiceApplicationStatus.PENDING_REVIEW

        # on_approved_with_file -> ISSUED
        adapter.on_approved_with_file(
            db=db_session,
            entity=invoice_pending,
            file_path="test.pdf",
            invoice_number="INV-001"
        )
        assert invoice_pending.status == InvoiceApplicationStatus.ISSUED
        assert invoice_pending.invoice_file_path == "test.pdf"
        # 注意：issued_time 和 reviewed_time 使用 func.now()，
        # 在 mock 环境下不会真正设置值

    def test_adapter_get_name(self, invoice_pending):
        """测试 get_name 方法返回正确的展示名"""
        adapter = get_adapter(BusinessType.INVOICE)
        name = adapter.get_name(invoice_pending)
        assert name == "发票申请#100"

    def test_adapter_get_submitter(self, invoice_pending):
        """测试 get_submitter 方法"""
        adapter = get_adapter(BusinessType.INVOICE)
        submitter_id, submitter_name = adapter.get_submitter(invoice_pending)
        assert submitter_id == "ou_test_user"
        assert submitter_name is None  # InvoiceApplication 无 applicant_name 列

    def test_adapter_match_kwargs(self, invoice_pending):
        """测试 match_kwargs 方法"""
        adapter = get_adapter(BusinessType.INVOICE)
        kwargs = adapter.match_kwargs(invoice_pending)
        assert kwargs["amount"] == 10000.00
        assert kwargs["license_type"] is None


# =============================================================================
# 并发和性能测试（可选）
# =============================================================================

class TestConcurrencyAndPerformance:
    """并发和性能相关测试"""

    def test_save_multiple_files_same_invoice(self, storage_service, temp_upload_dir):
        """测试同一发票上传多个文件（覆盖场景）"""
        # 第一次上传
        file_path1 = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename="first.pdf",
            content=b"first version"
        )

        # 第二次上传（不同时间戳会生成不同文件名）
        import time
        time.sleep(0.01)  # 确保时间戳不同

        file_path2 = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename="second.pdf",
            content=b"second version"
        )

        # 两个文件都存在（不会覆盖）
        assert storage_service.file_exists(file_path1)
        assert storage_service.file_exists(file_path2)

        # 文件名不同
        assert file_path1 != file_path2

    def test_save_file_chinese_filename(self, storage_service, temp_upload_dir):
        """测试中文文件名"""
        file_path = storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename="发票文件.pdf",
            content=b"chinese filename test"
        )

        # 文件应成功保存
        assert storage_service.file_exists(file_path)
        assert file_path.endswith(".pdf")
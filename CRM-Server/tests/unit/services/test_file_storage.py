# tests/unit/services/test_file_storage.py

import pytest
import tempfile
import os
from pathlib import Path
from app.services.file_storage import FileStorageService, FileStorageError

@pytest.fixture
def temp_upload_dir():
    """临时上传目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def storage_service(temp_upload_dir):
    """使用临时目录的存储服务"""
    return FileStorageService(base_dir=temp_upload_dir)

def test_save_invoice_file_success(storage_service, temp_upload_dir):
    """测试成功保存发票文件"""
    # 模拟上传文件
    file_content = b"test invoice pdf content"
    filename = "test_invoice.pdf"

    # 保存文件
    relative_path = storage_service.save_invoice_file(
        team_id=1,
        invoice_id=100,
        filename=filename,
        content=file_content
    )

    # 验证返回路径格式（目录结构正确，文件名以invoice_id开头）
    assert relative_path.startswith("invoices/1/100/")
    assert "/100_" in relative_path  # 文件名包含 invoice_id
    assert relative_path.endswith(".pdf")  # 保留扩展名

    # 验证文件实际存在
    full_path = os.path.join(temp_upload_dir, relative_path)
    assert os.path.exists(full_path)

    # 验证内容正确
    with open(full_path, "rb") as f:
        assert f.read() == file_content

def test_save_invoice_file_path_traversal_blocked(storage_service):
    """测试路径穿越攻击被阻止"""
    # 尝试路径穿越
    malicious_filename = "../../../etc/passwd"

    with pytest.raises(FileStorageError) as exc_info:
        storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename=malicious_filename,
            content=b"malicious"
        )

    assert "非法文件名" in str(exc_info.value)

def test_save_invoice_file_invalid_extension(storage_service):
    """测试非法扩展名被拒绝"""
    malicious_filename = "test_invoice.exe"

    with pytest.raises(FileStorageError) as exc_info:
        storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename=malicious_filename,
            content=b"malicious"
        )

    assert "不允许的文件类型" in str(exc_info.value)

def test_get_file_path(storage_service, temp_upload_dir):
    """测试获取完整文件路径"""
    relative_path = "invoices/1/100/test.pdf"
    full_path = storage_service.get_full_path(relative_path)

    expected = os.path.join(temp_upload_dir, relative_path)
    assert full_path == expected

def test_team_isolation(storage_service, temp_upload_dir):
    """测试团队隔离——不同团队文件不能互相访问"""
    # 团队 1 的文件
    path1 = storage_service.save_invoice_file(
        team_id=1, invoice_id=100, filename="a.pdf", content=b"team1"
    )

    # 团队 2 的文件
    path2 = storage_service.save_invoice_file(
        team_id=2, invoice_id=100, filename="b.pdf", content=b"team2"
    )

    # 验证路径在不同目录
    assert path1.startswith("invoices/1/")
    assert path2.startswith("invoices/2/")

    # 验证物理隔离
    full_path1 = storage_service.get_full_path(path1)
    full_path2 = storage_service.get_full_path(path2)
    assert os.path.dirname(os.path.dirname(full_path1)) != os.path.dirname(os.path.dirname(full_path2))
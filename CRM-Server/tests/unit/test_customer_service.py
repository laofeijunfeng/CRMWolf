"""
后端测试示例 - 类型安全实现

Description: 展示如何按照规范编写类型安全的 pytest 测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.core.exceptions import NotFoundException, ConflictException
from app.services.customer_service import CustomerService


# ===== Mock 数据（使用 Pydantic Schema） =====
@pytest.fixture
def customer_create_data() -> CustomerCreate:
    """客户创建数据 fixture"""
    return CustomerCreate(
        account_name="测试公司",
        city="北京",
        industry="互联网",
        address="北京市朝阳区",
        company_scale="51-200"
    )


@pytest.fixture
def mock_customer() -> Mock:
    """Mock 客户对象"""
    customer = Mock()
    customer.id = 1
    customer.account_name = "测试公司"
    customer.city = "北京"
    customer.industry = "互联网"
    customer.status = 0
    customer.owner_id = "ou_test123"
    customer.creator_id = "ou_test123"
    customer.version = 1
    customer.created_time = datetime(2024, 1, 1)
    customer.last_modified_time = datetime(2024, 1, 1)
    return customer


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock 数据库会话"""
    db = MagicMock()
    db.add = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    db.refresh = Mock()
    db.execute = Mock()
    db.query = Mock()
    return db


# ===== Service 测试 =====
class TestCustomerService:
    """客户服务测试"""

    def test_get_list_returns_paginated_results(
        self,
        mock_db: MagicMock,
        mock_customer: Mock
    ) -> None:
        """测试分页查询返回正确结果"""
        # Mock CRUD 返回
        mock_customers = [mock_customer]
        mock_total = 1

        with patch.object(
            CustomerService,
            'get_multi',
            return_value=(mock_customers, mock_total)
        ):
            result, total = CustomerService.get_list(mock_db, skip=0, limit=20)

            assert len(result) == 1
            assert total == 1
            assert result[0].account_name == "测试公司"

    def test_get_by_id_returns_customer(
        self,
        mock_db: MagicMock,
        mock_customer: Mock
    ) -> None:
        """测试根据 ID 获取客户"""
        with patch.object(
            CustomerService,
            'get',
            return_value=mock_customer
        ):
            result = CustomerService.get_by_id(mock_db, 1)

            assert result.id == 1
            assert result.account_name == "测试公司"

    def test_get_by_id_raises_not_found_when_missing(
        self,
        mock_db: MagicMock
    ) -> None:
        """测试客户不存在时抛出 NotFoundException"""
        with patch.object(
            CustomerService,
            'get',
            return_value=None
        ):
            with pytest.raises(NotFoundException) as exc_info:
                CustomerService.get_by_id(mock_db, 999)

            assert "999" in str(exc_info.value)

    def test_create_success(
        self,
        mock_db: MagicMock,
        customer_create_data: CustomerCreate,
        mock_customer: Mock
    ) -> None:
        """测试成功创建客户"""
        with patch.object(
            CustomerService,
            'get_by_name',
            return_value=None
        ):
            with patch.object(
                CustomerService,
                'create_with_owner',
                return_value=mock_customer
            ):
                result = CustomerService.create(
                    mock_db,
                    customer_create_data,
                    "ou_test123"
                )

                assert result.account_name == "测试公司"

    def test_create_raises_conflict_when_name_exists(
        self,
        mock_db: MagicMock,
        customer_create_data: CustomerCreate,
        mock_customer: Mock
    ) -> None:
        """测试名称已存在时抛出 ConflictException"""
        with patch.object(
            CustomerService,
            'get_by_name',
            return_value=mock_customer
        ):
            with pytest.raises(ConflictException) as exc_info:
                CustomerService.create(
                    mock_db,
                    customer_create_data,
                    "ou_test123"
                )

            assert "已存在" in str(exc_info.value)

    def test_update_success(
        self,
        mock_db: MagicMock,
        mock_customer: Mock
    ) -> None:
        """测试成功更新客户"""
        update_data = CustomerUpdate(city="上海")

        with patch.object(
            CustomerService,
            'get',
            return_value=mock_customer
        ):
            with patch.object(
                CustomerService,
                'update',
                return_value=mock_customer
            ):
                result = CustomerService.update(mock_db, 1, update_data)

                assert result.id == 1


# ===== 错误示例（禁止） =====

"""
❌ 禁止示例 1：Mock 数据使用裸 dict

# 错误
@pytest.fixture
def customer_data():
    return {"account_name": "测试", "city": "北京"}

# 正确：使用 Pydantic Schema
@pytest.fixture
def customer_data() -> CustomerCreate:
    return CustomerCreate(account_name="测试", city="北京")
"""

"""
❌ 禁止示例 2：函数无返回类型注解

# 错误
def test_get_list(mock_db):
    assert ...

# 正确
def test_get_list(mock_db: MagicMock) -> None:
    assert ...
"""

"""
❌ 禁止示例 3：跳过测试

# 错误
@pytest.mark.skip
def test_something():
    pass

# 正确：完成所有测试
def test_something() -> None:
    pass
"""

"""
❌ 禁止示例 4：无边界测试

# 错误：只测成功场景
def test_create(mock_db):
    result = CustomerService.create(mock_db, data)
    assert result is not None

# 正确：覆盖成功和失败场景
def test_create_success(mock_db) -> None:
    ...

def test_create_raises_conflict(mock_db) -> None:
    ...
"""
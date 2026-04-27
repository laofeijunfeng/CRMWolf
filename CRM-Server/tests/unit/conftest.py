"""
Pytest 配置文件

Description: 共享 fixtures 和测试配置
"""

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_db_session():
    """Mock 数据库会话 fixture"""
    session = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.refresh = Mock()
    session.execute = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def mock_redis():
    """Mock Redis fixture"""
    redis = Mock()
    redis.get = Mock(return_value=None)
    redis.set = Mock()
    redis.delete = Mock()
    return redis


@pytest.fixture
def mock_current_user():
    """Mock 当前用户 fixture"""
    return {
        "id": "ou_test123",
        "name": "测试用户",
        "roles": ["SALES_MEMBER"],
        "permissions": ["customer:view_own", "customer:create"]
    }
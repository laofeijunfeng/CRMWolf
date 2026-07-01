"""修改密码 API 单元测试"""
import pytest
from fastapi import HTTPException, status
from unittest.mock import MagicMock, patch
from app.api.auth import change_password
from app.schemas.auth import ChangePasswordRequest


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_user_with_password():
    """模拟设置了密码的用户"""
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    user.password_hash = "hashed_password"
    return user


@pytest.fixture
def mock_user_no_password():
    """模拟未设置密码的用户"""
    user = MagicMock()
    user.id = 2
    user.email = "nopass@example.com"
    user.password_hash = None
    return user


class TestChangePassword:
    """修改密码测试"""

    @patch('app.api.auth.verify_password')
    @patch('app.api.auth.user_crud.set_password')
    async def test_change_password_success(
        self, mock_set_password, mock_verify, mock_db, mock_user_with_password
    ):
        """测试成功修改密码"""
        # 旧密码验证成功，新密码与旧密码不同
        mock_verify.side_effect = [True, False]

        request = ChangePasswordRequest(
            old_password="oldpass123",
            new_password="newpass456"
        )

        result = await change_password(request, mock_user_with_password, mock_db)

        assert result["message"] == "密码修改成功"
        mock_set_password.assert_called_once()

    @patch('app.api.auth.verify_password')
    async def test_change_password_user_no_password(
        self, mock_verify, mock_db, mock_user_no_password
    ):
        """测试用户未设置密码时抛出异常"""
        request = ChangePasswordRequest(
            old_password="oldpass123",
            new_password="newpass456"
        )

        with pytest.raises(HTTPException) as exc_info:
            await change_password(request, mock_user_no_password, mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "未设置密码" in exc_info.value.detail

    @patch('app.api.auth.verify_password')
    async def test_change_password_wrong_old_password(
        self, mock_verify, mock_db, mock_user_with_password
    ):
        """测试旧密码错误时抛出异常"""
        mock_verify.return_value = False

        request = ChangePasswordRequest(
            old_password="wrongpass",
            new_password="newpass456"
        )

        with pytest.raises(HTTPException) as exc_info:
            await change_password(request, mock_user_with_password, mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "旧密码不正确" in exc_info.value.detail

    @patch('app.api.auth.verify_password')
    async def test_change_password_same_password(
        self, mock_verify, mock_db, mock_user_with_password
    ):
        """测试新密码与旧密码相同时抛出异常"""
        # 旧密码验证成功，新密码与旧密码相同
        mock_verify.side_effect = [True, True]

        request = ChangePasswordRequest(
            old_password="oldpass123",
            new_password="oldpass123"
        )

        with pytest.raises(HTTPException) as exc_info:
            await change_password(request, mock_user_with_password, mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "不能与旧密码相同" in exc_info.value.detail
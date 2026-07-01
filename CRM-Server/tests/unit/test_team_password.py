"""重置成员密码 API 单元测试"""
import pytest
from fastapi import HTTPException, status
from unittest.mock import MagicMock, patch
from app.api.teams import reset_member_password, is_team_admin
from app.schemas.team import ResetPasswordRequest


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_admin_user():
    """模拟团队管理员"""
    user = MagicMock()
    user.id = 1
    user.name = "Admin"
    return user


@pytest.fixture
def mock_normal_user():
    """模拟普通用户"""
    user = MagicMock()
    user.id = 2
    user.name = "Normal User"
    return user


@pytest.fixture
def mock_target_user():
    """模拟目标成员"""
    user = MagicMock()
    user.id = 3
    user.name = "Target User"
    return user


class TestResetMemberPassword:
    """重置成员密码测试"""

    @patch('app.api.teams.is_team_admin')
    @patch('app.api.teams.user_crud.get_by_id')
    @patch('app.api.teams.role_crud.get_user_roles')
    @patch('app.api.teams.user_crud.set_password')
    async def test_reset_password_success(
        self, mock_set_password, mock_get_roles, mock_get_user, mock_is_admin,
        mock_db, mock_admin_user, mock_target_user
    ):
        """测试成功重置密码"""
        mock_is_admin.return_value = True
        mock_get_user.return_value = mock_target_user
        mock_get_roles.return_value = [MagicMock()]  # 有角色表示属于团队

        request = ResetPasswordRequest(new_password="newpass456")

        result = await reset_member_password(
            1, 3, request, mock_admin_user, mock_db
        )

        assert "已重置" in result["message"]
        assert "Target User" in result["message"]
        mock_set_password.assert_called_once()

    @patch('app.api.teams.is_team_admin')
    async def test_reset_password_not_admin(
        self, mock_is_admin, mock_db, mock_normal_user
    ):
        """测试非管理员调用时抛出异常"""
        mock_is_admin.return_value = False

        request = ResetPasswordRequest(new_password="newpass456")

        with pytest.raises(HTTPException) as exc_info:
            await reset_member_password(
                1, 3, request, mock_normal_user, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "仅团队所有者" in exc_info.value.detail

    @patch('app.api.teams.is_team_admin')
    @patch('app.api.teams.user_crud.get_by_id')
    async def test_reset_password_user_not_found(
        self, mock_get_user, mock_is_admin, mock_db, mock_admin_user
    ):
        """测试用户不存在时抛出异常"""
        mock_is_admin.return_value = True
        mock_get_user.return_value = None

        request = ResetPasswordRequest(new_password="newpass456")

        with pytest.raises(HTTPException) as exc_info:
            await reset_member_password(
                1, 999, request, mock_admin_user, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "用户不存在" in exc_info.value.detail

    @patch('app.api.teams.is_team_admin')
    @patch('app.api.teams.user_crud.get_by_id')
    @patch('app.api.teams.role_crud.get_user_roles')
    async def test_reset_password_user_not_in_team(
        self, mock_get_roles, mock_get_user, mock_is_admin,
        mock_db, mock_admin_user, mock_target_user
    ):
        """测试用户不属于团队时抛出异常"""
        mock_is_admin.return_value = True
        mock_get_user.return_value = mock_target_user
        mock_get_roles.return_value = []  # 无角色表示不属于团队

        request = ResetPasswordRequest(new_password="newpass456")

        with pytest.raises(HTTPException) as exc_info:
            await reset_member_password(
                1, 3, request, mock_admin_user, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "不属于当前团队" in exc_info.value.detail


class TestIsTeamAdmin:
    """测试 is_team_admin 函数"""

    @patch('app.api.teams.role_crud.get_user_roles')
    def test_is_team_admin_true(self, mock_get_roles, mock_db):
        """测试用户是团队管理员"""
        admin_role = MagicMock()
        admin_role.code = "TEAM_ADMIN"
        mock_get_roles.return_value = [admin_role]

        result = is_team_admin(mock_db, 1, 1)
        assert result is True

    @patch('app.api.teams.role_crud.get_user_roles')
    def test_is_team_admin_false(self, mock_get_roles, mock_db):
        """测试用户不是团队管理员"""
        member_role = MagicMock()
        member_role.code = "SALES_MEMBER"
        mock_get_roles.return_value = [member_role]

        result = is_team_admin(mock_db, 1, 2)
        assert result is False
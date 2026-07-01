# 密码管理功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现用户修改密码和团队所有者重置成员密码两个功能

**Architecture:** 后端新增两个 API 端点（`/me/change-password` 和 `/{team_id}/members/{user_id}/reset-password`），前端新增两个对话框组件（Settings.vue 修改密码、TeamMembers.vue 重置密码），复用现有 CRUD 方法 `user_crud.set_password()`

**Tech Stack:** FastAPI + Pydantic (后端), Vue 3 + Element Plus + TypeScript (前端)

## Global Constraints

- 后端密码规则：6-50 字符（前后端一致）
- 前端使用 TypeScript interface（不使用 Zod），符合 auth.ts/team.ts 现有模式
- 请求工具：使用 `request` 从 `@/utils/request`，自动处理 token 和错误
- 成功提示：使用 `showSuccess()` 从 `@/utils/errorMessages`
- 图标导入：使用 `Key` 图标从 `@element-plus/icons-vue`
- 后端 CRUD：复用现有 `user_crud.set_password()` 方法
- 密码哈希：使用 bcrypt `get_password_hash()` 和 `verify_password()`
- 权限检查：TEAM_ADMIN 使用 `is_team_admin()` 函数
- 表单验证：使用 Element Plus FormRules + validator

---

## File Structure

| 文件 | 责责 |
|------|------|
| `CRM-Server/app/schemas/auth.py` | ChangePasswordRequest Schema 定义 |
| `CRM-Server/app/schemas/team.py` | ResetPasswordRequest Schema 定义 |
| `CRM-Server/app/api/auth.py` | `/me/change-password` 端点实现 |
| `CRM-Server/app/api/teams.py` | `/{team_id}/members/{user_id}/reset-password` 端点实现 |
| `CRM-Client/src/api/auth.ts` | `changePassword` API 方法 |
| `CRM-Client/src/api/team.ts` | `resetMemberPassword` API 方法 |
| `CRM-Client/src/views/Settings.vue` | 修改密码按钮 + 对话框 |
| `CRM-Client/src/views/TeamMembers.vue` | 重置密码按钮 + 对话框 |
| `CRM-Server/tests/unit/test_auth_password.py` | 修改密码 API 单元测试 |
| `CRM-Server/tests/unit/test_team_password.py` | 重置成员密码 API 单元测试 |

---

### Task 1: 后端 - 修改密码 Schema

**Files:**
- Modify: `CRM-Server/app/schemas/auth.py:1-43`

**Interfaces:**
- Consumes: Pydantic BaseModel, Field
- Produces: `ChangePasswordRequest` class with `old_password` and `new_password` fields

- [ ] **Step 1: 写入 Schema 定义**

在 `CRM-Server/app/schemas/auth.py` 文件末尾添加：

```python


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="旧密码"
    )
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=50,
        description="新密码（6-50位）"
    )
```

- [ ] **Step 2: 验证 Schema 定义正确**

```bash
cd CRM-Server && python -c "from app.schemas.auth import ChangePasswordRequest; print('Schema loaded successfully')"
```

Expected: `Schema loaded successfully`

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/schemas/auth.py
git commit -m "feat(auth): add ChangePasswordRequest schema"
```

---

### Task 2: 后端 - 修改密码 API 端点

**Files:**
- Modify: `CRM-Server/app/api/auth.py:1-316`
- Create: `CRM-Server/tests/unit/test_auth_password.py`

**Interfaces:**
- Consumes: `ChangePasswordRequest` from Task 1, `user_crud.set_password()`, `verify_password()`, `get_current_active_user`
- Produces: `POST /v1/auth/me/change-password` endpoint returning `{"message": "密码修改成功"}`

- [ ] **Step 1: 写入 API 实现**

在 `CRM-Server/app/api/auth.py` 中：

1. 在导入区域（约 line 26）添加：
```python
from app.schemas.auth import ChangePasswordRequest
```

2. 在文件末尾（约 line 316）添加新端点：
```python


@router.post("/me/change-password", summary="修改密码", description="修改当前用户密码")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    修改密码
    
    验证旧密码后更新为新密码
    """
    # 验证用户是否设置了密码
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户未设置密码，请通过其他方式设置密码"
        )
    
    # 验证旧密码
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码不正确"
        )
    
    # 新密码不能与旧密码相同
    if verify_password(request.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与旧密码相同"
        )
    
    # 更新密码（复用现有 CRUD 方法）
    user_crud.set_password(db, current_user, request.new_password)
    
    return {"message": "密码修改成功"}
```

- [ ] **Step 2: 写入单元测试**

创建 `CRM-Server/tests/unit/test_auth_password.py`：

```python
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
```

- [ ] **Step 3: 运行测试**

```bash
cd CRM-Server && pytest tests/unit/test_auth_password.py -v
```

Expected: 4 tests passed

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/api/auth.py CRM-Server/tests/unit/test_auth_password.py
git commit -m "feat(auth): implement change password endpoint with tests"
```

---

### Task 3: 后端 - 重置成员密码 Schema

**Files:**
- Modify: `CRM-Server/app/schemas/team.py:1-85`

**Interfaces:**
- Consumes: Pydantic BaseModel, Field
- Produces: `ResetPasswordRequest` class with `new_password` field

- [ ] **Step 1: 写入 Schema 定义**

在 `CRM-Server/app/schemas/team.py` 文件末尾添加：

```python


class ResetPasswordRequest(BaseModel):
    """重置成员密码请求"""
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=50,
        description="新密码（6-50位）"
    )
```

- [ ] **Step 2: 验证 Schema 定义正确**

```bash
cd CRM-Server && python -c "from app.schemas.team import ResetPasswordRequest; print('Schema loaded successfully')"
```

Expected: `Schema loaded successfully`

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/schemas/team.py
git commit -m "feat(team): add ResetPasswordRequest schema"
```

---

### Task 4: 后端 - 重置成员密码 API 端点

**Files:**
- Modify: `CRM-Server/app/api/teams.py:1-429`
- Create: `CRM-Server/tests/unit/test_team_password.py`

**Interfaces:**
- Consumes: `ResetPasswordRequest` from Task 3, `is_team_admin()`, `user_crud.set_password()`, `role_crud.get_user_roles()`
- Produces: `POST /v1/teams/{team_id}/members/{user_id}/reset-password` endpoint

- [ ] **Step 1: 写入 API 实现**

在 `CRM-Server/app/api/teams.py` 中：

1. 在导入区域（约 line 24）添加：
```python
from app.schemas.team import ResetPasswordRequest
```

2. 在文件末尾（约 line 429）添加新端点：
```python


@router.post("/{team_id}/members/{user_id}/reset-password", summary="重置成员密码", description="重置团队成员密码（仅 TEAM_ADMIN 可调用）")
async def reset_member_password(
    team_id: int,
    user_id: int,
    request: ResetPasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    重置团队成员密码（仅 TEAM_ADMIN 可调用）
    
    直接设置新密码，无需验证旧密码
    """
    # 权限检查：仅 TEAM_ADMIN 可调用
    if not is_team_admin(db, team_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅团队所有者可重置成员密码"
        )
    
    # 检查目标用户是否属于该团队
    target_user = user_crud.get_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查目标用户是否属于该团队（通过角色关联）
    user_roles = role_crud.get_user_roles(db, user_id, team_id)
    if not user_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户不属于当前团队"
        )
    
    # 更新密码（复用现有 CRUD 方法）
    user_crud.set_password(db, target_user, request.new_password)
    
    return {"message": f"已重置 {target_user.name} 的密码"}
```

- [ ] **Step 2: 写入单元测试**

创建 `CRM-Server/tests/unit/test_team_password.py`：

```python
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
```

- [ ] **Step 3: 运行测试**

```bash
cd CRM-Server && pytest tests/unit/test_team_password.py -v
```

Expected: 6 tests passed

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/api/teams.py CRM-Server/tests/unit/test_team_password.py
git commit -m "feat(team): implement reset member password endpoint with tests"
```

---

### Task 5: 前端 - auth.ts API 封装

**Files:**
- Modify: `CRM-Client/src/api/auth.ts:1-109`

**Interfaces:**
- Consumes: `request` from `@/utils/request`
- Produces: `ChangePasswordRequest` interface, `authApi.changePassword()` method

- [ ] **Step 1: 写入接口定义和 API 方法**

在 `CRM-Client/src/api/auth.ts` 中：

1. 在接口定义区域（约 line 49）添加：
```typescript
export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}
```

2. 在 `authApi` 对象中（约 line 108）添加：
```typescript
  // 修改密码（新增）
  changePassword: (data: ChangePasswordRequest) => {
    return request.post<{ message: string }>('/v1/auth/me/change-password', data)
  }
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd CRM-Client && npm run type-check
```

Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/api/auth.ts
git commit -m "feat(auth): add changePassword API method"
```

---

### Task 6: 前端 - team.ts API 封装

**Files:**
- Modify: `CRM-Client/src/api/team.ts:1-113`

**Interfaces:**
- Consumes: `request` from `@/utils/request`
- Produces: `ResetPasswordRequest` interface, `teamApi.resetMemberPassword()` method

- [ ] **Step 1: 写入接口定义和 API 方法**

在 `CRM-Client/src/api/team.ts` 中：

1. 在接口定义区域（约 line 52）添加：
```typescript
export interface ResetPasswordRequest {
  new_password: string
}
```

2. 在 `teamApi` 对象中（约 line 112）添加：
```typescript
  // 重置成员密码（新增）
  resetMemberPassword: (teamId: number, userId: string, data: ResetPasswordRequest) => {
    return request.post<{ message: string }>(`/v1/teams/${teamId}/members/${userId}/reset-password`, data)
  }
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd CRM-Client && npm run type-check
```

Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/api/team.ts
git commit -m "feat(team): add resetMemberPassword API method"
```

---

### Task 7: 前端 - Settings.vue 修改密码功能

**Files:**
- Modify: `CRM-Client/src/views/Settings.vue:1-448`

**Interfaces:**
- Consumes: `Key` icon, `showSuccess`, `FormInstance`, `FormRules`, `authApi.changePassword`
- Produces: 修改密码按钮 + el-dialog 对话框组件

- [ ] **Step 1: 添加导入**

在 `CRM-Client/src/views/Settings.vue` 的 `<script setup>` 区域（约 line 126）添加：

```typescript
import { Key } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
```

注意：`showSuccess` 已经导入，无需重复添加。

- [ ] **Step 2: 添加状态和方法**

在 `<script setup>` 区域（约 line 183，`onMounted` 之后）添加：

```typescript
// 修改密码相关状态
const changePasswordVisible = ref(false)
const changePasswordLoading = ref(false)
const changePasswordFormRef = ref<FormInstance>()

const changePasswordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const validateConfirmPassword = (rule: any, value: string, callback: any) => {
  if (value !== changePasswordForm.newPassword) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const changePasswordRules: FormRules = {
  oldPassword: [
    { required: true, message: '请输入旧密码', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度为6-50个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const showChangePasswordDialog = () => {
  changePasswordForm.oldPassword = ''
  changePasswordForm.newPassword = ''
  changePasswordForm.confirmPassword = ''
  changePasswordVisible.value = true
}

const handleChangePassword = async () => {
  const valid = await changePasswordFormRef.value?.validate().catch(() => false)
  if (!valid) return
  
  changePasswordLoading.value = true
  try {
    await authApi.changePassword({
      old_password: changePasswordForm.oldPassword,
      new_password: changePasswordForm.newPassword,
    })
    showSuccess('密码修改成功')
    changePasswordVisible.value = false
  } catch (error) {
    console.error('修改密码失败', error)
  } finally {
    changePasswordLoading.value = false
  }
}
```

- [ ] **Step 3: 添加按钮**

在 `<template>` 的 `user-actions` 区域（约 line 18-23），修改为：

```vue
<div class="user-actions">
  <el-button size="small" @click="showChangePasswordDialog">
    <el-icon><Key /></el-icon>
    修改密码
  </el-button>
  <el-button size="small" @click="handleLogout">
    <el-icon><SwitchButton /></el-icon>
    退出登录
  </el-button>
</div>
```

- [ ] **Step 4: 添加对话框**

在 `<template>` 的 `logs-card` 之后（约 line 117）添加：

```vue
    <!-- 修改密码对话框 -->
    <el-dialog
      v-model="changePasswordVisible"
      title="修改密码"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="changePasswordFormRef"
        :model="changePasswordForm"
        :rules="changePasswordRules"
        label-width="80px"
      >
        <el-form-item label="旧密码" prop="oldPassword">
          <el-input
            v-model="changePasswordForm.oldPassword"
            type="password"
            placeholder="请输入旧密码"
            show-password
          />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="changePasswordForm.newPassword"
            type="password"
            placeholder="请输入新密码（6-50位）"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="changePasswordForm.confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="changePasswordVisible = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword" :loading="changePasswordLoading">
          确认修改
        </el-button>
      </template>
    </el-dialog>
```

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd CRM-Client && npm run type-check
```

Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add CRM-Client/src/views/Settings.vue
git commit -m "feat(settings): add change password button and dialog"
```

---

### Task 8: 前端 - TeamMembers.vue 重置密码功能

**Files:**
- Modify: `CRM-Client/src/views/TeamMembers.vue:1-668`

**Interfaces:**
- Consumes: `Key` icon, `showSuccess`, `FormInstance`, `FormRules`, `teamApi.resetMemberPassword`
- Produces: 重置密码按钮 + el-dialog 对话框组件

- [ ] **Step 1: 添加导入**

在 `CRM-Client/src/views/TeamMembers.vue` 的 `<script setup>` 区域（约 line 161）修改导入：

```typescript
import { Plus, Refresh, Search, Loading, Key } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
```

注意：需要添加 `Key` 图标和 `FormInstance`, `FormRules` 类型导入。

- [ ] **Step 2: 添加状态和方法**

在 `<script setup>` 区域（约 line 356，`handleSaveRoles` 之后）添加：

```typescript
// 重置密码相关状态
const resetPasswordVisible = ref(false)
const resetPasswordLoading = ref(false)
const resetPasswordFormRef = ref<FormInstance>()
const resetPasswordTargetUser = ref<TeamMemberResponse | null>(null)

const resetPasswordForm = reactive({
  newPassword: '',
  confirmPassword: '',
})

const validateResetConfirmPassword = (rule: any, value: string, callback: any) => {
  if (value !== resetPasswordForm.newPassword) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const resetPasswordRules: FormRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度为6-50个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateResetConfirmPassword, trigger: 'blur' }
  ]
}

const showResetPasswordDialog = (member: TeamMemberResponse) => {
  resetPasswordTargetUser.value = member
  resetPasswordForm.newPassword = ''
  resetPasswordForm.confirmPassword = ''
  resetPasswordVisible.value = true
}

const handleResetPassword = async () => {
  const valid = await resetPasswordFormRef.value?.validate().catch(() => false)
  if (!valid || !resetPasswordTargetUser.value) return
  
  resetPasswordLoading.value = true
  try {
    await teamApi.resetMemberPassword(
      teamId.value!,
      resetPasswordTargetUser.value.id,
      { new_password: resetPasswordForm.newPassword }
    )
    ElMessage.success(`已重置 ${resetPasswordTargetUser.value.name} 的密码`)
    resetPasswordVisible.value = false
  } catch (error: any) {
    console.error('重置密码失败', error)
    ElMessage.error(error.response?.data?.detail || '重置密码失败')
  } finally {
    resetPasswordLoading.value = false
  }
}
```

- [ ] **Step 3: 添加按钮**

在 `<template>` 的操作列（约 line 58-81），修改为：

```vue
<el-table-column label="操作" fixed="right" width="200">
  <template #default="{ row }">
    <div class="action-buttons">
      <el-button
        v-if="row.id !== currentUserId && isTeamAdmin"
        type="text"
        size="small"
        class="wolf-btn wolf-btn--text"
        @click="showResetPasswordDialog(row)"
      >
        重置密码
      </el-button>
      <el-button
        v-if="row.id !== currentUserId && isTeamAdmin"
        type="text"
        size="small"
        class="wolf-btn wolf-btn--text"
        @click="handleAssignRoles(row)"
      >
        分配角色
      </el-button>
      <el-button
        v-if="row.id !== currentUserId && isTeamAdmin"
        type="text"
        size="small"
        class="wolf-btn wolf-btn--text-danger"
        @click="handleRemoveMember(row)"
      >
        移除
      </el-button>
    </div>
  </template>
</el-table-column>
```

注意：操作列宽度从 160 改为 200。

- [ ] **Step 4: 添加对话框**

在 `<template>` 的角色分配对话框之后（约 line 154）添加：

```vue
    <!-- 重置密码对话框 -->
    <el-dialog
      v-model="resetPasswordVisible"
      :title="`重置密码 - ${resetPasswordTargetUser?.name || ''}`"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="resetPasswordFormRef"
        :model="resetPasswordForm"
        :rules="resetPasswordRules"
        label-width="80px"
      >
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="resetPasswordForm.newPassword"
            type="password"
            placeholder="请输入新密码（6-50位）"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="resetPasswordForm.confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPasswordVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResetPassword" :loading="resetPasswordLoading">
          确认重置
        </el-button>
      </template>
    </el-dialog>
```

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd CRM-Client && npm run type-check
```

Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add CRM-Client/src/views/TeamMembers.vue
git commit -m "feat(team): add reset member password button and dialog"
```

---

### Task 9: 集成测试 - 后端 API 端点验证

**Files:**
- None (运行现有测试)

**Interfaces:**
- Consumes: All Tasks 1-4 backend implementations
- Produces: Verified working backend APIs

- [ ] **Step 1: 运行所有后端测试**

```bash
cd CRM-Server && pytest tests/unit/test_auth_password.py tests/unit/test_team_password.py -v
```

Expected: 10 tests passed

- [ ] **Step 2: 启动后端服务验证端点**

```bash
cd CRM-Server && python -c "
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)

# 检查路由是否注册
routes = [r.path for r in app.routes]
print('change-password route:', '/v1/auth/me/change-password' in routes)
print('reset-password route:', any('/members/{user_id}/reset-password' in r for r in routes))
"
```

Expected: Both routes registered

- [ ] **Step 3: Commit (如有修复)**

如有任何修复：
```bash
git add CRM-Server/
git commit -m "fix: backend password API integration fixes"
```

---

### Task 10: 集成测试 - 前端功能验证

**Files:**
- None (运行现有测试)

**Interfaces:**
- Consumes: All Tasks 5-8 frontend implementations
- Produces: Verified working frontend components

- [ ] **Step 1: 运行前端类型检查**

```bash
cd CRM-Client && npm run type-check
```

Expected: No errors

- [ ] **Step 2: 运行前端 lint**

```bash
cd CRM-Client && npm run lint
```

Expected: No errors (or fix any issues)

- [ ] **Step 3: 修复 lint 问题（如有）**

如有 lint 错误，运行：
```bash
cd CRM-Client && npm run lint -- --fix
```

- [ ] **Step 4: Commit (如有修复)**

如有任何修复：
```bash
git add CRM-Client/
git commit -m "fix: frontend password UI integration fixes"
```

---

### Task 11: 最终提交和验证

**Files:**
- None (提交验证)

**Interfaces:**
- Consumes: All completed tasks
- Produces: Complete feature implementation

- [ ] **Step 1: 查看所有更改**

```bash
git status
```

Expected: 所有修改已提交

- [ ] **Step 2: 查看提交历史**

```bash
git log --oneline -10
```

Expected: 看到所有 feature commits

- [ ] **Step 3: 推送到远程**

```bash
git push origin main
```

Expected: Push successful

---

## Self-Review Checklist

### 1. Spec Coverage

| 需求 | 任务 | 状态 |
|------|------|------|
| 用户修改密码入口 | Task 7 | ✅ |
| 旧密码验证 | Task 2 | ✅ |
| 新密码 6-50 字符 | Task 1, 2, 5, 7 | ✅ |
| 确认密码一致性 | Task 7 | ✅ |
| 成功提示 showSuccess | Task 7 | ✅ |
| 团队所有者重置成员密码 | Task 8 | ✅ |
| TEAM_ADMIN 权限检查 | Task 4 | ✅ |
| 团队归属验证 | Task 4 | ✅ |
| 前端 TypeScript interface | Task 5, 6 | ✅ |
| 后端 Pydantic Schema | Task 1, 3 | ✅ |
| 密码哈希 bcrypt | Task 2, 4 | ✅ |
| 单元测试 | Task 2, 4 | ✅ |

### 2. Placeholder Scan

- ✅ 无 "TBD" 或 "TODO"
- ✅ 无 "add appropriate error handling"
- ✅ 无 "write tests for the above" (测试代码完整)
- ✅ 无 "similar to Task N" (每步骤代码完整)
- ✅ 所有代码步骤包含实际代码

### 3. Type Consistency

| 检查项 | 状态 |
|--------|------|
| `ChangePasswordRequest.old_password` vs `changePasswordForm.oldPassword` | ✅ 一致 |
| `ChangePasswordRequest.new_password` vs `changePasswordForm.newPassword` | ✅ 一致 |
| `ResetPasswordRequest.new_password` vs `resetPasswordForm.newPassword` | ✅ 一致 |
| `teamApi.resetMemberPassword(userId: string)` vs API path `{user_id}` | ✅ 一致 (前端 string，后端 int，路径转换) |

---

**计划完成。保存到 `docs/superpowers/plans/2026-07-01-change-password.md`**

**执行选项：**

**1. Subagent-Driven (推荐)** - 我为每个任务派发一个新子代理，在任务之间进行审查，快速迭代

**2. Inline Execution** - 在此会话中使用 executing-plans 执行任务，批量执行带检查点审查

**选择哪种方式？**
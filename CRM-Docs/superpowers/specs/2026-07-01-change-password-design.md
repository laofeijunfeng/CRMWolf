# 密码管理功能设计文档

**创建日期**：2026-07-01
**状态**：待审核

---

## 1. 概述

### 1.1 背景

本设计包含两个密码管理功能：
1. **用户修改密码** - 用户在个人设置页面修改自己的密码
2. **团队所有者重置成员密码** - TEAM_ADMIN 在团队成员管理页面重置成员密码

### 1.2 目标

- 提供用户自助修改密码入口
- 支持团队所有者管理成员密码
- 验证旧密码/权限确保安全性
- 符合系统现有 UI/API 规范

### 1.3 功能对比

| 功能 | 用户修改密码 | 团队所有者重置成员密码 |
|------|--------------|------------------------|
| 执行者 | 用户本人 | 团队所有者 (TEAM_ADMIN) |
| 输入字段 | 旧密码 + 新密码 + 确认密码 | 仅新密码 + 确认密码 |
| 验证旧密码 | ✅ 需要 | ❌ 不需要 |
| 权限要求 | 无额外权限 | TEAM_ADMIN 角色 |
| 入口位置 | 个人设置页面 | 团队成员管理页面 |
| API 路径 | `/v1/auth/me/change-password` | `/v1/teams/{team_id}/members/{user_id}/reset-password` |

---

## 2. UI 设计

### 2.1 入口位置

在 Settings.vue 页面的用户信息卡片 `user-actions` 区域，退出登录按钮左侧添加"修改密码"按钮：

```vue
<div class="user-actions">
  <!-- 新增：修改密码按钮 -->
  <el-button size="small" @click="showChangePasswordDialog">
    <el-icon><Key /></el-icon>
    修改密码
  </el-button>
  
  <!-- 原有：退出登录按钮 -->
  <el-button size="small" @click="handleLogout">
    <el-icon><SwitchButton /></el-icon>
    退出登录
  </el-button>
</div>
```

### 2.2 对话框设计

使用 Element Plus `el-dialog` 居中弹窗，宽度 400px：

**表单字段**：
| 字段 | 类型 | 验证规则 |
|------|------|----------|
| 旧密码 | password | 必填，1-50字符 |
| 新密码 | password | 必填，6-50字符 |
| 确认密码 | password | 必填，需与新密码一致 |

**表单布局**：
```
┌─────────────────────────────────────┐
│  修改密码                         ✕ │
├─────────────────────────────────────┤
│  旧密码     [••••••••••••••]        │
│  新密码     [••••••••••••••]        │
│  确认密码   [••••••••••••••]        │
│                                     │
│         [取消]    [确认修改]        │
└─────────────────────────────────────┘
```

---

## 3. 前端实现

### 3.1 API 封装

**文件**：`src/api/auth.ts`

**新增接口**：
```typescript
export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export const authApi = {
  // ... 现有方法
  
  // 修改密码
  changePassword: (data: ChangePasswordRequest) => {
    return request.post<{ message: string }>('/v1/auth/me/change-password', data)
  }
}
```

### 3.2 Settings.vue 新增代码

**新增导入**：
```typescript
import { Key } from '@element-plus/icons-vue'
import { showSuccess } from '@/utils/errorMessages'
import type { FormInstance, FormRules } from 'element-plus'
```

**新增状态**：
```typescript
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
```

**新增方法**：
```typescript
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

---

## 4. 后端实现

### 4.1 API 端点

**路径**：`POST /v1/auth/me/change-password`

**符合现有规范**：
- 路由 `prefix="/auth"` + `main.py` 注册 `prefix="/v1"`
- 与现有 `/me`、`/me/roles`、`/me/permissions` 保持一致

### 4.2 Schema 定义

**文件**：`app/schemas/auth.py`

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

### 4.3 API 实现

**文件**：`app/api/auth.py`

```python
# 导入新增
from app.schemas.auth import ChangePasswordRequest

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

---

## 5. 安全考虑

| 安全措施 | 实现方式 |
|----------|----------|
| 旧密码验证 | bcrypt `verify_password()` 验证 |
| 密码哈希存储 | bcrypt `get_password_hash()` 哈希后存储 |
| 错误信息不泄露 | 仅返回"旧密码不正确"，不透露更多信息 |
| 新密码差异化 | 禁止新密码与旧密码相同 |
| 未设置密码处理 | 提示用户通过其他方式设置 |

---

## 6. 文件清单

### 6.1 新增文件

无（所有修改都在现有文件中）

### 6.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `CRM-Server/app/schemas/auth.py` | 新增 `ChangePasswordRequest` Schema |
| `CRM-Server/app/api/auth.py` | 新增 `/me/change-password` 端点 |
| `CRM-Client/src/api/auth.ts` | 新增 `changePassword` API 方法 |
| `CRM-Client/src/views/Settings.vue` | 新增修改密码按钮和对话框 |

---

## 7. 注意事项

### 7.1 现有规范遵循

- **前端 API**：使用 TypeScript interface（不使用 Zod），符合 `auth.ts` 现有模式
- **请求工具**：使用 `request` 从 `@/utils/request`，自动处理 token 和错误
- **成功提示**：使用 `showSuccess()` 从 `@/utils/errorMessages`
- **图标导入**：使用 `Key` 图标从 `@element-plus/icons-vue`
- **后端 CRUD**：复用现有 `user_crud.set_password()` 方法

### 7.2 密码规则一致性

前端和后端密码验证规则保持一致：
- 最小长度：6 字符
- 最大长度：50 字符

---

## 8. 团队成员重置密码功能设计

### 8.1 功能概述

团队所有者 (TEAM_ADMIN) 在团队成员管理页面可重置成员密码，无需输入旧密码。

### 8.2 UI 设计

**入口位置**：TeamMembers.vue 操作列

在现有操作按钮（分配角色、移除）前添加"重置密码"按钮：

```vue
<template #default="{ row }">
  <el-button size="small" @click="showResetPasswordDialog(row)" v-if="isTeamAdmin">
    <el-icon><Key /></el-icon>
    重置密码
  </el-button>
  <el-button size="small" @click="showAssignRolesDialog(row)" v-if="isTeamAdmin">
    分配角色
  </el-button>
  <el-button size="small" @click="handleRemove(row)" v-if="isTeamAdmin">
    移除
  </el-button>
</template>
```

**对话框设计**：

标题显示成员姓名，仅需要输入新密码和确认密码：

```
┌─────────────────────────────────────┐
│  重置密码 - 张三                  ✕ │
├─────────────────────────────────────┤
│  新密码                             │
│  ┌─────────────────────────────┐   │
│  │ ••••••••                   │   │
│  └─────────────────────────────┘   │
│                                     │
│  确认密码                           │
│  ┌─────────────────────────────┐   │
│  │ ••••••••                   │   │
│  └─────────────────────────────┘   │
│                                     │
│         [取消]    [确认重置]        │
└─────────────────────────────────────┘
```

### 8.3 前端实现

**API 封装** (`src/api/team.ts`)：

```typescript
export interface ResetPasswordRequest {
  new_password: string
}

export const teamApi = {
  // ... 现有方法
  
  // 重置成员密码（新增）
  resetMemberPassword: (teamId: number, userId: number, data: ResetPasswordRequest) => {
    return request.post<{ message: string }>(`/v1/teams/${teamId}/members/${userId}/reset-password`, data)
  }
}
```

**TeamMembers.vue 新增**：

```typescript
// 新增导入
import { Key } from '@element-plus/icons-vue'
import { showSuccess } from '@/utils/errorMessages'
import type { FormInstance, FormRules } from 'element-plus'

// 新增状态
const resetPasswordVisible = ref(false)
const resetPasswordLoading = ref(false)
const resetPasswordFormRef = ref<FormInstance>()
const resetPasswordTargetUser = ref<{ id: number; name: string } | null>(null)

const resetPasswordForm = reactive({
  newPassword: '',
  confirmPassword: '',
})

const validateConfirmPassword = (rule: any, value: string, callback: any) => {
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
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const showResetPasswordDialog = (user: any) => {
  resetPasswordTargetUser.value = { id: user.id, name: user.name }
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
      teamId,
      resetPasswordTargetUser.value.id,
      { new_password: resetPasswordForm.newPassword }
    )
    showSuccess(`已重置 ${resetPasswordTargetUser.value.name} 的密码`)
    resetPasswordVisible.value = false
  } catch (error) {
    console.error('重置密码失败', error)
  } finally {
    resetPasswordLoading.value = false
  }
}
```

### 8.4 后端实现

**Schema 定义** (`app/schemas/team.py`)：

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

**API 实现** (`app/api/teams.py`)：

```python
from app.schemas.team import ResetPasswordRequest
from app.core.security import get_password_hash

@router.post("/{team_id}/members/{user_id}/reset-password", summary="重置成员密码")
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

### 8.5 权限控制

| 检查点 | 实现方式 |
|--------|----------|
| TEAM_ADMIN 验证 | `is_team_admin(db, team_id, current_user.id)` |
| 目标用户存在性 | `user_crud.get_by_id()` |
| 团队归属验证 | `role_crud.get_user_roles()` 检查是否有角色 |
| 前端按钮显示 | `v-if="isTeamAdmin"` 条件渲染 |

### 8.6 安全考虑

| 安全措施 | 实现方式 |
|----------|----------|
| 权限隔离 | 仅 TEAM_ADMIN 可调用 |
| 团队归属验证 | 目标用户必须属于该团队 |
| 密码规则验证 | 6-50 字符，前后端一致 |
| 密码哈希存储 | bcrypt `get_password_hash()` |
| 无通知机制 | 直接修改，不发送邮件 |

---

## 9. 文件清单（更新）

### 9.1 新增文件

无（所有修改都在现有文件中）

### 9.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `CRM-Server/app/schemas/auth.py` | 新增 `ChangePasswordRequest` Schema |
| `CRM-Server/app/schemas/team.py` | 新增 `ResetPasswordRequest` Schema |
| `CRM-Server/app/api/auth.py` | 新增 `/me/change-password` 端点 |
| `CRM-Server/app/api/teams.py` | 新增 `/{team_id}/members/{user_id}/reset-password` 端点 |
| `CRM-Client/src/api/auth.ts` | 新增 `changePassword` API 方法 |
| `CRM-Client/src/api/team.ts` | 新增 `resetMemberPassword` API 方法 |
| `CRM-Client/src/views/Settings.vue` | 新增修改密码按钮和对话框 |
| `CRM-Client/src/views/TeamMembers.vue` | 新增重置密码按钮和对话框 |

---

## 10. 下一步

1. ✅ 用户审核设计文档
2. 编写实现计划（调用 writing-plans skill）
3. 实现代码
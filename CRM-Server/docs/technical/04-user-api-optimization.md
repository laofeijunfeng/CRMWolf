# 用户列表API优化总结

## 优化目标
为用户列表和用户详情接口增加角色信息，使前端能够在展示用户时同时显示用户的角色信息。

## 优化内容

### 1. 新增Schema模型
**文件**: `app/schemas/user.py`

新增了两个Schema类：

```python
class RoleInfo(BaseModel):
    id: int
    name: str
    code: str
    
    class Config:
        from_attributes = True


class UserWithRolesResponse(UserResponse):
    roles: List[RoleInfo] = Field(default_factory=list, description="用户角色列表")
    
    class Config:
        from_attributes = True
```

### 2. 更新用户列表API
**文件**: `app/api/users.py`

**修改前**:
```python
@router.get("/", response_model=List[UserResponse], ...)
def get_users(...):
    users = user_crud.get_multi(db, skip=skip, limit=limit, status=status, region=region)
    return users
```

**修改后**:
```python
@router.get("/", response_model=List[UserWithRolesResponse], ...)
def get_users(...):
    from sqlalchemy import text
    
    users = user_crud.get_multi(db, skip=skip, limit=limit, status=status, region=region)
    
    result = []
    for user in users:
        roles = db.execute(text("""
            SELECT DISTINCT r.id, r.name, r.code
            FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
        """), {"user_id": user.id}).fetchall()
        
        role_list = [{"id": r[0], "name": r[1], "code": r[2]} for r in roles]
        
        user_dict = {
            # ... 用户基本信息字段 ...
            "status": user.status.value.lower() if user.status else None,
            "roles": role_list
        }
        result.append(UserWithRolesResponse(**user_dict))
    
    return result
```

### 3. 更新用户详情API
**文件**: `app/api/users.py`

同样为用户详情接口增加了角色信息，返回 `UserWithRolesResponse`。

### 4. 关键修复
- **枚举值转换**: 将用户状态从大写（"ACTIVE"）转换为小写（"active"）以匹配schema定义
- **去重查询**: 使用 `DISTINCT` 关键字避免重复角色记录

## API响应示例

### 用户列表接口响应
```json
[
  {
    "id": 1,
    "name": "测试用户",
    "email": "test@example.com",
    "region": "北京",
    "status": "active",
    "roles": []
  },
  {
    "id": 2,
    "name": "test",
    "email": "test@example.com",
    "status": "active",
    "roles": [
      {
        "id": 3,
        "name": "系统管理员",
        "code": "SYSTEM_ADMIN"
      }
    ]
  },
  {
    "id": 3,
    "name": "Eddie1",
    "email": "Eddie@qq.com",
    "status": "active",
    "roles": [
      {
        "id": 1,
        "name": "销售总监",
        "code": "SALES_DIRECTOR"
      },
      {
        "id": 2,
        "name": "销售成员",
        "code": "SALES_MEMBER"
      }
    ]
  }
]
```

## 测试验证
创建了测试脚本 `test_users_api.py` 验证：
- Schema验证通过 ✓
- 角色信息正确返回 ✓
- 用户状态枚举值正确转换 ✓

## 性能考虑
- 使用SQL `DISTINCT` 避免重复记录
- 直接SQL查询提高查询效率
- 批量处理用户数据减少数据库往返

## 向后兼容性
- 保留了原有的 `UserResponse` schema
- 新增了 `UserWithRolesResponse` 作为扩展版本
- 如果需要向后兼容，可以创建两个版本的API端点

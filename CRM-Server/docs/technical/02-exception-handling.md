# 异常处理和参数验证改进总结

## 问题分析

之前系统存在以下问题：

1. **参数验证不足**：开发工具接口使用简单的函数参数，没有使用 Pydantic 模型进行验证
2. **缺少全局异常处理器**：没有统一的异常处理机制，错误信息不友好
3. **数据库查询问题**：SQLAlchemy join 查询缺少明确的连接条件
4. **空参数处理不当**：空字符串、None 等情况没有正确处理

## 解决方案

### 1. 创建全局异常处理器

**文件**: `app/core/exceptions.py`

创建了完整的异常处理体系：

- **AppException**: 基础异常类
- **ValidationException**: 验证异常 (422)
- **NotFoundException**: 资源不存在异常 (404)
- **ConflictException**: 资源冲突异常 (409)
- **ForbiddenException**: 权限不足异常 (403)
- **UnauthorizedException**: 未授权异常 (401)

**异常处理器**:
- `app_exception_handler`: 处理应用自定义异常
- `validation_exception_handler`: 处理 FastAPI 请求验证异常
- `pydantic_validation_exception_handler`: 处理 Pydantic 数据验证异常
- `sqlalchemy_exception_handler`: 处理数据库异常
- `generic_exception_handler`: 处理其他未捕获异常

### 2. 改进参数验证

**文件**: `app/schemas/dev.py`

为开发工具接口创建了专门的 Pydantic 模型：

```python
class MockLoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="用户姓名")
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="用户邮箱")
    mobile: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$', description="用户手机号")
    region: str = Field(..., min_length=1, max_length=50, description="所属地区")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('用户姓名不能为空')
        return v.strip()
```

**验证规则**:
- 所有必填字段使用 `Field(...)` 标记
- 字符串长度限制：`min_length=1, max_length=100`
- 邮箱格式验证：正则表达式 `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- 手机号格式验证：正则表达式 `^\+?[1-9]\d{1,14}$`
- 自定义验证器：检查空字符串并自动去除首尾空格

### 3. 修复数据库查询问题

**文件**: `app/crud/role.py` 和 `app/crud/permission.py`

修复了 SQLAlchemy join 查询问题：

```python
# 修复前
return db.query(Role).join(UserRole).filter(UserRole.user_id == user_id).all()

# 修复后
return db.query(Role).join(UserRole, Role.id == UserRole.role_id).filter(UserRole.user_id == user_id).all()
```

### 4. 更新 API 接口

**文件**: `app/api/dev.py`

将所有开发工具接口改为使用 Pydantic 模型：

```python
# 修复前
@router.post("/mock-login")
async def mock_login(
    name: str = "测试用户",
    email: str = "test@example.com",
    mobile: str = "+8613800138000",
    region: str = "北京",
    db: Session = Depends(get_db)
):

# 修复后
@router.post("/mock-login")
async def mock_login(
    request: MockLoginRequest,
    db: Session = Depends(get_db)
):
```

### 5. 更新前端页面

**文件**: `dev_login.html`

将所有 API 调用从 URL 参数改为 JSON body：

```javascript
// 修复前
const response = await fetch(`http://localhost:8000/dev/mock-login?name=${encodeURIComponent(name)}&email=${encodeURIComponent(email)}...`, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    }
});

// 修复后
const response = await fetch('http://localhost:8000/dev/mock-login', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        name: name,
        email: email,
        mobile: mobile,
        region: region
    })
});
```

### 6. 注册全局异常处理器

**文件**: `app/main.py`

在 FastAPI 应用中注册所有异常处理器：

```python
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
```

## 测试结果

### 测试 1: 空参数验证

```bash
curl -X POST "http://localhost:8000/dev/mock-login" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"","mobile":"","region":""}'
```

**响应**:
```json
{
  "error_code": "VALIDATION_ERROR",
  "detail": "请求参数验证失败",
  "errors": [
    {
      "field": "body -> name",
      "message": "String should have at least 1 character",
      "type": "string_too_short"
    },
    {
      "field": "body -> email",
      "message": "String should match pattern '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'",
      "type": "string_pattern_mismatch"
    },
    {
      "field": "body -> mobile",
      "message": "String should match pattern '^\\+?[1-9]\\d{1,14}$'",
      "type": "string_pattern_mismatch"
    },
    {
      "field": "body -> region",
      "message": "String should have at least 1 character",
      "type": "string_too_short"
    }
  ],
  "path": "http://localhost:8000/dev/mock-login"
}
```

### 测试 2: 邮箱格式验证

```bash
curl -X POST "http://localhost:8000/dev/mock-login" \
  -H "Content-Type: application/json" \
  -d '{"name":"张三","email":"invalid-email","mobile":"123","region":"北京"}'
```

**响应**:
```json
{
  "error_code": "VALIDATION_ERROR",
  "detail": "请求参数验证失败",
  "errors": [
    {
      "field": "body -> email",
      "message": "String should match pattern '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'",
      "type": "string_pattern_mismatch"
    }
  ],
  "path": "http://localhost:8000/dev/mock-login"
}
```

### 测试 3: 正常请求

```bash
curl -X POST "http://localhost:8000/dev/mock-login" \
  -H "Content-Type: application/json" \
  -d '{"name":"张三","email":"zhangsan@example.com","mobile":"+8613800138000","region":"北京"}'
```

**响应**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "name": "张三",
    "email": "zhangsan@example.com",
    "mobile": "+8613800138000",
    "region": "北京",
    ...
  }
}
```

### 测试 4: 权限验证

```bash
curl -X GET "http://localhost:8000/users/6" \
  -H "Authorization: Bearer <普通用户token>"
```

**响应**:
```json
{
  "detail": "缺少权限: user:manage"
}
```

### 测试 5: 数据库查询修复

```bash
curl -X GET "http://localhost:8000/users/6" \
  -H "Authorization: Bearer <管理员token>"
```

**响应**:
```json
{
  "name": "张三",
  "email": "zhangsan@example.com",
  "mobile": "+8613800138000",
  "region": "北京",
  ...
}
```

## 改进效果

### 1. 错误信息更友好
- 统一的错误响应格式
- 详细的错误字段和原因
- 清晰的错误代码分类

### 2. 参数验证更严格
- 所有必填字段必须提供
- 格式验证（邮箱、手机号等）
- 长度限制
- 空字符串处理

### 3. 系统更稳定
- 全局异常捕获
- 数据库查询修复
- 避免服务端崩溃

### 4. 开发体验更好
- 清晰的错误提示
- 便于调试
- 符合 RESTful API 规范

## 使用建议

### 1. 在其他接口中使用自定义异常

```python
from app.core.exceptions import NotFoundException, ConflictException

@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = user_crud.get_by_id(db, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    return user
```

### 2. 创建自定义 Pydantic 模型

```python
from pydantic import BaseModel, Field, field_validator

class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('客户名称不能为空')
        return v.strip()
```

### 3. 添加日志记录

```python
import logging

logger = logging.getLogger(__name__)

@router.post("/customers")
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    try:
        result = customer_crud.create(db, customer)
        logger.info(f"客户创建成功: {result.id}")
        return result
    except Exception as e:
        logger.error(f"客户创建失败: {str(e)}")
        raise
```

## 总结

通过以上改进，系统现在具有：

✅ 完善的异常处理机制
✅ 严格的参数验证
✅ 友好的错误提示
✅ 稳定的数据库查询
✅ 良好的开发体验

所有接口现在都能正确处理空参数、格式错误等情况，并返回清晰的错误信息，不会再出现服务端异常。

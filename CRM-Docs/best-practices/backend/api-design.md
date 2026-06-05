# API 设计规范

> 后端 API 设计必须遵循此规范，确保接口统一、易用。

---

## 响应格式统一

### 🟢 推荐做法

```python
# 成功响应
{
    "code": 0,
    "message": "success",
    "data": { ... },
    "timestamp": 1699999999
}

# 错误响应
{
    "error_code": "VALIDATION_ERROR",
    "detail": "参数校验失败",
    "timestamp": 1699999999
}
```

### 列表响应

```python
{
    "code": 0,
    "message": "success",
    "data": [
        { "id": 1, "name": "..." },
        { "id": 2, "name": "..." }
    ],
    "total": 100,
    "page": 1,
    "page_size": 10,
    "timestamp": 1699999999
}
```

---

## 路径规范

### 🟢 推荐做法

```python
# 资源命名使用复数
router = APIRouter(prefix="/v1/customers")

# 操作使用 RESTful 风格
GET    /v1/customers/          # 列表
GET    /v1/customers/{id}      # 详情
POST   /v1/customers/          # 创建
PUT    /v1/customers/{id}      # 更新
DELETE /v1/customers/{id}      # 删除

# 子资源
GET    /v1/customers/{id}/follow-ups/    # 客户跟进列表
POST   /v1/customers/{id}/follow-ups/    # 创建跟进
```

### 🔴 禁止做法

```python
# ❌ 禁止动词路径
/v1/get-customers/
/v1/create-customer/
/v1/delete-customer/

# ❌ 禁止不一致的前缀
/customers/      # 缺少 /v1
/v1/customer/    # 单数形式
```

---

## team_id 必传

### 🔴 强制要求

所有业务接口必须传入 team_id：

```python
@router.get("/customers")
async def list_customers(
    team_id: int = Depends(get_current_user_team),  # 必传
    db: Session = Depends(get_db)
):
    return customer_crud.get_multi(db, team_id=team_id)

@router.post("/customers")
async def create_customer(
    customer_in: CustomerCreate,
    team_id: int = Depends(get_current_user_team),  # 必传
    db: Session = Depends(get_db)
):
    return customer_crud.create(db, customer_in, team_id=team_id)
```

---

## 分页参数

### 🟢 推荐做法

```python
@router.get("/customers")
async def list_customers(
    team_id: int = Depends(get_current_user_team),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    customers, total = customer_crud.get_multi(
        db, team_id=team_id, skip=skip, limit=page_size
    )
    return {
        "code": 0,
        "data": customers,
        "total": total,
        "page": page,
        "page_size": page_size
    }
```

---

## 错误码规范

| 错误码 | 含义 | HTTP 状态码 |
|--------|------|-------------|
| VALIDATION_ERROR | 参数校验失败 | 400 |
| AUTHENTICATION_ERROR | 认证失败 | 401 |
| PERMISSION_ERROR | 权限不足 | 403 |
| NOT_FOUND | 资源不存在 | 404 |
| DATABASE_ERROR | 数据库错误 | 500 |
| INTERNAL_ERROR | 内部错误 | 500 |

### 错误响应实现

```python
from app.core.exceptions import AppException

@router.get("/customers/{id}")
async def get_customer(
    id: int,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get(db, id, team_id)
    if not customer:
        raise AppException(
            error_code="NOT_FOUND",
            detail="客户不存在或无权限访问"
        )
    return {"code": 0, "data": customer}
```

---

## SSE 流式响应

### 🟢 推荐做法

```python
from fastapi.responses import StreamingResponse

@router.post("/ai/test")
async def test_ai(test_in: AITestRequest, db: Session = Depends(get_db)):
    async def generate():
        yield f"data: {json.dumps({'event': 'start', 'message': '开始'})}\n\n"
        # AI 处理
        yield f"data: {json.dumps({'event': 'content', 'content': '...'})}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'success': True})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
    )
```

---

## 权限校验

### 🟢 推荐做法

```python
@router.post("/customers")
async def create_customer(
    customer_in: CustomerCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 权限校验
    permissions = permission_service.get_user_permissions(db, current_user.id)
    if not any(p.code == "customer:create" for p in permissions):
        raise HTTPException(status_code=403, detail="无权限创建客户")
    
    return customer_crud.create(db, customer_in, team_id)
```

---

## 文件上传

### 🟢 推荐做法

```python
@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    # 保存文件
    file_path = save_file(file, team_id)
    
    return {"code": 0, "data": {"path": file_path}}
```

---

## 相关文档

- [crud-patterns.md](crud-patterns.md) - CRUD 操作规范
- [team-isolation.md](team-isolation.md) - 团队隔离规范
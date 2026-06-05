# 团队隔离规范

> 所有数据必须按团队隔离，确保多租户数据安全。

---

## 核心原则

### 🔴 强制要求

**所有数据必须携带 team_id，所有查询必须过滤 team_id**

```
┌─────────────────────────────────────────────────────────────┐
│                      团队隔离架构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API 层                                                      │
│  ├── get_current_user_team: 提取当前用户所属团队              │
│  ├── 所有接口传入 team_id                                    │
│  └── 返回结果按 team_id 过滤                                  │
│                                                             │
│  CRUD 层                                                     │
│  ├── 所有方法接受 team_id 参数                                │
│  ├── 创建时设置 team_id                                       │
│  ├── 查询时过滤 team_id                                       │
│                                                             │
│  Model 层                                                    │
│  ├── team_id = Column(nullable=False, index=True)           │
│  ├── 外键关联也需 team_id                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## team_id 获取方式

### API 层注入

```python
from app.core.deps import get_current_user, get_current_user_team

@router.get("/customers")
async def list_customers(
    team_id: int = Depends(get_current_user_team),  # 自动注入
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return customer_crud.get_multi(db, team_id=team_id)
```

### get_current_user_team 实现

```python
def get_current_user_team(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> int:
    """获取当前用户所属团队"""
    user_team = user_team_crud.get_user_current_team(db, current_user.id)
    if not user_team:
        raise HTTPException(status_code=403, detail="用户未分配团队")
    return user_team.team_id
```

---

## Model 层设计

### 🔴 强制要求

所有业务 Model 必须有 team_id 字段：

```python
class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    team_id = Column(BigInteger, nullable=False, index=True)  # 必须有
    name = Column(String(100), nullable=False)
    # ...
```

### 外键关联

```python
# 关联数据也需要 team_id
class CustomerFollowUp(Base):
    __tablename__ = "customer_follow_ups"
    
    id = Column(BigInteger, primary_key=True)
    team_id = Column(BigInteger, nullable=False, index=True)  # 必须有
    customer_id = Column(BigInteger, ForeignKey("customers.id"))
    content = Column(Text)
```

---

## CRUD 层实现

### 创建操作

```python
def create(self, db: Session, obj_in: Schema, team_id: int) -> Model:
    """创建时设置 team_id"""
    db_obj = Model(
        team_id=team_id,  # 必须设置
        **obj_in.dict()
    )
    db.add(db_obj)
    db.commit()
    return db_obj
```

### 查询操作

```python
def get_multi(self, db: Session, team_id: int, **filters) -> List[Model]:
    """查询时过滤 team_id"""
    query = db.query(Model).filter(Model.team_id == team_id)  # 必须过滤
    return query.all()
```

### 更新/删除操作

```python
def update(self, db: Session, id: int, obj_in: Schema, team_id: int) -> Model:
    """更新时验证 team_id"""
    obj = db.query(Model).filter(
        Model.id == id,
        Model.team_id == team_id  # 必须验证归属
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="记录不存在或无权限")
    # 更新逻辑
```

---

## 违反后果

### 案例：DATABASE_ERROR

```python
# 错误代码
@router.post("/ai/config")
async def save_config(config_in: AIConfigCreate, db: Session = Depends(get_db)):
    config = ai_config_crud.create(db, config_in)  # 缺少 team_id

# Model 约束
team_id = Column(BigInteger, nullable=False)  # 违反约束

# 结果：DATABASE_ERROR "数据库操作失败"
```

### 排查成本

| 问题 | 排查时间 | 原因 |
|------|----------|------|
| team_id 缺失 | 4+ 小时 | Model 约束报错，定位困难 |
| 数据泄露 | 安全风险 | 查询未过滤 team_id |
| 数据混乱 | 维护成本 | 不同团队数据混杂 |

---

## 特殊场景

### 全局配置（无需 team_id）

少数全局配置可以不需要 team_id：

```python
# 全局系统配置（如 AI 配置）
class AIConfig(Base):
    __tablename__ = "ai_configs"
    
    id = Column(BigInteger, primary_key=True)
    team_id = Column(BigInteger, nullable=False, index=True)  # 仍然建议有
    # ...
```

### 跨团队数据（需特殊处理）

```python
# 跨团队访问需显式验证
def get_shared_data(self, db: Session, id: int, team_id: int) -> Optional[Model]:
    obj = db.query(Model).filter(Model.id == id).first()
    if obj and obj.team_id != team_id:
        # 检查是否有跨团队权限
        if not has_cross_team_permission(team_id):
            return None
    return obj
```

---

## 相关文档

- [crud-patterns.md](crud-patterns.md) - CRUD 操作规范
- [api-design.md](api-design.md) - API 设计规范
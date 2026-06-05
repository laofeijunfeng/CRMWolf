# CRUD 操作规范

> 后端数据库操作必须遵循此规范，确保团队隔离、数据安全。

---

## CRUD 层统一入口

### 🟢 强制要求

所有数据库操作必须通过 CRUD 层，禁止绕过：

```python
# 正确：通过 CRUD 层
customer_crud.get_multi(db, team_id=team_id)
customer_crud.create(db, obj_in=customer_data, team_id=team_id)
customer_crud.update(db, db_obj=customer, obj_in=update_data)

# 🔴 禁止：直接 query
db.query(Customer).filter(Customer.team_id == team_id).all()
db.query(Customer).filter(Customer.id == id).first()
```

---

## team_id 必传

### 🟢 强制要求

所有 CRUD 操作必须传入 team_id：

```python
# CRUD 层定义
class CustomerCRUD:
    def get_multi(
        self,
        db: Session,
        team_id: int,  # 必传
        skip: int = 0,
        limit: int = 100
    ) -> List[Customer]:
        return db.query(Customer).filter(
            Customer.team_id == team_id  # 过滤
        ).offset(skip).limit(limit).all()
    
    def create(
        self,
        db: Session,
        obj_in: CustomerCreate,
        team_id: int  # 必传
    ) -> Customer:
        db_obj = Customer(
            team_id=team_id,  # 设置
            **obj_in.dict()
        )
        db.add(db_obj)
        db.commit()
        return db_obj

# API 层调用
@router.get("/customers")
async def list_customers(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    return customer_crud.get_multi(db, team_id=team_id)
```

---

## CRUD 调用链

```
┌─────────────────────────────────────────────────────────────┐
│                        CRUD 调用链                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API 层                                                      │
│  ├── 提取 team_id (get_current_user_team)                   │
│  ├── 验证权限                                                │
│  └── 调用 CRUD                                               │
│      ↓                                                      │
│  CRUD 层                                                     │
│  ├── 传入 team_id 参数                                       │
│  ├── team_id 过滤/设置                                       │
│  └── 返回结果                                                │
│      ↓                                                      │
│  Model 层                                                    │
│  ├── team_id = Column(nullable=False)  # 约束               │
│  └── 数据库存储                                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 违反后果

| 违反方式 | 后果 | 排查成本 |
|----------|------|----------|
| 绕过 CRUD 层 | team_id 缺失 → DATABASE_ERROR | 4+ 小时 |
| CRUD 不传 team_id | 违反 nullable=False 约束 | 4+ 小时 |
| Model 层无约束 | 数据隔离失效 | 安全风险 |

---

## CRUD 文件结构

```python
# crud/customer.py
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate

class CustomerCRUD:
    """客户 CRUD 操作"""
    
    def get(self, db: Session, id: int, team_id: int) -> Optional[Customer]:
        """获取单个"""
        return db.query(Customer).filter(
            Customer.id == id,
            Customer.team_id == team_id
        ).first()
    
    def get_multi(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        **filters
    ) -> List[Customer]:
        """获取列表"""
        query = db.query(Customer).filter(Customer.team_id == team_id)
        # 应用其他过滤
        for key, value in filters.items():
            if value:
                query = query.filter getattr(Customer, key) == value)
        return query.offset(skip).limit(limit).all()
    
    def create(self, db: Session, obj_in: CustomerCreate, team_id: int) -> Customer:
        """创建"""
        db_obj = Customer(team_id=team_id, **obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, db_obj: Customer, obj_in: CustomerUpdate) -> Customer:
        """更新"""
        for field in obj_in.dict(exclude_unset=True):
            setattr(db_obj, field, obj_in.dict()[field])
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, id: int, team_id: int) -> bool:
        """删除"""
        obj = self.get(db, id, team_id)
        if obj:
            db.delete(obj)
            db.commit()
            return True
        return False

customer_crud = CustomerCRUD()
```

---

## CRUD 命名规范

| 方法 | 命名 | 用途 |
|------|------|------|
| 获取单个 | `get` | 按 ID 获取 |
| 获取列表 | `get_multi` | 批量获取 |
| 创建 | `create` | 新增记录 |
| 更新 | `update` | 修改记录 |
| 删除 | `delete` | 删除记录 |
| 按名称获取 | `get_by_name` | 按唯一字段获取 |

---

## 特殊 CRUD 场景

### 关联数据 CRUD

```python
# 跟进记录 CRUD（关联客户）
class CustomerFollowUpCRUD:
    def get_by_customer(
        self,
        db: Session,
        customer_id: int,
        team_id: int,  # 仍然需要 team_id
        skip: int = 0,
        limit: int = 100
    ) -> List[CustomerFollowUp]:
        # 验证客户属于该团队
        customer = customer_crud.get(db, customer_id, team_id)
        if not customer:
            return []
        
        return db.query(CustomerFollowUp).filter(
            CustomerFollowUp.customer_id == customer_id
        ).offset(skip).limit(limit).all()
```

### 统计查询

```python
# 统计查询也需要 team_id
def count_by_status(self, db: Session, team_id: int) -> Dict[str, int]:
    return db.query(
        Customer.status,
        func.count(Customer.id)
    ).filter(
        Customer.team_id == team_id
    ).group_by(Customer.status).all()
```

---

## 相关文档

- [team-isolation.md](team-isolation.md) - 团队隔离规范
- [api-design.md](api-design.md) - API 设计规范
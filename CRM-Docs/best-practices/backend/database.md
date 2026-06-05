# 数据库操作规范

> 后端数据库操作必须遵循此规范，确保数据安全、性能稳定。

---

## Model 定义规范

### 🟢 推荐做法

```python
class Customer(Base):
    __tablename__ = "customers"
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 团队隔离（必须有）
    team_id = Column(BigInteger, nullable=False, index=True)
    
    # 业务字段
    name = Column(String(100), nullable=False)
    status = Column(Integer, default=0, index=True)
    
    # 时间字段
    created_time = Column(DateTime, default=datetime.now)
    updated_time = Column(DateTime, onupdate=datetime.now)
    
    # 外键
    owner_id = Column(BigInteger, ForeignKey("users.id"))
```

---

## 约束规范

### 必须有的约束

| 约束类型 | 说明 | 示例 |
|----------|------|------|
| nullable=False | 不能为空 | team_id, name |
| index=True | 常查询字段 | team_id, status |
| ForeignKey | 外键关联 | owner_id → users.id |

### 🔴 禁止缺少的约束

```python
# ❌ 错误：team_id 没有 nullable=False
team_id = Column(BigInteger)  # 可能为空，违反团队隔离

# ✅ 正确
team_id = Column(BigInteger, nullable=False, index=True)
```

---

## 查询规范

### 🟢 推荐做法

```python
# 通过 CRUD 层查询
customers = customer_crud.get_multi(db, team_id=team_id)

# 批量查询使用 limit
customers = customer_crud.get_multi(db, team_id=team_id, limit=100)

# 索引字段过滤
customers = db.query(Customer).filter(
    Customer.team_id == team_id,  # 有索引
    Customer.status == 1          # 有索引
).all()
```

### 🔴 禁止做法

```python
# ❌ 禁止绕过 CRUD
db.query(Customer).all()

# ❌ 禁止无 team_id 过滤
db.query(Customer).filter(Customer.name == "xxx").all()

# ❌ 禁止全表扫描（无索引字段）
db.query(Customer).filter(Customer.description.like("%xxx%")).all()
```

---

## 事务处理

### 🟢 推荐做法

```python
# CRUD 层内处理事务
def create_with_related(self, db: Session, obj_in: Schema, team_id: int):
    try:
        # 创建主记录
        main_obj = Model(team_id=team_id, **obj_in.dict())
        db.add(main_obj)
        db.flush()  # 获取 ID
        
        # 创建关联记录
        related_obj = RelatedModel(main_id=main_obj.id, team_id=team_id)
        db.add(related_obj)
        
        db.commit()
        return main_obj
    except Exception:
        db.rollback()
        raise
```

### 🔴 禁止做法

```python
# ❌ 禁止忘记 commit
db.add(obj)
# 没有 db.commit()

# ❌ 禁止忘记 rollback
try:
    db.add(obj)
    db.commit()
except Exception:
    # 没有 db.rollback()
    raise
```

---

## 批量操作

### 🟢 推荐做法

```python
# 批量创建
def create_multi(self, db: Session, objs_in: List[Schema], team_id: int):
    db_objs = [Model(team_id=team_id, **obj.dict()) for obj in objs_in]
    db.add_all(db_objs)
    db.commit()
    return db_objs

# 批量更新
def update_status_multi(self, db: Session, ids: List[int], status: int, team_id: int):
    db.query(Model).filter(
        Model.id.in_(ids),
        Model.team_id == team_id
    ).update({Model.status: status})
    db.commit()
```

---

## 性能优化

### 查询优化

| 场景 | 优化方式 |
|------|----------|
| 分页查询 | offset + limit |
| 大表查询 | 添加索引 |
| 关联查询 | 使用 join，避免 N+1 |
| 计数查询 | func.count() |

### N+1 问题

```python
# ❌ N+1 问题
customers = db.query(Customer).all()
for c in customers:
    follow_ups = db.query(FollowUp).filter(FollowUp.customer_id == c.id).all()  # N 次查询

# ✅ 使用 join
customers = db.query(Customer).options(
    joinedload(Customer.follow_ups)
).all()
```

---

## Model 命名规范

| 类型 | 命名 | 示例 |
|------|------|------|
| Model 类 | PascalCase | Customer, CustomerFollowUp |
| 表名 | snake_case | customers, customer_follow_ups |
| 字段名 | snake_case | team_id, created_time |

---

## 关联关系

### 🟢 推荐做法

```python
class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(BigInteger, primary_key=True)
    team_id = Column(BigInteger, nullable=False, index=True)
    
    # 关系定义
    follow_ups = relationship("CustomerFollowUp", back_populates="customer")
    owner = relationship("User")

class CustomerFollowUp(Base):
    __tablename__ = "customer_follow_ups"
    
    id = Column(BigInteger, primary_key=True)
    team_id = Column(BigInteger, nullable=False, index=True)
    customer_id = Column(BigInteger, ForeignKey("customers.id"))
    
    # 关系定义
    customer = relationship("Customer", back_populates="follow_ups")
```

---

## 相关文档

- [crud-patterns.md](crud-patterns.md) - CRUD 操作规范
- [team-isolation.md](team-isolation.md) - 团队隔离规范
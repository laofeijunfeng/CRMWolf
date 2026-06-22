# 后端开发规则

**适用范围**：CRM-Server/app 所有 Python 文件

---

## Pydantic 强制校验

| 规则 | 要求 |
|------|------|
| 外部输入校验 | 所有外部输入必须 Pydantic 校验 |
| 禁止裸 dict | 禁止裸 dict 作为参数或返回值 |

```python
# 正确
from app.schemas.customer import CustomerCreate, CustomerResponse

def create_customer(data: CustomerCreate) -> CustomerResponse:
    ...

# 禁止
def create_customer(data: dict) -> dict:
    ...
```

---

## CRUD 层统一入口

### 强制要求

| 规则 | 要求 |
|------|------|
| 统一入口 | 所有数据库操作必须通过 CRUD 层 |
| 禁止直接 query | 禁止绕过 CRUD 使用 `db.query()` |

```python
# 正确：通过 CRUD 层
customer_crud.get_multi(db, team_id=team_id)
customer_crud.create(db, obj_in=customer_data, team_id=team_id)

# 禁止：直接 query
db.query(Customer).filter(Customer.team_id == team_id).all()
```

### 命名规范

| 方法 | 命名 | 用途 |
|------|------|------|
| 获取单个 | `get` | 按 ID 获取 |
| 获取列表 | `get_multi` | 批量获取 |
| 创建 | `create` | 新增记录 |
| 更新 | `update` | 修改记录 |
| 删除 | `delete` | 删除记录 |

---

## team_id 必传规则

### 核心原则

**所有数据必须携带 team_id，所有查询必须过滤 team_id**

### 三层架构

| 层级 | 职责 |
|------|------|
| API 层 | `get_current_user_team` 提取 team_id，传入 CRUD |
| CRUD 层 | 创建时设置 team_id，查询时过滤 team_id |
| Model 层 | `team_id = Column(BigInteger, nullable=False, index=True)` |

### 必须添加 team_id 的表

| 表类型 | 示例 |
|--------|------|
| 业务实体表 | customers, leads, opportunities, contracts |
| 配置表 | opportunity_stages, approval_flows, procurement_methods |
| 日志表 | operation_logs, conversation_logs, approval_records |
| 团队资源表 | ai_config, api_keys |

### 不需要 team_id 的表

| 表类型 | 示例 |
|--------|------|
| 系统级配置 | roles, permissions, ai_skills |
| 团队关系表 | teams, user_teams |
| 用户表 | users |

---

## API 响应格式统一

```python
# 成功
{"code": 0, "message": "success", "data": {...}, "timestamp": ...}

# 错误
{"error_code": "VALIDATION_ERROR", "detail": "...", "timestamp": ...}
```

### 错误码规范

| 错误码 | HTTP 状态码 |
|--------|-------------|
| VALIDATION_ERROR | 400 |
| AUTHENTICATION_ERROR | 401 |
| PERMISSION_ERROR | 403 |
| NOT_FOUND | 404 |
| DATABASE_ERROR | 500 |

---

## 数据库迁移规则

| 操作 | 正确方式 | 错误方式 |
|------|----------|----------|
| 新增字段 | `alembic revision` → upgrade/downgrade | 独立 `.py` 脚本 |
| 修改字段 | Alembic migration | 直接改模型不写迁移 |
| 新建表 | Alembic migration | `Base.metadata.create_all()` |

### 标准流程

```bash
alembic revision -m "描述变更内容"  # 创建迁移文件
alembic upgrade head               # 执行迁移
alembic current                    # 验证版本
```

---

## 禁止行为汇总

| 禁止 | 原因 |
|------|------|
| 裸 dict 作为参数 | 违反 Pydantic 校验 |
| 绕过 CRUD 直接 query | team_id 缺失风险 |
| CRUD 不传 team_id | 违反隔离约束 |
| 独立数据库脚本 | 违反迁移规范 |
| 无 team_id 过滤查询 | 数据隔离失效 |

---

## 代码复用

实现功能前必须先搜索现有实现：

| 复用场景 | 搜索关键词 | 复用目标 |
|----------|------------|----------|
| 时间解析 | `parse_relative_time`, `parse_date` | `follow_up_parser_service` |
| ID 提取 | `extract_id`, `ID_PATTERN` | `follow_up_parser_service` |
| 枚举匹配 | `enum_mapping`, `get_enum` | `ai_enum_mapping_crud` |

---

**详细参考**：`CRM-Docs/best-practices/backend/crud-patterns.md`, `CRM-Docs/best-practices/backend/team-isolation.md`
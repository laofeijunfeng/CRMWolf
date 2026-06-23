# 贡献指南

感谢你对 CRMWolf 项目的关注！本文档定义了项目的开发规范和红线规则。

---

## 🚨 开发红线（不可违反）

### TypeScript 四禁令

| 禁令 | 曝光后果 | 替代方案 |
|------|----------|----------|
| `: any` | 阻止提交 | 使用 Approved Types |
| `as any` | 阻止提交 | 使用 Zod 校验 + Approved Types |
| `@ts-ignore` | 阻止提交 | 修复错误源，不隐藏 |
| `!` 非空断言 | 阻止提交 | 使用 `?.` 条件判断 |

**正确示例**：
```typescript
// ❌ 禁止
const params: any = { page: 1 }
const response = await api.getCustomers() as any
// @ts-ignore
someUntypedFunction()
const id = customer.value!.id

// ✅ 正确
const params: PaginationParams = { page: 1, pageSize: 20 }
const response = CustomerListResponseSchema.parse(await api.getCustomers())
function someTypedFunction(): void { ... }
const id = customer.value?.id ?? 0
```

### 分支纪律

- ✅ **修改前必须新建特性分支**
- ❌ **禁止直接推送 `main` 或 `master` 分支**

```bash
# 创建新特性分支
git checkout main
git checkout -b feat/功能名称

# 开发完成后提交 Pull Request
```

---

## 前端开发规范

### Vue 组件规范

**Props 规范**：
```typescript
// ✅ 正确
const props = defineProps({
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  }
})

// ❌ 禁止
const props = defineProps({ customer: Object })  // 无类型
```

**Emits 规范**：
```typescript
// ✅ 正确
const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
  (e: 'delete', id: number): void
}>()

// ❌ 禁止
const emit = defineEmits(['update', 'delete'])  // 无类型
```

### Pinia Store 规范

**State 类型声明**：
```typescript
// ✅ 正确
const loading = ref<boolean>(false)
const items = ref<CustomerResponse[]>([])

// ❌ 禁止
const loading = ref(false)  // 无类型
const data = ref<any>(null)  // 使用 any
```

**解构规则**：
```typescript
// ✅ 正确 - State/Computed 使用 storeToRefs
const { items, loading } = storeToRefs(store)

// ✅ 正确 - Actions 直接解构
const { fetchList, create } = store

// ❌ 禁止 - State 直接解构（失去响应性）
const { items } = store
```

---

## 后端开发规范

### Pydantic 强制校验

```python
# ✅ 正确
from app.schemas.customer import CustomerCreate, CustomerResponse

def create_customer(data: CustomerCreate) -> CustomerResponse:
    ...

# ❌ 禁止
def create_customer(data: dict) -> dict:
    ...
```

### CRUD 层统一入口

```python
# ✅ 正确：通过 CRUD 层
customer_crud.get_multi(db, team_id=team_id)
customer_crud.create(db, obj_in=customer_data, team_id=team_id)

# ❌ 禁止：直接 query
db.query(Customer).filter(Customer.team_id == team_id).all()
```

### team_id 必传规则

**所有数据必须携带 team_id，所有查询必须过滤 team_id**

三层架构：
- API 层：`get_current_user_team` 提取 team_id，传入 CRUD
- CRUD 层：创建时设置 team_id，查询时过滤 team_id
- Model 层：`team_id = Column(BigInteger, nullable=False, index=True)`

---

## 测试规范

### 覆盖率要求

| 代码类型 | 覆盖率要求 | 校验时机 |
|----------|------------|----------|
| 新增组件 | 100% | pre-push |
| 新增 Store | 100% | pre-push |
| 新增 API | 100% | pre-push |
| 新增 Service | 100% | pre-push |
| 存量代码 | ≥80% | CI |

### 前端测试（Vitest）

```bash
npm run test:unit                 # 运行所有测试
npm run test:unit -- file.test.ts # 运行特定文件
npm run coverage                  # 生成覆盖率报告
```

### 后端测试（pytest）

```bash
pytest tests/unit -v                     # 运行单元测试
pytest tests/unit --cov=app              # 生成覆盖率报告
pytest tests/unit --cov=app --cov-report=html  # HTML 报告
```

---

## 数据库迁移规范

**所有数据库变更必须使用 Alembic 迁移**

```bash
alembic revision -m "描述变更内容"  # 创建迁移文件
alembic upgrade head               # 执行迁移
alembic current                    # 验证版本
```

---

## API 响应格式

```python
# 成功
{"code": 0, "message": "success", "data": {...}, "timestamp": ...}

# 错误
{"error_code": "VALIDATION_ERROR", "detail": "...", "timestamp": ...}
```

---

## 禁止行为汇总

| 禁止 | 原因 |
|------|------|
| TypeScript 四禁令 | 违反类型安全 |
| Props/State 使用 any | 违反类型安全 |
| 裸 dict 作为参数 | 违反 Pydantic 校验 |
| 绕过 CRUD 直接 query | team_id 缺失风险 |
| CRUD 不传 team_id | 违反数据隔离约束 |
| 独立数据库脚本 | 违反迁移规范 |
| 直接推送 main 分支 | 违反分支纪律 |
| 跳过测试 | 违反覆盖率要求 |
| 不写测试直接提交 | 违反红线 |

---

## 提交规范

### Commit Message 格式

```
type(scope): subject

# 示例
feat(customer): add customer import feature
fix(api): resolve team_id missing issue
docs(readme): update installation guide
```

### Type 类型

| Type | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| style | 代码格式调整 |
| refactor | 重构 |
| test | 测试相关 |
| chore | 构建/工具相关 |

---

## 开发流程

### 1. Fork 并克隆仓库

```bash
git clone https://github.com/你的用户名/CRMWolf.git
cd CRMWolf
```

### 2. 创建特性分支

```bash
git checkout main
git checkout -b feat/功能名称
```

### 3. 开发并测试

```bash
# 前端
cd CRM-Client
npm run lint          # ESLint 校验
npm run type-check    # TypeScript 类型检查
npm run test:unit     # 运行测试

# 后端
cd CRM-Server
ruff check app/       # Python lint
mypy app/             # 类型检查
pytest tests/unit -v  # 运行测试
```

### 4. 提交代码

```bash
git add .
git commit -m "feat(scope): 功能描述"
git push origin feat/功能名称
```

### 5. 创建 Pull Request

- 在 GitHub 创建 Pull Request
- 等待代码审查
- 确保所有测试通过后合并

---

## 详细文档

更多详细信息请参考：

| 文档 | 说明 |
|------|------|
| [CRM-Client/docs/TYPESCRIPT.md](CRM-Client/docs/TYPESCRIPT.md) | TypeScript 类型定义 |
| [CRM-Client/docs/COMPONENTS.md](CRM-Client/docs/COMPONENTS.md) | Vue 组件规范 |
| [CRM-Client/docs/STATE-MANAGEMENT.md](CRM-Client/docs/STATE-MANAGEMENT.md) | Pinia Store 规范 |
| [CRM-Docs/best-practices/backend/crud-patterns.md](CRM-Docs/best-practices/backend/crud-patterns.md) | CRUD 操作模板 |
| [CRM-Docs/best-practices/backend/team-isolation.md](CRM-Docs/best-practices/backend/team-isolation.md) | team_id 隔离架构 |
| [CRM-Docs/system/GLOSSARY.md](CRM-Docs/system/GLOSSARY.md) | 权限码/状态枚举 |

---

## 获取帮助

如有问题，请：
- 查阅文档：`CRM-Docs/`
- 提交 Issue：[GitHub Issues](https://github.com/laofeijunfeng/CRMWolf/issues)

---

**感谢你的贡献！**
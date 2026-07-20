# 开发协作约定

本文档只保留当前项目仍执行的开发红线和协作规则。具体前端 UI 规范以 `CRM-Docs/design-system/` 为准，部署说明以 `CRM-Docs/deployment/` 为准。

## 基本原则

- 不在根目录新增临时计划、阶段总结、验证报告或一次性测试脚本。
- 新增业务代码要遵循现有模块结构，不绕过既有 API、CRUD、Store、组件封装。
- 数据库结构变更必须通过 Alembic migration 交付。
- 前端新页面和改造页面必须遵循 V2 设计规范。
- 历史 V1 样式、Element Plus 主题变量、旧 FilterPanel、旧表头筛选和 Claude Code 文件均已废弃，不再新增依赖。

## 前端红线

### TypeScript

禁止：

- `: any`
- `as any`
- `@ts-ignore`
- 非必要的非空断言 `!`

优先使用：

- 明确的接口类型
- Zod 校验
- `unknown` + 类型收窄
- `?.`、`??` 处理空值

```typescript
// 禁止
const params: any = { page: 1 }
const response = await api.getCustomers() as any
// @ts-ignore
someUntypedFunction()
const id = customer.value!.id

// 推荐
const params: PaginationParams = { page: 1, pageSize: 20 }
const response = CustomerListResponseSchema.parse(await api.getCustomers())
const id = customer.value?.id ?? 0
```

### Vue / Pinia

- Props、Emits 必须有类型。
- Store 的 state/computed 解构使用 `storeToRefs`。
- Actions 可以直接解构。
- 不新增无类型 `ref<any>()`、`reactive<any>()`。

```typescript
const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
  (e: 'delete', id: number): void
}>()
```

### UI 规范

- 新增页面、Sheet、表格、列表卡片、表单必须先看 `CRM-Docs/design-system/README.md`。
- 列表页优先复用现有 ListCard、DataTable、工具栏、Sheet 组件模式。
- 不新增 Element Plus 组件、旧 SCSS token、`variables.scss`、`wolf-design.scss`。
- 不恢复已废弃组件，例如旧 `FilterPanel`、旧 `FilterTableHeader`。

## 后端红线

### Pydantic

API 入参和出参必须使用 Pydantic schema，不使用裸 `dict` 作为业务边界。

```python
from app.schemas.customer import CustomerCreate, CustomerResponse

def create_customer(data: CustomerCreate) -> CustomerResponse:
    ...
```

### CRUD 和 team_id

- 多租户数据必须携带 `team_id`。
- 查询必须过滤 `team_id`。
- API 层负责从当前用户上下文取得团队信息并传入服务/CRUD。
- 不在 API 层随意直接 `db.query(...)` 绕过既有 CRUD 规则。

### 数据库迁移

所有表结构变更必须创建 Alembic migration：

```bash
cd CRM-Server
alembic revision -m "change description"
alembic upgrade head
alembic current
```

不要用一次性 SQL 文件或临时 Python 脚本替代 migration。

## 本地开发

### 前端

```bash
cd CRM-Client
npm install
npm run dev
```

常用检查：

```bash
npm run lint
npm run type-check
npm run test:unit
```

### 后端

```bash
cd CRM-Server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./run.sh
```

常用检查：

```bash
ruff check app/
mypy app/
pytest tests/unit -v
```

本地开发不再使用 Docker Compose。

## 测试要求

- 修复 bug 时，优先补对应回归测试。
- 新增共享组件、Store、API、Service 时，需要补覆盖核心行为的测试。
- 小范围样式调整可以不强制补测试，但要保证 lint/type-check 通过。
- 数据库 migration 需要至少本地执行 `alembic upgrade head` 验证。

## 提交建议

提交信息建议使用：

```text
type(scope): subject
```

常用 type：

| Type | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| refactor | 重构 |
| test | 测试相关 |
| chore | 构建、工具、清理 |

## 文档入口

| 文档 | 用途 |
|------|------|
| [CRM-Docs/design-system/README.md](CRM-Docs/design-system/README.md) | V2 设计规范 |
| [CRM-Docs/design-system/patterns/list-page.md](CRM-Docs/design-system/patterns/list-page.md) | 列表页规范 |
| [CRM-Docs/design-system/components/table.md](CRM-Docs/design-system/components/table.md) | 表格规范 |
| [CRM-Docs/design-system/components/modal-sheet.md](CRM-Docs/design-system/components/modal-sheet.md) | Sheet / 弹窗规范 |
| [CRM-Docs/deployment/README.md](CRM-Docs/deployment/README.md) | 服务器部署说明 |

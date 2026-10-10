# License、部署与合同客户 ID 边界统一设计

- 日期：2026-10-09
- 状态：设计已获批准，待文档审阅
- 范围：统一 License 申请、部署信息、合同创建接口的客户/商机 ID 边界；修复外部 public ID 与内部数据库整数 ID 混用导致的创建失败；将可预期业务校验错误返回为 HTTP 400
- 非范围：不修改数据库表结构；不新增 Alembic migration；不修改客户、部署、合同的读取响应契约；不修改 Assistant 相关工作区改动；不改变现有审批、智能刷新和文件存储业务语义

## 1. 问题

系统对客户同时使用两种身份：

- API 对外使用客户 `public_id`，例如 `cus_599504a4ccd544a380da7695dc462d1f`。
- 数据库外键、ORM 模型和内部 CRUD 使用客户整数主键，例如 `230`。

当前三个创建入口在同一个 Pydantic 请求模型生命周期内修改 ID 语义：API 先用 public ID 做权限校验，再将 `customer_id` 改写为整数主键后继续把外部 schema 传入 CRUD。License CRUD 仍按 `Customer.public_id` 查询，因此会执行等价于 `Customer.public_id == 230` 的错误查询并抛出 `ValueError("客户不存在")`。部署和合同创建目前也依赖相同的隐式转换模式，继续保留同类风险。

License 创建没有捕获该业务 `ValueError`，因此预期的关联校验错误被全局异常处理器包装成 `500 INTERNAL_ERROR`；部署创建也缺少对应映射。

## 2. 决策

采用严格分层，不让 CRUD 同时兼容 public ID 和内部整数 ID：

1. 外部 API schema 只表达 public ID。
2. API 层完成 public ID 解析、当前团队校验和权限校验。
3. API 层构造独立的内部 create schema，显式传入整数主键。
4. 内部 CRUD 只接收内部 schema 或已经明确为内部整数的参数。
5. CRUD 不再自行猜测 ID 类型，也不接受同一字段的双重语义。
6. 预期的业务 `ValueError` 在创建路由转换为 HTTP 400；数据库异常和未知异常继续走现有错误处理链路。
7. 所有客户、商机、部署和合同关联查询继续带当前 `team_id` 过滤。

数据流固定为：

```text
HTTP public ID
    -> API 权限校验与 public ID 解析
内部整数 ID
    -> InternalCreate / typed internal arguments
CRUD 与 ORM 外键
    -> 现有 response mapper
HTTP public ID
```

## 3. 外部 API 契约

外部请求和响应保持兼容。

### 3.1 客户 ID

以下创建请求继续接收客户 public ID 字符串：

- `POST /v1/license-applications/`
- `POST /v1/deployment-infos/`
- `POST /v1/contracts/`

示例：

```json
{
  "customer_id": "cus_599504a4ccd544a380da7695dc462d1f"
}
```

响应仍通过现有 response mapper 返回 `cus_...`，不向前端暴露数据库客户整数主键。

### 3.2 合同商机 ID

手动创建合同的 `ContractCreate.opportunity_id` 继续使用商机 public ID。`/from-opportunity/{opportunity_id}` 路径参数也继续使用商机 public ID。API 在进入合同 CRUD 前解析为当前团队内的商机整数主键。

部署信息 ID、合同 ID、联系人 ID 当前已经是内部整数引用，本次不把它们改成 public ID，也不扩大本次 ID 边界重构范围。

### 3.3 不变的外部模型

保留以下外部模型作为 FastAPI 请求边界：

- `LicenseApplicationCreate`
- `DeploymentInfoCreate`
- `ContractCreate`
- `LicenseApplicationUpdate`
- `DeploymentInfoUpdate`
- `ContractUpdate`

不再对这些外部模型执行把 `customer_id` 或 `opportunity_id` 改写为内部整数的 `model_copy(update=...)` 操作。

## 4. 内部 schema 与转换

沿用现有 `SalesCommitmentInternalCreate` 命名模式，新增以下内部创建模型：

```python
class LicenseApplicationInternalCreate(BaseModel):
    customer_id: int
    deployment_info_id: int | None = None
    contract_id: int | None = None
    license_type: LicenseType
    authorized_users: int
    expiry_date: date
    remark: str | None = None


class DeploymentInfoInternalCreate(BaseModel):
    customer_id: int
    deployment_name: str
    server_address: str
    authorized_users: int | None = None
    is_default: bool = False


class ContractInternalCreate(BaseModel):
    customer_id: int
    opportunity_id: int
    signing_contact_id: int
    contract_name: str
    user_count: int
    total_amount: Decimal
    license_type: LicenseTypeEnum
    subscription_years: int | None = None
    signing_date: date | None = None
    effective_date: date | None = None
    owner_id: str | None = None
```

实际实现应复用现有字段约束和验证器，避免内部模型绕过外部 schema 的金额、数量、日期、URL、名称和订阅年限校验。可将不含 ID 的字段和验证器抽到共享 base model，再由外部和内部模型分别添加 public/int ID 字段；不得通过在同一个模型实例中改变字段语义来复用。

内部 schema 的规则：

- `customer_id` 必须是 `int`。
- `opportunity_id` 必须是 `int`。
- 内部 schema 不直接作为 FastAPI 外部请求体。
- 外部模型仍负责解析用户输入；API 转换时只复制已验证字段和已解析的内部 ID。
- `team_id` 继续作为 API/CRUD 的显式参数，不隐藏在外部请求体中。

### 4.1 License 创建

API 流程：

1. 使用外部 `application.customer_id` 调用 `check_customer_edit_permission`。
2. 该函数按当前 `team_id` 查找客户并检查权限。
3. 使用返回的 `customer.id` 构造 `LicenseApplicationInternalCreate`。
4. 将内部 schema 传给 `create_license_application`。
5. 创建成功后使用现有 `_license_application_response` 返回 public ID。

不得再将 `customer.id` 写回 `LicenseApplicationCreate`。

### 4.2 部署信息创建

API 流程：

1. 使用外部 `deployment.customer_id` 调用 `check_customer_edit_permission`。
2. 使用返回的 `customer.id` 构造 `DeploymentInfoInternalCreate`。
3. 将内部 schema 传给部署 CRUD。
4. 创建成功后使用现有 `_deployment_response` 返回 public ID。

部署创建 CRUD 仍使用内部整数客户外键。其客户归属校验必须以当前 `team_id` 为边界；API 权限校验是第一道边界，CRUD 不能通过缺失团队条件的查询重新引入跨租户关联。

### 4.3 手动合同创建

API 流程：

1. 使用外部 `contract.customer_id` 调用 `check_customer_edit_permission`，得到当前团队内的客户对象。
2. 使用外部 `contract.opportunity_id` 调用现有 `_get_opportunity_by_public_id_or_404`，得到当前团队内的商机对象。
3. 用内部客户 ID检查联系人归属，用内部客户 ID检查商机归属。
4. 构造 `ContractInternalCreate(customer_id=customer.id, opportunity_id=opportunity.id, ...)`。
5. 将内部 schema 传给 `contract_crud.create`。
6. 文件存储、合同加锁、提交审批、智能刷新和 response mapper 保持现有顺序与语义。

不得再将内部 ID 写回 `ContractCreate`。

### 4.4 从商机创建合同

路径参数仍为商机 public ID。API 先通过 `_get_opportunity_by_public_id_or_404` 解析并限定当前团队，再用该商机的内部 `opportunity.id` 和 `opportunity.customer_id` 调用 `create_from_opportunity`。该 CRUD 方法已经使用内部整数参数，因此继续保留 typed integer 参数，不需要让它接受 public ID。

同时补齐该方法中客户和商机查询的 `team_id` 条件，防止已解析的内部 ID在 CRUD 层被跨团队使用。

## 5. CRUD 接口与查询边界

### 5.1 License CRUD

`LicenseApplicationCRUD.create` 和便捷函数改为接收：

```python
obj_in: LicenseApplicationInternalCreate
```

客户查询改为：

```python
Customer.id == obj_in.customer_id
Customer.team_id == team_id
```

部署、合同关联查询继续同时过滤：

```python
DeploymentInfo.id == obj_in.deployment_info_id
DeploymentInfo.team_id == team_id
DeploymentInfo.customer_id == customer.id

Contract.id == obj_in.contract_id
Contract.team_id == team_id
Contract.customer_id == customer.id
```

CRUD 不再读取 `Customer.public_id` 来解析客户，也不再接受 `LicenseApplicationCreate`。

### 5.2 Deployment CRUD

`DeploymentInfoCRUD.create` 和 `create_deployment_info` 改为接收 `DeploymentInfoInternalCreate`。所有写入和默认值清理逻辑使用内部整数 `customer_id`。

如果创建流程需要在 CRUD 层验证客户存在或归属，查询必须同时使用 `Customer.id == customer_id` 和 `Customer.team_id == team_id`。不能用不带团队条件的客户查询作为内部写入依据。

### 5.3 Contract CRUD

手动创建的 `contract_crud.create` 改为接收 `ContractInternalCreate`。其现有客户、商机、重复合同和业务旅程逻辑继续使用内部整数 ID。

补齐并保留团队条件：

```python
Opportunity.id == opportunity_id
Opportunity.team_id == team_id

Customer.id == customer_id
Customer.team_id == team_id
```

`has_active_contract_for_opportunity` 已按 `team_id` 限定，继续保持该约束。

`create_from_opportunity` 继续接收内部整数 `opportunity_id` 和 `customer_id`；其客户和商机存在性查询也必须限定 `team_id`。

## 6. 错误处理与事务

### 6.1 HTTP 状态码

以下预期业务错误返回 `400 Bad Request`：

- License 关联部署信息不存在或不属于客户。
- License 关联合同不存在或不属于客户。
- 部署 CRUD 抛出的可预期业务 `ValueError`。
- 合同重复创建、归属冲突或其他现有 CRUD `ValueError`。
- 从商机创建合同时的现有业务 `ValueError`。

补齐两个缺口：

- License 创建路由捕获创建 CRUD 的 `ValueError` 并转换为 400。
- 部署创建路由捕获创建 CRUD 的 `ValueError` 并转换为 400。

合同两个创建路由保留现有 `ValueError -> 400` 映射。

客户不存在和权限不足继续使用既有语义：

- 客户不存在：`check_customer_edit_permission` 返回 404。
- 权限不足：返回 403。
- 联系人不存在：合同接口返回现有 404。

数据库异常、文件存储异常和未知异常不转换为业务 400。现有数据库错误处理、日志和 traceback 行为保持不变。

### 6.2 事务和副作用

不改变 CRUD 当前提交边界：

- License、部署、合同 CRUD 继续按现有实现提交数据库事务。
- 创建失败时不执行智能刷新。
- 创建成功并完成源事务提交后，继续使用现有 post-commit 智能刷新桥接。
- 合同文件存储失败时，继续执行现有清理和回滚语义。
- 不增加 migration，不改变表结构或外键定义。

## 7. 测试设计

测试通过 API/CRUD 公共边界验证行为，不断言 `model_copy` 等实现细节。

### 7.1 License 回归

新增或调整测试覆盖：

1. API 接收有效 `cus_...`，权限校验解析出内部客户 ID，CRUD 成功创建。
2. 传给 CRUD 的内部 schema 的 `customer_id` 是整数内部 ID，不是 public ID。
3. 创建响应继续返回客户 public ID。
4. 有效部署信息和合同能够通过当前团队及客户归属校验。
5. 错误的部署或合同归属返回 400，而不是 500。
6. 创建失败时不触发智能刷新。
7. 现有直接 CRUD 审批测试迁移为 `LicenseApplicationInternalCreate`，明确直接 CRUD 调用使用内部 ID。

### 7.2 Deployment 回归

覆盖：

1. API 接收有效客户 public ID并将其转换为内部整数。
2. CRUD 成功写入内部客户外键，响应返回 public ID。
3. CRUD 抛出业务 `ValueError` 时路由返回 400。
4. 创建失败时不触发智能刷新。

### 7.3 Contract 回归

手动创建路径覆盖：

1. 客户 public ID和商机 public ID都在 API 层解析为内部整数。
2. CRUD 收到 `ContractInternalCreate`，不收到被改写的 `ContractCreate`。
3. 联系人归属和商机归属检查使用内部客户 ID及当前团队。
4. 成功响应继续返回客户和商机 public ID。
5. 业务 `ValueError` 返回 400。

从商机创建路径覆盖：

1. public ID路径参数被解析为当前团队内的商机。
2. CRUD 收到内部商机 ID和客户 ID。
3. 跨团队或不存在的商机不会进入创建 CRUD。
4. 业务 `ValueError` 返回 400。

保留并适配现有业务智能创建测试，确保成功后仍构造并排队正确的业务对象变更；不要把智能刷新实现细节作为 ID 边界测试断言。

## 8. 文件边界

预期修改：

- `CRM-Server/app/schemas/license_application.py`
- `CRM-Server/app/schemas/deployment.py`
- `CRM-Server/app/schemas/contract.py`
- `CRM-Server/app/schemas/__init__.py`（如果项目导出约定需要）
- `CRM-Server/app/api/license_application.py`
- `CRM-Server/app/api/deployment.py`
- `CRM-Server/app/api/contracts.py`
- `CRM-Server/app/crud/crud_license_application.py`
- `CRM-Server/app/crud/crud_deployment.py`
- `CRM-Server/app/crud/contract.py`
- 相关 License、部署、合同单元测试

不修改：

- `CRM-Client` API 契约和 Assistant 相关文件
- 数据库模型和 migration
- 不相关的读接口、更新接口和删除接口
- 生产环境数据

## 9. 验收标准

1. License 创建不再执行 `Customer.public_id == <内部整数>` 的查询。
2. License、部署、合同创建接口不再把内部 ID写回外部请求 schema。
3. API 是 public ID 到内部整数 ID 的唯一转换边界。
4. License、部署、合同 CRUD 的客户主键输入均为内部整数语义。
5. 所有跨租户客户、商机、部署和合同关联查询保留 `team_id` 条件。
6. 预期业务校验错误返回 400，不再返回 `500 INTERNAL_ERROR`。
7. 创建失败不触发智能刷新或其他成功后副作用。
8. 外部请求和响应继续使用 public ID，现有前端无需改传数据库主键。
9. 不产生数据库 migration。
10. 不改动 Assistant 相关脏工作区文件。
11. 通过聚焦后端回归测试、`ruff check app/`、`mypy app/` 和项目规定的最小测试命令。
12. 上线后在受控部署验证原生产错误路径；在代码部署和回滚条件明确前，不重复提交生产 License 创建请求。

## 10. 实施顺序

1. 先增加内部 schema 和测试红灯用例。
2. 迁移 API 的显式 ID转换，删除外部 schema 的 `model_copy` ID改写。
3. 迁移三个 CRUD 的内部类型和团队过滤。
4. 补齐 License、部署创建路由的 `ValueError -> 400` 映射。
5. 运行聚焦测试，再运行贡献规范要求的后端检查。
6. 仅在验证完成后进行受控部署验证；不在本地或生产中重复提交原业务请求作为试错。

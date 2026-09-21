# DataTable 当前筛选结果 Excel 导出设计

## 1. 目标

为 CRMWolf 的核心分页 DataTable 增加统一的 Excel 导出能力：

- 导出当前页面上下文中符合搜索、页签、筛选、排序和权限范围的全部数据；
- 不受当前页码和每页条数限制；
- 通过统一弹窗选择导出字段；
- 默认选择当前 DataTable 可见列，允许临时勾选已隐藏列；
- 生成 `.xlsx` 文件；
- 使用独立导出权限控制入口和服务端访问；
- 永不导出数据库内部 `id`。

首期覆盖：

1. 客户
2. 客户追踪
3. 线索
4. 商机
5. 合同
6. 回款计划
7. 回款记录
8. 发票
9. 审批中心

## 2. 已确认产品决策

- 导出方式：同步生成并下载全部匹配数据，不设置产品层面的最大条数。
- 字段选择：点击导出后打开弹窗。
- 默认字段：当前 DataTable 可见列，顺序与当前字段配置一致。
- 隐藏字段：在弹窗中可临时勾选，勾选结果不修改 DataTable 字段配置。
- 业务 ID：有 `public_id` 的资源额外提供“业务 ID”字段，默认不勾选。
- 内部 ID：数据库 `id` 和内部外键不进入候选字段，也不能通过手工请求导出。
- 权限：使用独立导出权限；默认仅 `TEAM_ADMIN` 拥有。
- 文件格式：仅 Excel `.xlsx`，本期不提供 CSV。

## 3. 非目标

- 不导出当前页这一小部分数据。
- 不实现后台异步导出任务、导出中心、历史下载或定时导出。
- 不保存用户上一次在导出弹窗中的临时字段选择。
- 不允许导出自由 SQL、任意响应属性或未注册字段。
- 不在前端循环翻页并拼接所有数据。
- 不把内部数据库 ID 作为业务标识兜底；业务编号缺失时导出为空，不输出 `#123` 一类内部 ID。

## 4. 用户交互

### 4.1 入口

桌面 DataTable 工具栏顺序：

```text
搜索 → 筛选 → 排序 → 字段配置 → 导出 → 页面自定义工具
```

窄视口 `< 768px`：

- “排序”“字段配置”“导出”继续收纳在“更多设置”中；
- 导出入口仍显示明确文字和下载图标；
- 无导出权限时不渲染入口。

### 4.2 导出弹窗

标题：`导出 Excel`

说明：

```text
将导出当前筛选结果，共 76 条。
```

字段分两组：

1. `当前显示字段`
   - 默认全部勾选；
   - 顺序使用当前字段配置顺序。
2. `其他可选字段`
   - 包含当前隐藏的 DataTable 列；
   - 包含资源支持的额外“业务 ID”；
   - 默认不勾选。

导出顺序固定为：

1. 若用户选择“业务 ID”，它位于第一列；
2. 其余字段按当前 DataTable 字段配置顺序输出；
3. 本期不在导出弹窗中增加拖动排序。

按钮：

- `取消`
- `导出`

约束：

- 至少选择一个字段后才允许导出；
- 当前筛选结果为 0 条时导出按钮禁用，并提供可读原因；
- 生成期间按钮显示“正在导出”，阻止重复提交；
- 导出失败时保持弹窗和字段选择，允许用户直接重试；
- 关闭并重新打开弹窗时，重新以当前可见列作为默认值。

## 5. DataTable 组件合同

### 5.1 字段注册表

扩展现有 `ListFieldDefinition`：

```ts
export interface ListFieldExportConfig {
  label?: string
}

export interface ListFieldDefinition {
  key: string
  label: string
  // 现有 column/filter/sort 等字段保持不变
  export?: true | false | ListFieldExportConfig
}
```

投影规则：

- 普通业务列默认可导出；
- `role: 'action'` 和 `role: 'decoration'` 默认不可导出；
- 字段可通过 `export: false` 显式禁止导出；
- 无 `column` 但显式配置 `export: true` 或对象时，可作为导出专用字段；
- `key === 'id'` 永远不可导出，字段注册表校验应直接拒绝；
- 前端导出候选字段必须同时存在于对应服务端导出字段目录中。

有 `public_id` 的资源增加导出专用字段：

```ts
{
  key: 'public_id',
  label: '业务 ID',
  export: true
}
```

该字段没有 `column`，因此不会出现在 DataTable，也不会默认勾选。

### 5.2 DataTable Props 与事件

新增建议合同：

```ts
interface Props {
  exportEnabled?: boolean
  exporting?: boolean
  exportTitle?: string
}

const emit = defineEmits<{
  export: [fieldKeys: string[]]
}>()
```

- `exportEnabled` 由页面结合独立权限决定；
- `exporting` 由页面或共享导出 composable 管理；
- `exportTitle` 用于弹窗说明和文件名，例如“客户列表”；
- 匹配条数直接使用 DataTable 已有 `total`；
- DataTable 只负责字段选择和触发事件，不负责理解业务页签或拼装业务 API 参数。

### 5.3 组件结构

新增 `DataTableExportDialog.vue`：

- 展示导出入口；
- 管理弹窗开关和临时字段选择；
- 接收已投影的可见、隐藏和导出专用字段；
- 发出选定字段 key；
- 不读取 API、不生成 Excel、不保存偏好。

`ListAdvancedTools.vue` 将它与排序、字段配置放在同一响应式工具目标中，使桌面直接展示、移动端自动进入“更多设置”。

## 6. 前端数据流

每个页面继续拥有自己的查询上下文。页面已有列表请求参数构造逻辑应提取为单一函数，列表读取和导出共同复用，禁止分别维护两套筛选规则。

示例：

```ts
function currentCustomerQuery(): CustomerListContext {
  return {
    tab: activeTab.value,
    search: search.value.trim(),
    filters: activeFilters.value,
    sorts: activeSorts.value,
  }
}
```

列表请求在此上下文上增加分页；导出请求不增加分页：

```ts
await customerApi.exportCustomers({
  ...currentCustomerQuery(),
  fields: selectedFieldKeys,
})
```

共享 `useDataTableExport` composable 负责：

- `exporting` 状态；
- 调用页面提供的请求函数；
- 将 Blob 下载为 `.xlsx`；
- 成功/失败反馈；
- 始终释放 `URL.createObjectURL`。

同步全量导出请求必须覆盖通用 Axios 的 30 秒默认值：仅导出 API 使用 `timeout: 0`，不修改其他请求的全局超时。基础设施或服务端主动终止时仍按失败处理，不截断文件。

它不负责业务查询参数、权限判断或字段映射。

## 7. 服务端 API

采用资源级薄端点，而不是一个接收任意上下文字典的万能端点。每个请求使用明确的 Pydantic schema，并复用该资源现有列表查询逻辑。

端点：

| 页面 | 端点 | 权限 |
| --- | --- | --- |
| 客户 | `POST /v1/customers/export` | `customer:export` |
| 客户追踪 | `POST /v1/follow-up-tasks/export` | `follow_up_task:export` |
| 线索 | `POST /v1/leads/export` | `lead:export` |
| 商机 | `POST /v1/opportunities/export` | `opportunity:export` |
| 合同 | `POST /v1/contracts/export` | `contract:export` |
| 回款计划 | `POST /v1/payments/payment-plans/export` | `payment:plan:export` |
| 回款记录 | `POST /v1/payments/payment-records/export` | `payment:record:export` |
| 发票 | `POST /v1/invoice-applications/export` | `invoice:export` |
| 审批中心 | `POST /v1/approvals/export` | `approval:export` |

每个请求包含：

```json
{
  "fields": ["account_name", "owner", "status"],
  "search": "华东",
  "filters": [{ "field": "status", "op": "eq", "value": "0" }],
  "sorts": [{ "field": "created_time", "direction": "desc" }],
  "tab": "all"
}
```

`tab` 和其他上下文使用资源专属枚举或明确字段，不接受无类型 `dict`：

- 客户：`all | collaborated | public`
- 线索：`all | public`
- 商机：`all | active | won | lost`
- 合同：当前合同页签集合
- 回款计划：`all | pending | partial | completed`
- 回款记录：当前回款记录页签集合
- 发票：`all | pending | approved | invoiced`
- 客户追踪：当前追踪状态页签；继续固定当前页面的 `owner_scope=mine`
- 审批：当前审批页签、业务类型和页面已有角色范围

响应：

```text
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename*=UTF-8''...
```

## 8. 查询语义

导出必须复用列表的完整查询顺序：

```text
团队与用户权限范围
→ 当前页签约束
→ 搜索
→ filters
→ sorts / 默认排序
→ 稳定次级排序
→ 不分页读取
```

要求：

- 导出端点必须再次校验独立导出权限；前端隐藏入口不是安全边界；
- 独立导出权限只允许发起导出，不能扩大数据可见范围；
- 原列表只能看本人数据时，导出仍只能导出本人可见数据；
- 审批和客户追踪继续遵循其现有角色、节点和归属范围；
- 公海页签仍使用公海列表的范围规则；
- 不允许通过请求字段切换到比当前用户更大的 scope；
- 未传显式排序时使用现有列表默认排序；
- 在业务排序之后追加稳定业务标识或内部主键排序，仅用于确定顺序，不导出该内部主键。

现有列表端点普遍限制每页最多 100 条。导出不得调用列表 HTTP API 循环翻页，也不得对全部结果调用 `.all()` 一次性装入内存；应抽取并复用底层查询构造函数，以 `yield_per` / `stream_results` 或等价的资源级批量迭代器读取并逐行写入 workbook。关联名称和枚举值的补全必须按批预取，禁止形成逐行 N+1 查询。

## 9. 服务端导出字段目录

新增受控的导出字段目录：

```py
@dataclass(frozen=True)
class ListExportField:
    key: str
    label: str
    cell_type: Literal["text", "number", "date", "datetime", "currency"]
    value_getter: Callable[[object], object]

@dataclass(frozen=True)
class ListExportCatalog:
    resource: str
    fields: Sequence[ListExportField]
```

目录职责：

- 白名单校验请求字段；
- 提供可信表头；
- 从业务列表行读取用户可见值；
- 定义 Excel 单元格类型和格式；
- 明确禁止内部 ID。

前端增加生成的 `listExportCatalogManifest.json`，包含每个资源允许的字段 key、标签和类型。契约测试要求：

- 每个前端启用的导出字段都存在于对应服务端目录；
- 标签保持一致；
- `id` 不得出现在任何导出目录；
- 九个首期 DataTable 都注册了导出目录。

该 manifest 只用于契约校验和前端能力确认，不承载真实数据，也不替代服务端白名单。

## 10. Excel 生成

服务端使用 `openpyxl` write-only 模式生成 `.xlsx`：

- 使用临时文件，响应完成后删除；
- 首行写字段标题并冻结；
- 启用首行自动筛选；
- 金额和数字使用数值单元格，不预先格式化成带逗号字符串；
- 日期和时间使用 Excel 日期单元格及明确格式；
- 手机号、业务 ID、业务单号等强制按文本写入；
- 空值写空单元格，不写 Python `None` 文本；
- 多值字段使用 `、` 拼接；
- 文件名和工作表名移除非法字符，工作表名限制在 31 个字符内。

文本安全：

- 对用户文本先检查去除前导空白后的首字符；若为 `=`, `+`, `-`, `@`，写入安全的纯文本值，防止公式注入；
- 表头执行相同的安全处理；
- 不生成宏、公式、外部链接或隐藏工作表。

依赖交付：

- 项目当前未安装 `openpyxl`；实现必须把固定版本加入 `CRM-Server/requirements.txt` 和 `CRM-Server/pyproject.toml`；
- 使用仓库既有 `uv pip compile` 流程同时更新 `requirements.lock` 和 `requirements-dev.lock`，禁止只改非锁定依赖文件；
- CI 和生产安装继续使用带哈希锁文件，不在运行时动态安装依赖。

文件名示例：

```text
客户列表-所有客户-20260921-143500.xlsx
```

## 11. 用户可读值规则

Excel 导出值应与 DataTable 的业务语义一致，而不是直接序列化 API 对象：

- 状态码转为中文状态名称；
- 枚举使用字段选项中的显示文本；
- 负责人、创建人、申请人等输出姓名；
- 关联客户、商机、合同、回款计划输出名称或业务编号；
- 协作者、产品模块等数组使用 `、` 拼接；
- 金额输出数值；
- 日期输出本地业务日期/时间；
- `public_id` 输出为“业务 ID”；
- 合同、回款、发票、审批使用已有合同编号、计划编号、回款编号、申请单号等业务标识；
- 旧数据缺少业务编号时留空，不回退到内部数据库 `id`。

## 12. 权限与既有数据库升级

新增权限：

```text
customer:export
follow_up_task:export
lead:export
opportunity:export
contract:export
payment:plan:export
payment:record:export
invoice:export
approval:export
```

默认授权：

- `TEAM_ADMIN`：拥有全部九项；
- `SALES_DIRECTOR`、`SALES_MEMBER`、`FINANCE`：默认不授予；
- 团队管理员可在角色权限设置中按需分配。

交付必须覆盖已有数据库：

- 新增 Alembic 数据迁移写入九项权限；
- 将权限分配给所有既有 `TEAM_ADMIN` 角色；
- 不自动分配给其他角色；
- 迁移保持幂等，不重复创建权限或角色关联。

## 13. 错误处理

| 场景 | 行为 |
| --- | --- |
| 无导出权限 | 服务端 `403`；前端正常情况下不显示入口 |
| 未选择字段 | 前端阻止提交；服务端再次返回 `400` |
| 请求未知或禁用字段 | 服务端 `400`，不忽略字段 |
| 请求包含 `id` | 服务端 `400` |
| 当前结果已变为空 | 返回包含表头、0 条数据的有效 Excel，与请求执行时的真实结果一致 |
| Excel 生成失败 | 不返回部分文件；前端保留弹窗与选择并提示重试 |
| 网络中断 | 取消下载，不生成损坏的本地文件 |
| 大数据超过基础设施同步超时 | 明确失败，不截断、不偷偷只导出前 N 条 |

用户选择了同步全量导出，因此超大结果仍存在请求时间和临时磁盘占用风险。本期接受该风险，但禁止用静默上限改变“全部匹配数据”的合同。

## 14. 测试与验收

### 14.1 前端组件

验证：

- 桌面直接显示导出入口；移动端在“更多设置”中；
- 无权限时入口不存在；
- 可见列默认勾选，隐藏列和业务 ID 默认不勾选；
- 当前字段顺序正确；
- 至少选择一个字段；
- 0 条结果不可导出；
- exporting 状态阻止重复提交；
- 临时选择不修改字段配置；
- 关闭重开恢复当前可见列默认值。

### 14.2 前后端合同

验证：

- 九个前端字段注册表与服务端导出目录一致；
- 任一目录不含 `id`；
- `public_id` 只作为显式业务 ID；
- 未注册字段和 `id` 请求被拒绝；
- 权限 manifest 和默认角色映射符合设计。

### 14.3 服务端行为

每个资源至少验证：

- 当前页只有 20 条、total 为 76 时导出 76 条；
- 搜索、页签、filters、sorts 与列表结果一致；
- own 权限不能借导出扩大范围；
- 无独立导出权限返回 403；
- 状态、人员、关联对象、日期和金额格式正确；
- 公式注入文本被安全处理；
- 内部 ID 不出现在表头或单元格；
- 输出是可被 `openpyxl` 重新读取的有效工作簿。

### 14.4 实际界面验收

在客户列表至少执行一次真实端到端场景：

1. 设置筛选，使结果跨越多页；
2. 隐藏一个字段；
3. 打开导出弹窗，确认当前可见列默认选中；
4. 额外勾选隐藏字段和业务 ID；
5. 下载并打开 Excel；
6. 核对行数为筛选总数、列顺序正确、无内部 ID、中文状态和值格式正确。

其余八个页面逐一验证入口权限、当前上下文和至少一个业务值映射。

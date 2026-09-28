# 回款记录合同字段与角色权限分组优化设计

## 1. 目标

优化 `/payments/records` 回款管理页，使每条回款记录可直接查看关联合同的授权模式与采购类型，并让两项字段完整参与 DataTable 能力：

- 表格与移动端展示；
- 字段配置与自定义视图；
- 服务端全量筛选；
- 服务端全量排序；
- 当前筛选结果 Excel 导出。

同时修正角色权限配置中的回款权限展示：`payment:record:export` 必须出现在统一的“回款”权限组中，而不是因后端资源名不同被拆到单独的“回款记录”组。

## 2. 已确认产品决策

- 两个新字段默认显示，不做默认隐藏。
- 字段顺序位于“合同名称”之后，先“授权模式”，再“采购类型”。
- 两个字段使用现有枚举和 `StatusBadge` 视觉语义：
  - 授权模式：`SUBSCRIPTION` / `PERPETUAL`；
  - 采购类型：`NEW` / `RENEWAL` / `EXPANSION`。
- 两个字段具备完整 DataTable 能力，不仅是展示列。
- 授权模式取关联合同 `Contract.license_type`。
- 采购类型取关联合同对应商机 `Opportunity.purchase_type`；合同没有关联商机时返回空值并显示 `-`。
- 不把枚举字段加入统一文本搜索；搜索范围继续聚焦编号、客户、合同、阶段、付款方、发票抬头、负责人和团队成员。
- 不修改权限码、数据库中的 permission resource 或服务端权限校验方式。
- 角色权限 UI 将 `payment`、`payment_plan`、`payment_record` 三种资源聚合为同一个“回款”展示组。

## 3. 非目标

- 不修改合同、商机或回款记录的数据库结构。
- 不把授权模式或采购类型复制、快照到回款记录表。
- 不为 DataTable 增加任何回款领域硬编码。
- 不扩大用户可查看或可导出的数据范围。
- 不修改 `payment:record:export` 的权限语义或默认授权角色。
- 不重构角色管理页面的整体交互与样式。
- 不改变统一搜索的匹配字段。

## 4. 字段语义与空值规则

### 4.1 授权模式

稳定字段 key：`license_type`

数据链路：

```text
PaymentRecord
→ PaymentPlan
→ Contract
→ Contract.license_type
```

值与展示：

| 原始值 | 表格标签 | 筛选标签 | 导出文本 |
| --- | --- | --- | --- |
| `SUBSCRIPTION` | 订阅制 | 订阅 | 订阅 |
| `PERPETUAL` | 买断制 | 买断 | 买断 |
| `null` | `-` | 不适用 | 空单元格 |

表格标签继续复用现有 `StatusBadge type="authorizationMode"`，筛选和导出文本保持与合同列表现有字段契约一致。

### 4.2 采购类型

稳定字段 key：`purchase_type`

数据链路：

```text
PaymentRecord
→ PaymentPlan
→ Contract
→ Opportunity
→ Opportunity.purchase_type
```

值与展示：

| 原始值 | 表格、筛选与导出文本 |
| --- | --- |
| `NEW` | 新购 |
| `RENEWAL` | 续购 |
| `EXPANSION` | 增购 |
| `null` | 表格显示 `-`，导出为空单元格 |

表格继续复用现有 `StatusBadge type="procurementType"`。

## 5. 前端设计

### 5.1 回款记录类型

扩展 `PaymentRecordResponse` / `PaymentRecordWithDetails` 的公开类型：

```ts
license_type?: 'SUBSCRIPTION' | 'PERPETUAL' | null
purchase_type?: 'NEW' | 'RENEWAL' | 'EXPANSION' | null
```

字段保持可空，以兼容历史合同、未关联商机的合同以及旧响应缓存。

### 5.2 回款页面字段注册表

`CRM-Client/src/views/PaymentRecords.vue` 的单一字段注册表增加：

```ts
{
  key: 'license_type',
  label: '授权模式',
  type: 'enum',
  options: licenseTypeOptions,
  column: { align: 'center', width: '110px' },
  filter: true,
  sort: true,
},
{
  key: 'purchase_type',
  label: '采购类型',
  type: 'enum',
  options: purchaseTypeOptions,
  column: { align: 'center', width: '110px' },
  filter: true,
  sort: true,
},
```

两项定义位于 `contract_name` 之后。字段注册表继续作为列、筛选、排序、字段配置和导出候选的唯一来源，不新增平行字段清单。

页面增加两个单元格 slot，复用合同页已有 `StatusBadge` 表现。移动卡片在合同名称之后增加一组紧凑标签；没有值时不渲染空标签，桌面单元格显示 `-`。

现有自定义视图和列偏好继续按稳定 key 工作：

- 旧偏好中没有新 key 时，两列采用字段注册表的默认可见状态；
- 用户之后隐藏、排序两列时，继续保存为 `license_type`、`purchase_type`；
- 不迁移或重写既有视图数据。

### 5.3 DataTable 边界

`DataTable.vue` 已支持：

- enum 筛选字段；
- 服务端排序字段；
- 字段配置；
- 单元格 slot；
- 字段注册表驱动的导出候选。

因此不在通用 DataTable 中识别 `license_type` 或 `purchase_type`。本次只通过页面字段注册表使用现有能力。若实现过程中发现通用能力缺陷，只修复通用投影规则，不增加回款特例。

## 6. 服务端设计

### 6.1 响应契约

`PaymentRecordResponse` 增加两个可空字段：

```py
license_type: str | None
purchase_type: str | None
```

以下两条投影路径都必须赋值，避免列表、详情和写入返回出现契约差异：

1. `_payment_record_response`：从已加载的合同和商机读取；
2. `_build_payment_record_list_items`：批量投影列表与导出数据。

不查询或写入新的回款记录列。

### 6.2 服务端筛选与排序

`PAYMENT_RECORDS_LIST_QUERY_CATALOG` 增加：

- `license_type`：`type="enum"`，表达式为 `Contract.license_type`；
- `purchase_type`：`type="enum"`，表达式为 `Opportunity.purchase_type`。

回款列表基础查询已经连接 `Contract` 并外连接 `Opportunity`，因此新增能力不引入逐行查询或额外 join。统一 list-query 协议继续按以下顺序执行：

```text
租户与权限范围
→ 页签固定范围
→ filters
→ count
→ sorts
→ pagination
```

空商机的采购类型在正向枚举筛选中自然不匹配；排序沿用数据库的空值行为，不在应用层二次排序。

旧查询参数兼容路径不是本次 UI 的调用路径，不为两个新字段增加新的旧式 query 参数；前端 DataTable 继续使用统一 `filters` / `sorts` 协议。

### 6.3 导出

`PAYMENT_RECORDS_LIST_EXPORT_CATALOG` 增加：

- `license_type`，标签“授权模式”；
- `purchase_type`，标签“采购类型”。

`_payment_record_export_row` 将原始枚举转换为中文文本：

- 授权模式：订阅、买断；
- 采购类型：新购、续购、增购。

导出继续复用回款列表的权限范围、页签、搜索、筛选和排序上下文，导出所有匹配行而不是当前页。未知字段仍返回 400。

后端 list-query / list-export catalog manifest 按现有生成流程更新，前端契约测试继续校验页面字段与服务端目录一致。

## 7. 角色权限分组设计

### 7.1 问题

后端权限本身已经存在：

```text
payment:record:export
resource = payment_record
action = export
```

角色配置 UI 当前直接按 `permission.resource` 分组，导致：

- `payment:*` 显示在“回款”；
- `payment:plan:*` 显示在“回款计划”；
- `payment:record:*` 显示在“回款记录”。

用户在“回款”组中因此看不到“导出回款记录”，但服务端和数据库权限并未缺失。

### 7.2 展示层规范化

在 `CRM-Client/src/constants/permissions.ts` 增加共享的展示分组规范化能力。稳定规则：

```text
payment         → payment
payment_plan    → payment
payment_record  → payment
其他 resource   → 保持原值
```

规范化只决定角色配置 UI 的展示组 key，不修改权限对象，不修改提交给后端的 permission id，也不修改资源中文名称目录。

共享 helper 负责：

1. 过滤不可分配的历史权限；
2. 按规范化后的展示组 key 聚合；
3. 保留每个权限原始 id、code、resource、action 和 scope；
4. 输出稳定的组结构供 UI 使用。

`SettingsRolesPage.vue` 与仍可访问的旧 `RoleSheet.vue` 必须共同调用该 helper，删除两处重复的本地分组实现，避免入口行为分叉。

聚合后的“回款”组中至少包含：

- 回款提交、撤回、审批、确认等 `payment` 权限；
- 回款计划导出等 `payment_plan` 权限；
- 回款记录编辑、删除、导出等 `payment_record` 权限。

组级全选、半选和取消全选继续基于该组内 permission id 计算。保存时仍使用现有 `mergePermissionIdsPreservingDeprecated`，不会静默删除历史权限关联。

### 7.3 安全边界

- UI 展示聚合不授予任何新权限；
- `payment:record:export` 入口仍由前端 permission store 判断；
- 导出 API 仍使用 `require_permission("payment:record:export")` 强制校验；
- 无需 Alembic migration；
- 不修改 `ALL_PERMISSIONS`、现有 migration 或默认角色映射。

## 8. 错误与兼容行为

- 合同缺少授权模式：返回 `null`，页面显示 `-`，导出为空。
- 合同未关联商机或商机缺少采购类型：返回 `null`，页面显示 `-`，导出为空。
- 历史列偏好未包含新字段：采用字段注册表默认可见，不使偏好读取失败。
- 服务端收到未知枚举值：API 原样返回；表格 badge 按现有组件兜底行为显示，导出原样输出，避免静默丢数据。
- 用户没有 `payment:record:export`：DataTable 不显示导出入口；直接请求导出 API 返回 403。
- 权限目录中不存在该权限：角色 UI 无法显示不存在的数据，但不合成虚假权限；部署仍依赖既有 migration / 初始化服务提供真实权限记录。

## 9. 验证策略

### 9.1 后端

增加或扩展行为测试，证明：

1. 回款记录列表响应包含关联合同的 `license_type` 与关联商机的 `purchase_type`；
2. 无关联商机时 `purchase_type` 为 `null`；
3. `license_type` 枚举筛选在分页前对全量结果生效；
4. `purchase_type` 枚举筛选在分页前对全量结果生效；
5. 两个字段可服务端排序；
6. Excel 导出目录允许选择两个字段；
7. 导出值为中文文本且空关联导出为空；
8. 未授权用户仍无法调用回款记录导出 API。

### 9.2 前端

增加或扩展契约测试，证明：

1. `PaymentRecords.vue` 的字段注册表声明两个 enum 字段及完整筛选、排序、导出能力；
2. 两个桌面单元格使用现有状态标签；
3. 移动卡片展示非空授权模式和采购类型；
4. list-query 与 list-export manifest 包含两个字段；
5. 权限分组 helper 将 `payment`、`payment_plan`、`payment_record` 聚合为一个 `payment` 组；
6. 聚合后包含 `payment:record:export`，并保持其原始 permission id 和 resource；
7. 两个角色配置入口都使用共享 helper。

### 9.3 实际表面验证

运行前后端后验证真实页面：

- 回款管理表格默认显示两个新字段；
- 字段配置可隐藏、恢复和调整顺序；
- 筛选、排序跨页生效；
- 导出弹窗提供两个字段，下载文件中的中文值正确；
- 窄视口卡片展示两个标签且空值不占位；
- `settings/roles` 的“回款”组内可见“导出回款记录”；
- 勾选、保存并重新打开角色权限后状态保持一致。

## 10. 预计修改范围

前端：

- `CRM-Client/src/api/payment.ts`
- `CRM-Client/src/views/PaymentRecords.vue`
- `CRM-Client/src/constants/permissions.ts`
- `CRM-Client/src/views/settings/SettingsRolesPage.vue`
- `CRM-Client/src/components/system-config/RoleSheet.vue`
- 对应字段目录 manifest 与行为测试

后端：

- `CRM-Server/app/schemas/payment.py`
- `CRM-Server/app/api/payments.py`
- `CRM-Server/app/core/list_query/catalogs/payment_records.py`
- `CRM-Server/app/core/list_export/catalogs/payment_records.py`
- 对应列表、查询目录和导出测试

本设计不需要数据库 migration。

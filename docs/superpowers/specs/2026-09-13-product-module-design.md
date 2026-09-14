# 产品与模块管理 MVP 设计

## 目标

在系统设置中心提供团队级产品配置能力。每个产品可以配置一个基础模块和多个增强模块，普通用户只读，拥有明确产品权限的用户负责维护。

本期只交付产品主数据与模块配置，不改商机、合同、License 的业务字段，不实现产品推荐或审批 Agent。

## 现有系统约束

- 权限必须复用现有 `permissions`、`roles`、`role_permissions`、`user_roles` 体系。
- 产品接口按当前用户的 `team_id` 做租户隔离。
- 不以 `TEAM_ADMIN`、团队所有者或“管理员”字符串作为产品接口的授权旁路。
- 前端设置中心沿用 `SETTINGS_NAVIGATION` 和现有 `SettingsModulePage`/配置面板模式。
- 数据库结构变更使用 Alembic migration。
- 前端优先复用 `ListCard`、shadcn-vue `Dialog`、`Button`、`Input`、`Badge`、`ScrollArea` 等现有组件。

## 产品模型

### Product

团队级产品容器：

- `id`：内部主键
- `public_id`：对外 ID，前缀 `prd_`
- `team_id`：所属团队
- `code`：团队内唯一的稳定编码
- `name`：产品名称
- `description`：产品描述，可空
- `is_active`：是否启用
- `created_by`、`updated_by`、`created_time`、`updated_time`

### ProductModule

产品下的平级模块：

- `id`：内部主键
- `public_id`：对外 ID，前缀 `prm_`
- `team_id`：所属团队
- `product_id`：所属产品
- `code`：产品内唯一编码
- `name`：模块名称
- `description`：模块描述，可空
- `module_role`：`BASE` 或 `ADD_ON`
- `is_active`：是否启用
- `sort_order`：展示顺序
- 创建和更新时间字段

本期不做模块嵌套、不做版本实体、不做套餐组合。

## 基础模块规则

- 每个产品最多一个 `BASE` 模块。
- 产品进入配置时必须有且只有一个基础模块；创建产品时自动创建默认基础模块，名称默认使用“基础版”，编码默认使用 `BASE`。
- 基础模块自动包含，不能被删除或停用。
- 基础模块可以改名和描述，但不能改为 `ADD_ON`，除非先通过同一事务将另一个模块设为基础模块；本期 UI 不提供基础模块角色切换，避免产生复杂迁移交互。
- 增强模块为 `ADD_ON`，可以新增、编辑、停用和删除。
- 删除/停用产品前，如果产品仍存在模块或后续引用，优先返回业务错误；本期产品删除仅允许删除没有额外模块、没有未来引用的产品。页面以停用为主，删除为低频操作。
- 停用产品不影响历史数据；停用产品不出现在未来业务选择项中。

## 权限模型

新增四个系统权限：

- `product:view`
- `product:create`
- `product:edit`
- `product:delete`

`resource=product`，`action` 分别为 `view/create/edit/delete`，不使用 `own/all` scope。

接口授权：

- `GET /v1/products`、`GET /v1/products/{public_id}`：`product:view`
- `POST /v1/products`：`product:create`
- `PUT /v1/products/{public_id}`：`product:edit`
- `DELETE /v1/products/{public_id}`：`product:delete`
- 产品模块新增、更新、删除：`product:edit`

设置中心入口仅要求 `product:view`。页面内按权限显示新增、编辑、删除操作。前端隐藏按钮不是安全边界，后端必须单独校验每个接口。

默认角色映射：

- `TEAM_ADMIN` 继续由现有初始化机制获得全部已登记权限。
- `SALES_MEMBER` 获得 `product:view`，不默认获得维护权限。
- `SALES_DIRECTOR` 获得 `product:view`，不默认获得维护权限。
- `FINANCE` 不默认获得产品权限。

## API

### 产品列表

`GET /v1/products`

查询参数：

- `is_active`：可选 `0/1`，默认返回全部团队产品供设置页管理。

返回产品列表，每个产品包含模块列表和基础模块摘要。

### 产品详情

`GET /v1/products/{public_id}`

返回产品和按 `sort_order` 排序的模块。

### 创建产品

`POST /v1/products`

请求：

```json
{
  "code": "CRM_WOLF",
  "name": "CRMWolf",
  "description": "客户关系管理平台"
}
```

事务内创建产品和默认 `BASE` 模块。

### 更新产品

`PUT /v1/products/{public_id}`

可更新名称、描述和启用状态。编码创建后不变。

### 删除产品

`DELETE /v1/products/{public_id}`

仅允许删除未被保护的产品；基础模块随产品级联删除。被业务引用或包含无法安全删除内容时返回明确 400/409。

### 模块操作

- `POST /v1/products/{product_public_id}/modules`
- `PUT /v1/products/{product_public_id}/modules/{module_public_id}`
- `DELETE /v1/products/{product_public_id}/modules/{module_public_id}`

模块编码在产品内唯一。创建模块时默认 `ADD_ON`；首个默认模块由产品创建事务生成。模块角色只允许 `BASE`/`ADD_ON`，后端强制基础模块不可删除、不可停用。

## 前端页面

入口：`设置中心 → 流程与业务配置 → 产品管理`。

页面复用现有设置面板风格：

- 顶部搜索和状态筛选；
- `ListCard` 展示产品名称、编码、模块数量、基础模块和启用状态；
- 有 `product:create` 时显示“新增产品”；
- 有 `product:edit` 时显示“编辑产品”和模块配置；
- 有 `product:delete` 时显示删除/停用入口；
- 产品表单和模块表单使用现有 `Dialog`、`FormField`、Zod/VeeValidate 模式；
- 无维护权限时保持完整只读视图；
- 产品详情/编辑对话框中展示模块列表，基础模块使用明显 Badge，增强模块可编辑。

## 错误和并发

- 团队不匹配、对象不存在统一返回 404，不能泄露其他团队对象存在性。
- 编码重复返回 409 或 400，并保留可读错误信息。
- 基础模块删除/停用返回 400。
- 删除有引用产品返回 409。
- 保存失败时不关闭对话框，保留用户输入并显示页面级错误。
- 创建产品和默认模块必须同一事务提交；任一失败整体回滚。

## 测试与验收

后端：

- 产品和模块 CRUD 的团队隔离；
- 创建产品自动生成基础模块；
- 基础模块不能删除或停用；
- 重复产品/模块编码被拒绝；
- 四个接口权限分别生效；
- 无权限用户不能通过 API 绕过前端。

前端：

- 设置导航包含唯一产品入口；
- 只读用户看不到维护操作；
- 编辑用户可以配置增强模块；
- 基础模块显示为不可删除/停用；
- API 加载、空状态、错误状态和保存反馈可见。

验证：

- 后端定向 pytest、ruff；
- Alembic upgrade head；
- 前端产品组件定向 Vitest、type-check、lint；
- 启动真实前端页面，通过浏览器确认设置入口、列表、表单和只读/编辑状态。

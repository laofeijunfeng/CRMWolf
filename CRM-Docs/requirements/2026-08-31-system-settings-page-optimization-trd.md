# 系统设置页面化优化 TRD

本文承接 [系统设置页面化优化 PRD](https://apifox666.feishu.cn/wiki/LUUowHRKhiYYMikcPULcr4Opncc)，只写实现接法，不重写产品规则。

飞书 PRD：[系统设置页面化优化](https://apifox666.feishu.cn/wiki/LUUowHRKhiYYMikcPULcr4Opncc)

飞书 TRD：[系统设置页面化优化 TRD](https://apifox666.feishu.cn/docx/N4dId6FAeo5GIGxVoifcs3OWnHd)

| 项 | 内容 |
| --- | --- |
| 文档类型 | 技术需求文档 TRD v1.0 |
| 状态 | 技术方案评审稿 |
| 日期 | 2026-08-31 |
| 对应 PRD | 方案评审稿，产品规则已在 PRD 中定义 |
| 模块 | 系统设置 / 权限 / 导航 / 组织管理 / 业务配置 / 智能与集成 |
| 读者 | 后端、前端、测试、架构、实施 |
| Alembic | 页面化原则上不新增业务表；如权限字典、所有权转移或历史快照确认需要改库，再单独增加迁移 |

| 本文写 | 本文不写 |
| --- | --- |
| 现有代码盘点、模块边界、路由和组件拆分 | 产品规则正文（见 PRD） |
| `/settings/**` 页面架构、API 契约、权限码、缓存和数据边界 | 具体补丁代码与最终实现细节 |
| Sheet 页面化迁移、兼容路由、测试矩阵和发布回滚 | 与系统设置无关的客户、线索、商机、合同、回款、发票和 License 功能改造 |
| 团队所有者权限、配置引用保护、审计和安全规则 | 重新设计视觉风格或引入新的 UI 组件库 |

PRD 已拍板、本文不得推翻的决策：统一入口采用 `/settings`，默认页为 `/settings/account`；设置导航不增加搜索框，但业务管理列表继续保留搜索、筛选、排序和分页；长期管理型 Sheet 全部页面化，短时编辑和确认操作可保留 Dialog；菜单、路由、页面操作和后端 API 统一使用权限码，团队所有者默认拥有当前团队全部团队级权限但不获得平台级权限；页面优先复用 CRMWolf 现有组件，缺少能力时先封装项目级 shadcn-vue 组件后再使用。

## 1. 技术目标与边界

本 TRD 将 PRD 的产品规则落到现有 CRMWolf 前后端代码、路由、权限、接口、缓存、数据迁移和测试方案。最终系统需要形成一个真正的 `/settings` 设置工作区：用户菜单只有一个“系统设置”入口，进入后左侧导航切换为设置域导航，普通用户可以访问账户设置，团队级页面根据当前团队的有效权限显示和授权。

本次改造的核心不是把卡片换成更大的容器，而是将长期管理型 Sheet 变为可直接访问、可刷新、可收藏、可审计的页面。新建、编辑、分配角色、确认删除、连接测试等短任务仍可使用 Dialog；抽屉不再承担设置域的一级导航和长期管理列表。

### 1.1 本次范围

- 设置工作区外壳、设置侧栏、返回系统入口和用户菜单入口收拢。
- `/settings` 及其子路由、页面级权限、旧路由兼容和直接访问处理。
- 账户设置、团队信息与安全、团队成员、角色管理、审批流程、获客来源、采购方式/阶段、AI、通知、第三方集成页面化。
- 统一权限码控制菜单、路由、页面操作和后端 API，并处理团队所有者默认全团队权限。
- 保留现有团队隔离、审批实例、发票抬头业务边界和采购/获客来源引用保护。
- 复用既有组件和设计系统；缺少能力时先封装项目级组件，再基于 shadcn-vue 使用。

### 1.2 非目标

- 不在本次页面化中新增一套“设置数据表”，也不复制现有角色、审批、采购、获客来源或配置表。
- 不改变客户、线索、商机、合同、回款、发票、License 等业务页面的业务操作入口和权限语义。
- 不把发票抬头提升为团队系统设置；发票抬头仍属于客户/发票业务资料，历史发票申请必须使用快照。
- 不删除管理列表原有的搜索、筛选、排序和分页；“不用搜索”只针对设置侧栏，不针对业务列表。
- 不引入新的 UI 组件库，不恢复 Element Plus、旧 FilterPanel、旧 V1 样式或平行设计 token。

## 2. 现有系统技术盘点

### 2.1 前端现状

当前路由定义位于 `CRM-Client/src/router/index.ts`。系统仍使用旧结构：`/system-config` 加载 `SystemConfig.vue`，`/account` 加载 `AccountSettings.vue`，`/settings` 重定向到 `/system-config`；`/roles`、`/approval-flows`、`/procurement-methods`、`/ai-config`、`/notification-config`、`/team-members` 等路径大多重定向回旧配置页。因此当前不存在可承载设置域导航的 `/settings/**` 页面树。

`SystemConfig.vue` 使用 `defineAsyncComponent` 懒加载八个 Sheet，通过卡片点击切换布尔状态；权限判断分散在页面与 Sheet 中。`useSystemConfigAccess.ts` 以若干权限码加 `TEAM_ADMIN` 角色判断入口，`NavUser.vue` 同时渲染“账户设置”和“系统配置”。`AppSidebar.vue` 只构建业务导航，没有设置上下文，也没有“返回系统”行为。

现有权限 Store `CRM-Client/src/stores/permissions.ts` 已提供 `hasPermission`、`hasAnyPermission`、`hasAllPermissions` 和刷新能力，可作为设置导航和操作按钮的基础。当前路由守卫只处理登录、是否有团队，不处理页面权限；因此页面化后必须新增统一的页面权限解析，而不是继续在每个页面内部各自判断。

`TeamStore.switchTeam()`、`createTeam()`、`joinTeam()` 会刷新权限，但切换团队后当前实现直接 `router.go(0)`，没有定义统一的业务页面缓存清理、未保存表单处理、撤权后的页面降级和跨团队请求取消策略。设置工作区需要在团队切换完成后重建当前团队上下文。

### 2.2 现有 Sheet 的职责

| 模块 | 现有组件 | 当前能力 | 页面化后的主要技术形态 |
| --- | --- | --- | --- |
| 账户设置 | `views/AccountSettings.vue` | 个人资料、安全、修改密码、个人飞书绑定 | `SettingsAccountPage`，短任务仍用 Dialog |
| 团队信息与安全 | 现有 `TeamMemberSheet` 内夹带团队信息、邀请码 | 改名、查看邀请码、重置邀请码 | 独立 `SettingsTeamPage`；高风险动作确认 |
| 团队成员 | `TeamMemberSheet.vue` | 成员列表、邀请、角色分配、改名、重置密码、移除 | `SettingsMembersPage`；邀请/分配/重置使用 Dialog |
| 角色管理 | `RoleSheet.vue` | 角色列表、搜索、创建/编辑、权限配置、删除 | `SettingsRolesPage`；权限配置为详情/编辑区或 Dialog |
| 审批流程 | `ApprovalFlowSheet.vue` | 搜索、状态/授权类型/单据类型筛选、详情、启停、创建、AI 创建 | `SettingsApprovalFlowsPage`；节点编辑为表单页/短任务浮层 |
| 获客来源 | `AcquisitionSourceSheet.vue` | 搜索、状态筛选、新建、改名、排序、启停 | `SettingsAcquisitionSourcesPage` |
| 采购方式/阶段 | `ProcurementSheet.vue` | 搜索、状态筛选、CRUD、阶段模板、AI 创建 | `SettingsProcurementPage`，阶段模板有独立子路由 |
| AI 配置 | `AIConfigSheet.vue` | 供应商、接口、密钥、模型、连接测试 | `SettingsAIPage`，敏感字段脱敏 |
| 通知配置 | `NotificationSheet.vue` | Webhook、群名、通知测试 | `SettingsNotificationsPage`，独立通知权限 |
| 第三方集成 | `LoginIntegrationSheet.vue` | 飞书应用、事件订阅、机器人配置 | `SettingsIntegrationsPage`，团队级配置与个人绑定分开 |

### 2.3 后端现状与技术缺口

后端权限主链路位于 `CRM-Server/app/core/deps.py`、`app/services/permission_service.py` 和 `app/crud/permission.py`。当前 `require_permission()` 只从用户在当前团队角色的权限并集中判断；`Team` 的 `owner_id` 没有在权限计算中形成隐式全权限。另一方面，`teams.py`、`system_configs.py` 和部分业务依赖仍通过 `TEAM_ADMIN` 字符串硬编码判断，构成权限码与角色硬编码并存的两套机制。

`PermissionService` 的团队缓存 key 为 `user_permissions:{user_id}:team:{team_id}`，TTL 为 3600 秒；角色权限变化和部分用户角色变化会清理缓存，但团队所有权变更、成员移除、跨进程刷新和前端当前团队重建尚未形成统一契约。

角色模型为全局 `roles` 加团队范围的 `user_roles` 关联，角色本身没有 `team_id`。角色列表接口当前存在未携带团队过滤的风险；角色成员接口曾复用 `approval:flow:edit`，通知配置接口同时接受 `TEAM_ADMIN` 或 `approval:flow:edit`，AI 配置接口又直接调用权限服务并使用 `system:config`、`ai:manage`、`ai:read`。这些差异必须在页面化时收敛。

业务配置接口的成熟度不一致：获客来源已通过 `public_id`、团队过滤、启停和引用统计实现；采购阶段模板已有 `version_lock`、变更日志、删除引用检查和 409 冲突；采购方式接口仍存在部分旧式 ID 和返回结构；审批流程使用团队范围和事务创建，但审批模板与运行中的审批实例必须解耦。系统配置表 `crm_system_configs` 已存在，页面化不需要新增一张配置表。

### 2.4 可复用的现有能力

- 前端：`components/crmwolf`、`components/ui` 下的 Card、DataTable、ListCard、Dialog、Sheet、Form、Input、Select、Switch、Alert、Empty、Skeleton、Toast 等。
- 状态：Pinia 的用户、团队、权限、Header Store；现有 `handleApiError`、`confirmDialog`、日志工具。
- 后端：`require_permission`、`get_current_user_team`、角色/权限 CRUD、采购阶段 `version_lock`、获客来源引用统计、审批事务和 `crm_operation_logs`。
- 设计系统：`CRM-Docs/design-system` 的列表页、表单页、表格、浮层、Sidebar、Tabs 和状态规范。

## 3. 总体架构

### 3.1 设置工作区布局

新增 `SettingsLayout.vue` 作为设置域布局，挂载在 `/settings` 路由下。布局复用 `AppSidebar` 的 `Sidebar`、折叠、inset、移动端适配和 `NavUser` 外壳，但将 `NavMain` 的数据源切换为设置导航。主区域使用现有 TopBar/Header 和页面内容容器，子页面通过 `<RouterView />` 渲染。

设置侧栏顶部固定“返回系统”，目标由 `settings.returnTo` 解析，默认值为 `/agent`；若用户从特定业务页进入，可传入经过白名单校验的 `returnTo`，不允许把任意外部 URL 写入路由或造成开放重定向。返回操作是明确导航，不依赖浏览器后退。

建议菜单分组如下：

```text
系统设置
├── 返回系统
├── 账户设置
├── 团队与安全
│   ├── 团队信息与安全
│   ├── 团队成员
│   └── 角色管理
├── 业务配置
│   ├── 审批流程管理
│   ├── 获客来源
│   └── 采购方式管理
└── 智能与集成
    ├── AI 配置
    ├── 通知配置
    └── 第三方集成
```

### 3.2 Settings Navigation Registry

新增 `CRM-Client/src/settings/settingsNavigation.ts`，以一份类型化注册表描述设置模块：`id`、`label`、`icon`、`routeName`、`path`、`group`、`requiredAnyPermissions`、`requiredAllPermissions`、`requiresTeam`、`scope`、`legacyPaths`、`featureFlag` 和 `order`。

注册表只描述导航与访问契约，不放业务请求和组件状态。`SettingsLayout` 根据当前用户的有效权限投影菜单；路由 `meta.settingsKey` 从同一注册表解析；按钮权限仍由页面使用权限 Store，但权限码常量来自同一共享模块。若一个页面允许“查看”但不允许“编辑”，注册表只要求查看码，页面内部按操作码控制按钮。

前端不得把“菜单隐藏”当作安全控制。路由守卫和后端 API 必须再次验证；无权限直达页面显示统一 `ForbiddenState`，不发起会泄露数据的列表请求。

### 3.3 推荐路由树

```text
/settings                         -> /settings/account
/settings/account                 -> 账户设置
/settings/team                    -> 团队信息与安全
/settings/members                 -> 团队成员
/settings/roles                   -> 角色管理
/settings/approval-flows          -> 审批流程管理
/settings/approval-flows/create   -> 新建审批流程
/settings/approval-flows/:id      -> 审批流程详情
/settings/approval-flows/:id/edit -> 编辑审批流程
/settings/acquisition-sources     -> 获客来源
/settings/procurement-methods     -> 采购方式管理
/settings/procurement-methods/:methodId/stages -> 阶段模板
/settings/ai                      -> AI 配置
/settings/notifications           -> 通知配置
/settings/integrations            -> 第三方集成
```

账户页不依赖团队，可在无团队状态下访问；其余页面默认 `requiresTeam=true`。`/settings` 默认重定向到账户页，若当前用户无法访问账户页（异常或未来产品变更），再按注册表选择第一个可访问页面，绝不重定向循环。

### 3.4 旧路由兼容

保留 `/account`、`/system-config`、`/roles`、`/approval-flows`、`/procurement-methods`、`/ai-config`、`/notification-config`、`/team-members` 等旧路径，但只做一次性重定向到新页面。带有旧页面 query 的链接要建立显式映射，例如旧的 `?open=roles` 转为 `/settings/roles`，不把旧 query 原样传播到无意义的页面。

审批和采购的旧详情/编辑路径需保留参数映射；若旧路径的资源不存在或没有权限，按新页面的 404/403 规则处理。迁移收口前不删除兼容路由，以覆盖历史书签、外部链接和测试环境中的深链。

## 4. 前端实现方案

### 4.1 组件分层

建议新增以下项目级组件，先封装再在页面使用：

- `SettingsLayout`：设置域外壳、侧栏切换、返回系统、团队切换后的上下文重建。
- `SettingsSidebar`：消费注册表，处理分组、活动态、折叠、移动端可达性。
- `SettingsPageHeader`：统一标题、描述、主操作、面包屑/返回层级。
- `SettingsSection`：表单页分组和卡片层级。
- `SettingsListPage`：统一列表页骨架、筛选区、DataTable、分页、加载/空/错状态。
- `SettingsPermissionGate`：对按钮/区块做权限显隐与禁用理由；不替代后端鉴权。
- `SettingsForbiddenState`、`SettingsNoTeamState`、`SettingsUnsavedGuard`：统一页面状态与离开保护。

项目已有能力优先使用；如果确实缺少能力，基于 shadcn-vue 的 `Sidebar`、`Card`、`Table/DataTable`、`Dialog`、`Sheet`、`Form`、`Input`、`Select`、`Switch`、`Alert`、`Empty` 等组件封装为 CRMWolf 组件后使用，禁止页面直接堆叠第三方原始组件形成第二套视觉。

### 4.2 页面迁移策略

页面迁移采用“外壳先行、内容搬运、能力收口”的顺序。第一步将 Sheet 内的查询、表单、操作函数拆成页面可复用的 composable 或 service；第二步将列表主体替换为 `SettingsListPage`，保留短任务 Dialog；第三步删除 `SystemConfig.vue` 对 Sheet 的打开状态依赖，让卡片改为路由链接；第四步下线旧入口但保留重定向。

不要直接复制八份 Sheet 模板。页面的列表查询、过滤、分页、保存、错误和刷新逻辑应按资源抽成 `useSettingsResourceList` 或具体领域 composable；每个领域的 API 响应仍通过 Zod schema 解析，禁止使用 `any` 或裸 `dict`。

### 4.3 列表、筛选和分页

角色、成员、审批流程、获客来源和采购方式页面继续支持原有业务搜索/筛选。列表页遵循设计系统：筛选区在表格上方，搜索明确触发，不因输入即时发请求；筛选变化后页码重置为 1，分页切换不清空筛选。查询条件可序列化到 URL query，刷新后恢复；敏感表单值、密钥和密码不得进入 query 或 localStorage。

对于已经支持服务端分页的 API，前端不得在当前页执行客户端筛选后再 `slice`。角色 API 当前返回数组且 `pagination.total` 由前端按数组长度推断，技术改造时应优先升级为 `{ items, total, page, page_size }`，兼容期内页面可适配旧数组响应，但不应继续新增依赖旧结构。所有列表的字段、筛选、排序能力仍遵循设计系统的字段注册表原则。

### 4.4 页面状态和导航行为

每个设置页至少有以下状态：初始加载 Skeleton、加载失败 ErrorState、无数据 Empty、筛选无结果、无团队 NoTeam、无权限 Forbidden、保存中禁用重复提交、保存成功 toast/状态、保存失败保留用户输入、并发冲突刷新提示。路由切换或团队切换时取消未完成请求，防止旧团队响应覆盖新团队数据。

页面存在未保存表单时，浏览器返回、侧栏切换、返回系统、团队切换和刷新前必须触发统一确认；提交成功后清除 dirty 状态。若权限在页面停留期间被撤销，下一次 API 返回 403 时清理相关缓存并显示 Forbidden，不能继续渲染旧团队数据。

## 5. 权限统一技术方案

### 5.1 权限模型

统一模型为：**权限码是唯一授权判定；角色只是权限码集合；团队所有者是团队范围的有效权限兜底；领域安全规则是独立于普通 CRUD 的不变量。**

常规页面和操作不再写 `TEAM_ADMIN` 角色判断。建议使用以下权限码（最终以数据库权限字典为准）：

| 能力域 | 查看 | 编辑/操作 |
| --- | --- | --- |
| 账户 | 无团队要求，用户本人 | `user:profile:edit`、`user:password:change`、`user:oauth:manage` |
| 团队信息与安全 | `team:settings:view` | `team:settings:update`、`team:invite:manage`、`team:ownership:transfer` |
| 团队成员 | `team:member:view` | `team:member:invite`、`team:member:update`、`team:member:remove`、`team:member:password_reset` |
| 角色 | `role:view` | `role:manage`、`permission:manage` |
| 审批流程 | `approval:flow:view` | `approval:flow:create`、`approval:flow:edit`、`approval:flow:delete`、`approval:flow:activate` |
| 获客来源 | `acquisition_source:view` | `acquisition_source:create`、`acquisition_source:update`、`acquisition_source:delete` |
| 采购方式 | `procurement_method:view` | `procurement_method:create`、`procurement_method:update`、`procurement_method:delete` |
| 阶段模板 | `procurement_stage:view` | `procurement_stage:create`、`procurement_stage:update`、`procurement_stage:delete` |
| AI | `ai:read` | `ai:manage`、`ai:test` |
| 通知 | `notification:read` | `notification:manage`、`notification:test` |
| 第三方集成 | `integration:read` | `integration:manage`、`integration:test` |

现有 `procurement_method:view`、`procurement_stage:create/update/delete`、`acquisition_source:*`、`approval:flow:create/edit`、`role:manage`、`permission:manage`、`ai:manage` 应作为兼容别名逐步迁移，避免一次发布导致旧角色全部失权。后端依赖最终只接受规范码，兼容别名在权限解析层映射，不在业务 API 里继续堆叠 `or`。

通知权限必须独立，不得再复用 `approval:flow:edit`；角色成员查询不得复用审批流程权限；AI 的查看与管理分开。`TEAM_ADMIN` 仍可作为系统内置角色和审批角色标识，但不再作为常规设置 API 的授权分支。

### 5.2 团队所有者的有效权限

团队所有者进入当前团队后，权限服务返回该团队全部“团队范围”权限码的并集，确保即使历史数据中 `TEAM_ADMIN` 没有完整 `role_permissions` 行，也能进入设置、修复角色配置、邀请成员和转移所有权。该隐式集合不包含平台级、跨团队、运维级权限，也不绕过领域安全规则。

建议在 `PermissionService` 增加统一的 `get_effective_permission_codes(db, user_id, team_id)`：

1. 校验用户属于 `team_id`。
2. 查询用户角色权限集合。
3. 查询 `Team.owner_id`；若等于当前用户，加入权限字典中标记为 team-owner-derived 的团队权限。
4. 根据权限 scope 排除 platform/global 权限。
5. 返回去重后的权限对象/码集合和 `is_team_owner` 元数据。

`require_permission()`、`check_permission()`、用户权限接口、路由访问判断都只调用这一入口。所有权转移必须在一个事务中更新 `Team.owner_id`、新旧所有者的必要角色关系、审计日志，并清理新旧所有者当前团队权限缓存；转移后原所有者立即以新权限集合生效。禁止只在前端把所有者视为管理员。

### 5.3 领域安全规则

以下不是普通菜单权限，必须在领域服务中独立保护：

- 不能移除自己；不能让团队失去最后一个可管理者。
- 所有权转移必须指定团队成员，二次确认并校验当前所有者身份。
- 成员角色替换不能绕过目标用户属于当前团队的校验。
- 审批流程修改不追溯修改已创建的审批实例；审批人身份需按实例快照/当前有效成员规则明确校验。
- 采购方式、阶段模板、获客来源被业务引用时禁止物理删除；停用只影响新建和可选项，历史数据继续显示原名称。
- 发票历史记录不依赖可变客户发票抬头关联，必须保存展示快照。

### 5.4 缓存与会话失效

权限缓存继续使用 Redis，但所有写操作统一经过权限/团队服务执行缓存失效：

- 角色权限修改：清理该角色关联的所有团队用户缓存；必要时广播权限版本变化。
- 成员角色变更：清理目标成员当前团队缓存。
- 成员移除：清理目标成员团队缓存，并令其当前团队 token/会话在下一次请求上返回团队无效。
- 所有权转移：清理新旧所有者该团队缓存，并刷新团队版本。
- 团队切换：前端清理业务 query cache、取消请求、刷新 `/auth/me/permissions` 和 `/teams/me`，再恢复目标路由。
- 权限接口支持 `use_cache=false` 的强制刷新，管理操作成功后前端主动 refresh；不能依赖 1 小时 TTL 等待自然过期。

## 6. 各页面技术拆分

### 6.1 账户设置

前端从 `/account` 迁移到 `/settings/account`，复用现有账户页的用户信息、修改密码、飞书个人绑定能力。账户页不要求当前团队，避免无团队用户陷入死胡同。密码提交使用已有 Zod/VeeValidate 校验；成功后按现有认证策略决定是否使其他会话失效，不在页面中保存明文密码。

个人飞书绑定调用现有 OAuth binding API；绑定状态属于用户在当前团队的关联，页面文案需要明确“个人绑定”和“团队级飞书应用配置”不同。解绑要确认，并在 OAuth 回调失败、账号已被其他用户绑定时显示明确错误。

### 6.2 团队信息与安全

新增页面读取 `/v1/teams/me` 或当前团队详情，展示团队名称、邀请码、所有者、创建时间和团队状态。团队名称更新走 `team:settings:update`；邀请码重置走 `team:invite:manage`，必须二次确认，成功后刷新团队信息并使旧邀请链接失效。

PRD 中的所有权转移目前后端没有对应接口，应新增显式接口，例如 `POST /v1/teams/{team_id}/ownership-transfer`，请求体使用 Pydantic schema，包含目标成员、确认文本和幂等键。服务端事务校验当前所有者、目标成员、最后管理员保护、审计和缓存刷新。团队停用、删除、恢复若不在本次范围，应在页面上不展示虚假按钮，并列为后续能力。

### 6.3 团队成员

复用 `teamApi` 现有成员接口，但补齐服务端统一权限依赖、分页/搜索契约、目标成员团队归属校验和审计。成员列表不得通过“是否有角色”判断是否属于团队，应以 `user_teams` 为准；当前后端更新用户名和重置密码仍以 `TEAM_ADMIN` 硬编码，迁移到 `team:member:update` / `team:member:password_reset`，同时保留最后管理员与本人保护。

邀请、移除、角色替换、重置密码均为短任务 Dialog。批量移除或批量分配若后续上线，使用幂等请求和逐项结果返回，部分失败不能假装全部成功。删除成员后列表刷新、权限缓存刷新和当前用户被移除的回退路径必须可验证。

### 6.4 角色管理

现有 `roles.py` 的角色定义是全局表，角色成员通过 `user_roles.team_id` 关联。页面化一期不改变这一模型，但所有角色查询、角色详情、权限关联都应明确角色是否为系统内置角色，避免把全局角色误当作团队私有角色。

角色列表接口建议统一返回分页结构，并确保涉及成员统计的查询以当前团队过滤。角色编辑与权限配置分开提交：基本信息变更和权限集合变更各自有版本/审计，权限配置保存成功后刷新受影响用户的权限缓存。内置 `TEAM_ADMIN`、`SALES_MEMBER` 等系统角色应限制删除和关键字段修改，防止破坏审批角色和新团队初始化。

### 6.5 审批流程管理

审批页面消费现有 `/v1/approvals` 流程管理接口和审批 AI 能力。列表查询、状态、授权类型、业务单据类型等筛选均由服务端执行；流程模板的启停只影响后续提交，不修改已经创建的审批实例。创建/编辑保存流程和节点时使用事务，节点编码唯一、至少一个节点、审批角色有效等校验保留。

审批流程详情页需区分“模板配置”和“运行实例”：设置页展示模板及引用/生效状态，审批中心继续展示实例。若流程有待处理实例，停用和删除应给出影响说明；已有实例必须仍可完成或按领域规则迁移，不能因模板删除而变成悬空数据。

### 6.6 获客来源

继续使用 `acquisition_source:*` API 和 `public_id`，不改为旧式数字 ID 路由。页面保留启用/停用、搜索、排序和引用统计。被线索或客户引用的来源不物理删除；停用后不出现在新建表单选项，但历史记录仍显示原名称。排序接口必须以当前团队为范围，写入后返回完整排序结果。

### 6.7 采购方式与阶段模板

采购方式列表和详情请求统一携带当前团队；页面路由 `/settings/procurement-methods/:methodId/stages` 复用现有阶段模板接口。阶段模板继续使用 `version_lock` 乐观锁，409 时前端保留编辑内容并提示重新加载；删除前检查商机引用，失败返回可理解的业务原因。

采购方式编码和名称唯一性、启用状态、新建表单默认阶段、阶段顺序和默认起始阶段等规则保持不变。页面不能把采购方式停用解释成历史商机数据清空；停用只影响新建/编辑时的可选项，历史商机保留快照或稳定引用。

### 6.8 AI 配置

现有 AI API 为 `/v1/ai/config`、`POST /v1/ai/config`、`POST /v1/ai/test`。后端当前直接调用权限服务并用 `system:config`/`ai:manage`/`ai:read` 判断，需统一到 `require_permission` 和当前团队参数。返回只保留脱敏 API Key；保存时空 key 表示保持原值，不能把脱敏值回写覆盖真实密钥。

连接测试必须区分“测试未保存表单配置”和“测试已保存团队配置”，请求体不能把 API Key 写入日志。测试超时、供应商错误和 SSE 中断都要给出可重试反馈；保存和测试按钮避免并发提交。

### 6.9 通知配置

现有通知接口位于 `/v1/system/configs/notification`，系统配置表为 `crm_system_configs`。需要删除 `TEAM_ADMIN` 与 `approval:flow:edit` 的组合判断，改为 `notification:read`、`notification:manage`、`notification:test`。通知配置是团队级，不能被个人飞书绑定替代。

响应字段中 Webhook、App Secret 等敏感值必须只返回是否已配置或掩码；更新接口从“可选字段 patch”明确为带版本的 Pydantic 更新请求，避免空值误清除。通知测试不应改变配置，失败需记录可定位的错误事件但不记录密钥。

### 6.10 第三方集成

现有 OAuth API 同时包含团队级飞书应用配置和个人账号绑定。页面必须分两个区域表达：团队级飞书应用/机器人配置使用 `integration:manage`；个人绑定继续由账户页使用个人能力。保存 App Secret、Encrypt Key、Verification Token 时只写入加密存储，响应脱敏，复制操作需要明确风险提示。

集成回调必须继续校验 team_id、state、invite_code/user_id 和账号归属，不能因页面路由调整放宽回调安全。团队切换后禁止复用上一个团队的配置缓存。

## 7. API 契约与数据边界

### 7.1 通用约定

- 所有团队级接口从 `get_current_user_team` 获取当前团队，不信任前端传入的任意 team_id；需要路径 team_id 时必须校验当前用户属于该团队且与当前上下文一致。
- 入参/出参使用 Pydantic schema；不以裸 `dict` 作为 API 边界。
- 统一错误语义：401 未登录/凭证无效，403 无权限或无团队权限，404 资源不存在，409 乐观锁/状态冲突，422 参数校验失败。
- 列表接口推荐统一为 `{ items, total, page, page_size }`，兼容旧数组响应到迁移完成，但新页面不再依赖数组长度推断总数。
- 所有写操作支持前端防重复提交；高风险写操作支持 `Idempotency-Key` 或请求幂等 token。

### 7.2 建议接口矩阵

| 页面能力 | 当前接口/来源 | TRD 调整 |
| --- | --- | --- |
| 当前团队 | `GET /v1/teams/me` | 保留；统一返回团队状态、owner 标识和可用能力摘要 |
| 我的团队 | `GET /v1/teams/user-teams` | 保留；切换后返回当前 team_id 和权限版本 |
| 切换团队 | `POST /v1/teams/switch` | 保留；服务端更新当前团队，前端重建上下文 |
| 团队成员 | `GET /v1/teams/{team_id}/members` | 增加统一权限、分页、搜索和 user_teams 归属校验 |
| 团队设置 | `PUT /v1/teams/{team_id}` | 改为 `team:settings:update`，审计名称变更 |
| 邀请/邀请码 | 现有 invite/regenerate-code | 改为独立权限和幂等/审计；重置使旧 code 失效 |
| 所有权转移 | 暂无 | 新增 Pydantic 请求/响应、事务、二次确认、审计、缓存刷新 |
| 角色 | `/v1/roles` | 增加团队安全过滤、统一分页、内置角色保护 |
| 角色权限 | `/v1/roles/{id}/permissions` | 规范权限码/版本、审计、刷新受影响成员缓存 |
| 审批流程 | `/v1/approvals/...` | 模板/实例分离，保留团队隔离和状态影响说明 |
| 采购方式 | `/v1/procurement-methods/...` | 所有详情/写入明确 team_id，统一状态/分页 |
| 阶段模板 | `/v1/procurement-stage-templates/...` | 保留 version_lock、引用检查、409 |
| 获客来源 | `/v1/acquisition-sources/...` | 保留 public_id、引用统计、停用/排序 |
| AI | `/v1/ai/config`、`/v1/ai/test` | 统一权限依赖，脱敏和测试隔离 |
| 通知 | `/v1/system/configs/notification` | 拆分 notification 权限，Pydantic patch/version |
| 飞书集成 | `/v1/auth/oauth/feishu/...` | 区分团队配置与个人绑定，回调安全不变 |
| 当前权限 | `/v1/auth/me/permissions` | 返回 effective codes、team_id、is_team_owner、permission_version |

### 7.3 权限接口响应

建议扩展当前权限响应，不仅返回权限数组，还返回当前上下文：

```json
{
  "team_id": 123,
  "is_team_owner": true,
  "permission_version": "team-123-v8",
  "permissions": [
    { "code": "team:member:view", "scope": "team", "source": "owner" }
  ]
}
```

前端只使用 `permissions[].code` 做快速判断；`source` 和 `permission_version` 用于诊断、缓存失效和测试，不作为前端安全依据。平台权限不得混入团队权限数组。

## 8. 数据库与迁移策略

页面化本身不新增业务表。已有 `teams`、`user_teams`、`roles`、`user_roles`、`permissions`、`role_permissions`、`crm_system_configs`、审批/采购/获客来源表继续作为事实来源。

可能需要的 Alembic migration 按实际盘点结果拆分，不能把所有变化塞进一条迁移：

1. **权限字典迁移：**新增缺失的标准设置权限码，建立旧码到新码的兼容映射，给内置团队所有者/管理员补齐权限集合；确认不把平台权限授予团队所有者。
2. **团队所有权/状态迁移：**若所有权转移需要状态、转移记录或邀请版本字段，再新增最小字段和索引；否则复用 `teams.owner_id`，不新增重复表。
3. **审计迁移：**优先复用 `crm_operation_logs`；若要区分设置操作，只新增事件类型/资源类型数据字典，不复制审计表。敏感字段只记录“已更新/已测试”，不记录密钥原文。
4. **历史快照迁移：**如果现有发票申请没有抬头快照字段，必须单独评估并新增快照字段/回填策略；页面化不应在设置模块中重建发票抬头。

所有 migration 必须可回滚，在测试数据库执行 `alembic upgrade head`，并验证旧数据、团队隔离、唯一约束和权限缓存刷新。权限字典迁移发布前应先做只读盘点：统计缺失角色权限、孤立 user_roles、无 owner 团队和被引用的停用配置，不输出业务敏感内容。

## 9. 设计系统与 shadcn-vue 约束

实现以 `CRM-Docs/design-system/README.md` 及对应主题为唯一视觉约束。设置列表页遵循 `patterns/list-page.md`：筛选区、表格、分页共享上下文，筛选由服务端执行，加载/空/错误状态明确。表单页遵循 `patterns/form-page.md`：字段分组、校验反馈、提交状态和未保存保护清晰。Sidebar、Table、Modal/Sheet、Tabs 使用项目文档中规定的交互与可达性。

优先复用已有 CRMWolf 封装组件和 `components/ui`。若缺少组件能力，使用 shadcn-vue 文档中的对应组件（https://www.shadcn-vue.com/docs/components），但必须先在项目内封装为统一的 CRMWolf 组件，再由业务页面使用。不得让不同设置页各自直接引入 shadcn 原始实现，不得造轮子、引入新的 UI 库或恢复已废弃样式。

视觉上保持现有 Sidebar、inset、Card、TopBar、颜色 token、间距、圆角和 toast 反馈；页面化只改变承载层级，不对无关业务页面进行重设计。设置侧栏在 768px 断点下遵循现有折叠/移动端策略，页面主体不产生横向滚动，表格仅在自身容器内滚动。

## 10. 错误、并发、幂等与敏感数据

- **403：**不显示受保护列表数据；使用统一 Forbidden 状态，并提供返回可访问设置页/返回系统操作。
- **无团队：**账户设置可用；团队级页面显示 NoTeam，并提供创建/加入团队入口，不能把用户重定向到不存在的团队设置。
- **NO_CURRENT_TEAM：**进入设置前引导选择团队；选择成功后刷新权限和页面数据。
- **404：**资源删除或旧链接失效时显示资源不存在，不把空数据误显示为成功。
- **409：**阶段模板、审批流程或其他带版本资源发生并发修改时，保留用户输入并要求重新加载/合并。
- **部分失败：**批量邀请、批量角色变更、批量移除按项展示结果，支持重试失败项。
- **幂等：**写请求按钮在 pending 时禁用；高风险接口使用幂等键，重复请求返回第一次结果或明确已处理。
- **敏感数据：**密码、API Key、App Secret、Webhook token、Encrypt Key 不进入 URL、localStorage、前端日志、操作日志或错误详情；服务端响应只返回掩码/已配置标志。
- **未保存离开：**统一拦截路由、侧栏、团队切换、返回系统和浏览器 beforeunload。
- **权限变化：**接口 403 后刷新权限一次；仍无权则清理页面数据并进入 Forbidden，不进行无限重试。

## 11. 测试方案

### 11.1 前端

- 路由测试：`/settings` 默认跳转、每个子路由、旧路径重定向、参数映射、无团队和 403。
- 导航测试：普通成员只看到账户页；团队所有者看到所有团队设置；权限变化后菜单刷新；返回系统使用稳定目标。
- 权限组件测试：requiredAny/requiredAll、查看与编辑分离、按钮禁用理由、页面直达不发请求。
- 页面状态测试：Skeleton、Empty、筛选无结果、Error、保存中、409、403、未保存离开、团队切换取消请求。
- 列表测试：筛选触发、清空、分页保持筛选、URL query 恢复、服务端 total 展示；不得在当前页客户端二次筛选。
- 表单测试：Zod 校验、重复提交、敏感字段不进入 query/localStorage、保存后刷新和 toast。
- 组件测试：SettingsLayout、SettingsSidebar、SettingsPageHeader、SettingsListPage 的键盘、活动态、移动端折叠。

### 11.2 后端

- 权限单元测试：普通角色、多个角色并集、团队所有者隐式团队权限、平台权限排除、无团队、跨团队访问。
- 权限契约测试：设置注册表中的每个页面权限码都存在数据库权限字典；前端按钮码与后端依赖码不出现孤儿。
- API 测试：所有团队接口携带并校验 team_id；成员/角色/配置/审批/采购/获客来源不得跨团队读取或写入。
- 领域安全测试：最后管理员保护、不能移除自己、所有权转移、邀请码失效、被引用配置停用/删除、审批模板与实例解耦、发票抬头快照。
- 缓存测试：角色权限变更、成员变更、所有权转移、团队切换后缓存立即失效；旧缓存不能恢复已撤销权限。
- 并发测试：阶段模板 version_lock 409、重复邀请/重复保存、重复转移所有权、重复重置邀请码。
- 敏感字段测试：AI/OAuth/通知响应脱敏、日志脱敏、异常不泄露凭证。
- Migration 测试：空库、既有数据、旧权限字典、回滚和 `alembic upgrade head`。

### 11.3 验收场景矩阵

| 场景 | 期望 |
| --- | --- |
| 普通成员无团队 | 可进 `/settings/account`，团队页面显示无团队状态 |
| 普通成员有团队 | 只看到账户和实际拥有查看权限的页面 |
| 团队所有者角色权限被误删 | 仍能进入当前团队全部团队级设置并修复权限 |
| 所有权转移 | 新所有者立即获得全部团队级权限，原所有者按新权限生效 |
| 成员被移除 | 当前成员下次请求被拒绝并回到团队选择/无团队处理 |
| 配置被其他人修改 | 页面显示 409，保留输入并要求刷新 |
| 被引用获客来源/阶段 | 禁止物理删除，可停用，历史数据仍可显示 |
| 修改发票抬头名称 | 历史发票申请显示原快照，不显示 `-` |
| 旧书签 `/system-config` | 无循环，进入 `/settings/account` 或第一个可访问页 |
| 切换团队 | 取消旧请求，刷新权限和数据，不串团队数据 |

## 12. 实施顺序、发布与回滚

### Phase 0：契约和基础设施

- 盘点权限字典、角色权限、页面 API 和所有硬编码 `TEAM_ADMIN` 的设置/团队接口。
- 确定标准权限码、旧码兼容策略、所有者有效权限算法和缓存失效事件。
- 增加 Settings Navigation Registry、布局、权限 Gate、Forbidden/NoTeam 状态和路由测试。
- 不改变旧入口行为，先让新壳可以灰度访问。

### Phase 1：高频设置页面

- 账户设置、团队信息与安全、团队成员、角色管理、审批流程页面化。
- 迁移旧 Sheet 的业务逻辑到页面和短任务 Dialog。
- 后端统一团队权限、角色查询范围、所有者保护和审计。
- 通过 feature flag 或内部用户白名单逐步开放。

### Phase 2：业务配置

- 获客来源、采购方式和阶段模板页面化。
- 补齐分页、服务端筛选、排序、乐观锁、引用保护和深链。

### Phase 3：智能与集成

- AI、通知、第三方集成页面化。
- 完成独立权限、敏感字段脱敏、测试连接和失败重试。

### Phase 4：收口

- 用户菜单只保留“系统设置”；旧卡片仅作为兼容重定向，不再维护 Sheet 一级入口。
- 完成历史链接、浏览器刷新/前进后退、移动端、权限撤销、团队切换、无团队和异常状态回归。
- 删除不再被引用的旧 Sheet 容器和重复权限分支；保留必要的兼容路由。

发布策略采用向后兼容优先：先发布后端权限兼容和新路由，再发布前端入口切换；发现问题时将入口 feature flag 切回旧入口，保留 API 和数据库迁移，不回滚会破坏已有数据的权限/快照迁移。回滚后仍需清理新页面缓存和权限缓存，避免用户继续看到错误菜单。

## 13. 文件影响清单

### 前端新增/调整

- `CRM-Client/src/router/index.ts`：新增 `/settings/**`、meta、守卫、旧路由映射。
- `CRM-Client/src/components/app-sidebar/AppSidebar.vue`、`NavMain.vue`、`NavUser.vue`：设置上下文和单一入口。
- `CRM-Client/src/settings/settingsNavigation.ts`：导航/权限注册表。
- `CRM-Client/src/layouts/SettingsLayout.vue` 或等价布局目录：设置工作区外壳。
- `CRM-Client/src/components/settings/*`：项目级设置布局、列表、状态和权限组件。
- `CRM-Client/src/views/settings/*`：各设置页面。
- `CRM-Client/src/composables/*`、`src/api/*`、`src/schemas/*`：页面复用逻辑、接口和 Zod 契约。
- `CRM-Client/src/components/system-config/*`：迁移期间保留短任务组件，页面上线后移除一级 Sheet 依赖。

### 后端新增/调整

- `CRM-Server/app/core/deps.py`：统一有效权限依赖，减少角色硬编码。
- `CRM-Server/app/services/permission_service.py`：所有者权限、scope、版本和缓存失效。
- `CRM-Server/app/constants/permissions.py`：设置权限码和兼容映射。
- `CRM-Server/app/api/teams.py`、`roles.py`、`system_configs.py`、`ai_config.py`、`oauth.py`、审批/采购/获客来源 API：统一鉴权、团队隔离、审计和响应结构。
- `CRM-Server/app/schemas/*`、`app/services/*`、`app/crud/*`：Pydantic 契约和领域服务。
- `CRM-Server/migrations/versions/*`：仅在权限字典、所有权/审计/历史快照确有需要时新增 Alembic migration。
- `CRM-Server/tests/*`：权限、接口、迁移、并发和敏感字段测试。

## 14. 风险、待确认项与决策门禁

| 风险/待确认项 | 技术处理 |
| --- | --- |
| `TEAM_ADMIN` 是角色、所有者还是审批角色语义混用 | 统一：所有权决定 owner-derived 权限，角色只做权限集合，审批角色单独保留业务语义 |
| 角色表全局、角色分配团队级 | 一期不改模型；禁止把团队私有角色需求混入页面化，若未来需要另立设计 |
| 现有权限字典缺少建议标准码 | 先做只读盘点和兼容映射，再通过 migration 补码；不直接在前端写不存在的码 |
| 所有权转移接口当前不存在 | 需要产品确认目标成员、是否支持回收原所有者、二次确认文案和审计保留期 |
| 团队停用/删除/恢复 | 本期页面不展示未实现按钮；需单独定义生命周期和数据保留策略 |
| 角色、成员、审批接口分页结构不一致 | 统一新契约，兼容旧响应，分阶段切换 |
| 旧 Sheet 与页面并存 | 每个页面上线后立即让入口走路由，不新增两套业务实现 |
| 发票抬头历史快照现状 | 需以现有 invoice/license 数据盘点为准，必要时单独 migration 和回填 |
| 平台级权限边界 | 权限字典必须有 scope；所有者隐式权限只覆盖 team scope |
| 跨实例缓存刷新 | 若部署有多个后端实例，需使用 Redis pub/sub 或权限版本号，不能只清本地进程缓存 |

进入开发前必须锁定：标准权限码清单、所有者有效权限的实现方式、所有权转移范围、团队生命周期按钮范围、角色是否允许团队自定义、历史发票抬头快照是否需要 migration、统一列表响应是否一次性切换还是兼容迁移。

## 15. 技术验收结论

满足以下条件后，技术方案才可进入实现：

- `/settings` 是唯一规范入口，设置导航、路由 meta、页面访问和操作按钮使用同一权限注册/契约。
- 团队所有者在当前团队内不会因为 `TEAM_ADMIN` 角色权限行缺失而失去全部团队级权限，但不获得平台级权限。
- 常规设置 API 不再通过 `TEAM_ADMIN` 或审批权限旁路授权；领域安全规则有独立服务端保护。
- 一级管理内容不再依赖 Sheet；短任务 Dialog 保持焦点、未保存保护和明确结果反馈。
- 所有团队级查询携带并校验 team_id；配置引用、审批实例、历史发票抬头和敏感字段符合 PRD 规则。
- 页面遵循现有 CRMWolf 设计系统和 shadcn-vue 封装约束，列表筛选由服务端执行，移动端和无障碍路径可用。
- 迁移、兼容路由、缓存、权限撤销、并发、幂等、审计和回滚均有测试与发布方案。

## 16. 修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-08-31 | 基于《系统设置页面化优化 PRD》及现有 CRMWolf 前后端、权限、路由、Sheet、配置、审批、采购、获客来源和设计系统实现形成 TRD。 |

# 系统设置工作区视觉与操作统一

- 日期：2026-09-17
- 状态：用户已确认方向，待书面审阅
- 范围：`/settings/**` 全部子页面的外壳、列表、分组表单、行操作和主操作放置
- 上游决定：对齐业务页，不换皮；列表走 DataTable；表单卡片左右撑满并复用客户编辑两列网格；已有组件直接复用，不为设置另做一套视觉
- 相关规范：`CRM-Docs/design-system/patterns/list-page.md`、`CRM-Docs/design-system/patterns/form-page.md`、`CRM-Docs/design-system/components/table.md`、`CRM-Docs/design-system/components/list-card.md`、`CRM-Docs/design-system/components/card.md`、`CRM-Docs/requirements/2026-08-31-system-settings-page-optimization.md`
- 相关实现：`CRM-Client/src/views/SettingsModulePage.vue`、`CRM-Client/src/views/AccountSettings.vue`、`CRM-Client/src/views/TeamSettings.vue`、`CRM-Client/src/views/ProcurementStagesSettings.vue`、`CRM-Client/src/components/system-config/*`、`CRM-Client/src/components/crmwolf/DataTable.vue`、`CRM-Client/src/views/Customers.vue`、`CRM-Client/src/views/CustomerEdit.vue`

## 1. 背景与目标

设置工作区外壳已经在：`SettingsSidebar`、`/settings/**` 路由、TopBar 标题。内容没有从抽屉迁完。

现状是三套骨架叠在同一侧栏下：

1. 账户页：V2 大卡片 + 页内 `<h2>`，和 TopBar 标题重复；个人信息是只读定义列表。
2. 团队页 / 采购阶段页 / `SettingsModulePage`：`max-w-6xl p-6`，页内再写「系统设置」眉题和大标题。
3. 成员、角色、审批、获客来源、采购、产品、AI、通知、集成：`SettingsModulePage` 把旧 `*Sheet` / `*Panel` 以 `embedded` 嵌进页面。搜索栏、ListCard、一行 3～4 个图标按钮仍是抽屉布局。

ListCard 规范写明：只用于 Sheet、侧栏等受限空间；完整列表页、需要检索的场景用表格。设置已经是完整页面，继续用 ListCard 会和客户 / 合同列表手感分裂。

成员页还把邀请码、复制链接、重置邀请码叠在列表顶上，和「团队信息与安全」职责重叠。

目标：

1. `/settings/**` 只保留两种页面类型：列表页、分组表单页；子页（采购阶段模板）沿用列表页骨架加 TopBar 返回。
2. 列表页复用客户列表的 DataTable、搜索、行操作、空/错/加载。
3. 表单页复用客户编辑的全宽卡片 + 两列网格 + 底部操作条；去掉 `max-w-6xl` 和并排窄卡。
4. 主操作、搜索、行操作、说明文字的位置全工作区一致。
5. 不改权限码、业务规则、敏感字段脱敏、引用保护。

## 2. 非目标

- 不改权限模型、所有者兜底、菜单注册表语义。
- 不改审批实例、发票抬头、业务列表入口。
- 不引入新 UI 库，不另做设置专用色板 / 字号 / 圆角。
- 不新增 `SettingsPageHeader`、`SettingsListPage`、`SettingsSection` 等平行组件库；缺的只是一层很薄的页面外壳（padding 与全宽容器）。
- 不在本期把审批流程改成独立画布编辑页（`/settings/approval-flows-new` 画布保持原样，只收口外壳）。
- 不在本期做所有权转移、团队停用/删除。
- 不为设置列表新建一套筛选/排序后端 catalog，除非该资源已经具备 list-query 协议。
- 不把临时效果样例提交进仓库。

## 3. 方案选择

采用「按页面类型对齐现有业务模式」。

放弃：

- 只统一 padding 和去掉重复 H1：列表仍是 ListCard 多按钮操作列，和客户列表操作差还在。
- 另做设置专用视觉：和设计系统、TRD「不引入新 UI 库」冲突。

## 4. 页面类型

| 类型 | 页面 | 对齐对象 |
|---|---|---|
| 列表 | 团队成员、角色管理、审批流程管理、获客来源、采购方式、产品管理、采购阶段模板 | `Customers.vue` + `DataTable` |
| 分组表单 | 账户设置、团队信息与安全、AI 配置、通知配置、第三方集成 | `CustomerEdit.vue` 的 `form-container` / `form-grid` / `form-actions-card` |
| 画布例外 | 审批流程管理（新）打开工作流编辑器时 | 现有 `WorkflowEditor`，进出编辑器时外壳仍走设置 TopBar 返回 |

侧栏分组和路由保持 `settingsNavigation.ts`，不改信息架构。

## 5. 共享外壳

设置内容区不再自己画一套页头。

```text
AppLayout
├── SettingsSidebar          ← 已有，不动
└── SidebarInset
    ├── TopBar               ← 标题来自 route.meta.title / usePageTitle
    │   ├── 列表：useTopBarRegistration 挂唯一主操作
    │   └── 表单：TopBar 不挂保存，避免和底部操作条重复
    └── 页面内容
        ├── 一句说明（可选，13px muted，不是第二套 H1）
        └── 列表 DataTable 或全宽分组 Card
```

约束：

- 去掉页内「系统设置」眉题、`text-2xl` 标题、与 TopBar 重复的主按钮。
- 内容区 padding 对齐业务页：`$wolf-page-padding-v2`（24px），不要 `max-w-6xl mx-auto`。
- 列表说明和表单说明最多一句；不再单独一张「配置说明」卡。帮助文字贴字段。
- 子页（采购阶段模板）TopBar 开返回，目标 `/settings/procurement-methods`，不用 `router.back()`。
- 权限不可用、无权限、无团队、加载失败继续用现有 `ErrorState` / `DataViewStatePanel`，文案保持各页已有含义。

允许抽一个很薄的 `SettingsContent.vue`（或等价 class）：只提供全宽 padding 和可选说明槽。禁止在这个外壳里放搜索、表格、表单字段。

## 6. 组件复用

| 能力 | 复用 | 禁止 |
|---|---|---|
| 侧栏 | `SettingsSidebar` | 新导航样式 |
| 标题 / 列表主操作 | TopBar + `useTopBarRegistration` | 页内第二套 H1 + 主按钮 |
| 列表 | `DataTable` + `defineListFields` | 设置页继续用 ListCard |
| 搜索 | `DataTableSearch`（点搜索才提交） | `v-model` 跟输入即时过滤 |
| 行操作 | `getRowActions` → 当前态 1 个主操作 + 更多 | 一行多个 ghost 图标按钮 |
| 表单容器 | shadcn `Card` 全宽；内部两列网格 token 对齐客户编辑 | `max-w-6xl`、`lg:grid-cols-2` 并排窄卡 |
| 字段 | `Form` / `FormField` / `Input` / `Select` / `Switch` / `Label` | 裸 `<label>` 与 Form 混用两套 |
| 短任务 | 现有 `Dialog` | 把长期列表塞回 Sheet |
| 状态 | `ErrorState`、Skeleton、`DataViewStatePanel` | 页面私有 pulse 条 |
| 确认 | 现有 confirm dialog | 重置邀请码 / 删除无确认 |

ListCard 退出设置一级页面后，仍可用于详情 Sheet 内的短列表，不在本期删除组件。

## 7. 列表页

### 7.1 DataTable 接入

每个列表页提供一份 `defineListFields` 注册表。DataTable 只吃这一份，不再平行维护 columns。

设置列表当前普遍是「一次拉全量 + 前端 `filter` + `pagination.total = data.length`」。这违反列表页规范：禁止当前页客户端筛选后再 `slice`。本期处理：

1. 搜索走 `DataTableSearch`，明确触发后再请求或过滤。
2. 在后端尚未提供 list-query catalog 的资源上，业务列必须显式 `filter: false` / `sort: false`，并写 `filterDisabledReason` / `sortDisabledReason`。理由写成「本期仍全量读取当前团队数据，未接入服务端 list-query」。不允许用「接口暂不支持」当长期借口，但本期不顺手升级所有设置 API。
3. `total` 必须等于当前展示集合的真实条数。去掉「请求了 skip/limit 却把 `total` 设成当前数组长度」的假分页。数据量与现在同量级（团队成员、角色、来源、采购方式通常远小于 50）时，用 `heightStrategy="page"` 或 `"auto"`，一次渲染当前结果，分页控件可保留但不要谎报总页。
4. 输入即时过滤（成员 / 角色 / 来源 / 产品现有 `computed filter`）改为提交搜索后再生效。
5. 不开启客户列表那套视图保存、列偏好、自定义筛选视图，除非该页已经有对应后端。`searchEnabled` 打开即可。

行点击：设置列表默认不打开详情 Sheet。查看类动作能进主操作或更多就不要再做整行点击。审批流程「查看」进更多或主操作「编辑」。

移动端：`mobileMode="card"`，行操作到底部，不依赖桌面操作列。

### 7.2 各列表字段与行操作

**团队成员**

- 列：成员（头像 + 姓名 + 邮箱，识别列）、角色、加入时间。
- 搜索：姓名、邮箱。
- 主操作（TopBar）：邀请成员，权限 `team:member:invite`。
- 行主操作：分配角色。更多：修改用户名、重置密码、移除。对自己不显示管理操作。
- 邀请码、复制链接、重置邀请码从本页删除，只留在团队信息页。

**角色管理**

- 列：角色名称 + 描述、代码、更新时间。有成员统计则加一列，没有就不编。
- 搜索：代码、名称。
- 主操作：新建角色。
- 行主操作：配置权限。更多：编辑、删除。内置角色删除按现有规则禁用。

**审批流程管理**

- 列：流程名称 + 编码、单据类型、金额范围、节点数、状态。
- 搜索：名称、编码。状态 / 单据类型仅当请求参数真正进服务端时才作为 DataTable 筛选；否则先放工具栏里的提交式筛选，或显式关闭字段筛选。
- 主操作：手动创建。AI 创建若保留，作为次操作进 TopBar 次按钮或工具栏，不得和「手动创建」并列两个主按钮。
- 行主操作：编辑。更多：查看、启用/停用。
- 创建 / 编辑继续用现有 `ApprovalFlowFormDialog`。

**获客来源**

- 列：名称、引用数、状态、排序。
- 搜索：名称。
- 主操作：新建来源。
- 行主操作：停用 / 启用（按当前状态切换）。更多：编辑。被引用时删除按现有规则禁止。

**采购方式**

- 列：名称 + 编码、阶段数、状态。
- 主操作：新建采购方式。
- 行主操作：阶段模板（路由到 `/settings/procurement-methods/:methodId/stages`）。更多：编辑、删除/停用。

**产品管理**

- 列：名称、状态、模块摘要（现有主信息）。
- 主操作：新建产品。
- 行主操作：编辑。更多：模块维护、启停。模块 Dialog 保持短任务。

**采购阶段模板**

- TopBar 返回采购方式。
- 列：阶段名称 + 编码、赢率、排序、默认起点、可跳过。
- 主操作：新增阶段。
- 行主操作：编辑。更多：删除。

## 8. 分组表单页

### 8.1 布局

对齐客户编辑，不是对齐团队页现在的两列窄卡。

```text
页面内容（width: 100%，padding 24px）
├── 一句说明
├── Card（全宽）分组 1
│   ├── CardHeader 标题 + 一句描述
│   └── CardContent
│       └── form-grid：桌面两列，窄屏一列
│           └── 长字段（URL、密钥、说明）占满整行
├── Card 分组 2
└── form-actions-card：仅页级保存。组内复制 / 测试 / 重置不放这里
```

- 卡片之间间距固定为 `$wolf-space-lg-v2`（16px），与客户编辑 `form-card` 一致，不用 24px 再做一套。
- 桌面 `grid-template-columns: repeat(2, minmax(0, 1fr))`；`<=768px` 单列。
- 组内次操作（复制邀请链接、重置邀请码、测试连接、发送测试）留在该组 Card 内，使用 outline / ghost，不和页级保存抢主按钮。
- 页级保存只有一个，放底部操作条。设置表单不是创建弹窗，默认不放「取消」。处理中禁用重复提交。
- 危险操作（重置邀请码、解绑飞书）必须确认。
- 只读资料（账户个人信息）用定义列表，桌面四列（标签/值/标签/值），窄屏两列；不要把只读字段装成禁用输入，除非它本来就可复制（邀请码、回调 URL）。

### 8.2 各表单页

**账户设置**

- 卡 1 个人信息：头像 + 姓名/邮箱，下面只读资料（姓名、邮箱、手机、区域、工号、状态、用户 ID、角色）。用户 ID 复制保留。
- 卡 2 安全与授权：登录密码 → 修改密码 Dialog；飞书个人绑定 / 解绑。文案写明这是个人绑定，不是团队飞书应用。
- 无页级保存。
- 去掉账户页私有 `account-settings` 大段布局中与工作区冲突的第二套 padding；保留密码 Dialog。

**团队信息与安全**

- 卡 1 团队信息：团队名称（可编辑）、只读创建时间等。
- 卡 2 邀请：邀请码、邀请链接（只读 + 复制）、重置邀请码。
- 卡 3 所有者：只读展示。不做转移。
- 页级保存只提交团队名称等可写资料。复制 / 重置不是保存。

**AI 配置**

- 卡 1 服务配置：供应商、模型（两列）；接口地址、API Key 整行。密钥不明文回显；空值保存保持原密钥。
- 卡 2 连接测试：测试消息 + 测试按钮 + 结果。测试不是保存。
- 页级保存「保存配置」。
- 现有大段说明卡删掉，改成字段 `FormDescription`。

**通知配置**

- 一卡：群名称、Webhook（两列）。发送测试为组内次操作。
- 页级保存。说明改字段帮助。

**第三方集成**

- 卡 1 飞书应用：启用开关、App ID / Secret 两列、重定向 URL 整行。
- 卡 2 AI Agent 机器人：开关与只读回调、Token / Open ID。
- 页级保存。个人飞书绑定不出现在此页。

## 9. 迁移策略

顺序：外壳 → 表单撑满 → 列表换 DataTable。不要先复制八份 Sheet 模板。

1. 抽出设置内容外壳，改 `AccountSettings`、`TeamSettings`、`SettingsModulePage`、`ProcurementStagesSettings` 去掉 `max-w-6xl` 和重复标题。这一步用户立刻能看到撑满。
2. 表单页（账户、团队、AI、通知、集成）改为全宽 Card + 两列网格 + 底部保存；Sheet 头在 `embedded` 时继续不渲染。
3. 列表页从 `legacyComponentKey` 嵌入改为真正页面：composable 留下请求/权限/Dialog，模板换成 DataTable。成员页同时拆走邀请码。
4. `SettingsModulePage` 不再作为内容宿主。各模块走具名路由组件。嵌入用的 `embedded` / `active` 分支能删就删；设置路由不再打开 Sheet。
5. `ApprovalFlowsNew` 只收口与外壳冲突的第二套 H1；画布打开时隐藏列表骨架，保留编辑器。

兼容路由（`/account`、`/roles`、`?action=create` 等）继续重定向到新页，并由页面打开对应 Dialog，不把用户丢在空白页。

## 10. 数据流与错误

- 列表请求取消：切设置子路由或切团队时 abort 进行中的请求，避免旧团队数据写到新页。
- 表单 dirty：团队名称、AI / 通知 / 集成配置在侧栏切换、返回系统、刷新前必须确认；账户页只有 Dialog 内 dirty，随 Dialog 关闭保护即可。
- 403：统一 Forbidden，不发起会泄露列表的请求。
- 保存失败保留输入；409（采购阶段 version_lock）保留编辑内容并提示重新加载。
- Toast 成功反馈沿用现有文案风格，不新造通知系统。

## 11. 测试与验收

不新挂大页 Vue 测试。改现有设置页 / 嵌入面板测试，使其断言新骨架而不是 Sheet 头。

必须可观察：

- 任意设置子页没有第二套「系统设置」眉题和 `text-2xl` 页内标题。
- 账户、团队、AI、通知、集成的卡片 `width` 为内容区 100%，不是 `max-w-6xl` 居中窄列，也不是两张卡并排各占 50%（字段两列可以，卡片本身全宽堆叠）。
- 成员 / 角色 / 审批 / 来源 / 采购 / 产品桌面是 `DataTable`，行尾是主操作 + 更多，不再是 ListCard 多图标。
- 成员页没有邀请码 / 重置邀请码；团队页有。
- 搜索提交前不发请求（或不等价于每个按键过滤全表）。
- 列表 `total` 不等于「当前数组长度冒充服务端分页」那种假总数。
- 现有 Dialog 短任务（邀请、改密、分配角色、新建来源、阶段编辑）仍可用。
- 密钥、Webhook、App Secret 不明文回显。
- 窄屏表单单列，列表卡片化，触达高度仍 44px。

手工走一遍：账户 → 团队 → 成员邀请 → 角色权限 → 获客来源启停 → 采购阶段 → AI 保存/测试 → 通知测试 → 集成保存。

## 12. 风险

1. DataTable 默认给业务列开筛选/排序。设置 API 多数还不是 list-query。漏写 `filter: false` 会让筛选弹层发出前端无法兑现的查询。每个设置 catalog 必须显式关闭并写原因。
2. 成员 / 角色等前端过滤改成提交搜索后，使用者会感觉「输入不再即时出结果」。这是规范要求，搜索框旁必须有明确搜索按钮（DataTableSearch 已有）。
3. 从 Sheet 嵌页改成真页面时，旧测试按 `SheetTitle` / `embedded` 断言会红。一并改，不保留嵌入双路径。
4. `ApprovalFlowsNew` 与旧审批页并存。本期只统一外壳，不合并两套审批产品。
5. 客户编辑的 `form-card` 带卡片阴影，DataTable 明确不带阴影。设置表单用 shadcn Card（已有 `shadow-wolf-card`），列表用 DataTable 无阴影。不要给表格再包一层带阴影的 Card。

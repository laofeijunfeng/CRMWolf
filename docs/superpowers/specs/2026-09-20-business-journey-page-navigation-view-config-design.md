# 业务旅程独立页面、导航分组与视图配置设计

- 日期：2026-09-20
- 状态：已实施（2026-09-21）
- 范围：左侧导航信息架构；独立业务旅程页面；表格 / 看板显示模式；自定义视图保存；业务旅程 Sheet；现有业务看板迁移
- 上游决定：销售日常入口增加「业务旅程」；页面默认表格，现有看板迁入同页；「视图配置」提供「看板视图」开关；系统 Tab 不持久化，用户自定义视图保存筛选、排序、字段和显示模式；表格行与看板卡片直接打开业务旅程 Sheet；页面与浮层只组合现有设计系统和既有业务组件，不私自开发重复组件
- 覆盖决定：覆盖 `docs/superpowers/specs/2026-09-16-customer-detail-business-journey-identity-design.md` 中「独立业务旅程管理页不做」「看板卡片不跳转」「DealJourneyDetailContent 只挂在 CustomerDetailSheet」三项旧决定；其余对象身份、商机详情瘦身、履约对象归属和 `public_id` 契约继续有效
- 相关规范：`CRM-Docs/design-system/README.md`、`CRM-Docs/design-system/patterns/list-page.md`、`CRM-Docs/design-system/patterns/kanban-page.md`、`CRM-Docs/design-system/components/table.md`、`docs/superpowers/specs/2026-09-16-customer-detail-business-journey-identity-design.md`
- 相关实现：`CRM-Client/src/components/app-sidebar/AppSidebar.vue`、`CRM-Client/src/views/BusinessJourneys.vue`、`CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue`、`CRM-Client/src/components/business-journey/DealJourneyDetailHost.vue`、`CRM-Client/src/views/DealJourneyDetailSheet.vue`、`CRM-Client/src/components/panels/DealJourneyDetailContent.vue`、`CRM-Client/src/components/crmwolf/DataTable.vue`、`CRM-Client/src/components/crmwolf/ListAdvancedTools.vue`、`CRM-Client/src/composables/useCustomFilterViews.ts`、`CRM-Server/app/api/business_journeys.py`、`CRM-Server/app/services/business_journey_query_service.py`、`CRM-Server/app/schemas/view_preference.py`

## 1. 背景与目标

当前左侧「销售流程」同时放了销售工作入口和交易对象列表：

```text
AI Agent
线索管理
客户管理
客户追踪
商机管理
合同管理
回款计划
```

「业务看板」位于「数据看板」，但它的数据源和阶段语义已经是 `CustomerDealJourney`，不是统计报表：

```text
初期交流 → 持续推进 → 即将签约 → 签约中 → 回款中 → 开票中 → 已完成 / 已输单
```

商机状态中的「已赢单」只表示客户已选择方案、可以进入签约，不表示合同已签、款项已回或交易已闭环。只有业务旅程能够表达从商机到合同、回款和开票的完整过程。

同时，商机、合同、回款计划不是元数据。它们是可单独查询、筛选和维护的交易业务对象。业务旅程也不替代这些对象列表；它解决的是跨对象过程追踪。

目标：

1. 新增独立「业务旅程」页面，作为销售查看完整交易推进的入口。
2. 默认表格视图，现有业务看板迁入同页，通过「视图配置」切换。
3. 表格和看板共用权限、系统 Tab、筛选、排序和业务阶段定义。
4. 用户自定义视图能够固定表格 / 看板模式；系统 Tab 只保留页面会话状态，不写后端。
5. 列表行和看板卡片直接打开业务旅程 Sheet，不再先打开客户 Sheet。
6. 重组左侧导航，区分销售工作、交易对象和财务执行。
7. 页面视觉、浮层、按钮、表格、看板、Sheet 全部复用现有组件与已有页面样式。

## 2. 非目标

- 不把商机、合同、回款计划定义为元数据或系统配置。
- 不删除商机「已赢单 / 已输单」状态。
- 不让业务旅程替代商机、合同、回款计划的精确列表与批量操作。
- 不改变创建商机、合同、回款计划、回款、发票或 License 的写接口和审批流程。
- 不提供手工「新建业务旅程」入口；创建商机仍由 `ensure_for_opportunity` 自动建立旅程。
- 不向客户、商机、合同等其他页面推广表格 / 看板显示模式。本期只有业务旅程页面使用。
- 不新建另一套视图偏好、自定义 Tab、筛选或排序框架。
- 不新建自定义 UI 控件替代已有 DataTable、筛选、排序、字段配置、按钮、Card、Sheet 等组件。
- 不重写 `DealJourneyDetailContent`；只增加独立 Sheet 壳并复用同一内容组件。
- 不把财务记录（实际回款、发票）移动到交易管理分组。

## 3. 导航信息架构

左侧导航调整为：

```text
销售工作
  AI Agent
  线索管理
  客户管理
  客户追踪
  业务旅程

交易管理
  商机管理
  合同管理
  回款计划

财务管理
  回款管理
  发票管理

数据看板
  销售看板
```

规则：

- 「销售流程」改名「销售工作」，只放销售日常入口和跨对象过程入口。
- 「业务旅程」位于「客户追踪」之后，路由 `/business-journeys`。
- 新分组「交易管理」承载商机、合同、回款计划三个交易对象列表。
- 「财务流程」改名「财务管理」，继续承载实际回款和发票。
- 原「业务看板」菜单和 `/business-journey-board` 页面入口下线；看板能力迁入 `/business-journeys`。
- 数据看板只保留销售看板；无销售看板权限时按现有逻辑隐藏该分组。

### 3.1 菜单权限

业务旅程是日常业务入口，不能继续由 `sales_dashboard:view:*` 决定是否显示。

旅程可见性应对齐现有客户 / 商机可见性：

- `opportunity:view:all` 或 `customer:view:all`：可看团队内全部可见旅程。
- `opportunity:view:own`：可看主商机由自己负责的旅程。
- `customer:view:own`：可看自己负责客户下的旅程，包括无主商机旅程。
- 客户成员具备 `VIEW / FOLLOW_UP / EDIT`：可看该客户下旅程。
- 无上述任何可见范围：隐藏入口或返回 403，不再要求销售看板权限。

后端列表和看板必须使用同一套可见性谓词，不能出现表格可见而看板不可见。

## 4. 页面与路由

统一页面：

```text
/business-journeys
```

页面标题「业务旅程」。页面容器统一管理：

- 系统 Tab / 自定义视图 Tab
- 搜索
- 筛选
- 排序
- 字段配置
- 视图配置
- 当前显示模式
- 列表或看板读取状态
- 业务旅程 Sheet

不保留两个并列页面，不让用户在导航层选择「业务旅程」和「业务看板」。

## 5. 系统 Tab

系统自带 Tab：

```text
全部旅程
推进中
已完成
已输单
```

语义：

- 全部旅程：除归档外的全部可见旅程。
- 推进中：未完成、未输单，包含销售推进、签约、回款、开票阶段。
- 已完成：旅程状态 / 确定性闭环阶段为已完成。
- 已输单：旅程或主商机已输单。

系统 Tab 只提供稳定业务范围，不为每个看板阶段新增 Tab。看板阶段仍通过列表示。

系统 Tab 本身不保存为后端偏好，也不能被用户覆盖、重命名或删除。

## 6. 页面显示模式

```typescript
type ViewDisplayMode = 'table' | 'board'
```

默认：`table`。

### 6.1 表格视图

使用现有 `DataTable` 和列表页模式。推荐列：

| 字段 | 说明 |
|---|---|
| 旅程名称 | 详情入口 / 行点击 |
| 客户 | 客户名称 |
| 当前阶段 | `current_board_stage_label` |
| 主商机 | 主商机名称，无则 `-` |
| 产品 | 主商机产品 |
| 金额 | 主商机金额 |
| 采购类型 | 新购 / 续购 / 增购 |
| 负责人 | 主商机负责人，回退客户负责人 |
| 最近动态 | `last_event_at` |
| 开始时间 | `started_at` |

表格支持服务端分页、搜索、筛选、排序、字段配置和自定义视图。

### 6.2 看板视图

迁入现有业务旅程看板，阶段和样式继续遵循 `kanban-page.md`：

```text
初期交流
持续推进
即将签约
签约中
回款中
开票中
已完成
已输单
```

现有看板 Card、Badge、Skeleton、阶段配色、刷新态、错误态和横向滚动样式继续复用，不重新设计。

排序作用于各列内的卡片顺序。字段配置在看板模式不影响展示，但配置仍保存在视图中，切回表格时恢复。

## 7. 视图配置

业务旅程页面沿用现有列表工具体系，不新增独立 `ViewConfigPopover` 或第二套配置浮层。

现有「视图配置」表面增加一个仅由业务旅程页面传入的选项：

```text
看板视图  [开关]
```

- 关闭：`display_mode = 'table'`
- 开启：`display_mode = 'board'`

实现约束：

- 优先扩展现有 `ListAdvancedTools` / 当前「视图配置」面板的可选页面配置区域或 slot。
- 业务旅程页传入该开关；其他页面不传，因此 UI 和行为完全不变。
- 不另建业务旅程专用配置弹窗，不复制筛选、排序、字段配置 UI。
- 桌面与窄屏均使用现有工具栏 / 「更多设置」布局规则。

## 8. 视图偏好契约

现有 `ViewPreferenceConfig` 增加可选字段：

```typescript
interface ViewPreferenceConfig {
  version: number
  columns: ViewPreferenceColumn[]
  sorts?: Record<string, unknown>[]
  filters?: Record<string, unknown>[]
  density?: string | null
  display_mode?: 'table' | 'board'
}
```

后端：

```python
display_mode: Literal['table', 'board'] | None = None
```

规则：

- 旧配置缺少 `display_mode` 时按 `table` 读取。
- `config_json` 已是 JSON 文本，不增加数据库列。
- 其他页面不主动写该字段，也不显示开关。
- 新页面的稳定 view key：`business-journeys.list`。
- 搜索词继续不保存，与当前视图机制一致。

## 9. 系统 Tab 与自定义视图行为

显示模式进入 `useCustomFilterViews` 的视图快照，与筛选、排序、字段配置同生命周期：

```text
ViewApplySnapshot
  activeTab
  filters
  sorts
  columns
  displayMode   ← 仅调用方传入时参与
```

### 9.1 系统 Tab

- 在系统 Tab 内打开 / 关闭看板，只改变当前页面会话状态，不调用保存 API。
- 系统 Tab 之间切换时，显示模式与当前筛选 / 排序一样继续保留。
- 进入自定义视图前记录系统 Tab 的临时状态。
- 从自定义视图返回系统 Tab 时，恢复进入前的显示模式、筛选、排序和字段配置。
- 刷新或重新进入页面，默认表格；若按现有逻辑自动应用置顶自定义视图，则采用该视图保存的模式。

### 9.2 自定义视图

- 自定义视图保存后，`display_mode` 与筛选、排序、字段配置一并固定。
- 切入自定义视图：应用保存的显示模式后再读取对应数据。
- 在自定义视图内切换表格 / 看板：走现有 `updateActiveCustomViewConfig()`，更新该自定义视图。
- 从自定义视图切回系统 Tab：不污染系统 Tab。
- 重命名、置顶、删除继续使用现有自定义 Tab 逻辑。

### 9.3 从系统 Tab 另存为视图

现有「另存为视图」只在筛选面板中出现，且至少有一个筛选条件才能保存。业务旅程要支持「仅看板模式」保存，因此：

- 「视图配置」中增加「另存为视图」动作，调用现有 `viewPreferenceApi.createCustomView`。
- 即使筛选为空，只要当前模式为看板、存在排序或字段变化，也允许保存。
- 保存内容使用当前实际生效状态：系统 Tab 的隐含业务范围转换成该自定义视图的明确状态过滤条件，系统 Tab 自身不写入 config。
- 保存后生成现有自定义视图 Tab，默认名称仍走当前「未命名视图 → 重命名」流程，不新增命名弹窗。
- 保留 `ListFilterPopover` 中现有另存入口；它和视图配置入口调用同一 composable 方法，不复制创建逻辑。

`useCustomFilterViews` 应新增通用的「保存当前快照为自定义视图」能力；既有 `saveAsCustomView(filters)` 可内部转调，其他页面行为保持不变。

## 10. 表格与看板共用查询语义

表格和看板必须共用一套后端查询服务 / 可见性条件 / 字段定义：

```text
团队与用户可见范围
  → 系统 Tab 范围
  → 搜索
  → filters
  → sorts
  → 表格分页 或 看板阶段分组
```

不能继续让表格读取客户旅程接口、看板读取销售看板权限下的另一套结果。

建议：

- 新增团队级业务旅程列表查询 API，提供分页表格数据。
- 现有 `/v1/business-journey-board/` 可保留为看板投影 API，但内部改用同一 `BusinessJourneyQueryService`。
- 新增 `DEAL_JOURNEYS_LIST_QUERY_CATALOG`，成为表格列 / 筛选 / 排序字段的服务端能力源。
- 看板读取同一组过滤条件；仅将结果按 `current_board_stage` 分组。
- 表格 total 和看板卡片总数在相同 scope + filters 下必须一致（看板 limit 截断时明确返回 truncated）。

首期共用字段至少包括：旅程名称、客户、阶段、负责人、金额、采购类型、产品、最近动态、商机创建时间、预计成交日期。

## 11. 点击行为与业务旅程 Sheet

表格行和看板卡片统一：

```text
点击旅程
  → DealJourneyDetailSheet
  → DealJourneyDetailContent
```

要求：

- 看板响应必须返回旅程 `public_id` 和客户 `public_id`，不能再用内部 `journey_id: int` 导航。
- `DealJourneyDetailContent` 仍是唯一详情内容组件。
- 新建的 `DealJourneyDetailSheet` 只负责 Sheet 壳、打开 / 关闭、焦点恢复和 `customerPublicId + journeyPublicId` 参数。
- 客户详情内部对象栈继续复用同一个 `DealJourneyDetailContent`。
- Sheet 中客户名称可作为上下文和客户详情入口，但不要求用户先打开客户 Sheet。
- 合同、回款计划、回款、发票、License 仍由旅程详情内既有面板和接口操作。

旧设计中「DealJourneyDetailContent 只挂 CustomerDetailSheet」被本设计覆盖。

## 12. 现有看板迁移

### 12.1 页面和路由

- `BusinessJourneyBoard.vue` 的看板主体迁为业务旅程页的 board view；样式和组件不重做。
- `/business-journey-board` 前端路由和菜单清理，不保留双入口。
- `/business-journeys` 同时承载表格和看板。

允许为了复用而把现有看板主体做纯代码拆分，但禁止在拆分时重新设计 Card、列头、工具栏或错误态。

### 12.2 用户已保存视图

现有看板使用 view key：

```text
business-journey-board.board
```

通过 Alembic 数据迁移：

1. 将该 key 的默认偏好和自定义视图改为 `business-journeys.list`。
2. `config_json` 补 `display_mode: 'board'`。
3. 保留 `name`、`scope`、`user_id`、`preference_key`、`sort_order`、筛选和排序。
4. 不创建重复视图；迁移可重跑。
5. downgrade 恢复旧 key，并移除本迁移添加的 `display_mode`。

旧看板自定义视图迁移后仍显示在业务旅程页的自定义 Tab 中，并自动进入看板模式。

## 13. 组件与样式复用红线

页面必须复用：

- `DataTable`
- `DataTableSearch`
- `ListFilterPopover`
- `ListSortPopover`
- `ColumnConfigPopover`
- `ListAdvancedTools` / 现有「视图配置」表面
- `ListViewStateSummary`
- `TableToolbarButton`
- `Card` / `CardContent`
- `Badge`
- `Skeleton`
- shadcn-vue `Sheet`
- `DealJourneyDetailContent`
- 现有业务看板阶段样式和颜色映射

禁止：

- 新建第二套筛选、排序、字段配置、视图保存组件。
- 新建业务旅程专用按钮、开关、Popover 基础组件替代设计系统。
- 复制 `DealJourneyDetailContent`。
- 从 V1 / Element Plus 恢复旧组件或主题变量。
- 为新页面引入独立阴影、圆角、颜色、间距体系。
- 不经设计系统文档支持自创响应式行为。

新增文件只允许是业务组合边界，例如统一页面、既有看板主体的无视觉改造拆分、独立 Sheet 壳；不得把业务页面包装成新的通用设计系统组件。

## 14. 导航大类的业务边界

| 分组 | 用户任务 | 页面 |
|---|---|---|
| 销售工作 | 找客户、跟进客户、查看完整推进过程 | Agent、线索、客户、客户追踪、业务旅程 |
| 交易管理 | 精确查找和维护某类交易单据 | 商机、合同、回款计划 |
| 财务管理 | 处理真实资金和开票执行 | 回款管理、发票管理 |
| 数据看板 | 查看经营统计 | 销售看板 |

商机「已赢单」语义保持为「商机选择结果已确认，可以进入签约」。业务旅程中的对应阶段显示「即将签约」，只有完整闭环后显示「已完成」。

## 15. 测试与验收

### 后端

- 表格与看板在相同权限、系统 Tab 和 filters 下返回相同旅程集合。
- 普通销售凭 `opportunity:view:own` / `customer:view:own` 可访问自己的旅程，不依赖销售看板权限。
- 客户成员只能看到有权限客户下的旅程。
- 表格分页 total 正确；看板按同一查询结果分组。
- 看板卡片返回旅程 `public_id`，不以内部 int 作为导航 ID。
- `ViewPreferenceConfig.display_mode` 接受 `table / board / null`，非法值 422。
- 旧 view key 数据迁移后保留自定义视图并带 `display_mode=board`。

### 前端

- 左侧分组和顺序与第 3 节一致；业务看板旧入口不存在。
- 业务旅程默认表格；视图配置打开看板后显示现有看板。
- 系统 Tab 切换不调用视图保存 API，当前会话保持显示模式。
- 自定义视图保存并恢复 `display_mode`。
- 只选看板、无筛选时也能另存为视图。
- 保存「推进中 + 看板」后，自定义视图恢复推进中范围和看板模式。
- 从看板自定义视图返回系统 Tab，恢复系统 Tab 进入前模式。
- 旧看板自定义视图迁移后自动打开看板。
- 表格行和看板卡片打开同一个 `DealJourneyDetailSheet`。
- Sheet 使用 `DealJourneyDetailContent`，不经过客户 Sheet。
- 表格字段配置在看板模式不展示，但切回表格后仍恢复。
- 其他 DataTable 页面不出现看板开关，现有自定义视图行为不变。

### 手工

- 业务旅程表格 → 点击旅程 → 旅程 Sheet → 合同 / 回款操作。
- 业务旅程看板 → 点击同一旅程 → 相同 Sheet。
- 系统 Tab 临时切到看板 → 进入自定义表格视图 → 返回系统 Tab，恢复看板。
- 置顶一个看板自定义视图 → 重新进入页面后自动应用。
- 商机已赢单但未创建合同的旅程位于「即将签约」，不显示「已完成」。

## 16. 风险

1. **两种视图查询不一致**：必须先抽共享查询服务，再接表格；不能在前端对当前页分组。
2. **权限回退**：旧看板依赖销售看板权限；迁移后必须改成客户 / 商机可见性，否则普通销售会丢入口。
3. **视图保存不完整**：显示模式必须进入 snapshot、创建、更新、失败回滚和内置 Tab 恢复全链路。
4. **只看板模式无法保存**：不能继续依赖筛选面板的非空筛选门禁，视图配置需提供统一另存动作。
5. **旧自定义视图丢失**：必须迁移 view key 和 JSON，不能只改前端常量。
6. **看板详情身份仍是内部 ID**：迁移点击前必须返回 `public_id`。
7. **页面重复组件**：看板迁移只能抽现有主体，不允许复制一份或重做视觉。
8. **系统 Tab 与自定义视图混淆**：系统 Tab 只提供业务范围；保存时把实际范围固化为自定义 filter，不保存系统 Tab 身份。
9. **旧路由书签**：本期按 clean cutover 移除旧页面入口；若部署要求兼容，需要单独批准路由跳转，不默认保留。

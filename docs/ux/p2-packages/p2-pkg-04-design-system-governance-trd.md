# P2-PKG-04 设计系统迁移治理与共享状态组件收敛 TRD

- **文档状态**：TRD 草案，可进入技术评审
- **版本**：v0.1
- **日期**：2026-09-04
- **对应 PRD**：P2-PKG-04 设计系统迁移治理与共享状态组件收敛 PRD
- **改造包**：P2-04
- **技术范围**：CRM-Client 设计系统、共享组件、页面级样式和本地治理检查
- **明确排除**：Agent / AI 自动化链路；业务接口、数据模型、审批业务规则

## 1. 技术结论

本改造包不是从零建设设计系统，也不是一次性把所有页面重新换肤。仓库已经具备 shadcn-vue 基础组件、`base.css` 运行时 Token、`variables-v2.scss` 业务兼容层，以及 `DataTable`、`DetailSheetContent`、`StatusBadge`、`ErrorState`、`LoadingSkeleton`、`TableRowActions` 等共享实现。因此，直接全量替换会制造较大的回归面，也会重复改造已经落地的能力。

真实问题是“目标体系已存在，但使用入口和状态组合仍未完全收敛”：一部分业务样式仍直接依赖 Sass 兼容 Token；列表页状态已经集中在 `DataTable`，详情面板、设置页和局部卡片仍各自组合加载、空、错误反馈；业务状态已有通用徽章和审批专用徽章，但局部页面还存在直接使用 `Badge` 或自定义状态 class 的分叉；原生色值同时包含应迁移的 UI 色值和图表、看板色板等合理例外，当前没有统一的例外登记机制。

本 TRD 采用“先盘点和加门禁，再收敛共享组合，最后迁移首批高频文件”的渐进方案。迁移只改变样式入口、组件组合方式和治理方式，不改变客户、商机、合同、发票、回款、审批等业务流程，不改变 `DataTable` 固定高度、内部滚动、操作列和移动端卡片滚动模型。

## 2. 系统审计范围与方法

本次分析以 2026-09-04 工作区源码为基线，检查 `CRM-Client/src`、`CRM-Docs/design-system`、`package.json`、Tailwind 配置、ESLint 和 Stylelint 配置，并对核心列表页、详情 Sheet、状态反馈组件进行源码级映射。审计关注的是实际调用链，而不是仅根据设计系统文档中的“目标状态”推断已实现程度。

审计结果的几个基线事实如下：

| 审计项 | 当前事实 | 技术含义 |
| --- | --- | --- |
| shadcn 运行时 Token | `src/styles/base.css` 定义亮暗主题 CSS variables，`main.ts` 全局引入 | 运行时入口已经存在，不应另建第三套主题入口 |
| 业务兼容 Token | `global.scss` 将 shadcn variables 映射为 `--wolf-*`，大量组件通过 `variables-v2.scss` 使用 `$wolf-*-v2` | 兼容层仍是存量主入口，不能本期直接删除 |
| Element Plus | `package.json` 未发现 Element Plus 依赖，源码未发现真实 `el-*` 组件调用 | PRD 中“迁移治理”不能简单等同于继续做 Element Plus 替换 |
| 列表表格 | `DataTable` 被客户、客户追踪、线索、商机、合同、发票、回款计划、回款记录、审批中心等高频列表复用 | DataTable 是本期最重要的共享回归边界 |
| 列表布局 | 上述页面已传入 `height-strategy="fill"` 与 `scroll-mode="contained"`；移动端卡片由 DataTable 特殊处理 | 不能通过样式清理破坏固定高度和滚动责任 |
| 空/错误/加载 | `DataTable` 已统一读取态；同时存在 `ErrorState`、`LoadingSkeleton`、原生 `Skeleton`、直接组合 `Empty` | 需要统一“推荐组合”，而不是强行只保留一个组件 |
| 状态徽章 | `StatusBadge` 覆盖销售实体状态和枚举字段，`ApprovalStatusBadge` 保留审批图标语义，局部还有直接 `Badge` | 需要收敛契约，不宜把审批状态粗暴并入通用实体状态 |
| 设计系统门禁 | 存在 `.stylelintrc.design-system.js`，但默认 `npm run lint:style` 未显式引用该配置；ESLint 也主要校验 TypeScript/Vue 规则 | “有规则文件”不等于“提交时一定执行”，需要明确接入方式和例外机制 |

## 3. PRD 到现状的逐项映射

| PRD 需求 | 系统现状 | 是否已有实现 | TRD 处理 |
| --- | --- | --- | --- |
| 建立迁移清单 | 设计系统有迁移说明，但缺少以文件、符号、目标入口、风险为粒度的可执行台账 | 部分实现 | 增加机器可读清单及人工维护字段，不重复创建组件 |
| 新增代码门禁 | 已有 Stylelint 设计系统规则，存在 raw color 和旧变量检查意图，但未形成完整例外流程 | 部分实现 | 补充脚本入口、例外登记、CI/本地命令和误报处理 |
| 共享组件优先 | `DataTable`、详情 Sheet、状态徽章、反馈组件已存在，但调用层仍有多套组合 | 部分实现 | 先冻结共享 API，再迁移首批页面和局部状态组合 |
| 状态组合收敛 | 列表态由 `DataTable` 统一，详情/设置/卡片中仍有定制 loading/empty/error 文案和结构 | 未完全实现 | 提供状态配方和共享容器，保留页面业务文案差异 |
| 迁移回归 | base.css 已有 focus、暗色、reduced motion、移动触控基础规则，多个组件有独立 Sass 样式 | 部分实现 | 建立主题、无障碍、滚动、移动端和回归快照矩阵 |
| 首批审计文件 | `AppLayout.vue`、`SalesDashboard.vue`、`MetricCard.vue`、`TopBarTabs.vue`、`PaymentPlanDetailContent.vue` 均存在独立样式或 raw color/兼容 Token 使用 | 已确认存在 | 作为首批迁移对象，但先按实际风险拆批，不一次性改完所有页面 |

## 4. 当前设计系统资产盘点

### 4.1 令牌与样式入口

`base.css` 是当前唯一运行时主题入口，定义 `--background`、`--foreground`、`--primary`、`--muted`、`--destructive`、`--border`、`--ring` 及亮暗主题变量。Tailwind 配置也消费这些 CSS variables，并提供 `bg-background`、`text-muted-foreground`、`bg-wolf-*` 等语义类。

`global.scss` 负责将 shadcn variables 映射为历史 `--wolf-*` CSS 变量，`variables-v2.scss` 则提供大量 Sass Token，包括颜色、间距、圆角、阴影、断点、字体、触控尺寸和 Sheet/DataTable 尺寸。源码审计显示约 105 个源文件存在 `variables-v2.scss` 引用或使用，说明它目前不是可以立即删除的“废弃文件”，而是实际兼容层。技术方案应把它治理为过渡入口，而不是在本期强制清空。

### 4.2 已经收敛的共享组件

`DataTable.vue` 已承载字段注册、筛选排序、视图状态、空态、加载态、错误态、分页、列固定、移动端卡片和桌面行操作；其公开 API 同时保留 `loading`、`height` 等兼容参数，并新增 `viewState`、`heightStrategy`、`scrollMode` 等迁移参数，表明它本身处于兼容演进阶段。

`DetailSheetContent.vue` 已提供统一的右侧详情 Sheet 宽度、移动端全屏、动态视口高度和 flex 布局。客户、审批、客户追踪及多类详情页已经使用或接近使用该承载层，后续只应补齐局部页面，不应重新设计 Sheet 交互。

`StatusBadge.vue` 已将线索、客户、商机、合同、发票、回款计划、回款记录及若干枚举字段映射到统一状态语义；`ApprovalStatusBadge.vue` 额外提供审批状态图标、文案和可访问性表达。二者职责不同：审批状态不能因为“统一”而丢失严肃场景需要的图标和状态确认语义。

`ErrorState.vue` 使用统一 Empty 基础组件表达错误；`LoadingSkeleton.vue` 提供列表、卡片、表格骨架；`ui/skeleton`、`ui/empty`、`ui/alert` 等基础组件也已存在。下一阶段的重点是统一组合方式和边界，而非简单删除其中任意一个。

### 4.3 当前仍存在的分叉

**样式入口分叉。** 业务文件大量直接 `@use '@/styles/variables-v2.scss'`，虽然这些 Token 已经是 V2 命名，但它们绕开了“新增代码优先使用 shadcn 语义类和 CSS variables”的目标约定。需要区分“颜色/主题入口”与“尺寸、断点、动效等 Sass 编译期 Token”，不能把所有 Sass 使用一概判定为错误。

**反馈状态分叉。** `DataTable` 对列表读取态已有完整处理，但 `LeadDetailSheet`、`InvoiceDetailSheet`、`CustomerDetailSheet`、设置页和多个面板仍自行编排 `loading`、`Empty`、`ErrorState` 或文本提示。相同的失败场景可能出现不同的标题、图标、重试按钮位置和 aria 行为。

**状态表达分叉。** 通用实体状态使用 `StatusBadge`，审批使用 `ApprovalStatusBadge`，超时、许可证、业务看板列色等局部语义仍有自定义 class 或直接 `Badge`。其中图表序列、看板列色和数据可视化颜色不应强行套用状态徽章，但应登记为有意例外，避免“所有 raw color 都禁止”造成误报。

**页面级重复样式。** Customers、CustomerTracking、Leads、Opportunities、Contracts、Invoices、PaymentPlans、PaymentRecords 等页面均有较大块的局部 Sass，并重复处理列表页边距、状态文字、移动卡片、详情入口和操作区域。重复本身不代表需要马上抽象；只有被三个以上页面验证为相同语义和行为的样式，才进入共享组件或 recipe。

**门禁与文档脱节。** 设计系统文档已声明禁止新增 Element Plus、raw color 和旧 Token，但现有配置不能完整区分业务颜色、图表颜色、阴影 rgba 和迁移中的存量文件。若直接将规则升级为全量 error，会阻塞正常开发并诱发绕过规则；应先建立基线和例外机制，再对新增 diff 执行严格检查。

## 5. 问题地图与优先级

| 编号 | 问题 | 影响 | 优先级 | 处理边界 |
| --- | --- | --- | --- | --- |
| DS-01 | 新增样式缺少统一的 Token/例外判定入口 | 设计系统会继续产生分叉，审查依赖人工记忆 | P1 | 先做门禁与例外台账，不做全量换色 |
| DS-02 | 兼容 Token 使用面广，移除条件未被代码验证 | 贸然删除会造成编译失败和主题回归 | P1 | 建立引用统计和逐步迁移规则 |
| DS-03 | 列表与详情的 loading/empty/error 组合不一致 | 用户在跨页面处理任务时需要重新理解反馈 | P1 | 统一配方和可访问性，不强制统一文案 |
| DS-04 | 通用状态、审批状态、局部 Badge 的职责边界不够清晰 | 状态颜色、图标和文案容易继续分叉 | P1 | 稳定两个核心契约，清理重复映射 |
| DS-05 | 首批高频共享文件含 raw color/局部视觉实现 | 设计系统规范与源码不一致 | P2 | 只迁移能映射到语义 Token 的部分 |
| DS-06 | 页面迁移状态文档是人工维护，缺少可复核证据 | 评审无法判断“已实现”还是“目标状态” | P2 | 增加验证日期、命令、文件证据 |
| DS-07 | DataTable API 同时存在新旧参数 | 继续新增调用时容易复制兼容写法 | P2 | 新代码只允许推荐 API，存量按页面迁移 |

本改造包不识别新的 P0。上述问题主要是跨页面一致性、维护成本和回归风险问题，适合按改造批次推进，不应以一次性大重构方式处理。

## 6. 目标技术架构

### 6.1 设计系统分层

目标依赖方向如下：

```text
base.css shadcn CSS variables
        ↓
global.scss --wolf-* 兼容变量（过渡层）
        ↓
ui primitives（Button / Empty / Skeleton / Dialog / Sheet / Badge / Table）
        ↓
CRMWolf shared components（DataTable / DetailSheetContent / StatusBadge / ErrorState）
        ↓
页面与业务组件
```

页面不得反向定义新的全局 Token，不得直接把页面业务状态映射成色值。业务组件可以拥有局部布局样式，但颜色、焦点、禁用、状态和通用反馈优先从基础层或共享组件取得。

### 6.2 Token 迁移策略

1. **运行时颜色只认 `base.css`。** 新增颜色优先使用 Tailwind shadcn 语义类或 `hsl(var(--...))`；不得新增新的主色、成功色、警告色和危险色入口。
2. **`--wolf-*` 和 `$wolf-*-v2` 作为兼容层保留。** 本期不删除；对存量文件继续允许使用，但新改动不得扩展兼容层中的颜色别名。
3. **尺寸类 Sass Token暂不强制清除。** 断点、safe area、DataTable 固定高度、触控尺寸等编译期值仍有实际用途；迁移目标是建立清晰的使用边界，而非为了形式全部改成 Tailwind。
4. **例外必须可解释。** 图表序列色、业务看板列色、阴影透明度、渐变透明度等可以保留，但应在例外登记中记录文件、属性、理由、替代条件和复核日期。

### 6.3 共享反馈状态配方

建立一个轻量的“状态配方”层，不新增复杂状态管理。推荐组合如下：

| 场景 | 推荐容器 | 必须包含 | 允许页面定制 |
| --- | --- | --- | --- |
| 首次加载 | `LoadingSkeleton` 或 `Skeleton` | `aria-busy`/`role=status`、稳定布局占位 | 行数、字段数量、文案 |
| 有数据刷新 | 保留原数据 + DataTable 刷新指示 | 不清空用户当前视图，避免闪烁 | 刷新文案、局部 loading indicator |
| 无筛选结果 | `Empty` | 明确“当前筛选无结果”、清除筛选动作 | 业务文案、操作按钮 |
| 无业务数据 | `Empty` | 说明下一步可做什么 | 新建按钮、帮助文案 |
| 首次读取失败 | `ErrorState` | 错误原因、重试入口、alert 语义 | 标题、描述、重试回调 |
| 局部面板失败 | `ErrorState` 或等价共享组合 | 不影响其他详情面板、局部重试 | 面板标题和恢复动作 |
| 写操作结果 | `toast`/页面反馈 | 成功、失败、部分成功必须可区分 | 业务结果文案 |

该配方只统一信息架构、可访问性和恢复动作，不要求所有页面使用相同标题，也不把详情页强行改造成 DataTable。

### 6.4 状态徽章契约

保留两个核心组件并明确边界：

- `StatusBadge`：客户、线索、商机、合同、发票、回款等业务实体状态，以及已登记的稳定枚举展示；输入为语义状态，不接受页面直接传色值。
- `ApprovalStatusBadge`：审批生命周期状态；保留图标 + 文案 + 颜色组合，服务审批中心和审批详情。审批中心继续保持单条严肃操作，不引入批量审批。

局部 `Badge` 只有在“非状态标签”或“特殊业务指标”时使用，例如审批超时提示、计数标签、静态分类标签。若它表达的是生命周期状态，应迁移到上述契约之一。

### 6.5 DataTable 兼容边界

`DataTable` 是当前高频列表的稳定深模块，不能在本期借治理之名重写。新页面统一使用：

- `fields` 作为列、筛选、排序、列配置的单一字段注册表；
- `viewState` / `loadError` 表达读取状态；
- `heightStrategy="fill"` + `scrollMode="contained"` 表达桌面列表固定高度与内部滚动；
- `getRowActions` 提供桌面、右键和移动端动作来源；
- `mobile-mode="card"` 或页面移动卡片插槽承载窄屏场景。

`height`、布尔 `loading` 等兼容属性在存量页面保留，待调用方迁移后再评估删除。任何样式清理必须通过“超过 20 条数据、分页、横向滚动、固定列、操作列、移动卡片、空态和刷新失败”回归，不得改变页面滚动责任。

## 7. 实施拆分与依赖关系

### 7.1 P2-04-01：建立审计基线与迁移台账

**目标。** 把“旧 Token/raw color/共享组件/状态组合”从口头判断变成可追踪记录。

**实现内容。** 新增 `CRM-Docs/design-system/migration/p2-pkg-04-inventory.md` 或等价机器可读清单，字段至少包括：文件、符号或代码位置、问题类别、目标入口、是否例外、负责人、迁移批次、风险、验证命令、状态、最后验证日期。首批覆盖 PRD 指定五个文件及 DataTable、StatusBadge、ErrorState、LoadingSkeleton、ApprovalStatusBadge。

**独立验收。** 任意一条清单记录都能定位到源码；已实现能力与待迁移缺口不再混在一起；不修改业务运行时行为。

### 7.2 P2-04-02：门禁接入与例外登记

**目标。** 让新增代码不再扩大设计系统债务，同时不因存量问题阻塞开发。

**实现内容。** 在现有 Stylelint 规则基础上增加明确命令入口，区分“全量基线检查”和“新增 diff 检查”。检查范围至少包含：新增 raw hex/rgb/rgba UI 色值、新增旧 Token、新增 Element Plus 组件、未登记的状态颜色。允许例外配置文件必须有 reason、owner、expires/review date，图表和看板色板优先使用属性或路径级例外，不允许无理由关闭整条规则。

**独立验收。** 新增一个违规样式可以被本地命令稳定识别；已有基线问题不会被误报成新增问题；合理的图表例外可以通过并出现在报告中。

### 7.3 P2-04-03：共享反馈状态配方

**目标。** 收敛列表、详情和设置页面的状态信息架构。

**实现内容。** 优先复用现有 `DataTable`、`ErrorState`、`LoadingSkeleton`、`ui/Empty`、`ui/Skeleton`，必要时新增轻量组合组件或 composable，而不是新增一套视觉组件。先迁移一个列表页面和一个详情页面作为样板，再推广到 `LeadDetailSheet`、`InvoiceDetailSheet`、`CustomerDetailSheet`、系统设置和局部面板。

**独立验收。** 样板页面在首次加载、刷新、有数据刷新失败、无数据、无筛选结果、局部错误和重试后均有稳定反馈；不改变 API 和业务动作；焦点与 `role`/`aria-live` 行为通过测试。

### 7.4 P2-04-04：状态徽章契约收敛

**目标。** 让生命周期状态只从稳定映射产生，保留审批专用表达。

**实现内容。** 为 `StatusBadge` 和 `ApprovalStatusBadge` 补充输入、未知状态、尺寸、可访问性和主题回归测试；审计直接 `Badge` 和页面级状态 class，按“生命周期状态 / 指标标签 / 可视化色板”分类。只迁移第一类，不改业务状态枚举。

**独立验收。** 客户、商机、合同、发票、回款和审批状态在亮色/暗色主题下均有文案、颜色和必要图标；未知状态不会渲染为空；审批状态不丢失图标和严肃语义。

### 7.5 P2-04-05：首批共享组件与高频页面迁移

**目标。** 消除首批文件中可直接映射的局部 Token 和重复实现。

**迁移顺序。**

1. `MetricCard.vue`：优先处理卡片边框、背景、阴影和状态 tone，保留指标视觉层级。
2. `TopBarTabs.vue`：处理导航激活、hover、focus 和暗色主题入口，保持现有 tab 路由行为。
3. `AppLayout.vue`：只收敛壳层颜色、分隔线、focus 和响应式 Token，不动路由、侧栏和审批入口。
4. `PaymentPlanDetailContent.vue`：只收敛面板状态、回款计划状态显示和可复用反馈组合，不改变回款登记流程。
5. `SalesDashboard.vue`：把可迁移的页面 UI 色值改成语义 Token；图表序列色和 tooltip 内联色按例外规则处理，不改变图表数据和交互。

**独立验收。** 每个文件可单独发布和回滚；页面视觉变化仅限 Token 等价替换和状态组合一致化；通过该页面的主题、无障碍、移动端和业务动作回归。

### 7.6 P2-04-06：实现状态文档与治理闭环

**目标。** 使设计系统文档反映源码实际状态，而不是只记录目标状态。

**实现内容。** 更新 `implementation-status.md`，记录每个组件或页面的“已验证入口、未迁移入口、验证命令、验证日期”；将清单、规则和实现状态从设计系统根入口可追踪访问；运行现有设计系统文档检查。

**独立验收。** 新成员可以从设计系统根入口找到规则、迁移表和实现证据；文档检查通过；实现状态与源码审计结果一致。

## 8. 文件级技术变更建议

| 文件/目录 | 变更 | 不变内容 |
| --- | --- | --- |
| `CRM-Client/src/styles/base.css` | 仅补充缺失的语义变量或主题回归所需变量 | 不改变现有主色、暗色主题和全局 focus 约定 |
| `CRM-Client/src/styles/global.scss` | 明确兼容变量注释和迁移边界 | 不删除 `--wolf-*` 存量入口 |
| `CRM-Client/src/styles/variables-v2.scss` | 增加 deprecated/compat 注释或拆分迁移清单，不在本期大规模改名 | 不删除尺寸、safe area、断点等仍被使用的 Token |
| `.stylelintrc.design-system.js` / `scripts` | 增加新增 diff 检查、例外文件校验和输出格式 | 不以全量 error 的方式一次性阻塞所有存量问题 |
| `components/crmwolf/DataTable.vue` | 稳定推荐 API 的注释和测试，必要时补充状态配方接入 | 不改变固定高度、内部滚动、分页、操作列、移动模式 |
| `components/StatusBadge.vue` | 补齐契约测试、未知状态兜底和主题验证 | 不修改业务状态枚举和文案含义 |
| `components/ApprovalStatusBadge.vue` | 补齐审批专用状态测试和边界说明 | 不引入批量审批，不改变审批业务流程 |
| `components/ErrorState.vue`、`LoadingSkeleton.vue`、`ui/empty`、`ui/skeleton` | 统一使用边界与可访问性约定 | 不要求所有页面使用同一份文案 |
| PRD 首批五个文件 | 按清单逐项迁移颜色、状态和重复组合 | 不重写页面结构，不修改接口和路由 |

## 9. 测试与验证方案

### 9.1 静态检查

- `npm run type-check`
- `npm run lint`
- `npm run lint:style`
- 设计系统文档检查：`node CRM-Docs/scripts/check-design-system-docs.js`
- 新增 diff 设计系统门禁：检查 raw color、旧 Token、未登记例外和新增旧组件入口

### 9.2 共享组件单元测试

- `StatusBadge`：各业务类型、未知状态、small/default、亮暗主题 class、`role=status` 和 aria-label。
- `ApprovalStatusBadge`：PENDING/APPROVED/REJECTED/CANCELLED 等状态的图标、文案和颜色；不出现批量操作入口。
- `ErrorState` 与反馈配方：重试回调、错误语义、无描述场景。
- `DataTable`：首次加载、保留旧数据刷新、空态、错误态、筛选无结果、分页、固定高度、内部滚动、操作列宽度、右键入口和移动端卡片。

### 9.3 页面回归矩阵

| 维度 | 必测页面/组件 | 通过条件 |
| --- | --- | --- |
| 亮色/暗色 | AppLayout、TopBarTabs、MetricCard、DataTable、StatusBadge | 文字、边框、状态色和 focus 可读，不出现白底白字或低对比 |
| 键盘/焦点 | 列表筛选、表格行操作、详情 Sheet、审批详情 | Tab 顺序稳定，Esc/Enter 行为不变，焦点不丢失 |
| 移动端 | Customers、CustomerTracking、ApprovalCenter、PaymentPlans | 44px 触控目标，卡片不产生额外页面横向滚动 |
| 表格滚动 | Customers、Contracts、Invoices、PaymentRecords | 超过 20 条时页面不随表格内容增长，表格内部滚动和分页正常 |
| 状态组合 | LeadDetailSheet、InvoiceDetailSheet、CustomerDetailSheet、设置页 | 首次加载、空、错误、重试语义一致，局部失败不遮蔽其他内容 |
| 业务流程 | 回款登记、发票申请、合同审批、审批单单条处理 | API 请求、状态变更、成功/失败反馈与迁移前一致 |
| 动效偏好 | 所有首批页面 | `prefers-reduced-motion: reduce` 下不出现持续动画或滚动异常 |

## 10. 发布、兼容与回滚

采用按批次发布，不采用一次性全站迁移。每个批次只包含同一类风险：规则与台账、共享状态组合、状态徽章、首批页面。共享组件先增加测试和兼容能力，再迁移调用方；调用方完成后再评估收紧 API。

兼容策略如下：

- 保留 `DataTable` 的 `loading`、`height` 等存量参数，新增代码使用推荐 API；
- 保留 `--wolf-*` / `$wolf-*-v2`，仅停止新增兼容别名；
- 共享状态组件通过现有 props 和 slot 扩展，不直接改变调用方的业务回调；
- 例外登记以文件路径和属性为粒度，避免通过全局关闭规则回滚。

回滚以批次为单位：如果主题、焦点、DataTable 滚动或业务反馈出现回归，先回滚首批页面调用方；共享组件保持向后兼容。如果共享组件本身导致回归，回滚其新增样式/配方分支，保留不影响存量调用的测试和台账。不得通过删除 `base.css`、`global.scss` 或 `variables-v2.scss` 解决回归。

## 11. 验收标准

1. 迁移清单覆盖 PRD 指定首批文件和共享状态组件，每一项均有目标入口、风险和验证证据。
2. 新增 diff 检查能够识别主要 raw color、旧 Token 和旧组件入口，同时支持有理由、有责任人、有复核日期的例外。
3. `DataTable`、`DetailSheetContent`、`StatusBadge`、`ApprovalStatusBadge`、`ErrorState`、`LoadingSkeleton` 的职责和推荐用法在源码、测试和设计系统文档中一致。
4. 至少一个列表页和一个详情页完成共享反馈状态配方样板迁移；首次加载、有数据刷新失败、无数据、筛选无结果、局部失败和重试均可验收。
5. 首批 `AppLayout`、`SalesDashboard`、`MetricCard`、`TopBarTabs`、`PaymentPlanDetailContent` 完成可迁移样式项处理；图表和看板色板例外均有登记。
6. 亮色/暗色、键盘焦点、禁用态、移动端触控、reduced motion 和状态色对比度通过回归。
7. 客户、客户追踪、合同、发票、回款计划、回款记录和审批中心的 DataTable 固定高度、内部滚动、分页、操作列和移动端模式无回归。
8. 审批中心保持单条严肃审批操作，不新增或恢复批量审批。
9. `type-check`、`lint`、样式检查、单元测试和设计系统文档检查通过，或对已知存量问题有明确基线说明。
10. 本期不要求删除全部兼容 Token、不要求移除 Element Plus 之外的无关依赖、不要求全量视觉换肤。

## 12. 不做事项

- 不改客户、线索、商机、合同、发票、回款、审批的业务状态机和接口契约；
- 不改 DataTable 页面高度、内部滚动责任、固定列、操作列或移动端卡片模型；
- 不把所有 `Badge` 强制替换成一个“大一统”状态组件；
- 不删除审批中心批量操作相关内容以外的业务流程，也不新增批量审批；
- 不修改 Agent / AI 自动化页面和交互链路；
- 不进行品牌色、圆角、阴影、字体和全站布局的一次性视觉重构；
- 不为了满足门禁而删除合理的图表、看板色板和阴影透明度例外；
- 不以全量重命名 Sass Token 作为本期完成条件。

## 13. 待技术评审确认

- 新增 diff 门禁落在现有 Stylelint 命令、独立 Node 脚本，还是 CI workflow；
- 例外登记使用 JSON/YAML 还是 Markdown 表格，并由谁定期复核；
- 首批页面中 `SalesDashboard` 图表序列色是否采用 CSS variables，还是长期保留数据可视化例外；
- 是否在本改造包内新增统一的 `DataViewStatePanel` 组合组件，还是先以现有 `ErrorState`、`LoadingSkeleton` 和 `Empty` 的配方文档推进；
- 兼容 Token 的删除条件是否以“零运行时引用 + 一次完整主题回归”为准；
- 首批迁移验收是否纳入截图快照，或以组件测试和人工主题矩阵为主。

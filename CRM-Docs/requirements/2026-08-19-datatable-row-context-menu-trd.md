# 列表行操作改为右键菜单 TRD

把桌面 DataTable 的行操作从右侧「操作」列收成行右键菜单。本文承接 [列表行操作改为右键菜单 PRD v1.1](https://apifox666.feishu.cn/wiki/ThaEwhhKPikJaqkecwIcLnZTnEb)，只写实现接法，不重写产品规则。

飞书 PRD：[列表行操作改为右键菜单](https://apifox666.feishu.cn/wiki/ThaEwhhKPikJaqkecwIcLnZTnEb)

飞书 TRD：[列表行操作改为右键菜单 TRD](https://apifox666.feishu.cn/wiki/WbvzwL5yjiVnn3kX2RCcTgHfned)

| 项 | 内容 |
| --- | --- |
| 文档类型 | 技术需求文档 TRD v1.0 |
| 状态 | 待开发 |
| 日期 | 2026-08-19 |
| 对应 PRD | v1.1，方案已评审 |
| 模块 | 前端 DataTable / 列表页 |
| 读者 | 前端、测试、实施 |
| Alembic | 无。本期纯前端，不改库、不改接口。 |

| 本文写 | 本文不写 |
| --- | --- |
| 组件边界、页面 API、菜单分组算法 | 产品规则正文（见 PRD） |
| 九页改造清单与固定列处理 | 手机长按、行尾「更多」、批量操作 |
| 右键 / 键盘 / 点行互斥细节 | 后端权限码、确认框文案改写 |
| 设计规范同步点与测试矩阵 | 具体补丁代码 |

PRD 已拍板、本文不得推翻的决策：桌面去掉操作列，右键是指针设备唯一入口；原主按钮和「更多」项全部进入同一份 Context Menu；键盘菜单键 / Shift+F10 打开同一份菜单；手机保持 `#mobile-actions`，不做长按；`fixedRightCount` 默认改为 0；九张 DataTable 一次切齐；空动作不弹菜单；链接和输入框的原生菜单优先；关菜单不得误开详情。

## 1. 范围与约束

| 类型 | 说明 |
| --- | --- |
| 范围内 | DataTable 桌面行菜单、去掉操作列、取消右侧自动固定、九个列表页改接入、设计规范与相关单测 |
| 范围内 | 把 ApprovalCenter 当前桌面操作列按钮收成 ActionConfig；公海领取从裸 Button 收成同一套动作合同 |
| 范围外 | 后端、Alembic、权限码、确认对话框文案与流程、批量操作、看板 / 非 DataTable 列表 |
| 范围外 | 桌面行尾 ⋯ / Dropdown Menu；手机长按；给审批中心桌面菜单补「通过 / 驳回」 |
| 约束 | 动作集合、visible / disabled / destructive、确认框必须复用现有 handler，只换露出 |
| 约束 | 不得给 `<tr>` 外包非法 DOM。菜单层必须兼容表格语义 |
| 约束 | 九页同发，不允许出现「有的页还是操作列、有的页已经是右键」 |

## 2. 现状结论

### 2.1 DataTable 把操作当成最后一列

`CRM-Client/src/components/crmwolf/DataTable.vue` 现在默认 `fixedRightCount: 1`。没有显式 `column.fixed` 时，最后 N 列会被钉到右侧。九张表都把 `key: 'actions'` 放在字段目录末尾，所以被钉住的其实是操作列，不是业务字段。

桌面单元格走 `#cell-actions`；窄视口卡片走 `#mobile-actions`。行点击、Enter、Space 在 `rowInteractive` 时发出 `row-click`。九张表都已经是 `row-interactive`，行上有 `tabindex="0"`。表格行目前没有 `contextmenu` 处理。

`processedColumns` 仍会渲染 `key === 'actions'`。`dataColumns` 只是给手机兜底卡片把这一列滤掉。字段配置里 `actions` 被特殊处理为不可配置、不可隐藏。它本来就不是可筛、可排的业务字段，只是被塞进了列目录。

### 2.2 TableRowActions 仍是「按钮 + ⋯」

`TableRowActions.vue` 的合同已经对了：`ActionConfig` + `primaryActions` + `secondaryActions`。桌面渲染却还是高频 ghost Button，低频走 shadcn-vue DropdownMenu 的 ⋯。仓库里已经有完整的 Context Menu（`CRM-Client/src/components/ui/context-menu/`，并从 `crmwolf/index.ts` 导出），但没有任何 DataTable 行在用。

`ActionConfig` 现有字段继续用：`label`、`handler`、`visible`、`disabled`、`icon`、`destructive`、`separator`。`separator` 今天表示「该项上方画一条线」，服务于 ⋯ 菜单；收成右键分组后，分隔线改由分组规则生成，不再依赖行尾按钮。

### 2.3 九页接入并不整齐

九个消费者都在 `listFieldCatalog.test.ts` 的 DataTable 契约里：客户、线索、商机、合同、发票、回款计划、回款记录、客户跟踪、审批中心。它们全都 `row-interactive`，都同时写了 `#cell-actions` 和 `#mobile-actions`，但动作来源不一致。

| 页面 | 现状 |
| --- | --- |
| 合同 | 已有 `getRowActions(row)`，cell / mobile 共用 |
| 商机、客户跟踪 | 有 `getPrimaryActions` / `primaryActions` 一类 helper，cell / mobile 各绑一次 |
| 客户、线索 | 非公海走 TableRowActions，配置在 cell 和 mobile 各写一遍；公海 tab 桌面是裸「领取」Button，不是 TableRowActions |
| 发票、回款计划、回款记录 | cell / mobile 两份内联 ActionConfig |
| 审批中心 | 桌面 `#cell-actions` 是自定义按钮：详情 / 预览 / 催办 / 修改并重新提交，不走 TableRowActions。待办的通过 / 驳回只在手机卡片。目录里操作列还写了 `fixed: 'right'` |

客户跟踪操作列 260px，并显式 `fixed: 'right'`。去掉这一列后，横滑收益最大，但也必须同步取消右固定，否则最后一列业务字段会被钉死。

### 2.4 视图偏好不需要迁移任务

列偏好按 catalog key 查找。去掉 `actions` 后，历史偏好里残留的 `actions` 会自然对不上现有字段，被忽略。不要做回填或清理 job。

### 2.5 设计规范仍在写「操作列固定右侧」

`CRM-Docs/design-system/components/table.md`、`patterns/list-page.md`，以及 `listFieldCatalog.ts` 注释，都还把操作列当成列目录的一部分。实现切齐时这些文案必须改，否则下一张列表会按旧规范把操作列加回来。

## 3. 目标架构

本期只改前端。桌面由 DataTable 拥有行菜单；页面只提供动作。手机继续走现有卡片槽。动作合同不变。

| 层 | 职责 |
| --- | --- |
| 页面 | 提供 `getRowActions(row)`。删除 `#cell-actions`。从字段目录删除 `actions`。`#mobile-actions` 继续把同一份动作交给 TableRowActions 或审批中心现有卡片按钮 |
| DataTable | 桌面监听行右键和键盘菜单键；空动作 / 原生优先目标不接管；打开同一份 Context Menu；关菜单不发 `row-click`。`fixedRightCount` 默认 0 |
| 分组函数 | 把 primary / secondary 收成 常用 / 更多 / 危险。空组省略 |
| 菜单内容组件 | 只渲染 Context Menu 的 Label / Item / Separator，不负责 Trigger，也不渲染行尾按钮 |
| TableRowActions | 只服务手机卡片和任何非 DataTable 按钮行。禁止把它的 ⋯ 加回桌面表格 |

桌面组件选型锁定 shadcn-vue / reka-ui Context Menu，不使用 Dropdown Menu 冒充右键。Dropdown Menu 可以继续活在 TableRowActions 里，因为手机卡片仍需要「更多」。

## 4. 组件与数据流

### 4.1 动作合同

继续用现有 `ActionConfig`，不要另起一套菜单 DTO。页面输出：

```ts
export interface TableRowActionSet {
  primaryActions: ActionConfig[]
  secondaryActions: ActionConfig[]
}

getRowActions?: (row: T, index: number) => TableRowActionSet | null
```

handler、权限、确认框仍由页面闭包提供。DataTable 只根据 `visible !== false` 决定是否展示，根据 `disabled` 决定能否点，根据 `destructive` 决定进哪一组、用红色。点菜单项后调用 `action.handler(row)`，与今天 TableRowActions 的 `executeAction` 相同。

返回 `null`、两个数组都空、或过滤后没有任何可见项，都视为「无动作」。

### 4.2 菜单分组

新增纯函数，建议放在 `CRM-Client/src/components/crmwolf/tableRowActionGroups.ts`，供桌面菜单和单测共用。不要把分组写死在某个页面里。

| 分组 | 来源 |
| --- | --- |
| 常用 | 可见且非 destructive 的 `primaryActions` |
| 更多 | 可见且非 destructive 的 `secondaryActions` |
| 危险 | 可见且 `destructive === true` 的项，不论原先在 primary 还是 secondary |

空组的标题和分隔线一起省略。只有一项时不硬造分组标题。组与组之间用 `ContextMenuSeparator`。「更多」只是菜单内 Label，不是按钮，也不是 Dropdown 触发器。

`ActionConfig.separator` 桌面忽略，避免和分组分隔线打架。手机 TableRowActions 仍可按原字段画 ⋯ 里的分隔线，避免窄视口视觉回退。

公海「领取」这类只剩一个可见动作的行，菜单里就这一项。

### 4.3 菜单内容组件

新增 `TableRowContextMenuContent.vue`（名称可微调，但职责必须是内容层）。它接收 `row` + `TableRowActionSet`，内部调用分组函数，渲染：

- `ContextMenuLabel`：常用 / 更多 / 危险
- `ContextMenuItem`：图标 + 文案；disabled、destructive 样式跟现有下拉项对齐
- `ContextMenuSeparator`：只出现在两个非空组之间

这个组件不包含 Trigger，不渲染任何行内 Button。crmwolf 需要补齐导出：`ContextMenuLabel`、`ContextMenuSeparator`、`ContextMenuGroup`。现有 index 只导出了 Root / Content / Item / Trigger。

### 4.4 DataTable 怎么挂菜单

首选受控、表格级一份 Context Menu，不要给每行包一个 Root：

1. 表格级 `ContextMenu` 受控 `open`。Content 用当前行的 `getRowActions` 结果。
2. `<tr>` 上听 `contextmenu`。命中原生优先目标则直接 return，不 `preventDefault`。
3. 可见动作为空则直接 return，不 `preventDefault`，让系统菜单自己出现；CRM 菜单不打开。
4. 否则 `preventDefault` + `stopPropagation`，记下坐标和当前行，打开菜单。
5. 若 reka-ui Content 不吃坐标，再用 PointerDownOutside / 受控定位兜底；禁止为了定位在 `<tr>` 外包 `<div>`。

备选：`ContextMenuTrigger as-child` 直接绑到 `<tr>`。仅当 as-child 不插入非法表格 DOM、且仍能实现「空菜单不打开 / 原生目标放行」时才采用。只要 Trigger 会给 tr 外包节点，就必须退回受控方案。菜单内容组件两种挂法共用。

DataTable 删除对 `#cell-actions` 的桌面依赖。页面不再传这个槽。内部若还看到 `key === 'actions'`，继续当不可配置列并建议从 catalog 删除；防御即可，不是新功能。

### 4.5 页面接入

九页统一改成：

1. 抽出或补齐 `getRowActions(row)`，desktop / mobile 共用。
2. `<DataTable :get-row-actions="getRowActions">`。
3. 删除 `#cell-actions`。
4. 字段目录删除 `{ key: 'actions', ... }`。客户跟踪、审批中心的 `fixed: 'right'` 随这一条一起删。
5. `#mobile-actions` 保持。标准页继续 `<TableRowActions v-bind="getRowActions(row)" size="lg" />`。审批中心手机待办继续现有通过 / 驳回常显，不改成长按，也不改成右键。

没有行操作的未来表格可以不传 `getRowActions`。右键此时不应打开空菜单。

### 4.6 TableRowActions 的去留

保留组件，但职责收缩为窄视口按钮行。注释里「高频操作放在表格行外」这条对桌面表格不再成立。不要为了桌面再给它加 Context Menu 模式，也不要在 DataTable 行悬停时调用它。

## 5. 交互细节

### 5.1 右键与点行

左键点行：可交互列表仍 `row-click`，进详情或原来的行点击。右键只开菜单。菜单项 `@click.stop` / 选择后只执行 handler，不得再发 `row-click`。

右键之后浏览器可能补发 click / mouseup。DataTable 必须吞掉这次后续点击，否则会出现「右键开菜单又进详情」。关菜单点到菜单外时，也不得把这次 pointer 当成行点击。建议用短时锁：`contextmenu` 或菜单 `open` 期间忽略该行 click；菜单 close 后再放行。

Enter / Space 继续点行，不要改成开菜单。

### 5.2 键盘

九张表行已经能聚焦。焦点在行上时：

- Context Menu 键，或 Shift+F10，打开同一份菜单。
- Safari 等不一定把 Shift+F10 转成 `contextmenu`，所以 keydown 要显式处理 `ContextMenu` 和 `Shift+F10`。
- 打开后焦点进入菜单，方向键移动，Enter 执行，Esc 关闭。
- 键盘打开时没有鼠标坐标，按行矩形定位，优先行右侧中部或 reka-ui 默认锚点，保证不挡住行识别列。

桌面不提供行尾 ⋯。键盘发现成本按 PRD 接受。

### 5.3 原生菜单优先

若 `event.target` 命中 `a, input, textarea, select, [contenteditable="true"]`，或这些节点的内部，不打开行菜单，不 `preventDefault`。复制链接、选中单元格里的文本必须仍是浏览器行为。

行内已有 Button 在桌面操作列删除后应不再出现。若单元格里还有业务按钮（极少），点击仍走 `isNestedInteractiveElement` 的现有逻辑，不触发行点击；右键若点在 button 上，按原生优先处理，不抢系统/按钮菜单。

### 5.4 空菜单

过滤后可见动作为 0：不打开 CRM 菜单。典型：公海无领取权限、审批中心当前 tab 该行桌面无任何动作、权限全部隐藏。

### 5.5 固定列

`fixedRightCount` 默认从 1 改为 0。左侧识别列继续 `fixedLeftCount: 1`。去掉操作列后，禁止把「现在的最后一列」自动钉右。右侧阴影逻辑可以保留，但默认没有右固定列时不应再画出右墙阴影。

不要给任何业务列补 `fixed: 'right'` 来「填补」操作列空缺。

### 5.6 危险操作

菜单项仍然只调用原 handler。删除、输单、失效、标记无效等继续走原来的 AlertDialog / 确认框。取消则不执行。不得因为进了菜单就直接打接口。

## 6. 九页改造清单

每页都要做四件事：抽 `getRowActions`、传给 DataTable、删 `#cell-actions`、删 catalog 里的 actions。下面只写差异。

| 页面 | 改造要点 |
| --- | --- |
| 合同 `Contracts.vue` | 已有 `getRowActions`。直接改绑 DataTable，mobile 继续 v-bind 同一函数。 |
| 商机 `Opportunities.vue` | 把现有 primary / secondary helper 收成一个 `getRowActions`。动作：编辑、推进阶段、赢单、输单、删除，可见性保持现状。 |
| 客户 `Customers.vue` | 公海 tab 把裸「领取」改成 `primaryActions: [{ label: '领取', ... }]`，不要再写独立 Button。非公海保持新建商机 / 编辑为常用，移交 / 退回公海 / 赢单为更多，输单 / 失效 / 删除为危险。 |
| 线索 `Leads.vue` | 与客户相同：公海领取收进 `getRowActions`。非公海编辑 / 转化为客户为常用，领取 / 分配 / 退回公海为更多，标记无效 / 删除为危险。 |
| 发票 / 回款计划 / 回款记录 | 去掉 cell / mobile 两份内联配置，抽公共 `getRowActions`。动作集合原样搬家。 |
| 客户跟踪 `CustomerTracking.vue` | 去掉 260px 操作列和显式右固定。现有 `primaryActions(row)` 收成 `getRowActions`。 |
| 审批中心 `ApprovalCenter.vue` | 只把当前桌面列按钮收成 ActionConfig：详情；有附件则预览；submitted+REJECTED 则修改并重新提交；submitted+PENDING 则催办。桌面菜单不得加入通过 / 驳回。手机 `#mobile-actions` 原样保留，待办通过 / 驳回继续常显。 |

审批中心桌面现在不是「主按钮 + 更多」。收成菜单后仍按 4.2 分组：详情 / 预览进常用，催办 / 重新提交按现有语义进常用或更多，不要为了凑组而新增桌面动作。

## 7. 设计规范与注释同步

代码和规范必须一起改，避免下一张列表按旧文案把操作列加回来。

| 位置 | 改成 |
| --- | --- |
| `CRM-Docs/design-system/components/table.md` 结构与内容、操作与响应式 | 桌面以行右键菜单为唯一行操作入口；键盘保留菜单键 / Shift+F10。不要再写「操作集中在操作列」 |
| `CRM-Docs/design-system/patterns/list-page.md` 表格与密度、响应式适配、字段注册表 | 删除「操作列固定于右侧」。窄视口改成：保留标识，行操作走卡片底部，不依赖桌面操作列。字段注册表例子里的「操作列只有列配置」改成协作者 / 派生展示列 |
| `listFieldCatalog.ts` 注释 | 同步删除「操作列只有列配置」 |
| `DataTable.vue` 文件头注释 | 「固定首列和尾列」改为只固定左侧识别列，右侧默认不固定 |
| `listFieldCatalog.test.ts` | column-only 示例不要再用 `actions` 充当操作列契约。九页消费者契约改为：目录里没有 `key: 'actions'`，源码没有 `#cell-actions` |

## 8. 测试矩阵

单测优先打在 DataTable 和分组函数上，页面用契约测试锁接入，不把九页都写成点击快照。

### 8.1 组件单测

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T-01 | 目录无 actions，默认渲染 | 表头/单元格没有「操作」；对应 A-01 |
| T-02 | 行上 contextmenu，有可见动作 | 打开菜单，项与 getRowActions 可见集一致；对应 A-02 |
| T-03 | 左键点行 | 只发 row-click，不打开菜单；对应 A-03 |
| T-04 | 右键后再 pointerup/click，或点菜单外关闭 | 不发 row-click；对应 A-04 |
| T-05 | 悬停、聚焦 | 行内不出现 Button / ⋯；对应 A-05 |
| T-06 | 行聚焦后 Shift+F10 / ContextMenu 键 | 打开同一份菜单，可键盘执行；对应 A-06 |
| T-07 | getRowActions 返回空或全 hidden | 不打开菜单；对应 A-07 |
| T-08 | destructive 项 | 进危险组且红色；click 只调原 handler；对应 A-08 |
| T-09 | 多列横向滚动 | fixedRightCount 默认 0，最后一列不 sticky right；左列仍可固定；对应 A-09 |
| T-10 | 在 a / input 上右键 | 不 preventDefault，不打开行菜单；对应 A-12 |
| T-11 | 分组函数 | 常用 / 更多 / 危险来源正确；空组省略；destructive 从 primary 也会进危险组 |

### 8.2 页面契约与回归

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T-20 | 九个 DataTable 消费者源码 | 都传 getRowActions 或等价 API；都没有 #cell-actions；fields 里没有 key: 'actions' |
| T-21 | 九页都仍有 #mobile-actions | 窄视口卡片操作还在；对应 A-10 |
| T-22 | 审批中心 | 桌面 getRowActions 不含通过 / 驳回；mobile-actions 仍含待办通过 / 驳回；对应 A-11 |
| T-23 | 客户 / 线索公海 | 领取只出现在 getRowActions，不再有桌面裸 Button |
| T-24 | DataTableInteraction 现有点行 / 移动端卡片测试 | 继续绿；补上右键与 click 互斥 |

手工验收按 PRD A-01 到 A-12，九页各走一遍桌面右键和一次窄视口。审批中心额外核对手机待办通过 / 驳回仍在卡片上。危险项各抽一条确认框：删除、输单、失效、标记无效。

## 9. 发布与回滚

一次前端发布切齐，无后端、无 Alembic、无数据迁移。视图偏好里残留的 `actions` key 忽略即可。

发布前检查：桌面九页无操作列、无行尾 ⋯；右键和 Shift+F10 能开菜单；点行仍进详情；关菜单不进详情；横滑右侧无固定数据列；手机卡片操作未变。

回滚：回退该前端版本。没有库回滚，也没有双写窗口。

## 10. 非本期

| 项 | 原因 |
| --- | --- |
| 桌面行尾「更多」或悬停才出现的操作按钮 | PRD D-03，操作列换皮 |
| 手机长按菜单 | PRD D-04，和滚动、点进详情冲突 |
| 审批中心桌面补通过 / 驳回 | PRD A-11，这两项继续只在手机待办常显 |
| 批量行操作、多选后的右键 | 超出行操作收口 |
| 改确认框、权限码、接口 | 动作集合不变 |
| 给每行 ContextMenu Root 做复杂动画或二级子菜单 | 现有分组足够，不要引入 SubMenu 除非某页动作层级已经存在 |

## 11. 风险与实施顺序

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| as-child 破坏表格 DOM | 行错位或无法滚动 | 默认走受控菜单，不外包 tr |
| 右键后的合成 click | 误开详情 | 菜单生命周期内锁 row-click，单测锁 T-04 |
| Shift+F10 浏览器差异 | 键盘用户打不开菜单 | keydown 显式处理，不依赖系统转 contextmenu |
| 忘记改 fixedRightCount | 创建时间等被钉在右侧 | 默认改为 0，并加 T-09 |
| 审批中心桌面误带通过 / 驳回 | 和手机主任务按钮重复且破坏现网桌面流程 | T-22 契约禁止这两项进入 getRowActions |

建议实施顺序：分组函数和菜单内容组件 → DataTable 受控菜单 + 固定列默认值 + 单测 → 九页删操作列并改接入 → 设计规范与契约测试 → 按 PRD A-01…A-12 手工过一遍。未接到实施指令前不改代码。

## 12. 修订记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-08-19 | v1.0 | 按 PRD v1.1 首版。前端收口行操作到 Context Menu，手机保持卡片操作，取消右侧自动固定，九页一次切齐。 |

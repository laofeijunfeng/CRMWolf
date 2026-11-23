# 助手页

- **用途：**销售助手对话流的页面组合与块级视觉契约。
- **适用范围：**`components/agent-ui/**`、`components/sales-assistant/**`；路由 `/assistant`。
- **权威性：**本主题是助手页消息骨架、待办卡片、反馈条与输入区的唯一事实来源，属于页面特有规则；令牌、按钮、徽标、输入与浮层规则由各自文档拥有，本页不得覆盖。
- **相关规范：**[页面模式索引](README.md) · [组件选型](../components/registry.md) · [按钮](../components/button.md) · [输入](../components/input.md) · [状态徽标](../components/status-badge.md) · [列表卡片](../components/list-card.md) · [表格](../components/table.md) · [数据视图状态面板](../components/data-view-state-panel.md) · [令牌数值](../foundations/token-values.md) · [无障碍](../foundations/accessibility.md)

## 定位

助手页是 CRM 里的一个工作台页面，不是独立的聊天应用。几何、状态色、字阶与表面层级和其它页面完全一致；助手不拥有自己的颜色、圆角、高度或字号。对话里的块收敛为六个 recipe：消息骨架、待办卡片、选项瓦片、反馈条、数据块、执行过程与输入区。

## 分层

`components/agent-ui` 属于业务组合层，只组合 crmwolf 基元与 ui 原语，登记见[组件选型](../components/registry.md)。

- 不得出现颜色、圆角、高度、字号的字面值；间距只用 `$space-*` 档，字号只用 `text-body` 与 `text-caption`，行高与字号成对。
- 不得向 Button 传入颜色类改写变体，不得用 `:deep()` 覆盖基元外观。
- 焦点只用全局 `*:focus-visible`；禁用只用 `--disabled-opacity`；处理中用 Button 的 `loading`，文字与宽度不变。
- 状态色只通过 `data-tone` 与 `text-tone-*` 使用；透明度修饰符必须落在 opacity 刻度内，见[组件门禁](../governance/component-lifecycle.md#组件门禁)。

## 页面与消息骨架

- 对话内容与输入区同处 `--assistant-column` 居中阅读列；窄视口阅读列占满。
- 用户消息右对齐，使用 `--secondary` 气泡与 `rounded-lg`；不使用 `--primary`。
- 助手消息没有气泡：内容直接落在页面上，左侧为圆形品牌色头像；一组连续的助手条目只在首条显示头像，任务完成分隔线之后重新出现。
- 间距：轮次之间 `$space-6`，同轮条目之间 `$space-4`，块之间 `$space-2`。
- 消息骨架的类串只在宿主定义一处；不引入第二套气泡或消息原语。

## 待办卡片

- 结构为标题行、正文、底部操作区。标题行 = 标题（`text-body`、半粗）+ [状态徽标](../components/status-badge.md)（small）；底部操作区以 `border-t` 分隔并右对齐。
- 表面为 `--card` + `--border` hairline + `rounded-lg`，无阴影。不得用描边颜色、虚线或底色表达卡片状态；状态只由状态徽标表达。
- 属性组：标签 `text-caption`、值 `text-body`，同一张卡片内标签列宽一致。
- 底部操作遵循[按钮](../components/button.md)：取消在主操作左侧，同排同档；提交中使用 `loading`。
- 折叠内容使用 `ui/collapsible`，行高按列表单行。
- 不再待处理的选择与确认折叠为一行摘要，不保留任何操作入口；只读内容文字转 `--muted-foreground`。
- 历史跟进任务：状态徽标走 `agentDisposition` 域，文案取服务端 `result_title`；每个任务行按列表双行行高。

## 选项

- 单选与确认的选项使用 crmwolf `SegmentedChoiceControl`：说明行、分组标题、逐项禁用与多选都是它的扩展；即点即交的动作用 Button。
- 选中、悬停、焦点、禁用沿用分段选择与全局规则；被禁用的选项在说明行写明原因。
- 双行选项行高按列表双行，单行按控件高度 md；窄视口统一抬到 `--touch-target`。选项文字较长时打开换行，不得用省略号截断。

## 反馈条

- 提示、错误、动作结果与卡片内的失败、过期提示统一为反馈条 `AgentUIBanner`：由 `data-tone` 提供底色与语气色，左侧 `--icon-sm` 语气图标，标题用前景色，说明用 `--muted-foreground`，动作在右侧。
- 反馈条不描边，圆角 `--radius-md`。
- 语义色的文字与图标只用 `text-tone-*`，不得直接使用状态基色；success、warning、info 的派生色只给图标，不给文字，见[对比度](../foundations/accessibility.md#对比度)。

## 数据块

- 表格只用 crmwolf `DataTable` 的只读嵌入形态（`embedded`）。
- 实体列表使用 crmwolf `ListCard` 紧凑态：行高按列表单行，悬停 `--wash-hover`，以 chevron 作为可打开线索；不可打开的行不呈现为按钮。
- 指标组为单个 hairline 容器，竖线分栏；数值 `tabular-nums`，不引入第三档字号。
- 时间线节点 `--icon-sm`，节点间 hairline 连接；状态用状态徽标。
- 执行过程只使用 `AgentUIProcessBlock`：折叠头与步骤行行高按列表单行；步骤文字用前景色，只有图标与元信息带语义色；耗时与评分右对齐并使用 `tabular-nums`。聊天里的实时阶段由宿主映射成同一个块，不另写内联卡。
- 空态、加载、失败使用 crmwolf [DataViewStatePanel](../components/data-view-state-panel.md) 与 `FeedbackAlert`。

## 表单与输入区

- 卡片内的表单字段只用 crmwolf `*Field`，见[输入](../components/input.md#实现契约)；校验失败把焦点移到首个出错字段。
- 输入区是输入组合区：`rounded-lg` + `--input` hairline + `--card`，无阴影；获得焦点时边框改为 `--ring-input`。
- 同一排按钮使用同一档；发送为「图标 + 文字」的主按钮。
- 因待办卡片而锁定输入时，用一行文字说明原因；不改边框宽度或颜色。

[返回页面模式](README.md)

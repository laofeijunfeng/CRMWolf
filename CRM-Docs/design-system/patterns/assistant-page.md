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
- 焦点只用全局 `*:focus-visible`；禁用只用 `--disabled-opacity`；处理中用 Button 的 `loading`，标签保留为可读名称、宽度不变。
- 状态色只通过 `data-tone` 与 `text-tone-*` 使用；透明度修饰符必须落在 opacity 刻度内，见[组件门禁](../governance/component-lifecycle.md#组件门禁)。

## 页面与消息骨架

- 对话内容与输入区同处 `--assistant-column` 居中阅读列；窄视口阅读列占满。
- 用户消息右对齐，使用 `--secondary` 气泡与 `rounded-lg`；不使用 `--primary`。
- 助手消息没有气泡：内容直接落在页面上，左侧为圆形品牌色头像；一组连续的助手条目只在首条显示头像，任务完成分隔线之后重新出现。
- 间距：轮次之间 `$space-6`，同轮条目之间 `$space-4`，块之间 `$space-2`。
- 消息骨架的类串只在宿主定义一处；不引入第二套气泡或消息原语。
- 滚动遵循贴底跟随与上滑即停：用户位于底缘阈值内（`$space-2`）时新内容自动滚底，手动上滑离开后停止强拉；离底超过阈值在滚动容器底缘浮现轻量化「回到底部」按钮（`variant="outline" size="sm"` + `shadow-1`），点击平滑回底并恢复跟随；加载更早历史保持视口位置不跳动；首次打开长对话且末尾回复超出一屏时，优先落点到最近一轮用户消息起点上方留白。
- 视口高度使用 `min(100vh, 100dvh)` 并结合 `--safe-bottom` 适配移动端安全区；窄视口下外层会话区零横向溢出（`scrollWidth === clientWidth`），监听 `visualViewport` 变化保持最新消息可见。

## 待办卡片

- 结构为标题行、正文、底部操作区。标题行 = 标题（`text-body`、半粗）+ [状态徽标](../components/status-badge.md)（small）；底部操作区以 `border-t` 分隔并右对齐。
- 表面为 `--card` + `--border` hairline + `rounded-lg`，无阴影。不得用描边颜色、虚线或底色表达卡片状态；状态只由状态徽标表达。
- 属性组：标签 `text-caption`、值 `text-body`，同一张卡片内标签列宽一致。
- 底部操作遵循[按钮](../components/button.md)：取消在主操作左侧，同排同档；提交中使用 `loading`。
- 折叠内容使用 `ui/collapsible`，行高按列表单行。
- 不再待处理的选择与确认折叠为一行摘要，不保留任何操作入口；只读内容文字转 `--muted-foreground`。
- 同源消息刷新采用原位更新（保持稳定 key），不得因重挂载导致闪烁或高度跳动。
- `UNKNOWN_COMMIT_RESULT` 写入结果未确认时，待办卡片原位收敛为警告态（`data-tone="warning"`、`role="status"`、徽标「待核对」），仅提供「核对写入结果」单一入口，严禁展示成功态或再次开放「确认写入」。
- 历史跟进任务：状态徽标走 `agentDisposition` 域，文案取服务端 `result_title`；每个任务行按列表双行行高。

## 选项

- 单选与确认的选项使用 crmwolf `SegmentedChoiceControl`：说明行、分组标题、逐项禁用与多选都是它的扩展；即点即交的动作用 Button。
- 选中、悬停、焦点、禁用沿用分段选择与全局规则；被禁用的选项在说明行写明原因。
- 双行选项行高按列表双行，单行按控件高度 md；窄视口统一抬到 `--touch-target`。选项文字较长时打开换行，不得用省略号截断。

## 反馈条

- 提示、错误、动作结果与卡片内的失败、过期提示统一为反馈条 `AgentUIBanner`：由 `data-tone` 提供底色与语气色，左侧 `--icon-sm` 语气图标，标题用前景色，说明用 `--muted-foreground`，动作在右侧。
- 反馈条不描边，圆角 `--radius-md`。
- 语义色的文字与图标只用 `text-tone-*`，不得直接使用状态基色；语气文字在自身底色上须满足[对比度](../foundations/accessibility.md#对比度)，`ui/alert` 派生的反馈条同样适用。

## 数据块

- 表格只用 crmwolf `DataTable` 的只读嵌入形态（`embedded`）。
  - 表格外层提供独立横向滚动容器（`overflow-x-auto`），宽表在窄视口内局部滚动，不得撑破页面宽度。
- 实体列表使用 crmwolf `ListCard` 紧凑态：行高按列表单行，悬停 `--wash-hover`，以 chevron 作为可打开线索；不可打开的行不呈现为按钮。
- 查询结果由服务端共享查询引擎（`CRMQueryAgent`）经 `AgentUIComposer` 投影为 `entity_list`，客户列表正文固定为「共找到 N 家公司。」；分页块只派发服务端给出的翻页 action，由服务端按已存查询确定性重跑；前端不持有游标、不自行重查。查询失败只展示「查询没完成」错误块，不得复用写入失败文案。
- 指标组为单个 hairline 容器，竖线分栏；数值 `tabular-nums`，不引入第三档字号。
- 时间线节点 `--icon-sm`，节点间 hairline 连接；状态用状态徽标。
- 执行过程只使用 `AgentUIProcessBlock`：折叠头与步骤行行高按列表单行；步骤文字用前景色，只有图标与元信息带语义色；耗时与评分右对齐并使用 `tabular-nums`。聊天里的实时阶段由宿主映射成同一个块，不另写内联卡。
  - 展开态归属用户优先：未手动切换时运行中自动展开、完成后自动收起；用户手动展开或收起后在当前轮次内不再强行覆盖，新一轮任务重置为自动策略。
  - 单一进度锚点：实时过程块可见时，输入区上方不再重复展示旋转中的处理中条；安抚说明收口在过程块下方的反馈条内。
  - 运行态步骤标题使用语义色微光（`.text-shimmer`），`prefers-reduced-motion: reduce` 下停止动画并回退前景色；无详情步骤保持纯静态文本不进 Tab 序，有详情步骤以单步 `Collapsible`（`aria-expanded`、`unmount-on-hide="false"`）渐进披露。
  - 运行态基于服务端 `step_started_at` 在本地按 1s 刷新 `tabular-nums` 实时耗时，结束或卸载时清理定时器。
- 持久化异步操作条（Durable Async）独立展示 `QUEUED / RUNNING / DEGRADED / SUCCEEDED / FAILED` 状态徽标，不与 Envelope 或执行过程状态混用。
- 空态、加载、失败使用 crmwolf [DataViewStatePanel](../components/data-view-state-panel.md) 与 `FeedbackAlert`；空态可提供典型录入建议按钮，点击仅回填并聚焦输入框，不得自动发送。

## 表单与输入区

- 卡片内的表单字段只用 crmwolf `*Field`，见[输入](../components/input.md#实现契约)；校验失败把焦点移到首个出错字段。
- 输入区是输入组合区：`rounded-lg` + `--input` hairline + `--card`，无阴影；获得焦点时边框改为 `--ring-input`。
- 同一排按钮使用同一档；发送为「图标 + 文字」的主按钮。
- 因待办卡片而锁定输入时，用一行文字说明原因；不改边框宽度或颜色。
- 输入区交互契约：Enter 发送、Shift+Enter 换行，中文等 IME 组合态（`isComposing` 或 `keyCode === 229`）按 Enter 选词不得误发；内容为空或仅空格时禁用发送按钮。
- 输入框随内容自适应增高（上限 `min(8 行, 30vh)`，超出后内部滚动），发送清空后立即回缩，窗口尺寸变化时重算上限；待办卡片解锁且无阻断错误时，焦点平滑交回输入框。
- 输入增强：按 `team_id + user_id + conversation_id` 隔离本地草稿自动保存与恢复条；支持 `@客户` 快捷键与弹窗筛选（键盘 `↑↓/Enter/Esc`，服务端强校验权限）并以标签展示；支持图片粘贴/上传芯片（单行省略 + `title`）及预留语音入口按钮。
- 流式生成中断区分为「停止生成」（立即中止流并调用 turn stop；若服务端已进入写阶段返回 `WRITE_IN_PROGRESS`，则收敛到权威结果或「待核对」，不展示已停止提示；否则保留已生成只读文本并展示中性提示条与「重新生成」）与「算了（取消任务）」。
- 窄视口（`<768px`）下输入工具栏按钮、发送/停止按钮与待办卡片操作按钮统一满足 `--touch-target`（44px）触控热区。
- 实时状态播报：非阻断进度与恢复提示使用 `role="status"` / `aria-live="polite"`，阻断错误使用 `role="alert"`。

[返回页面模式](README.md)

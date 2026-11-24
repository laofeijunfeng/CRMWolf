# 按钮

- **用途：**触发用户发起的明确操作。
- **适用范围：**components 领域。
- **权威性：**本主题是按钮行为与组合的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [令牌数值](../foundations/token-values.md#控件与版式) · [圆角与层级](../foundations/radius-elevation.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md) · [状态徽标](status-badge.md)

## 使用边界

按钮用于提交、保存、确认、删除或启动任务；纯导航使用链接，状态展示不伪装成按钮。每个任务区域只保留一个主操作，危险操作必须使用危险语义并在不可逆时取得确认。

## 变体与内容

- 主按钮强调当前最重要的可执行任务；次要按钮用于并列的低优先级操作；文字按钮用于不应争夺注意力的操作。每个区域只有一个 primary；destructive 只用于删除或危险操作。
- 不设 success 变体：赢单用 `default`，输单用 `outline`，结果用 [StatusBadge](status-badge.md) 与 toast 呈现；不得用 class 覆盖变体颜色。
- 图标可辅助文字；纯图标按钮只用于编辑、更多、删除、关闭、复制、展开等通用动作，其余操作必须带文字，纯图标必须有 `aria-label`。按钮文案使用动词，说明将发生的结果。
- 同一组中的按钮按任务优先级排列；取消位于主操作左侧，取消或返回不与确认操作交换位置。

## 状态与反馈

默认、悬停、按压、处理中、成功或失败、禁用状态必须可区分。处理中阻止重复提交，并保留说明当前任务的文案或可读状态，loading 不改变按钮宽度，也不套用禁用透明度变淡；结束后恢复可操作状态或呈现结果。

禁用只用于当前确实不可执行的任务；说明原因或提供满足条件的路径。遵循[无障碍](../foundations/accessibility.md)的焦点、禁用和图标名称规则，使用[颜色令牌](../foundations/color-tokens.md)表达语义，不以颜色单独传达含义。

## 尺寸与动效

尺寸由 `size` 声明：xs 用于行内，sm 用于工具栏与 Tabs，md 用于表单，lg 用于主 CTA；同排按钮使用同一档。高度与内边距用 `--control-h-*`、`--control-px-*`，图标用 `--icon-*`，图标与文字间距用 `--control-gap-sm` / `--control-gap-md`，圆角用 `--radius-*`；数值见[令牌数值](../foundations/token-values.md#控件与版式)与[圆角与阴影](../foundations/token-values.md#圆角与阴影)。

按钮的几何、圆角和间距遵循[间距与布局](../foundations/spacing-layout.md)与[圆角与层级](../foundations/radius-elevation.md)。窄视口中的可触达尺寸与文字遵循[响应式与移动端](../foundations/responsive-mobile.md)。状态反馈和减少动效遵循[动效与性能](../foundations/motion-performance.md)。

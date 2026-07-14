# 按钮

- **用途：**触发用户发起的明确操作。
- **适用范围：**components 领域。
- **权威性：**本主题是按钮行为与组合的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [圆角与层级](../foundations/radius-elevation.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md)

## 使用边界

按钮用于提交、保存、确认、删除或启动任务；纯导航使用链接，状态展示不伪装成按钮。每个任务区域只保留一个主操作，危险操作必须使用危险语义并在不可逆时取得确认。

## 变体与内容

- 主按钮强调当前最重要的可执行任务；次要按钮用于并列的低优先级操作；文字按钮用于不应争夺注意力的操作。
- 图标可辅助文字，但仅图标按钮必须有可读名称。按钮文案使用动词，说明将发生的结果。
- 同一组中的按钮按任务优先级排列；取消或返回不与确认操作交换位置。

## 状态与反馈

默认、悬停、按压、处理中、成功或失败、禁用状态必须可区分。处理中阻止重复提交，并保留说明当前任务的文案或可读状态；结束后恢复可操作状态或呈现结果。

禁用只用于当前确实不可执行的任务；说明原因或提供满足条件的路径。遵循[无障碍](../foundations/accessibility.md)的焦点、禁用和图标名称规则，使用[颜色令牌](../foundations/color-tokens.md)表达语义，不以颜色单独传达含义。

## 尺寸与动效

按钮的几何、圆角和间距遵循[间距与布局](../foundations/spacing-layout.md)与[圆角与层级](../foundations/radius-elevation.md)。窄视口中的可触达尺寸与文字遵循[响应式与移动端](../foundations/responsive-mobile.md)。状态反馈和减少动效遵循[动效与性能](../foundations/motion-performance.md)。

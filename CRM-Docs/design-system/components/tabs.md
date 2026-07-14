# 标签页

- **用途：**切换同一上下文中的并列内容视图。
- **适用范围：**components 领域。
- **权威性：**本主题是标签页选择、切换与溢出规则的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [排版](../foundations/typography.md) · [颜色令牌](../foundations/color-tokens.md) · [圆角与层级](../foundations/radius-elevation.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md)

## 使用边界

标签页只切换同一对象或任务中的同级内容，不承担跨模块导航，也不用于连续步骤。标签文案应描述内容而非操作；当内容存在固定先后关系时，使用步骤流程。

默认显示一个明确的当前标签。当前内容与选中标签保持对应，切换后保留必要上下文；不因切换而静默丢弃未保存输入。

## 状态与溢出

默认、悬停、选中、不可用状态必须可辨。选中态使用文本、位置或指示物与语义颜色共同表达，不只依赖颜色。标签过多时使用可发现的溢出方式，窄视口可在标签栏内滚动；不得让页面整体横向滚动。

标签文字和层级遵循[排版](../foundations/typography.md)，颜色遵循[颜色令牌](../foundations/color-tokens.md)，圆角遵循[圆角与层级](../foundations/radius-elevation.md)。

## 可达性与动效

键盘用户可以在标签间移动、激活当前标签并进入对应内容；焦点、名称和内容关系遵循[无障碍](../foundations/accessibility.md)。切换反馈和减少动效遵循[动效与性能](../foundations/motion-performance.md)，窄视口规则遵循[响应式与移动端](../foundations/responsive-mobile.md)。

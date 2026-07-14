# 底部导航

- **用途：**提供移动端的一级目的地导航。
- **适用范围：**components 领域。
- **权威性：**本主题是底部导航项目、更多入口与移动行为的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [排版](../foundations/typography.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md) · [响应式与移动端](../foundations/responsive-mobile.md)

## 项目规则

底部导航只包含一级目的地，每项同时提供图标和文字标签，并明确当前目的地。项目数量保持在可快速扫读的范围；不得嵌套二级导航或用仅图标项目隐藏目的地含义。

移动端“更多”是固定的一级目的地，进入包含线索、回款、发票、审批和设置的完整目的地列表，而不是仅展开当前页面的局部操作。列表中保留名称、当前状态和可回退路径。

## 布局与响应式

底部导航固定在移动视口的底部，内容和触达区域避开安全区域。它在侧栏退出常驻导航的窄视口中承担一级导航；切换边界遵循[响应式与移动端](../foundations/responsive-mobile.md)。不得以底部导航遮挡页面最后的可操作内容。

文字遵循[排版](../foundations/typography.md)，活动和非活动状态使用[颜色令牌](../foundations/color-tokens.md)并辅以位置或文字线索。状态过渡与减少动效遵循[动效与性能](../foundations/motion-performance.md)。

## 可达性

每个项目具有可读名称、当前状态和可见焦点；键盘与辅助技术用户可识别“更多”进入的是完整目的地列表。完整要求遵循[无障碍](../foundations/accessibility.md)。

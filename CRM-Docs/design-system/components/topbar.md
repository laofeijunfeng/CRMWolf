# 顶部栏

- **用途：**承载当前页面定位、返回路径和全局操作。
- **适用范围：**components 领域。
- **权威性：**本主题是顶部栏信息优先级与组合的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [排版](../foundations/typography.md) · [颜色令牌](../foundations/color-tokens.md) · [间距与布局](../foundations/spacing-layout.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md) · [响应式与移动端](../foundations/responsive-mobile.md)

## 结构

顶部栏包含当前页面或对象的定位信息，并在有明确返回路径时提供返回操作。主标题保持可见；局部操作只在与当前上下文直接相关时出现，账户操作放入[用户菜单](user-menu.md)。

桌面端审批入口仅以铃铛按钮进入，不在顶部栏并列显示审批文字入口。铃铛的待办语义、数量和目的地遵循[审批通知](approval-notification.md)。

## 优先级与响应式

窄视口优先保留返回、标题和最高优先级操作，次要操作转入可发现的溢出入口。顶部栏避免与侧栏、底部导航或页面标题重复表达同一导航目的。

文字层级遵循[排版](../foundations/typography.md)，颜色和间距分别遵循[颜色令牌](../foundations/color-tokens.md)与[间距与布局](../foundations/spacing-layout.md)。安全区域和断点遵循[响应式与移动端](../foundations/responsive-mobile.md)。

## 可达性与反馈

图标操作必须提供可读名称；键盘顺序匹配任务优先级，焦点和禁用规则遵循[无障碍](../foundations/accessibility.md)。状态过渡和减少动效遵循[动效与性能](../foundations/motion-performance.md)。

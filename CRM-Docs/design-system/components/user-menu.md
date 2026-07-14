# 用户菜单

- **用途：**提供团队切换、个人设置和会话操作。
- **适用范围：**components 领域。
- **权威性：**本主题是账户菜单内容、层级与安全操作的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [圆角与层级](../foundations/radius-elevation.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md)

## 内容与分组

菜单按任务分组：团队切换、个人资料与账户设置、会话操作。当前团队必须可辨；切换团队后，界面内容和权限范围应更新并明确反馈。与账户无关的全局导航不得放入此菜单。

会话结束是独立且清晰的操作，与普通设置保持视觉分隔；需要确认时应说明影响。菜单项使用结果导向文案，避免只用图标或含糊术语。

## 展开与关闭

菜单从触发器附近展开，并保持在可用视口内。打开时焦点进入菜单；可用键盘逐项移动和激活，按关闭操作或移开焦点后返回触发器。点击或激活菜单项后按其任务结果关闭或保留菜单，不得产生不确定状态。

颜色遵循[颜色令牌](../foundations/color-tokens.md)，圆角与浮层层级遵循[圆角与层级](../foundations/radius-elevation.md)，焦点、名称和键盘规则遵循[无障碍](../foundations/accessibility.md)。过渡与减少动效遵循[动效与性能](../foundations/motion-performance.md)。

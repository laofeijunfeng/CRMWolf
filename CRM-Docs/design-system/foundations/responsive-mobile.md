# 响应式与移动端

- **用途：**断点、安全区域与滚动边界。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## Mobile-first 断点

先满足窄视口任务，再扩展内容空间。导航在可折叠侧栏断点进入对应模式；更大断点逐步扩展布局。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-breakpoint-xs-v2` | `375px` | 小型手机基线。 |
| `$wolf-breakpoint-sm-v2` | `768px` | 可折叠侧栏起点。 |
| `$wolf-breakpoint-md-v2` | `1024px` | 小桌面布局。 |
| `$wolf-breakpoint-lg-v2` | `1440px` | 大桌面布局。 |
| `$wolf-page-padding-mobile-v2` | `16px` | 移动端页面内边距。 |
| `$wolf-card-padding-mobile-v2` | `12px` | 移动端卡片内边距。 |
| `$wolf-section-gap-mobile-v2` | `16px` | 移动端模块间距。 |

## 安全区域与视口

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-safe-area-top-v2` | `env(safe-area-inset-top, 0px)` | 顶部系统区域。 |
| `$wolf-safe-area-bottom-v2` | `env(safe-area-inset-bottom, 0px)` | 底部手势区域。 |
| `$wolf-safe-area-left-v2` / `$wolf-safe-area-right-v2` | `env(safe-area-inset-left, 0px)` / `env(safe-area-inset-right, 0px)` | 横屏边缘。 |
| `$wolf-viewport-height-mobile-v2` | `min(100vh, 100dvh)` | 动态移动端视口高度。 |

交互目标避开安全区域；移动端高度使用动态视口令牌。

## 滚动与密集数据

页面主体不得横向滚动；信息密集表格可在自身容器横向滚动。表格细则见[表格](../components/table.md)。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-table-min-width-mobile-v2` | `100%` | 移动端表格最小宽度。 |
| `$wolf-table-cell-padding-mobile-v2` | `8px 4px` | 移动端紧凑单元格。 |

移动端优先保留核心列，避免固定像素宽的内容容器。正文与输入字号见[排版](typography.md)。

# 间距与布局

- **用途：**空间、容器与页面几何。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## 间距尺度

以令牌维持相邻内容、模块与页面的节奏；相同关系使用相同尺度。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-space-xs-v2` | `4px` | 元素内部的紧凑间距。 |
| `$wolf-space-sm-v2` | `8px` | 图标与文字、关联元素。 |
| `$wolf-space-md-v2` | `12px` | 模块内部间距。 |
| `$wolf-space-lg-v2` | `16px` | 模块间距与卡片内边距。 |
| `$wolf-space-xl-v2` | `24px` | 页面安全边距。 |
| `$wolf-space-2xl-v2` | `32px` | 大块内容分隔。 |

## 页面与容器

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-page-padding-v2` | `24px` | 桌面页面内边距。 |
| `$wolf-card-padding-v2` | `16px` | 卡片内边距。 |
| `$wolf-card-gap-v2` | `16px` | 卡片之间间距。 |
| `$wolf-section-gap-v2` | `24px` | 页面模块之间间距。 |
| `$wolf-table-row-height-v2` | `44px` | 数据行最小高度。 |
| `$wolf-table-header-height-v2` | `44px` | 表头高度。 |
| `$wolf-table-cell-padding-y-v2` / `$wolf-table-cell-padding-x-v2` | `12px` / `8px` | 单元格内边距。 |

页面容器负责与周边结构的间距；页面内容以自身内边距和模块间距组织，避免用外边距补偿结构位置。移动端替代尺度见[响应式与移动端](responsive-mobile.md)，圆角与层级见[圆角与层级](radius-elevation.md)。

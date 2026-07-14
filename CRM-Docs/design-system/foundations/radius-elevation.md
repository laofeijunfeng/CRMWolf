# 圆角与层级

- **用途：**圆角例外与视觉层级。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## 圆角

默认使用默认圆角令牌。仅在语义需要时使用命名的紧凑、大型或完全圆角例外；不以任意数值制造层级差异。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-radius-v2` | `6px` | 默认：卡片、控件和常规容器。 |
| `$wolf-radius-sm-v2` | `4px` | 紧凑标签与小型元素。 |
| `$wolf-radius-lg-v2` | `8px` | 大型浮层容器。 |
| `$wolf-radius-full-v2` | `9999px` | 圆形头像与胶囊形徽章。 |

## 阴影与层级

阴影只表达叠放关系和临时浮层，不作为常规卡片的装饰性动效。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-shadow-card-v2` | `0 1px 3px rgba(0, 0, 0, 0.1)` | 基础内容层。 |
| `$wolf-shadow-hover-v2` | `0 2px 8px rgba(0, 0, 0, 0.15)` | 可交互表面的悬停层级。 |
| `$wolf-shadow-dropdown-v2` | `0 -4px 12px rgba(0, 0, 0, 0.15)` | 向上展开的面板。 |
| `$wolf-shadow-modal-v2` | `0 4px 16px rgba(0, 0, 0, 0.15)` | 模态浮层。 |
| `$wolf-shadow-bottom-v2` | `0 -2px 8px rgba(0, 0, 0, 0.1)` | 底部固定区域。 |

过渡时长和减少动效要求见[动效与性能](motion-performance.md)。

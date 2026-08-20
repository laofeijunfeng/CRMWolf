# 圆角与层级

- **用途：**圆角例外与视觉层级。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [浮层表面](../components/overlay.md) · [设计系统根入口](../README.md)

## 圆角

控件使用默认圆角。卡片、菜单、面板、弹窗和抽屉使用 overlay 圆角，不以任意数值制造层级差异。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-radius-v2` / `$wolf-radius-control-v2` | `6px` | 按钮、输入和常规控件。 |
| `$wolf-radius-sm-v2` | `4px` | 紧凑标签与小型元素。 |
| `$wolf-radius-lg-v2` | `8px` | 少量较大控件。 |
| `$wolf-radius-xl-v2` / `$wolf-radius-surface-v2` / `$wolf-radius-overlay-v2` / `$wolf-radius-sheet-v2` / `$wolf-radius-popover-v2` | `12px` | 卡片、菜单、面板、弹窗和抽屉。 |
| `$wolf-radius-full-v2` | `9999px` | 圆形头像与胶囊形徽章。 |

`$wolf-radius-popover-v2` 与 overlay 同值，不得再当作控件圆角。浮层如何分档见[浮层表面](../components/overlay.md)。

## 阴影与层级

阴影只表达叠放关系和临时浮层。表格、列表和普通内容容器优先使用浅边框建立边界，默认不使用阴影。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-shadow-card-v2` | `0 1px 3px rgba(0, 0, 0, 0.1)` | 基础内容层。 |
| `$wolf-shadow-hover-v2` | `0 2px 8px rgba(0, 0, 0, 0.15)` | 可交互表面悬停与 Tooltip。 |
| `$wolf-shadow-overlay-v2` | `0 4px 12px rgba(0, 0, 0, 0.12)` | 向下展开的菜单和面板。 |
| `$wolf-shadow-dropdown-v2` | `0 -4px 12px rgba(0, 0, 0, 0.15)` | 仅向上展开的面板。 |
| `$wolf-shadow-modal-v2` | `0 4px 16px rgba(0, 0, 0, 0.15)` | 模态浮层。 |
| `$wolf-shadow-bottom-v2` | `0 -2px 8px rgba(0, 0, 0, 0.1)` | 底部固定区域。 |

过渡时长和减少动效要求见[动效与性能](motion-performance.md)。

# 圆角与层级

- **用途：**圆角例外与视觉层级。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源；数值见[令牌数值](token-values.md#圆角与阴影)。
- **相关规范：**[foundations 索引](README.md) · [令牌数值](token-values.md) · [浮层表面](../components/overlay.md) · [设计系统根入口](../README.md)

## 圆角

圆角全部由 `--radius` 派生，不以任意数值制造层级差异。

| 令牌 | 用途 |
| --- | --- |
| `--radius-sm`（`rounded-sm`） | 紧凑标签与小型元素。 |
| `--radius-md`（`rounded-md`） | 按钮、输入和常规控件。 |
| `--radius-lg`（`rounded-lg`） | 卡片、表格、面板、看板卡片等内容表面。 |
| `--radius-xl`（`rounded-xl`） | 弹窗、抽屉、菜单等浮层。 |
| `rounded-full` | 圆形头像与胶囊形元素。 |

浮层如何分档见[浮层表面](../components/overlay.md)。

## 阴影与层级

阴影只表达叠放关系和临时浮层。表格、列表和普通内容容器使用浅边框建立边界，不使用阴影。

| 令牌 | 用途 |
| --- | --- |
| `--shadow-1`（`shadow-1`） | 轻微抬起，如悬停中的可拖拽卡片、底部固定区域。 |
| `--shadow-2`（`shadow-2`） | 菜单、下拉、Popover 与 Tooltip，向上或向下展开同用。 |
| `--shadow-3`（`shadow-3`） | 模态弹窗与抽屉。 |

过渡时长和减少动效要求见[动效与性能](motion-performance.md)。

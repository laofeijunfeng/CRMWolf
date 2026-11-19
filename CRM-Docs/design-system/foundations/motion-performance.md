# 动效与性能

- **用途：**动效、降动效与响应预算。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源；时长与曲线数值见[令牌数值](token-values.md#动效)。
- **相关规范：**[foundations 索引](README.md) · [令牌数值](token-values.md) · [设计系统根入口](../README.md)

## 过渡令牌

动效应说明状态变化或直接反馈操作；避免无意义的持续运动和整卡抬升动画。

| 令牌 | 用途 |
| --- | --- |
| `--ease-standard` | 全部过渡曲线。 |
| `--duration-base` | 状态变化、悬停与按压反馈。 |
| `--duration-overlay` | 菜单、弹窗、抽屉等浮层进出。 |
| `--press-scale`（`.press-feedback`） | 按压缩放反馈。 |

过渡必须列出具体属性（如 `transition: background-color var(--duration-base) var(--ease-standard)`），禁止 `transition: all`。单次动画不超过令牌数值中的上限。减少动效偏好由 `base.css` 中唯一的 `prefers-reduced-motion` 块统一处理，组件不得重复声明。

## 性能预算

| 场景 | 预算 | 用途 |
| --- | --- | --- |
| 轻触反馈 | `100ms` | 操作立即可感知。 |
| 悬停反馈 | `150ms` | 指针反馈连贯。 |
| 加载提示 | `300ms` | 延迟时及时提示。 |

优先动画化 `transform` 与 `opacity`，避免导致布局重排的属性；复杂动效与绘制同步。焦点、禁用等状态的可访问性规则见[无障碍](accessibility.md)。

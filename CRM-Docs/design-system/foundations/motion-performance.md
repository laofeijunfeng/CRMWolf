# 动效与性能

- **用途：**动效、降动效与响应预算。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## 过渡令牌

动效应说明状态变化或直接反馈操作；避免无意义的持续运动和整卡抬升动画。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-transition-v2` | `all 0.15s ease` | 常规状态过渡。 |
| `$wolf-transition-hover-v2` | `all 0.2s ease` | 悬停反馈。 |
| `$wolf-transition-press-v2` | `all 0.15s ease` | 按压反馈。 |
| `$wolf-motion-state-duration-v2` | `150–300ms` | 状态变化时长。 |
| `$wolf-motion-max-duration-v2` | `500ms` | 单次动画时长上限。 |
| `$wolf-reduced-motion-duration-v2` | `0.01ms` | 减少动效偏好下的持续时间。 |
| `$wolf-reduced-motion-delay-v2` | `0ms` | 减少动效偏好下的延迟。 |

常规反馈使用状态时长令牌，动画不超过时长上限令牌。尊重减少动效偏好，并保留对应令牌定义的最小持续时间。

## 性能预算

| 交互 | 最大延迟 | 目标 |
| --- | --- | --- |
| 轻触反馈 | `100ms` | 操作立即可感知。 |
| 悬停反馈 | `150ms` | 指针反馈连贯。 |
| 加载提示 | `300ms` | 延迟时及时提示。 |

优先动画化 `transform` 与 `opacity`，避免导致布局重排的属性；复杂动效与绘制同步。焦点、禁用等状态的可访问性规则见[无障碍](accessibility.md)。

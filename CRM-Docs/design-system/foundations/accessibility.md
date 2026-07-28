# 无障碍

- **用途：**对比度、焦点和辅助技术支持。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## 对比度

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-contrast-text-min-v2` | `4.5:1` | 常规文字的前景与背景。 |
| `$wolf-contrast-large-text-min-v2` | `3:1` | 大文字的前景与背景。 |
| `$wolf-contrast-icon-focus-min-v2` | `3:1` | 图标与焦点指示。 |

亮色与暗色组合均须独立验证；颜色令牌见[颜色令牌](color-tokens.md)。

## 焦点

键盘可达元素必须有可见焦点，并满足焦点指示对比度令牌。不得在没有等效替代时移除焦点轮廓。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-focus-ring-width-v2` | `2px` | 默认焦点环宽度。 |
| `$wolf-focus-ring-color-v2` | `rgba(#2563EB, 0.5)` | 默认焦点环颜色。 |
| `$wolf-focus-ring-offset-v2` | `2px` | 焦点环外偏移。 |
| `$wolf-focus-ring-width-strong-v2` | `3px` | 关键操作与输入。 |
| `$wolf-focus-ring-width-subtle-v2` | `1px` | 次级链接。 |
| `$wolf-focus-shadow-v2` | `0 0 0 2px rgba(#2563EB, 0.3)` | 阴影式焦点替代。 |

## 辅助技术与禁用态

- 图标按钮提供可读名称；动态结果以适当的实时区域通知。
- 使用语义元素和关联标签；键盘顺序与视觉和任务顺序一致。
- 出错后将焦点移动到首个需要处理的字段。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-disabled-opacity-v2` | `0.38` | 所有禁用态的不透明度。 |
| `$wolf-cursor-disabled-v2` | `not-allowed` | 禁用态指针提示。 |

禁用项必须有禁用语义与可辨识视觉，且不接受操作。减少动效要求见[动效与性能](motion-performance.md)。

# 无障碍

- **用途：**对比度、焦点和辅助技术支持。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源；令牌数值见[令牌数值](token-values.md)。
- **相关规范：**[foundations 索引](README.md) · [令牌数值](token-values.md) · [设计系统根入口](../README.md)

## 对比度

| 组合 | 最低对比度 |
| --- | --- |
| 常规文字的前景与背景 | `4.5:1` |
| 大文字的前景与背景 | `3:1` |
| 图标与焦点指示 | `3:1` |

系统只有亮色主题，颜色组合只验证亮色；`--muted-foreground` 须在 `--card`、`--background`、`--wash-hover`、`--wash-selected` 与 `--muted` 上均满足常规文字阈值。颜色令牌见[颜色令牌](color-tokens.md)。

## 焦点

键盘可达元素必须有可见焦点，并满足焦点指示对比度。不得在没有等效替代时移除焦点轮廓。

全站唯一焦点样式为 `*:focus-visible` 的实线轮廓（宽度与偏移见[令牌数值](token-values.md#颜色)），颜色为 `--ring` 50% 不透明度；输入、文本域与组合框获焦时轮廓改用 `--ring-input`；危险操作使用 `.focus-ring-danger`。不得再以 `box-shadow` 另写焦点环。

## 辅助技术与禁用态

- 图标按钮提供可读名称；动态结果以适当的实时区域通知。
- 使用语义元素和关联标签；键盘顺序与视觉和任务顺序一致。
- 出错后将焦点移动到首个需要处理的字段。

所有禁用态统一使用 `--disabled-opacity` 与 `cursor: not-allowed`（`.disabled-state`），不得另设不透明度。处理中不是禁用，按[按钮](../components/button.md#状态与反馈)保持原底色。禁用项必须有禁用语义与可辨识视觉，且不接受操作。减少动效要求见[动效与性能](motion-performance.md)。

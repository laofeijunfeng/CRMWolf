# 排版

- **用途：**文字层级与可读性。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源；字阶数值见[令牌数值](token-values.md#控件与版式)。
- **相关规范：**[foundations 索引](README.md) · [令牌数值](token-values.md) · [设计系统根入口](../README.md)

## 字体与层级

优先使用系统字体栈保证业务文本的清晰与稳定；展示场景可使用展示字体。信息层级通过字号、字重和留白建立，不以颜色单独承载层级。

| 令牌 | 用途 |
| --- | --- |
| `font-sans`（`--font-sans`） | 常规业务文本。 |
| `font-display`（`--font-display`） | 展示性标题。 |
| `font-mono`（`--font-mono`） | 代码与技术标识。 |
| `text-display` | 展示标题。 |
| `text-title` | 页面主标题。 |
| `text-body-strong` | 区块标题与强调正文。 |
| `text-body` | 正文。 |
| `text-caption` | 次要备注与辅助信息。 |

只使用上述五档字阶，不另设辅助字号或移动端字阶。sm 尺寸控件内部文字略小于正文，不作为独立层级。移动端输入字号由 `base.css` 统一设置以防缩放，属唯一平台例外；数值见[令牌数值](token-values.md#控件与版式)。

颜色对比度见[无障碍](accessibility.md)，断点和页面空间见[响应式与移动端](responsive-mobile.md)。

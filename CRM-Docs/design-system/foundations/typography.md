# 排版

- **用途：**文字层级与可读性。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## 字体与层级

优先使用系统字体栈保证业务文本的清晰与稳定；展示场景可使用展示字体令牌。信息层级通过字号、字重和留白建立，不以颜色单独承载层级。

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-font-family-v2` | 系统字体栈 | 常规业务文本。 |
| `$wolf-font-display-v2` | `IBM Plex Sans` 加系统字体栈 | 展示性标题。 |
| `$wolf-font-mono-v2` | 等宽字体栈 | 代码与技术标识。 |
| `$wolf-font-size-title-v2` | `16px` | 页面主标题。 |
| `$wolf-font-size-body-v2` | `14px` | 桌面端正文。 |
| `$wolf-font-size-auxiliary-v2` | `13px` | 辅助信息。 |
| `$wolf-font-size-caption-v2` | `12px` | 次要备注。 |
| `$wolf-font-weight-normal-v2` / `$wolf-font-weight-medium-v2` / `$wolf-font-weight-semibold-v2` | `400` / `500` / `600` | 常规、强调与标题。 |

## 移动端

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-font-size-body-mobile-v2` | `16px` | 移动端正文及输入文本，避免自动缩放。 |
| `$wolf-font-size-title-mobile-v2` | `18px` | 移动端页面标题。 |
| `$wolf-font-size-caption-mobile-v2` | `14px` | 移动端辅助信息。 |

移动端输入与正文使用移动端正文令牌。颜色对比度见[无障碍](accessibility.md)，断点和页面空间见[响应式与移动端](responsive-mobile.md)。

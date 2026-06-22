# UI 设计规范

**适用范围**：CRM-Client 所有 UI 开发

---

## 品牌色权威来源

**唯一来源**：`CRM-Client/src/styles/variables.scss`

⚠️ **禁止在 Markdown 中重复定义颜色值**，所有 UI 代码必须引用 Sass 变量：

| 用途 | Sass 变量 | 禁止行为 |
|------|-----------|----------|
| 品牌主色 | `$wolf-primary` | 禁止硬编码颜色值 |
| 成功状态 | `$wolf-success-text` / `$wolf-success-bg` | 禁止硬编码颜色值 |
| 警告状态 | `$wolf-warning-text` / `$wolf-warning-bg` | 禁止硬编码颜色值 |
| 危险状态 | `$wolf-danger-text` / `$wolf-danger-bg` | 禁止硬编码颜色值 |

---

## 设计红线汇总

| 红线 | 说明 |
|------|------|
| 禁止纯色填充标签 | 必须用浅底色 + 同色系文字（引用 `$wolf-*-bg` + `$wolf-*-text`） |
| 禁用 700+ 字重 | 最大使用 600 (semibold) |
| 禁止高饱和色 | 使用 `$wolf-*` 低饱和色系 |
| 禁止多层阴影 | 卡片仅用一级阴影 |
| 禁止竖分割线 | 仅保留行分割线 |
| 禁止斑马纹 | 用 hover 高亮代替 |
| **禁止魔数** | **所有间距/圆角必须引用 Design Token 或向 4px 基准网格对齐** |

---

## 标签颜色引用指南

生成状态标签时，必须使用以下 Sass 变量组合：

| 状态 | 背景变量 | 文字变量 |
|------|----------|----------|
| 成功/完成 | `$wolf-success-bg` | `$wolf-success-text` |
| 警告/待处理 | `$wolf-warning-bg` | `$wolf-warning-text` |
| 错误/失败 | `$wolf-danger-bg` | `$wolf-danger-text` |
| 信息/进行中 | `$wolf-primary-light` | `$wolf-primary` |
| 默认/无状态 | `$wolf-bg-hover` | `$wolf-text-tertiary` |

---

## Design Token 速查

| Token | Sass 变量 | 说明 |
|-------|-----------|------|
| 页面内边距 | `$wolf-page-padding` 或自定义 | 24px |
| 卡片内边距 | `$wolf-card-padding` 或自定义 | 20px |
| 卡片圆角 | `$wolf-radius-lg` | 12px |
| 按钮圆角 | `$wolf-radius-sm` | 4px/8px |
| 输入框圆角 | `$wolf-radius-md` | 6px |
| 弹窗圆角 | `$wolf-radius-xl` | 16px |

⚠️ **禁止在 CSS 中写魔数如 `margin: 13px`，必须向 4px 基准网格对齐**

---

## 字号规范

| 用途 | 推荐值 | 字重 |
|------|--------|------|
| 页面大标题 | 24px | 600 |
| 页面标题 | 20px | 600 |
| 卡片标题 | 16px | 600 |
| 正文 | 14px | 400 |
| 小字/辅助 | 13px | 400 |
| 标签 | 12px | 400 |

---

## 表格规范

| 规则 | 要求 |
|------|------|
| 表头高度 | 44px |
| 表头背景 | `$wolf-bg-hover` |
| 内容行最小高度 | 44px |
| Hover 背景 | `$wolf-bg-active` |
| 禁止竖分割线 | 仅行分割 |

---

## 页面布局规范

| 规则 | 值 |
|------|-----|
| 表单卡片 max-width | 800px |
| 页面头部 sticky 高度 | 48px |
| 弹窗宽度（小/中/大） | 400px/600px/800px |
| 抽屉宽度（小/中/大） | 400px/600px/700px+ |

---

## 禁止行为汇总

| 禁止 | 原因 |
|------|------|
| 硬编码颜色值 | 违反唯一来源原则，导致不一致 |
| 使用魔数间距 | 违反 Design Token 体系 |
| 纯色填充标签 | 违反低饱和色原则 |
| 700+ 字重 | 视觉过重，违反极简原则 |

---

**详细参考**：`CRM-Client/src/styles/variables.scss`, `CRM-Client/docs/DESIGN-PRINCIPLES.md`
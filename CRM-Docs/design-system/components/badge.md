# 徽标

徽标用于承载短文本元信息，例如数量、负责人、赢率、阶段和状态补充。徽标只表达当前对象的属性，不承载主要操作；需要点击行为时应使用按钮或菜单。

## 视觉规则

- 默认使用 shadcn-vue `Badge` 封装，不新增一次性标签样式。
- 徽标默认中性：`--muted` 浅底、`--foreground` 文字，用于数量、负责人、赢率、阶段等常规元信息。
- 需要表达好 / 需关注 / 坏时只用 `data-tone="success|warning|danger|info"`，浅底与文字色由[令牌数值](../foundations/token-values.md#状态语气)派生；不得使用 Tailwind 色阶类，不使用实心彩色徽标，阶段与分类不配色。
- 徽标圆角、字号和间距遵循[圆角与层级](../foundations/radius-elevation.md)、[排版](../foundations/typography.md)和[间距与布局](../foundations/spacing-layout.md)。长文本必须截断或换行，不能撑开卡片或列宽。

## 使用约束

- 同一卡片内徽标数量保持克制，只保留用户判断下一步所需的信息。
- 不只依赖颜色表达状态；徽标文字必须直接说明含义。
- 徽标与正文之间应有稳定间距，不跟标题、金额或操作区重叠。

[返回组件契约](README.md)

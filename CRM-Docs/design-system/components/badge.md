# 徽标

徽标用于承载短文本元信息，例如数量、负责人、赢率、阶段和状态补充。徽标只表达当前对象的属性，不承载主要操作；需要点击行为时应使用按钮或菜单。

## 视觉规则

- 默认使用 shadcn-vue `Badge` 封装，不新增一次性标签样式。
- 在浅色背景、浅色分组列或看板卡片内，常规业务元信息徽标优先使用浅底深字，减少白色卡片内的重色块密度。
- 阶段或分类徽标可使用官方 Tailwind 色阶表达分组。常规数量和元信息使用浅色组合，例如 `blue-50 text-blue-700 border-blue-100`、`emerald-50 text-emerald-700 border-emerald-100`；少量关键强调信息可使用实心组合，例如 `sky-600 text-white border-transparent`。
- 徽标圆角、字号和间距遵循[圆角与层级](../foundations/radius-elevation.md)、[排版](../foundations/typography.md)和[间距与布局](../foundations/spacing-layout.md)。长文本必须截断或换行，不能撑开卡片或列宽。

## 使用约束

- 同一卡片内徽标数量保持克制，只保留用户判断下一步所需的信息。
- 不只依赖颜色表达状态；徽标文字必须直接说明含义。
- 徽标与正文之间应有稳定间距，不跟标题、金额或操作区重叠。

[返回组件契约](README.md)

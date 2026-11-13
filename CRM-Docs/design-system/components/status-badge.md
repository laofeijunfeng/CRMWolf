# 状态徽标

- **用途：**以紧凑形式表达记录或流程的业务状态。
- **适用范围：**components 领域。
- **权威性：**本主题是所有状态语义、调色板映射与徽标内容的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [排版](../foundations/typography.md) · [圆角与层级](../foundations/radius-elevation.md) · [无障碍](../foundations/accessibility.md)

## 语义映射

状态徽标使用成功、警告、危险、中性和信息等语义调色板；具体颜色令牌由[颜色令牌](../foundations/color-tokens.md)唯一拥有。页面模式和业务页面不得复制状态色值、色表或替代映射。

业务状态先映射到稳定的语义类别，再呈现给用户。相同含义在不同对象和页面中使用同一语义；未知、处理中或不适用状态使用明确文案，不能借用成功或失败颜色猜测含义。

## 内容与组合

每个徽标包含状态文字，颜色仅作辅助。可补充图标或简短说明，但不以颜色或形状单独传达状态。徽标用于快速扫描，不取代详情、时间线或需要采取行动的说明。

同一行内的多个徽标按任务相关性排序，避免为每个字段重复放置。若状态可执行，将操作放在相邻的按钮、链接或菜单中，不把静态徽标伪装为入口。

## 可达性与视觉

文字层级遵循[排版](../foundations/typography.md)，胶囊或紧凑形态遵循[圆角与层级](../foundations/radius-elevation.md)。对比度和非颜色线索遵循[无障碍](../foundations/accessibility.md)。

## 实现契约

- 状态展示映射的唯一来源是 `CRM-Client/src/utils/statusPresentation.ts`。页面和面板只做 API 值到领域 key 的适配，不复制文案或颜色表。
- `invoiceApplication`、`licenseApplication` 与 `approval` 是相互独立的领域。申请的“已批准”与通用审批的“已通过”共享 success 语义，但不合并业务枚举。
- 未知状态显示“未知状态”，使用 neutral 语义，并通过 `title`、`data-status-domain` 和 `data-status-value` 保留原始值；不得回退成合法状态。属性类动态来源、行业名称继续显示原值。
- 静态状态徽标不可聚焦，也不可伪装成按钮；状态文字必须存在，圆点或图标只能补充语义，图标应使用 `aria-hidden`。

## 运行时颜色

- 状态徽标使用 `CRM-Client/src/styles/base.css` 中成对的 `--status-*-foreground` / `--status-*-background` 运行时变量，并通过 `data-status-tone` 选择语义。浅色和强制深色主题都必须使用不透明背景，避免依赖外层页面表面。
- 普通小字号文字的实际前景/背景对比度目标为至少 4.5:1；页面特有的授权有效期摘要若处于遗留白色表面，也必须使用对应的成对变量。

# 颜色令牌

- **用途：**语义颜色与令牌使用。
- **适用范围：**foundations 领域。
- **权威性：**本主题是颜色使用规则的唯一事实来源；数值见[令牌数值](token-values.md#颜色)。
- **相关规范：**[foundations 索引](README.md) · [令牌数值](token-values.md) · [设计系统根入口](../README.md)

## 使用原则

使用语义令牌表达角色，不以色值表达业务含义；状态除颜色外还应有文字或其他可感知线索。系统只有亮色主题。运行时唯一入口为 `CRM-Client/src/styles/base.css` 的 `:root`；Tailwind 只映射 `var(--x)`，组件使用 `bg-background`、`text-foreground`、`bg-primary`、`border-border`、`text-muted-foreground` 等语义类，不使用 Tailwind 色阶类（如 `blue-500`、`slate-600`）。

`$wolf-*-v2` 是迁移期过渡桥接，只指向上述令牌，新代码不得引用；`--wolf-*` 已废除。见[兼容策略](../migration/compatibility.md)。

## 角色分工

| 令牌 | 用途 |
| --- | --- |
| `--primary` | 主操作按钮；中性深色，不用品牌蓝。 |
| `--brand` | 链接、活动导航、选中态、品牌标识。 |
| `--ring` / `--ring-input` | 全局焦点环 / 输入控件获焦边框。 |
| `--background` / `--card` / `--popover` | 页面、内容表面、浮层表面。 |
| `--muted` | 辅助背景与看板列。 |
| `--foreground` / `--muted-foreground` | 主信息与输入值 / 次级、辅助与占位文字。 |
| `--border` / `--input` | 描边与输入框边框。 |
| `--wash-hover` / `--wash-selected` / `--accent` | 行与菜单项的悬停 / 选中中性水洗；不使用蓝色悬停。 |
| `data-tone` + `--status-*` | 成功、警告、危险、信息与中性状态；浅底与文字色由基色派生。 |
| `--chart-1…5` | 图表系列。 |

对比度阈值与焦点颜色的可访问性要求见[无障碍](accessibility.md)。

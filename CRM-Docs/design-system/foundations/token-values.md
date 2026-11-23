# 令牌数值

- **用途：**全部设计数值的文档镜像。
- **适用范围：**foundations 领域；所有组件、模式与页面。
- **权威性：**本主题是设计数值的唯一事实来源，不参与规则优先级；运行时唯一入口为 `CRM-Client/src/styles/base.css` 的 `:root`，两者必须同步修改。
- **相关规范：**[foundations 索引](README.md) · [颜色令牌](color-tokens.md) · [设计系统根入口](../README.md)

系统只有亮色主题，不定义 `.dark`、`dark:` 变体或 `prefers-color-scheme`。其他文档只引用令牌名，不得重复书写色值或像素表。

## 颜色

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `--background` | `#fcfcfd` | 页面与侧栏表面。 |
| `--card` / `--popover` | `#fff` | 卡片、表格与浮层表面。 |
| `--muted` | `#f1f5f9` | 辅助背景、看板列。 |
| `--foreground` | `#020817` | 主信息与输入值。 |
| `--muted-foreground` | `#475569` | 次级、辅助与占位文字。 |
| `--border` / `--input` | `#e2e8f0` | 描边与输入框边框。 |
| `--primary` | `#17191b` | 主操作按钮。 |
| `--brand` | `#0472c3` | 链接、活动导航、选中、品牌标识。 |
| `--ring` / 焦点轮廓 | `= --brand` / `2px` 实线，外偏移 `2px` | 全局焦点环，50% 不透明度；`*:focus-visible` 全站唯一焦点样式。 |
| `--ring-input` | `#1f8aff` | 输入与选择控件获焦边框。 |
| `--accent` | `#f5f5f6` | 白底上的悬停等值色。 |
| `--wash-hover` / `--wash-selected` | 前景色 4% / 8% 半透明 | 行悬停 / 选中；叠白 = `#f5f5f6` / `#ebebec`。 |

## 状态语气

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `--status-success` | `#20c45f` | 成功、已完成。 |
| `--status-warning` | `#daa100` | 需关注。 |
| `--status-danger` | `#e50022` | 失败、危险、已流失。 |
| `--status-info` | `#269cff` | 提示信息。 |
| `--status-neutral` | `= --muted-foreground` | 中性状态。 |
| `text-tone-success` / `warning` / `danger` / `info` | 基色 `--status-fg-mix` + 前景 | 状态色的图标与文字（Tailwind `text-tone-*`）；不得直接用基色做图标或文字。 |
| `--status-bg-mix` | `12%` | 语气浅底 = 基色 12%。 |
| `--status-fg-mix` | `72%` | 语气文字 = 基色 72% + 前景 28%。 |
| `--chart-1…5` | brand / success / warning / info / muted-foreground | 图表系列。 |

状态只通过 `data-tone="success|warning|danger|info"` 或缺省中性使用，不使用 Tailwind 色阶类。

## 圆角与阴影

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `--radius-sm` | `6px` | 紧凑标签、小型元素。 |
| `--radius-md` | `8px` | 按钮、输入与常规控件。 |
| `--radius-lg`（`--radius`） | `10px` | 卡片、表格、面板等内容表面。 |
| `--radius-xl` | `14px` | 弹窗、抽屉与浮层。 |
| `rounded-full` | `9999px` | 头像与胶囊形元素。 |
| `--shadow-1` | `0 1px 2px rgb(0 0 0 / .05)` | 轻微抬起。 |
| `--shadow-2` | `0 4px 12px -2px rgb(0 0 0 / .08), 0 2px 4px rgb(0 0 0 / .04)` | 菜单、下拉、Tooltip。 |
| `--shadow-3` | `0 9px 48px rgb(0 0 0 / .08), 0 6px 24px rgb(0 0 0 / .1), 0 1px 1px rgb(0 0 0 / .04)` | 模态浮层。 |

## 控件与版式

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `--control-h-xs/sm/md/lg` | `24` / `28` / `32` / `36px` | 控件高度；桌面默认 md。 |
| `--control-px-xs/sm/md/lg` | `8` / `10` / `12` / `14px` | 控件水平内边距。 |
| `--control-gap-sm/md` | `4` / `6px` | 图标与文字间距（xs·sm / md·lg）。 |
| `--icon-xs/sm/lg` | `14` / `16` / `18px` | 图标尺寸。 |
| `--touch-target` | `44px` | 移动端可点下限，含输入控件。 |
| `--menu-min-width` | `160px` | Menu 浮层最小宽度（右键菜单、下拉菜单）。 |
| `--dialog-w-sm/md/lg/xl/full` | `440` / `560` / `720` / `960px` / `90vw` | Dialog 宽度档位（`DialogContent size`，默认 md）；AlertDialog 固定 sm；窄视口统一 `calc(100vw - 2rem)`。 |
| 移动端输入字号 | `16px` | 防 iOS 缩放，`base.css` 统一设置。 |
| `text-display` / `var(--font-size-display)` | `24/32px · 600` | 展示标题。 |
| `text-title` / `var(--font-size-title)` | `18/28px · 600` | 页面主标题、浮层标题（Dialog/Sheet/AlertDialog）。 |
| `text-body-strong` / `var(--font-size-body-strong)` | `16/24px · 500` | 区块标题、卡片标题。 |
| `text-body` / `var(--font-size-body)` | `14/20px · 400` | 正文；正文不得使用 13px。scoped SCSS 字号必须用 `var(--font-size-*)` / `var(--line-height-*)`，不得写裸 px。Label 与列表主字段用 body + `font-medium`。 |
| `var(--font-size-control-sm)` | `13px` | 仅限 sm 控件内文字（筛选栏、工具栏、Tabs），不得用于正文。 |
| 数值列 / 正文行长 | `tabular-nums` / ≤ 72 字符 | 金额、数量、日期列等宽数字（`td[data-numeric]` 自动生效）/ 说明、帮助文字等长段落最大行长。 |
| `text-caption` / `var(--font-size-caption)` | `12/16px · 400` | 次要备注。 |
| `--disabled-opacity` | `0.5` | 所有禁用态。 |

## 动效

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `--ease-standard` | `cubic-bezier(.4, 0, .2, 1)` | 全部过渡曲线。 |
| `--duration-base` | `150ms` | 状态、悬停、按压。 |
| `--duration-overlay` | `200ms` | 浮层进出。 |
| `--press-scale` | `0.98` | 按压缩放。 |
| 单次动画上限 | `300ms` | 任何动画不得超过。 |

## 间距与布局

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$space-1/2/3/4/6/8`（Tailwind `*-space-N` 档，如 `p-space-1`） | `4` / `8` / `12` / `16` / `24` / `32px` | 间距尺度。根字号 14px 下 Tailwind rem 档（`p-1`、`gap-2`）会缩放为 3.5 / 7px，新代码不得使用。 |
| `--page-padding` | `24px`（<768px 为 `16px`） | 页面内边距，含列表页顶部。 |
| `--assistant-column` | `720px`（<768px 为 `100%`） | 助手页阅读列；对话内容与输入区同轴。 |
| `--sidebar-width` | `220px` | 桌面侧栏宽度。 |
| `--topbar-height` / `--bottom-nav-height` / `--context-tabs-height` | `56px` / `56px` / `36px` | 顶栏 / 移动端底部导航 / 上下文标签栏。 |
| 卡片内边距 / 卡片间距 / 模块间距 | `$space-4` / `$space-4` / `$space-6`（移动端 `$space-3` / `$space-4` / `$space-4`） | 容器节奏。 |
| 表格行 / 表头最小高度；表格单元格内边距 | `44px`；纵 `12px` / 横 `8px`（移动端 `8px 4px`） | 数据表格。 |
| 列表 / 菜单行高 | `36px`（单行）/ `52px`（双行） | 菜单项、紧凑列表行；双行含主次两行文字。 |
| `$bp-xs/sm/md/lg` | `375` / `768` / `1024` / `1440px` | 断点，与 Tailwind `screens` 一致。 |
| `--safe-top` / `--safe-bottom`；移动端视口高度 | `env(safe-area-inset-top/bottom, 0px)`；`min(100vh, 100dvh)` | 安全区域；动态视口。 |

# 颜色令牌

- **用途：**语义颜色与令牌使用。
- **适用范围：**foundations 领域。
- **权威性：**本主题是该范围的唯一事实来源。
- **相关规范：**[foundations 索引](README.md) · [设计系统根入口](../README.md)

## 使用原则

使用语义令牌表达角色，不以色值表达业务含义；状态除颜色外还应有文字或其他可感知线索。组件基础色遵循 `components.json` 中的 shadcn-vue `baseColor: "slate"` 与 `cssVariables: true` 配置，中性色使用 slate，主强调色使用官方 Tailwind blue 色阶。运行时唯一入口为 `CRM-Client/src/styles/base.css` 的 shadcn CSS variables。`$wolf-*` / `--wolf-*` 为业务兼容层，新增组件优先使用 `bg-background`、`text-foreground`、`bg-primary`、`border-border`、`text-muted-foreground` 等 shadcn 语义令牌。

## 亮色令牌

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-primary-v2` | `#2563EB` | 主操作、活动导航、链接。 |
| `$wolf-primary-hover-v2` | `#1D4ED8` | 主操作悬停。 |
| `$wolf-primary-light-v2` | `rgba(#2563EB, 0.1)` | 选中与浅色背景。 |
| `$wolf-bg-page-v2` | `#F8FAFC` | 页面画布。 |
| `$wolf-bg-card-v2` | `#FFFFFF` | 卡片与数据区域背景。 |
| `$wolf-bg-hover-v2` | `#EFF6FF` | 悬停背景。 |
| `$wolf-bg-muted-v2` | `#F1F5F9` | 辅助背景。 |
| `$wolf-text-primary-v2` | `#020817` | 主信息。 |
| `$wolf-text-secondary-v2` | `#64748B` | 正文与次级信息。 |
| `$wolf-text-tertiary-v2` | `#64748B` | 辅助信息。 |
| `$wolf-success-v2` / `$wolf-warning-v2` / `$wolf-danger-v2` | `#10B981` / `#F59E0B` / `#DC2626` | 成功、警告、危险状态。 |

## 暗色令牌

| 令牌 | 解析值 | 用途 |
| --- | --- | --- |
| `$wolf-bg-page-dark-v2` | `#020817` | 页面画布。 |
| `$wolf-bg-card-dark-v2` | `#020817` | 卡片与数据区域背景。 |
| `$wolf-bg-hover-dark-v2` | `#1E293B` | 悬停背景。 |
| `$wolf-text-primary-dark-v2` | `#F8FAFC` | 主信息。 |
| `$wolf-text-secondary-dark-v2` | `#CBD5E1` | 次级信息。 |
| `$wolf-success-dark-v2` / `$wolf-warning-dark-v2` / `$wolf-danger-dark-v2` | `#34D399` / `#FBBF24` / `#F87171` | 暗色状态表达。 |

对比度阈值与焦点颜色的可访问性要求见[无障碍](accessibility.md)。

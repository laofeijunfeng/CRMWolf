# CRMWolf 设计原则与基础 Token

**适用范围**：前端 UI 开发必读

---

## 一、设计原则

### 1.1 核心原则

- **简约至上**：去除多余装饰，保留核心信息
- **层次分明**：浅灰背景 + 白色卡片建立清晰层级
- **轻量高效**：柔和阴影、细腻圆角、流畅动效
- **一致统一**：全系统使用同一套设计 token
- **信息密度**：在保证可读性的前提下，提高信息密度

### 1.2 命名空间

所有 CSS 类名使用 `wolf-` 前缀：

```css
.wolf-card      /* 卡片 */
.wolf-tag       /* 标签 */
.wolf-btn       /* 按钮 */
.wolf-table     /* 表格 */
.wolf-layout    /* 布局 */
```

---

## 二、色彩系统

### 2.1 页面背景

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-bg-page` | #F5F7FA | 页面背景 |
| `--wolf-bg-card` | #FFFFFF | 卡片背景 |
| `--wolf-bg-hover` | #F7F8FA | 悬停背景 |
| `--wolf-bg-active` | #F2F3F5 | 激活/选中背景 |
| `--wolf-bg-sidebar` | #1A1F2E | 侧边栏背景 |

### 2.2 品牌主色（Wolf Blue）

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-primary` | #165DFF | 主色 - 按钮、链接 |
| `--wolf-primary-hover` | #0E42D2 | 主色悬停 |
| `--wolf-primary-active` | #0B36B0 | 主色按下 |
| `--wolf-primary-light` | #E8F3FF | 主色浅背景 |

### 2.3 状态色

| 状态 | 文字色 | 背景色 | 用途 |
|------|--------|--------|------|
| 成功 | #00B42A | #E8FFEA | 成功、活跃 |
| 警告 | #FF7D00 | #FFF7E8 | 警告、VIP |
| 错误 | #F53F3F | #FFECE8 | 错误、删除 |
| 信息 | #165DFF | #E8F3FF | 信息、进行中 |
| 紫色 | #722ED1 | #F5E8FF | 复购率等特殊指标 |
| 灰色 | #86909C | #F2F3F5 | 默认、无状态 |

### 2.4 文字色

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-text-primary` | #1D2129 | 主要文字 - 标题 |
| `--wolf-text-secondary` | #4E5969 | 次要文字 - 正文 |
| `--wolf-text-tertiary` | #86909C | 辅助文字 - 标签 |
| `--wolf-text-placeholder` | #C9CDD4 | 占位符、禁用 |
| `--wolf-text-link` | #165DFF | 链接文字 |
| `--wolf-text-inverse` | #FFFFFF | 反色文字 |

### 2.5 边框色

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-border-color` | #E5E6EB | 边框 |
| `--wolf-border-light` | #F2F3F5 | 浅色边框 |
| `--wolf-border-focus` | #165DFF | 聚焦边框 |

---

## 三、字体系统

### 3.1 字号层级

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-font-size-display` | 24px | 页面大标题 |
| `--wolf-font-size-title` | 20px | 页面标题 |
| `--wolf-font-size-card-title` | 16px | 卡片标题 |
| `--wolf-font-size-body` | 14px | 正文 |
| `--wolf-font-size-small` | 13px | 小字 |
| `--wolf-font-size-label` | 12px | 标签/辅助文字 |

### 3.2 字重

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-font-weight-normal` | 400 | 正文 |
| `--wolf-font-weight-medium` | 500 | 强调 |
| `--wolf-font-weight-semibold` | 600 | 标题 |

### 3.3 行高

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-line-height-tight` | 1.25 | 紧凑 - 标题 |
| `--wolf-line-height-normal` | 1.5 | 正常 - 正文 |

---

## 四、设计红线

| 规则 | 说明 |
|------|------|
| 禁止纯色填充标签 | 必须用浅底色+同色系文字 |
| 禁用 700+ 字重 | 最大使用 semibold (600) |
| 禁止高饱和色 | 状态色必须低饱和 |
| 禁止多层阴影 | 卡片仅用一级阴影 |
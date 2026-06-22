# CRMWolf 设计快速参考

⚠️ **品牌色唯一来源**：`src/styles/variables.scss`

**所有颜色必须引用 Sass 变量，禁止在代码或文档中硬编码颜色值。**

| 用途 | Sass 变量 |
|------|-----------|
| 品牌主色 | `$wolf-primary` |
| 成功状态 | `$wolf-success-bg` + `$wolf-success-text` |
| 警告状态 | `$wolf-warning-bg` + `$wolf-warning-text` |
| 错误状态 | `$wolf-danger-bg` + `$wolf-danger-text` |
| **AI 消息背景** | `$wolf-bg-ai-message`（← Signature） |

---

## 一、Signature 元素速查

| Signature | 样式 |
|-----------|------|
| AI 消息字体 | `font-family: $wolf-font-mono` |
| AI 消息背景 | `background: $wolf-bg-ai-message` |
| AI 消息边线 | `border-left: 2px solid rgba($wolf-primary, 0.3)` |
| 智能边界线 | 渐变 `linear-gradient(90deg, transparent → rgba($wolf-primary, 0.25) → transparent)` |

---

## 二、圆角速查

| 组件 | 圆角值 |
|------|--------|
| 按钮 | 8px（小按钮 4px） |
| 标签 | 4px |
| 卡片 | 12px |
| 弹窗 | 16px |
| 输入框 | 6px |
| 头像 | full（圆形） |

---

## 二、间距速查

| 场景 | 间距 |
|------|------|
| 页面内边距 | 24px |
| 卡片内边距 | 20px |
| 卡片间距 | 16px |
| 模块间距 | 24px |
| 表单项间距 | 16px |
| 按钮间距 | 12px |

---

## 三、字号速查（已统一）

| 用途 | 字号 | 字重 | 字体 |
|------|------|------|------|
| 页面大标题 | 24px | 600 | IBM Plex Sans |
| 页面标题 | 20px | 600 | IBM Plex Sans |
| 卡片标题 | 16px | 600 | 系统字体栈 |
| 正文 | 14px | 400 | 系统字体栈 |
| **AI 消息** | 14px | 400 | IBM Plex Mono |
| 小字/辅助 | 13px | 400 | 系统字体栈 |
| 标签 | 12px | 400 | 系统字体栈 |

---

## 四、按钮尺寸速查

| 尺寸 | 高度 | Padding |
|------|------|---------|
| 默认 | 32px | 8px 24px |
| 小 | 24px | 4px 8px |

---

## 五、状态码与标签对应

状态标签颜色引用 `variables.scss` 中对应变量：

### 线索状态

| 状态值 | 文字 | 标签色变量 |
|--------|------|------------|
| 0 | 新建 | `$wolf-primary-light` + `$wolf-primary` |
| 1 | 跟进中 | `$wolf-warning-bg` + `$wolf-warning-text` |
| 2 | 已转化 | `$wolf-success-bg` + `$wolf-success-text` |
| 3 | 无效 | `$wolf-danger-bg` + `$wolf-danger-text` |

### 商机状态

| 状态值 | 文字 | 标签色变量 |
|--------|------|------------|
| 0 | 跟进中 | `$wolf-warning-bg` + `$wolf-warning-text` |
| 1 | 已赢单 | `$wolf-success-bg` + `$wolf-success-text` |
| 2 | 已输单 | `$wolf-danger-bg` + `$wolf-danger-text` |

### 合同状态

| 状态值 | 文字 | 标签色变量 |
|--------|------|------------|
| DRAFT | 草稿 | `$wolf-bg-hover` + `$wolf-text-tertiary` |
| PENDING | 待审批 | `$wolf-warning-bg` + `$wolf-warning-text` |
| APPROVED | 已通过 | `$wolf-success-bg` + `$wolf-success-text` |
| REJECTED | 已拒绝 | `$wolf-danger-bg` + `$wolf-danger-text` |

---

## 六、设计红线汇总

| 红线 | 说明 |
|------|------|
| 禁止硬编码颜色 | 必须引用 variables.scss 变量 |
| 禁止纯色标签 | 浅底色+同色系文字 |
| 禁止 700+ 字重 | 最大 600 |
| 禁止竖分割线 | 仅行分割 |
| 禁止斑马纹 | hover 高亮 |
| 禁止魔数间距 | 向 4px 基准网格对齐 |
| **禁止卡片用 Display font** | 卡片标题用系统字体栈 |

---

## 七、间距命名规范（仅语义化）

| 变量 | 值 | 用途 |
|------|-----|------|
| `$wolf-space-xs` | 4px | 元素内间距 |
| `$wolf-space-sm` | 8px | 关联元素间距 |
| `$wolf-space-md` | 16px | 模块内间距 |
| `$wolf-space-lg` | 24px | 模块间间距 |

❌ **废弃**：`$wolf-space-1/2/3/4/5/6/8/10/12`（数字命名已废弃）

---

**颜色详细定义**：`src/styles/variables.scss`
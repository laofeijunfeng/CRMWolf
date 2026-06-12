# CRMWolf 极简中性风 UI 设计规范

> 本规范是 CRMWolf 系统的 UI 设计唯一标准，所有页面必须严格遵循。

---

## 一、核心设计总纲

所有 UI 元素必须严格遵循以下 4 个原则：

1. **极致克制**：全页面 95% 的视觉元素均来自中性色体系，品牌/功能色占比 ≤ 5%，拒绝任何无意义的装饰性设计。
2. **柔和低噪**：全程采用低饱和度、低对比度的色彩与元素，拒绝高饱和硬撞、强对比、厚重装饰。
3. **统一有序**：全页面所有圆角、间距、字号、字重、阴影均使用固定数值，无零散自定义参数。
4. **服务内容**：所有 UI 差异仅用于区分信息层级与交互状态，核心永远是内容本身。

---

## 二、色彩体系

### 2.1 背景色规范（用色彩分层替代分割线）

| 变量名 | 色值 | 适用场景 |
|--------|------|----------|
| `$neutral-bg-page` | `#F9F8F5` | 页面画布底色 |
| `$neutral-bg-card` | `#FFFFFF` | 卡片/模块容器底色 |
| `$neutral-bg-elevated` | `#FAF9F7` | 弹窗/抽屉内容区底色 |
| `$neutral-bg-sidebar` | `#F2F0EB` | 侧边栏/固定导航底色 |
| `$neutral-bg-hover` | `#F5F5F5` | hover 态背景、斑马纹行背景 |
| `$neutral-bg-active` | `#EAEAEA` | active/pressed 态背景 |
| `$neutral-bg-disabled` | `#F5F5F5` | 禁用态背景 |

### 2.2 中性色梯度（全页面 95% 色彩来源）

| 变量名 | 色值 | 对比度 | 适用场景 |
|--------|------|--------|----------|
| `$neutral-text-primary` | `#1C1C1C` | 14:1 | 页面主标题、一级最高优先级信息（≤5%） |
| `$neutral-text-secondary` | `#3A3A3A` | 10:1 | 正文、按钮文字、表格核心信息 |
| `$neutral-text-tertiary` | `#636363` | 5:1 | 辅助信息、未选中导航、标签文字 |
| `$neutral-text-placeholder` | `#909090` | 3:1 | 备注信息、禁用态、图标默认色 |
| `$neutral-text-disabled` | `#C4C4C4` | 1.8:1 | 禁用态文字 |

| 变量名 | 色值 | 适用场景 |
|--------|------|----------|
| `$neutral-border-default` | `#E5E5E5` | 输入框默认边框、控件边框 |
| `$neutral-border-hover` | `#C4C4C4` | hover 态边框 |
| `$neutral-divider` | `#E5E5E5` | 分割线（尽量用留白替代） |

### 2.3 品牌色（极度克制使用）

采用低饱和商务蓝，同一页面内主色填充元素不超过 2 个：

| 变量名 | 色值 | 适用场景 |
|--------|------|----------|
| `$brand-primary` | `#4A6FA5` | 主按钮填充、选中态指示、关键链接 |
| `$brand-hover` | `#4065A0` | 主按钮 hover 态（加深 10%） |
| `$brand-active` | `#365A95` | 主按钮 active 态（加深 15%） |
| `$brand-light` | `rgba(#4A6FA5, 0.1)` | 选中态背景、品牌色浅底 |
| `$brand-disabled` | `rgba(#4A6FA5, 0.3)` | 禁用态 |

### 2.4 功能色（仅用于状态标签）

功能色必须搭配「浅底色 + 同色系文字」使用，禁止纯色填充：

| 状态 | 文字色 | 背景色 | 适用场景 |
|------|--------|--------|----------|
| 成功 | `$status-success-text: #2B633C` | `$status-success-bg: #EDF7EF` | 成功提示、允许状态 |
| 警告 | `$status-warning-text: #7A4F1E` | `$status-warning-bg: #FFF6E8` | 警告提示、待处理 |
| 危险 | `$status-danger-text: #7A2828` | `$status-danger-bg: #FCECEC` | 错误提示、危险操作 |

---

## 三、字体规范

### 3.1 字体家族

```scss
$font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
```

### 3.2 字号与字重（全页面仅 5 种组合）

| 变量名 | 字号 | 字重 | 色值 | 适用场景 |
|--------|------|------|------|----------|
| `$font-size-title` | 16px | 600 | `#1C1C1C` | 页面主标题、弹窗标题 |
| `$font-size-body` | 14px | 400/500 | `#3A3A3A` | 正文、按钮、表格内容 |
| `$font-size-auxiliary` | 13px | 400 | `#636363` | 辅助信息、标签、下拉选项 |
| `$font-size-caption` | 12px | 400 | `#909090` | 次要备注、时间戳 |

### 3.3 行高

| 变量名 | 行高 | 适用场景 |
|--------|------|----------|
| `$line-height-title` | 1.2 | 标题 |
| `$line-height-body` | 1.5 | 正文 |
| `$line-height-auxiliary` | 1.4 | 辅助文字 |

---

## 四、圆角规范

全页面仅 4 个固定数值：

| 变量名 | 圆角 | 适用元素 |
|--------|------|----------|
| `$radius-sm` | 4px | 按钮、标签、输入框、开关 |
| `$radius-md` | 8px | 卡片、表格、下拉面板 |
| `$radius-lg` | 12px | 弹窗、对话框 |
| `$radius-xl` | 16px | 页面级大容器（极少使用） |

---

## 五、间距规范

所有间距均为 8px 的倍数：

| 变量名 | 间距 | 适用场景 |
|--------|------|----------|
| `$space-xs` | 4px | 元素内间距（图标与文字） |
| `$space-sm` | 8px | 关联元素间距 |
| `$space-md` | 16px | 模块内间距（卡片内边距） |
| `$space-lg` | 24px | 模块间间距、页面安全边距 |

---

## 六、阴影规范

仅 2 种固定阴影，极淡极柔：

| 变量名 | 参数 | 适用场景 |
|--------|------|----------|
| `$shadow-card` | `0 2px 8px rgba(0, 0, 0, 0.04)` | 卡片、下拉面板 |
| `$shadow-modal` | `0 4px 16px rgba(0, 0, 0, 0.08)` | 弹窗、对话框 |

---

## 七、按钮规范

### 7.1 尺寸（全页面仅 2 种）

| 尺寸 | 高度 | 内边距 | 圆角 | 适用场景 |
|------|------|--------|------|----------|
| 迷你型（主用） | 24px | 12px 4px | 4px | 页面内绝大多数操作 |
| 常规型 | 32px | 16px 6px | 6px | 弹窗操作、表单提交 |

### 7.2 类型（全页面仅 3 种）

| 类型 | 默认样式 | 适用场景 |
|------|----------|----------|
| 主按钮 | 品牌色填充，白色文字 | 页面核心操作（≤2个） |
| 次按钮 | `#F5F5F5` 背景，`#3A3A3A` 文字 | 辅助操作（主用） |
| 文字按钮 | 无背景，深灰文字 | 次要操作、取消返回 |

---

## 八、控件规范

| 控件 | 尺寸 | 样式 |
|------|------|------|
| 输入框 | 高 32px，圆角 4px | 白背景，`#E5E5E5` 边框，聚焦态边框变品牌色 |
| 下拉选择器 | 高 24px/32px | 浅灰背景 `#F5F5F5`，无边框 |
| 开关 | 宽 40px，高 22px | 关闭：`#E5E5E5`；开启：`#5B5B5B` |
| 单选/复选框 | 16×16px | 未选中：`#C4C4C4` 边框；选中：品牌色填充 |

---

## 九、图标规范

- **样式**：仅用线性图标，线条粗细 2px，圆角 2px
- **尺寸**：12px、14px、16px（与文字字号匹配）
- **色彩**：默认 `#909090`，hover/选中 `#3A3A3A`，禁用 `#C4C4C4`

---

## 十、红线禁用规范

| 序号 | 禁用项 | 替代方案 |
|------|--------|----------|
| 1 | 纯黑 `#000000`、纯白 `#FFFFFF` 作为背景或正文 | 使用 `#1C1C1C`、`#F9F8F5` |
| 2 | 高饱和度色彩、大面积品牌色 | 使用低饱和色，品牌色 ≤ 5% |
| 3 | 700+ 粗体、12px 以下字号 | 最高字重 600，最小字号 12px |
| 4 | 按钮/控件重描边、渐变、装饰阴影 | 使用规范中的轻量化样式 |
| 5 | 直角元素、超大圆角 | 使用 4px/8px/12px/16px 圆角 |
| 6 | 面性图标、彩色图标 | 使用线性图标，中性色 |
| 7 | 大量分割线 | 用留白替代分割线 |
| 8 | 装饰性动效、超过 0.3s 动效 | 仅状态切换，时长 0.2s |

---

## 十一、组件样式速查

### 按钮

```scss
// 主按钮
.btn-primary {
  background: $brand-primary;
  color: #FFFFFF;
  border-radius: $radius-sm;
  &:hover { background: $brand-hover; }
  &:active { background: $brand-active; }
  &:disabled { background: $brand-disabled; color: rgba(#FFFFFF, 0.5); }
}

// 次按钮（主用）
.btn-secondary {
  background: $neutral-bg-hover;
  color: $neutral-text-secondary;
  border-radius: $radius-sm;
  &:hover { background: $neutral-bg-active; }
}

// 文字按钮
.btn-text {
  background: transparent;
  color: $neutral-text-secondary;
  &:hover { background: $neutral-bg-hover; }
}
```

### 状态标签

```scss
// 成功状态
.tag-success {
  background: $status-success-bg;
  color: $status-success-text;
  border-radius: $radius-sm;
  padding: 4px 8px;
}

// 警告状态
.tag-warning {
  background: $status-warning-bg;
  color: $status-warning-text;
}

// 危险状态
.tag-danger {
  background: $status-danger-bg;
  color: $status-danger-text;
}
```

### 卡片

```scss
.card {
  background: $neutral-bg-card;
  border-radius: $radius-md;
  box-shadow: $shadow-card;
  padding: $space-md;
}
```

### 输入框

```scss
.input {
  height: 32px;
  border-radius: $radius-sm;
  border: 1px solid $neutral-border-default;
  background: #FFFFFF;
  
  &:hover { border-color: $neutral-border-hover; }
  &:focus { border-color: $brand-primary; outline: none; }
}
```
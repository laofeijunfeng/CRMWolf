# CRMWolf 组件规范

⚠️ **品牌色唯一来源**：`src/styles/variables.scss`

**所有颜色必须引用 Sass 变量，禁止硬编码。**

---

## 一、按钮规范

### 1.1 按钮类型

| 类型 | 样式 | 用途 |
|------|------|------|
| 主按钮 | `$wolf-primary` 品牌色填充 | 页面核心操作 |
| 次按钮 | `$wolf-bg-hover` 浅灰背景 | 辅助操作 |
| 文本按钮 | 无背景 | 弱操作、取消 |
| 危险按钮 | `$wolf-danger-text` 红色文字 | 删除、危险操作 |

### 1.2 按钮尺寸

| 尺寸 | 高度 | Padding | 用途 |
|------|------|---------|------|
| 默认 | 32px | 8px 24px | 页面操作 |
| 小 | 24px | 4px 8px | 表格操作 |

### 1.3 按钮结构规范

```css
/* 按钮基础结构（颜色引用 variables.scss） */
.wolf-btn {
  height: 32px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 400;
}

.wolf-btn-primary {
  background: $wolf-primary;
  color: $wolf-text-inverse;
}

.wolf-btn-default {
  background: $wolf-bg-hover;
  color: $wolf-text-secondary;
}

.wolf-btn-text {
  background: transparent;
  color: $wolf-text-tertiary;
}

.wolf-btn-danger {
  color: $wolf-danger-text;
}
```

---

## 二、标签规范

### 2.1 标签样式规则

**红线：禁止纯色填充，必须用浅底色+同色系文字**

### 2.2 状态标签颜色引用

| 状态 | Sass 变量组合 |
|------|---------------|
| 成功 | `background: $wolf-success-bg; color: $wolf-success-text` |
| 警告 | `background: $wolf-warning-bg; color: $wolf-warning-text` |
| 错误 | `background: $wolf-danger-bg; color: $wolf-danger-text` |
| 信息 | `background: $wolf-primary-light; color: $wolf-primary` |
| 默认 | `background: $wolf-bg-hover; color: $wolf-text-tertiary` |

### 2.3 标签尺寸

```css
.wolf-tag {
  height: 22px;
  padding: 0 8px;
  font-size: 12px;
  border-radius: 4px;
}
```

---

## 三、卡片规范

### 3.1 标准卡片

```css
.wolf-card {
  background: $wolf-bg-card;       /* #FFFFFF */
  border-radius: 12px;
  box-shadow: $wolf-shadow-card;   /* 0 1px 2px rgba(0,0,0,0.04) */
  padding: 20px;
}
```

### 3.2 卡片头部

```css
.wolf-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.wolf-card__title {
  font-size: 16px;
  font-weight: 600;
  color: $wolf-text-primary;
}
```

---

## 四、输入框规范

### 4.1 输入框样式

```css
.el-input__wrapper {
  height: 28px;
  border-radius: 6px;
  background: $wolf-bg-hover;
  border: none;
}
```

### 4.2 下拉框样式

与输入框完全统一：28px 高度，6px 圆角，无边框。

---

## 五、弹窗规范

### 5.1 弹窗尺寸

| 类型 | 宽度 | 用途 |
|------|------|------|
| 小 | 400px | 确认、简单表单 |
| 中 | 600px | 标准表单 |
| 大 | 800px | 复杂内容 |

### 5.2 弹窗样式

```css
.el-dialog {
  border-radius: 16px;
  box-shadow: $wolf-shadow-modal;  /* 0 16px 48px rgba(0,0,0,0.16) */
}
```

---

## 六、描述列表规范

用于详情页信息展示：

```vue
<el-descriptions :column="2" border>
  <el-descriptions-item label="客户名称">...</el-descriptions-item>
</el-descriptions>
```

标签宽度：120px，文字右对齐。

---

## 七、时间轴规范

用于审批流程、跟进记录：

- 节点：圆形图标，16px 直径
- 线条：2px 宽度，灰色
- 内容：卡片样式，12px 圆角

---

## 八、Tab 切换规范

```css
.el-tabs__item {
  font-size: 14px;
  color: $wolf-text-tertiary;
}

.el-tabs__item:hover {
  color: $wolf-text-secondary;
}

.el-tabs__item.is-active {
  color: $wolf-text-primary;
  font-weight: 500;
}
```

---

**颜色详细定义**：`src/styles/variables.scss`
# CRMWolf 组件规范

**适用范围**：前端组件开发必读

---

## 一、按钮规范

### 1.1 按钮类型

| 类型 | 样式 | 用途 |
|------|------|------|
| 主按钮 | 品牌色填充 | 页面核心操作 |
| 次按钮 | 浅灰背景 | 辅助操作 |
| 文本按钮 | 无背景 | 弱操作、取消 |
| 危险按钮 | 红色文字 | 删除、危险操作 |

### 1.2 按钮尺寸

| 尺寸 | 高度 | Padding | 用途 |
|------|------|---------|------|
| 默认 | 32px | 8px 24px | 页面操作 |
| 小 | 24px | 4px 8px | 表格操作 |

### 1.3 按钮样式

```css
/* 主按钮 */
.wolf-btn-primary {
  background: #165DFF;
  color: #FFFFFF;
  border-radius: 8px;
  height: 32px;
}

/* 次按钮 */
.wolf-btn-default {
  background: #F7F7F5;
  color: #3A3A3A;
  border-radius: 8px;
}

/* 文本按钮 */
.wolf-btn-text {
  background: transparent;
  color: #636363;
  &:hover { background: #F5F5F3; }
}

/* 危险按钮 */
.wolf-btn-danger {
  color: #A83232;
  &:hover { background: #FCECEC; }
}
```

---

## 二、标签规范

### 2.1 标签样式规则

**红线：禁止纯色填充，必须用浅底色+同色系文字**

### 2.2 状态标签颜色

| 状态 | 背景色 | 文字色 | 示例 |
|------|--------|--------|------|
| 成功 | #EDF7EF | #2B633C | 已完成、赢单 |
| 警告 | #FFF6E8 | #7A4F1E | 待处理、跟进中 |
| 错误 | #FCECEC | #7A2828 | 已拒绝、输单 |
| 信息 | #E8F3FF | #165DFF | 进行中 |
| 默认 | #F5F5F3 | #636363 | 无状态 |

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
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
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
  color: #1D2129;
}
```

---

## 四、输入框规范

### 4.1 输入框样式

```css
.el-input__wrapper {
  height: 28px;
  border-radius: 6px;
  background: #F5F5F3;
  border: none;
  &:hover { background: #F0F0ED; }
  &:focus { background: #EFEFED; }
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
  box-shadow: 0 16px 48px rgba(0,0,0,0.16);
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
  color: #86909C;
  &:hover { color: #4E5969; }
  &.is-active { color: #1D2129; font-weight: 500; }
}
```
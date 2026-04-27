# CRMWolf 表格规范

**适用范围**：前端列表页开发必读

---

## 一、表格设计原则

**极简中性风**：无竖分割线、自适应行高、柔和色差、内容优先

### 红线规则

| 规则 | 说明 |
|------|------|
| 禁止竖分割线 | 仅保留行分割线 |
| 禁止斑马纹 | 用 hover 高亮代替 |
| 禁止高对比背景 | 表头用浅灰 #F5F5F3 |
| 禁止固定行高 | 最小 44px，允许换行 |

---

## 二、表头规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 高度 | 44px | 固定高度 |
| 背景 | #F5F5F3 | 浅灰，比页面深半色阶 |
| 字号 | 13px | 较小，不抢眼 |
| 字重 | 500 | 仅用此区分 |
| 文字色 | #3A3A3A | 次级文字色 |
| 边框 | 1px solid #F0F0ED | 表头底部分割线 |

---

## 三、内容行规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 最小高度 | 44px | 支撑舒适点击区 |
| 背景 | #FFFFFF | 纯白 |
| Hover 背景 | #F0F0ED | 极淡暖灰 |
| 字号 | 14px | 正文标准 |
| 文字色 | #3A3A3A | 正文色 |
| 行高 | 1.5 | 支持换行 |
| 边框 | 1px solid #F2F2F0 | 行分割线（极淡） |

---

## 四、列内容显示规则

| 列类型 | 显示规则 | 说明 |
|--------|----------|------|
| 核心信息 | 单行省略 | 名称、标题等，max-width + ellipsis |
| 长文本 | 允许换行（最多2行） | 备注、描述等 |
| 状态 | 标签样式 | 浅底色+同色系文字 |
| 数字 | 右对齐 | 金额、数量 |
| 操作 | 固定右侧 | 链接样式按钮 |

---

## 五、CSS 变量定义

```scss
$wolf-table-row-height: 44px;
$wolf-table-header-height: 44px;
$wolf-table-cell-padding-y: 12px;
$wolf-table-cell-padding-x: 8px;
$wolf-table-header-bg: #F5F5F3;
$wolf-table-header-text: #3A3A3A;
$wolf-table-header-font-size: 13px;
$wolf-table-header-font-weight: 500;
$wolf-table-border-color: #F2F2F0;
$wolf-table-hover-bg: #F0F0ED;
$wolf-table-cell-font-size: 14px;
$wolf-table-cell-text: #3A3A3A;
$wolf-table-line-height: 1.5;
```

---

## 六、固定列规范

操作列固定右侧时：

```scss
// 固定列必须有实色背景
.el-table__fixed-right {
  z-index: 20;
}

.el-table td.el-table-fixed-column--right {
  background-color: #FFFFFF !important;
}

// hover 时继承行背景
.el-table .el-table__body tr:hover td.el-table-fixed-column--right {
  background-color: #F0F0ED !important;
}
```

---

## 七、操作列规范

### 7.1 操作按钮样式

```scss
.action-link {
  color: $wolf-text-link;       // #4A6FA5
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  &:hover { color: $wolf-text-link-hover; }
}

.action-danger {
  color: $wolf-danger-text;     // #7A2828
  &:hover { color: #A83232; }
}
```

### 7.2 操作列宽度参考

| 操作数量 | 宽度 |
|----------|------|
| 1-2 个 | 100px |
| 3-4 个 | 160px |
| 5-6 个 | 220px |

---

## 八、分页规范

```scss
.pagination-bar {
  display: flex;
  justify-content: space-between;
  padding: 16px;
}

.total-text {
  font-size: 13px;
  color: #86909C;
}
```
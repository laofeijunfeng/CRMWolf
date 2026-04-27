# CRMWolf 间距、圆角、阴影与布局规范

**适用范围**：前端 UI 开发必读

---

## 一、间距系统（4px 倍数）

### 1.1 基础间距

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-space-1` | 4px | 元素内间距 |
| `--wolf-space-2` | 8px | 关联元素间距 |
| `--wolf-space-3` | 12px | 小模块间距 |
| `--wolf-space-4` | 16px | 模块内间距 |
| `--wolf-space-6` | 24px | 模块间间距 |
| `--wolf-space-8` | 32px | 大模块间距 |

### 1.2 页面间距

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-page-padding` | 24px | 页面内边距 |
| `--wolf-page-max-width` | 1400px | 页面最大宽度 |
| `--wolf-section-gap` | 24px | 区块间距 |
| `--wolf-card-gap` | 16px | 卡片间距 |
| `--wolf-card-padding` | 20px | 卡片内边距 |

### 1.3 组件间距

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-form-item-gap` | 16px | 表单项间距 |
| `--wolf-button-gap` | 12px | 按钮间距 |
| `--wolf-header-height` | 56px | 顶部导航栏高度 |
| `--wolf-sidebar-width` | 220px | 侧边栏宽度 |

---

## 二、圆角系统

### 2.1 基础圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-radius-sm` | 4px | 按钮、标签、输入框 |
| `--wolf-radius-md` | 8px | 输入框、小卡片 |
| `--wolf-radius-lg` | 12px | 卡片（标准） |
| `--wolf-radius-xl` | 16px | 大卡片、弹窗 |
| `--wolf-radius-full` | 9999px | 头像、胶囊按钮 |

### 2.2 圆角使用规范

| 组件 | 圆角 | 说明 |
|------|------|------|
| 按钮（默认） | 8px | 标准按钮 |
| 按钮（小） | 4px | 表格操作按钮 |
| 标签 | 4px | 状态标签 |
| 卡片 | 12px | 标准卡片 |
| 弹窗 | 16px | 对话框 |
| 头像 | full | 圆形 |

---

## 三、阴影系统

### 3.1 基础阴影

| Token | 值 | 用途 |
|-------|-----|------|
| `--wolf-shadow-card` | 0 1px 2px rgba(0,0,0,0.04), 0 2px 4px rgba(0,0,0,0.02) | 静态卡片 |
| `--wolf-shadow-hover` | 0 4px 12px rgba(0,0,0,0.08) | 悬停状态 |
| `--wolf-shadow-dropdown` | 0 8px 24px rgba(0,0,0,0.12) | 下拉菜单 |
| `--wolf-shadow-modal` | 0 16px 48px rgba(0,0,0,0.16) | 弹窗、抽屉 |
| `--wolf-shadow-bottom` | 0 -2px 8px rgba(0,0,0,0.05) | 底部固定栏 |

### 3.2 阴影层级

| 层级 | 阴影 | 使用场景 |
|------|------|----------|
| Level 1 | card | 静态卡片 |
| Level 2 | hover | 悬停状态 |
| Level 3 | dropdown | 下拉菜单 |
| Level 4 | modal | 弹窗、抽屉 |

---

## 四、头像尺寸

| 尺寸 | Token | 值 | 用途 | 字体大小 |
|------|-------|-----|------|----------|
| 超小 | `--wolf-avatar-xs` | 24px | 评论、嵌套回复 | 12px |
| 小 | `--wolf-avatar-sm` | 32px | 列表、表格 | 16px |
| 中 | `--wolf-avatar-md` | 48px | 卡片标题、详情页 | 24px |
| 大 | `--wolf-avatar-lg` | 64px | 个人资料页 | 32px |

---

## 五、布局系统

### 5.1 标准页面结构

```vue
<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1 class="page-title">页面标题</h1>
      <div class="page-actions">
        <el-button type="primary">主要操作</el-button>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="content-area">
      <div class="wolf-card">...</div>
    </div>
  </div>
</template>
```

### 5.2 页面头部规范

- 标题：20px 字号，600 字重，primary 文字色
- 描述：14px 字号，400 字重，tertiary 文字色
- 底部间距：24px（与内容区）
- 操作按钮区：右侧对齐
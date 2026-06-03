# CRMWolf 设计规范 V2.0

> **注意**：此文件已拆分为多个小文件便于 AI 读取，推荐使用：
> - `DESIGN-PRINCIPLES.md` - 设计原则、色彩、字体
> - `DESIGN-SPACING.md` - 间距、圆角、阴影、布局
> - `DESIGN-COMPONENTS.md` - 按钮、标签、卡片等组件
> - `DESIGN-TABLE.md` - 表格规范
> - `DESIGN-QUICK-REF.md` - 快速参考
>
> 本文件保留作为完整参考备份。

## 基于 Element Plus 的现代简约设计体系

***

## 一、设计原则

### 1.1 核心原则

- **简约至上**：去除多余装饰，保留核心信息
- **层次分明**：浅灰背景 + 白色卡片建立清晰层级
- **轻量高效**：柔和阴影、细腻圆角、流畅动效
- **一致统一**：全系统使用同一套设计 token
- **信息密度**：在保证可读性的前提下，提高信息密度

### 1.2 命名空间

所有 CSS 类名使用 `wolf-` 前缀，避免与其他样式冲突：

```css
.wolf-card      /* 卡片 */
.wolf-tag       /* 标签 */
.wolf-btn       /* 按钮 */
.wolf-table     /* 表格 */
.wolf-layout    /* 布局 */
```

***

## 二、色彩系统（CRMWolf 品牌色）

### 2.1 页面背景

```css
--wolf-bg-page: #F5F7FA;           /* 页面背景 - 浅灰蓝 */
--wolf-bg-card: #FFFFFF;            /* 卡片背景 - 纯白 */
--wolf-bg-hover: #F7F8FA;           /* 悬停背景 */
--wolf-bg-active: #F2F3F5;          /* 激活/选中背景 */
--wolf-bg-sidebar: #1A1F2E;         /* 侧边栏背景 */
--wolf-bg-mask: rgba(0, 0, 0, 0.45); /* 遮罩层背景 */
```

### 2.2 品牌主色（Wolf Blue）

```css
--wolf-primary: #165DFF;            /* 主蓝色 - 按钮、链接 */
--wolf-primary-hover: #0E42D2;      /* 主蓝悬停 */
--wolf-primary-active: #0B36B0;     /* 主蓝按下 */
--wolf-primary-light: #E8F3FF;      /* 主蓝浅背景 */
--wolf-primary-gradient: linear-gradient(135deg, #165DFF 0%, #0E42D2 100%);
```

### 2.3 状态色（带背景）

```css
/* 成功/活跃 - 绿色 */
--wolf-success: #00B42A;
--wolf-success-hover: #009A24;
--wolf-success-bg: #E8FFEA;
--wolf-success-border: #86EFAC;

/* 警告/VIP - 橙色 */
--wolf-warning: #FF7D00;
--wolf-warning-hover: #E56F00;
--wolf-warning-bg: #FFF7E8;
--wolf-warning-border: #FCD34D;

/* 错误/删除 - 红色 */
--wolf-danger: #F53F3F;
--wolf-danger-hover: #D93636;
--wolf-danger-bg: #FFECE8;
--wolf-danger-border: #FCA5A5;

/* 信息/进行中 - 蓝色 */
--wolf-info: #165DFF;
--wolf-info-hover: #0E42D2;
--wolf-info-bg: #E8F3FF;
--wolf-info-border: #93C5FD;

/* 紫色 - 复购率等特殊指标 */
--wolf-purple: #722ED1;
--wolf-purple-hover: #6025B0;
--wolf-purple-bg: #F5E8FF;
--wolf-purple-border: #D8B4FE;

/* 灰色 - 默认/无状态 */
--wolf-gray: #86909C;
--wolf-gray-hover: #6B7785;
--wolf-gray-bg: #F2F3F5;
--wolf-gray-border: #E5E6EB;
```

### 2.4 文字色

```css
--wolf-text-primary: #1D2129;       /* 主要文字 - 标题 */
--wolf-text-secondary: #4E5969;     /* 次要文字 - 正文 */
--wolf-text-tertiary: #86909C;      /* 辅助文字 - 标签 */
--wolf-text-placeholder: #C9CDD4;   /* 占位符文字 */
--wolf-text-disabled: #C9CDD4;      /* 禁用文字 */
--wolf-text-link: #165DFF;          /* 链接文字 */
--wolf-text-link-hover: #0E42D2;    /* 链接悬停 */
--wolf-text-inverse: #FFFFFF;       /* 反色文字（深色背景上） */
```

### 2.5 边框色

```css
--wolf-border-color: #E5E6EB;       /* 边框 */
--wolf-border-light: #F2F3F5;       /* 浅色边框 */
--wolf-border-divider: #E5E6EB;     /* 分割线 */
--wolf-border-focus: #165DFF;       /* 聚焦边框 */
```

***

## 三、字体系统

```css
--wolf-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
--wolf-font-mono: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", monospace;

/* 字号层级 */
--wolf-font-size-display: 24px;      /* 页面大标题 */
--wolf-font-size-title: 20px;        /* 页面标题 */
--wolf-font-size-card-title: 16px;   /* 卡片标题 */
--wolf-font-size-subtitle: 15px;     /* 小标题 */
--wolf-font-size-body: 14px;         /* 正文 */
--wolf-font-size-small: 13px;        /* 小字 */
--wolf-font-size-label: 12px;        /* 标签/辅助文字 */
--wolf-font-size-caption: 11px;      /* 最小文字 */

/* 字重 */
--wolf-font-weight-normal: 400;
--wolf-font-weight-medium: 500;
--wolf-font-weight-semibold: 600;
--wolf-font-weight-bold: 700;

/* 行高 */
--wolf-line-height-tight: 1.25;      /* 紧凑 */
--wolf-line-height-normal: 1.5;      /* 正常 */
--wolf-line-height-relaxed: 1.75;    /* 宽松 */
```

***

## 四、间距系统

### 4.1 基础间距（4px 倍数）

```css
--wolf-space-0: 0px;
--wolf-space-1: 4px;
--wolf-space-2: 8px;
--wolf-space-3: 12px;
--wolf-space-4: 16px;
--wolf-space-5: 20px;
--wolf-space-6: 24px;
--wolf-space-8: 32px;
--wolf-space-10: 40px;
--wolf-space-12: 48px;
```

### 4.2 页面间距

```css
--wolf-page-padding: 24px;           /* 页面内边距 */
--wolf-page-max-width: 1400px;       /* 页面最大宽度 */
--wolf-section-gap: 24px;            /* 区块间距 */
--wolf-card-gap: 16px;               /* 卡片间距 */
--wolf-card-padding: 20px;           /* 卡片内边距 */
--wolf-card-padding-sm: 16px;        /* 小卡片内边距 */
--wolf-card-padding-xs: 12px;        /* 超小卡片内边距 */
```

### 4.3 组件间距

```css
--wolf-form-item-gap: 16px;          /* 表单项间距 */
--wolf-form-label-gap: 8px;          /* 表单标签与输入框间距 */
--wolf-button-gap: 12px;             /* 按钮间距 */
--wolf-list-item-gap: 8px;           /* 列表项间距 */
--wolf-table-row-height: 56px;       /* 表格行高 */
--wolf-table-row-height-sm: 48px;    /* 小表格行高 */
--wolf-header-height: 56px;          /* 顶部导航栏高度 */
--wolf-sidebar-width: 220px;         /* 侧边栏宽度 */
```

***

## 五、圆角系统

### 5.1 基础圆角

```css
--wolf-radius-none: 0px;             /* 无圆角 */
--wolf-radius-sm: 4px;               /* 小圆角 - 按钮、标签、输入框 */
--wolf-radius-md: 8px;               /* 中圆角 - 输入框、小卡片 */
--wolf-radius-lg: 12px;              /* 大圆角 - 卡片（关键！） */
--wolf-radius-xl: 16px;              /* 超大圆角 - 大卡片、弹窗 */
--wolf-radius-2xl: 20px;             /* 2倍大圆角 - 特殊卡片 */
--wolf-radius-full: 9999px;          /* 圆形 - 头像、胶囊 */
```

### 5.2 圆角使用规范

| 组件     | 圆角值                       | 说明     |
| ------ | ------------------------- | ------ |
| 按钮（默认） | `--wolf-radius-md` (8px)  | 标准按钮   |
| 按钮（小）  | `--wolf-radius-sm` (4px)  | 表格操作按钮 |
| 标签     | `--wolf-radius-sm` (4px)  | 状态标签   |
| 卡片     | `--wolf-radius-lg` (12px) | 标准卡片   |
| 大卡片    | `--wolf-radius-xl` (16px) | 统计卡片   |
| 输入框    | `--wolf-radius-md` (8px)  | 表单输入   |
| 弹窗     | `--wolf-radius-xl` (16px) | 对话框    |
| 头像     | `--wolf-radius-full`      | 圆形头像   |
| 胶囊按钮   | `--wolf-radius-full`      | 筛选器    |

### 5.3 头像尺寸规范

```css
/* 头像尺寸 */
--wolf-avatar-xs: 24px;              /* 超小头像 - 评论、嵌套回复 */
--wolf-avatar-sm: 32px;              /* 小头像 - 列表、表格中的头像 */
--wolf-avatar-md: 48px;              /* 中头像 - 卡片标题、详情页 */
--wolf-avatar-lg: 64px;              /* 大头像 - 个人资料页 */
--wolf-avatar-xl: 96px;              /* 超大头像 - 独立头像展示 */
```

#### 头像使用场景

| 尺寸     | 变量                        | 用途            | 字体大小 |
| ------ | ------------------------- | ------------- | ---- |
| **超小** | `--wolf-avatar-xs` (24px) | 评论、嵌套回复       | 12px |
| **小**  | `--wolf-avatar-sm` (32px) | 列表、表格中的头像     | 16px |
| **中**  | `--wolf-avatar-md` (48px) | 卡片标题、详情页（推荐）✅ | 24px |
| **大**  | `--wolf-avatar-lg` (64px) | 个人资料页         | 32px |
| **超大** | `--wolf-avatar-xl` (96px) | 独立头像展示        | 48px |

#### 头像样式规范

```css
.wolf-avatar {
  border-radius: var(--wolf-radius-full);      /* 圆形 */
  background: var(--wolf-primary-active);       /* 深蓝色背景 */
  color: var(--wolf-text-inverse);              /* 白色文字 */
  display: flex;                                 /* Flex 布局 */
  align-items: center;                           /* 垂直居中 */
  justify-content: center;                       /* 水平居中 */
  font-weight: var(--wolf-font-weight-bold);     /* 粗体 */
  box-shadow: var(--wolf-shadow-float);          /* 浮动阴影 */
}
```

#### 头像字体大小

字体大小应为头像尺寸的 **1/2**，确保视觉协调：

```css
.wolf-avatar--xs {
  width: var(--wolf-avatar-xs);     /* 24px */
  height: var(--wolf-avatar-xs);
  font-size: 12px;                   /* 24px × 0.5 */
}

.wolf-avatar--sm {
  width: var(--wolf-avatar-sm);     /* 32px */
  height: var(--wolf-avatar-sm);
  font-size: 16px;                   /* 32px × 0.5 */
}

.wolf-avatar--md {
  width: var(--wolf-avatar-md);     /* 48px */
  height: var(--wolf-avatar-md);
  font-size: 24px;                   /* 48px × 0.5 */
}

.wolf-avatar--lg {
  width: var(--wolf-avatar-lg);     /* 64px */
  height: var(--wolf-avatar-lg);
  font-size: 32px;                   /* 64px × 0.5 */
}

.wolf-avatar--xl {
  width: var(--wolf-avatar-xl);     /* 96px */
  height: var(--wolf-avatar-xl);
  font-size: 48px;                   /* 96px × 0.5 */
}
```

**示例**：

```vue
<template>
  <!-- 中等尺寸头像（推荐用于详情页） -->
  <div class="wolf-avatar wolf-avatar--md">
    {{ userName.charAt(0) }}
  </div>
</template>
```

***

## 六、阴影系统

### 6.1 基础阴影

```css
/* 卡片阴影 - 超柔和 */
--wolf-shadow-card: 0 1px 2px rgba(0, 0, 0, 0.04), 
                    0 2px 4px rgba(0, 0, 0, 0.02);

/* 卡片悬停阴影 */
--wolf-shadow-hover: 0 4px 12px rgba(0, 0, 0, 0.08), 
                     0 2px 4px rgba(0, 0, 0, 0.04);

/* 底部操作栏阴影 */
--wolf-shadow-bottom: 0 -2px 8px rgba(0, 0, 0, 0.05);

/* 下拉阴影 */
--wolf-shadow-dropdown: 0 8px 24px rgba(0, 0, 0, 0.12);

/* 弹窗阴影 */
--wolf-shadow-modal: 0 16px 48px rgba(0, 0, 0, 0.16);

/* 悬浮按钮阴影 */
--wolf-shadow-float: 0 4px 12px rgba(22, 93, 255, 0.25);
```

### 6.2 阴影层级

| 层级      | 阴影                       | 使用场景         |
| ------- | ------------------------ | ------------ |
| Level 1 | `--wolf-shadow-card`     | 静态卡片         |
| Level 2 | `--wolf-shadow-hover`    | 悬停状态         |
| Level 3 | `--wolf-shadow-dropdown` | 下拉菜单、Popover |
| Level 4 | `--wolf-shadow-modal`    | 弹窗、抽屉        |
| Level 5 | `--wolf-shadow-bottom`   | 底部固定栏        |

***

## 七、布局系统

### 7.1 页面布局

```vue
<template>
  <!-- 标准页面布局 -->
  <div class="wolf-page">
    <!-- 顶部导航栏 -->
    <header class="wolf-page-header">
      <div class="wolf-page-header__left">...</div>
      <div class="wolf-page-header__right">...</div>
    </header>
    
    <!-- 页面内容区 -->
    <main class="wolf-page__content">
      <!-- 内容区域 -->
    </main>
  </div>
</template>

<style>
/* 页面容器 */
.wolf-page {
  padding: 0;
  background: var(--wolf-bg-page);
  min-height: calc(100vh - 48px);
}

/* 页面内容区 */
.wolf-page__content {
  max-width: var(--wolf-page-max-width);
  margin: 0 auto;
  padding: var(--wolf-page-padding);
}

/* 顶部导航栏 */
.wolf-page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--wolf-bg-card);
  border-bottom: 1px solid var(--wolf-border-color);
  height: var(--wolf-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--wolf-page-padding);
  margin: 0;
}

.wolf-page-header__left,
.wolf-page-header__right {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-3);
}

.wolf-page-header__left {
  flex: 1;
  min-width: 0;
}

.wolf-page-header__right {
  flex-shrink: 0;
}
</style>
```

#### 7.1.1 页面头部规范（page-header 简化）

**设计原则：**

- **去除冗余**：页面标题已在左侧导航栏显示，无需重复
- **场景区分**：列表页无 page-header，详情页/表单页仅保留返回按钮
- **操作内聚**：列表页操作按钮整合到筛选区右侧

**页面分类规范：**

| 页面类型 | page-header | 说明 |
|---------|-------------|------|
| **列表页** | ❌ 不需要 | 标题在侧边栏已显示，操作按钮移至筛选区 |
| **详情页** | ✅ 仅返回按钮 | 返回按钮 + 标题，右侧操作按钮 |
| **表单页** | ✅ 仅返回按钮 | 返回按钮 + 标题，保存/取消按钮在表单底部 |

**列表页结构（无 page-header）：**

```vue
<template>
  <div class="list-container">
    <!-- 筛选区：搜索 + 状态筛选 + 操作按钮 -->
    <div class="wolf-card search-card">
      <el-form :inline="true">
        <el-form-item>
          <el-input v-model="searchText" placeholder="搜索..." />
        </el-form-item>
        <el-form-item>
          <el-select v-model="status" placeholder="状态筛选" />
        </el-form-item>
        <!-- 操作按钮放在筛选区右侧 -->
        <el-form-item style="margin-left: auto">
          <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            新建
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 表格区 -->
    <div class="wolf-card table-card">
      <el-table :data="tableData">...</el-table>
    </div>
  </div>
</template>
```

**详情页/表单页结构（sticky page-header）：**

> ⚠️ **重要**：详情页采用 sticky header 设计，确保滚动时头部固定，内容区撑满页面宽度。

```vue
<template>
  <div class="detail-page">
    <!-- sticky 页面头部：返回按钮 + 标题 + 操作按钮 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">{{ pageTitle }}</h1>
      </div>
      <div class="page-header-right">
        <el-button type="primary" size="small" @click="handleEdit">编辑</el-button>
      </div>
    </div>

    <!-- 内容区：撑满页面宽度 -->
    <div v-loading="loading" class="detail-content">
      <!-- 信息卡片 -->
      <div class="info-card">...</div>
      <!-- 其他卡片 -->
      <div class="tabs-card">...</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

// 详情页容器
.detail-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// sticky 页面头部（关键样式）
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.page-header-left,
.page-header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.page-header-left {
  flex: 1;
  min-width: 0;
}

.page-header-right {
  flex-shrink: 0;
}

// 返回按钮
.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-bg-hover !important;
  }
}

// 页面标题
.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// 内容区：撑满页面宽度（关键样式）
.detail-content {
  padding: $wolf-page-padding;
}

// 信息卡片：撑满父容器宽度
.info-card,
.tabs-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}
</style>
```

**返回按钮样式规范：**

| 属性 | 值 | 说明 |
|-----|-----|------|
| 尺寸 | 32px × 32px | 固定尺寸 |
| 背景 | `$wolf-purple-bg` | 浅紫背景 |
| 圆角 | `$wolf-radius-md` (8px) | 中等圆角 |
| hover | `$wolf-bg-hover` | 悬停变灰 |

**使用场景：**

- ❌ **列表页**：Leads、Customers、Contracts、Opportunities 等列表页面不需要 page-header
- ✅ **详情页**：LeadDetail、CustomerDetail、ContractDetail 等需要返回按钮
- ✅ **表单页**：LeadForm、ContractCreate、ApprovalFlowForm 等需要返回按钮

#### 7.1.2 表单页布局规范

**表单页分类：**

| 表单类型 | 最大宽度 | 说明 |
|---------|---------|------|
| **简单表单** | 800px | 单列布局，表单项较少 |
| **复杂配置表单** | 1200px | 双列布局，带右侧预览区 |

**简单表单页示例（800px）：**

适用于 LeadForm、CustomerEdit、OpportunityEdit、ContractCreate、PaymentPlanCreate、InvoiceForm 等。

```vue
<template>
  <div class="form-page">
    <!-- sticky 页面头部 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">{{ pageTitle }}</h1>
      </div>
    </div>

    <!-- 表单内容：居中布局，最大宽度 800px -->
    <div class="form-container">
      <div class="form-card">
        <el-form :model="form" :rules="rules" label-position="top">
          <!-- 表单项... -->
        </el-form>
        <div class="form-actions">
          <el-button @click="handleBack">取消</el-button>
          <el-button type="primary" @click="handleSubmit">保存</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

// 表单容器：居中布局，最大宽度 800px
.form-container {
  max-width: 800px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}
</style>
```

**复杂配置表单页示例（1200px）：**

适用于 ApprovalFlowForm、ProcurementMethodForm 等，包含左侧表单 + 右侧预览区的双列布局。

```vue
<template>
  <div class="config-form-page">
    <!-- sticky 页面头部 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">{{ pageTitle }}</h1>
      </div>
    </div>

    <!-- 表单内容：居中布局，最大宽度 1200px -->
    <div class="form-content">
      <el-row :gutter="16">
        <el-col :span="14">
          <!-- 左侧表单区 -->
          <div class="form-card">...</div>
        </el-col>
        <el-col :span="10">
          <!-- 右侧预览区 -->
          <div class="preview-card">...</div>
        </el-col>
      </el-row>
      <div class="form-actions">...</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

// 表单内容：居中布局，最大宽度 1200px
.form-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}
</style>
```

### 7.2 网格布局

```vue
<template>
  <!-- 左右双栏布局（8:4） -->
  <div class="wolf-grid wolf-grid--8-4">
    <div class="wolf-grid__main">...</div>
    <div class="wolf-grid__side">...</div>
  </div>
  
  <!-- 左右双栏布局（7:5） -->
  <div class="wolf-grid wolf-grid--7-5">
    <div class="wolf-grid__main">...</div>
    <div class="wolf-grid__side">...</div>
  </div>
  
  <!-- 三栏布局（4:4:4） -->
  <div class="wolf-grid wolf-grid--4-4-4">
    <div class="wolf-grid__col">...</div>
    <div class="wolf-grid__col">...</div>
    <div class="wolf-grid__col">...</div>
  </div>
</template>

<style>
/* 网格容器 */
.wolf-grid {
  display: grid;
  gap: var(--wolf-card-gap);
}

/* 8:4 布局 */
.wolf-grid--8-4 {
  grid-template-columns: 2fr 1fr;
}

/* 7:5 布局 */
.wolf-grid--7-5 {
  grid-template-columns: 7fr 5fr;
}

/* 三栏等分 */
.wolf-grid--4-4-4 {
  grid-template-columns: repeat(3, 1fr);
}

/* 四栏等分 */
.wolf-grid--3-3-3-3 {
  grid-template-columns: repeat(4, 1fr);
}

/* 响应式：平板 */
@media (max-width: 1024px) {
  .wolf-grid--8-4,
  .wolf-grid--7-5 {
    grid-template-columns: 1fr;
  }
  
  .wolf-grid--4-4-4 {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 响应式：手机 */
@media (max-width: 768px) {
  .wolf-grid--4-4-4,
  .wolf-grid--3-3-3-3 {
    grid-template-columns: 1fr;
  }
}
</style>
```

***

## 八、组件规范

### 8.1 卡片（wolf-card）

```vue
<template>
  <!-- 标准卡片 -->
  <div class="wolf-card">
    <div class="wolf-card__header">
      <div class="wolf-card__title">卡片标题</div>
      <div class="wolf-card__extra">更多</div>
    </div>
    <div class="wolf-card__body">
      <!-- 卡片内容 -->
    </div>
  </div>
  
  <!-- 紧凑卡片 -->
  <div class="wolf-card wolf-card--compact">
    <!-- 内容 -->
  </div>
  
  <!-- 无边框卡片 -->
  <div class="wolf-card wolf-card--ghost">
    <!-- 内容 -->
  </div>
</template>

<style>
/* 基础卡片 */
.wolf-card {
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  box-shadow: var(--wolf-shadow-card);
  padding: var(--wolf-card-padding);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.wolf-card:hover {
  box-shadow: var(--wolf-shadow-hover);
}

/* 紧凑卡片 */
.wolf-card--compact {
  padding: var(--wolf-card-padding-sm);
}

/* 超紧凑卡片 */
.wolf-card--xs {
  padding: var(--wolf-card-padding-xs);
}

/* 无边框卡片 */
.wolf-card--ghost {
  background: transparent;
  box-shadow: none;
  border: 1px solid var(--wolf-border-light);
}

/* 卡片头部 */
.wolf-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--wolf-space-4);
  padding-bottom: var(--wolf-space-3);
  border-bottom: 1px solid var(--wolf-border-light);
}

.wolf-card__title {
  font-size: var(--wolf-font-size-card-title);
  font-weight: var(--wolf-font-weight-semibold);
  color: var(--wolf-text-primary);
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
}

.wolf-card__title-icon {
  color: var(--wolf-text-tertiary);
}

.wolf-card__extra {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-link);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--wolf-space-1);
}

.wolf-card__extra:hover {
  text-decoration: underline;
}

/* 卡片内容 */
.wolf-card__body {
  /* 无默认样式 */
}

/* 卡片底部 */
.wolf-card__footer {
  margin-top: var(--wolf-space-4);
  padding-top: var(--wolf-space-3);
  border-top: 1px solid var(--wolf-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
```

### 8.2 标签（wolf-tag）

```vue
<template>
  <!-- 状态标签 - 成功 -->
  <el-tag class="wolf-tag wolf-tag--success">已完成</el-tag>
  
  <!-- 状态标签 - 进行中 -->
  <el-tag class="wolf-tag wolf-tag--info">进行中</el-tag>
  
  <!-- 状态标签 - 警告 -->
  <el-tag class="wolf-tag wolf-tag--warning">VIP</el-tag>
  
  <!-- 状态标签 - 危险 -->
  <el-tag class="wolf-tag wolf-tag--danger">已取消</el-tag>
  
  <!-- 来源标签 - 灰色 -->
  <el-tag class="wolf-tag wolf-tag--gray">网站咨询</el-tag>
  
  <!-- 特殊标签 - 紫色 -->
  <el-tag class="wolf-tag wolf-tag--purple">技术导向</el-tag>
  
  <!-- 小标签 -->
  <el-tag class="wolf-tag wolf-tag--success wolf-tag--sm">已完成</el-tag>
  
  <!-- 大标签 -->
  <el-tag class="wolf-tag wolf-tag--success wolf-tag--lg">已完成</el-tag>
</template>

<style>
/* 基础标签样式 - 覆盖 Element Plus */
.wolf-tag {
  border-radius: var(--wolf-radius-sm) !important;
  padding: 2px 10px !important;
  font-size: var(--wolf-font-size-label) !important;
  font-weight: var(--wolf-font-weight-medium) !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

/* 小标签 */
.wolf-tag--sm {
  padding: 1px 6px !important;
  font-size: var(--wolf-font-size-caption) !important;
}

/* 大标签 */
.wolf-tag--lg {
  padding: 4px 12px !important;
  font-size: var(--wolf-font-size-small) !important;
}

/* 成功/活跃 - 绿色 */
.wolf-tag--success {
  background-color: var(--wolf-success-bg) !important;
  border-color: var(--wolf-success-border) !important;
  color: var(--wolf-success) !important;
}

/* 警告/VIP - 橙色 */
.wolf-tag--warning {
  background-color: var(--wolf-warning-bg) !important;
  border-color: var(--wolf-warning-border) !important;
  color: var(--wolf-warning) !important;
}

/* 危险/重要 - 红色 */
.wolf-tag--danger {
  background-color: var(--wolf-danger-bg) !important;
  border-color: var(--wolf-danger-border) !important;
  color: var(--wolf-danger) !important;
}

/* 信息/进行中 - 蓝色 */
.wolf-tag--info {
  background-color: var(--wolf-info-bg) !important;
  border-color: var(--wolf-info-border) !important;
  color: var(--wolf-info) !important;
}

/* 紫色 - 特殊标签 */
.wolf-tag--purple {
  background-color: var(--wolf-purple-bg) !important;
  border-color: var(--wolf-purple-border) !important;
  color: var(--wolf-purple) !important;
}

/* 灰色 - 来源/渠道 */
.wolf-tag--gray {
  background-color: var(--wolf-gray-bg) !important;
  border-color: var(--wolf-gray-border) !important;
  color: var(--wolf-gray) !important;
}

/* 标签组 */
.wolf-tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--wolf-space-2);
}
</style>
```

### 8.3 按钮（wolf-btn）

```vue
<template>
  <!-- 主按钮 - 大 -->
  <el-button type="primary" class="wolf-btn wolf-btn--primary wolf-btn--lg">
    <el-icon><Plus /></el-icon>
    创建订单
  </el-button>
  
  <!-- 主按钮 - 默认 -->
  <el-button type="primary" class="wolf-btn wolf-btn--primary">
    确认
  </el-button>
  
  <!-- 主按钮 - 小 -->
  <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm">
    编辑
  </el-button>
  
  <!-- 次要按钮 -->
  <el-button class="wolf-btn wolf-btn--default">
    取消
  </el-button>
  
  <!-- 文字按钮 -->
  <el-button type="text" class="wolf-btn wolf-btn--text">
    导出资料
  </el-button>
  
  <!-- 危险按钮 -->
  <el-button type="danger" class="wolf-btn wolf-btn--danger">
    删除
  </el-button>
  
  <!-- 图标按钮 -->
  <el-button type="text" class="wolf-btn wolf-btn--icon">
    <el-icon><More /></el-icon>
  </el-button>
  
  <!-- 返回按钮 -->
  <el-button type="text" class="wolf-btn wolf-btn--back">
    <el-icon><ArrowLeft /></el-icon>
  </el-button>
  
  <!-- 幽灵按钮 -->
  <el-button class="wolf-btn wolf-btn--ghost">
    查看详情
  </el-button>
</template>

<style>
/* 基础按钮 */
.wolf-btn {
  border-radius: var(--wolf-radius-md) !important;
  font-weight: var(--wolf-font-weight-medium) !important;
  transition: all 0.2s ease !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: var(--wolf-space-1) !important;
}

/* 大按钮 */
.wolf-btn--lg {
  padding: 12px 24px !important;
  font-size: var(--wolf-font-size-body) !important;
}

/* 主按钮 - 默认 */
.wolf-btn--primary {
  padding: 10px 20px !important;
  background-color: var(--wolf-primary) !important;
  border-color: var(--wolf-primary) !important;
  color: var(--wolf-text-inverse) !important;
}

.wolf-btn--primary:hover {
  background-color: var(--wolf-primary-hover) !important;
  border-color: var(--wolf-primary-hover) !important;
}

.wolf-btn--primary:active {
  background-color: var(--wolf-primary-active) !important;
  border-color: var(--wolf-primary-active) !important;
}

/* 主按钮 - 小尺寸（表格操作） */
.wolf-btn--primary-sm {
  padding: 6px 12px !important;
  font-size: var(--wolf-font-size-small) !important;
  background-color: var(--wolf-primary) !important;
  border-color: var(--wolf-primary) !important;
  border-radius: var(--wolf-radius-sm) !important;
}

.wolf-btn--primary-sm:hover {
  background-color: var(--wolf-primary-hover) !important;
  border-color: var(--wolf-primary-hover) !important;
}

/* 次要按钮 */
.wolf-btn--default {
  padding: 10px 20px !important;
  border-color: var(--wolf-border-color) !important;
  color: var(--wolf-text-primary) !important;
}

.wolf-btn--default:hover {
  border-color: var(--wolf-primary) !important;
  color: var(--wolf-primary) !important;
}

/* 幽灵按钮 */
.wolf-btn--ghost {
  padding: 10px 20px !important;
  background: transparent !important;
  border-color: var(--wolf-border-color) !important;
  color: var(--wolf-text-secondary) !important;
}

.wolf-btn--ghost:hover {
  background: var(--wolf-bg-hover) !important;
  border-color: var(--wolf-border-color) !important;
}

/* 文字按钮 */
.wolf-btn--text {
  padding: 8px 12px !important;
  color: var(--wolf-text-secondary) !important;
}

.wolf-btn--text:hover {
  background-color: var(--wolf-bg-hover) !important;
  color: var(--wolf-text-primary) !important;
}

/* 危险按钮 */
.wolf-btn--danger {
  padding: 10px 20px !important;
  background-color: var(--wolf-danger) !important;
  border-color: var(--wolf-danger) !important;
  color: var(--wolf-text-inverse) !important;
}

.wolf-btn--danger:hover {
  background-color: var(--wolf-danger-hover) !important;
  border-color: var(--wolf-danger-hover) !important;
}

/* 文字危险按钮 */
.wolf-btn--text-danger {
  color: var(--wolf-danger) !important;
  border: 1px solid var(--wolf-danger-border) !important;
  background-color: var(--wolf-bg-card) !important;
  padding: 8px 12px !important;
}

.wolf-btn--text-danger:hover {
  background-color: var(--wolf-danger-bg) !important;
}

/* 图标按钮 */
.wolf-btn--icon {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: var(--wolf-radius-md) !important;
}

.wolf-btn--icon:hover {
  background-color: var(--wolf-bg-hover) !important;
}

/* 小图标按钮 */
.wolf-btn--icon-sm {
  width: 28px !important;
  height: 28px !important;
  padding: 0 !important;
  border-radius: var(--wolf-radius-sm) !important;
}

.wolf-btn--icon-sm:hover {
  background-color: var(--wolf-bg-hover) !important;
}

/* 返回按钮 */
.wolf-btn--back {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: var(--wolf-radius-md) !important;
}

.wolf-btn--back:hover {
  background-color: var(--wolf-bg-hover) !important;
}

/* 按钮组 */
.wolf-btn-group {
  display: flex;
  gap: var(--wolf-space-3);
}

.wolf-btn-group--sm {
  gap: var(--wolf-space-2);
}
</style>
```

### 8.4 列表项（wolf-list-item）

列表项适用于：左侧菜单栏、设置页面管理入口、用户列表等导航/选择场景。

**设计特点**：
- 图标 + 标题 + 描述/箭头 的三段式结构
- hover 时显示灰色背景，无颜色变化
- active 时同样灰色背景，文字变主色（可选）

```vue
<template>
  <!-- 基础列表项 -->
  <div class="wolf-list-item">
    <el-icon class="item-icon"><User /></el-icon>
    <span class="item-text">用户管理</span>
    <el-icon class="item-arrow"><ArrowRight /></el-icon>
  </div>
  
  <!-- 带描述的列表项 -->
  <div class="wolf-list-item">
    <el-icon class="item-icon"><Document /></el-icon>
    <span class="item-text">审批流程</span>
    <span class="item-desc">配置审批流程模板</span>
    <el-icon class="item-arrow"><ArrowRight /></el-icon>
  </div>
  
  <!-- 激活状态 -->
  <div class="wolf-list-item active">
    <el-icon class="item-icon"><TrendCharts /></el-icon>
    <span class="item-text">商机管理</span>
    <el-icon class="item-arrow"><ArrowRight /></el-icon>
  </div>
</template>

<style>
/* 列表项容器 */
.wolf-list-item {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-md);
  padding: var(--wolf-space-md);
  cursor: pointer;
  transition: background 0.2s;
  border-radius: var(--wolf-radius-sm);
  color: var(--wolf-text-tertiary);
}

.wolf-list-item:hover {
  background: var(--wolf-bg-hover);
}

.wolf-list-item.active {
  background: var(--wolf-bg-hover);
  color: var(--wolf-primary);
}

/* 图标 */
.wolf-list-item .item-icon {
  font-size: 18px;
  color: var(--wolf-text-tertiary);
  flex-shrink: 0;
}

.wolf-list-item.active .item-icon {
  color: var(--wolf-primary);
}

/* 标题文字 */
.wolf-list-item .item-text {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  flex: 1;
}

/* 描述文字（可选） */
.wolf-list-item .item-desc {
  font-size: var(--wolf-font-size-caption);
  color: var(--wolf-text-tertiary);
  flex: 1;
  text-align: right;
}

/* 箭头图标 */
.wolf-list-item .item-arrow {
  font-size: 14px;
  color: var(--wolf-text-placeholder);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.wolf-list-item:hover .item-arrow,
.wolf-list-item.active .item-arrow {
  opacity: 1;
  color: var(--wolf-text-tertiary);
}
</style>
```

**使用场景对照**：

| 场景 | 文件 | 说明 |
| --- | --- | --- |
| 左侧菜单栏 | `AppLayout.vue` | 导航菜单项，hover 灰色背景 |
| 系统管理入口 | `Settings.vue` | 图标+标题+描述+箭头 |
| 用户/角色列表 | `Users.vue`, `Roles.vue` | 可复用列表项样式 |

### 8.5 表格（wolf-table）

```vue
<template>
  <div class="wolf-table-wrapper">
    <el-table class="wolf-table" :data="list" stripe>
      <!-- 名称列 - 蓝色链接 -->
      <el-table-column label="名称" min-width="180">
        <template #default="{ row }">
          <span class="wolf-link">{{ row.name }}</span>
        </template>
      </el-table-column>
      
      <!-- 来源列 - 灰色标签 -->
      <el-table-column label="来源" width="100">
        <template #default="{ row }">
          <el-tag class="wolf-tag wolf-tag--gray" size="small">
            {{ row.source }}
          </el-tag>
        </template>
      </el-table-column>
      
      <!-- 状态列 - 状态标签 -->
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :class="`wolf-tag wolf-tag--${row.statusType}`" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      
      <!-- 操作列 -->
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <div class="wolf-table-actions">
            <el-button 
              type="primary" 
              size="small" 
              class="wolf-btn wolf-btn--primary-sm"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-dropdown>
              <el-button type="text" class="wolf-btn wolf-btn--icon-sm">
                <el-icon><More /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item>查看详情</el-dropdown-item>
                  <el-dropdown-item>分配</el-dropdown-item>
                  <el-dropdown-item divided type="danger">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style>
/* 表格容器 */
.wolf-table-wrapper {
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  overflow: hidden;
}

/* 表头 */
.wolf-table .el-table__header th {
  background-color: var(--wolf-bg-hover) !important;
  color: var(--wolf-text-secondary);
  font-weight: var(--wolf-font-weight-semibold);
  font-size: var(--wolf-font-size-small);
  padding: 14px 16px;
  border-bottom: 1px solid var(--wolf-border-color);
}

/* 表体行 */
.wolf-table .el-table__row {
  height: var(--wolf-table-row-height);
}

.wolf-table .el-table__row td {
  padding: 12px 16px;
  font-size: var(--wolf-font-size-body);
  color: var(--wolf-text-primary);
  border-bottom: 1px solid var(--wolf-border-light);
}

/* 行悬停 */
.wolf-table .el-table__row:hover td {
  background-color: var(--wolf-bg-hover) !important;
}

/* 链接文字 */
.wolf-link {
  color: var(--wolf-text-link);
  cursor: pointer;
  font-weight: var(--wolf-font-weight-medium);
}

.wolf-link:hover {
  text-decoration: underline;
}

/* 表格操作区 */
.wolf-table-actions {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
}
</style>
```

### 8.6 描述列表（wolf-descriptions）

```vue
<template>
  <!-- 标准描述列表 - 3列 -->
  <div class="wolf-descriptions wolf-descriptions--3">
    <div class="wolf-descriptions__item">
      <div class="wolf-descriptions__label">合同编号</div>
      <div class="wolf-descriptions__value">CT202602270001</div>
    </div>
    <div class="wolf-descriptions__item">
      <div class="wolf-descriptions__label">关联客户</div>
      <div class="wolf-descriptions__value">山东港口科技集团日照有限公司</div>
    </div>
    <!-- 更多项... -->
  </div>
  
  <!-- 紧凑描述列表 - 4列 -->
  <div class="wolf-descriptions wolf-descriptions--4 wolf-descriptions--compact">
    <div class="wolf-descriptions__item">
      <el-icon class="wolf-descriptions__icon"><FileText /></el-icon>
      <div class="wolf-descriptions__content">
        <span class="wolf-descriptions__label">编号:</span>
        <span class="wolf-descriptions__value">CT202602270001</span>
      </div>
    </div>
    <!-- 更多项... -->
  </div>
</template>

<style>
/* 描述列表容器 */
.wolf-descriptions {
  display: grid;
  gap: var(--wolf-space-5) var(--wolf-space-4);
}

/* 3列布局 */
.wolf-descriptions--3 {
  grid-template-columns: repeat(3, 1fr);
}

/* 4列布局 */
.wolf-descriptions--4 {
  grid-template-columns: repeat(4, 1fr);
}

/* 2列布局 */
.wolf-descriptions--2 {
  grid-template-columns: repeat(2, 1fr);
}

/* 响应式 */
@media (max-width: 1024px) {
  .wolf-descriptions--4 {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .wolf-descriptions--3,
  .wolf-descriptions--4 {
    grid-template-columns: 1fr;
  }
}

/* 描述项 */
.wolf-descriptions__item {
  display: flex;
  align-items: flex-start;
  gap: var(--wolf-space-2);
}

/* 紧凑模式 */
.wolf-descriptions--compact .wolf-descriptions__item {
  align-items: center;
  gap: var(--wolf-space-1);
}

/* 图标 */
.wolf-descriptions__icon {
  font-size: 16px;
  color: var(--wolf-text-tertiary);
  flex-shrink: 0;
  margin-top: 2px;
}

.wolf-descriptions--compact .wolf-descriptions__icon {
  font-size: 14px;
  margin-top: 0;
}

/* 内容区 */
.wolf-descriptions__content {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-1);
  min-width: 0;
}

/* 标签 */
.wolf-descriptions__label {
  font-size: var(--wolf-font-size-label);
  color: var(--wolf-text-tertiary);
  flex-shrink: 0;
}

.wolf-descriptions--compact .wolf-descriptions__label {
  font-size: var(--wolf-font-size-caption);
}

/* 值 */
.wolf-descriptions__value {
  font-size: var(--wolf-font-size-body);
  color: var(--wolf-text-primary);
  font-weight: var(--wolf-font-weight-medium);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wolf-descriptions--compact .wolf-descriptions__value {
  font-size: var(--wolf-font-size-small);
}
</style>
```

### 8.7 时间轴（wolf-timeline）

```vue
<template>
  <div class="wolf-timeline">
    <div class="wolf-timeline__item" v-for="item in items" :key="item.id">
      <div class="wolf-timeline__line"></div>
      <div class="wolf-timeline__dot" :class="`wolf-timeline__dot--${item.type}`">
        <el-icon :size="14">
          <component :is="item.icon" />
        </el-icon>
      </div>
      <div class="wolf-timeline__content">
        <div class="wolf-timeline__header">
          <span class="wolf-timeline__title">{{ item.title }}</span>
          <el-tag v-if="item.status" :class="`wolf-tag wolf-tag--${item.statusType}`" size="small">
            {{ item.status }}
          </el-tag>
        </div>
        <div class="wolf-timeline__meta">
          <span class="wolf-timeline__user">{{ item.user }}</span>
          <span class="wolf-timeline__time">{{ item.time }}</span>
        </div>
        <div v-if="item.result" class="wolf-timeline__result">
          <el-tag :class="`wolf-tag wolf-tag--${item.resultType}`" size="small">
            {{ item.result }}
          </el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
.wolf-timeline {
  position: relative;
}

.wolf-timeline__item {
  position: relative;
  padding-left: 40px;
  padding-bottom: var(--wolf-space-5);
}

.wolf-timeline__item:last-child {
  padding-bottom: 0;
}

.wolf-timeline__line {
  position: absolute;
  left: 15px;
  top: 32px;
  bottom: 0;
  width: 2px;
  background: var(--wolf-border-color);
}

.wolf-timeline__item:last-child .wolf-timeline__line {
  display: none;
}

.wolf-timeline__dot {
  position: absolute;
  left: 0;
  top: 2px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: var(--wolf-font-weight-medium);
}

.wolf-timeline__dot--primary {
  background-color: var(--wolf-primary);
}

.wolf-timeline__dot--success {
  background-color: var(--wolf-success);
}

.wolf-timeline__dot--info {
  background-color: var(--wolf-info);
}

.wolf-timeline__dot--gray {
  background-color: var(--wolf-gray);
}

.wolf-timeline__dot--number {
  background-color: var(--wolf-info-bg);
  color: var(--wolf-info);
}

.wolf-timeline__content {
  padding-top: 4px;
}

.wolf-timeline__header {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
  margin-bottom: var(--wolf-space-1);
}

.wolf-timeline__title {
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
  font-size: var(--wolf-font-size-body);
}

.wolf-timeline__meta {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-tertiary);
}

.wolf-timeline__result {
  margin-top: var(--wolf-space-1);
}
</style>
```

### 8.8 弹窗/对话框（wolf-modal）

```vue
<template>
  <el-dialog 
    class="wolf-modal" 
    :model-value="visible" 
    @update:model-value="$emit('update:visible', $event)"
    :title="title"
    width="480px"
  >
    <div class="wolf-modal__body">
      <!-- 弹窗内容 -->
    </div>
    <template #footer>
      <div class="wolf-modal__footer">
        <el-button class="wolf-btn wolf-btn--default" @click="handleCancel">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleConfirm">确认</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style>
/* 弹窗容器 */
.wolf-modal {
  border-radius: var(--wolf-radius-xl);
  overflow: hidden;
}

.wolf-modal .el-dialog__header {
  padding: var(--wolf-space-4) var(--wolf-space-5);
  border-bottom: 1px solid var(--wolf-border-light);
  margin-right: 0;
}

.wolf-modal .el-dialog__title {
  font-size: var(--wolf-font-size-card-title);
  font-weight: var(--wolf-font-weight-semibold);
  color: var(--wolf-text-primary);
}

.wolf-modal .el-dialog__headerbtn {
  top: 16px;
  right: 16px;
  width: 32px;
  height: 32px;
  border-radius: var(--wolf-radius-md);
}

.wolf-modal .el-dialog__headerbtn:hover {
  background: var(--wolf-bg-hover);
}

.wolf-modal .el-dialog__body {
  padding: var(--wolf-space-4) var(--wolf-space-5);
}

.wolf-modal .el-dialog__footer {
  padding: var(--wolf-space-3) var(--wolf-space-5);
  border-top: 1px solid var(--wolf-border-light);
}

/* 弹窗内容区 */
.wolf-modal__body {
  /* 无默认样式 */
}

/* 弹窗底部 */
.wolf-modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--wolf-space-3);
}

/* 不同尺寸的弹窗 */
.wolf-modal--sm {
  width: 400px !important;
}

.wolf-modal--md {
  width: 560px !important;
}

.wolf-modal--lg {
  width: 720px !important;
}

.wolf-modal--xl {
  width: 960px !important;
}
</style>
```

### 8.9 Tab 切换（wolf-tabs）

```vue
<template>
  <div class="wolf-tabs">
    <div class="wolf-tabs__header">
      <div 
        v-for="tab in tabs" 
        :key="tab.key"
        class="wolf-tabs__item"
        :class="{ 'is-active': activeKey === tab.key }"
        @click="activeKey = tab.key"
      >
        {{ tab.label }}
      </div>
    </div>
    <div class="wolf-tabs__content">
      <!-- Tab 内容 -->
    </div>
  </div>
</template>

<style>
.wolf-tabs {
  /* 无默认样式 */
}

.wolf-tabs__header {
  display: flex;
  gap: var(--wolf-space-6);
  border-bottom: 1px solid var(--wolf-border-color);
  margin-bottom: var(--wolf-space-4);
}

.wolf-tabs__item {
  padding: var(--wolf-space-3) 0;
  font-size: var(--wolf-font-size-body);
  color: var(--wolf-text-secondary);
  cursor: pointer;
  position: relative;
  transition: color 0.2s ease;
}

.wolf-tabs__item:hover {
  color: var(--wolf-text-primary);
}

.wolf-tabs__item.is-active {
  color: var(--wolf-primary);
  font-weight: var(--wolf-font-weight-medium);
}

.wolf-tabs__item.is-active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--wolf-primary);
}

.wolf-tabs__content {
  /* 无默认样式 */
}
</style>
```

### 8.10 底部操作栏（wolf-bottom-actions）

```vue
<template>
  <div class="wolf-bottom-actions">
    <div class="wolf-bottom-actions__left">
      <el-button type="danger" text class="wolf-btn wolf-btn--text-danger">
        <el-icon><Delete /></el-icon>
        删除
      </el-button>
    </div>
    <div class="wolf-bottom-actions__right">
      <el-button class="wolf-btn wolf-btn--default">取消</el-button>
      <el-button type="primary" class="wolf-btn wolf-btn--primary">保存</el-button>
    </div>
  </div>
</template>

<style>
.wolf-bottom-actions {
  position: fixed;
  bottom: 0;
  left: var(--wolf-sidebar-width);
  right: 0;
  background: var(--wolf-bg-card);
  border-top: 1px solid var(--wolf-border-color);
  padding: var(--wolf-space-4) var(--wolf-page-padding);
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: var(--wolf-shadow-bottom);
  z-index: 100;
}

.wolf-bottom-actions__left,
.wolf-bottom-actions__right {
  display: flex;
  gap: var(--wolf-space-3);
}

@media (max-width: 768px) {
  .wolf-bottom-actions {
    left: 0;
    flex-direction: column;
    gap: var(--wolf-space-3);
  }
  
  .wolf-bottom-actions__left,
  .wolf-bottom-actions__right {
    width: 100%;
    justify-content: center;
  }
}
</style>
```

***

## 九、完整 CSS 文件

### `wolf-design-system.css`

```css
/**
 * CRMWolf 设计系统 V2.0
 * 基于 Element Plus 的现代简约设计体系
 * 命名空间: wolf-
 */

/* ========================================
   1. CSS Variables
   ======================================== */
:root {
  /* 背景 */
  --wolf-bg-page: #F5F7FA;
  --wolf-bg-card: #FFFFFF;
  --wolf-bg-hover: #F7F8FA;
  --wolf-bg-active: #F2F3F5;
  --wolf-bg-sidebar: #1A1F2E;
  --wolf-bg-mask: rgba(0, 0, 0, 0.45);
  
  /* 品牌主色 */
  --wolf-primary: #165DFF;
  --wolf-primary-hover: #0E42D2;
  --wolf-primary-active: #0B36B0;
  --wolf-primary-light: #E8F3FF;
  --wolf-primary-gradient: linear-gradient(135deg, #165DFF 0%, #0E42D2 100%);
  
  /* 状态色 */
  --wolf-success: #00B42A;
  --wolf-success-hover: #009A24;
  --wolf-success-bg: #E8FFEA;
  --wolf-success-border: #86EFAC;
  
  --wolf-warning: #FF7D00;
  --wolf-warning-hover: #E56F00;
  --wolf-warning-bg: #FFF7E8;
  --wolf-warning-border: #FCD34D;
  
  --wolf-danger: #F53F3F;
  --wolf-danger-hover: #D93636;
  --wolf-danger-bg: #FFECE8;
  --wolf-danger-border: #FCA5A5;
  
  --wolf-info: #165DFF;
  --wolf-info-hover: #0E42D2;
  --wolf-info-bg: #E8F3FF;
  --wolf-info-border: #93C5FD;
  
  --wolf-purple: #722ED1;
  --wolf-purple-hover: #6025B0;
  --wolf-purple-bg: #F5E8FF;
  --wolf-purple-border: #D8B4FE;
  
  --wolf-gray: #86909C;
  --wolf-gray-hover: #6B7785;
  --wolf-gray-bg: #F2F3F5;
  --wolf-gray-border: #E5E6EB;
  
  /* 文字 */
  --wolf-text-primary: #1D2129;
  --wolf-text-secondary: #4E5969;
  --wolf-text-tertiary: #86909C;
  --wolf-text-placeholder: #C9CDD4;
  --wolf-text-disabled: #C9CDD4;
  --wolf-text-link: #165DFF;
  --wolf-text-link-hover: #0E42D2;
  --wolf-text-inverse: #FFFFFF;
  
  /* 边框 */
  --wolf-border-color: #E5E6EB;
  --wolf-border-light: #F2F3F5;
  --wolf-border-focus: #165DFF;
  
  /* 阴影 */
  --wolf-shadow-card: 0 1px 2px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.02);
  --wolf-shadow-hover: 0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.04);
  --wolf-shadow-bottom: 0 -2px 8px rgba(0, 0, 0, 0.05);
  --wolf-shadow-dropdown: 0 8px 24px rgba(0, 0, 0, 0.12);
  --wolf-shadow-modal: 0 16px 48px rgba(0, 0, 0, 0.16);
  
  /* 圆角 */
  --wolf-radius-none: 0px;
  --wolf-radius-sm: 4px;
  --wolf-radius-md: 8px;
  --wolf-radius-lg: 12px;
  --wolf-radius-xl: 16px;
  --wolf-radius-2xl: 20px;
  --wolf-radius-full: 9999px;
  
  /* 字体 */
  --wolf-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
  
  /* 字号 */
  --wolf-font-size-display: 24px;
  --wolf-font-size-title: 20px;
  --wolf-font-size-card-title: 16px;
  --wolf-font-size-subtitle: 15px;
  --wolf-font-size-body: 14px;
  --wolf-font-size-small: 13px;
  --wolf-font-size-label: 12px;
  --wolf-font-size-caption: 11px;
  
  /* 字重 */
  --wolf-font-weight-normal: 400;
  --wolf-font-weight-medium: 500;
  --wolf-font-weight-semibold: 600;
  --wolf-font-weight-bold: 700;
  
  /* 间距 */
  --wolf-space-0: 0px;
  --wolf-space-1: 4px;
  --wolf-space-2: 8px;
  --wolf-space-3: 12px;
  --wolf-space-4: 16px;
  --wolf-space-5: 20px;
  --wolf-space-6: 24px;
  --wolf-space-8: 32px;
  --wolf-space-10: 40px;
  --wolf-space-12: 48px;
  
  /* 页面间距 */
  --wolf-page-padding: 24px;
  --wolf-page-max-width: 1400px;
  --wolf-section-gap: 24px;
  --wolf-card-gap: 16px;
  --wolf-card-padding: 20px;
  --wolf-card-padding-sm: 16px;
  --wolf-card-padding-xs: 12px;
  
  /* 组件尺寸 */
  --wolf-table-row-height: 56px;
  --wolf-table-row-height-sm: 48px;
  --wolf-header-height: 56px;
  --wolf-sidebar-width: 220px;
}

/* ========================================
   2. Global Reset
   ======================================== */
body {
  font-family: var(--wolf-font-family);
  background-color: var(--wolf-bg-page);
  color: var(--wolf-text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ========================================
   3. Card
   ======================================== */
.wolf-card {
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  box-shadow: var(--wolf-shadow-card);
  padding: var(--wolf-card-padding);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.wolf-card:hover {
  box-shadow: var(--wolf-shadow-hover);
}

.wolf-card--compact {
  padding: var(--wolf-card-padding-sm);
}

.wolf-card--xs {
  padding: var(--wolf-card-padding-xs);
}

.wolf-card--ghost {
  background: transparent;
  box-shadow: none;
  border: 1px solid var(--wolf-border-light);
}

/* ========================================
   4. Tag - 覆盖 Element Plus
   ======================================== */
.wolf-tag {
  border-radius: var(--wolf-radius-sm) !important;
  padding: 2px 10px !important;
  font-size: var(--wolf-font-size-label) !important;
  font-weight: var(--wolf-font-weight-medium) !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

.wolf-tag--sm {
  padding: 1px 6px !important;
  font-size: var(--wolf-font-size-caption) !important;
}

.wolf-tag--lg {
  padding: 4px 12px !important;
  font-size: var(--wolf-font-size-small) !important;
}

.wolf-tag--success {
  background-color: var(--wolf-success-bg) !important;
  border-color: var(--wolf-success-border) !important;
  color: var(--wolf-success) !important;
}

.wolf-tag--warning {
  background-color: var(--wolf-warning-bg) !important;
  border-color: var(--wolf-warning-border) !important;
  color: var(--wolf-warning) !important;
}

.wolf-tag--danger {
  background-color: var(--wolf-danger-bg) !important;
  border-color: var(--wolf-danger-border) !important;
  color: var(--wolf-danger) !important;
}

.wolf-tag--info {
  background-color: var(--wolf-info-bg) !important;
  border-color: var(--wolf-info-border) !important;
  color: var(--wolf-info) !important;
}

.wolf-tag--purple {
  background-color: var(--wolf-purple-bg) !important;
  border-color: var(--wolf-purple-border) !important;
  color: var(--wolf-purple) !important;
}

.wolf-tag--gray {
  background-color: var(--wolf-gray-bg) !important;
  border-color: var(--wolf-gray-border) !important;
  color: var(--wolf-gray) !important;
}

/* ========================================
   5. Button - 覆盖 Element Plus
   ======================================== */
.wolf-btn {
  border-radius: var(--wolf-radius-md) !important;
  font-weight: var(--wolf-font-weight-medium) !important;
  transition: all 0.2s ease !important;
}

.wolf-btn--lg {
  padding: 12px 24px !important;
  font-size: var(--wolf-font-size-body) !important;
}

.wolf-btn--primary {
  padding: 10px 20px !important;
  background-color: var(--wolf-primary) !important;
  border-color: var(--wolf-primary) !important;
}

.wolf-btn--primary:hover {
  background-color: var(--wolf-primary-hover) !important;
  border-color: var(--wolf-primary-hover) !important;
}

.wolf-btn--primary-sm {
  padding: 6px 12px !important;
  font-size: 13px !important;
  border-radius: var(--wolf-radius-sm) !important;
  background-color: var(--wolf-primary) !important;
  border-color: var(--wolf-primary) !important;
}

.wolf-btn--primary-sm:hover {
  background-color: var(--wolf-primary-hover) !important;
  border-color: var(--wolf-primary-hover) !important;
}

/* ========================================
   6. Table
   ======================================== */
.wolf-table-wrapper {
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  overflow: hidden;
}

.wolf-table .el-table__header th {
  background-color: var(--wolf-bg-hover) !important;
  color: var(--wolf-text-secondary);
  font-weight: var(--wolf-font-weight-semibold);
  font-size: var(--wolf-font-size-small);
  padding: 14px 16px;
  border-bottom: 1px solid var(--wolf-border-color);
}

.wolf-table .el-table__row {
  height: var(--wolf-table-row-height);
}

.wolf-table .el-table__row td {
  padding: 12px 16px;
  font-size: var(--wolf-font-size-body);
  color: var(--wolf-text-primary);
  border-bottom: 1px solid var(--wolf-border-light);
}

.wolf-table .el-table__row:hover td {
  background-color: var(--wolf-bg-hover) !important;
}

.wolf-link {
  color: var(--wolf-text-link);
  cursor: pointer;
  font-weight: var(--wolf-font-weight-medium);
}

.wolf-link:hover {
  text-decoration: underline;
}
```

***

## 十、命名规范总结

| 类型  | 前缀                    | 示例                                               |
| --- | --------------------- | ------------------------------------------------ |
| 页面  | `wolf-page`           | `.wolf-page`, `.wolf-page__content`              |
| 布局  | `wolf-grid`           | `.wolf-grid`, `.wolf-grid--8-4`                  |
| 卡片  | `wolf-card`           | `.wolf-card`, `.wolf-card__header`               |
| 标签  | `wolf-tag`            | `.wolf-tag`, `.wolf-tag--success`                |
| 按钮  | `wolf-btn`            | `.wolf-btn`, `.wolf-btn--primary`                |
| 表格  | `wolf-table`          | `.wolf-table`, `.wolf-table-wrapper`             |
| 描述  | `wolf-descriptions`   | `.wolf-descriptions`, `.wolf-descriptions__item` |
| 时间轴 | `wolf-timeline`       | `.wolf-timeline`, `.wolf-timeline__dot`          |
| 弹窗  | `wolf-modal`          | `.wolf-modal`, `.wolf-modal__body`               |
| Tab | `wolf-tabs`           | `.wolf-tabs`, `.wolf-tabs__item`                 |
| 底部栏 | `wolf-bottom-actions` | `.wolf-bottom-actions__left`                     |

***

## 九之二、组件规范补充（极简中性风）

### 按钮设计规范

**设计总原则**：全程采用低饱和度暖调中性色，无强对比、无厚重装饰，仅用背景色差异区分状态。

**按钮类型体系**：全页面仅保留3种按钮类型，禁止新增自定义样式。

| 按钮类型 | 视觉定位 | 核心使用场景 | 单页面出现频率 |
|:---|:---|:---|:---|
| 通用次按钮（胶囊型） | 页面核心常规操作 | 添加、新建、了解更多等 | 无限制 |
| 文本按钮 | 弱操作、次要操作 | 编辑、取消、更多等 | 无限制 |
| 危险按钮 | 不可逆负面操作 | 删除、清空、注销等 | 极低 |

**通用次按钮（胶囊型）规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 按钮总高度 | 32px | 固定高度，全系统统一 |
| 圆角 | 16px | 全圆角胶囊型，圆角值=高度的50% |
| 水平内边距 | 24px | 文字左右间距 |
| 垂直内边距 | 8px | 文字上下间距 |
| 字号 | 14px | 固定字号 |
| 字重 | 500 | 中等字重，非粗体 |
| 按钮间距 | 12px | 多个按钮并列时间距 |

**交互状态规范**：

| 交互状态 | 背景色 | 文字色 | 阴影 |
|:---|:---|:---|:---|
| 默认态 | `#F7F7F5` | `#3A3A3A` | `0 2px 8px rgba(0,0,0,0.04)` |
| Hover态 | `#F0F0ED` | `#1C1C1C` | `0 2px 10px rgba(0,0,0,0.06)` |
| Active态 | `#EAEAE7` | `#1C1C1C` | `0 1px 4px rgba(0,0,0,0.04)` |
| 禁用态 | `#F7F7F5` | `#909090` | 无阴影 |

**文本按钮规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 按钮总高度 | 24px | 固定高度 |
| 圆角 | 4px | 小圆角，非全圆角 |
| 水平内边距 | 8px | 文字左右间距 |
| 垂直内边距 | 4px | 文字上下间距 |
| 字号 | 14px | 固定字号 |
| 字重 | 400 | 正常字重 |

**危险按钮规范**：
- 基础尺寸与文本按钮一致
- 默认态：文字色 `#A83232`（低饱和暗红），透明无背景
- Hover态：背景 `#FCECEC`，文字色 `#7A2828`
- Active态：背景 `#F8E0E0`

---

### 下拉框（Select 选择器）规范

**基础尺寸规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 选择器总高度 | 28px | 固定高度 |
| 圆角 | 6px | 中等圆角 |
| 水平内边距 | 12px | 文字左侧间距 |
| 字号 | 13px | 固定字号 |

**交互状态规范**：

| 交互状态 | 背景色 | 文字色 | 箭头色 |
|:---|:---|:---|:---|
| 默认态 | `#F5F5F3` | `#3A3A3A` | `#909090` |
| Hover态 | `#F0F0ED` | `#3A3A3A` | `#636363` |
| 激活态 | `#EFEFED` | `#3A3A3A` | `#3A3A3A` |
| 禁用态 | `#F5F5F3` | `#909090` | `#C4C4C4` |

**下拉面板规范**：
- 面板背景：`#FFFFFF` 纯白，圆角8px
- 面板阴影：`0 4px 16px rgba(0,0,0,0.06)`
- 选项高度：36px，圆角4px，间距2px
- 选项字号：13px，字重400

---

### 输入框（Input）规范

**设计原则**：与下拉框样式完全统一，保持视觉一致性。

**基础尺寸规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 输入框总高度 | 28px | 与下拉框统一 |
| 圆角 | 6px | 与下拉框统一 |
| 水平内边距 | 12px | 与下拉框统一 |
| 字号 | 13px | 与下拉框统一 |
| 边框 | 无 | 与下拉框统一 |

**交互状态规范**：

| 交互状态 | 背景色 | 文字色 | 占位符色 |
|:---|:---|:---|:---|
| 默认态 | `#F5F5F3` | `#3A3A3A` | `#909090` |
| Hover态 | `#F0F0ED` | `#3A3A3A` | `#909090` |
| 激活态 | `#EFEFED` | `#3A3A3A` | `#909090` |
| 禁用态 | `#F5F5F3` | `#909090` | `#C4C4C4` |

---

### 下拉选项（Dropdown Item）规范

**基础尺寸规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 选项总高度 | 36px | 固定高度 |
| 圆角 | 4px | 小圆角 |
| 水平内边距 | 12px | 内容左右间距 |
| 选项间距 | 2px | 选项之间间距 |
| 字号 | 13px | 固定字号 |
| 字重 | 400（选中态500） | 正常/选中字重 |

**交互状态规范**：

| 交互状态 | 背景色 | 文字色 |
|:---|:---|:---|
| 默认态 | 透明 | `#3A3A3A` |
| Hover态 | `#F7F7F5` | `#3A3A3A` |
| 选中态 | `#F0F0ED` | `#1C1C1C`（字重500） |
| 禁用态 | 透明 | `#909090` |
| 危险选项 | 透明 | `#A83232`（Hover加背景`#FCECEC`） |

---

### 标签（Tag）规范

**设计原则**：全系统仅用「浅底色+同色系文字」样式，禁止纯色填充、描边样式。

**基础尺寸规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 标签总高度 | 22px | 固定高度 |
| 圆角 | 4px | 小圆角 |
| 水平内边距 | 8px | 文字左右间距 |
| 垂直内边距 | 3px | 文字上下间距 |
| 标签间距 | 6px | 多标签并列间距 |
| 字号 | 12px | 固定字号 |
| 字重 | 400 | 正常字重 |

**视觉样式规范**：

| 标签类型 | 背景色 | 文字色 | 核心使用场景 |
|:---|:---|:---|:---|
| 中性默认标签 | `#F5F5F3` | `#636363` | 通用状态、类型标记 |
| 成功/允许标签 | `#EDF7EF` | `#2B633C` | 成功、正常状态 |
| 警告标签 | `#FFF6E8` | `#7A4F1E` | 警告、待处理、风险状态 |
| 危险标签 | `#FCECEC` | `#7A2828` | 禁用、错误、失败状态 |

**使用规则**：
1. 禁止给标签加描边、渐变、阴影；
2. 标签文字禁止换行，禁止超过6个汉字/12个字符；
3. 禁止使用高饱和背景与文字；
4. 同一行内，标签类型不超过3种。

---

### 表格（Table）规范

**设计总原则**：
1. **内容绝对优先，极致视觉降噪**：完全去除非必要装饰，无竖分割线、无厚重边框、无高对比元素
2. **呼吸感均匀布局**：用固定行高、统一留白替代生硬分割线
3. **柔和层级区分**：仅用极细微的色值差异、字重区分表头与内容
4. **全系统规范统一**：所有样式完全复用全局UI规范

**表格容器规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 容器背景 | 透明 | 继承父容器背景，无额外背景色、描边、圆角、阴影 |
| 列宽规则 | 固定宽度列+自适应剩余宽度 | 核心信息列固定最小宽度，长文本列自适应填充，禁止平均分配 |

**表头规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 行高 | 44px | 固定高度，不随内容变化 |
| 背景 | `#F5F5F3` | 比页面背景深0.5个色阶 |
| 字号 | 13px | 固定字号 |
| 字重 | 500 | 仅用字重区分表头与内容 |
| 文字色 | `#3A3A3A` | 深中性灰 |
| 内边距 | 左右8px，上下12px | 保证表头有足够呼吸感 |
| 对齐 | 左对齐 | 与内容对齐方式一致 |
| 底部分割线 | 1px，色值`#F0F0ED` | 极淡分割线 |
| 内容处理 | 单行不换行 | 表头文字始终单行显示 |

**内容行规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 最小行高 | 44px | 保证基本呼吸感，内容多时自动撑高 |
| 内边距 | 左右8px，上下12px | 垂直内边距支持换行内容 |
| 对齐 | 左对齐、垂直居中 | 所有单元格统一 |
| 竖分割线 | 无 | 仅用列间距区分，取消网格感 |

**列内容显示规则**：

| 列类型 | 显示规则 | 适用场景 |
|:---|:---|:---|
| 核心信息列 | 单行省略，禁止换行 | 状态、金额、日期、操作等固定宽度列 |
| 长文本列 | 允许换行，最多2行 | 客户名称、商机名称、备注等自适应列 |
| 代码/ID列 | 单行省略，等宽字体 | 编号、编码等 |

**内容换行规范**：
- 允许换行的列：设置 `white-space: normal`，最多显示2行，超出部分省略
- 单行省略的列：设置 `white-space: nowrap` + `text-overflow: ellipsis`
- 行高自适应：内容行不设固定高度，由内容自然撑开，最小高度44px
- 多行内容间距：行内上下内边距12px，保证换行内容有足够呼吸感

**行状态背景规范**：

| 行状态 | 背景色 | 适用场景 |
|:---|:---|:---|
| 默认常态 | 透明（继承`#F9F8F5`） | 所有常规数据行 |
| Hover悬浮 | `#F0F0ED` | 鼠标悬浮整行 |
| 选中态 | `#EFEFED` | 单单/多选选中行 |
| 禁用态 | 透明（内容透明度50%） | 不可操作行 |

**行分割线规范**：
- 行底部1px分割线，色值`#F2F2F0`（极淡暖灰）
- 无上下边框、无竖分割线

**滚动条规范**：

| 参数 | 固定数值 | 规则说明 |
|:---|:---|:---|
| 宽度/高度 | 4px | 垂直/水平滚动条 |
| 圆角 | 2px | 小圆角 |
| 滑块默认色 | `#E5E5E0` | 低对比度 |
| 滑块Hover色 | `#C4C4C0` | hover加深 |
| 显示模式 | overlay | 不占用内容宽度 |

**表格红线规则**：
1. 禁止竖分割线、厚重边框、描边、渐变等装饰性元素
2. 禁止斑马纹（隔行变色），禁止高对比背景区分数据行
3. 禁止表头使用700+粗体、高饱和色值
4. 禁止列宽平均分配
5. 禁止给单元格添加背景色、描边、阴影
6. 禁止高饱和状态标签，必须复用全局标签规范
7. 核心信息列禁止换行，保持单行省略

---

### 设计红线规则

**按钮红线**：
1. 禁止修改按钮固定高度、圆角比例，禁止非胶囊型的通用次按钮；
2. 禁止给按钮加描边、渐变、厚重阴影、装饰性图案；
3. 禁止使用高饱和纯色填充按钮，禁止纯黑、纯白按钮背景；
4. 同一页面内，禁止出现3种以上的按钮类型；
5. 按钮文字禁止换行，禁止使用600+粗体。

**标签红线**：
1. 禁止给标签加描边、渐变、阴影；
2. 标签文字禁止超过6个汉字/12个字符；
3. 禁止使用高饱和背景与文字。

***

## 十一、快速参考

### 标签颜色速查

| 场景          | 颜色类                 | 示例        |
| ----------- | ------------------- | --------- |
| 已完成/成功/活跃   | `wolf-tag--success` | 已完成、活跃客户  |
| 进行中/待处理/跟进中 | `wolf-tag--info`    | 进行中、待回款   |
| 警告/VIP/暂停   | `wolf-tag--warning` | VIP、警告    |
| 失败/删除/取消    | `wolf-tag--danger`  | 已取消、删除    |
| 来源/渠道       | `wolf-tag--gray`    | 网站咨询、电话咨询 |
| 特殊/复购率      | `wolf-tag--purple`  | 技术导向      |

### 按钮尺寸速查

| 尺寸 | 类名                     | 用途   |
| -- | ---------------------- | ---- |
| 大  | `wolf-btn--lg`         | 主要操作 |
| 默认 | `wolf-btn--primary`    | 标准按钮 |
| 小  | `wolf-btn--primary-sm` | 表格操作 |
| 图标 | `wolf-btn--icon`       | 更多操作 |

### 圆角速查

| 组件     | 圆角值  | 变量                   |
| ------ | ---- | -------------------- |
| 按钮（默认） | 8px  | `--wolf-radius-md`   |
| 按钮（小）  | 4px  | `--wolf-radius-sm`   |
| 标签     | 4px  | `--wolf-radius-sm`   |
| 卡片     | 12px | `--wolf-radius-lg`   |
| 弹窗     | 16px | `--wolf-radius-xl`   |
| 头像     | 圆形   | `--wolf-radius-full` |


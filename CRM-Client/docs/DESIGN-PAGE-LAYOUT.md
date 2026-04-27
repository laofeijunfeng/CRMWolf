# CRMWolf 页面布局规范

**适用范围**：前端所有二级页面开发必读

---

## 一、布局分类

根据业务场景，系统二级页面分为两种布局模式：

| 布局类型 | 适用场景 | 特点 |
|----------|----------|------|
| 表单页面布局 | 创建/编辑页面（线索、商机、合同、发票等） | Sticky 头部 + 单卡片居中表单 + 底部操作 |
| 管理列表布局 | 系统设置页面（用户、角色、配置等） | 搜索卡片 + 表格卡片 + 分页 |

---

## 二、表单页面布局

### 2.1 页面结构

```
┌─────────────────────────────────────────┐
│ [←] 页面标题                    (sticky) │  ← 页面头部
├─────────────────────────────────────────┤
│                                         │
│     ┌─────────────────────────┐        │
│     │ 基本信息                │        │  ← 表单分区标题
│     │ ┌──────────┬──────────┐ │        │
│     │ │ 字段1    │ 字段2    │ │        │  ← 两列布局
│     │ └──────────┴──────────┘ │        │
│     │ ─────────────────────── │        │  ← 分区分割线
│     │ 联系人信息              │        │
│     │ ┌──────────┬──────────┐ │        │
│     │ │ 字段3    │ 字段4    │ │        │
│     │ └──────────┴──────────┘ │        │
│     │                         │        │
│     │ ─────────────────────── │        │  ← 操作分割线
│     │           [取消] [提交] │        │  ← 操作按钮
│     └─────────────────────────┘        │
│            max-width: 800px             │
│                                         │
└─────────────────────────────────────────┘
```

### 2.2 页面头部规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 定位 | sticky, top: 0 | 固定在顶部 |
| 高度 | 48px | 与全局 header 同高 |
| 背景 | #FFFFFF | 纯白背景 |
| 边框 | 1px solid #E5E5E0 | 底部分割线 |
| z-index | 100 | 保证在上层 |
| 内边距 | 0 24px | 左右边距 |

### 2.3 返回按钮规范

```scss
.back-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  
  &:hover {
    background: $wolf-bg-hover;  // #F0F0ED
  }
}
```

**使用方式**：必须使用 `<el-button>` 组件，不使用 `<span>`

### 2.4 表单卡片规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 最大宽度 | 800px | 居中显示 |
| 背景 | #FFFFFF | 纯白 |
| 圆角 | 12px | 卡片圆角 |
| 内边距 | 24px | 卡片内容区 |
| 阴影 | 0 1px 2px rgba(0,0,0,0.04) | 极淡阴影 |
| 外边距 | 24px auto | 居中 + 上下边距 |

### 2.5 表单分区规范

```scss
.form-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1D2129;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #F0F0ED;
}

.section-divider {
  height: 1px;
  background: #F0F0ED;
  margin: 24px 0;
}
```

### 2.6 表单布局规范

**两列布局**：使用 CSS Grid（推荐）

```scss
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  margin-bottom: 16px;
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
```

**单列布局**：用于备注、描述等长文本字段

```scss
.form-row--single {
  grid-template-columns: 1fr;
}
```

### 2.7 操作按钮规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 位置 | 卡片底部右对齐 | |
| 分割线 | 1px solid #F0F0ED | 与表单内容分隔 |
| 间距 | 12px | 两个按钮之间 |
| 取消按钮 | 次按钮样式 | 灰色背景 |
| 提交按钮 | 主按钮样式 | 品牌色填充 |

```scss
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid #F0F0ED;
}
```

---

## 三、管理列表页面布局

### 3.1 页面结构

```
┌─────────────────────────────────────────┐
│                                         │
│     ┌─────────────────────────┐        │
│     │ [筛选字段] [搜索] [重置] │        │  ← 搜索/操作卡片
│     │ [新建按钮]              │        │
│     └─────────────────────────┘        │
│                                         │
│     ┌─────────────────────────┐        │
│     │ ID │ 名称 │ 状态 │ 操作 │        │  ← 表头
│     │───│──────│──────│──────│        │
│     │ 1 │ xxx  │ 标签 │ [编辑]│        │  ← 数据行
│     │ 2 │ xxx  │ 标签 │ [编辑]│        │
│     │                         │        │
│     │ ─────────────────────── │        │
│     │ 共 N 条  [分页控件]     │        │  ← 分页区
│     └─────────────────────────┘        │
│                                         │
└─────────────────────────────────────────┘
```

### 3.2 搜索卡片规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 背景 | #FFFFFF | 纯白 |
| 圆角 | 12px | |
| 内边距 | 24px | |
| 下边距 | 16px | 与表格卡片间距 |
| 阴影 | 0 1px 2px rgba(0,0,0,0.04) | |

### 3.3 表格卡片规范

| 属性 | 值 | 说明 |
|------|-----|------|
| 背景 | #FFFFFF | 纯白 |
| 圆角 | 12px | |
| 内边距 | 24px | |
| 阴影 | 0 1px 2px rgba(0,0,0,0.04) | |

### 3.4 分页区规范

```scss
.pagination-bar {
  display: flex;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid #F0F0ED;
}

.total-text {
  font-size: 13px;
  color: #86909C;
}
```

---

## 四、弹窗/抽屉布局规范

### 4.1 弹窗尺寸

| 类型 | 宽度 | 用途 |
|------|------|------|
| 小 | 400px | 确认、简单表单 |
| 中 | 600px | 标准表单（用户创建等） |
| 大 | 800px | 复杂内容 |

### 4.2 弹窗样式

```scss
.el-dialog {
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.16);
}

.el-dialog__header {
  padding: 20px 24px;
  border-bottom: 1px solid #F0F0ED;
}

.el-dialog__body {
  padding: 24px;
}

.el-dialog__footer {
  padding: 16px 24px;
  border-top: 1px solid #F0F0ED;
}
```

### 4.3 抽屉尺寸

| 类型 | 宽度 | 用途 |
|------|------|------|
| 小 | 400px | 简单配置 |
| 中 | 600px | 标准配置 |
| 大 | 700px+ | 权限配置、详情展示 |

---

## 五、CSS 变量定义

```scss
// 页面布局
$wolf-page-padding: 24px;
$wolf-header-height: 48px;
$wolf-card-padding: 20px;
$wolf-card-radius: 12px;
$wolf-card-shadow: 0 1px 2px rgba(0,0,0,0.04);

// 表单布局
$wolf-form-max-width: 800px;
$wolf-form-grid-gap: 24px;
$wolf-form-section-gap: 24px;
$wolf-form-action-gap: 12px;

// 搜索/表格卡片
$wolf-search-card-gap: 16px;
$wolf-table-padding: 12px 24px;
```

---

## 六、页面模板

### 6.1 表单页面模板

```vue
<template>
  <div class="form-page">
    <!-- 页面头部（sticky） -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">{{ isEdit ? '编辑XX' : '新建XX' }}</h1>
      </div>
    </div>

    <!-- 表单内容 -->
    <div class="form-container">
      <div class="form-card">
        <el-form ref="formRef" :model="formData" :rules="formRules" label-position="top">
          <!-- 分区1 -->
          <div class="form-section">
            <div class="section-title">基本信息</div>
            <div class="form-grid">
              <el-form-item label="字段1" prop="field1">
                <el-input v-model="formData.field1" />
              </el-form-item>
              <el-form-item label="字段2" prop="field2">
                <el-input v-model="formData.field2" />
              </el-form-item>
            </div>
          </div>

          <div class="section-divider"></div>

          <!-- 分区2 -->
          <div class="form-section">
            <div class="section-title">其他信息</div>
            <!-- ... -->
          </div>
        </el-form>

        <!-- 操作按钮 -->
        <div class="form-actions">
          <el-button @click="handleBack">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            {{ isEdit ? '保存' : '创建' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.form-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

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

.page-header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

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

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.form-container {
  max-width: $wolf-form-max-width;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-card-radius;
  padding: $wolf-card-padding;
  box-shadow: $wolf-card-shadow;
}

.form-section {
  margin-bottom: $wolf-form-section-gap;
}

.section-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

.section-divider {
  height: 1px;
  background: $wolf-border-light;
  margin: $wolf-form-section-gap 0;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-form-grid-gap;
  margin-bottom: $wolf-space-md;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-form-action-gap;
  padding-top: $wolf-form-section-gap;
  border-top: 1px solid $wolf-border-light;
}

@media (max-width: 768px) {
  .form-container {
    padding: $wolf-space-md;
  }
  
  .form-grid {
    grid-template-columns: 1fr;
  }
  
  .form-actions {
    flex-direction: column-reverse;
    
    .el-button {
      width: 100%;
    }
  }
}
</style>
```

### 6.2 管理列表页面模板

```vue
<template>
  <div class="list-page">
    <!-- 搜索/操作卡片 -->
    <div class="wolf-card search-card">
      <el-form :model="searchForm" :inline="true">
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable style="width: 120px">
            <!-- options -->
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="请输入" clearable style="width: 150px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>
            搜索
          </el-button>
          <el-button @click="handleReset">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
          <el-button type="primary" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            新建
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 表格卡片 -->
    <div class="wolf-card table-card">
      <el-table :data="tableData" v-loading="loading" style="width: 100%">
        <!-- columns -->
      </el-table>

      <div class="pagination-bar">
        <span class="total-text">共 {{ total }} 条</span>
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          layout="sizes, prev, pager, next"
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.list-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.wolf-card {
  background: $wolf-bg-card;
  border-radius: $wolf-card-radius;
  box-shadow: $wolf-card-shadow;
  margin-bottom: $wolf-search-card-gap;
}

.search-card {
  padding: $wolf-card-padding;
}

.table-card {
  padding: $wolf-card-padding;
}

.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

.total-text {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}
</style>
```

---

## 七、布局红线

| 红线 | 说明 |
|------|------|
| 表单页面必须有 sticky 头部 | 保持导航一致性 |
| 返回按钮必须用 el-button | 不用 span/div |
| 表单卡片 max-width: 800px | 不超过此宽度 |
| 操作按钮右对齐 | 取消在左，提交在右 |
| 管理页面必须有搜索卡片 | 即使没有筛选条件也要有操作区 |
| 分页区必须有总数显示 | 左侧显示"共 N 条" |
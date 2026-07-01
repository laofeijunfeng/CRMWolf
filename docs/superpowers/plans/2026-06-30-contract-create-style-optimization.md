# 合同创建页面样式优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化合同创建页面样式，使其与商机创建页面保持一致（撑满宽度、添加分组标题、操作按钮独立卡片）

**Architecture:** 单文件 Vue 组件样式调整，参考 OpportunityEdit.vue 的结构，修改模板结构和 CSS 样式

**Tech Stack:** Vue 3, Element Plus, SCSS, Wolf Design Tokens

## Global Constraints

- 使用 Wolf Design Tokens（$wolf-* 变量）
- 保持与 OpportunityEdit.vue 结构一致
- 响应式设计（768px 断点）

---

### Task 1: 模板结构修改

**Files:**
- Modify: `CRM-Client/src/views/ContractCreate.vue:13-166` (模板部分)

**Interfaces:**
- Consumes: 无
- Produces: 新的模板结构（card-title + form-actions-card）

- [ ] **Step 1: 添加 card-title 标题**

在 `<el-form>` 标签前添加分组标题：

```vue
<!-- 在第16行 <el-form> 前添加 -->
<div class="card-title">基本信息</div>
<el-form ref="formRef" :model="form" :rules="rules" label-position="top">
```

- [ ] **Step 2: 将 form-actions 移出 form-card**

将原来的 `.form-actions` 移到 `.form-card` 外部，并改名为 `.form-actions-card`：

```vue
<!-- 原第159-165行，修改为 -->
</el-form>
</div>  <!-- 关闭 form-card -->

<div class="form-actions-card">
  <el-button @click="handleBack">取消</el-button>
  <el-button type="primary" @click="handleSubmit" :loading="submitting">
    提交
  </el-button>
</div>
</div>  <!-- 关闭 form-container -->
```

- [ ] **Step 3: 验证模板结构**

确认最终模板结构为：

```vue
<div class="form-container">
  <div class="form-card">
    <div class="card-title">基本信息</div>
    <el-form>
      <!-- 表单字段保持不变 -->
    </el-form>
  </div>

  <div class="form-actions-card">
    <el-button @click="handleBack">取消</el-button>
    <el-button type="primary" @click="handleSubmit" :loading="submitting">
      提交
    </el-button>
  </div>
</div>
```

---

### Task 2: CSS 样式修改

**Files:**
- Modify: `CRM-Client/src/views/ContractCreate.vue:414-555` (CSS 部分)

**Interfaces:**
- Consumes: Wolf Design Tokens（$wolf-bg-card, $wolf-radius-lg 等）
- Produces: 新的样式结构（.card-title, .form-actions-card）

- [ ] **Step 1: 删除 form-container 的 max-width**

修改 `.form-container` 样式，删除宽度限制：

```scss
// 原第464-468行，修改为
.form-container {
  padding: $wolf-page-padding;
}
```

- [ ] **Step 2: 删除 form-actions 样式块**

删除原有的 `.form-actions` 样式（约第525-531行）：

```scss
// 删除以下代码块
// .form-actions {
//   display: flex;
//   justify-content: flex-end;
//   gap: $wolf-space-sm;
//   padding-top: $wolf-space-lg;
//   border-top: 1px solid $wolf-border-light;
// }
```

- [ ] **Step 3: 添加 card-title 样式**

在 `.form-card` 样式后添加 `.card-title`：

```scss
// 在第475行后添加
.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;  // 添加 margin-bottom
  box-shadow: $wolf-shadow-card;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}
```

- [ ] **Step 4: 添加 form-actions-card 样式**

添加新的 `.form-actions-card` 样式：

```scss
// 在 card-title 后添加
.form-actions-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
}
```

- [ ] **Step 5: 修改响应式样式**

更新 `@media (max-width: 768px)` 部分：

```scss
// 原第534-554行，修改为
@media (max-width: 768px) {
  .form-container {
    padding: $wolf-space-md;
  }

  .form-card {
    padding: $wolf-space-md;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions-card {
    flex-direction: column-reverse;

    .el-button {
      width: 100%;
    }
  }
}
```

- [ ] **Step 6: 验证样式完整性**

确认最终样式结构包含：
- `.form-container`（无 max-width）
- `.form-card`（有 margin-bottom）
- `.card-title`（新增）
- `.form-actions-card`（新增，替代 form-actions）

---

### Task 3: 验证和提交

**Files:**
- Test: 浏览器手动验证

- [ ] **Step 1: 启动开发服务器**

```bash
cd CRM-Client
npm run dev
```

- [ ] **Step 2: 浏览器验证**

访问合同创建页面 `/contracts/create`，确认：

1. ✅ 页面横向撑满（无 max-width 限制）
2. ✅ form-card 内有 "基本信息" 标题
3. ✅ 操作按钮在独立的白色卡片内
4. ✅ 移动端响应式正常（调整浏览器宽度测试）

- [ ] **Step 3: 提交改动**

```bash
cd CRMWolf
git add CRM-Client/src/views/ContractCreate.vue
git commit -m "style: optimize contract create page layout

- Remove max-width constraint, page now fills full width
- Add '基本信息' section title in form-card
- Move action buttons to independent form-actions-card
- Match OpportunityEdit.vue style structure"
```

---

## Self-Review Checklist

| 检查项 | 状态 |
|--------|------|
| Spec 覆盖完整 | ✅ 所有改动点已覆盖 |
| 无 Placeholders | ✅ 所有步骤有完整代码 |
| 类型一致性 | ✅ 无类型问题 |
| 任务独立性 | ✅ 可独立测试验证 |
# 合同创建页面样式优化设计

日期：2026-06-30

## 背景

合同创建页面（ContractCreate.vue）样式与商机创建页面（OpportunityEdit.vue）不一致，需要统一优化。

## 现状问题

1. **宽度限制**：`.form-container` 设置了 `max-width: 800px`，导致页面横向不撑满
2. **缺少分组标题**：form-card 内没有 "基本信息" 标题
3. **操作按钮位置**：`.form-actions` 在 form-card 内部，而非独立卡片

## 目标设计

参考商机创建页面（OpportunityEdit.vue）的样式结构：
- 表单撑满页面宽度
- form-card 内添加 "基本信息" 分组标题
- 操作按钮独立为 form-actions-card

## 改动清单

### 1. 模板改动

**位置**：`CRM-Client/src/views/ContractCreate.vue`

```vue
<!-- 改动前 -->
<div class="form-container">
  <div class="form-card">
    <el-form>
      <!-- 表单字段 -->
    </el-form>

    <div class="form-actions">
      <el-button>取消</el-button>
      <el-button type="primary">提交</el-button>
    </div>
  </div>
</div>

<!-- 改动后 -->
<div class="form-container">
  <div class="form-card">
    <div class="card-title">基本信息</div>
    <el-form>
      <!-- 表单字段 -->
    </el-form>
  </div>

  <div class="form-actions-card">
    <el-button>取消</el-button>
    <el-button type="primary">提交</el-button>
  </div>
</div>
```

### 2. CSS 改动

**位置**：`CRM-Client/src/views/ContractCreate.vue` `<style>` 部分

```scss
// 删除
.form-container {
  max-width: 800px;  // ❌ 删除这行
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.form-actions {  // ❌ 删除整个样式块
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding-top: $wolf-space-lg;
  border-top: 1px solid $wolf-border-light;
}

// 添加（与 OpportunityEdit.vue 保持一致）
.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

.form-actions-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
}

// 修改 form-card 样式
.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;  // 添加 margin-bottom，与 actions-card 分隔
  box-shadow: $wolf-shadow-card;
}
```

### 3. 响应式样式调整

```scss
@media (max-width: 768px) {
  // 删除原有的 .form-actions 响应式样式
  // 添加 .form-actions-card 响应式样式
  .form-actions-card {
    flex-direction: column-reverse;

    .el-button {
      width: 100%;
    }
  }
}
```

## 文件改动范围

| 文件 | 改动行数 |
|------|----------|
| `CRM-Client/src/views/ContractCreate.vue` | ~20 行（模板 + CSS） |

## 验收标准

1. 页面横向撑满（无 max-width 限制）
2. form-card 内有 "基本信息" 标题
3. 操作按钮在独立的白色卡片内
4. 移动端响应式正常（按钮堆叠）
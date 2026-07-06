---
name: license-management-ui-supplement
description: License 授权码管理 UI/UX 视觉设计补充说明
created: 2026-07-06
status: supplement
---

# License 授权码管理 UI/UX 视觉设计补充说明

> **用途**: 本文档为 `2026-07-06-license-management-implementation.md` 实施计划的 UI/UX 补充章节（Phase 8: Task 21-27），详细说明前端视觉设计细节，确保与 CRMWolf 设计系统无缝融合。

---

## 一、导航结构优化 - 合并单一 Tab

### 1.1 设计方案

**问题**: 原设计提议新增两个独立 Tab（部署信息 + License 申请），会增加导航复杂度。

**方案**: 合并为单一 **"授权管理" Tab**，采用两段式布局：

```
┌────────────────────────────────────────────────────────────┐
│ 授权管理                                    [+ 部署信息] │
├────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────│
│ │ 部署信息                                                 │
│ │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│ │ │ 生产环境    │ │ 测试环境    │ │ + 新增      │        │
│ │ │ 10.1.2.3   │ │ 默认 ✓      │ │             │        │
│ │ │ 100人       │ │ 50人        │ │             │        │
│ │ └─────────────┘ └─────────────┘ └─────────────┘        │
│ └─────────────────────────────────────────────────────────│
│                                                            │
│ ┌─────────────────────────────────────────────────────────│
│ │ License 申请                             [+ 申请授权] │
│ │ ┌───────────────────────────────────────────────────────│
│ │ │ LIC-2026-001  正式 License  2026-12-31  ✓ 已发放   │ │
│ │ │ LIC-2026-002  试用 License  2026-07-17  ⏳ 待审批   │ │
│ │ └───────────────────────────────────────────────────────│
│ └─────────────────────────────────────────────────────────│
└────────────────────────────────────────────────────────────┘
```

### 1.2 导航项图标

使用 `Key` 图标（Element Plus Icons）区别于其他业务模块：

```typescript
// CustomerDetailSidebar.vue 导航项新增
import { Key } from '@element-plus/icons-vue'

const navItems = [
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets },
  { key: 'license', label: '授权', icon: Key }  // 新增
]
```

---

## 二、部署信息卡片视觉设计

### 2.1 卡片结构

参照发票抬头卡片（`invoice-title-item`）结构，增加技术 vernacular 特征：

```
┌────────────────────────────────────┐
│ 生产环境            [默认 ✓]       │ ← deployment_name + is_default 标签
│                                    │
│ 🌐 https://crm.example.com:8891   │ ← server_address（mono 字体）
│ 👥 授权人数: 100                   │ ← authorized_users
│                                    │
│           [编辑] [删除]             │ ← 操作按钮
└────────────────────────────────────┘
```

### 2.2 样式规范

```scss
@use '@/styles/variables.scss' as *;

// 部署信息卡片样式
.deployment-info-item {
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border: 1px solid $wolf-border-default;
  border-radius: $wolf-radius-md;
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    border-color: $wolf-primary;
    box-shadow: $wolf-shadow-card;
  }

  &.is-default {
    border-color: $wolf-success-text;
    background: $wolf-success-bg;
  }

  // Signature: 服务器地址使用 IBM Plex Mono（技术 vernacular）
  .server-address {
    font-family: $wolf-font-mono;
    font-size: $wolf-font-size-caption;
    color: $wolf-text-secondary;
    background: $wolf-primary-light;  // URL 风格：浅蓝底色区分
    padding: 2px 6px;
    border-radius: $wolf-radius-sm;
  }
}
```

### 2.3 卡片网格布局

```scss
.deployment-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: $wolf-space-md;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}
```

---

## 三、License 申请状态徽章

### 3.1 状态枚举

| 后端状态 | 前端文案 | 颜色 token | 图标 |
|----------|----------|------------|------|
| DRAFT | 草稿 | `--wolf-text-tertiary` | EditPen |
| PENDING | 待审批 | `--wolf-approval-pending-text` | Clock |
| APPROVED | 已批准 | `--wolf-approval-approved-text` | CircleCheckFilled |
| REJECTED | 已驳回 | `--wolf-approval-rejected-text` | CircleCloseFilled |
| ISSUED | 已发放 | `--wolf-success-text` | Key |

### 3.2 ApprovalStatusBadge 更新

新增 ISSUED 状态映射（使用 Key 图标作为 signature）：

```typescript
import { Key } from '@element-plus/icons-vue'

const STATUS_MAP: Record<ApprovalStatus, StatusConfig> = {
  // ... 其他状态
  ISSUED: {
    label: '已发放',
    icon: Key,  // Signature: 使用钥匙图标
    textVar: '--wolf-success-text',
    bgVar: '--wolf-success-bg'
  }
}
```

---

## 四、申请表单 UI 细化

### 4.1 动态表单逻辑

**表单布局**（参照 invoice-title-form-dialog）：

```
┌─────────────────────────────────────────────────────┐
│ 申请 License 授权                                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 部署信息                                            │
│ ┌─────────────────────────────────────────────────┐│
│ │ [下拉选择] 生产环境 (默认)          [+ 新增]    ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│ License 类型                                        │
│ ○ 试用 License (TRIAL)                             │
│ ● 正式 License (OFFICIAL)                          │
│                                                     │
│ 关联合同 ← 正式 License 时显示                     │
│ ┌─────────────────────────────────────────────────┐│
│ │ [下拉选择] HT-2026-001 销售合同                ││
│ │              合同金额: ¥50,000                  ││
│ │              状态: ✓ 生效中                     ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│ 到期时间                                            │
│ ┌─────────────────────────────────────────────────┐│
│ │ [日期选择器] 2026-12-31                        ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│ 备注 (可选)                                         │
│ ┌─────────────────────────────────────────────────┐│
│ │ [文本框] 需要开通 desktop,web,branch 模块      ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│                      [取消] [提交申请]              │
└─────────────────────────────────────────────────────┘
```

### 4.2 动态表单实现

```vue
<!-- 正式 License 时动态显示合同字段 -->
<el-form-item
  v-show="form.license_type === 'OFFICIAL'"
  label="关联合同"
  prop="contract_id"
  :required="form.license_type === 'OFFICIAL'"
>
  <el-select v-model="form.contract_id" placeholder="选择合同（仅生效中或已签约）">
    <el-option
      v-for="c in effectiveContracts"
      :key="c.id"
      :label="c.contract_name"
      :value="c.id"
    >
      <div style="display: flex; justify-content: space-between">
        <span>{{ c.contract_name }}</span>
        <el-tag :class="getContractStatusClass(c.status)" size="small">{{ c.status_info?.name }}</el-tag>
      </div>
    </el-option>
  </el-select>
</el-form-item>
```

```typescript
// License 类型切换时清空合同字段
const handleLicenseTypeChange = (value: string) => {
  if (value === 'TRIAL') {
    form.value.contract_id = null
  }
}

// 动态校验规则
const rules = computed(() => ({
  contract_id: form.value.license_type === 'OFFICIAL'
    ? [{ required: true, message: '正式 License 必须关联合同' }]
    : []
}))
```

---

## 五、审批对话框 License 信息输入

### 5.1 UI 设计

```
┌─────────────────────────────────────────────────────┐
│ License 审批详情                                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 申请信息                                            │
│ ┌─────────────────────────────────────────────────┐│
│ │ 申请单号: LIC-2026-001                         ││
│ │ 客户: 广东智通人才连锁股份有限公司             ││
│ │ 类型: 正式 License                             ││
│ │ 到期时间: 2026-12-31                           ││
│ │ 部署信息: 生产环境 (100人)                     ││
│ │ 关联合同: HT-2026-001                          ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│ ⚠️ 授权码填写（必填）                              │
│ ┌─────────────────────────────────────────────────┐│
│ │ [多行文本框 - IBM Plex Mono 字体]              ││
│ │ 企业编号: 15739                                ││
│ │ 支持模块: desktop,web,branch                   ││
│ │ 服务端 License:                                ││
│ │ iHE43m7q//cI+...                               ││
│ │                                                ││
│ │ 客户端 License:                                ││
│ │ NPR7aI2qGG1G...                                ││
│ └─────────────────────────────────────────────────┘│
│                                                     │
│              [拒绝] [通过并发放授权码]              │
└─────────────────────────────────────────────────────┘
```

### 5.2 样式规范

```scss
.license-code-input {
  :deep(.el-textarea__inner) {
    font-family: $wolf-font-mono;  // Signature: 技术 vernacular
    font-size: $wolf-font-size-caption;
    background: $wolf-bg-page;
    border: 1px solid $wolf-border-default;
    border-radius: $wolf-radius-sm;
    line-height: 1.6;
    min-height: 200px;
  }
}

.license-format-hint {
  margin-top: 12px;
  padding: 12px;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
}

.license-format-example {
  font-family: $wolf-font-mono;
  font-size: 11px;
  color: $wolf-text-tertiary;
  background: $wolf-bg-card;
  padding: 12px;
  border-radius: $wolf-radius-sm;
  white-space: pre-wrap;
}
```

### 5.3 Signature Element

- 审批通过按钮文案：**"通过并发放授权码"**（明确动作）
- License 信息输入框使用 `$wolf-font-mono` 字体
- 禁用状态：License 信息为空时禁用通过按钮

---

## 六、Empty States 和 Loading States

### 6.1 部署信息空状态

```
┌─────────────────────────────────────────────────────┐
│                    🌐                               │
│                                                    │
│           添加部署信息，配置服务器地址              │
│                                                    │
│              [+ 添加部署信息]                       │
└─────────────────────────────────────────────────────┘
```

**文案**: "添加部署信息，配置服务器地址"

### 6.2 License 申请空状态

```
┌─────────────────────────────────────────────────────┐
│                    🔑                               │
│                                                    │
│           申请 License 授权，管理产品授权           │
│                                                    │
│              [+ 申请授权]                           │
└─────────────────────────────────────────────────────┘
```

**文案**: "申请 License 授权，管理产品授权"

### 6.3 Loading States

使用 Element Plus `v-loading` 指令：
- 最小高度：120px
- 加载文案："加载中..."

---

## 七、无障碍设计

### 7.1 键盘导航

- 部署信息卡片：`tabindex="0"` + `@keydown.enter` 跳转编辑
- 申请表单：焦点顺序符合逻辑（部署信息 → 类型 → 合同 → 到期时间 → 备注 → 提交）
- 导出按钮：`aria-label="导出 License 授权文件 Word 文档"`

### 7.2 颜色非唯一指示

所有状态标签必须包含：
- 图标 + 文字（满足 WCAG AA）
- 颜色仅作为辅助区分

### 7.3 Reduced Motion

```scss
@media (prefers-reduced-motion: reduce) {
  .deployment-info-item,
  .license-application-item {
    transition: none;
  }
}
```

---

## 八、响应式设计

### 8.1 移动端适配

**部署信息卡片**:
- 768px 以下：卡片宽度 100%，服务器地址自动截断（`overflow: hidden; text-overflow: ellipsis`）

**申请表单**:
- 合同下拉框：显示合同金额摘要（隐藏状态标签）
- 到期时间选择器：使用原生日期选择器（避免 Element Plus 弹窗遮挡）

### 8.2 Sidebar 折叠适配

参照 CustomerDetailSidebar.scss 的响应式断点：
- 768-1024px：icon-only 模式（使用 `Key` 图标）
- <768px：顶部横向标签（flex-wrap）

---

## 九、Signature Elements - 独特视觉标识

### 9.1 License 专属图标

**导航图标**: `Key`（钥匙）- 区别于其他业务模块

**状态徽章图标**: ISSUED 状态使用 `Key` 图标（而非通用的 CircleCheck）

### 9.2 服务器地址技术 vernacular

**字体**: `IBM Plex Mono`（已在 variables.scss 定义）

**视觉处理**:
- 浅蓝底色（`$wolf-primary-light`）
- 圆角标签（`$wolf-radius-sm`）
- 类似代码片段的视觉暗示

### 9.3 授权码填写区特殊样式

审批页面的授权码填写框使用技术 vernacular：
- `font-family: $wolf-font-mono`
- `background: $wolf-bg-page`
- `border: 1px solid $wolf-border-default`
- 多行授权码使用 textarea（`min-height: 200px`）

---

## 十、补充细节

### 10.1 状态文案统一

| 后端状态 | 前端文案 | 说明 |
|----------|----------|------|
| DRAFT | 草稿 | 申请创建未提交 |
| PENDING | 待审批 | 提交后等待审批 |
| APPROVED | 已批准 | 审批人批准但未回填授权码 |
| REJECTED | 已驳回 | 审批人拒绝 |
| ISSUED | 已发放 | 审批人回填授权码后 |

### 10.2 提示文案规范

| 场景 | 提示文案 |
|------|----------|
| 创建部署成功 | "部署信息添加成功" |
| 删除部署成功 | "部署信息删除成功" |
| 提交申请成功 | "申请已提交，等待审批" |
| 审批通过成功 | "授权码已发放" |
| 导出成功 | "授权文件已导出" |

### 10.3 校验错误提示

| 校验规则 | 错误提示 |
|----------|----------|
| 正式 License 无合同 | "正式 License 必须关联合同" |
| 合同状态非生效 | "仅可选择生效中或已签约的合同" |
| 到期时间过期 | "到期时间必须大于今天" |
| 授权码未填写 | "请填写完整授权码信息" |

---

## 十一、新增样式 token 建议

```scss
// variables.scss 新增（如有）
$wolf-license-code-bg: $wolf-primary-light;  // 授权码输入框背景
$wolf-license-code-border: $wolf-border-default;

// 审批状态新增 ISSUED（已在 ApprovalStatusBadge 建议中包含）
$wolf-approval-issued-text: $wolf-success-text;
$wolf-approval-issued-bg: $wolf-success-bg;
```

---

## 十二、组件文件建议

| 组件 | 路径 | 说明 |
|------|------|------|
| DeploymentInfoCard.vue | `components/DeploymentInfoCard.vue` | 部署信息卡片 |
| LicenseApplicationList.vue | `components/LicenseApplicationList.vue` | License 申请列表 |
| LicenseApplicationForm.vue | `components/LicenseApplicationForm.vue` | 申请表单弹窗 |
| LicenseApprovalDetail.vue | `components/LicenseApprovalDetail.vue` | 审批详情页 |
| DeploymentInfoDialog.vue | `components/DeploymentInfoDialog.vue` | 部署信息编辑弹窗 |

---

## 十三、总结

以上 UI/UX 补充聚焦于：

1. **视觉一致性**: 复用发票抬头模式（卡片结构、表单布局）
2. **交互细节**: 动态表单、状态区分、明确按钮文案
3. **无障碍**: WCAG AA 合规（图标 + 文字 + 颜色）
4. **Signature 元素**: Key 图标、IBM Plex Mono 字体、技术 vernacular

确保 License 功能与现有 CRMWolf 系统设计系统无缝融合，同时保留独特的技术特征。
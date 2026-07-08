# CRMWolf 页面结构规范 - 审批中心

**适用页面**：审批中心（ApprovalCenter.vue）

---

## 一、页面组成

### 1.1 导航层级

```
Sidebar（一级导航，固定）
└── TopBar（顶部栏，固定）
    └── Approval Content（审批内容区域）
```

### 1.2 组件清单

| 位置 | 组件 | 高度 | 说明 |
|------|------|------|------|
| **左侧** | `SidebarV2` | 100vh | 全局菜单，固定不动 |
| **顶部** | `TopBarV2` | 56px | 包含页面标题 |
| **右侧固定** | `ApprovalIcon` | 40px | 审批铃铛（顶部栏内） |
| **内容** | Tabs + Tables | 自适应 | 审批类型标签 + 待审批列表 |

---

## 二、审批铃铛设计

### 2.1 ApprovalIcon（顶部栏右侧）

| 属性 | 值 |
|------|-----|
| **位置** | TopBar 右侧最右 |
| **尺寸** | 40px × 40px |
| **图标** | 🔔 铃铛图标（SVG） |
| **Badge** | 待审批数量（红色圆点） |

### 2.2 Badge 样式

| 属性 | 值 |
|------|-----|
| **背景** | `#DC2626`（红色） |
| **字号** | 10px |
| **圆角** | 10px（圆形） |
| **位置** | 铃铛图标右上角 |

---

## 三、审批中心布局

### 3.1 审批类型标签

**位置**：内容区域顶部，横向标签栏

| 标签 | Badge | 内容 |
|------|-------|------|
| **合同审批** | 3 | 合同待审批列表 |
| **回款审批** | 2 | 回款登记待审批列表 |
| **发票审批** | 0 | 发票待审批列表 |

### 3.2 标签样式（参考 ContextTabs）

| 属性 | 值 |
|------|-----|
| **高度** | 48px |
| **圆角** | 6px |
| **字号** | 14px |
| **字重 active** | 600 |

---

## 四、待审批表格规范

### 4.1 表格列设计

| 列 | 说明 | 对齐 |
|------|------|------|
| **提交人** | 提交审批的人员 | 左对齐 |
| **提交时间** | 审批提交时间 | 左对齐 |
| **业务类型** | 合同/回款/发票 | 居中 |
| **金额** | 审批金额 | 右对齐 |
| **状态** | 待审批/审批中 | 居中 |
| **操作** | 审批/驳回按钮 | 居中 |

### 4.2 操作按钮

| 按钮 | 类型 | 尺寸 |
|------|------|------|
| **审批通过** | Primary（Success） | md |
| **驳回** | Danger | md |

### 4.3 状态 Badge

| 状态 | 背景色 | 文字色 |
|------|--------|--------|
| **待审批** | `#FEF3C7` | `#92400E` |
| **审批中** | `#FEF3C7` | `#92400E` |

---

## 五、审批详情设计

### 5.1 点击审批按钮后的流程

1. **打开审批详情 Modal**
2. **显示审批详情卡片**
3. **审批时间线（ApprovalTimeline）**
4. **审批/驳回按钮**

### 5.2 ApprovalProgressCompact

**位置**：审批详情 Modal 内，进度指示器

| 元素 | 说明 |
|------|------|
| **进度条** | 审批进度（0-100%） |
| **当前节点** | 当前审批节点标记 |
| **节点列表** | 所有审批节点（横向排列） |

---

## 六、审批时间线（ApprovalTimeline）

### 6.1 时间线布局

| 元素 | 说明 |
|------|------|
| **节点** | 审批节点（圆形图标） |
| **连线** | 节点之间连线 |
| **状态** | 待审批/已通过/已驳回 |
| **时间** | 审批时间 |

### 6.2 时间线样式

| 节点状态 | 图标颜色 | 连线颜色 |
|---------|---------|---------|
| **已通过** | `#10B981`（绿色） | `#10B981` |
| **当前节点** | `#2563EB`（蓝色） | `#E4ECFC` |
| **待审批** | `#94A3B8`（灰色） | `#E4ECFC` |

---

## 七、交互动效

### 7.1 点击审批铃铛

| 效果 | 说明 |
|------|------|
| **打开审批中心** | 跳转到 `/approvals` |
| **Badge 清除** | 访问后 Badge 数量更新 |

### 7.2 审批操作

| 操作 | 效果 |
|------|------|
| **点击"审批通过"** | 打开 Modal，显示详情 |
| **确认审批** | 表格行消失（状态更新） |

---

## 八、代码示例

### 8.1 ApprovalIcon（伪代码）

```vue
<template>
  <div class="approval-icon" @click="openApprovalCenter">
    <svg class="bell-icon">
      <!-- 铃铛 SVG -->
    </svg>
    <div v-if="count > 0" class="badge">{{ count }}</div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-icon {
  width: 40px;
  height: 40px;
  cursor: pointer;
  position: relative;
  
  &:hover {
    background: $wolf-bg-hover-v2;
  }
  
  .badge {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 18px;
    height: 18px;
    background: $wolf-danger-v2;
    color: white;
    font-size: 10px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
}
</style>
```

---

## 九、导航入口优化

### 9.1 审批入口唯一性

**原则**：
- ✅ **唯一入口**：Header ApprovalIcon（铃铛）
- ❌ **移除左侧菜单审批项**（已优化）

### 9.2 审批路由

| 路由 | 说明 |
|------|------|
| `/approvals` | 统一审批中心 |
| `/finance/approvals` | 重定向到 `/approvals` |
| `/finance/invoice-approvals` | 重定向到 `/approvals` |
| `/finance/payment-confirmations` | 重定向到 `/approvals` |

---

**适用页面**：
- 审批中心（ApprovalCenter.vue）

**相关组件**：
- ApprovalIcon.vue
- ApprovalTimeline.vue
- ApprovalProgressCompact.vue

**版本：V2 | 最后更新：2026-07-08**
---
status: optimization_plan
created: 2026-06-23
priority: high
type: ux-optimization
---

# CRMWolf 现有功能 UI/UX 优化方案（无新增功能）

**目标**：仅优化现有功能的视觉和交互体验  
**约束**：不新增功能模块  
**预期评分**：6.4/10 → 8/10

---

## 一、优化可行性分析

### 1.1 当前功能清单

| 功能模块 | 已实现 | UI/UX 可优化点 |
|---------|--------|----------------|
| **侧边栏导航** | ✅ | 折叠动画、hover 反馈、active 标识 |
| **客户列表** | ✅ | 行 hover 样式、筛选区视觉、空状态 |
| **客户详情** | ✅ | 信息布局、卡片间距、标签样式 |
| **商机列表** | ✅ | 同客户列表 |
| **商机详情** | ✅ | 同客户详情 |
| **合同管理** | ✅ | 同客户列表 |
| **AI 助手** | ✅ | 输入区样式、气泡间距、执行过程视觉 |
| **表格组件** | ✅ | 行 hover、斑马纹优化、单元格间距 |
| **表单组件** | ✅ | 标签对齐、错误提示样式、必填标识 |
| **筛选区** | ✅ | 布局优化、按钮间距、分隔线 |
| **空状态** | ✅ | 插图、引导文案、操作提示 |

### 1.2 评分提升路径

| 维度 | 当前 | 优化后 | 仅优化提升 |
|------|------|--------|-----------|
| **视觉一致性** | 7/10 | 9/10 | +2 (Design Token 已完善) |
| **信息层级** | 8/10 | 9/10 | +1 (间距/字号微调) |
| **表格交互** | 6/10 | 8/10 | +2 (hover 样式优化) |
| **表单体验** | 5/10 | 7/10 | +2 (错误提示样式优化) |
| **加载状态** | 6/10 | 7/10 | +1 (局部加载提示) |
| **空状态** | 5/10 | 7/10 | +2 (视觉优化) |
| **导航反馈** | 7/10 | 9/10 | +2 (hover/active 优化) |
| **整体评分** | **6.4** | **8.0** | **+1.6** |

---

## 二、具体优化清单（仅 UI/UX）

### 2.1 侧边栏导航优化（+2 分）

**当前问题**：
- hover 背景色变化不够明显
- active 状态仅靠颜色区分
- 无过渡动画

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **hover 反馈** | 背景色 `$wolf-bg-hover` | 增加左侧指示条 + 背景色渐变 | 0.5 天 |
| **active 状态** | 背景色 + 文字色 | 左侧 2px 高亮条 + 背景 + 文字 | 0.5 天 |
| **过渡动画** | `transition: background 0.2s` | 添加左侧条动画 | 0.5 天 |
| **图标 hover** | 颜色不变 | 颜色同步变化 + 微放大 | 0.5 天 |

**代码示例**：
```scss
.menu-item {
  // 现有样式
  padding: $wolf-space-md;
  cursor: $wolf-cursor-clickable;  // 已添加
  transition: all 0.15s ease;       // 优化：缩短时长
  border-radius: $wolf-radius-sm;
  
  // 新增：左侧指示条
  position: relative;
  
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 16px;
    background: $wolf-primary;
    border-radius: 0 2px 2px 0;
    transition: width 0.15s ease;
  }
  
  &:hover::before {
    width: 3px;  // hover 时微指示
  }
  
  &.active::before {
    width: 4px;  // active 时明显指示
  }
}
```

---

### 2.2 表格交互优化（+2 分）

**当前问题**：
- stripe 斑马纹过于明显
- hover 背景色不够清晰
- 无行内操作入口

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **斑马纹** | Element Plus 默认 stripe | 改为更淡的分隔线 | 0.5 天 |
| **hover 背景** | 默认色 | 自定义 `$wolf-table-hover-bg` | 0.5 天 |
| **行内操作** | 无 | Hover 显示快捷按钮（查看/编辑） | 1 天 |
| **行选中** | 无 | 添加选中行高亮样式 | 0.5 天 |
| **单元格间距** | 默认 | 调整为 `$wolf-table-cell-padding` | 0.5 天 |

**代码示例**：
```scss
// 表格行样式优化
.el-table {
  // 斑马纹优化：改为极淡分隔线
  .el-table__row {
    border-bottom: 1px solid $wolf-border-light;
    
    // hover 状态优化
    &:hover > td {
      background: $wolf-table-hover-bg !important;
      transition: background 0.15s ease;
    }
    
    // 选中状态
    &.current-row > td {
      background: $wolf-table-selected-bg !important;
    }
  }
  
  // 行内操作按钮（hover 显示）
  .row-actions {
    opacity: 0;
    transition: opacity 0.15s ease;
    
    .el-table__row:hover .row-actions {
      opacity: 1;
    }
  }
}
```

---

### 2.3 筛选区视觉优化（+1 分）

**当前问题**：
- 筛选项平铺，视觉负担重
- 按钮间距不统一
- 无分隔视觉

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **筛选项分组** | 平铺一行 | 左侧搜索 + 中间筛选 + 右侧按钮 | 0.5 天 |
| **分隔线** | 无 | 筛选项与按钮间添加分隔线 | 0.5 天 |
| **按钮间距** | 不统一 | 统一 `$wolf-button-gap-sm` (8px) | 0.5 天 |
| **重置按钮样式** | 默认 | 降低视觉权重（text 类型） | 0.5 天 |
| **筛选标签** | 无 | 已筛选条件显示为标签 | 1 天 |

**代码示例**：
```vue
<!-- 筛选区布局优化 -->
<div class="filter-card">
  <div class="filter-row">
    <!-- 搜索（强调） -->
    <div class="filter-left">
      <el-input class="search-input" placeholder="搜索" />
    </div>
    
    <!-- 分隔线 -->
    <div class="filter-divider"></div>
    
    <!-- 筛选项（次要） -->
    <div class="filter-center">
      <el-select placeholder="行业" class="filter-item" />
      <el-input placeholder="城市" class="filter-item" />
    </div>
    
    <!-- 分隔线 -->
    <div class="filter-divider"></div>
    
    <!-- 操作按钮 -->
    <div class="filter-right">
      <el-button text>重置</el-button>  <!-- 降低权重 -->
      <el-button type="primary">查询</el-button>
      <el-button type="primary">新建</el-button>
    </div>
  </div>
  
  <!-- 已筛选标签 -->
  <div v-if="hasFilters" class="active-filters">
    <el-tag 
      v-for="f in activeFilters" 
      :key="f.key"
      closable
      @close="removeFilter(f.key)"
    >
      {{ f.label }}
    </el-tag>
    <el-button text size="small" @click="clearAllFilters">清除全部</el-button>
  </div>
</div>
```

---

### 2.4 表单体验优化（+2 分）

**当前问题**：
- 必填标识不明显
- 错误提示样式突兀
- 标签与输入框间距不统一

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **必填标识** | 红色 * | 改为 `*` 前置 + 灰色文字提示 | 0.5 天 |
| **错误提示** | 红色文字 | 浅红背景 + 图标 + 文字 | 0.5 天 |
| **标签对齐** | 默认 | 统一右对齐 + 固定宽度 | 0.5 天 |
| **输入框 hover** | 默认边框色 | 边框色加深 + 背景微变化 | 0.5 天 |
| **帮助提示** | 无 | Tooltip 显示填写示例 | 1 天 |

**代码示例**：
```scss
// 表单项样式优化
.el-form-item {
  // 标签样式优化
  .el-form-item__label {
    text-align: right;
    width: 100px;  // 固定宽度对齐
    padding-right: $wolf-space-sm;
    
    // 必填标识优化
    .el-form-item__label-content::before {
      content: '';
      margin-right: 4px;
    }
  }
  
  // 输入框样式优化
  .el-input__wrapper {
    transition: all 0.15s ease;
    
    &:hover {
      box-shadow: 0 0 0 1px $wolf-border-hover inset;
    }
  }
  
  // 错误提示样式优化
  .el-form-item__error {
    background: rgba($wolf-danger-bg, 0.8);
    padding: 4px 8px;
    border-radius: $wolf-radius-sm;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    
    &::before {
      content: '⚠️';  // 或使用图标
    }
  }
}
```

---

### 2.5 空状态优化（+2 分）

**当前问题**：
- Element Plus 默认插图
- 无操作引导
- 文案过于技术化

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **自定义插图** | Element Plus 默认 | 品牌风格插图 | 1 天 |
| **引导文案** | "暂无数据" | 业务化引导文案 | 0.5 天 |
| **操作按钮** | 无 | 添加主要操作按钮 | 0.5 天 |
| **视觉层级** | 单一 | 标题 + 文案 + 按钮 + 插图 | 0.5 天 |

**代码示例**：
```vue
<!-- 空状态优化 -->
<div class="empty-state-guide">
  <!-- 自定义插图 -->
  <div class="empty-illustration">
    <!-- 品牌风格 SVG，非 Element Plus 默认 -->
    <svg viewBox="0 0 120 120">
      <!-- 简化的客户/商机图标 -->
    </svg>
  </div>
  
  <!-- 标题 -->
  <div class="empty-title">
    {{ contextBasedTitle }}
  </div>
  
  <!-- 引导文案 -->
  <div class="empty-hint">
    {{ contextBasedHint }}
  </div>
  
  <!-- 操作按钮 -->
  <el-button type="primary" @click="handlePrimaryAction">
    <el-icon><Plus /></el-icon>
    {{ primaryActionText }}
  </el-button>
</div>
```

---

### 2.6 详情页信息布局优化（+1 分）

**当前问题**：
- 信息层级不够清晰
- 卡片间距不统一
- 标签样式单一

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **信息分组** | 无明确分组 | 左侧核心信息 + 右侧统计 | 0.5 天 |
| **分隔线样式** | 简单 div | 渐变分隔线或留白分隔 | 0.5 天 |
| **标签样式** | 状态标签 | 状态 + 行业 + 规模标签分层 | 0.5 天 |
| **卡片间距** | 不统一 | `$wolf-section-gap` (24px) | 0.5 天 |

---

### 2.7 AI 助手界面优化（+1 分）

**当前问题**：
- 输入区样式简单
- 气泡间距不统一
- 执行过程视觉单调

**优化方案**：

| 优化项 | 当前实现 | 优化后 | 工作量 |
|--------|----------|--------|--------|
| **输入区样式** | 基础 el-input | 添加智能边界线视觉 | 0.5 天 |
| **气泡间距** | 默认 | `$wolf-space-md` (16px) | 0.5 天 |
| **执行过程** | ThinkingBubble | 已优化（10/10） | ✅ 完成 |
| **时间戳样式** | 默认 | IBM Plex Mono + 右对齐 | 0.5 天 |

---

### 2.8 整体视觉一致性优化（+2 分）

**当前问题**：
- 部分页面间距不一致
- 某些组件魔数
- Element Plus 默认样式残留

**优化方案**：

| 优化项 | 检查范围 | 工作量 |
|--------|----------|--------|
| **间距审计** | 全部页面替换魔数为 Design Token | 2 天 |
| **Element Plus 覆盖** | 检查并覆盖默认样式 | 1 天 |
| **全局过渡时长** | 统一为 `$wolf-transition-fast` (0.15s) | 0.5 天 |
| **圆角一致性** | 检查并统一为 `$wolf-radius-*` | 0.5 天 |

---

## 三、工作量汇总

| 优化项 | 工作量 | 评分提升 |
|--------|--------|----------|
| 侧边栏导航优化 | 2 天 | +2 分 |
| 表格交互优化 | 3 天 | +2 分 |
| 筛选区视觉优化 | 2.5 天 | +1 分 |
| 表单体验优化 | 3 天 | +2 分 |
| 空状态优化 | 2.5 天 | +2 分 |
| 详情页布局优化 | 2 天 | +1 分 |
| AI 助手界面优化 | 1.5 天 | +1 分 |
| 整体视觉一致性 | 4 天 | +2 分 |
| **总计** | **18.5 天** | **+11 分（各维度）** |

---

## 四、实施路线（3 周）

### Week 1：核心交互

```
Day 1-2: 侧边栏导航优化（hover/active/过渡）
Day 3-4: 表格 hover + 行内操作
Day 5: 筛选区布局优化
```

### Week 2：表单与空状态

```
Day 1-2: 表单样式优化（必填标识/错误提示）
Day 3: 表单帮助提示
Day 4-5: 空状态优化（插图/文案/按钮）
```

### Week 3：细节与一致性

```
Day 1-2: 详情页布局优化
Day 3: AI 助手细节优化
Day 4-5: 全局一致性审计
```

---

## 五、预期效果对比

### 5.1 视觉对比

**优化前**：
```
┌─────────────────────────────────┐
│ [图标] 客户管理              →  │ ← hover 仅背景变化
│ [图标] 商机管理              →  │ ← active 仅文字色
└─────────────────────────────────┘
```

**优化后**：
```
┌─────────────────────────────────┐
│ │ [图标] 客户管理              │ ← hover 左侧指示条
│ ██ [图标] 商机管理              │ ← active 明显指示条
└─────────────────────────────────┘
```

### 5.2 表格对比

**优化前**：
```
斑马纹明显、hover 弱、无行内操作
```

**优化后**：
```
极淡分隔线、hover 背景明显、hover 显示操作按钮
```

### 5.3 空状态对比

**优化前**：
```
[Element Plus 默认插图]
暂无数据
```

**优化后**：
```
[品牌风格插图]
还没有客户记录
点击下方按钮添加第一个客户
[新建客户]
```

---

## 六、达成 8/10 的关键

| 关键点 | 说明 |
|--------|------|
| **视觉一致性** | Design Token 100% 覆盖，无魔数 |
| **交互反馈** | 所有可交互元素有清晰 hover/active/focus |
| **信息层级** | 间距/字号/颜色层级清晰 |
| **错误友好** | 错误提示有解决方案，非技术化 |
| **空状态引导** | 有插图 + 文案 + 操作按钮 |
| **过渡动画** | 统一 0.15s，无突兀变化 |

---

## GSTACK UX OPTIMIZATION REPORT

| Optimization | Scope | Work Estimate | Score Target |
|--------------|-------|---------------|--------------|
| Visual-only UX | Existing features | 18.5 days | 6.4 → 8.0 |

**VERDICT:** 仅优化现有功能 UI/UX，可在 3 周内达到 8/10，无需新增功能。

**KEY ENHANCEMENTS:**
1. 侧边栏 hover/active 指示条（+2 分）
2. 表格行内操作 + hover 样式（+2 分）
3. 表单错误提示 + 必填标识（+2 分）
4. 空状态插图 + 引导按钮（+2 分）
5. 全局间距/过渡一致性（+2 分）

NO NEW FEATURES REQUIRED
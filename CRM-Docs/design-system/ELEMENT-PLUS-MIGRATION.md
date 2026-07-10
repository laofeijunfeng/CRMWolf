# CRMWolf 设计系统 - Element Plus → shadcn-vue 迁移指南

**UI 组件框架迁移完整文档**

---

## 零、shadcn-vue Skill 使用规范 ⚠️ CRITICAL

> **强制要求**：所有 shadcn-vue 组件使用前，必须通过 shadcn-vue Skill 查找组件和使用规范。

### 0.1 Skill 安装

```bash
pnpm dlx skills add unovue/shadcn-vue
```

**安装位置**：`.agents/skills/shadcn-vue/`

### 0.2 使用方式

在 Claude Code 中调用：

```
/shadcn-vue <prompt>
```

### 0.3 使用场景（必须使用）

| 场景 | 示例 Prompt |
|------|------------|
| **查找组件** | "查找分页组件" / "搜索表单组件" |
| **安装组件** | "添加 Dialog 组件" / "安装 Select 组件" |
| **查看用法** | "AlertDialog 如何使用" / "Tabs 组件示例" |
| **检查更新** | "检查已安装组件" / "查看可升级组件" |

### 0.4 强制流程

```
需要 shadcn-vue 组件
    ↓
/shadcn-vue 查找组件和使用规范
    ↓
获取正确的组件名称和 API
    ↓
在代码中使用
```

### 0.5 项目配置

**components.json** 位置：`CRM-Client/components.json`

Skill 会自动读取项目配置：
- 框架类型
- 组件别名
- 已安装组件
- 图标库
- 基础库

---

## 一、迁移目标

| 目标 | 说明 | 状态 |
|------|------|------|
| **100% 替换 Element Plus** | 所有 `el-*` 组件替换为 shadcn-vue 或自定义 V2 组件 | ⏳ 进行中 |
| **设计系统统一** | 所有组件使用 V2 Design Tokens | ✅ 已定义 |
| **不漏迁移** | ESLint + CI + 扫描脚本强制检查 | ✅ 已配置 |

---

## 二、迁移进度

| 阶段 | 任务 | 状态 | 完成日期 |
|------|------|------|---------|
| **Phase 0 Week 1** | Design Tokens + Lint Rules | ✅ 已完成 | 2026-07-08 |
| **Phase 0 Week 2** | 基础组件库（ButtonV2, InputV2, TableV2, CardV2, TabV2） | ✅ 已完成 | 2026-07-08 |
| **Phase 0 Week 3** | 导航组件库（SidebarV2, TopBarV2, UserInfoDropdown） | ✅ 已完成 | 2026-07-09 |
| **Phase 1** | 页面迁移（Leads.vue → shadcn-vue） | ⏳ 进行中 | - |
| **Phase 2** | Element Plus 清理（删除依赖、CSS、全局注册） | ⏳ 待规划 | - |

---

## 二.1、已迁移文件记录

### AppLayout.vue（2026-07-09）

**迁移范围**：Sidebar 导航菜单 + TopBar Header + UserInfoDropdown

**迁移内容**：

| 组件 | Element Plus | shadcn-vue/V2 | 状态 |
|------|--------------|---------------|------|
| **Sidebar 菜单图标** | `@element-plus/icons-vue` | `lucide-vue-next` | ✅ 已替换 |
| **TopBar 按钮** | `el-button` | `Button` (shadcn-vue) | ✅ 已替换 |
| **团队切换对话框** | `el-dialog` | 自定义 Dropdown（向上展开） | ✅ 已移除并重构 |
| **Design Tokens** | `variables.scss` | `variables-v2.scss` | ✅ 已迁移 |

**核心变更**：

1. **分组导航菜单**（销售流程/财务流程/管理工具）
2. **左侧指示条 Signature 元素**（hover 3px / active 4px）
3. **移除独立团队选择器**（节省 ~80px sidebar 高度）
4. **UserInfoDropdown 向上展开**（含团队切换）

**验收清单**：

| 检查项 | 规范来源 | 状态 |
|--------|---------|------|
| Touch targets ≥44px | UI/UX Pro Max §2 | ✅ |
| aria-labels + keyboard-nav | UI/UX Pro Max §1 | ✅ |
| Focus ring 2px | MASTER.md 8.2 | ✅ |
| prefers-reduced-motion | MASTER.md 8.3 | ✅ |
| Sidebar 220px + TopBar 56px | MASTER.md 6.1/6.2 | ✅ |

---

## 三、Element Plus 使用统计

**当前状态**：426+ 处使用待迁移

| 类别 | 数量 | 说明 |
|------|------|------|
| **组件使用** | 426+ | `el-*` 组件在 Vue 文件中 |
| **高频组件** | el-button (46+), el-dialog (44+), el-input (40+), el-form (38+) | P0 优先迁移 |
| **全局 API** | ElMessage (26), ElMessageBox (38) | 替换为 toast() + AlertDialog |
| **图标** | Element Plus Icons → Lucide Icons | 图标映射表已定义 |

---

## 四、组件映射表（Element Plus → V2）

| Element Plus 组件 | V2 组件 | 优先级 | 说明 |
|------------------|--------|--------|------|
| `el-button` | `ButtonV2` | P0 | 5 种变体 + Focus Ring + Touch Target |
| `el-input` | `InputV2` | P0 | Visible Label + Error Placement |
| `el-table` | `TableV2` | P0 | No Vertical Divider + Hover State |
| `el-dialog` | `DialogV2` | P0 | 基于 shadcn-vue Dialog |
| `el-form` | `FormV2` | P0 | VeeValidate + Zod Schema |
| `el-select` | `SelectV2` | P0 | 基于 shadcn-vue Select |
| `ElMessage` | `toast()` | P1 | vue-sonner Toast |
| `ElMessageBox.confirm` | `confirmDialog()` | P1 | 函数式确认对话框 |
| `el-tooltip` | `Tooltip` | P2 | shadcn-vue Tooltip |
| `el-pagination` | `Pagination` | P2 | shadcn-vue Pagination |

---

## 五、图标迁移（Element Plus Icons → Lucide Icons）

| Element Plus Icon | Lucide Icon | 使用场景 |
|------------------|-------------|---------|
| `el-icon-edit` | `Pencil` | 编辑按钮 |
| `el-icon-delete` | `Trash2` | 删除按钮 |
| `el-icon-plus` | `Plus` | 新增按钮 |
| `el-icon-search` | `Search` | 搜索框 |
| `el-icon-loading` | `Loader2` (animate-spin) | 加载状态 |
| `el-icon-arrow-right` | `ArrowRight` | 导航箭头 |
| `el-icon-arrow-left` | `ArrowLeft` | 返回箭头 |
| `el-icon-close` | `X` | 关闭按钮 |
| `el-icon-check` | `Check` | 确认/勾选 |
| `el-icon-warning` | `AlertTriangle` | 警告提示 |
| `el-icon-info` | `Info` | 信息提示 |
| `el-icon-user` | `User` | 用户图标 |
| `el-icon-calendar` | `Calendar` | 日历图标 |
| `el-icon-document` | `FileText` | 文档图标 |
| `el-icon-download` | `Download` | 下载按钮 |
| `el-icon-upload` | `Upload` | 上传按钮 |
| `el-icon-setting` | `Settings` | 设置图标 |
| `el-icon-menu` | `Menu` | 菜单图标 |
| `el-icon-more` | `MoreHorizontal` | 更多操作 |
| `el-icon-bell` | `Bell` | 通知铃铛 |

---

## 六、迁移追踪工具

| 工具 | 路径 | 用途 |
|------|------|------|
| **ESLint 规则** | `CRM-Client/eslint.config.js` | 禁止新增 Element Plus |
| **Stylelint 规则** | `CRM-Client/.stylelintrc.design-system.js` | 禁止硬编码样式 |
| **扫描脚本** | `CRM-Client/scripts/scan-element-plus.sh` | 统计迁移进度 |

---

## 七、实施路线图（4 个阶段）

### 7.1 Phase 1: 设计系统基础升级（2-3 周）

**目标**：建立新设计系统基础，保持向后兼容

| 任务 | 优先级 | 工作量 | 依赖 |
|------|--------|--------|------|
| **1.1 更新 Design Tokens** | P0 | 2天 | 无 |
| 创建新文件 `variables-v2.scss`，包含新的颜色、圆角、阴影 tokens | | | |
| **1.2 创建过渡方案** | P0 | 1天 | 1.1 |
| 编写迁移指南，列出旧变量→新变量的映射关系 | | | |
| **1.3 创建 Design System 文档** | P0 | 2天 | 1.1 |
| 使用 UI/UX Pro Max 的 `--design-system --persist` 生成 MASTER.md | | | |
| **1.4 更新 Element Plus 主题** | P0 | 1天 | 1.1 |
| 调整 `element-plus-theme.scss`，适配新的主色调 | | | |

**输出成果**：
- `src/styles/variables-v2.scss`（新设计系统）
- `CRM-Docs/design-system/MASTER.md`（设计系统文档）
- Storybook 新旧对比展示

---

### 7.2 Phase 2: 核心组件库建设（3-4 周）

**目标**：创建新的导航组件和通用组件，逐步替换旧组件

#### 7.2.1 导航组件重构

| 组件 | 优先级 | 工作量 | 说明 |
|------|--------|--------|------|
| **SidebarV2** | P0 | 2天 | 左侧全局菜单（含左侧指示条设计） |
| **TopBarV2** | P0 | 2天 | 顶部栏（含面包屑、操作按钮、审批铃铛） |
| **ContextTabsV2** | P0 | 2天 | 上下文标签栏（动态二级导航） |
| **UserInfoDropdownV2** | P1 | 1天 | 用户下拉菜单（含团队切换） |

#### 7.2.2 通用组件库

| 组件 | 优先级 | 工作量 | 说明 |
|------|--------|--------|------|
| **ButtonV2** | P0 | 1天 | 5 种变体 + Focus Ring + Touch Target |
| **InputV2** | P0 | 1天 | Visible Label + Error Placement |
| **TableV2** | P0 | 2天 | No Vertical Divider + Hover State |
| **CardV2** | P1 | 1天 | 统一阴影 + 圆角 6px |
| **TabV2** | P1 | 1天 | Active 指示条设计 + 150ms 过渡 |

#### 7.2.3 Storybook 建设

每个组件必须包含：
- `.stories.ts` 文件（展示组件的所有状态）
- 设计说明（引用 MASTER.md 的设计规则）
- 交互测试（hover/active/disabled 状态）

---

### 7.3 Phase 3: 逐页面替换（4-6 周）

**目标**：逐页面替换，确保功能不受影响

#### 7.3.1 替换策略

**渐进式替换**（不建议一次性全替换）：
- 先替换高频页面（线索管理、客户管理、合同管理）
- 再替换低频页面（设置、配置）
- 最后替换详情页（客户详情、合同详情）

#### 7.3.2 页面替换顺序

| 页面 | 优先级 | 原因 |
|------|--------|------|
| **线索管理（Leads.vue）** | P0 | 高频使用，简单页面，适合作为试点 |
| **客户管理（Customers.vue）** | P0 | 高频使用，核心业务页面 |
| **合同管理（Contracts.vue）** | P0 | 高频使用，核心业务页面 |
| **回款管理（Payments.vue）** | P0 | 高频使用，涉及财务审批 |
| **发票管理（Invoices.vue）** | P1 | 中频使用 |
| **审批中心（ApprovalCenter.vue）** | P1 | 中频使用，涉及审批流程 |
| **客户详情（CustomerDetail.vue）** | P2 | 复杂页面，包含多个子组件 |
| **合同详情（ContractDetail.vue）** | P2 | 复杂页面 |
| **设置页面（Settings.vue）** | P3 | 低频使用 |

#### 7.3.3 替换标准

每个页面替换前必须满足：
- ✅ 所有新组件已测试通过（Storybook + 单元测试）
- ✅ 功能完整性测试通过（所有按钮、表单、表格功能正常）
- ✅ 性能测试通过（加载时间、交互响应）
- ✅ 无障碍测试通过（keyboard nav、screen reader）
- ✅ 团队评审通过（至少 2 人评审）

---

### 7.4 Phase 4: 测试与验证（2 周）

**目标**：全面测试，确保无遗漏问题

#### 7.4.1 自动化测试

| 测试类型 | 工具 | 覆盖范围 |
|---------|------|---------|
| **单元测试** | Vitest + Vue Test Utils | 所有新组件 |
| **视觉回归测试** | Playwright + Storybook | 所有页面截图对比 |
| **性能测试** | Lighthouse | Core Web Vitals（CLS < 0.1） |
| **无障碍测试** | axe-core | WCAG AA 标准（4.5:1 contrast） |

#### 7.4.2 验收标准

| 标准 | 目标值 | 说明 |
|------|--------|------|
| **视觉一致性** | 100% | 所有页面采用新设计系统 |
| **功能完整性** | 100% | 所有功能正常工作 |
| **性能** | CLS < 0.1 | Core Web Vitals 合规 |
| **无障碍** | WCAG AA | 4.5:1 contrast ratio |
| **单元测试覆盖率** | > 80% | 所有新组件有单元测试 |

---

## 八、实施顺序决策指南

### 8.1 核心问题

**问题**：是先建立基础组件库（按钮、表格、tab、配色体系），然后再迁移，还是直接开始迁移？

**正确答案**：**先建立基础组件库，再迁移**。这是业界最佳实践，避免大爆炸式重构。

### 8.2 策略对比

| 策略 | 说明 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|---------|
| **策略 A：基础先行** | 先建 Design Tokens + 基础组件库，再迁移页面 | ✅ 风险可控<br>✅ 新组件充分测试<br>✅ 设计系统先验证 | ⚠️ 初期工作量大<br>⚠️ 需要耐心 | **推荐** |
| **策略 B：直接迁移** | 直接在页面中创建新组件，边迁移边完善 | ✅ 立即可见效果<br>✅ 快速反馈 | ❌ 组件质量不稳定<br>❌ 可能重复返工<br>❌ 样式不统一风险高 | ❌ 不推荐（风险高） |

### 8.3 为什么必须先建立基础组件库？

| 风险类型 | 策略 A（基础先行） | 策略 B（直接迁移） |
|---------|------------------|------------------|
| **组件质量不稳定** | ✅ 低风险（先测试充分） | ❌ 高风险（边迁移边返工） |
| **样式不统一** | ✅ 低风险（统一 Tokens） | ❌ 高风险（可能重复定义） |
| **大规模返工** | ✅ 低风险（试点验证） | ❌ 高风险（发现问题需重做） |
| **团队协作混乱** | ✅ 低风险（统一标准） | ❌ 高风险（没有统一标准） |
| **向后兼容问题** | ✅ 低风险（别名保留） | ❌ 高风险（直接替换） |

---

## 九、快速启动指南

### 9.1 步骤 1：创建 Design Tokens 文件

**文件位置**：`CRM-Client/src/styles/variables-v2.scss`

```scss
// ==================== CRMWolf 设计系统 V2 ====================
// 来源：navigation-redesign-v3.html + UI/UX Pro Max

// ==================== 颜色系统 ====================

// 主色调（现代蓝色）
$wolf-primary-v2: #2563EB;
$wolf-primary-hover-v2: #1E40AF;
$wolf-primary-active-v2: #1D4ED8;
$wolf-primary-light-v2: rgba(#2563EB, 0.1);

// 次要色
$wolf-secondary-v2: #3B82F6;

// 强调色（成功/成交）
$wolf-accent-v2: #059669;

// 背景
$wolf-bg-page-v2: #F8FAFC;
$wolf-bg-card-v2: #FFFFFF;
$wolf-bg-sidebar-v2: #FFFFFF;
$wolf-bg-hover-v2: #EEF2FF;
$wolf-bg-muted-v2: #F1F5FD;

// 文字
$wolf-text-primary-v2: #0F172A;
$wolf-text-secondary-v2: #64748B;
$wolf-text-tertiary-v2: #94A3B8;

// 边框
$wolf-border-default-v2: #E4ECFC;

// 功能色
$wolf-success-v2: #10B981;
$wolf-warning-v2: #F59E0B;
$wolf-danger-v2: #DC2626;

// ==================== 圆角系统（统一为 6px）====================

$wolf-radius-v2: 6px;        // 主要圆角（按钮、卡片、输入框）
$wolf-radius-sm-v2: 4px;     // 小圆角（标签、小型元素）
$wolf-radius-lg-v2: 8px;     // 大圆角（弹窗、对话框）
$wolf-radius-full-v2: 9999px; // 完全圆角（头像、徽章）

// ==================== 间距系统（保留 8dp grid）====================

$wolf-space-xs-v2: 4px;
$wolf-space-sm-v2: 8px;
$wolf-space-md-v2: 12px;
$wolf-space-lg-v2: 16px;
$wolf-space-xl-v2: 24px;

// ==================== 阴影系统（中等强度）====================

$wolf-shadow-card-v2: 0 1px 3px rgba(0, 0, 0, 0.1);
$wolf-shadow-hover-v2: 0 2px 8px rgba(0, 0, 0, 0.15);
$wolf-shadow-dropdown-v2: 0 -4px 12px rgba(0, 0, 0, 0.15);

// ==================== 过渡动画 ====================

$wolf-transition-v2: all 0.15s ease;  // 标准：150ms
$wolf-transition-hover-v2: all 0.2s ease; // hover：200ms

// ==================== 向后兼容（保留旧变量别名）====================

$wolf-primary: $wolf-primary-v2;
$wolf-primary-hover: $wolf-primary-hover-v2;
$wolf-radius-sm: $wolf-radius-v2;
```

---

### 9.2 步骤 2：配置 ESLint 强制使用新变量

**文件位置**：`CRM-Client/.eslintrc.design-system.js`

```javascript
module.exports = {
  rules: {
    // ✅ 禁止使用旧变量（强制使用新变量）
    'no-restricted-syntax': [
      'error',
      {
        // 禁止旧颜色变量
        selector: 'Identifier[name=/^wolf-primary$/]',
        message: '请使用 $wolf-primary-v2 (#2563EB) 替代旧变量'
      },
      {
        // 禁止旧圆角变量
        selector: 'Identifier[name=/^wolf-radius-/]',
        message: '请使用 $wolf-radius-v2 (统一 6px) 替代'
      }
    ]
  }
}
```

---

### 9.3 步骤 3：配置 Stylelint 禁止硬编码样式

**文件位置**：`CRM-Client/.stylelintrc.design-system.js`

```javascript
module.exports = {
  rules: {
    // ✅ 禁止直接写颜色 hex 值（强制使用 Design Tokens）
    'declaration-property-value-disallowed-list': {
      'color': [
        '/#[0-9a-fA-F]{3,6}/'  // 禁止：color: #2563EB
      ],
      '/.*/': [
        '/#2563EB/',  // 禁止硬编码主色
        '/#4A6FA5/',  // 禁止旧主色
        '/border-radius: (4|8|12|16)px/'  // 禁止旧圆角值
      ]
    },
    
    // ✅ 强制使用 Design Tokens
    'declaration-property-value-allowed-list': {
      'border-radius': [
        '$wolf-radius-v2',
        '$wolf-radius-sm-v2',
        '$wolf-radius-lg-v2'
      ]
    }
  }
}
```

---

### 9.4 步骤 4：创建第一个新组件 - SidebarV2

基于 `navigation-redesign-v3.html` 的左侧菜单设计。

**核心视觉特征**：
- 左侧指示条设计（hover 3px，active 4px）
- 统一圆角 6px
- 过渡动画 150ms
- 颜色：Primary #2563EB

**关键原则**：
- ✅ 所有可点击元素 cursor: pointer
- ✅ Hover 状态：背景 #EEF2FF
- ✅ Active 状态：背景 #F1F5FD，指示条 4px
- ✅ 键盘导航支持（Tab 顺序）
- ✅ Focus ring 可见（2px outline）

---

## 十、Phase 0 检查清单（必须完成后才能迁移）

### 10.1 Design Tokens 检查

- ✅ `variables-v2.scss` 已创建
- ✅ 所有颜色变量已定义（primary、secondary、accent、success、warning、danger）
- ✅ 所有圆角变量已定义（统一 6px）
- ✅ 所有间距变量已定义（保留 8dp grid）
- ✅ 所有阴影变量已定义（中等强度）
- ✅ 向后兼容别名已添加（`$wolf-primary: $wolf-primary-v2`）
- ✅ `MASTER.md` 已生成

### 10.2 基础组件检查

- ✅ **ButtonV2** 已创建 + Storybook展示 + 单元测试
- ✅ **InputV2** 已创建 + Storybook展示 + 单元测试
- ✅ **TableV2** 已创建 + Storybook展示 + 单元测试
- ✅ **CardV2** 已创建 + Storybook展示 + 单元测试
- ✅ **TabV2** 已创建 + Storybook展示 + 单元测试

### 10.3 导航组件检查

- ✅ **SidebarV2** 已创建 + Storybook展示 + 单元测试
- ✅ **TopBarV2** 已创建 + Storybook展示 + 单元测试
- ✅ **ContextTabsV2** 已创建 + Storybook展示 + 单元测试
- ✅ **UserInfoDropdownV2** 已创建 + Storybook展示 + 单元测试

### 10.4 强制规则检查

- ✅ ESLint 配置已添加（禁止旧变量）
- ✅ Stylelint 配置已添加（禁止硬编码）
- ✅ Storybook 配置已添加（自动文档）

---

## 十一、迁移检查清单

### 11.1 组件迁移检查

- [ ] 确认所有 `el-*` 组件已替换
- [ ] 确认所有 `ElMessage` 已替换为 `toast()`
- [ ] 确认所有 `ElMessageBox` 已替换为 `AlertDialog`
- [ ] 确认所有 Element Plus 图标已替换为 Lucide
- [ ] 确认所有样式使用 V2 Design Tokens

### 11.2 依赖清理检查

- [ ] 删除 `element-plus` 依赖
- [ ] 删除 `@element-plus/icons-vue` 依赖
- [ ] 删除 Element Plus CSS 引入
- [ ] 删除 Element Plus 全局注册代码

### 11.3 测试验证

- [ ] 所有页面功能正常
- [ ] 无 Element Plus 相关报错
- [ ] 设计系统样式统一
- [ ] 无障碍测试通过

---

## 十二、时间预估

| 阶段 | 工作内容 | 时间 | 里程碑 |
|------|---------|------|--------|
| **Phase 0** | Design Tokens + 基础组件库 | 2-3周 | ✅ 所有基础组件就绪 |
| **Phase 1** | 试点页面 + 核心页面迁移 | 4-6周 | ✅ 所有核心页面使用新设计 |
| **Phase 2** | 清理旧组件 + 优化 | 1-2周 | ✅ 100% 使用新设计系统 |
| **总计** | 完整迁移 | **7-11周** | ✅ 整体替换、统一标准、组件化 |

---

## 十三、参考资料

| 文档 | 路径 | 说明 |
|------|------|------|
| **设计系统主文档** | `CRM-Docs/design-system/MASTER.md` | 全局设计规则唯一来源 |
| **页面结构规范** | `CRM-Docs/design-system/pages/*.md` | 页面特定规则 |
| **Design Tokens** | `CRM-Client/src/styles/variables-v2.scss` | V2 设计系统变量 |
| **shadcn-vue 文档** | https://www.shadcn-vue.com/ | 组件库参考 |
| **Lucide Icons** | https://lucide.dev/ | 图标库参考 |
| **VeeValidate** | https://vee-validate.logaretm.com/ | 表单验证 |
| **vue-sonner** | https://github.com/xiaoluoboding/vue-sonner | Toast 组件 |

---

**版本：V2.2 | 最后更新：2026-07-09**
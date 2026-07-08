# CRMWolf 设计系统文档索引

**全局设计规范文档中心**

---

## 一、文档结构

```
CRM-Docs/design-system/
├── MASTER.md                      # 全局设计规则唯一来源
├── pages/                         # 页面特定结构规范
│   ├── list-page.md               # 列表页结构规范
│   ├── detail-page.md             # 详情页结构规范
│   ├── form-page.md               # 表单页结构规范
│   └── approval-center.md         # 审批中心结构规范
└── README.md                      # 本文档（索引）
```

---

## 二、文档使用指南

### 2.1 如何查阅

**步骤**：

1. **确定页面类型**（列表页/详情页/表单页/审批中心）
2. **查阅页面特定文档**（`pages/[页面类型].md`）
3. **查阅 MASTER.md**（补充通用规则）

### 2.2 文档优先级

```
页面特定规则 > MASTER.md 规则
```

**示例**：
- 如果在 `pages/detail-page.md` 中有关于"ContextTabs 高度"的规则，优先使用
- 如果没有，使用 `MASTER.md` 中的通用规则（48px）

---

## 三、文档清单

### 3.1 MASTER.md（全局规则）

| 章节 | 内容 |
|------|------|
| **一、设计原则** | 四大核心原则、设计优先级 |
| **二、视觉风格规范** | 色彩、圆角、间距、阴影、动画系统 |
| **三、组件设计规范** | Button、Input、Table、Card、Tab |
| **四、导航组件规范** | Sidebar、TopBar、ContextTabs、UserInfoDropdown |
| **五、交互规范** | Hover、Active、Disabled、Loading 状态 |
| **六、无障碍规范** | 对比度、Focus、Screen Reader |
| **七、性能规范** | 动画性能、响应时间 |
| **八、响应式规范** | 断点系统、间距适配 |
| **九、禁止事项** | Anti-Patterns、Stylelint 强制规则 |
| **十、向后兼容** | 变量别名、迁移时间表 |

---

### 3.2 pages/list-page.md（列表页）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 三层结构、组件清单 |
| **二、TopBar 布局** | 三段式、操作按钮规范 |
| **三、表格区域布局** | 搜索栏、表格规范、表头对齐 |
| **四、状态 Badge 规范** | 客户状态、审批状态 |
| **五、分页规范** | 分页位置、样式 |
| **六、空状态规范** | 空状态设计 |

**适用页面**：线索管理、客户管理、商机管理、合同管理、回款管理、发票管理

---

### 3.3 pages/detail-page.md（详情页）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 四层结构、组件清单 |
| **二、TopBar 布局** | 三段式、操作按钮规范 |
| **三、ContextTabs** | 二级导航、标签内容、样式 |
| **四、内容区域布局** | 信息头部、属性网格、业务流程卡片 |
| **五、表格区域规范** | 表格位置、样式、操作按钮 |

**适用页面**：客户详情、合同详情、回款详情、发票详情

---

### 3.4 pages/form-page.md（表单页）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 导航层级、组件清单 |
| **二、TopBar 布局** | 三段式、返回按钮 |
| **三、表单布局规范** | 表单宽度、卡片、分组 |
| **四、表单字段规范** | 字段布局、高度、间距 |
| **五、标签规范** | 标签样式、必填标识 |
| **六、错误提示规范** | 错误位置、样式、Input Error 状态 |
| **七、操作按钮规范** | 按钮位置、样式 |

**适用页面**：新建客户、新建合同、新建商机、编辑客户、编辑合同

---

### 3.5 pages/approval-center.md（审批中心）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 导航层级、组件清单 |
| **二、审批铃铛设计** | ApprovalIcon、Badge 样式 |
| **三、审批中心布局** | 审批类型标签、待审批表格 |
| **四、审批详情设计** | Modal、ApprovalProgressCompact |
| **五、审批时间线** | ApprovalTimeline 布局、样式 |
| **六、导航入口优化** | 审批入口唯一性、路由 |

**适用页面**：审批中心

---

## 四、核心设计原则速查

### 4.1 四大核心原则

| 原则 | 说明 | 关键检查 |
|------|------|---------|
| **极致克制** | 装饰性元素不超过5% | 所有设计元素必须有明确用途 |
| **柔和低噪** | 使用中性暖灰为主色调 | 避免高饱和色彩 |
| **统一有序** | 所有组件使用 Design Tokens | 禁止硬编码颜色、圆角、间距 |
| **服务内容** | UI 不抢夺用户注意力 | 内容为王，UI 为辅 |

### 4.2 关键数值速查表

| 属性 | Token | 值 |
|------|-------|-----|
| **主色** | `$wolf-primary-v2` | `#2563EB` |
| **统一圆角** | `$wolf-radius-v2` | `6px` |
| **过渡动画** | `$wolf-transition-v2` | `0.15s ease` |
| **表格行高** | - | `44px`（自适应） |
| **ContextTabs 高度** | - | `48px` |
| **Sidebar 宽度** | - | `220px` |
| **TopBar 高度** | - | `56px` |

---

## 五、强制规则速查

### 5.1 禁止事项

| 禁止项 | 原因 | 强制工具 |
|--------|------|---------|
| ❌ Emoji 作为图标 | 跨平台不一致 | Stylelint |
| ❌ 硬编码颜色 | 违反 Design Tokens | Stylelint |
| ❌ 硬编码圆角（4/8/12/16px） | 统一 6px | Stylelint |
| ❌ 超过 500ms 动画 | 用户感知慢 | 手动检查 |
| ❌ 无 Focus 状态 | 无障碍不合规 | axe-core |

### 5.2 Stylelint 配置（强制）

```javascript
{
  'declaration-property-value-disallowed-list': {
    'color': ['/#[0-9a-fA-F]{3,6}/'],
    'border-radius': ['/(4|8|12|16)px/']
  }
}
```

---

## 六、团队协作指南

### 6.1 设计评审流程

```
设计师提交设计稿 → 前端查阅 MASTER.md → 前端查阅页面文档 →
前端实现 → 设计师对照文档验收 → 团队评审
```

### 6.2 文档更新流程

```
发现设计规则缺失 → 提出 Issue → 团队讨论 →
更新 MASTER.md 或页面文档 → 团队通知
```

---

## 七、文档版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| **V2** | 2026-07-08 | 基于 navigation-redesign-v3.html 重新设计 |
| **V1** | 之前 | 极简中性风设计（variables.scss） |

---

## 八、UI 组件框架迁移（Element Plus → shadcn-vue）

### 8.1 迁移目标

| 目标 | 说明 | 状态 |
|------|------|------|
| **100% 替换 Element Plus** | 所有 `el-*` 组件替换为 shadcn-vue 或自定义 V2 组件 | ⏳ 进行中 |
| **设计系统统一** | 所有组件使用 V2 Design Tokens | ✅ 已定义 |
| **不漏迁移** | ESLint + CI + 扫描脚本强制检查 | ✅ 已配置 |

### 8.2 当前迁移进度

| 阶段 | 任务 | 状态 | 完成日期 |
|------|------|------|---------|
| **Phase 0 Week 1** | Design Tokens + Lint Rules | ✅ 已完成 | 2026-07-08 |
| **Phase 0 Week 2** | 基础组件库（ButtonV2, InputV2, TableV2, CardV2, TabV2） | ⏳ 待执行 | - |
| **Phase 0 Week 3** | 导航组件库（SidebarV2, TopBarV2, ContextTabsV2） | ⏳ 待执行 | - |
| **Phase 1** | 页面迁移（Leads → Customers → Contracts → Payments） | ⏳ 待规划 | - |
| **Phase 2** | Element Plus 清理（删除依赖、CSS、全局注册） | ⏳ 待规划 | - |

### 8.3 Element Plus 使用统计

**当前状态**：426+ 处使用待迁移

| 类别 | 数量 | 说明 |
|------|------|------|
| **组件使用** | 426+ | `el-*` 组件在 Vue 文件中 |
| **高频组件** | el-button (46+), el-dialog (44+), el-input (40+), el-form (38+) | P0 优先迁移 |
| **全局 API** | ElMessage (26), ElMessageBox (38) | 替换为 toast() + AlertDialog |
| **图标** | Element Plus Icons → Lucide Icons | 图标映射表已定义 |

### 8.4 组件映射表（Element Plus → V2）

| Element Plus 组件 | V2 组件 | 优先级 | 说明 |
|------------------|--------|--------|------|
| `el-button` | `ButtonV2` | P0 | 5 种变体 + Focus Ring + Touch Target |
| `el-input` | `InputV2` | P0 | Visible Label + Error Placement |
| `el-table` | `TableV2` | P0 | No Vertical Divider + Hover State |
| `el-dialog` | `DialogV2` | P0 | 基于 shadcn-vue Dialog |
| `el-form` | `FormV2` | P0 | VeeValidate + Zod Schema |
| `el-select` | `SelectV2` | P0 | 基于 shadcn-vue Select |
| `ElMessage` | `toast()` | P1 | vue-sonner Toast |
| `ElMessageBox` | `AlertDialog` | P1 | shadcn-vue AlertDialog |
| `el-tooltip` | `Tooltip` | P2 | shadcn-vue Tooltip |
| `el-pagination` | `Pagination` | P2 | shadcn-vue Pagination |

**完整映射表**: `docs/superpowers/specs/2026-07-08-element-plus-to-shadcn-vue-migration-design.md`

### 8.5 图标迁移（Element Plus Icons → Lucide Icons）

| Element Plus Icon | Lucide Icon | 使用场景 |
|------------------|-------------|---------|
| `el-icon-edit` | `Pencil` | 编辑按钮 |
| `el-icon-delete` | `Trash2` | 删除按钮 |
| `el-icon-plus` | `Plus` | 新增按钮 |
| `el-icon-search` | `Search` | 搜索框 |
| `el-icon-loading` | `Loader2` (animate-spin) | 加载状态 |

**完整图标映射表**: `docs/superpowers/specs/2026-07-08-element-plus-to-shadcn-vue-migration-design.md §1.2`

### 8.6 迁移追踪工具

| 工具 | 路径 | 用途 |
|------|------|------|
| **ESLint 规则** | `CRM-Client/eslint.config.js` | 禁止新增 Element Plus |
| **Stylelint 规则** | `CRM-Client/.stylelintrc.design-system.js` | 禁止硬编码样式 |
| **扫描脚本** | `CRM-Client/scripts/scan-element-plus.sh` | 统计迁移进度 |
| **迁移清单** | `docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md` | 详细进度追踪 |

### 8.7 迁移相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| **迁移设计规范** | `docs/superpowers/specs/2026-07-08-element-plus-to-shadcn-vue-migration-design.md` | 完整迁移设计 |
| **Phase 0 Week 1 计划** | `docs/superpowers/plans/2026-07-08-design-system-phase0-week1.md` | Design Tokens 实施 |
| **Phase 0 Week 2-3 计划** | `docs/superpowers/plans/2026-07-08-design-system-phase0-week2-3.md` | 基础组件库实施 |
| **迁移路线图** | `docs/design-system-migration-roadmap.md` | 整体迁移路线 |

---

## 九、参考资料

| 文档 | 路径/链接 |
|------|----------|
| **UI/UX Pro Max** | `~/.claude/skills/ui-ux-pro-max/` |
| **shadcn-vue 文档** | https://www.shadcn-vue.com/ |
| **Lucide Icons** | https://lucide.dev/ |
| **VeeValidate** | https://vee-validate.logaretm.com/ |
| **vue-sonner (Toast)** | https://github.com/xiaoluoboding/vue-sonner |
| **Element Plus 文档** | https://element-plus.org/（迁移完成后删除） |
| **Material Design** | https://material.io/design |
| **Apple HIG** | https://developer.apple.com/design/human-interface-guidelines |

---

## 九、联系与反馈

**文档维护团队**：
- 设计负责人：[待定]
- 前端负责人：[待定]

**反馈渠道**：
- GitHub Issue：[项目仓库链接]
- Slack Channel：#design-system

---

**版本：V2 | 最后更新：2026-07-08**
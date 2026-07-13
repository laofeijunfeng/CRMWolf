---
priority: high
status: active
created: 2026-07-13
last_updated: 2026-07-13
---

# 系统配置页面重构设计文档

**版本**: V1.0
**创建日期**: 2026-07-13
**最后更新**: 2026-07-13
**状态**: 已批准

---

## 一、概述

### 1.1 背景

原有的 Settings.vue 页面混合了两个部分：
- **个人账户部分**：用户信息卡片、账户详情、操作记录、修改密码
- **系统管理入口**：角色管理、审批流程、采购配置、AI配置、通知配置、团队成员

原有设计存在以下问题：
1. **信息架构不清晰**：个人账户和系统管理混合在一起
2. **交互方式过时**：点击配置项跳转到独立页面，多次页面跳转
3. **不符合现代设计趋势**：现代CRM系统（如Linear、Notion）都使用Sheet抽屉作为设置页面

### 1.2 目标

将系统配置功能重构为独立的页面，使用 Sheet 抽屉替代页面跳转，提升用户体验和交互流畅度。

### 1.3 影响范围

- **新增文件**：
  - `src/views/SystemConfig.vue` - 系统配置页面
  - `src/components/system-config/RoleSheet.vue` - 角色管理 Sheet
  - `src/components/system-config/ApprovalFlowSheet.vue` - 审批流程 Sheet
  - `src/components/system-config/ProcurementSheet.vue` - 采购配置 Sheet
  - `src/components/system-config/AIConfigSheet.vue` - AI配置 Sheet
  - `src/components/system-config/NotificationSheet.vue` - 通知配置 Sheet
  - `src/components/system-config/TeamMemberSheet.vue` - 团队成员 Sheet

- **修改文件**：
  - `src/router/index.ts` - 添加 `/system-config` 路由
  - `src/AppLayout.vue` - 左侧菜单"系统配置"导航到 `/system-config`
  - `src/components/ui/detail-sheet/DetailSheetContent.vue` - 调整宽度为 `w-3/4 max-w-[1080px]`

- **保留文件**：
  - `src/views/Settings.vue` - 保留用于个人账户管理（后续迁移到用户下拉菜单，本次重构不涉及）

---

## 二、设计方案

### 2.1 总体架构

#### 用户旅程

**原有旅程**：
```
左侧菜单"系统配置" → /settings 页面
→ 点击配置项 → 跳转到独立页面（如 /roles）
→ 完成操作 → 返回 /settings
```

**新旅程**：
```
左侧菜单"系统配置" → /system-config 页面
→ 点击配置卡片 → 打开 Sheet 抽屉（不离开页面）
→ 完成操作 → 关闭 Sheet，停留在 /system-config
```

#### 层级关系

```
Dialog (z-[1000]) > Sheet (z-[200]) > TopBar (z-90)
```

- **Sheet**: 使用 `DetailSheetContent`（z-[200]），宽度 `w-3/4 max-w-[1080px]`
- **Dialog**: 使用 `DialogContent`（z-[1000]），渲染在 Sheet 外部

### 2.2 系统配置页面结构

#### 页面布局

```
SystemConfig.vue（页面）
├─ 页面容器
│  ├─ padding: 24px（遵循设计规范）
│  ├─ gap: 24px（卡片间距）
│  └─ flex: 1（继承高度）
│
├─ 标题区
│  └─ h1 "系统配置"（wolf-page-title）
│
└─ 卡片网格区
   ├─ layout: grid grid-cols-3 gap-6（响应式：lg 3列，md 2列，sm 1列）
   │
   ├─ 角色管理卡片
   ├─ 审批流程卡片
   ├─ 采购配置卡片
   ├─ AI配置卡片
   ├─ 通知配置卡片
   ├─ 团队成员卡片
```

#### 单个卡片结构

```vue
<Card
  v-if="canManageRoles"
  class="cursor-pointer hover:shadow-md transition-shadow duration-200"
  @click="openSheet('roles')"
>
  <CardHeader>
    <Shield class="w-10 h-10 mb-2 text-primary" />
    <CardTitle>角色管理</CardTitle>
    <CardDescription>配置角色与权限</CardDescription>
  </CardHeader>
</Card>
```

#### 图标选择

| 配置项 | 图标 | 说明 |
|--------|------|------|
| 角色管理 | `Shield` | 盾牌，代表权限 |
| 审批流程 | `Workflow` | 流程图 |
| 采购配置 | `ShoppingCart` | 购物车 |
| AI配置 | `Cpu` | CPU |
| 通知配置 | `Bell` | 铃铛 |
| 团队成员 | `Users` | 用户组 |

### 2.3 Sheet 组件统一设计框架

#### Sheet 组件结构

```
Sheet 组件（使用已封装的 DetailSheetContent）
├─ Sheet（shadcn-vue Sheet）
│  ├─ v-model:open="sheetVisible"
│  └─ @update:open="handleSheetClose"
│
├─ SheetHeader（固定，p-6 pb-4）
│  ├─ SheetTitle：配置项名称
│  └─ SheetDescription：简短说明
│
├─ DetailSheetContent（优化后：w-3/4 max-w-[1080px]）
│  └─ ScrollArea（h-full，可滚动）
│  │  ├─ 搜索/操作栏（Card 或 div，p-4）
│  │  │  ├─ 左侧：搜索输入框、筛选下拉
│  │  │  └─ 右侧：新建按钮
│  │  │
│  │  └─ 内容区域
│  │  │  ├─ 表格列表型：DataTable（简化分页）
│  │  │  │  └─ 简化分页：上一页/下一页（不显示总数）
│  │  │  │
│  │  │  └─ 表单型：表单字段
│  │  │
│  │  └─ 特殊区域（如有）
│  │  │  ├─ AI配置：连接测试卡片
│  │  │  ├─ 通知配置：发送测试卡片
│
└─ Dialog（嵌套在 Sheet 外部，z-[1000]）
   └─ 复杂操作：配置权限、分配角色、创建审批流程等
```

#### 关键设计原则

| 原则 | 说明 |
|------|------|
| **Sheet 宽度** | `w-3/4 max-w-[1080px]`（优化后，更适合表格） |
| **Dialog 层级** | 使用 `DialogContent`（z-[1000]），渲染在 Sheet 外部 |
| **Sheet 内滚动** | 使用 `ScrollArea`，Header 固定 |
| **简化分页** | 上一页/下一页，不显示总数 |
| **权限控制** | 无权限的卡片不显示（`v-if="canManageXxx"`） |
| **返回行为** | Sheet 有关闭按钮（X）+ ESC 键支持 |

---

## 三、各配置模块详细设计

### 3.1 角色管理

#### Sheet 内部布局

```
角色管理 Sheet
├─ SheetHeader: "角色管理"
│
├─ DetailSheetContent
│  └─ ScrollArea
│  │  ├─ 搜索/操作栏
│  │  │  ├─ Input: 搜索角色代码、名称
│  │  │  └─ Button: 新建角色
│  │  │
│  │  └─ DataTable
│  │  │  ├─ 列：角色代码、角色名称、描述、创建时间、操作
│  │  │  ├─ 操作：编辑、配置权限、删除
│  │  │  └─ 简化分页
│
└─ Dialog（外部）
   ├─ 新建/编辑角色 Dialog
   │  └─ 表单：角色代码、角色名称、描述
   │
   └─ 配置权限 Dialog
      └─ 权限树（Checkbox嵌套）
```

#### 表格列设计

| 列名 | 宽度 | 说明 |
|------|------|------|
| 角色代码 | 150px | 可点击（查看详情） |
| 角色名称 | 150px | - |
| 描述 | 自适应 | 文本溢出省略号 |
| 创建时间 | 160px | 格式：YYYY-MM-DD HH:mm |
| 操作 | 200px | 固定右侧：编辑、配置权限、删除 |

#### 权限控制

```typescript
const canManageRoles = computed(() => permissionStore.hasPermission('role:manage'))
```

### 3.2 审批流程

#### Sheet 内部布局

```
审批流程 Sheet
├─ SheetHeader: "审批流程"
│
├─ DetailSheetContent
│  └─ ScrollArea
│  │  ├─ 搜索/筛选栏
│  │  │  ├─ Input: 搜索流程名称、编码
│  │  │  ├─ Select: 筛选状态
│  │  │  ├─ Select: 授权类型
│  │  │  ├─ Select: 单据类型
│  │  │  └─ 按钮组
│  │  │     ├─ Button: AI 创建流程
│  │  │     └─ Button: 手动创建
│  │  │
│  │  └─ DataTable
│  │  │  ├─ 列：流程名称、流程编码、授权类型、单据类型、状态、操作
│  │  │  ├─ 操作：编辑、删除
│  │  │  └─ 简化分页
│
└─ Dialog（外部）
   ├─ AI 创建流程 Dialog
   │  └─ Input: 流程描述（自然语言）
   │
   └─ 手动创建流程 Dialog（去掉右侧预览）
      └─ 表单：流程名称、流程编码、描述、适用条件、审批节点配置
```

#### 特殊处理

- ✅ **去掉右侧预览功能**（原有 ApprovalFlowForm.vue 的右侧预览）
- ✅ **AI 创建流程**：使用 Dialog 居中弹出

### 3.3 采购配置

#### Sheet 内部布局

```
采购配置 Sheet
├─ SheetHeader: "采购配置"
│
├─ DetailSheetContent
│  └─ ScrollArea
│  │  ├─ 搜索/操作栏
│  │  │  ├─ Input: 搜索方式名称、编码
│  │  │  ├─ Select: 筛选状态
│  │  │  └─ Button: 新增采购方式
│  │  │
│  │  └─ DataTable
│  │  │  ├─ 列：编码、名称、排序、状态、描述、创建时间、操作
│  │  │  ├─ 操作：编辑、删除
│  │  │  └─ 简化分页
│
└─ Dialog（外部）
   └─ 新建/编辑采购方式 Dialog
      └─ 表单：编码、名称、排序序号、状态、描述
```

#### 简化设计

- ✅ 只保留采购方式管理，去掉阶段管理（用户已确认）

### 3.4 AI 配置

#### Sheet 内部布局

```
AI 配置 Sheet
├─ SheetHeader: "AI 配置"
│
├─ DetailSheetContent
│  └─ ScrollArea
│  │  ├─ 配置表单区域
│  │  │  ├─ Select: AI 供应商
│  │  │  ├─ Input: 接口地址
│  │  │  ├─ Input（password）: API Key
│  │  │  ├─ Input: 模型名称
│  │  │  └─ Button: 保存配置（右上角）
│  │  │
│  │  └─ 连接测试区域
│  │  │  ├─ Input: 测试消息
│  │  │  ├─ Button: 测试连接
│  │  │  └─ 测试结果展示
│  │  │     ├─ 成功/失败提示
│  │  │     ├─ AI 回复（流式输出）
│  │  │     └─ Button: 重试（失败时显示）
```

#### 表单字段设计

| 字段 | 类型 | 说明 |
|------|------|------|
| AI 供应商 | Select | 选项：DeepSeek、OpenAI、智谱 AI、阿里云通义、百度文心、自定义 |
| 接口地址 | Input | placeholder: "如 https://api.deepseek.com/v1" |
| API Key | Input（password） | show-password |
| 模型名称 | Input | placeholder: "如 deepseek-chat" |

#### 优化建议

- ✅ **连接测试**：Sheet 内展示（不需要 Dialog）
- ✅ **流式输出**：添加"生成中..."加载指示器
- ✅ **错误恢复**：添加"重试"按钮

### 3.5 通知配置

#### Sheet 内部布局

```
通知配置 Sheet
├─ SheetHeader: "通知配置"
│
├─ DetailSheetContent
│  └─ ScrollArea
│  │  ├─ 配置表单区域
│  │  │  ├─ Switch: 启用通知
│  │  │  ├─ Input: Webhook URL
│  │  │  ├─ Input: 通知群名称（可选）
│  │  │  └─ Button: 保存配置（右上角）
│  │  │
│  │  └─ 发送测试区域
│  │  │  ├─ Button: 发送测试消息
│  │  │  └─ 测试结果展示
```

#### 表单字段设计

| 字段 | 类型 | 说明 |
|------|------|------|
| 启用通知 | Switch | active-text="开启", inactive-text="关闭" |
| Webhook URL | Input | placeholder: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" |
| 通知群名称 | Input | placeholder: "如：审批通知群"（可选） |

### 3.6 团队成员

#### Sheet 内部布局

```
团队成员 Sheet
├─ SheetHeader: "团队成员"
│
├─ DetailSheetContent
│  └─ ScrollArea
│  │  ├─ 团队信息栏
│  │  │  ├─ 左侧：团队名称、邀请码
│  │  │  └─ 右侧
│  │  │     ├─ Button: 邀请成员
│  │  │     └─ Button: 重置邀请码
│  │  │
│  │  └─ DataTable
│  │  │  ├─ 列：姓名、邮箱、当前团队、加入时间、角色、操作
│  │  │  ├─ 操作：重置密码、分配角色、移除成员（仅 TEAM_ADMIN 可见）
│  │  │  └─ 简化分页
│
└─ Dialog（外部）
   ├─ 邀请成员 Dialog
   │  └─ 提示：邀请码 + 分享链接
   │
   ├─ 重置密码 Dialog
   │  └─ 确认提示
   │
   ├─ 分配角色 Dialog
   │  └─ Checkbox Group: 可选角色列表
   │
   └─ 移除成员 Dialog（AlertDialog）
      └─ 确认提示
```

#### 表格列设计

| 列名 | 宽度 | 说明 |
|------|------|------|
| 姓名 | 120px | 头像 + 姓名 |
| 邮箱 | 180px | - |
| 当前团队 | 80px | Badge：是/否 |
| 加入时间 | 160px | 格式：YYYY-MM-DD |
| 角色 | 150px | Badge 列表 |
| 操作 | 200px | 固定右侧：重置密码、分配角色、移除 |

#### 特殊处理

- ✅ **操作按钮**：仅 TEAM_ADMIN 可见（`v-if="isTeamAdmin"`）
- ✅ **当前用户**：不显示操作按钮（`v-if="row.id !== currentUserId"`）

---

## 四、实现规范

### 4.1 技术栈

- **UI 组件**：shadcn-vue（Sheet、Dialog、DataTable、Input、Button 等）
- **状态管理**：Pinia（usePermissionStore）
- **表单验证**：VeeValidate + Zod
- **错误处理**：`handleApiError` from `@/utils/errorHandler`

### 4.2 设计规范遵循

| 规范 | 说明 |
|------|------|
| **Design Token** | 使用 `variables-v2.scss`，禁止硬编码颜色/间距/圆角 |
| **Typography** | 使用 IBM Plex Sans（与项目一致） |
| **Icons** | 使用 Lucide Icons（禁止 Emoji 作为图标） |
| **z-index** | Dialog z-[1000] > Sheet z-[200] > TopBar z-90 |
| **间距** | padding: 24px，gap: 6（卡片间距） |

### 4.3 Accessibility 要求

| 检查项 | 规范来源 | 状态 |
|--------|---------|------|
| `role="navigation"` aria-label="主导航" | §1 aria-labels | ✅ |
| `role="menuitem"` aria-current="page" | §1 aria-labels | ✅ |
| `aria-expanded` on dropdown trigger | §1 aria-labels | ✅ |
| `focus-visible` outline 2px | §1 focus-states | ✅ |
| Touch targets ≥44px | §2 touch-target-size | ✅ |
| `prefers-reduced-motion` 支持 | §7 reduced-motion | ✅ |

---

## 五、迁移计划

### 5.1 第一阶段：创建新页面和组件

1. 创建 `SystemConfig.vue` 页面
2. 创建 6 个 Sheet 组件（RoleSheet、ApprovalFlowSheet 等）
3. 添加 `/system-config` 路由
4. 修改左侧菜单导航

### 5.2 第二阶段：调整 DetailSheetContent 宽度

1. 修改 `DetailSheetContent.vue` 宽度为 `w-3/4 max-w-[1080px]`
2. 测试现有 Sheet（商机详情、客户详情、线索详情）是否受影响

### 5.3 第三阶段：迁移个人账户功能

1. 在用户头像下拉菜单中添加个人账户管理入口
2. 测试完成后，可考虑删除或重命名 Settings.vue

---

## 六、验收标准

### 6.1 功能验收

- [ ] 系统配置页面正确显示 6 个配置卡片
- [ ] 无权限的卡片不显示或禁用
- [ ] 点击卡片打开对应的 Sheet 抽屉
- [ ] Sheet 内表格数据正确显示，分页正常
- [ ] Dialog 正确打开，层级正确（显示在 Sheet 上方）
- [ ] 权限控制逻辑正确

### 6.2 设计规范验收

- [ ] 使用 `variables-v2.scss`，无硬编码颜色/间距/圆角
- [ ] 使用 Lucide Icons，无 Emoji
- [ ] z-index 层级正确
- [ ] 响应式布局正确（lg 3列，md 2列，sm 1列）

### 6.3 Accessibility 验收

- [ ] 键盘导航正常（Tab 顺序正确）
- [ ] Screen Reader 可正确朗读
- [ ] 对比度符合 WCAG AA 标准
- [ ] Focus 状态可见

---

## 七、参考文档

- [CRMWolf 设计系统 - MASTER.md](../../CRM-Docs/design-system/MASTER.md)
- [CRMWolf 设计系统 - README.md](../../CRM-Docs/design-system/README.md)
- [布局与层级管理规范 - LAYOUT.md](../../CRM-Client/docs/LAYOUT.md)
- [UI/UX Pro Max - Best Practices](../../.claude/skills/ui-ux-pro-max/)

---

## 八、变更记录

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|---------|------|
| 2026-07-13 | V1.0 | 初始设计文档 | Claude |
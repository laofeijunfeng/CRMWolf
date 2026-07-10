# 日历功能废弃实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完全废弃日历功能，移除所有相关代码和入口，将底部导航替换为回款功能。

**Architecture:** 前后端分离删除 + 入口替换。前端删除视图、组件、API、UI组件库；后端删除路由、CRUD、Schema；修改导航入口和路由配置。

**Tech Stack:** Vue 3 + TypeScript + FastAPI + SQLAlchemy

## Global Constraints

- 底部导航第一项：日历 → 回款（Payments 页面）
- 完全废弃，包括未实现的跟进 API
- `follow_up_parser.py` 服务必须保留（被 AI 创建线索/客户等功能使用）
- 每个步骤独立可验证，频繁提交

---

## Task 1: 删除前端核心文件

**Files:**
- Delete: `CRM-Client/src/views/Calendar.vue`
- Delete: `CRM-Client/src/components/CalendarDayDrawer.vue`
- Delete: `CRM-Client/src/components/FollowUpDialog.vue`
- Delete: `CRM-Client/src/api/calendar.ts`

**Interfaces:**
- Consumes: None
- Produces: None（删除后不影响其他功能）

- [ ] **Step 1: 删除日历主视图**

```bash
rm CRM-Client/src/views/Calendar.vue
```

- [ ] **Step 2: 删除日历详情抽屉组件**

```bash
rm CRM-Client/src/components/CalendarDayDrawer.vue
```

- [ ] **Step 3: 删除跟进弹窗组件**

```bash
rm CRM-Client/src/components/FollowUpDialog.vue
```

- [ ] **Step 4: 删除日历 API 文件**

```bash
rm CRM-Client/src/api/calendar.ts
```

- [ ] **Step 5: 验证删除成功**

```bash
ls CRM-Client/src/views/Calendar.vue CRM-Client/src/components/CalendarDayDrawer.vue CRM-Client/src/components/FollowUpDialog.vue CRM-Client/src/api/calendar.ts 2>&1
```

Expected: "No such file or directory" for all 4 files

- [ ] **Step 6: 提交删除**

```bash
git add -A CRM-Client/src/views/Calendar.vue CRM-Client/src/components/CalendarDayDrawer.vue CRM-Client/src/components/FollowUpDialog.vue CRM-Client/src/api/calendar.ts
git commit -m "refactor(client): delete calendar core files (view, drawer, dialog, api)"
```

---

## Task 2: 删除 UI 日历组件库

**Files:**
- Delete: `CRM-Client/src/components/ui/calendar/*.vue` (12 files)

**Interfaces:**
- Consumes: None
- Produces: None（UI 组件未被其他功能使用）

- [ ] **Step 1: 删除整个 UI 日历组件目录**

```bash
rm -rf CRM-Client/src/components/ui/calendar/
```

- [ ] **Step 2: 验证目录已删除**

```bash
ls CRM-Client/src/components/ui/calendar/ 2>&1
```

Expected: "No such file or directory"

- [ ] **Step 3: 提交删除**

```bash
git add -A CRM-Client/src/components/ui/calendar/
git commit -m "refactor(client): delete shadcn-vue calendar UI components"
```

---

## Task 3: 修改路由配置

**Files:**
- Modify: `CRM-Client/src/router/index.ts:323-328`

**Interfaces:**
- Consumes: None
- Produces: None（路由删除后 `/calendar` 返回 404）

- [ ] **Step 1: 打开路由文件定位日历路由**

找到第 323-328 行的日历路由定义。

- [ ] **Step 2: 删除日历路由定义**

使用 Edit 工具删除以下内容：

```typescript
      {
        path: 'calendar',
        name: 'Calendar',
        component: () => import('@/views/Calendar.vue'),
        meta: { requiresAuth: true, title: '我的日历' }
      },
```

- [ ] **Step 3: 验证路由文件语法**

```bash
cd CRM-Client && npm run type-check 2>&1 | head -20
```

Expected: No TypeScript errors related to router

- [ ] **Step 4: 提交修改**

```bash
git add CRM-Client/src/router/index.ts
git commit -m "refactor(client): remove /calendar route"
```

---

## Task 4: 修改侧边栏菜单

**Files:**
- Modify: `CRM-Client/src/AppLayout.vue:9-20`

**Interfaces:**
- Consumes: None
- Produces: None（侧边栏菜单移除日历入口）

- [ ] **Step 1: 打开 AppLayout 文件定位日历菜单项**

找到第 9-20 行的日历菜单项。

- [ ] **Step 2: 删除日历菜单项**

使用 Edit 工具删除以下内容：

```vue
          <a
            class="nav-item"
            :class="{ active: currentPath === '/calendar' }"
            role="menuitem"
            :aria-current="currentPath === '/calendar' ? 'page' : undefined"
            :aria-label="`我的日历${currentPath === '/calendar' ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/calendar')"
            @keydown.enter="handleMenuClick('/calendar')"
          >
            <component :is="Calendar" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">我的日历</span>
          </a>
```

- [ ] **Step 3: 删除 Calendar 图标导入**

检查文件开头的导入语句，删除 `Calendar` 相关导入。

- [ ] **Step 4: 验证修改**

```bash
cd CRM-Client && npm run type-check 2>&1 | head -20
```

Expected: No TypeScript errors related to Calendar

- [ ] **Step 5: 提交修改**

```bash
git add CRM-Client/src/AppLayout.vue
git commit -m "refactor(client): remove calendar menu from sidebar"
```

---

## Task 5: 修改底部导航

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/BottomNav.vue:16-47`

**Interfaces:**
- Consumes: None
- Produces: 底部导航第一项变为回款

- [ ] **Step 1: 修改图标导入**

删除 `Calendar` 导入，保留其他图标：

```typescript
import {
  OfficeBuilding,
  TrendCharts,
  Document,
  Flag,
  Money,
  Tickets,
  Bell,
  Setting,
} from '@element-plus/icons-vue'
```

- [ ] **Step 2: 修改导航项配置**

将 `mainNavItems` 第一项从日历改为回款：

```typescript
const mainNavItems: NavItem[] = [
  { route: '/payments', icon: Money, label: '回款' },
  { route: '/customers', icon: OfficeBuilding, label: '客户' },
  { route: '/opportunities', icon: TrendCharts, label: '商机' },
  { route: '/contracts', icon: Document, label: '合同' },
]
```

- [ ] **Step 3: 修改 overflowItems**

将回款从 overflowItems 移除（已移到 mainNavItems）：

```typescript
const overflowItems: NavItem[] = [
  { route: '/leads', icon: Flag, label: '线索' },
  { route: '/invoices', icon: Tickets, label: '发票' },
  { route: '/approvals', icon: Bell, label: '审批' },
  { route: '/settings', icon: Setting, label: '设置' },
]
```

- [ ] **Step 4: 验证修改**

```bash
cd CRM-Client && npm run type-check 2>&1 | head -20
```

Expected: No TypeScript errors

- [ ] **Step 5: 提交修改**

```bash
git add CRM-Client/src/components/crmwolf/BottomNav.vue
git commit -m "refactor(client): replace calendar with payments in bottom nav"
```

---

## Task 6: 修改组件导出

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/index.ts:91-92`

**Interfaces:**
- Consumes: None
- Produces: None（Calendar 导出已删除）

- [ ] **Step 1: 删除 Calendar 导出**

删除以下两行：

```typescript
// Calendar & Date
export { Calendar } from '@/components/ui/calendar'
```

- [ ] **Step 2: 验证修改**

```bash
cd CRM-Client && npm run type-check 2>&1 | head -20
```

Expected: No TypeScript errors

- [ ] **Step 3: 提交修改**

```bash
git add CRM-Client/src/components/crmwolf/index.ts
git commit -m "refactor(client): remove Calendar export from crmwolf index"
```

---

## Task 7: 删除后端文件

**Files:**
- Delete: `CRM-Server/app/api/calendar.py`
- Delete: `CRM-Server/app/crud/calendar.py`
- Delete: `CRM-Server/app/schemas/calendar.py`

**Interfaces:**
- Consumes: None
- Produces: None（后端日历 API 已删除）

- [ ] **Step 1: 删除 API 路由文件**

```bash
rm CRM-Server/app/api/calendar.py
```

- [ ] **Step 2: 删除 CRUD 文件**

```bash
rm CRM-Server/app/crud/calendar.py
```

- [ ] **Step 3: 删除 Schema 文件**

```bash
rm CRM-Server/app/schemas/calendar.py
```

- [ ] **Step 4: 验证删除成功**

```bash
ls CRM-Server/app/api/calendar.py CRM-Server/app/crud/calendar.py CRM-Server/app/schemas/calendar.py 2>&1
```

Expected: "No such file or directory" for all 3 files

- [ ] **Step 5: 提交删除**

```bash
git add -A CRM-Server/app/api/calendar.py CRM-Server/app/crud/calendar.py CRM-Server/app/schemas/calendar.py
git commit -m "refactor(server): delete calendar API, CRUD and schema"
```

---

## Task 8: 修改后端路由注册

**Files:**
- Modify: `CRM-Server/app/main.py:14,104`

**Interfaces:**
- Consumes: None
- Produces: None（calendar router 注册已删除）

- [ ] **Step 1: 删除 calendar 导入**

在第 14 行的导入语句中删除 `calendar`：

```python
from app.api import auth, users, roles, permissions, leads, customers, customer_follow_ups, opportunities, filter_options, contracts, approvals, payments, invoices, finance, operation_logs, procurement_methods, procurement_stage_templates, opportunity_stages, customer_procurement, procurement_admin, teams, industry, lead_ai, procurement_ai, approval_ai, system_configs
```

- [ ] **Step 2: 删除路由注册**

删除第 104 行：

```python
# === 日历路由 ===
api_router.include_router(calendar.router)
```

- [ ] **Step 3: 验证后端启动**

```bash
cd CRM-Server && python -c "from app.main import app; print('Import OK')" 2>&1
```

Expected: "Import OK" without errors

- [ ] **Step 4: 提交修改**

```bash
git add CRM-Server/app/main.py
git commit -m "refactor(server): remove calendar router from main.py"
```

---

## Task 9: 前端构建验证

**Files:**
- None（验证步骤）

**Interfaces:**
- Consumes: 所有之前的修改
- Produces: 验证结果

- [ ] **Step 1: 运行前端类型检查**

```bash
cd CRM-Client && npm run type-check
```

Expected: All checks pass without calendar-related errors

- [ ] **Step 2: 运行前端构建**

```bash
cd CRM-Client && npm run build
```

Expected: Build succeeds without calendar-related errors

- [ ] **Step 3: 搜索残留引用**

```bash
grep -rn "Calendar\|calendar\|日历" CRM-Client/src --include="*.vue" --include="*.ts" 2>/dev/null | grep -v "^CRM-Client/src/types/lunar-javascript.d.ts"
```

Expected: Empty or only lunar-javascript type definition

- [ ] **Step 4: 提交验证结果记录**

如有残留引用，记录到文档；如无，继续下一步。

---

## Task 10: 后端启动验证

**Files:**
- None（验证步骤）

**Interfaces:**
- Consumes: 所有之前的修改
- Produces: 验证结果

- [ ] **Step 1: 运行后端导入检查**

```bash
cd CRM-Server && python -c "from app.main import app; print('Backend import OK')"
```

Expected: "Backend import OK"

- [ ] **Step 2: 运行 Ruff 代码检查**

```bash
cd CRM-Server && ruff check app/ --ignore F401,F841
```

Expected: No errors related to calendar

- [ ] **Step 3: 搜索残留引用**

```bash
grep -rn "from app.api.calendar\|from app.crud.calendar\|from app.schemas.calendar\|calendar.router\|calendar_crud" CRM-Server/app --include="*.py"
```

Expected: Empty result

- [ ] **Step 4: 提交验证结果记录**

如有残留引用，记录到文档；如无，继续下一步。

---

## Task 11: 功能验证

**Files:**
- None（手动测试步骤）

**Interfaces:**
- Consumes: 所有之前的修改
- Produces: 验证结果

- [ ] **Step 1: 启动前端开发服务器**

```bash
cd CRM-Client && npm run dev
```

- [ ] **Step 2: 验证导航入口**

- 检查侧边栏无"我的日历"菜单项
- 检查底部导航第一项为"回款"
- 点击回款入口，确认跳转到 `/payments`

- [ ] **Step 3: 验证路由 404**

- 访问 `/calendar`，确认返回 404 或重定向到首页

- [ ] **Step 4: 启动后端服务**

```bash
cd CRM-Server && ./run.sh
```

- [ ] **Step 5: 验证 API 404**

- 访问 `/api/v1/calendar/todos`，确认返回 404

- [ ] **Step 6: 验证其他功能**

- 测试 AI 创建线索（使用 `follow_up_parser_service`）
- 测试 AI 创建客户（使用 `follow_up_parser_service`）
- 测试线索详情页跟进功能
- 测试回款计划页面

---

## Task 12: 最终提交

**Files:**
- None（清理步骤）

**Interfaces:**
- Consumes: 所有之前的修改
- Produces: 完整的废弃变更集

- [ ] **Step 1: 查看所有变更**

```bash
git status
git log --oneline -10
```

- [ ] **Step 2: 确认无遗漏**

检查是否有未提交的文件。

- [ ] **Step 3: 创建废弃说明文档**

如有需要，更新相关文档说明日历功能已废弃。

- [ ] **Step 4: 推送变更**

```bash
git push origin main
```

---

## Summary

| Phase | Tasks | Files Changed |
|-------|-------|---------------|
| 前端删除 | 1-2 | 16 files deleted |
| 前端修改 | 3-6 | 4 files modified |
| 后端删除 | 7 | 3 files deleted |
| 后端修改 | 8 | 1 file modified |
| 验证 | 9-11 | None |
| 完成 | 12 | Git push |

**Total:** 12 tasks, ~20 files affected

---

**Plan created:** 2026-07-10
# 日历功能废弃设计文档

**日期**: 2026-07-10
**状态**: 待实施
**作者**: Claude

---

## 一、废弃目标

废弃"我的日历"功能，确保不影响其他功能正常使用。

---

## 二、废弃范围

### 完全废弃

- 日历主视图及详情抽屉
- FollowUpDialog 跟进弹窗（后端 API 未实现）
- 日历相关的所有前端和后端代码

### 替换方案

- 底部导航：日历 → 回款（Payments 页面）
- 侧边栏菜单：删除"我的日历"入口

---

## 三、文件删除清单

### 前端删除（共 16 个文件）

| 文件路径 | 说明 |
|----------|------|
| `CRM-Client/src/views/Calendar.vue` | 日历主视图 |
| `CRM-Client/src/components/CalendarDayDrawer.vue` | 日历详情抽屉 |
| `CRM-Client/src/components/FollowUpDialog.vue` | 跟进弹窗（API 未实现） |
| `CRM-Client/src/api/calendar.ts` | 日历 API 客户端 |
| `CRM-Client/src/components/ui/calendar/Calendar.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarCell.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarCellTrigger.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarGrid.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarGridBody.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarGridHead.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarGridRow.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarHeadCell.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarHeader.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarHeading.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarNextButton.vue` | UI 组件 |
| `CRM-Client/src/components/ui/calendar/CalendarPrevButton.vue` | UI 组件 |

### 后端删除（共 3 个文件）

| 文件路径 | 说明 |
|----------|------|
| `CRM-Server/app/api/calendar.py` | 日历 API 路由 |
| `CRM-Server/app/crud/calendar.py` | 日历 CRUD 操作 |
| `CRM-Server/app/schemas/calendar.py` | 日历 Schema 定义 |

---

## 四、文件修改清单

### 前端修改（共 4 个文件）

#### 1. `CRM-Client/src/router/index.ts`

删除路由定义（第308-312行）：

```diff
-      {
-        path: 'calendar',
-        name: 'Calendar',
-        component: () => import('@/views/Calendar.vue'),
-        meta: { requiresAuth: true, title: '我的日历' }
-      },
```

#### 2. `CRM-Client/src/AppLayout.vue`

删除侧边栏菜单项（第12-20行附近）：

```diff
-            <div
-              class="nav-item"
-              :class="{ active: currentPath === '/calendar' }"
-              role="button"
-              tabindex="0"
-              :aria-current="currentPath === '/calendar' ? 'page' : undefined"
-              :aria-label="`我的日历${currentPath === '/calendar' ? '（当前页面）' : ''}`"
-              @click="handleMenuClick('/calendar')"
-              @keydown.enter="handleMenuClick('/calendar')"
-            >
-              <el-icon class="nav-item-icon"><Calendar /></el-icon>
-              <span class="nav-item-text">我的日历</span>
-            </div>
```

#### 3. `CRM-Client/src/components/crmwolf/BottomNav.vue`

替换底部导航项（第44行）：

```diff
 import {
-  Calendar,
   OfficeBuilding,
   TrendCharts,
   Document,
   Flag,
   Money,
   ...
 } from '@element-plus/icons-vue'

 const mainNavItems: NavItem[] = [
-  { route: '/calendar', icon: Calendar, label: '日历' },
+  { route: '/payments', icon: Money, label: '回款' },
   { route: '/customers', icon: OfficeBuilding, label: '客户' },
   { route: '/opportunities', icon: TrendCharts, label: '商机' },
   { route: '/contracts', icon: Document, label: '合同' },
 ]
```

#### 4. `CRM-Client/src/components/crmwolf/index.ts`

删除 Calendar 导出（第91-92行）：

```diff
-// Calendar & Date
-export { Calendar } from '@/components/ui/calendar'
```

### 后端修改（共 1 个文件）

#### `CRM-Server/app/main.py`

删除路由注册：

```diff
 from app.api import auth, users, ..., calendar, teams, ...
 
 # === 日历路由 ===
-api_router.include_router(calendar.router)
```

---

## 五、保留的服务

| 文件路径 | 说明 |
|----------|------|
| `CRM-Server/app/services/follow_up_parser.py` | 共享跟进解析服务，被以下模块使用： |
| | - `app/api/customer_ai.py`（AI 创建客户） |
| | - `app/api/lead_ai.py`（AI 创建线索） |
| | - `app/services/ai_parser/lead_parser.py`（线索解析器） |
| | - `app/services/ai_parser/customer_parser.py`（客户解析器） |

---

## 六、影响分析

### 无影响项

| 功能 | 说明 |
|------|------|
| AI 创建线索 | 使用 `follow_up_parser_service`，不依赖日历 API |
| AI 创建客户 | 使用 `follow_up_parser_service`，不依赖日历 API |
| 线索详情页跟进 | `LeadDetailSheet.vue` 有独立的跟进 Dialog |
| 待办数据源 | `LeadFollowUp`、`CustomerFollowUp`、`Opportunity`、`PaymentPlan` 数据本身不变 |
| 回款计划功能 | 回款页面及详情页正常工作 |

### 变更影响

| 功能 | 变更 |
|------|------|
| 移动端导航 | 第一项从「日历」变为「回款」 |
| 桌面端侧边栏 | 删除「我的日历」菜单项 |
| 路由 `/calendar` | 删除，访问返回 404 |

---

## 七、实施步骤

### Phase 1: 前端删除

1. 删除日历视图文件
2. 删除日历相关组件
3. 删除日历 API 文件
4. 删除 UI 组件库（12 个文件）

### Phase 2: 前端修改

1. 修改路由配置（删除 `/calendar` 路由）
2. 修改 AppLayout（删除侧边栏菜单项）
3. 修改 BottomNav（日历 → 回款）
4. 修改组件导出（删除 Calendar）

### Phase 3: 后端删除

1. 删除 API 路由文件
2. 删除 CRUD 文件
3. 删除 Schema 文件

### Phase 4: 后端修改

1. 修改 main.py（移除路由注册）

### Phase 5: 验证

1. 运行前端构建：`npm run build`
2. 运行后端启动：`./run.sh`
3. 测试其他功能：
   - AI 创建线索
   - AI 创建客户
   - 线索详情跟进
   - 回款计划页面

---

## 八、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 遗漏依赖引用 | 全面 grep 搜索 Calendar/日历 引用 |
| 导入错误 | 前端构建验证 + TypeScript 类型检查 |
| 后端路由注册遗漏 | 后端启动验证 |

---

## 九、附录：依赖关系图

```
┌─────────────────────────────────────────────────────────────┐
│                    日历功能完整依赖图                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [用户入口]                                                  │
│   ├─→ AppLayout.vue (侧边栏"我的日历") [待删除]             │
│   ├─→ BottomNav.vue (底部导航"日历") [待修改为"回款"]       │
│   │                                                         │
│  [核心视图]                                                  │
│   ├─→ Calendar.vue [待删除]                                │
│   │    └─→ CalendarDayDrawer.vue [待删除]                  │
│   │         └─→ FollowUpDialog.vue [待删除]                │
│   │              └─→ calendarApi.parseFollowUp (未实现)    │
│   │              └─→ calendarApi.executeFollowUp (未实现)  │
│   │                                                         │
│  [API 层]                                                    │
│   ├─→ calendar.ts [待删除]                                 │
│   │    ├─ getMonthTodos → GET /v1/calendar/todos           │
│   │    ├─ getDateTodos → GET /v1/calendar/todos/date       │
│   │    ├─ getTodoContext → GET /v1/calendar/todos/:id      │
│   │    ├─ parseFollowUp → POST (未实现)                     │
│   │    └─ executeFollowUp → POST (未实现)                   │
│   │                                                         │
│  [后端]                                                      │
│   ├─→ app/api/calendar.py [待删除]                         │
│   │    └─→ app/crud/calendar.py [待删除]                   │
│   │    └─→ app/schemas/calendar.py [待删除]                │
│   │                                                         │
│  [共享服务] ✅ 保留                                          │
│   ├─→ follow_up_parser.py                                  │
│   │    ├─→ lead_ai.py (AI 创建线索)                         │
│   │    ├─→ customer_ai.py (AI 创建客户)                     │
│   │    ├─→ ai_parser/lead_parser.py                        │
│   │    └─→ ai_parser/customer_parser.py                    │
│                                                             │
│  [UI 组件库] [待删除]                                        │
│   ├─→ components/ui/calendar/*.vue (12 个文件)             │
│   │    └─→ components/crmwolf/index.ts (导出)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

**文档完成日期**: 2026-07-10
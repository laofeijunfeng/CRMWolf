---
status: active
created: 2026-06-17
updated: 2026-06-23
related_plan: ../plans/AI-ASSISTANT-PAGE-IMPLEMENTATION-PLAN.md
---

# AI 助手独立页面需求文档

**文档类型**：需求文档
**创建日期**：2026-06-16
**状态**：draft（待评审）

---

## 一、需求背景

### 1.1 当前问题

| 问题 | 影响 | 严重程度 |
|------|------|----------|
| AI 助手嵌入在各管理页面的 Drawer 中 | 交互割裂，无法形成统一入口 | 高 |
| Drawer 空间受限（420px） | 无法展示完整对话历史和操作预览 | 高 |
| 缺少历史对话列表 | 无法快速切换和回顾之前操作 | 中 |
| 撤销功能未实现 | 操作失误无法恢复，降低使用信心 | 高 |
| 双状态系统并存（Stage + SidebarState） | 状态维护复杂，代码可读性差 | 中 |

### 1.2 用户反馈

> "AI 助手在各个管理页面中，感觉不是很好用，不如直接做成一个单独的页面"

### 1.3 目标

将 AI 助手从 Drawer 模式改为**独立页面**，提供专注、高效的操作体验。

---

## 二、业务场景

### 2.1 目标用户

| 角色 | 使用频率 | 核心诉求 |
|------|----------|----------|
| 销售团队 | 高频（日常） | 快速执行业务操作（创建客户、跟进、商机管理） |
| 销售主管 | 中频 | 查看团队操作记录、审批 |

### 2.2 业务操作类型

系统支持以下业务操作（共 17 种）：

| 分类 | 操作 | 使用频率 |
|------|------|----------|
| **跟进类** | 创建跟进记录、跟进线索 | 高频 |
| **商机类** | 创建商机、推进阶段、赢单/输单 | 高频 |
| **合同类** | 创建合同、查询合同、更新状态 | 中频 |
| **回款类** | 登记回款、确认回款、查询回款记录 | 中频 |
| **发票类** | 申请开票、查询开票申请 | 低频 |

### 2.3 使用场景

| 场景 | 描述 |
|------|------|
| **快速录入** | 销售人员在拜访客户后，快速创建客户或跟进记录 |
| **批量操作** | 处理多个商机或合同的批量状态更新 |
| **信息查询** | 快速查询客户、商机、合同的详细信息 |
| **操作回顾** | 查看历史对话记录，回顾之前的操作 |

---

## 三、功能需求

### 3.1 页面布局

参考 ChatGPT 的成熟设计：

| 区域 | 宽度 | 内容 |
|------|------|------|
| **Header** | 100% 撑满 | 页面标题 + 新对话按钮 + 历史记录入口 |
| **左侧侧边栏** | 固定 280px | 历史对话列表（按日期分组：今天、昨天、更早） |
| **右侧对话区** | flex: 1 | 当前对话 + 内嵌预览卡片 + 输入框 |

### 3.2 Header 功能

| 元素 | 说明 |
|------|------|
| 页面标题 | "AI 助手" |
| 新对话按钮 | 清空当前对话，返回初始状态 |
| 历史记录入口 | 展开/收起侧边栏（响应式时可隐藏） |

**注意**：一级页面，无返回按钮。

### 3.3 左侧侧边栏功能

| 功能 | 说明 |
|------|------|
| 历史对话列表 | 显示用户历史对话记录 |
| 按日期分组 | 今天、昨天、更早 |
| 对话项展示 | 显示对话标题（自动提取：如"创建客户张三"）+ 时间 |
| 点击切换 | 点击历史对话项，切换到该对话上下文 |
| 删除对话 | 支持删除单条历史记录 |

### 3.4 右侧对话区功能

| 功能 | 说明 |
|------|------|
| **欢迎状态** | 初始状态显示欢迎界面 + 快捷操作按钮 |
| **对话气泡** | 用户消息（右侧蓝色）+ AI 消息（左侧灰色） |
| **内嵌预览卡片** | 操作确认前显示参数预览 + 风险等级 + 确认/取消按钮 |
| **状态卡片** | 操作完成后显示成功/失败状态卡片 |
| **输入框** | 居中，max-width: 800px，支持 Enter 提交 |

### 3.5 内嵌预览卡片

根据业务操作类型动态展示参数：

| 操作类型 | 关键参数 |
|----------|----------|
| 创建跟进记录 | 客户名称、跟进内容、跟进方式、下次跟进时间 |
| 商机赢单 | 商机名称、实际成交金额、成交日期 |
| 创建商机 | 客户名称、产品名称、预计金额、预期成交日期 |
| 创建合同 | 客户名称、合同金额、签约日期 |
| 登记回款 | 合同名称、回款金额、回款日期 |

**卡片结构**：
- Header：操作类型图标 + 名称 + 风险等级标签
- 参数区：根据 `action_type` 动态渲染字段（通过配置映射）
- 操作按钮：确认执行 + 取消 + 编辑参数

### 3.6 快捷操作

欢迎状态显示快捷操作按钮：

| 操作 | 说明 |
|------|------|
| 创建客户 | 快速录入新客户 |
| 跟进记录 | 添加跟进日志 |
| 商机赢单 | 标记商机成功 |
| 查询合同 | 查看合同详情 |

---

## 四、交互需求

### 4.1 状态流转

简化为单一状态机：

```
IDLE → COLLECTING → PREVIEW → EXECUTING → COMPLETED → IDLE
```

| 状态 | 说明 | UI 表现 |
|------|------|----------|
| IDLE | 空闲，显示欢迎界面 | 快捷操作按钮 + 输入框 |
| COLLECTING | 解析意图 | 加载动画 + 对话气泡 |
| PREVIEW | 等待确认 | 内嵌预览卡片 |
| EXECUTING | 执行中 | 加载动画 + 停止按钮 |
| COMPLETED | 完成 | 状态卡片 + 新对话按钮 |

### 4.2 响应式布局

| 屏幕宽度 | 布局 |
|----------|------|
| ≥1200px | 左侧侧边栏 280px + 右侧对话区 flex: 1 |
| 768px-1199px | 左侧侧边栏可折叠 + 右侧对话区全宽 |
| <768px | 侧边栏隐藏（通过 Header 按钮展开）+ 对话区全宽 |

---

## 五、非功能需求

### 5.1 性能要求

| 验收项 | 标准 |
|--------|------|
| 页面加载 | < 1s |
| 状态转换响应 | < 100ms |
| 对话气泡渲染 | < 50ms |

### 5.2 可访问性

| 验收项 | 标准 |
|--------|------|
| 键盘导航 | 支持 Tab 切换焦点 |
| 屏幕阅读器 | 关键元素添加 aria-label |
| 对比度 | 符合 WCAG AA 标准 |

---

## 六、验收标准

### 6.1 功能验收

| 验收项 | 标准 |
|--------|------|
| 页面布局 | Header 撑满 + 左侧侧边栏 + 右侧对话区 |
| 历史对话列表 | 按日期分组显示，支持切换 |
| 对话气泡 | 用户/AI 消息区分显示 |
| 内嵌预览卡片 | 根据 action_type 动态渲染参数 |
| 快捷操作 | 4 个快捷按钮，点击填充输入框 |
| 响应式布局 | 小屏侧边栏可折叠 |

### 6.2 体验验收

| 验收项 | 标准 |
|--------|------|
| 新对话 | 清空对话，返回欢迎状态 |
| 停止操作 | 中断执行，返回 IDLE |
| 撤销操作 | 显示撤销提示（复用现有 UndoToast） |

---

## 七、影响分析

### 7.1 影响范围

| 文件/模块 | 改动类型 |
|-----------|----------|
| 新增：`AIAssistant.vue` | 独立页面组件 |
| 修改：`router/index.ts` | 新增路由 |
| 新增：`PreviewCard.vue` | 内嵌预览卡片组件 |
| 新增：`previewFieldConfig.ts` | 字段映射配置 |
| 新增：`HistoryList.vue` | 历史对话列表组件 |
| 新增：`stores/aiConversation.ts` | AI 对话历史 Store |
| 新增：`api/aiConversation.ts` | AI 对话历史 API |
| 删除：`MagicWandDialog.vue` | 移除 Drawer 模式 |

### 7.2 与现有功能的关系

| 现有功能 | 处理方式 |
|----------|----------|
| `MagicWandDialog.vue` | **移除**（统一为独立页面入口） |
| `useSidebarState.ts` | 复用（独立页面使用此状态管理） |
| `aiAssistant.ts API` | 复用（聊天 API 不改动） |

---

## 八、已确认决策

### 8.1 决策记录

| 问题 | 决策 | 理由 |
|------|------|------|
| 历史对话持久化 | **服务器存储** | 企业级 CRM 标准做法，数据安全、跨设备同步、审计合规 |
| 侧边栏默认状态 | **默认展开** | 提升历史对话可见性 |
| MagicWandDialog Drawer | **移除** | 统一入口，避免双模式维护成本 |

---

## 九、服务器存储技术方案

### 9.1 数据库表设计

```sql
-- AI 对话历史表
CREATE TABLE ai_conversation_history (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  team_id BIGINT NOT NULL,                    -- 团队隔离
  user_id BIGINT NOT NULL,                    -- 用户归属
  title VARCHAR(200),                         -- 对话标题（自动提取）
  summary TEXT,                               -- 对话摘要
  action_type VARCHAR(50),                    -- 主要操作类型
  entity_type VARCHAR(20),                    -- 关联实体类型
  entity_id BIGINT,                           -- 关联实体 ID
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  INDEX idx_team_user (team_id, user_id),
  INDEX idx_created_at (created_at)
);
```

### 9.2 API 端点设计

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/assistant/conversations` | GET | 获取历史对话列表（分页，按日期分组） |
| `/api/v1/assistant/conversations/:id` | GET | 获取单个对话详情 |
| `/api/v1/assistant/conversations/:id` | DELETE | 删除对话记录 |
| `/api/v1/assistant/conversations/search` | GET | 搜索对话（按关键词/实体） |

### 9.3 请求/响应格式

**获取历史对话列表**：

```typescript
// Request
GET /api/v1/assistant/conversations?page=1&pageSize=20

// Response
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": 1,
        "title": "创建客户张三",
        "action_type": "create_customer",
        "entity_type": "customer",
        "entity_id": 123,
        "created_at": "2024-01-15T10:30:00"
      }
    ],
    "total": 50,
    "groups": {
      "today": [...],
      "yesterday": [...],
      "earlier": [...]
    }
  }
}
```

### 9.4 Store 设计

```typescript
// stores/aiConversation.ts
export const useAIConversationStore = defineStore('aiConversation', {
  state: () => ({
    history: [] as ConversationHistory[],
    currentConversation: null as ConversationHistory | null,
    loading: false
  }),
  
  actions: {
    async fetchHistory(page: number) {
      this.loading = true
      const res = await aiConversationApi.getHistory(page)
      this.history = res.data.groups
      this.loading = false
    },
    
    async deleteConversation(id: number) {
      await aiConversationApi.delete(id)
      this.history = this.history.filter(c => c.id !== id)
    }
  }
})
```

---

**文档状态**：confirmed
**下一步**：设计方案 → 实施计划
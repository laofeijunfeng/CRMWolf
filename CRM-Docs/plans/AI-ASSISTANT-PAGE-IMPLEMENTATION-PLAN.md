# AI 助手独立页面实施计划

**文档类型**：实施计划
**创建日期**：2026-06-17
**状态**：ready（待执行）
**依据设计**：[AI-ASSISTANT-PAGE-DESIGN.md](./AI-ASSISTANT-PAGE-ASSISTANT-PAGE-DESIGN.md)

---

## 一、实施阶段概览

| Phase | 内容 | 工作量 | 优先级 |
|-------|------|--------|--------|
| **Phase 0** | 前端基础架构（路由、Store骨架） | 0.5天 | P0 |
| **Phase 1** | 页面骨架组件（布局、Header、侧边栏） | 1天 | P0 |
| **Phase 2** | 对话区组件（欢迎界面、对话气泡） | 1天 | P0 |
| **Phase 3** | 内嵌预览卡片组件 | 1天 | P0 |
| **Phase 4** | 输入区组件 | 0.5天 | P0 |
| **Phase 5** | 后端API + 数据库表 | 1天 | P0 |
| **Phase 6** | 响应式布局 + 测试验证 | 1天 | P0 |

**总工作量**：约 5天

---

## 二、Phase 0：前端基础架构

### 任务清单

| 任务 | 输出 |
|------|------|
| 创建路由配置 | `router/index.ts` 新增路由 |
| 创建 Store 骨架 | `stores/aiConversation.ts` |
| 创建 API 骤骨架 | `api/aiConversation.ts` |

### 技术方案

**路由配置**：
```typescript
// router/index.ts
{
  path: 'ai-assistant',
  name: 'AIAssistant',
  component: () => import('@/views/AIAssistant.vue'),
  meta: { requiresAuth: true }
}
```

**Store 骨架**：
```typescript
// stores/aiConversation.ts
export const useAIConversationStore = defineStore('aiConversation', {
  state: () => ({
    history: [] as ConversationHistory[],
    currentId: null as number | null,
    loading: false
  }),
  actions: {
    async fetchHistory() { /* TODO */ },
    async loadConversation(id: number) { /* TODO */ },
    async deleteConversation(id: number) { /* TODO */ }
  }
})
```

---

## 三、Phase 1：页面骨架组件

### 任务清单

| 任务 | 输出 |
|------|------|
| 创建页面主组件 | `AIAssistant.vue` |
| 创建历史列表组件 | `HistoryList.vue` |
| 创建历史项组件 | `HistoryItem.vue` |

### 技术方案

**页面主组件结构**：
```vue
<template>
  <div class="ai-assistant-page">
    <PageHeader />
    <main class="page-main">
      <HistoryList />
      <ConversationArea />
    </main>
    <ChatInput />
  </div>
</template>
```

---

## 四、Phase 2：对话区组件

### 任务清单

| 任务 | 输出 |
|------|------|
| 创建欢迎界面 | `WelcomeScreen.vue` |
| 创建对话气泡 | `ChatBubble.vue` |

---

## 五、Phase 3：内嵌预览卡片

### 任务清单

| 任务 | 输出 |
|------|------|
| 创建预览卡片 | `PreviewCard.vue` |
| 创建字段映射配置 | `previewFieldConfig.ts` |
| 创建字段项组件 | `PreviewField.vue` |

---

## 六、Phase 4：输入区组件

### 任务清单

| 任务 | 输出 |
|------|------|
| 创建输入组件 | `ChatInput.vue` |
| 集成 SSE 请求 | 复用现有 `aiAssistantApi` |

---

## 七、Phase 5：后端API + 数据库

### 任务清单

| 任务 | 输出 |
|------|------|
| 创建数据库迁移 | Alembic migration |
| 创建 CRUD 层 | `ai_conversation_history_crud.py` |
| 创建 API 端点 | `/api/v1/assistant/conversations` |

---

## 八、Phase 6：响应式布局 + 测试

### 任务清单

| 任务 | 输出 |
|------|------|
| 响应式 CSS | Media Query |
| 组件单元测试 | Vitest 测试文件 |
| 验收测试 | 手动测试清单 |

---

## 九、文件变更清单

### 新增文件

| 文件 | 类型 |
|------|------|
| `src/views/AIAssistant.vue` | 页面组件 |
| `src/components/ai-assistant/HistoryList.vue` | 组件 |
| `src/components/ai-assistant/HistoryItem.vue` | 组件 |
| `src/components/ai-assistant/WelcomeScreen.vue` | 组件 |
| `src/components/ai-assistant/ChatBubble.vue` | 组件 |
| `src/components/ai-assistant/PreviewCard.vue` | 组件 |
| `src/components/ai-assistant/PreviewField.vue` | 组件 |
| `src/components/ai-assistant/ChatInput.vue` | 组件 |
| `src/config/previewFieldConfig.ts` | 配置 |
| `src/stores/aiConversation.ts` | Store |
| `src/api/aiConversation.ts` | API |
| `CRM-Server/app/models/ai_conversation_history.py` | Model |
| `CRM-Server/app/crud/ai_conversation_history_crud.py` | CRUD |
| `CRM-Server/app/api/v1/assistant/conversations.py` | API |

### 删除文件

| 文件 | 原因 |
|------|------|
| `src/components/MagicWandDialog.vue` | Drawer 模式移除 |

---

## 十、验收清单

| 验收项 | 标准 |
|--------|------|
| 页面布局 | Header + 侧边栏(280px) + 对话区 |
| 历史对话列表 | 按日期分组，实体标签显示 |
| 对话气泡 | 用户/AI 区分，内嵌预览卡片 |
| 内嵌预览卡片 | 参数动态渲染，确认/取消按钮 |
| 响应式布局 | 小屏侧边栏可折叠 |
| API 功能 | 列表/详情/删除 |
| 单元测试 | 覆盖率 ≥80% |

---

**实施计划状态**：ready
**下一步**：开始 Phase 0 实施
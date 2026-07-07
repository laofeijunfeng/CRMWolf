# AI 助手与 Skills 功能清理设计规范

**日期**: 2026-07-07
**状态**: Draft
**范围**: 全系统清理

---

## 1. 背景

系统包含两套 AI 对话功能需要清理：

1. **AI 助手** (AI Assistant) - 对话式 AI 交互界面，基于 Glue DialogueEngine + SSE 流式响应
2. **Skills** - AI 能力扩展框架，包含动态 Prompt、Handler 体系、CRUD/Enum 映射

清理原因：功能不再需要，移除以减少代码维护负担。

**重要约束**: 不能影响其他 AI 相关功能，包括：
- AIConfig (模型/提供商配置)
- `/api/ai/actions` (程序化 AI 动作执行层)
- Domain-specific AI APIs (`customer_ai`, `lead_ai`, `approval_ai`, `procurement_ai`)
- `customer_profile_service` (客户档案 AI 生成)

---

## 2. 依赖分析

### 2.1 共享依赖发现

| 文件 | 依赖 | 处理方式 |
|------|------|----------|
| `ai_service.py` | `dynamic_prompt_service` | 删除 Skills 相关方法，保留底层 SSE 调用 |
| `entity_search.py` | `EntityCandidate` (Glue types) | 删除整个文件 |
| `AIParsedIntent` schema | Skills 模型定义 | 删除整个 schema 文件 |
| `calendar.py` | `dynamic_prompt_service`, `dynamic_skill_service` | 删除 follow-up AI 端点 |

### 2.2 程序化 AI Actions (保留)

以下组件 **不依赖 Skills/Glue**，必须保留：

- `app/services/ai/action_entry.py` - Preview/Gate/Audit 入口
- `app/services/ai/action_executor.py` - CRUD 调用层
- `app/services/ai/idempotency.py` - 幂等性管理
- `app/services/ai/intent_parser.py` - 意图解析
- `app/api/ai/actions.py` - HTTP 适配层
- `app/api/ai/deps.py` - AI 用户上下文

---

## 3. 清理范围

### Phase 1: Frontend (CRM-Client)

#### 删除文件

| 文件/目录 | 说明 |
|-----------|------|
| `src/views/AIAssistant.vue` | AI 助手主页面 |
| `src/views/AISkills.vue` | Skills 管理页面 |
| `src/components/ai-assistant/*` | AI 助手组件目录（ChatBubble, ChatInput, HistoryList 等） |
| `src/components/SkillGeneratorDialog.vue` | Skill 生成对话框 |
| `src/api/aiAssistant.ts` | AI 助手 API |
| `src/api/aiSkills.ts` | Skills API |
| `src/composables/useGluePhases.ts` | Glue Phases composable |
| `src/types/aiAssistant.ts` | AI 助手类型定义 |
| `src/stores/aiConversation.ts` | AI 对话状态管理（如存在） |
| `src/views/__tests__/AIAssistant-*.test.ts` | AI 助手测试文件 |

#### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/router/index.ts` | 删除 `{ path: 'ai-assistant', name: 'AIAssistant', ... }` 路由 |

---

### Phase 2: Backend API (CRM-Server)

#### 删除文件

| 文件 | 说明 |
|------|------|
| `app/api/agent_assistant.py` | Glue 代理端点 `/v1/agent/chat` |
| `app/api/ai_conversation_history.py` | 对话历史端点 |
| `app/api/ai/intents.py` | Skills 意图端点 |
| `app/api/ai/logs.py` | Skills 日志端点 |
| `app/api/ai/metadata.py` | Skills 元数据端点 |

**保留** `app/api/ai/actions.py` 和 `app/api/ai/deps.py`

#### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `app/api/calendar.py` | 删除 `parse_follow_up` 和 `execute_follow_up` 端点（约 line 95-191） |
| `app/main.py` | 删除以下 import 和 router 注册：<br>- `agent_assistant_router`<br>- `ai_conversation_history_router`<br>- `glue_router` |

---

### Phase 3: Backend Models & CRUD

#### 删除文件

| 文件 | 说明 |
|------|------|
| `app/models/ai_conversation_history.py` | AI 对话历史模型 |
| `app/models/ai_skill.py` | Skill/Action/Mapping 模型 |
| `app/crud/ai_conversation_history_crud.py` | 对话历史 CRUD |
| `app/crud/ai_skill.py` | Skill CRUD |
| `app/crud/ai_crud_mapping.py` | CRUD 映射 |
| `app/crud/ai_enum_mapping.py` | Enum 映射 |

#### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `app/models/__init__.py` | 删除导出：`AISkill`, `AISkillAction`, `AICRUDMapping`, `AIEnumMapping`, `AIConversationHistory` |
| `app/crud/__init__.py` | 删除导出：`ai_skill_crud`, `ai_skill_action_crud` |

---

### Phase 4: Backend Schemas

#### 删除文件

| 文件 | 说明 |
|------|------|
| `app/schemas/web_assistant.py` | Web 助手 schema |
| `app/schemas/ai_skill.py` | Skill schema（含 AIParsedIntent） |
| `app/schemas/ai_skill_config.py` | Skill 配置 schema |

#### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `app/schemas/__init__.py` | 删除导出：`AIParsedIntent`, `SkillExecutionResult`, `SkillDefinition`, `SkillActionDefinition` |

---

### Phase 5: Backend Services

#### 删除目录/文件

| 目录/文件 | 说明 |
|-----------|------|
| `app/services/skills/*` | 整个 Skills 服务目录（含 handlers 子目录） |
| `app/glue/*` | 整个 Glue 框架目录 |
| `app/services/ai/entity_search.py` | 实体搜索服务（依赖 Glue EntityCandidate） |

#### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `app/services/ai_service.py` | 1. 删除 import `from app.schemas.ai_skill import AIParsedIntent`<br>2. 删除 import `from app.services.skills.dynamic_prompt_service import dynamic_prompt_service`<br>3. 删除方法 `parse_intent`<br>4. 删除方法 `_get_system_prompt`<br>5. 删除方法 `stream_intent_parse`（使用 AIParsedIntent）<br>**保留**: `_stream_chat_collect`, `get_config_and_key`, `test_connection` |
| `app/services/ai/__init__.py` | 删除导出 `EntitySearchService` |

---

### Phase 6: Migrations & Scripts

#### 删除文件

| 文件 | 说明 |
|------|------|
| `migrations/add_ai_skill_tables.py` | Skill 表迁移脚本 |
| `migrations/add_ai_action_params_table.py` | Action 参数表迁移脚本 |
| `scripts/migrate_skills_to_db.py` | Skills 数据迁移脚本 |
| `scripts/migrate_skill_name_lookup.py` | Skill 名称查找迁移脚本 |
| `scripts/add_next_action_to_skill.py` | 添加 next_action 脚本 |
| `scripts/migrate_opportunity_stage_skill.py` | 商机阶段 Skill 迁移脚本 |
| `scripts/seed_action_params.py` | Action 参数种子数据脚本 |

---

## 4. 保留组件

以下组件 **不删除**，确保其他 AI 功能正常工作：

| 组件 | 用途 | 依赖关系 |
|------|------|----------|
| `AIConfig.vue` | AI 配置界面 | 用户明确保留 |
| `app/api/ai_config.py` | AI 配置 API | 被 customer_profile_service 等使用 |
| `app/models/ai_config.py` | AI 配置模型 | 共享配置存储 |
| `app/crud/ai_config.py` | AI 配置 CRUD | 共享 CRUD 层 |
| `/api/ai/actions.py` | 程序化 AI 动作 | 无 Skills 依赖 |
| `app/services/ai/action_entry.py` | Action 入口函数 | 无 Skills 依赖 |
| `app/services/ai/action_executor.py` | Action 执行器 | 无 Skills 依赖 |
| `app/services/ai/idempotency.py` | 幂等性管理 | 无 Skills 依赖 |
| `app/services/ai/intent_parser.py` | 意图解析 | 无 Skills 依赖 |
| `app/services/customer_profile_service.py` | 客户档案生成 | 仅使用 `_stream_chat_collect`，不依赖 Skills |
| `app/api/customer_ai.py` | 客户 AI 搜索 | 独立功能 |
| `app/api/lead_ai.py` | 线索 AI 功能 | 独立功能 |
| `app/api/approval_ai.py` | 审批 AI 功能 | 独立功能 |
| `app/api/procurement_ai.py` | 采购 AI 功能 | 独立功能 |

---

## 5. 验证计划

### 5.1 代码检查

1. **类型检查**
   ```bash
   # Backend
   cd CRM-Server && mypy app/
   
   # Frontend
   cd CRM-Client && npm run type-check
   ```

2. **Lint 检查**
   ```bash
   # Backend
   cd CRM-Server && ruff check app/
   
   # Frontend
   cd CRM-Client && npm run lint
   ```

3. **导入检查**
   ```bash
   # 确认无残留导入
   grep -rn "from app.glue" CRM-Server/app --include="*.py"
   grep -rn "from app.services.skills" CRM-Server/app --include="*.py"
   grep -rn "from app.models.ai_skill" CRM-Server/app --include="*.py"
   ```

### 5.2 功能测试

| 测试项 | 方法 | 预期结果 |
|--------|------|----------|
| `/api/ai/actions` 端点 | 发送 HTTP 请求 | 正常响应 |
| `/api/ai-config` 端点 | 发送 HTTP 请求 | 正常响应 |
| Domain AI APIs | 测试 customer_ai, lead_ai 等 | 正常响应 |
| Customer Profile 生成 | 创建客户触发 | 正常生成档案 |
| AI 助手路由 | 访问 `/ai-assistant` | 404 或重定向 |

### 5.3 数据库清理（可选）

Skills 相关表数据可保留（不影响功能），如需清理：

```bash
# 创建清理迁移（可选）
alembic revision -m "drop_ai_skill_tables"
# 编辑迁移文件添加 DROP TABLE 语句
alembic upgrade head
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 遗漏导入依赖 | 运行时 ImportError | 全面 grep 检查 + 类型检查 |
| Calendar AI 功能缺失 | 用户无法快速跟进 | 功能已确认删除，无影响 |
| 数据库表残留 | 存储空间占用 | 可选 Alembic 清理 |
| 前端路由残留 | 404 页面 | Router 配置清理确认 |

---

## 7. 实施顺序

```
Phase 1 (Frontend) → Phase 2 (Backend API) → Phase 3 (Models/CRUD)
→ Phase 4 (Schemas) → Phase 5 (Services) → Phase 6 (Migrations/Scripts)
→ Verification
```

建议按 Phase 顺序依次执行，每 Phase 完成后运行类型检查，确保无编译错误。

---

## 附录：文件清单

### A. 删除文件完整列表

**Frontend (CRM-Client):**
- src/views/AIAssistant.vue
- src/views/AISkills.vue
- src/components/ai-assistant/*.vue
- src/components/SkillGeneratorDialog.vue
- src/api/aiAssistant.ts
- src/api/aiSkills.ts
- src/composables/useGluePhases.ts
- src/types/aiAssistant.ts
- src/stores/aiConversation.ts
- src/views/__tests__/AIAssistant-*.test.ts

**Backend (CRM-Server):**
- app/api/agent_assistant.py
- app/api/ai_conversation_history.py
- app/api/ai/intents.py
- app/api/ai/logs.py
- app/api/ai/metadata.py
- app/models/ai_conversation_history.py
- app/models/ai_skill.py
- app/crud/ai_conversation_history_crud.py
- app/crud/ai_skill.py
- app/crud/ai_crud_mapping.py
- app/crud/ai_enum_mapping.py
- app/schemas/web_assistant.py
- app/schemas/ai_skill.py
- app/schemas/ai_skill_config.py
- app/services/skills/* (directory)
- app/glue/* (directory)
- app/services/ai/entity_search.py
- migrations/add_ai_skill_tables.py
- migrations/add_ai_action_params_table.py
- scripts/migrate_skills_to_db.py
- scripts/migrate_skill_name_lookup.py
- scripts/add_next_action_to_skill.py
- scripts/migrate_opportunity_stage_skill.py
- scripts/seed_action_params.py

### B. 修改文件完整列表

- src/router/index.ts
- app/main.py
- app/api/calendar.py
- app/models/__init__.py
- app/crud/__init__.py
- app/schemas/__init__.py
- app/services/ai_service.py
- app/services/ai/__init__.py
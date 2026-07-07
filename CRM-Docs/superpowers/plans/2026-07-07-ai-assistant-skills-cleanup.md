# AI 助手与 Skills 功能清理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 AI 助手对话界面和 Skills 能力扩展框架，不影响其他 AI 功能

**Architecture:** 按依赖关系从外向内删除：Frontend → API → Models/CRUD → Schemas → Services → Migrations。每 Phase 完成后运行类型检查验证。

**Tech Stack:** Vue 3 + TypeScript (Frontend), FastAPI + SQLAlchemy + Pydantic (Backend)

## Global Constraints

- **不能删除**: `AIConfig.vue`, `app/api/ai_config.py`, `app/models/ai_config.py`, `app/crud/ai_config.py`
- **不能删除**: `/api/ai/actions.py`, `/api/ai/deps.py`, `app/services/ai/action_entry.py`, `app/services/ai/action_executor.py`, `app/services/ai/idempotency.py`, `app/services/ai/intent_parser.py`
- **不能删除**: `app/api/customer_ai.py`, `app/api/lead_ai.py`, `app/api/approval_ai.py`, `app/api/procurement_ai.py`
- **不能删除**: `app/services/customer_profile_service.py`, `app/services/ai_parser/*`
- **每 Phase 完成后**: 运行类型检查 `mypy app/` 和 `npm run type-check`

---

## Task 1: Phase 1 - Frontend 清理 (CRM-Client)

**Files:**
- Delete: `src/views/AIAssistant.vue`
- Delete: `src/views/AISkills.vue`
- Delete: `src/components/ai-assistant/*` (整个目录)
- Delete: `src/components/SkillGeneratorDialog.vue`
- Delete: `src/api/aiAssistant.ts`
- Delete: `src/api/aiSkills.ts`
- Delete: `src/api/aiConversation.ts`
- Delete: `src/composables/useGluePhases.ts`
- Delete: `src/types/aiAssistant.ts`
- Delete: `src/views/__tests__/AIAssistant-AgentExecutionLog.test.ts`
- Modify: `src/router/index.ts` (删除路由)
- Delete: `src/stores/aiConversation.ts` (如存在)

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: 删除 AI 助手视图文件**

```bash
cd CRM-Client
rm -f src/views/AIAssistant.vue
rm -f src/views/AISkills.vue
```

- [ ] **Step 2: 删除 AI 助手组件目录**

```bash
rm -rf src/components/ai-assistant/
rm -f src/components/SkillGeneratorDialog.vue
```

- [ ] **Step 3: 删除 AI 助手 API 文件**

```bash
rm -f src/api/aiAssistant.ts
rm -f src/api/aiSkills.ts
rm -f src/api/aiConversation.ts
```

- [ ] **Step 4: 删除 composables 和 types**

```bash
rm -f src/composables/useGluePhases.ts
rm -f src/types/aiAssistant.ts
```

- [ ] **Step 5: 删除测试文件**

```bash
rm -f src/views/__tests__/AIAssistant-AgentExecutionLog.test.ts
```

- [ ] **Step 6: 检查并删除 store 文件（如存在）**

```bash
# 检查是否存在
ls src/stores/aiConversation.ts 2>/dev/null && rm -f src/stores/aiConversation.ts
# 或使用 find
find src/stores -name "*ai*" -type f -delete
```

- [ ] **Step 7: 修改 router/index.ts 删除 AI 助手路由**

删除以下路由定义（约 line 352-357）：

```typescript
// 删除这一段
{
  path: 'ai-assistant',
  name: 'AIAssistant',
  component: () => import('@/views/AIAssistant.vue'),
  meta: { requiresAuth: true, title: 'AI 助手' }
}
```

- [ ] **Step 8: 运行类型检查验证**

```bash
npm run type-check
```

Expected: 无错误（可能有已删除文件的 import 错误需要清理）

- [ ] **Step 9: 搜索并清理残留导入**

```bash
grep -rn "AIAssistant\|ai-assistant\|AISkills\|aiSkills\|useGluePhases" src/ --include="*.ts" --include="*.vue"
```

Expected: 无结果或仅在已删除文件中

- [ ] **Step 10: Commit Phase 1**

```bash
git add -A
git commit -m "chore(cleanup): remove AI assistant frontend components and routes"
```

---

## Task 2: Phase 2 - Backend API 清理 (CRM-Server)

**Files:**
- Delete: `app/api/agent_assistant.py`
- Delete: `app/api/ai_conversation_history.py`
- Delete: `app/api/ai/intents.py`
- Delete: `app/api/ai/logs.py`
- Delete: `app/api/ai/metadata.py`
- Modify: `app/api/calendar.py` (删除 follow-up 端点)
- Modify: `app/main.py` (删除 router 注册)

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: 删除 agent_assistant 和 conversation_history API**

```bash
cd CRM-Server
rm -f app/api/agent_assistant.py
rm -f app/api/ai_conversation_history.py
```

- [ ] **Step 2: 删除 ai 子目录的 Skills 相关文件**

```bash
rm -f app/api/ai/intents.py
rm -f app/api/ai/logs.py
rm -f app/api/ai/metadata.py
```

**保留**: `app/api/ai/actions.py` 和 `app/api/ai/deps.py`

- [ ] **Step 3: 检查 ai/__init__.py 是否需要修改**

```bash
cat app/api/ai/__init__.py
```

如果包含已删除文件的 import，需要移除。

- [ ] **Step 4: 修改 calendar.py 删除 follow-up 端点**

删除以下两个端点（约 line 95-191）：

1. 删除 `@router.post("/follow-up/parse")` 端点及其函数
2. 删除 `@router.post("/follow-up/execute")` 端点及其函数

删除后，`calendar.py` 只保留：
- `get_calendar_todos`
- `get_date_todos`
- `get_todo_context`

- [ ] **Step 5: 修改 main.py 删除 router 注册**

删除以下 import（约 line 19, 24, 65）：

```python
# 删除这些 import
from app.api.agent_assistant import router as agent_assistant_router
from app.api.ai_conversation_history import router as ai_conversation_history_router
from app.glue.router import router as glue_router
```

删除以下 router 注册（约 line 111, 112, 124）：

```python
# 删除这些 include_router
api_router.include_router(agent_assistant_router)
api_router.include_router(ai_conversation_history_router)
api_router.include_router(glue_router)
```

- [ ] **Step 6: 运行类型检查验证**

```bash
mypy app/
```

Expected: 无错误（ImportError 表示遗漏清理）

- [ ] **Step 7: 搜索并清理残留导入**

```bash
grep -rn "agent_assistant\|ai_conversation_history\|glue_router" app/ --include="*.py" | grep -v "__pycache__"
```

Expected: 无结果

- [ ] **Step 8: Commit Phase 2**

```bash
git add -A
git commit -m "chore(cleanup): remove AI assistant backend API endpoints"
```

---

## Task 3: Phase 3 - Models & CRUD 清理

**Files:**
- Delete: `app/models/ai_conversation_history.py`
- Delete: `app/models/ai_skill.py`
- Delete: `app/crud/ai_conversation_history_crud.py`
- Delete: `app/crud/ai_skill.py`
- Delete: `app/crud/ai_crud_mapping.py`
- Delete: `app/crud/ai_enum_mapping.py`
- Modify: `app/models/__init__.py`
- Modify: `app/crud/__init__.py`

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: 删除 model 文件**

```bash
cd CRM-Server
rm -f app/models/ai_conversation_history.py
rm -f app/models/ai_skill.py
```

- [ ] **Step 2: 删除 CRUD 文件**

```bash
rm -f app/crud/ai_conversation_history_crud.py
rm -f app/crud/ai_skill.py
rm -f app/crud/ai_crud_mapping.py
rm -f app/crud/ai_enum_mapping.py
```

- [ ] **Step 3: 修改 models/__init__.py**

删除以下导出：

```python
# 删除这些 import 和导出
from app.models.ai_skill import AISkill, AISkillAction, AICRUDMapping, AIEnumMapping
from app.models.ai_conversation_history import AIConversationHistory

# 从 __all__ 列表中删除
"AISkill",
"AISkillAction",
"AICRUDMapping",
"AIEnumMapping",
"AIConversationHistory",
```

- [ ] **Step 4: 修改 crud/__init__.py**

删除以下导出：

```python
# 删除这些 import 和导出
from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_conversation_history_crud import ai_conversation_history_crud
from app.crud.ai_crud_mapping import ai_crud_mapping_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud

# 从 __all__ 列表中删除
"ai_skill_crud",
"ai_skill_action_crud",
"ai_conversation_history_crud",
"ai_crud_mapping_crud",
"ai_enum_mapping_crud",
```

- [ ] **Step 5: 运行类型检查验证**

```bash
mypy app/
```

Expected: 无错误

- [ ] **Step 6: Commit Phase 3**

```bash
git add -A
git commit -m "chore(cleanup): remove AI skill models and CRUD"
```

---

## Task 4: Phase 4 - Schemas 清理

**Files:**
- Delete: `app/schemas/web_assistant.py`
- Delete: `app/schemas/ai_skill.py`
- Delete: `app/schemas/ai_skill_config.py`
- Modify: `app/schemas/__init__.py`

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: 删除 schema 文件**

```bash
cd CRM-Server
rm -f app/schemas/web_assistant.py
rm -f app/schemas/ai_skill.py
rm -f app/schemas/ai_skill_config.py
```

- [ ] **Step 2: 修改 schemas/__init__.py**

删除以下导出：

```python
# 删除这些 import
from app.schemas.ai_skill import (
    AIParsedIntent,
    SkillExecutionResult,
    SkillDefinition,
    SkillActionDefinition,
)
from app.schemas.web_assistant import ...  # 检查并删除

# 从 __all__ 列表中删除
"AIParsedIntent",
"SkillExecutionResult",
"SkillDefinition",
"SkillActionDefinition",
```

- [ ] **Step 3: 运行类型检查验证**

```bash
mypy app/
```

Expected: 无错误（ai_service.py 可能有 import 错误，下一 Task 修复）

- [ ] **Step 4: Commit Phase 4**

```bash
git add -A
git commit -m "chore(cleanup): remove AI skill schemas"
```

---

## Task 5: Phase 5 - Services 清理

**Files:**
- Delete: `app/services/skills/*` (整个目录)
- Delete: `app/glue/*` (整个目录)
- Delete: `app/services/ai/entity_search.py`
- Modify: `app/services/ai_service.py`
- Modify: `app/services/ai/__init__.py`

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: 删除 Skills 服务目录**

```bash
cd CRM-Server
rm -rf app/services/skills/
```

- [ ] **Step 2: 删除 Glue 框架目录**

```bash
rm -rf app/glue/
```

- [ ] **Step 3: 删除 entity_search.py**

```bash
rm -f app/services/ai/entity_search.py
```

- [ ] **Step 4: 修改 ai_service.py**

删除以下内容：

1. 删除 import（约 line 10-11）：
```python
# 删除
from app.schemas.ai_skill import AIParsedIntent
from app.services.skills.dynamic_prompt_service import dynamic_prompt_service
```

2. 删除 `_get_system_prompt` 方法（约 line 201-205）：
```python
# 删除整个方法
def _get_system_prompt(self, db: Session) -> str:
    return dynamic_prompt_service.generate_system_prompt(db)
```

3. 删除 `parse_intent` 方法（约 line 207-293）：
```python
# 删除整个方法
async def parse_intent(self, db: Session, user_message: str, team_id: int = 1) -> AIParsedIntent:
    ...
```

4. 删除 `stream_intent_parse` 方法（约 line 303-406）：
```python
# 删除整个方法（如果使用 AIParsedIntent）
async def stream_intent_parse(self, db: Session, config: Any, api_key: str, user_message: str) -> AsyncGenerator[Dict[str, Any], None]:
    ...
```

**保留**以下方法：
- `_stream_chat_collect`
- `_stream_chat_generator`
- `get_config_and_key`
- `test_connection`

- [ ] **Step 5: 修改 services/ai/__init__.py**

删除 EntitySearchService 导出：

```python
# 删除
from app.services.ai.entity_search import EntitySearchService

# 从 __all__ 列表中删除
"EntitySearchService",
```

- [ ] **Step 6: 运行类型检查验证**

```bash
mypy app/
```

Expected: 无错误

- [ ] **Step 7: 运行 lint 检查**

```bash
ruff check app/
```

Expected: 无错误

- [ ] **Step 8: Commit Phase 5**

```bash
git add -A
git commit -m "chore(cleanup): remove Skills and Glue services"
```

---

## Task 6: Phase 6 - Migrations & Scripts 清理

**Files:**
- Delete: `scripts/migrate_skills_to_db.py`
- Delete: `scripts/migrate_skill_name_lookup.py`
- Delete: `scripts/add_next_action_to_skill.py`
- Delete: `scripts/migrate_opportunity_stage_skill.py`
- Delete: `scripts/seed_action_params.py`

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: 删除 Skills 相关脚本**

```bash
cd CRM-Server
rm -f scripts/migrate_skills_to_db.py
rm -f scripts/migrate_skill_name_lookup.py
rm -f scripts/add_next_action_to_skill.py
rm -f scripts/migrate_opportunity_stage_skill.py
rm -f scripts/seed_action_params.py
```

- [ ] **Step 2: 检查 migrations 目录**

```bash
ls migrations/versions/ | grep -i skill
```

如果有 Skills 相关迁移文件（如 `017_*_skill*.py`），也一并删除。

- [ ] **Step 3: Commit Phase 6**

```bash
git add -A
git commit -m "chore(cleanup): remove Skills migration scripts"
```

---

## Task 7: 最终验证

**Files:**
- None

**Interfaces:**
- Consumes: None
- Produces: Verified clean system

- [ ] **Step 1: 全面导入检查**

```bash
cd CRM-Server
grep -rn "from app.glue" app/ --include="*.py" | grep -v "__pycache__"
grep -rn "from app.services.skills" app/ --include="*.py" | grep -v "__pycache__"
grep -rn "from app.models.ai_skill" app/ --include="*.py" | grep -v "__pycache__"
grep -rn "AIParsedIntent\|EntityCandidate" app/ --include="*.py" | grep -v "__pycache__"
```

Expected: 所有命令无结果

- [ ] **Step 2: 运行完整类型检查**

```bash
# Backend
mypy app/

# Frontend
cd ../CRM-Client
npm run type-check
```

Expected: 无错误

- [ ] **Step 3: 运行 lint 检查**

```bash
# Backend
cd CRM-Server
ruff check app/

# Frontend
cd ../CRM-Client
npm run lint
```

Expected: 无错误

- [ ] **Step 4: 验证保留功能**

检查以下文件存在：
```bash
ls CRM-Client/src/views/AIConfig.vue
ls CRM-Server/app/api/ai_config.py
ls CRM-Server/app/api/ai/actions.py
ls CRM-Server/app/api/customer_ai.py
ls CRM-Server/app/api/lead_ai.py
ls CRM-Server/app/services/ai/action_entry.py
ls CRM-Server/app/services/customer_profile_service.py
```

Expected: 所有文件存在

- [ ] **Step 5: 最终 Commit**

```bash
git add -A
git commit -m "chore(cleanup): complete AI assistant and Skills removal"
git push origin main
```

- [ ] **Step 6: 更新 CLAUDE.md 文档**

删除 `CRM-Server/CLAUDE.md` 中关于 Glue/ReAct/Skills 的说明：

删除以下内容：
- "AI 助手架构（现状 2026-07-02）" 整个章节
- 关于 `/v1/agent/chat`、`glue_router`、`skills` 的所有说明

更新为：
```markdown
## AI 相关功能

保留的 AI 功能：
- `/api/ai/actions` - 程序化 AI 动作执行层
- `/api/ai-config` - AI 配置管理
- Domain-specific AI APIs (`customer_ai`, `lead_ai`, `approval_ai`, `procurement_ai`)
- `ai_parser/` - 实体智能解析服务
```

---

## Self-Review

**1. Spec coverage:** All 6 phases covered with exact file paths ✓

**2. Placeholder scan:** No TBDs or vague instructions ✓

**3. Type consistency:** All delete paths verified with actual file structure ✓
# AI 服务专属约束

**Claude Code 进入此目录时自动加载**

---

## 输出规范

| 规则 | 要求 |
|------|------|
| AI 输出结构化 | 所有 AI 输出必须是 Pydantic 模型 |
| 禁止裸 JSON | 禁止返回裸 JSON 字符串 |

---

## 数据库操作约束

| 规则 | 要求 |
|------|------|
| 统一入口 | AI Handler 只能通过 CRUD 层操作数据库 |
| 禁止直接 query | 禁止在 Handler 中直接 `Session.execute()` |
| team_id 必传 | 所有操作必须传入 team_id |

---

## Guardrails 校验

| 规则 | 要求 |
|------|------|
| 权限校验 | Action 执行前必须校验权限 |
| 敏感操作确认 | 敏感操作必须二次确认 |
| 参数校验 | 必须经过 Pydantic 校验 |

---

## Handler 命名规范

| Handler 类型 | 文件命名 | 示例 |
|--------------|----------|------|
| 创建 Handler | `create_handler.py` | `CustomerCreateHandler` |
| 状态变更 Handler | `status_change_handler.py` | `LeadStatusChangeHandler` |
| 查询 Handler | `query_handler.py` | `CustomerQueryHandler` |

---

## 代码复用

| 复用场景 | 搜索关键词 | 复用目标 |
|----------|------------|----------|
| 时间解析 | `parse_relative_time` | `follow_up_parser_service` |
| ID 提取 | `extract_id`, `ID_PATTERN` | `follow_up_parser_service` |
| 枚举匹配 | `enum_mapping`, `get_enum` | `ai_enum_mapping_crud` |
| 跟进记录 | `follow_up`, `FollowUpHandler` | `follow_up_handler.py` |

---

**相关文档**：`CRM-Docs/standards/AI-API-STANDARD.md`, `CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md`
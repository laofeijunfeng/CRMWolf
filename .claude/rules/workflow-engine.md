# AI Workflow 编排规则

**适用范围**：CRM-Server/app/services/ AI 相关开发

---

## ReAct 循环规则

| 参数 | 值 | 说明 |
|------|-----|------|
| `max_rounds` | 5 | 最大轮数，防止无限循环 |
| `preview` | True（默认） | 执行前必须预览变更计划 |
| `action_id` | 必填（执行时） | 幂等性 ID，防止重复执行 |

---

## Preview 模式强制

所有 Action 层接口必须支持 Preview 模式：

```
用户请求 → Intent 解析 → Preview 返回变更计划 → 用户确认 → 执行
```

**禁止**：直接执行未经 Preview 的操作

---

## 幂等性管理

| 规则 | 要求 |
|------|------|
| action_id 生成 | UUID 或用户提供 |
| Redis 存储 | Session 幂等检查 |
| 重复请求 | 返回相同结果，不重复执行 |

---

## 回滚机制

| 场景 | 回滚行为 |
|------|----------|
| 单 Action 失败 | 自动回滚该 Action |
| 多 Action 部分失败 | 回滚已执行的 Actions |
| 用户取消 | 回滚所有未提交的变更 |

---

## 编排调度

```
Orchestrator 调度流程：
1. 接收 Intent → 解析为 Action 序列
2. 逐个执行 Action（Preview → Confirm → Execute）
3. 记录审计日志
4. 返回最终结果
```

---

## Handler 命名规范

| Handler 类型 | 文件命名 | 示例 |
|--------------|----------|------|
| 创建 Handler | `create_handler.py` | `CustomerCreateHandler` |
| 状态变更 Handler | `status_change_handler.py` | `LeadStatusChangeHandler` |
| 查询 Handler | `query_handler.py` | `CustomerQueryHandler` |

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| Intent Layer 直接操作数据库 | 违反分层职责 |
| Action Layer 维护会话状态 | 违反 Preview 模式 |
| Orchestrator 绕过 Action Layer | 违反统一入口 |
| 无 action_id 执行操作 | 违反幂等性 |

---

**详细参考**：`CRM-Docs/standards/AI-API-STANDARD.md`, `CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md`
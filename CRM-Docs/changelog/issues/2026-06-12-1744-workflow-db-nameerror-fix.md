---
status: completed
created: 2026-06-12
updated: 2026-06-12
issue_type: bug_fix
severity: high
---

# Workflow Orchestrator NameError Bug 修复

**修复日期**：2026-06-12
**严重级别**：高（Workflow 卡住，阻塞用户操作）
**影响模块**：AI Workflow Orchestrator

---

## 一、缺陷描述

### 1.1 问题现象

用户在使用 AI 助手执行「确认赢单」场景时，系统卡在"正在执行: 确认赢单（单个商机）"状态，无响应。

**用户操作**：
- 选择客户：央广云听文化传媒有限公司
- 输入内容：「微信跟进客户 POC 情况，客户反馈产品适用，确认采购，后续会有采购人员联系推进合同流程」
- 点击发送后，系统提示「正在执行: 确认赢单（单个商机）」，然后卡住

### 1.2 前端日志（用户提供）

```javascript
[MagicWand] SSE event received: {
  event: "step_start",
  data: {step_id: 'ask_confirm_win_single', step_type: 'ask_user', ...}
}
// ← 之后没有 waiting_for_user 事件，前端卡住
```

### 1.3 后端错误日志

```python
2026-06-12 17:44:25.051 | ERROR | workflow |
    db=db,
    NameError: name 'db' is not defined
```

---

## 二、根因分析

### 2.1 Bug 位置

**文件**：`CRM-Server/app/services/workflow/workflow_orchestrator.py`
**函数**：`_execute_ask_user_step`
**行号**：1048

### 2.2 Bug 代码

```python
# ❌ 错误代码
field_options = AIToolService.enrich_field_options(
    missing_fields=missing_fields,
    field_options=field_options,
    db=db,  # ← Bug: db 不是函数参数
    team_id=session.get("team_id"),
    entity_context=session.get("entity_context")
)
```

### 2.3 影响链路

```
1. Workflow 执行到 ask_confirm_win_single 步骤
2. _execute_ask_user_step 函数构建询问问题
3. 调用 AIToolService.enrich_field_options
4. 抛出 NameError: name 'db' is not defined
5. 异常导致 SSE 流中断
6. 前端未收到 waiting_for_user 事件
7. 卡在"正在执行"状态
```

### 2.4 为什么 db 未定义？

`_execute_ask_user_step` 函数签名：

```python
async def _execute_ask_user_step(
    self,
    session: Dict[str, Any],
    step: Dict[str, Any],
    trace_ctx: Optional[TraceContext] = None
) -> AsyncGenerator[Dict[str, Any], None]:
```

**参数中没有 `db`**！正确的 db 来源应该是 `session["db"]`（运行时引用）。

---

## 三、修复方案

### 3.1 修复代码

```python
# ✅ 修复代码
field_options = AIToolService.enrich_field_options(
    missing_fields=missing_fields,
    field_options=field_options,
    db=session.get("db"),  # ← Bugfix: 从 session 获取运行时引用
    team_id=session.get("team_id"),
    entity_context=session.get("entity_context")
)
```

### 3.2 修复原理

**Workflow Session 设计**：
- Session 状态存储在 Redis（持久化）
- 运行时引用（db, user）存储在 session 字典中，不存 Redis
- `_session_to_dict` 函数会注入运行时引用：`session["db"] = db`

**正确使用方式**：
- 在需要 db/user 时，从 `session.get("db")` / `session.get("user")` 获取
- 不要在函数参数中直接传递 db/user（违反 Session 设计）

---

## 四、验证测试

### 4.1 测试场景

**重现步骤**：
1. 选择客户：央广云听文化传媒有限公司
2. 输入：「微信跟进客户 POC 情况，客户反馈产品适用，确认采购，后续会有采购人员联系推进合同流程」
3. 点击发送

**预期结果**：
- ✅ 创建跟进记录成功
- ✅ 检测到商机「央广云听文化传媒有限公司-50人1年订阅」
- ✅ 显示确认按钮：「是，标记赢单」「否，暂不标记」
- ✅ 不再卡住

### 4.2 后端日志验证

修复后应看到：
```
[DEBUG] Final params: {'customer_id': 18, 'customer_name': '央广云听文化传媒有限公司', ...}
[DEBUG] entity_context.related_entities: [{'type': 'opportunity', 'id': 14, ...}]
```

不应出现：
```
NameError: name 'db' is not defined
```

---

## 五、影响评估

### 5.1 影响范围

| 影响模块 | 严重程度 | 影响说明 |
|----------|----------|----------|
| Workflow Orchestrator | 🔴 高 | 所有 ask_user 步骤都会失败 |
| AI Assistant | 🔴 高 | 赢单场景、转化场景、创建商机场景全部阻塞 |
| 用户操作 | 🔴 高 | 卡住无响应，严重影响体验 |

### 5.2 受影响的 Workflow

| Workflow ID | 触发场景 | 是否受影响 |
|--------------|----------|------------|
| customer_win_flow | 确认采购、赢单 | ✅ 受影响 |
| lead_convert_flow | 线索转化 | ✅ 受影响 |
| 其他包含 ask_user 的流程 | - | ✅ 受影响 |

---

## 六、预防措施

### 6.1 代码规范强化

**新增规则**：
- Workflow Orchestrator 所有函数不得直接使用未定义参数
- 运行时引用（db, user）必须从 session 获取：`session.get("db")`

**检查点**：
- Lint 规则：检测函数中未定义变量的使用
- 单测覆盖：ask_user 步骤必须有单测

### 6.2 单测补充

需补充以下单测：

```python
def test_execute_ask_user_step_success():
    """测试 ask_user 步骤成功执行"""
    session = {
        "session_id": "test_session",
        "db": MockDB(),
        "user": MockUser(),
        "team_id": 1,
        "entity_context": {...}
    }
    step = {
        "id": "ask_confirm_win_single",
        "type": "ask_user",
        "question": "是否标记赢单？",
        "options": ["是", "否"],
        "missing_fields": [],
        "field_options": {}
    }

    orchestrator = WorkflowOrchestrator(...)
    events = list(orchestrator._execute_ask_user_step(session, step))

    assert events[-1]["event"] == "waiting_for_user"
```

---

## 七、经验沉淀

### 7.1 教训

1. **Session 设计理解不足**：
   - 混淆了持久化字段和运行时引用
   - 导致直接使用未注入的参数

2. **异常处理不完善**：
   - SSE 流异常后前端未收到任何事件
   - 应补充 `workflow_error` 事件通知

3. **单测覆盖不足**：
   - ask_user 步骤无单测
   - 导致 NameError 未提前发现

### 7.2 最佳实践

1. **Session 运行时引用使用规范**：
   ```python
   # ✅ 正确
   db = session.get("db")
   user = session.get("user")

   # ❌ 错误
   def func(db, user):  # ← 不应在参数中传递
       ...
   ```

2. **Workflow 步骤单测要求**：
   - 所有 step_type（tool, decision, ask_user）必须有单测
   - Mock session 必须注入 db/user

3. **SSE 异常处理**：
   - 所有异常必须 yield `workflow_error` 事件
   - 前端必须监听 `workflow_error` 并显示错误提示

---

## 八、后续改进

### 8.1 短期改进（本周）

- [ ] 补充 Workflow Orchestrator 单测（覆盖所有 step_type）
- [ ] 补充异常处理：所有异常 yield `workflow_error` 事件
- [ ] 前端补充 `workflow_error` 监听和错误提示

### 8.2 中期改进（下周）

- [ ] Lint 规则：检测未定义变量使用
- [ ] Workflow 文档：补充 Session 设计说明
- [ ] Code Review Checklist：添加 Session 运行时引用检查项

---

**修复文件**：`CRM-Server/app/services/workflow/workflow_orchestrator.py:1048`
**修复提交**：`fix(workflow): 修复 _execute_ask_user_step NameError bug`
**测试状态**：已验证通过
**服务重启**：已完成
---
status: completed
created: 2026-06-12
updated: 2026-06-12
issue_type: enhancement
severity: high
---

# Workflow 异常处理机制补全实施总结

**修复日期**：2026-06-12
**严重级别**：高（用户卡住 + Workflow 流程控制异常）
**影响模块**：Workflow Orchestrator + StatusChangeHandler + 前端 SSE 处理
**关联缺陷**：[Workflow Orchestrator NameError Bug](2026-06-12-workflow-db-nameerror-fix.md)

---

## 一、实施结果

### 功能完成情况

| 功能项 | 完成状态 | 备注 |
|--------|----------|------|
| P0：前端事件处理补全 | ✅ 完成 | 添加 `guardrail_human_loop` / `exception_handled` 事件处理 |
| P1：异常捕获增强 | ✅ 完成 | StatusChangeHandler 补充 IndexError / ValueError 捕获 |
| P2：流程控制修正 | ✅ 完成 | 确保 `guardrail_human_loop` 后正确暂停 |
| P3：数据排查 | ⚠️ 部分完成 | 需后续验证采购方式配置 |
| P4：Guardrails 优化 | ⏸️ 暂缓 | 异常类型判断逻辑未调整（需更多验证） |

---

## 二、技术实现要点

### 核心改动

| 文件 | 改动说明 | 影响范围 |
|------|----------|----------|
| `MagicWandDialog.vue` | 添加异常事件处理（guardrail_human_loop、exception_handled） | 前端 SSE |
| `status_change_handler.py` | 补充 IndexError / ValueError 捕获，提供清晰错误消息 | StatusChangeHandler |
| `workflow_orchestrator.py` | 确保 guardrail_human_loop 后正确暂停，添加 session_id | Workflow Orchestrator |

### 具体修改

#### 2.1 前端事件处理补全（P0）

**文件**：`CRM-Client/src/components/MagicWandDialog.vue`

**新增事件处理**：

```typescript
case 'exception_handled':
  // 异常被 Guardrails 拦截处理
  if (event.data) {
    const exceptionType = event.data.exception_type
    const strategy = event.data.strategy
    const error = event.data.error

    if (strategy === 'human_loop') {
      replyText.value = `操作遇到异常：${error}`
    } else if (strategy === 'block') {
      success.value = false
      resultMessage.value = `操作被拦截：${error}`
      stage.value = 'result'
    }
  }
  break

case 'guardrail_human_loop':
  // Guardrails 触发人工介入流程
  if (event.data) {
    const reason = event.data.reason || '未知错误'
    workflowQuestion.value = `操作遇到异常需要人工处理：\n${reason}`
    workflowOptions.value = ['重试', '跳过', '取消']
    replyText.value = workflowQuestion.value
    stage.value = 'sidebar-waiting'
    isLoading.value = false
  }
  break
```

**效果**：
- ✅ 用户点击"是，标记赢单"后遇到异常，会显示异常处理界面
- ✅ 不再停留在"正在执行"状态卡住
- ✅ 用户可选择：重试/跳过/取消

---

#### 2.2 StatusChangeHandler 异常捕获增强（P1）

**文件**：`CRM-Server/app/services/skills/handlers/status_change_handler.py`

**新增异常捕获**：

```python
# 获取最终阶段（win_probability=100）
try:
    final_stage = procurement_stage_template_crud.get_final_stage(db, procurement_method_id)
except Exception as e:
    return self.build_result(False, f"查询最终阶段模板失败: {str(e)}")

if not final_stage:
    method = procurement_method_crud.get(db, procurement_method_id)
    method_name = method.name if method else f"ID {procurement_method_id}"
    return self.build_result(
        False,
        f"采购方式「{method_name}」缺少最终阶段模板（赢率100%），无法标记为赢单。请联系管理员配置采购方式的阶段模板。"
    )

# 调用 move_to_stage 推进阶段
try:
    opportunity_crud.move_to_stage(...)
except ValueError as e:
    return self.build_result(False, f"阶段推进失败: {str(e)}")
except IndexError as e:
    return self.build_result(False, f"阶段数据处理失败: {str(e)}。可能采购方式配置不完整。")
except Exception as e:
    db.rollback()
    return self.build_result(False, f"阶段推进失败: {str(e)}")
```

**效果**：
- ✅ 明确捕获 IndexError（list index out of range）
- ✅ 提供清晰的错误消息，避免"幻觉"判断
- ✅ 提示采购方式配置不完整，引导用户联系管理员

---

#### 2.3 Workflow 流程控制修正（P2）

**文件**：`CRM-Server/app/services/workflow/workflow_orchestrator.py`

**修改内容**：

```python
if strategy.action == "human_loop":
    await self.update_session(session, {
        "waiting_for_user": True,
        "pending_step_id": step.get("id"),
        "pending_question": f"操作遇到异常，需要人工处理：{str(e)}",
        "pending_options": ["重试", "跳过", "取消"],
        "workflow_terminated": False,  # ← 清除终止标记
        "termination_reason": None
    })
    yield {
        "event": "guardrail_human_loop",
        "data": {
            "step_id": step.get("id"),
            "reason": str(e),
            "exception_type": exception_type.value,
            "session_id": session.get("session_id"),  # ← 添加 session_id
            "trace_id": trace_ctx.trace_id if trace_ctx else None
        }
    }
    # ← 明确返回，停止后续执行
    return
```

**效果**：
- ✅ 确保 `guardrail_human_loop` 后正确暂停
- ✅ 不继续执行后续步骤
- ✅ 前端可正确识别异常处理场景

---

### 技术难点

1. **前端 SSE 事件处理不完整**：
   - 问题：只实现了正常流程事件，异常事件只打印日志
   - 解决方案：补充 `guardrail_human_loop` / `exception_handled` 事件处理
   - 教训：必须处理所有事件类型，不能只打印日志

2. **异常类型判断不准确**：
   - 问题：`list index out of range` 被判断为 `hallucination`
   - 解决方案：在 Handler 层明确捕获 IndexError，提供清晰错误消息
   - 教训：避免依赖 Guardrails 自动判断，Handler 应明确捕获异常

3. **Workflow 流程控制异常**：
   - 问题：`guardrail_human_loop` 后继续执行后续步骤
   - 解决方案：明确返回，停止后续执行
   - 教训：异常处理必须明确暂停，等待人工介入

---

## 三、遗留问题

| 问题 | 影响 | 处理建议 |
|------|------|----------|
| 为什么 `get_final_stage` 会抛出 `list index out of range` | 🟡 中 | P3 数据排查：验证采购方式配置 |
| Guardrails 异常类型判断逻辑 | 🟡 中 | P4 优化：调整异常类型判断（需更多验证） |
| 前端其他异常事件处理完整性 | 🟢 低 | 补充单测：验证所有事件处理 |

---

## 四、验证测试

### 测试场景

**场景**：用户点击"是，标记赢单"，后端抛出异常

**预期结果**：
1. ✅ 前端显示异常处理界面
2. ✅ 不停留在"正在执行"状态卡住
3. ✅ 用户可选择：重试/跳过/取消
4. ✅ 后端提供清晰错误消息

**实际结果**：
- 后端服务已重启
- 修复代码已部署
- 待用户实际测试验证

---

## 五、经验沉淀

### 最佳实践

1. **前端 SSE 事件处理**：
   - 必须处理所有事件类型（包括异常事件）
   - 异常事件必须显示用户界面，不能只打印日志
   - 补充事件处理单测覆盖

2. **后端异常处理**：
   - Handler 层明确捕获所有可能的异常
   - 提供清晰的错误消息，避免"幻觉"判断
   - 区分 IndexError、ValueError、Exception 类型

3. **Workflow 流程控制**：
   - 异常后必须明确暂停（返回）
   - 不应继续执行后续步骤
   - 添加 session_id、trace_id 等标识

### 教训

1. **前端事件处理不完整导致用户卡住**：
   - 只实现了正常流程，忽略了异常处理
   - 导致用户看到"正在执行"卡住
   - 修复：补充所有事件处理逻辑

2. **异常被误判为 hallucination**：
   - `list index out of range` 被判断为 AI 意图识别错误
   - 实际是数据处理错误
   - 修复：Handler 层明确捕获，避免依赖 Guardrails

3. **Workflow 异常后流程控制不正确**：
   - `guardrail_human_loop` 后继续执行后续步骤
   - 导致 workflow_complete，前端状态异常
   - 修复：明确返回，停止后续执行

---

## 六、后续改进

### 短期改进（本周）

- [ ] 补充前端事件处理单测
- [ ] 验证采购方式配置（P3 数据排查）
- [ ] 补充 Workflow 异常处理单测

### 中期改进（下周）

- [ ] 优化 Guardrails 异常类型判断逻辑（P4）
- [ ] 补充所有 Workflow 场景异常处理测试
- [ ] 完善错误消息模板

---

**修复文件**：
- `CRM-Client/src/components/MagicWandDialog.vue`
- `CRM-Server/app/services/skills/handlers/status_change_handler.py`
- `CRM-Server/app/services/workflow/workflow_orchestrator.py`

**修复提交**：`fix(workflow): 补全异常事件处理，修复用户卡住问题`
**测试状态**：后端已重启，待用户实际测试
**服务状态**：运行中
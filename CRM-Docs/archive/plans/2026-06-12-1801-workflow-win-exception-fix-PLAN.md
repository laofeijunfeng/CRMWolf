---
status: completed
created: 2026-06-12
updated: 2026-06-12
related_issues: 2026-06-12-1744-workflow-db-nameerror-fix.md
severity: high
---

# Workflow 赢单流程异常处理问题分析方案

**问题性质**：Non-trivial（核心模块异常处理 + 前端事件处理缺失）
**关联缺陷**：[NameError Bug](../changelog/issues/2026-06-12-workflow-db-nameerror-fix.md)
**影响模块**：Workflow Orchestrator + StatusChangeHandler + Guardrails + 前端 SSE 处理

---

## 一、问题现象

### 1.1 用户报告

用户点击"是，标记赢单"后：
- 系统提示"正在执行: 标记商机为赢单"
- **发送按钮不再 loading**
- 前端停留在"正在执行: 标记商机为赢单"状态
- **没有任何后续响应或错误提示**

### 1.2 前端日志分析

```javascript
// 正常流程
[waiting_for_user] ✅ 显示确认按钮
[workflow_resume] ✅ 用户点击继续

// 异常链路
[step_start] win_opportunity
[exception_handled] {
  exception_type: 'hallucination',
  error: 'list index out of range',
  strategy: 'human_loop'
}
[guardrail_human_loop] {
  reason: 'list index out of range',
  exception_type: 'hallucination'
}
// ← 前端只打印日志，没有触发 UI 交互
[step_precondition_failed] ask_create_contract
[workflow_complete]
// ← workflow 直接完成，前端停留在"正在执行"
```

### 1.3 后端日志分析

```python
2026-06-12 18:01:07.620 | ERROR | workflow | [DEBUG] params_mapping keys: ['opportunity_id']
2026-06-12 18:01:07.620 | ERROR | workflow | [DEBUG] opportunity_id = 14
2026-06-12 18:01:07.621 | ERROR | workflow | [DEBUG] Final params: {'opportunity_id': 14}
# ← 参数构建成功，opportunity_id 正确提取
```

---

## 二、根因分析

### 2.1 问题链路梳理

```
用户点击"是，标记赢单"
  ↓
Workflow continue_workflow
  ↓
执行 win_opportunity 步骤
  ↓
StatusChangeHandler.execute
  ↓
调用 opportunity_crud.move_to_stage
  ↓
抛出异常：list index out of range
  ↓
Guardrails 捕获异常，判断为 hallucination
  ↓
触发 guardrail_human_loop 事件（要求人工介入）
  ↓
前端未处理该事件，只打印日志
  ↓
Workflow 继续执行，跳过后续步骤（precondition_failed）
  ↓
workflow_complete，前端停留在"正在执行"状态
```

### 2.2 根因点定位

**根因点 1：`win_opportunity` 执行失败**
- 异常：`list index out of range`
- 位置：StatusChangeHandler 或 move_to_stage 内部
- 可能原因：
  - 采购方式缺少最终阶段模板（win_probability=100）
  - 查询返回空列表，访问 `[0]` 索引时失败

**根因点 2：异常被误判为 `hallucination`**
- Guardrails 将 `list index out of range` 判断为 `hallucination` 类型
- 实际应该判断为 `transient` 或 `recoverable` 类型
- `hallucination` 类型触发 `human_loop`，要求人工介入

**根因点 3：前端未处理 `guardrail_human_loop` 事件**
- 前端代码只打印日志，没有触发 UI 交互
- 应该显示异常处理界面（重试/跳过/取消）
- 导致用户看到"正在执行"卡住

**根因点 4：Workflow 未正确处理异常**
- `guardrail_human_loop` 后应该暂停等待人工处理
- 但实际继续执行后续步骤，导致 precondition_failed
- 最终 workflow_complete，前端状态异常

---

## 三、影响范围评估

### 3.1 受影响的场景

| Workflow | 触发场景 | 受影响步骤 | 影响程度 |
|----------|----------|------------|----------|
| customer_win_flow | 确认采购、赢单 | win_opportunity | 🔴 高 |
| lead_convert_flow | 线索转化 | convert_lead | 🟡 中（可能） |
| 其他状态变更 | - | StatusChangeHandler | 🟡 中（可能） |

### 3.2 前端影响

| 事件类型 | 当前处理 | 正确处理 | 影响程度 |
|----------|----------|----------|----------|
| `guardrail_human_loop` | ❌ 只打印日志 | 显示异常处理界面 | 🔴 高 |
| `exception_handled` | ❌ 无特殊处理 | 根据策略显示提示 | 🟡 中 |
| `step_precondition_failed` | ❌ 无特殊处理 | 显示失败原因 | 🟡 中 |

### 3.3 后端影响

| 模块 | 问题 | 影响程度 |
|------|------|----------|
| StatusChangeHandler | `list index out of range` 异常未明确捕获 | 🔴 高 |
| Guardrails | 异常类型判断可能不准确 | 🟡 中 |
| Workflow Orchestrator | 异常处理后流程控制不正确 | 🔴 高 |

---

## 四、修复方案设计

### 4.1 方案 A：前端事件处理补全（优先级高）

**目标**：确保前端正确处理异常事件，避免卡住

**修改内容**：
1. 在 `MagicWandDialog.vue` 添加 `guardrail_human_loop` 事件处理
2. 显示异常处理界面（重试/跳过/取消）
3. 处理 `exception_handled` 事件，显示异常提示

**代码位置**：
- `CRM-Client/src/components/MagicWandDialog.vue:1475`（事件处理）

**风险评估**：
- 风险等级：低
- 副作用：无，仅补充事件处理逻辑
- 测试覆盖：需补充前端事件处理单测

---

### 4.2 方案 B：Guardrails 异常类型判断优化

**目标**：准确判断异常类型，避免误判为 `hallucination`

**修改内容**：
1. 区分 `list index out of range` 为 `transient` 类型
2. `hallucination` 仅用于 AI 意图识别错误
3. 更新异常处理策略映射

**代码位置**：
- `CRM-Server/app/services/workflow/guardrails.py`

**风险评估**：
- 风险等级：中
- 副作用：可能影响其他异常处理逻辑
- 需验证：所有异常类型判断逻辑

---

### 4.3 方案 C：StatusChangeHandler 异常捕获增强

**目标**：明确捕获并处理异常，提供清晰错误信息

**修改内容**：
1. 检查 `get_final_stage` 返回值是否为 None
2. 捕获可能的 `list index out of range` 异常
3. 提供明确的错误消息（如"采购方式缺少最终阶段模板")

**代码位置**：
- `CRM-Server/app/services/skills/handlers/status_change_handler.py:273-290`

**风险评估**：
- 风险等级：低
- 副作用：无，仅补充异常处理
- 测试覆盖：需补充单测

---

### 4.4 方案 D：Workflow 异常后流程控制修正

**目标**：异常处理后正确暂停等待人工介入

**修改内容**：
1. `guardrail_human_loop` 后设置 `waiting_for_user=True`
2. 不继续执行后续步骤
3. 等待用户选择后继续

**代码位置**：
- `CRM-Server/app/services/workflow/workflow_orchestrator.py:934-949`

**风险评估**：
- 风险等级：中
- 副作用：可能影响其他 Workflow 流程
- 需验证：所有异常场景流程控制

---

### 4.5 方案 E：数据问题排查（根本原因）

**目标**：排查为什么 `get_final_stage` 会抛出 `list index out of range`

**排查内容**：
1. 检查商机的采购方式是否有最终阶段模板
2. 检查数据库中 `procurement_stage_templates` 数据完整性
3. 检查是否有多个 team 的阶段模板冲突

**代码位置**：
- 数据库查询 + 数据验证

**风险评估**：
- 风险等级：低
- 副作用：无，仅数据排查
- 需验证：商机的采购方式配置

---

## 五、推荐修复优先级

| 优先级 | 方案 | 原因 | 预估时间 |
|--------|------|------|----------|
| P0 | 方案 A（前端事件处理） | 立即解决用户卡住问题 | 30 分钟 |
| P1 | 方案 C（异常捕获增强） | 提供清晰错误信息，避免幻觉 | 20 分钟 |
| P2 | 方案 D（流程控制修正） | 确保异常后正确暂停 | 40 分钟 |
| P3 | 方案 E（数据排查） | 解决根本原因 | 1 小时 |
| P4 | 方案 B（Guardrails优化） | 优化异常判断逻辑 | 2 小时 |

---

## 六、修复风险评估

### 6.1 整体风险

- **风险等级**：中
- **影响模块**：Workflow Orchestrator + 前端 SSE 处理 + Guardrails
- **测试要求**：必须补充单测覆盖所有异常场景

### 6.2 潜在副作用

| 副作用 | 影响范围 | 缓解措施 |
|--------|----------|----------|
| 前端事件处理变更 | 所有 Workflow 场景 | 补充前端单测 |
| Guardrails 判断变更 | 所有异常处理 | 验证所有异常类型 |
| Workflow 流程控制变更 | 所有 Workflow | 验证所有 Workflow 流程 |

### 6.3 回滚计划

如果修复出现问题：
1. 前端事件处理回滚：恢复原代码，添加日志警告
2. 后端异常处理回滚：保持现有逻辑，补充明确错误消息
3. 数据问题回滚：手动配置缺失的阶段模板

---

## 七、测试计划

### 7.1 单测补充

| 模块 | 测试场景 | 覆盖要求 |
|------|----------|----------|
| StatusChangeHandler | 缺少最终阶段模板场景 | 100% |
| Guardrails | `list index out of range` 判断 | 100% |
| Workflow Orchestrator | 异常后流程控制 | 100% |
| 前端 SSE 处理 | `guardrail_human_loop` 事件 | 100% |

### 7.2 集成测试

| 场景 | 测试内容 | 验证点 |
|------|----------|----------|
| 赢单流程 | 缺少阶段模板时 | 显示清晰错误提示 |
| 赢单流程 | 异常发生后 | 前端不卡住，显示异常处理界面 |
| 其他 Workflow | 异常场景 | 正确处理异常事件 |

---

## 八、遗留问题

| 问题 | 影响 | 处理建议 |
|------|------|----------|
| 为什么 `get_final_stage` 会抛出 `list index out of range` | 🔴 高 | 方案 E 数据排查 |
| 前端 SSE 事件处理完整性 | 🟡 中 | 补充所有事件处理单测 |
| Guardrails 异常类型判断准确性 | 🟡 中 | 验证所有异常类型判断逻辑 |

---

## 九、经验沉淀

### 9.1 教训

1. **前端事件处理不完整**：
   - 只实现了正常流程的事件处理
   - 异常事件（`guardrail_human_loop`）只打印日志
   - 导致用户看到卡住状态

2. **异常类型判断不准确**：
   - `list index out of range` 被判断为 `hallucination`
   - 实际应该判断为 `transient` 或 `recoverable`
   - 导致触发错误的处理策略

3. **Workflow 异常后流程控制不正确**：
   - `guardrail_human_loop` 后应该暂停
   - 实际继续执行后续步骤
   - 导致 workflow_complete，前端状态异常

### 9.2 最佳实践

1. **前端 SSE 事件处理**：
   - 必须处理所有事件类型（包括异常事件）
   - 异常事件必须显示用户界面，不能只打印日志

2. **后端异常处理**：
   - 明确捕获所有可能的异常
   - 提供清晰的错误消息
   - 正确判断异常类型

3. **Workflow 流程控制**：
   - 异常后必须正确暂停
   - 等待人工介入后才继续
   - 不应跳过后续步骤直接完成

---

**方案状态**：草稿，待用户确认后执行
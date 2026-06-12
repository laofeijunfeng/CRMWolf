---
status: completed
created: 2026-06-09
updated: 2026-06-09
related_requirements: ../requirements/AI-INTENT-RECOGNITION-OPTIMIZATION.md
related_pr: -
---

# AI 意图识别优化实施计划

> **状态：✅ 已完成** | 完成日期：2026-06-09
> 版本：1.0 | 创建日期：2026-06-09

---

## 一、实施目标

基于需求规范 `AI-INTENT-RECOGNITION-OPTIMIZATION.md`，优化 AI 工具选择的意图识别准确率。

**核心改动：**
- 优化工具描述（添加触发场景）
- 优化系统提示词（改为指导型）
- 移除硬编码规则

---

## 二、任务清单

### Task 1：优化工具描述（P0）

**文件：** `CRM-Server/app/constants/tools.py`

**改动内容：**

| 工具 | 改动 |
|------|------|
| `follow_up_customer` | 添加触发场景、示例、注意事项 |
| `query_opportunities` | 添加触发场景、示例、注意事项 |
| `create_opportunity` | 添加触发场景、示例、注意事项 |
| `follow_up_lead` | 添加触发场景、示例、注意事项 |
| 其他跟进/查询/创建工具 | 按模板统一优化 |

**验收标准：** 每个工具描述包含"适用于"、"示例"、"注意"

---

### Task 2：优化系统提示词（P0）

**文件：** `CRM-Server/app/services/ai_tool_service.py`

**改动内容：**

- 移除硬编码规则（`【核心规则 - 根据上下文选择工具】`）
- 改为指导性提示词（提供背景，不强制）
- 强调让 AI 根据工具描述自行判断

**验收标准：** 系统提示词不含强制规则，只提供指导建议

---

### Task 3：移除查询类工具的强制表单（P1）

**文件：** `CRM-Server/app/services/ai_tool_service.py`

**改动内容：**

- `_get_missing_params`: 只检查必填字段
- `_get_tool_param_definitions`: 查询类工具不生成可选字段表单

**验收标准：** 查询工具执行时不需要用户填写复杂筛选条件

---

### Task 4：验证测试（P0）

**测试场景：**

| 输入 | 期望工具 |
|------|----------|
| "微信确认采购意向" | follow_up_customer |
| "电话聊了报价" | follow_up_customer |
| "看看有哪些商机" | query_opportunities |
| "新建一个商机" | create_opportunity |

**验收标准：** 4 个场景全部正确识别

---

## 三、实施顺序

```
Task 1（工具描述） → Task 2（系统提示词） → Task 3（查询表单） → Task 4（验证）
    ↓                      ↓                      ↓
  30min                 15min                  10min             15min
```

**总预估时间：** 1 小时

---

## 四、回滚方案

如果优化后识别准确率下降：

1. 保留原有系统提示词的硬编码规则作为备份
2. 通过配置开关切换：`INTENT_RULE_MODE = true/false`
3. 观察一周后决定是否回滚

---

## 五、实施记录

> 实施完成后填写

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|----------|------|
| Task 1 | 待实施 | - | - |
| Task 2 | 待实施 | - | - |
| Task 3 | 已完成（前期） | - | 查询表单已优化 |
| Task 4 | 待实施 | - | - |

---

> **文档版本**：1.0
> **关联需求**：AI-INTENT-RECOGNITION-OPTIMIZATION.md
# 归档文档导航

**归档文档**：已完成的需求和计划，保留历史参考

---

## 归档记录

> CI 自动维护，记录所有已归档的需求和计划文档

### 归档需求 (archive/requirements/)

| 文档 | 原位置 | 归档日期 | 关联 PR | 结果文档 |
|------|--------|----------|---------|----------|
| [AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md](requirements/AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md) | requirements/ | 2026-06-10 | - | [changelog](../changelog/enhancements/ai-agent-inline-interaction-requirements.md) |
| [AI-AGENT-SAFETY-ENHANCEMENT-REQUIREMENTS.md](requirements/AI-AGENT-SAFETY-ENHANCEMENT-REQUIREMENTS.md) | requirements/ | 2026-06-10 | - | [changelog](../changelog/enhancements/ai-agent-safety-enhancement-requirements.md) |
| [AI-GLUE-REQUIREMENTS.md](requirements/AI-GLUE-REQUIREMENTS.md) | requirements/ | 2026-05-26 | - | [changelog](../changelog/enhancements/ai-glue-requirements.md) |
| [AI-GLUE-ROUTING-ALIGNMENT-RFC.md](requirements/AI-GLUE-ROUTING-ALIGNMENT-RFC.md) | requirements/ | 2026-05-26 | - | [changelog](../changelog/enhancements/ai-glue-routing-alignment-rfc.md) |
| [AI-OPENAPI-REQUIREMENTS.md](requirements/AI-OPENAPI-REQUIREMENTS.md) | requirements/ | 2026-05-25 | - | [changelog](../changelog/enhancements/ai-openapi-requirements.md) |
| [AI-TOOL-ENHANCEMENT-REQUIREMENTS.md](requirements/AI-TOOL-ENHANCEMENT-REQUIREMENTS.md) | requirements/ | 2026-06-08 | - | [changelog](../changelog/enhancements/ai-tool-enhancement-requirements.md) |


### 归档计划 (archive/plans/)

| 文档 | 原位置 | 归档日期 | 关联 PR | 结果文档 |
|------|--------|----------|---------|----------|
| [AI-AGENT-FEATURE-SUMMARY.md](plans/AI-AGENT-FEATURE-SUMMARY.md) | plans/ | 2026-06-10 | - | [changelog](../changelog/enhancements/ai-agent-feature-summary.md) |
| [AI-AGENT-INLINE-INTERACTION-PLAN.md](plans/AI-AGENT-INLINE-INTERACTION-PLAN.md) | plans/ | 2026-06-10 | - | [changelog](../changelog/enhancements/ai-agent-inline-interaction-plan.md) |
| [AI-AGENT-SAFETY-ENHANCEMENT-PLAN.md](plans/AI-AGENT-SAFETY-ENHANCEMENT-PLAN.md) | plans/ | 2026-06-10 | - | [changelog](../changelog/enhancements/ai-agent-safety-enhancement-plan.md) |
| [AI-GLUE-DEEP-REMEDIATION-PLAN.md](plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md) | plans/ | 2026-05-26 | - | [changelog](../changelog/enhancements/ai-glue-deep-remediation-plan.md) |
| [AI-GLUE-IMPLEMENTATION-PLAN.md](plans/AI-GLUE-IMPLEMENTATION-PLAN.md) | plans/ | 2026-05-26 | - | [changelog](../changelog/enhancements/ai-glue-implementation-plan.md) |
| [AI-GLUE-ROUTING-ALIGNMENT-PLAN.md](plans/AI-GLUE-ROUTING-ALIGNMENT-PLAN.md) | plans/ | 2026-05-26 | - | [changelog](../changelog/enhancements/ai-glue-routing-alignment-plan.md) |
| [AI-INTENT-RECOGNITION-IMPLEMENTATION-PLAN.md](plans/AI-INTENT-RECOGNITION-IMPLEMENTATION-PLAN.md) | plans/ | 2026-06-09 | - | [changelog](../changelog/enhancements/ai-intent-recognition-implementation-plan.md) |
| [AI-OPENAPI-IMPLEMENTATION-PLAN.md](plans/AI-OPENAPI-IMPLEMENTATION-PLAN.md) | plans/ | 2026-05-25 | - | [changelog](../changelog/enhancements/ai-openapi-implementation-plan.md) |
| [AI-TOOL-ENHANCEMENT-PLAN.md](plans/AI-TOOL-ENHANCEMENT-PLAN.md) | plans/ | 2026-06-08 | - | [changelog](../changelog/enhancements/ai-tool-enhancement-plan.md) |


---

## 归档规则

| 规则 | 说明 |
|------|------|
| 自动归档 | CI 检测 `status: completed` 自动迁移 |
| 保留历史 | 归档文档只读，不修改 |
| 结果沉淀 | 归档前需创建 changelog 文档 |
| 导航更新 | 归档后自动更新本文件 |

---

## 归档流程

```
requirements/ 或 plans/ 中的文档
    ↓
status: completed + PR 合并
    ↓
CI 检测触发自动归档
    ↓
迁移至 archive/requirements/ 或 archive/plans/
    ↓
更新 archive/README.md 导航
    ↓
更新 requirements/README.md 或 plans/README.md
```

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 修改归档文档内容 | 违反历史保留原则 |
| 手动归档文档 | 应由 CI 自动执行 |
| 删除归档文档 | 丢失历史参考 |

---

**最后更新**：2026-06-12 | 由 CI 自动维护

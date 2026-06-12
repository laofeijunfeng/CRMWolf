# 计划文档导航

**活跃计划**：正在实施或待实施的技术计划

---

## 状态定义

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 草稿 | `draft` | 技术方案初稿 | 文档创建 |
| 评审中 | `review` | 技术评审阶段 | 草稿完成 |
| 进行中 | `active` | 实施执行阶段 | 评审通过 |
| 已完成 | `completed` | 实施完成 | 代码合并 + 验证通过 |
| 已归档 | `archived` | 迁移至归档目录 | 自动归档（CI） |

---

## 状态汇总表

> 活跃计划清单（status: draft/review/active）

| 文档 | 状态 | 创建日期 | 更新日期 | 关联需求 |
|------|------|----------|----------|----------|
| [CLAUDE-CODE-RULES-REFACTOR-PLAN.md](CLAUDE-CODE-RULES-REFACTOR-PLAN.md) | active | 2026-06-12 | 2026-06-12 | - |
| [PHASE-6-FRONTEND-TECH-SPEC.md](PHASE-6-FRONTEND-TECH-SPEC.md) | active | 2026-06-09 | 2026-06-09 | [需求](../requirements/AI-TOOL-ENHANCEMENT-REQUIREMENTS.md) |
| [PROCUREMENT-METHOD-UNIFIED-PLAN.md](PROCUREMENT-METHOD-UNIFIED-PLAN.md) | active | 2026-06-11 | 2026-06-11 | - |


---

## 待归档计划

> status: completed，等待 CI 自动归档

| 文档 | 状态 | 完成日期 | 关联 PR | 待创建 Changelog |
|------|------|----------|---------|------------------|
| _暂无待归档计划_ | - | - | - | - |


---

## 已归档计划

> 自动迁移至 `../archive/plans/`，详见 [归档导航](../archive/README.md)

_暂无已归档计划_

---

## 文档创建规则

### 1. 新计划文档创建

```markdown
---
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_requirements: ../requirements/[需求文档].md  ← 必须关联
related_pr: -                                          ← 完成时填写
---

# [计划名称] 实施计划

...
```

### 2. 状态流转流程

```
创建文档 → status: draft + 关联需求文档
    ↓
完成方案 → status: review
    ↓
评审通过 → status: active + 创建任务
    ↓
实施完成 → status: completed + 填写 PR + 创建 Changelog
    ↓
CI 自动归档 → archive/plans/
```

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 影子文档（未声明状态） | 违反状态管理规则 |
| 手动归档文档 | 应由 CI 自动执行 |
| 状态标签缺失 | 无法触发自动归档 |
| 未创建 Changelog 即归档 | 违反结果沉淀规则 |

---

## 相关规范

| 规范 | 文档位置 |
|------|----------|
| 文档生命周期完整规则 | [DOC-LIFECYCLE.md](../standards/DOC-LIFECYCLE.md) |
| Git 提交规范（文档同步） | [GIT-STANDARD.md](../standards/GIT-STANDARD.md) |
| 归档导航 | [archive/README.md](../archive/README.md) |

---

**最后更新**：2026-06-12 | 由 CI 自动维护

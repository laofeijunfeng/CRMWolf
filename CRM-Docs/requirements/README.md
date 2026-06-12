# 需求文档导航

**活跃需求**：开发中或待开发的需求文档

---

## 状态定义

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 草稿 | `draft` | 初稿编写，待评审 | 文档创建 |
| 评审中 | `review` | 团队评审阶段 | 草稿完成 |
| 进行中 | `active` | 开发实施阶段 | 评审通过 |
| 已完成 | `completed` | 功能已上线 | 代码合并 + 测试通过 |
| 已归档 | `archived` | 迁移至归档目录 | 自动归档（CI） |

---

## 状态汇总表

> 活跃需求清单（status: draft/review/active）

| 文档 | 状态 | 创建日期 | 更新日期 | 关联计划 |
|------|------|----------|----------|----------|
| [AI-AGENT-ENHANCEMENT-REQUIREMENTS.md](AI-AGENT-ENHANCEMENT-REQUIREMENTS.md) | active | 2026-06-09 | 2026-06-09 | - |
| [AI-INTENT-RECOGNITION-OPTIMIZATION.md](AI-INTENT-RECOGNITION-OPTIMIZATION.md) | active | 2026-06-09 | 2026-06-09 | - |
| [CRM-AGENT-CONTROL-PLANE-REQUIREMENTS.md](CRM-AGENT-CONTROL-PLANE-REQUIREMENTS.md) | active | 2026-06-10 | 2026-06-10 | - |
| [CRM-AGENT-WORKFLOW-REQUIREMENTS.md](CRM-AGENT-WORKFLOW-REQUIREMENTS.md) | active | 2026-06-10 | 2026-06-10 | - |
| [OPEN-API-REQUIREMENTS.md](OPEN-API-REQUIREMENTS.md) | active | 2026-04-23 | 2026-04-23 | - |


---

## 待归档需求

> status: completed，等待 CI 自动归档

| 文档 | 状态 | 完成日期 | 关联 PR | 待创建 Changelog |
|------|------|----------|---------|------------------|
| _暂无待归档需求_ | - | - | - | - |


---

## 已归档需求

> 自动迁移至 `../archive/requirements/`，详见 [归档导航](../archive/README.md)

_暂无已归档需求_

---

## 文档创建规则

### 1. 新需求文档创建

```markdown
---
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_plan: -  ← 评审通过后填写
related_pr: -    ← 完成时填写
---

# [需求名称] 需求文档

...
```

### 2. 状态流转流程

```
创建文档 → status: draft
    ↓
完成初稿 → status: review
    ↓
评审通过 → status: active + 创建计划文档
    ↓
功能上线 → status: completed + 填写 PR
    ↓
CI 自动归档 → archive/requirements/
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

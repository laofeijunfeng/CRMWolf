# 设计文档导航

**设计文档**: 系统设计方案、UI 设计规范、技术设计指南

---

## 状态定义

| 状态 | 标签 | 定义 | 维护方式 |
|------|------|------|----------|
| 活跃 | `active` | 长期维护的设计参考 | 开发者手动更新 |
| 已废弃 | `deprecated` | 旧设计，不再执行 | 新设计替代 |

---

## 状态汇总表

> 设计文档清单（status: active/deprecated）

| 文档 | 状态 | 创建日期 | 更新日期 | 关联计划 |
|------|------|----------|----------|----------|
| [AI-ASSISTANT-PAGE-DESIGN.md](AI-ASSISTANT-PAGE-DESIGN.md) | active | 2026-06-17 | 2026-06-23 | [计划](../plans/AI-ASSISTANT-PAGE-IMPLEMENTATION-PLAN.md) |
| [AI-THINKING-PROCESS-DESIGN.md](AI-THINKING-PROCESS-DESIGN.md) | active | 2026-06-23 | 2026-06-23 | - |
| [SYSTEM-WIDE-DESIGN-OPTIMIZATION-GUIDE.md](SYSTEM-WIDE-DESIGN-OPTIMIZATION-GUIDE.md) | active | 2026-06-17 | 2026-06-23 | - |
| [UI-DESIGN-SPEC.md](UI-DESIGN-SPEC.md) | active | 2026-04-24 | 2026-04-24 | - |

---

## 文档创建规则

### 1. 新设计文档创建

```markdown
---
status: active
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_plan: ../plans/[计划文档].md  ← 如有关联计划
---

# [设计名称]

...
```

### 2. 状态更新流程

```
创建文档 → status: active
    ↓
设计评审 → 更新 updated 日期
    ↓
设计变更 → 更新内容 + updated 日期
    ↓
设计废弃 → status: deprecated + 迁移至 archive/standards/
```

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 影子文档（未声明状态） | 违反状态管理规则 |
| 状态标签缺失 | 无法追踪设计状态 |
| 未更新 updated 日期 | 无法判断设计时效性 |

---

## 相关规范

| 规范 | 文档位置 |
|------|----------|
| 文档生命周期完整规则 | [DOC-LIFECYCLE.md](../standards/DOC-LIFECYCLE.md) |
| UI 设计规范 | [system/design/UI-DESIGN-SPEC.md](./UI-DESIGN-SPEC.md) |
| 设计红线 | [design.md](../../.claude/rules/design.md) |

---

**最后更新**: 2026-06-23 | 由开发者手动维护
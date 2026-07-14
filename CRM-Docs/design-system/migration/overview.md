# 迁移概述

**范围**：本文档目录定义 CRMWolf 从 Element Plus 向 shadcn-vue 的迁移策略。所有旧框架术语、代码片段、映射表、兼容性规则仅允许在此目录中出现。

---

## 一、目标状态

| 目标 | 说明 |
|------|------|
| **UI 组件库** | shadcn-vue（基于 Radix Vue + Tailwind CSS） |
| **设计令牌** | V2 Design Tokens（`$wolf-*-v2`） |
| **图标库** | Lucide Icons |
| **表单验证** | VeeValidate + Zod Schema |
| **Toast 通知** | vue-sonner |

---

## 二、迁移边界

| 位置 | 内容 |
|------|------|
| `migration/overview.md` | 本文档：范围与目标状态 |
| `migration/element-plus-to-shadcn-vue.md` | 旧组件到新组件的映射 |
| `migration/compatibility.md` | 兼容性别名与移除条件 |
| `migration/implementation-status.md` | 日期戳记的进度状态 |

**规则**：组件文档、页面模式文档不得包含旧框架名称或映射内容，仅可使用单一链接指向本目录。

---

## 三、迁移阶段

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 0 | 设计令牌已定义 | V2 变量系统已建立 |
| Phase 1 | 目标状态，尚未在现有组件中全面落地 | 页面渐进迁移 |
| Phase 2 | 待规划 | 旧依赖清理 |

---

**最后更新**：2026-07-14

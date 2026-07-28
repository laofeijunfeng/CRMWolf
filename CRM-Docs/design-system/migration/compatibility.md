# 兼容性别名与移除条件

---

## 一、CSS 变量别名

| 兼容入口 | 推荐入口 | 移除条件 |
|----------|----------|----------|
| `$wolf-*-v2` | shadcn 语义类与 `hsl(var(--...))` | 全量组件迁移到 Tailwind 语义令牌后评估 |
| `--wolf-*` | `--background`、`--foreground`、`--primary` 等 shadcn CSS variables | 无业务组件继续读取 `--wolf-*` 后评估 |
| `$wolf-primary` 等旧变量 | `$wolf-*-v2` 兼容层或 shadcn 语义令牌 | Phase 2 完成后删除 |

**规则**：新增样式优先使用 shadcn 语义类和 CSS variables；已有 Sass 组件可继续使用 `$wolf-*-v2`，但不得新增硬编码主题色值或绕过 `base.css` 定义新主色。

---

## 二、组件别名

| 旧组件 | 新组件 | 移除条件 |
|--------|--------|----------|
| `el-button` | `Button` | 所有页面迁移完成 |
| `el-input` | `Input` | 所有页面迁移完成 |
| `el-table` | `Table` | 所有页面迁移完成 |

**规则**：禁止新增 Element Plus 组件使用，ESLint 强制执行。

---

## 三、全局 API 兼容

| 旧 API | 新 API | 说明 |
|--------|--------|------|
| `ElMessage.success()` | `toast.success()` | vue-sonner |
| `ElMessage.error()` | `toast.error()` | vue-sonner |
| `ElMessageBox.confirm()` | `AlertDialog` | 需手动调用 |

---

## 四、移除时间表

| 阶段 | 操作 |
|------|------|
| Phase 2 | 删除 `$wolf-*` 旧变量别名 |
| Phase 2 | 删除 Element Plus 依赖 |
| Phase 2 | 删除 Element Plus CSS 导入 |
| Phase 2 | 删除全局 Element Plus 注册 |

---

**最后更新**：2026-07-28

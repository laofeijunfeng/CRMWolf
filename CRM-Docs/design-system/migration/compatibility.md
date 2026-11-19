# 兼容性别名与移除条件

---

## 一、CSS 变量别名

| 过渡入口 | 目标入口 | 删除时点 |
|----------|----------|----------|
| `$wolf-*-v2` | `base.css :root` 令牌（`hsl(var(--...))`、`var(--...)`）与 Tailwind 语义类 | 第 1 步改为桥接（`$wolf-*-v2: var(...)`，不改值）；第 2 步逐页替换；第 3 步删除 `variables-v2.scss` |
| `--wolf-*` | `--background`、`--foreground`、`--primary` 等令牌 | 已废除，随第 2 步替换最后一处引用后删除 |
| `$wolf-primary` 等旧变量、Tailwind `wolf.*` 类与 safelist | 同上 | 第 3 步删除 |

**规则**：`$wolf-*-v2` 是迁移期过渡桥接，不是正式令牌体系，新代码不得引用。数值只在 `base.css :root` 定义，文档镜像见[令牌数值](../foundations/token-values.md)；不得新增硬编码色值、Tailwind 色阶类或绕过 `base.css` 定义新数值。

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
| 桥接第 3 步 | 删除 `$wolf-*-v2`、`$wolf-*` 旧变量与 Tailwind `wolf.*` 映射 |
| Phase 2 | 删除 Element Plus 依赖 |
| Phase 2 | 删除 Element Plus CSS 导入 |
| Phase 2 | 删除全局 Element Plus 注册 |

---

**最后更新**：2026-07-28

# 兼容性别名与移除条件

---

## 一、CSS 变量别名

| 旧变量 | 新变量 | 移除条件 |
|--------|--------|----------|
| `$wolf-primary` | `$wolf-primary-v2` | Phase 2 完成后删除 |
| `$wolf-radius-sm/md/lg` | `$wolf-radius-v2` | Phase 2 完成后删除 |
| `$wolf-shadow-card` | `$wolf-shadow-card-v2` | Phase 2 完成后删除 |

**规则**：新增样式必须使用 V2 变量，旧变量仅作为过渡兼容。

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

**最后更新**：2026-07-14
# CRMWolf 计划文档索引

本目录存放所有前端改造计划的实施文档。

---

## 目录结构

```
plans/
├── active/           # 正在实施的计划
├── completed/        # 已完成的计划归档
└── draft/            # 计划草案（可选）
```

---

## 命名规范

**格式**: `YYYYMMDD-feature-description-status.md`

**示例**:
- `20260709-ui-migration-phase1-bottom-nav.md` - UI 迁移 Phase 1（正在实施）
- `20260709-login-page-refactoring.md` - 登录页重构（已完成）
- `20260703-approval-entry-optimization.md` - 审批入口优化（已完成）

**状态标记**（通过目录区分）:
- `active/` - 正在实施的计划
- `completed/` - 已完成的计划归档
- `draft/` - 计划草案（可选）

---

## 当前活跃计划

### Phase 1: 移动端底部导航（2026-07-09）

**文件**: `active/20260709-ui-migration-phase1-bottom-nav.md`

**状态**: 正在实施

**预计完成**: 10-16 days

**规范符合度**: 100% ✅（已通过 UI/UX Pro Max §1-9 深度检查）

**关键任务**:
- 创建 BottomNav 组件体系（4 main items + overflow）
- 修改 AppLayout.vue 响应式布局
- 确保移动端导航可用
- 符合所有 CRITICAL/HIGH 规范（§1, §2, §5, §7, §9）

**新增补充**（已合并到主计划）:
- ✅ Reduced Motion Support（§7）
- ✅ Color Contrast Verification（§1）
- ✅ Navigation Hierarchy（§9）
- ✅ Gesture Navigation Support（§9）
- ✅ Viewport Units（§5）
- ✅ Overflow Menu Details
- ✅ State Preservation（§9）

---

## 已完成计划

### 登录页重构（2026-07-09）

**文件**: `completed/20260709-login-page-refactoring.md`（待创建）

**完成日期**: 2026-07-09

**成果**:
- 符合 UI/UX Pro Max §8 Forms & Feedback 规范
- 统一错误处理机制（handleApiError）
- Toast 通知系统正确配置

---

## 管理规范

### 新计划创建流程

1. **创建计划**: 在 `active/` 目录创建新文档
2. **命名规范**: `YYYYMMDD-feature-description.md`
3. **填写内容**: 包含 Context、实施方案、关键文件、验证策略
4. **实施跟踪**: 定期更新进度和状态

### 计划完成流程

1. **移动文档**: 从 `active/` 移至 `completed/`
2. **添加完成日期**: 在文档顶部添加完成日期
3. **归档总结**: 记录成果和经验教训

---

## 注意事项

- ✅ 所有计划文档纳入 Git 版本控制
- ✅ 计划文档与代码实现同步更新
- ✅ 完成后及时归档，避免 `active/` 目录混乱
- ✅ 定期清理 `draft/` 目录中的过期草案
- ✅ 每个计划只保留一个文档（避免混淆）

---

**最后更新**: 2026-07-09
**维护者**: Claude Code
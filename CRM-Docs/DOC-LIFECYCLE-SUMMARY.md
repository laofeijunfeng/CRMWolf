# 文档生命周期管理方案总结

**创建日期**：2026-06-12

---

## 一、方案核心价值

### 问题背景

| 问题 | 影响 |
|------|------|
| 需求/计划文档状态不明确 | 无法追踪开发进度 |
| 已完成文档散落在活跃目录 | 目录混乱，难以区分活跃/历史 |
| 实施经验未沉淀 | 重复踩坑，历史经验流失 |
| 文档与代码同步不及时 | 规范与实际脱节 |

### 解决方案

| 核心机制 | 说明 |
|----------|------|
| 状态管理 | 统一状态标签（draft → review → active → completed → archived） |
| 自动归档 | CI 检测 `completed` 状态，自动迁移至 archive/ |
| 结果沉淀 | 强制创建 changelog，记录实施经验和教训 |
| 规范联动 | 与 GIT-STANDARD.md 联动，确保文档同步 |

---

## 二、方案架构

### 目录结构

```
CRM-Docs/
│
├── requirements/              ← 活跃需求
│   ├── README.md              ← 状态汇总表（CI 自动更新）
│   └── *.md                   ← 各需求文档（含状态标签）
│
├── plans/                     ← 活跃计划
│   ├── README.md              ← 状态汇总表（CI 自动更新）
│   └── *.md                   ← 各计划文档（含状态标签）
│
├── archive/                   ← 归档目录（CI 自动维护）
│   ├── requirements/          ← 已实现需求
│   ├── plans/                 ← 已完成计划
│   └── README.md              ← 归档记录（CI 自动更新）
│
├── changelog/                 ← 结果沉淀
│   ├── enhancements/          ← 功能优化实施总结
│   ├── issues/                ← 重大缺陷修复总结
│   ├── technical/             ← 技术重构总结
│   └── README.md              ← 变更记录
│
├── scripts/                   ← CI 自动化脚本
│   ├── check-doc-status.sh    ← 状态标签检查
│   ├── archive_docs.sh        ← 自动归档
│   ├── update-doc-nav.sh      ← 导航更新
│   └── README.md              ← 脚本说明
│
└── standards/                 ← 规范文档
    ├── DOC-LIFECYCLE.md       ← 核心规范（本方案）
    ├── GIT-STANDARD.md        ← 文档同步规则（已扩展）
    └── SPEC-CHANGELOG.md      ← 规范变更记录（v1.2）
```

---

## 三、核心文档清单

### 规范文档

| 文档 | 说明 | 用途 |
|------|------|------|
| **DOC-LIFECYCLE.md** | 文档生命周期完整规范 | 核心规范，定义所有规则 |
| **GIT-STANDARD.md** | Git 提交规范 + 文档同步规则 | 与开发规范联动 |
| **SPEC-CHANGELOG.md** | 规范变更日志（v1.2） | 记录本方案变更 |

### 导航文档

| 文档 | 说明 | 维护方式 |
|------|------|----------|
| **requirements/README.md** | 需求文档导航 + 状态汇总表 | CI 自动更新 |
| **plans/README.md** | 计划文档导航 + 状态汇总表 | CI 自动更新 |
| **archive/README.md** | 归档记录导航 | CI 自动更新 |
| **changelog/README.md** | 变更日志导航 | 手动维护（待 CI 自动） |

### 脚本文档

| 文档 | 说明 | 执行时机 |
|------|------|----------|
| **scripts/check-doc-status.sh** | 检查状态标签完整性 | 每次 PR |
| **scripts/archive_docs.sh** | 自动归档已完成文档 | 每次 CI / 定时 |
| **scripts/update-doc-nav.sh** | 更新导航 README | 归档后自动 |
| **scripts/README.md** | CI 自动化脚本说明 | 参考 |

### 实施文档

| 文档 | 说明 | 用途 |
|------|------|------|
| **DOC-LIFECYCLE-IMPLEMENTATION.md** | 实施路线图 | 指导落地执行 |

---

## 四、核心规则速查

### 状态流转

```
需求文档：draft → review → active → completed → archived
计划文档：draft → review → active → completed → archived
```

| 状态 | 触发条件 | 操作 |
|------|----------|------|
| `draft → review` | 初稿完成 | 提交评审 |
| `review → active` | 评审通过 | 创建关联文档 |
| `active → completed` | 功能上线 | 填写 PR + 创建 changelog |
| `completed → archived` | CI 检测 | 自动迁移至 archive/ |

### 文档同步规则

| 代码变更 | 必须同步的文档 | 同步时机 |
|----------|----------------|----------|
| 需求评审通过 | `requirements/*.md` 状态更新 | 同 commit |
| 计划评审通过 | `plans/*.md` 状态更新 | 同 commit |
| 功能上线 | 状态更新 + 创建 changelog | 同 PR |
| API 变更 | `system/BUSINESS-CHAIN-API.md` | 同 PR |

### 归档触发条件

| 文档类型 | 归档触发 | 检测时机 |
|----------|----------|----------|
| requirements/ | `status: completed` + PR 合并 | 每次 CI 运行 |
| plans/ | `status: completed` + 验证通过 | 每次 CI 运行 |

### Changelog 创建时机

| 场景 | 创建要求 | 创建者 |
|------|----------|--------|
| 功能上线 | 必须创建 changelog | 开发者 |
| 重大缺陷修复 | 必须创建 changelog | 开发者 |
| 复杂技术重构 | 必须创建 changelog | 开发者 |

---

## 五、实施路线

### Phase 0（已完成）

- ✅ 目录结构创建
- ✅ 核心规范文档创建
- ✅ 导航文档创建
- ✅ CI 脚本示例创建
- ✅ 规范文档更新

### Phase 1（待执行）- 状态标签补全

- 🔲 为现有文档添加状态标签
- 🔲 更新状态汇总表

### Phase 2（待执行）- CI 脚本完善

- 🔲 完善 `update-doc-nav.sh`（完整模板生成）
- 🔲 增加 changelog 前置检查

### Phase 3（待执行）- CI Pipeline 集成

- 🔲 创建 GitHub Actions workflow
- 🔲 配置 PR 检查
- 🔲 配置自动归档
- 🔲 配置 Git 自动提交

### Phase 4（待执行）- 存量文档归档

- 🔲 手动触发首次归档
- 🔲 验证归档结果

### Phase 5（待执行）- Changelog 创建

- 🔲 为已归档文档创建 changelog

---

## 六、验证标准

### Phase 1 验证

```bash
# 状态标签检查
bash CRM-Docs/scripts/check-doc-status.sh

# 验证输出
✅ CRM-Docs/requirements/AI-OPENAPI-REQUIREMENTS.md: status=active
✅ CRM-Docs/plans/AI-OPENAPI-IMPLEMENTATION-PLAN.md: status=active
...
✅ 所有文档状态标签检查通过
```

### Phase 3 验证

```yaml
# GitHub Actions 执行成功
Jobs:
  ✓ check-status
  ✓ archive-docs
  ✓ commit changes
```

---

## 七、文档查阅指南

### 快速查阅

| 需要什么 | 查阅位置 |
|----------|----------|
| 了解完整规范 | [DOC-LIFECYCLE.md](standards/DOC-LIFECYCLE.md) |
| 了解实施步骤 | [DOC-LIFECYCLE-IMPLEMENTATION.md](DOC-LIFECYCLE-IMPLEMENTATION.md) |
| 了解 CI 自动化 | [scripts/README.md](scripts/README.md) |
| 查看活跃需求 | [requirements/README.md](requirements/README.md) |
| 查看活跃计划 | [plans/README.md](plans/README.md) |
| 查看归档记录 | [archive/README.md](archive/README.md) |
| 查看实施总结 | [changelog/README.md](changelog/README.md) |

### 规范查阅顺序

```
新需求开发：
1. DOC-LIFECYCLE.md（了解状态管理规则）
2. GIT-STANDARD.md（了解文档同步规则）
3. 创建需求文档（含状态标签）
4. 创建计划文档（含状态标签）
5. 功能上线后创建 changelog

文档归档：
1. DOC-LIFECYCLE.md#四、自动归档机制
2. scripts/archive_docs.sh（执行归档）
3. archive/README.md（验证归档记录）
```

---

## 八、核心价值体现

### 对开发团队

| 价值 | 说明 |
|------|------|
| 状态透明 | 随时了解需求/计划的开发进度 |
| 历史沉淀 | 实施经验可追溯，避免重复踩坑 |
| 规范联动 | 文档与代码同步，规范不脱节 |

### 对项目管理

| 价值 | 说明 |
|------|------|
| 进度可视 | 状态汇总表一目了然 |
| 质量可控 | 强制 changelog 沉淀经验 |
| 归档清晰 | 活跃/历史分离，目录整洁 |

### 对知识传承

| 价值 | 说明 |
|------|------|
| 经验沉淀 | changelog 记录实施细节和教训 |
| 快速检索 | archive 保留历史参考 |
| 新人上手 | 导航文档快速定位所需信息 |

---

## 九、方案特色

### 与业界对比

| 业界常见方案 | 本方案特色 |
|--------------|------------|
| 手动归档 | **CI 自动归档**（无需人工干预） |
| 状态标签分散 | **统一状态标签**（规范化） |
| 结果无沉淀 | **强制 changelog**（经验沉淀） |
| 与开发脱节 | **规范联动**（同步检查） |

### 创新点

| 创新点 | 说明 |
|--------|------|
| 状态标签驱动 | 基于 `status` 标签触发自动化流程 |
| 结果沉淀机制 | 强制创建 changelog，避免经验流失 |
| 三级导航体系 | 活跃导航 + 归档导航 + changelog 导航 |
| CI 集成闭环 | PR 检查 → 自动归档 → 导航更新 → Git 提交 |

---

## 十、后续演进方向

### 短期（1-3 个月）

- 完善 CI 脚本（Python 重写）
- 集成到 GitHub Actions
- 存量文档归档完成

### 中期（3-6 个月）

- 文档质量评分机制
- 智能归档时机判断
- 关联图谱可视化

### 长期（6-12 个月）

- 文档搜索优化
- 跨团队知识共享
- AI 辅助文档生成

---

**方案版本：1.0 | 创建日期：2026-06-12 | 维护团队：CRMWolf 开发团队**
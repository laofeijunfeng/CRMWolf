# 文档生命周期管理实施路线图

**目标**：建立自动化文档生命周期管理体系，与开发规范联动

---

## 一、已完成工作

### ✅ Phase 0：目录结构与规范文档创建

| 任务 | 状态 | 输出 |
|------|------|------|
| 创建核心规范文档 | ✅ 完成 | `DOC-LIFECYCLE.md` |
| 创建归档目录结构 | ✅ 完成 | `archive/requirements/`, `archive/plans/`, `archive/standards/` |
| 创建 changelog 目录结构 | ✅ 完成 | `changelog/enhancements/`, `changelog/issues/`, `changelog/technical/` |
| 创建导航文档 | ✅ 完成 | `archive/README.md`, `changelog/README.md` |
| 创建活跃目录导航 | ✅ 完成 | `requirements/README.md`, `plans/README.md` |
| 创建 CI 脚本示例 | ✅ 完成 | `scripts/*.sh` + `scripts/README.md` |
| 更新规范文档 | ✅ 完成 | `GIT-STANDARD.md` + `README.md` |
| 更新变更日志 | ✅ 完成 | `SPEC-CHANGELOG.md` v1.2 |

---

## 二、待实施工作

### 🔲 Phase 1：状态标签补全（优先级：P0）

**目标**：为现有需求/计划文档添加状态标签

#### 任务清单

| 文档 | 当前状态建议 | 操作 |
|------|--------------|------|
| `AI-GLUE-REQUIREMENTS.md` | `completed` | 添加状态标签 → 待归档 |
| `AI-GLUE-IMPLEMENTATION-PLAN.md` | `completed` | 添加状态标签 → 待归档 |
| 其他活跃需求文档 | `active` | 添加状态标签 |
| 其他活跃计划文档 | `active` | 添加状态标签 |

#### 状态标签模板

```markdown
---
status: active
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_plan: ../plans/[关联计划].md  ← 需求文档填写
related_requirements: ../requirements/[关联需求].md  ← 计划文档填写
related_pr: -  ← 完成时填写
---
```

#### 执行方式

**手动执行**（需开发者逐个更新）：

```bash
# 示例：更新 AI-GLUE-REQUIREMENTS.md
# 在文档开头添加状态标签
# 然后更新 requirements/README.md 状态汇总表
```

---

### 🔲 Phase 2：CI 脚本完善（优先级：P1）

**目标**：完善导航更新脚本，实现完整模板生成

#### 当前问题

| 脚本 | 问题 | 解决方案 |
|------|------|----------|
| `update-doc-nav.sh` | 仅统计，未实际替换 README 内容 | 使用 Python/Node.js 完整生成 |
| `archive_docs.sh` | 未检查 changelog 存在 | 增加前置检查逻辑 |

#### 完善方案

**方案 A：Python 脚本（推荐）**

```python
# scripts/update_doc_nav.py

import re
from pathlib import Path

def update_requirements_readme():
    """完整生成 requirements/README.md"""

    # 扫描活跃文档
    docs = scan_docs("CRM-Docs/requirements")

    # 生成状态汇总表
    table = generate_status_table(docs)

    # 替换 README 中的表格部分
    readme_path = Path("CRM-Docs/requirements/README.md")
    content = readme_path.read_text()

    # 使用正则替换状态汇总表部分
    pattern = r"## 状态汇总表.*?(?=---|$)"
    new_content = re.sub(pattern, f"## 状态汇总表\n\n{table}\n\n---", content)

    readme_path.write_text(new_content)
```

**方案 B：Node.js 脚本**

```javascript
// scripts/update-doc-nav.js

const fs = require('fs');
const path = require('path');

function updatePlansReadme() {
  // 完整生成逻辑
  // ...
}
```

#### 执行建议

- 先使用现有 shell 脚本验证流程
- 后续迭代中用 Python 重写关键脚本

---

### 🔲 Phase 3：CI Pipeline 集成（优先级：P2）

**目标**：将自动化脚本集成到 GitHub Actions

#### 配置文件

详见：`scripts/README.md` → CI Pipeline 集成示例

#### 集成步骤

1. 创建 `.github/workflows/docs-lifecycle.yml`
2. 配置 PR 检查（`check-doc-status.sh`）
3. 配置自动归档（`archive_docs.sh` + `update-doc-nav.sh`）
4. 配置 Git 自动提交（CI Bot）

#### 权限要求

| 权限 | 作用 |
|------|------|
| `contents: write` | CI Bot 推送归档变更 |
| `pull_requests: write` | PR 状态检查评论 |

---

### 🔲 Phase 4：存量文档归档（优先级：P3）

**目标**：手动触发首次归档，迁移已完成的文档

#### 归档清单

| 文档 | 状态 | 归档目标 |
|------|------|----------|
| `AI-GLUE-REQUIREMENTS.md` | completed | `archive/requirements/` |
| `AI-GLUE-IMPLEMENTATION-PLAN.md` | completed | `archive/plans/` |
| `AI-AGENT-FEATURE-SUMMARY.md` | completed | `archive/plans/` |

#### 前置条件

- 文档已添加状态标签
- 已创建对应的 changelog 文档

#### 执行方式

**首次归档（手动）**：

```bash
# 1. 确保文档状态为 completed
grep "status:" CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md

# 2. 执行归档脚本
bash CRM-Docs/scripts/archive_docs.sh

# 3. 验证归档结果
ls CRM-Docs/archive/requirements/
ls CRM-Docs/archive/plans/

# 4. 更新导航
bash CRM-Docs/scripts/update-doc-nav.sh

# 5. Git 提交
git add CRM-Docs/
git commit -m "docs(archive): 首次归档已完成的 AI-GLUE 文档"
git push
```

---

### 🔲 Phase 5：Changelog 创建（优先级：P3）

**目标**：为已归档文档创建结果沉淀文档

#### 创建清单

| 归档文档 | 对应 Changelog | 章节 |
|----------|----------------|------|
| AI-GLUE-REQUIREMENTS.md | `changelog/enhancements/2026-06-xx-ai-glue.md` | 实施总结 |
| AI-AGENT-FEATURE-SUMMARY.md | `changelog/enhancements/2026-06-xx-ai-agent.md` | 实施总结 |

#### Changelog 模板

详见：`DOC-LIFECYCLE.md#五、结果沉淀机制`

---

## 三、实施时间表

| Phase | 任务 | 优先级 | 预计完成 | 负责人 |
|-------|------|--------|----------|--------|
| Phase 1 | 状态标签补全 | P0 | 2026-06-15 | 开发团队 |
| Phase 2 | CI 脚本完善 | P1 | 2026-06-20 | 开发团队 |
| Phase 3 | CI Pipeline 集成 | P2 | 2026-06-25 | 开发团队 |
| Phase 4 | 存量文档归档 | P3 | 2026-06-30 | 开发团队 |
| Phase 5 | Changelog 创建 | P3 | 2026-07-05 | 开发团队 |

---

## 四、验证清单

### Phase 1 验证

- [ ] 所有需求文档已添加状态标签
- [ ] 所有计划文档已添加状态标签
- [ ] `check-doc-status.sh` 执行通过
- [ ] `requirements/README.md` 状态汇总表更新
- [ ] `plans/README.md` 状态汇总表更新

### Phase 2 验证

- [ ] Python 脚本可完整生成 README 内容
- [ ] 归档脚本增加 changelog 前置检查
- [ ] 手动测试归档流程正常

### Phase 3 验证

- [ ] GitHub Actions workflow 创建
- [ ] PR 检查流程正常（状态标签缺失阻止合并）
- [ ] 自动归档流程正常
- [ ] CI Bot 可自动提交变更

### Phase 4 验证

- [ ] 存量 completed 文档已迁移至 archive/
- [ ] `archive/README.md` 归档记录更新
- [ ] `requirements/README.md` 已移除归档记录
- [ ] `plans/README.md` 已移除归档记录

### Phase 5 验证

- [ ] AI-GLUE changelog 已创建
- [ ] AI-Agent changelog 已创建
- [ ] `changelog/README.md` 变更记录更新

---

## 五、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 状态标签遗漏 | 归档流程失败 | PR 检查强制阻止 |
| Changelog 未创建 | 结果沉淀缺失 | 彘档前前置检查 |
| CI Bot 权限不足 | 自动提交失败 | 配置正确的 GitHub Token |
| 归档冲突 | 文档丢失 | 归档前 git stash + 备份 |

---

## 六、后续优化

### 优化方向

| 方向 | 说明 |
|------|------|
| 智能归档 | 基于内容分析自动判断归档时机 |
| 文档评分 | 根据文档质量评分决定归档优先级 |
| 关联图谱 | 可视化需求 → 计划 → 实施 → 沉淀的完整链路 |
| 搜索优化 | 归档文档索引，快速检索历史参考 |

---

## 七、相关文档

| 文档 | 说明 |
|------|------|
| [DOC-LIFECYCLE.md](../standards/DOC-LIFECYCLE.md) | 文档生命周期完整规范 |
| [scripts/README.md](../scripts/README.md) | CI 自动化脚本说明 |
| [GIT-STANDARD.md](../standards/GIT-STANDARD.md) | 文档同步规则 |
| [archive/README.md](../archive/README.md) | 归档导航 |
| [changelog/README.md](../changelog/README.md) | 变更日志导航 |

---

**版本：1.0 | 创建日期：2026-06-12**
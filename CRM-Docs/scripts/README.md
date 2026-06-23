# CRM-Docs CI 自动化脚本

**用途**：文档生命周期自动化管理

---

## 脚本清单

| 脚本 | 用途 | 执行时机 | 版本 |
|------|------|----------|------|
| `check-doc-location.sh` | **检查根目录散落文档** | **pre-commit + CI** | Shell ✅ |
| `check-doc-status.sh` | 检查状态标签完整性 | 每次 PR | Shell |
| `archive_docs.sh` | 自动归档已完成文档 | 每次 CI / 定时 | Shell |
| `update_doc_nav.py` | **更新导航 README（完整版）** | 归档后自动 | **Python ✅** |
| `update-doc-nav.sh` | 更新导航 README（简化版-已废弃） | - | Shell（已废弃） |

---

## 脚本优先级

| 脚本 | 推荐使用 | 说明 |
|------|----------|------|
| **`check-doc-location.sh`** | ✅ **必须** | 阻止根目录散落文档，pre-commit hook |
| **`update_doc_nav.py`** | ✅ **推荐** | 完整版，生成规范的 README 内容 |
| `update-doc-nav.sh` | ❌ 已废弃 | 简化版，仅统计，不生成内容 |

---

## 执行流程

```
Git 提交（pre-commit）
    ↓
check-doc-location.sh（检查根目录散落文档） ← 🆕 新增
    ↓ [违规则阻止提交]
    
PR 提交
    ↓
check-doc-status.sh（检查状态标签）
    ↓
PR 合并（status: completed）
    ↓
archive_docs.sh（自动归档）
    ↓
update_doc_nav.py（更新导航） ← 🆕 Python 版本
```

---

## CI Pipeline 集成示例

### GitHub Actions 配置

```yaml
# .github/workflows/docs-lifecycle.yml

name: Docs Lifecycle Management

on:
  push:
    branches: [ main ]
    paths:
      - 'CRM-Docs/**'
  pull_request:
    paths:
      - 'CRM-Docs/**'
  schedule:
    - cron: '0 2 * * *'  # 每天 2:00 AM 执行归档检查

jobs:
  check-status:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v3

      - name: Check document status
        run: |
          chmod +x CRM-Docs/scripts/*.sh
          bash CRM-Docs/scripts/check-doc-status.sh

  archive-docs:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' || github.event_name == 'schedule'
    steps:
      - uses: actions/checkout@v3

      - name: Archive completed docs
        run: |
          chmod +x CRM-Docs/scripts/*.sh
          bash CRM-Docs/scripts/archive_docs.sh

      - name: Update navigation
        run: bash CRM-Docs/scripts/update-doc-nav.sh

      - name: Commit changes
        run: |
          git config --local user.email "ci-bot@crmwolf.com"
          git config --local user.name "CI Bot"
          git add CRM-Docs/archive/ CRM-Docs/requirements/README.md CRM-Docs/plans/README.md
          git diff --quiet && git diff --staged --quiet || git commit -m "docs(archive): 自动归档已完成文档"
          git push
```

---

## Python 脚本详解

### update_doc_nav.py

**功能**：
- 扫描 requirements/ 和 plans/ 目录
- 提取文档状态信息（status/created/updated/关联文档）
- 生成完整规范的 README 内容
- 自动更新 archive/README.md

**特性**：
| 特性 | 说明 |
|------|------|
| **完整内容生成** | 生成包含状态定义、状态汇总表、待归档清单的完整 README |
| **关联文档追踪** | 自动提取 related_plan/related_requirements 链接 |
| **Changelog 链接** | 为 completed 文档自动生成 changelog 链接 |
| **UTF-8 支持** | 支持中文文档，编码正确 |

**依赖**：
- Python 3.6+
- 无外部依赖（仅使用标准库）

**执行方式**：
```bash
# 从项目根目录执行
python3 CRM-Docs/scripts/update_doc_nav.py

# 输出示例
🔄 开始更新导航文档...
  ✅ 更新 CRM-Docs/requirements/README.md
  ✅ 更新 CRM-Docs/plans/README.md
  ✅ 更新 CRM-Docs/archive/README.md
✅ 导航文档更新完成
```

**生成内容示例**：
- **活跃需求表格**：列出 draft/review/active 状态的文档
- **待归档需求表格**：列出 completed 状态的文档 + changelog 链接
- **状态定义表**：自动生成状态流转说明
- **文档创建规则**：包含模板和流程说明

---

## Shell 脚本详解

### check-doc-status.sh

**检查项**：
- 状态标签存在性（`status`）
- 状态值合法性（draft/review/active/completed/archived）
- 创建/更新日期标签存在性
- 计划文档关联需求文档（警告，不强制）

**失败处理**：
- 状态标签缺失 → 阻止 PR 合并
- 无效状态值 → 阻止 PR 合并

---

### archive_docs.sh

**归档逻辑**：
1. **前置检查**：检查 changelog 目录是否有文档
2. 扫描 `requirements/*.md` 和 `plans/*.md`
3. 检测 `status: completed` 的文档
4. 迁移至 `archive/requirements/` 或 `archive/plans/`
5. 调用 `update_doc_nav.py` 更新导航

**前置检查（新增）**：
```bash
🔍 前置检查: changelog 存在性
✅ changelog 检查通过: 发现 X 个文档

# 如果无 changelog
⚠️  警告: changelog 目录无文档，建议先创建 changelog
是否继续归档（不创建 changelog）？[y/N]:
```

**执行方式**：
```bash
bash CRM-Docs/scripts/archive_docs.sh

# 输出示例
📦 开始自动归档文档...
🔍 前置检查: changelog 存在性
✅ changelog 检查通过: 发现 3 个文档

📦 开始归档流程...
  📦 归档: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md
  ...

✅ 归档完成: 6 个文档

🔄 更新导航 README...
✅ 导航更新完成（Python 版本）

✅ 自动归档流程完成

📋 归档统计:
  - 归档文档数: 6
  - 归档需求数: 6
  - 归档计划数: 9
```

---

## 部署建议

### 立即可用

| 脚本 | 状态 | 说明 |
|------|------|------|
| `check-doc-status.sh` | ✅ 可用 | 可直接集成到 CI |
| `update_doc_nav.py` | ✅ **可用** | **推荐使用 Python 版本** |
| `archive_docs.sh` | ✅ 可用 | 已增强 changelog 前置检查 |

### 执行顺序

```bash
# 1. 检查状态标签（PR 提交时）
bash CRM-Docs/scripts/check-doc-status.sh

# 2. 手动归档（首次）
bash CRM-Docs/scripts/archive_docs.sh

# 3. Python 脚本会自动调用（无需手动执行）
python3 CRM-Docs/scripts/update_doc_nav.py
```

### 后续完善（Phase 3）

1. **CI Pipeline 集成**：
   - 创建 GitHub Actions workflow
   - 配置自动归档触发条件
   - 配置 Git 自动提交

2. **增强 changelog 检查**：
   - 归档前强制检查 changelog 存在
   - 自动关联 changelog 链接

---

## 注意事项

| 注意点 | 说明 |
|--------|------|
| 权限设置 | CI Bot 需有 push 权限 |
| 冲突处理 | 归档操作应避免与其他 commit 冲突 |
| 回滚机制 | 提供手动回滚归档的脚本 |
| 日志记录 | 归档操作应记录详细日志 |

---

**版本：1.0 | 创建日期：2026-06-12**
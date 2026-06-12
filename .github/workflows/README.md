# GitHub Actions 使用指南

**用途**：CI Pipeline 配置说明 + 权限设置

---

## Workflow 文件位置

**文件**：`.github/workflows/docs-lifecycle.yml`

---

## Workflow 功能

### Job 1: check-status（PR 检查）

**触发条件**：PR 提交且涉及 CRM-Docs 文件

**执行步骤**：
1. Checkout 代码
2. Setup Python 3.9
3. 执行 `check-doc-status.sh` 检查状态标签
4. 失败时在 PR 中添加评论（修复指引）

**评论内容**：
- 状态标签缺失说明
- 修复方法示例
- 详细规范链接

---

### Job 2: archive-docs（自动归档）

**触发条件**：Push 到 main 或定时执行（每天 2:00 AM）

**执行步骤**：
1. Checkout 代码（带 GITHUB_TOKEN）
2. Setup Python 3.9
3. 执行 `archive_docs.sh` 归档 completed 文档
4. 执行 `update_doc_nav.py` 更新导航
5. Git 提交归档变更（CI Bot）
6. Push 到 main 分支
7. 创建执行总结

**Git 提交信息**：
```
docs(archive): 自动归档 N 个已完成文档
```

---

### Job 3: periodic-check（定期检查）

**触发条件**：定时执行（每天 2:00 AM）

**执行步骤**：
1. Checkout 代码
2. 检查 completed 文档数 vs changelog 数
3. 如果 changelog 缺失，创建 GitHub Issue

**Issue 内容**：
- 检查日期
- Completed 文档数 vs Changelog 数
- 缺失数量
- Changelog 创建指引
- 优先创建建议

---

## 权限配置

### GITHUB_TOKEN 权限

需要在仓库设置中配置以下权限：

| 权限 | 用途 |
|------|------|
| `contents: write` | CI Bot 推送归档变更 |
| `pull_requests: write` | PR 评论 + 创建 Issue |
| `issues: write` | 创建 changelog 缺失 Issue |

### 配置步骤

1. **仓库设置**：
   - Settings → Actions → General
   - Workflow permissions: "Read and write permissions"
   - 勾选 "Allow GitHub Actions to create and approve pull requests"

2. **验证权限**：
   ```bash
   # 检查 Workflow 是否有 write 权限
   gh api repos/{owner}/{repo}/actions/permissions
   ```

---

## CI Bot 身份配置

**Git 提交身份**：
```
user.email: "ci-bot@crmwolf.com"
user.name: "CI Bot"
```

**提交信息格式**：
```
docs(archive): 自动归档 N 个已完成文档
```

---

## 定时执行配置

**Cron 表达式**：`0 2 * * *`

**说明**：
- 每天 2:00 AM（UTC）执行
- 对应北京时间：10:00 AM（UTC+8）
- 执行归档检查 + 状态检查

---

## 触发路径配置

**路径过滤**：`CRM-Docs/**`

**说明**：
- 只有 CRM-Docs 目录的变更才触发 Workflow
- 其他目录变更不触发，减少 CI 消耗

---

## 测试 Workflow

### 手动触发测试

**方法 1：Push 测试**：
```bash
# 创建测试变更
git add CRM-Docs/
git commit -m "docs(test): 测试 CI Pipeline"
git push origin main
```

**方法 2：PR 测试**：
```bash
# 创建测试 PR
git checkout -b test/docs-lifecycle
git add CRM-Docs/
git commit -m "docs(test): 测试 PR 检查"
git push origin test/docs-lifecycle
gh pr create --title "测试文档生命周期 CI" --body "测试"
```

**方法 3：手动触发（使用 gh CLI）**：
```bash
# 手动触发 workflow
gh workflow run docs-lifecycle.yml
```

---

## 验证清单

### PR 检查验证

- [ ] 状态标签缺失时阻止 PR 合并
- [ ] 失败时在 PR 中添加评论
- [ ] 评论内容包含修复指引

### 自动归档验证

- [ ] Push 到 main 时触发归档
- [ ] completed 文档迁移至 archive/
- [ ] 导航 README 自动更新
- [ ] Git 提交成功
- [ ] Push 到 main 成功

### 定期检查验证

- [ ] 每天 2:00 AM 自动执行
- [ ] changelog 缺失时创建 Issue
- [ ] Issue 内容包含创建指引

---

## 禁用 Workflow（紧急情况）

如果需要紧急禁用 Workflow：

**方法 1：删除文件**：
```bash
rm .github/workflows/docs-lifecycle.yml
git commit -m "chore: 禁用文档生命周期 CI"
git push
```

**方法 2：禁用 workflow**：
```bash
# 在仓库设置中禁用
gh workflow disable docs-lifecycle.yml
```

---

## 监控与日志

### 查看 Workflow 执行日志

```bash
# 查看最近的 workflow 运行
gh run list --workflow=docs-lifecycle.yml --limit 10

# 查看特定运行的日志
gh run view <run-id>
```

### 查看 CI Bot 提交

```bash
# 查看 CI Bot 的提交记录
gh log --author="CI Bot" --oneline
```

---

## 故障排查

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 权限不足错误 | GITHUB_TOKEN 权限不足 | 在仓库设置中启用 write 权限 |
| Push 失败 | 分支保护规则 | 允许 CI Bot 推送到 main |
| Python 脚本失败 | Python 版本不匹配 | 使用 setup-python@v4 |
| 归档无变更 | 无 completed 文档 | 等待文档状态更新 |

---

## 优化建议

### 减少 CI 消耗

1. **路径过滤**：仅 CRM-Docs 目录触发
2. **定时执行**：每天 2:00 AM，避免频繁执行
3. **条件判断**：has_changes=true 才执行 Git 操作

### 提升执行效率

1. **并发控制**：使用 `concurrency` 防止重复执行
2. **缓存配置**：缓存 Python 依赖（如果需要）
3. **增量执行**：仅处理变更文档

---

**Workflow 状态**：✅ 已创建

**下一步**：配置权限 + 测试执行
# Git 提交规范

**AI 自主执行** - 无需用户提醒，按规则自动提交

---

## 提交时机

| 场景 | 触发条件 | 操作 |
|------|----------|------|
| 功能完成 | 单个功能/任务完成，代码可运行 | 立即提交 |
| Bug 修复 | 问题定位并修复，验证通过 | 立即提交 |
| 阶段性完成 | 大任务拆分后的子任务完成 | 立即提交 |
| 配置调整 | 修改配置文件（非红线类） | 单独提交 |
| 文档更新 | 规范文档、注释变更 | 单独提交 |

**禁止提交时机**：
- 代码未完成（半成品）
- 测试未通过
- 有明显 bug
- 依赖未安装/配置未完成

---

## Commit Message 格式

采用约定式提交（Conventional Commits）：

```
<type>(<scope>): <subject>

<body>
```

### Type 类型

| Type | 说明 | 示例 |
|------|------|------|
| feat | 新功能 | feat(ai): 新增内置 AI 助手页面 |
| fix | Bug 修复 | fix(follow-up): 修复客户跟进 schema 路径错误 |
| refactor | 重构 | refactor(api): 统一错误响应格式 |
| docs | 文档 | docs(spec): 更新 Git 提交规范 |
| style | 格式 | style: 统一代码缩进 |
| test | 测试 | test(customer): 新增客户服务单测 |
| chore | 杂务 | chore: 更新依赖版本 |

### Scope 范围

按模块划分：
- `ai` - AI 助手相关
- `lead` - 线索管理
- `customer` - 客户管理
- `opportunity` - 商机管理
- `contract` - 合同管理
- `payment` - 回款管理
- `invoice` - 发票管理
- `auth` - 认证授权
- `api` - API 层
- `ui` - UI 组件
- `store` - Pinia Store
- `router` - 路由
- `spec` - 规范文档

### Subject 主题

- 中文描述，简洁明了
- 不超过 50 字
- 首字母小写，不加句号

### Body 正文（可选）

用于详细说明：
- 多行时每行不超过 72 字
- 说明改动原因、影响范围

---

## 提交前校验

自动执行，失败则阻止提交：

| 校验项 | 命令 | 失败处理 |
|--------|------|----------|
| ESLint | `npm run lint` | 修复 lint 错误后提交 |
| TypeScript | `npm run type-check` | 修复类型错误后提交 |
| Python Lint | `ruff check app/` | 修复 lint 错误后提交 |

---

## 提交流程

```
1. 检查 git status → 确认改动范围
2. 执行 lint/type-check → 全部通过
3. 分组文件 → 按逻辑关联分组
4. 编写 commit message → 符合格式规范
5. git add + commit → 提交
6. 报告用户 → 显示提交摘要
```

### 分组策略

按逻辑关联分组，避免单次提交过多文件：

| 分组 | 文件类型 | 示例 |
|------|----------|------|
| 功能组 | schema + api + service + 前端页面 | AI 助手功能 |
| 修复组 | handler + 相关测试 | Bug 修复 |
| 文档组 | *.md 文件 | 规范更新 |
| 配置组 | package.json / pyproject.toml | 依赖更新 |

**单次提交限制**：
- 文件数 ≤ 10
- 不相关改动分开提交
- 大改动拆分为多个提交

---

## 分支策略

当前采用 **单分支开发**（main）：

- 直接在 main 分支开发
- 每次提交保持代码可运行
- 未来可切换 feature 分支模式

---

## AI 执行规则

| 规则 | 说明 |
|------|------|
| 自动判断 | 根据改动内容判断是否满足提交条件 |
| 主动提交 | 任务完成后主动提交，不等待用户提醒 |
| 分组提交 | 多文件按逻辑分组，分开提交 |
| 校验优先 | 提交前必须通过 lint/type-check |
| 报告用户 | 提交后告知用户提交内容和 commit id |

---

## 示例

### 新功能提交

```bash
# 后端
git add app/schemas/ai_assistant.py app/api/ai_assistant.py app/services/ai_skill_main.py app/main.py
git commit -m "feat(ai): 新增内置 AI 助手 API 接口

- 新增 /api/v1/ai/chat SSE 流式接口
- 新增 /api/v1/ai/history 历史记录接口
- 支持 JWT 认证的 Web 用户对话"

# 前端
git add CRM-Client/src/api/aiAssistant.ts CRM-Client/src/views/AIAssistant.vue CRM-Client/src/router/index.ts CRM-Client/src/AppLayout.vue
git commit -m "feat(ai): 新增内置 AI 助手前端页面

- SSE 流式对话界面
- 历史记录加载
- 侧边栏 AI 入口"
```

### Bug 修复提交

```bash
git add app/services/skills/handlers/follow_up_handler.py
git commit -m "fix(follow-up): 修复客户跟进 schema 路径错误

问题：使用 parent_crud_mapping_name 导致 schema_module 错误解析为 customer
修复：改用 crud_mapping_name 正确解析为 customer_follow_up"
```

---

**版本：1.0 | 最后更新：2026-04-28**
# CRM Agent Query API 验收记录

> 本记录仅覆盖本轮 Query Agent / Agent UI 公共 HTTP 链路，不代表完整 Workflow、checkpoint 数据迁移或生产发布门禁已经完成。

## 运行信息

- 日期：2026-08-27
- 环境：local-dev
- 公共入口：`POST /api/v1/agent/chat/stream`
- 历史读取：`GET /api/v1/agent/sessions/{session_id}/messages`
- 认证：使用本地开发账号重新登录获取临时 Token；凭据未写入文档
- 数据策略：仅新增会话和消息，不删除任何 Dev 数据
- 服务：Backend `localhost:8000`、Frontend `localhost:5173`、MySQL `3307`、Redis `6380`、Qdrant `6333`

## 验收结果

| 场景 | 结果 | 证据 |
|---|---|---|
| typed `AgentChatRequest` 输入 | PASS | `client_request_id` + `input.type=text` + `input.text` 请求返回 200/SSE |
| 同一 Session 查询上海客户 | PASS | Session `949`：返回 6 家公司及 6 个 `entity_ref` |
| 同一 Session 切换到深圳 | PASS | Session `949`：返回 4 家公司，没有继承上海条件 |
| 同一 Session 切换到北京 | PASS | Session `949`：返回 1 家公司，没有复用前一轮客户实体 |
| 结构化公司列表 | PASS | 只有 `text` 和 `entity_list` block；列表项只有 `entity_ref` |
| 历史消息投影 | PASS | Session `950` 历史消息均为 `crm.agent.ui.v1`，旧 `title/fields/ref_id/actions/subtitle` 字段不存在 |
| CRM API 5xx/429 错误分类 | PASS | 定向单元测试覆盖 408、429、500、503 |
| 模型调用有限重试 | PASS | Query Agent 定向测试确认 `ChatOpenAI.max_retries=2`，不重放整个 Agent Turn |

## 真实返回摘要

```text
上海有哪些客户 -> 共找到 6 家公司。
深圳有哪些客户 -> 共找到 4 家公司。
我在北京有哪些客户 -> 共找到 1 家公司。
```

公司名称和实体引用由服务端 CRM 查询结果产生，前端可以依据 `entity_ref` 打开对应客户详情 Sheet；Agent 不再输出旧的列表字段和按钮字段。

## 自动化验证

```text
CRM-Server/tests/unit/test_agent_query_executor.py                         19 passed
CRM-Server Query/Root/UI 定向组合测试                                     144 passed
```

前端在本轮无新增代码变更；此前 Agent 相关前端测试、`npm run type-check` 和 `npm run build` 已通过。构建中的 Sass legacy API、Rollup chunk size 和 `@vueuse/core` 注释为既有警告，不作为本轮 Query 验收失败。

## 未覆盖与发布阻断

- 未在本轮执行写入型 Workflow、历史待办自动完成/人工确认、多任务对账和 checkpoint 恢复的完整公共 API 回归。
- 未执行生产部署、线上数据迁移或 destructive checkpoint cutover。
- 完整 Agent 版本仍需完成全量测试、数据 inventory/备份恢复演练、最终 Code Review 和发布门禁。

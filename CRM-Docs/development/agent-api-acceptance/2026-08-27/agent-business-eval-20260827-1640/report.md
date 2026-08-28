# Agent 公共 API 业务评测补充记录

> 本记录补充验证当前 `crm.agent.ui.v1` 公共 SSE 协议下的业务评测脚本。测试仅运行在 local-dev，不发布生产，不删除任何 Dev 测试数据。

## 运行信息

- 日期：2026-08-27
- 环境：local-dev
- 公共入口：`POST /api/v1/agent/chat/stream`
- 认证：使用本地开发账号重新登录获取临时 Token；凭据未写入文档
- 数据策略：只新增 Agent 会话、消息和查询结果，不删除 Dev 数据
- 服务：Backend `localhost:8000`、MySQL `3307`、Redis `6380`、Qdrant `6333`
- 数据快照：84 家客户、40 个联系人、139 条跟进记录、33 个商机、12 个合同、358 个客户向量文档

## 本轮变更

此前评测脚本仍按已废弃的 `intent`、`tool_result`、`customer_candidates` 事件以及旧的 `message.content` 字段判断结果，因此出现“真实 API 已返回成功，但评测脚本判定失败”的协议误报。

本轮已将评测脚本统一到当前公共协议：

- 以 `agent_ui / phase=final / message` 作为权威结果；
- 通过 `message.metadata.route` 判断 `QUERY`、`WORKFLOW`、`CLARIFY` 等路由；
- 从 `message.blocks[].type=text` 提取文本；
- 从 `entity_list.items[].entity_ref.display_name` 校验客户实体；
- 从 `action_result.status` 校验公开操作结果；
- 交互恢复使用 `interaction_submission`，提交服务端签名的 `submit_action_id` 和选项值；
- 不再依赖已删除的旧事件协议或内部工具名。

## 评测结果

| 场景 | 结果 | 证据 |
|---|---|---|
| 客户摘要：河南双汇发展股份有限公司 | PASS | `QUERY` 路由；`text` + `entity_list`；命中客户实体 |
| 客户摘要：广东智通人才连锁股份有限公司 | PASS | `QUERY` 路由；`text` + `entity_list`；命中客户实体 |
| 客户摘要：广西时顺信息科技 | PASS | `QUERY` 路由；`text` + `entity_list`；命中客户实体 |

汇总：**3 / 3 通过，0 失败**。

典型返回结构：

```text
session -> agent_ui(final) -> done
route: QUERY
blocks: text, entity_list
```

文本块返回公司数量，客户名称和详情引用位于 `entity_list.items[].entity_ref`，前端可根据实体引用打开客户详情 Sheet。

## 自动化验证

```text
CRM-Server/tests/unit/test_agent_business_eval.py  4 passed
CRM-Server/scripts/run_agent_business_eval.py      py_compile passed
```

## 结论与剩余范围

- 本轮 0 / 3 失败是评测器读取旧协议造成的误报，不是这 3 个 Query API 场景的 Agent 功能失败。
- 当前 Query 公共 API 链路、Agent UI v1 结果解析和客户实体引用校验已通过真实 Dev 验收。
- 本记录不等同于完整发布门禁：写入型 Workflow、历史待办自动完成/人工确认、多任务对账、跨会话边界、Action 取消/过期/重复点击、checkpoint 恢复以及生产迁移仍需独立验收。

## 后续评测器收口（2026-08-27）

针对代码审查发现的评测隔离和误判风险，已继续收口：

- 数据快照不再硬编码 `team_id=1`；有 Token 时通过团队接口解析并校验当前认证用户所属团队，也支持显式 `--team-id`。
- 客户、联系人、跟进、商机、合同、回款、发票、部署、License 和向量证据统计及样本查询统一按团队过滤。
- 评测器使用服务端 `AgentSSEEventEnvelope` 严格校验 `crm.agent.ui.v1` 的 SSE 事件、最终消息和嵌套 block；非法 envelope 不会被当成成功。
- confirmation 交互只允许提交明确的 `value=confirm`，不再依赖选项顺序自动误选。
- 新增 transport error、缺失 done、非法实体引用、失败 action result 等协议/业务失败测试。

验证结果：

```text
CRM-Server/tests/unit/test_agent_business_eval.py  10 passed
Agent 相关单元回归                         703 passed, 20 skipped
真实 Dev Query API 评测                     3 / 3 passed
```

本轮仍未执行写入型自动确认评测，不删除任何 Dev 数据，也未发布生产。

# CRMWolf Agent 设计规范

这是 CRM AI Agent 的目标状态规范库根入口。Agent 面向“围绕客户跟进记录的智能客户关系管理系统”，当前重点是销售跟进记录、客户识别、商机创建/推进、客户资料补充、IM 协作入口，以及通过现有 CRM API 执行业务动作。

## 核心原则

这些原则来自 LangChain 迁移到 LangGraph 过程中暴露的问题，后续设计、实现和评审必须优先按这些原则校验。

1. LangGraph 管状态，不做包装层

   LangGraph 必须承载业务状态机：新流程、当前待办、字段补全、确认执行、暂停草稿、恢复草稿、跨渠道确认、用户追问。不能只是把原来的线性函数调用搬进图节点里。

2. LangChain/LLM 管结构化语义，不管确定性写入

   LLM 负责把用户输入转成结构化判断和结构化业务 payload，例如 `AgentSemanticParseResult`、`AgentTurnRelationDecision`、确认意图和质检结果。LLM 不直接决定数据库写入，不直接调用 CRM API，不生成前端业务协议。

3. 代码管业务规则、权限、幂等和前端协议

   写入动作必须经过 Agent task、HITL、guardrails、幂等 key 和 CRM API。前端弹窗、表单、选择器依赖结构化 `interaction` 协议，不依赖自然语言文案。

4. 禁止关键词驱动核心意图路由

   不能用 `patch_keywords`、固定句式或正则关键词决定“继续当前任务、修改草稿、恢复暂停草稿、开启新流程”。关键词可以用于搜索、去重、格式清洗、保守候选提示，但不能直接触发业务状态迁移或写入。

5. 显式用户输入优先于会话记忆

   session memory 只能在用户没有明确新客户/新业务对象时继承。用户本轮明确提到客户时，必须以本轮显式客户为准，并重新走客户搜索/候选选择，避免旧客户惯性。

6. 不确定就追问，不自动迁移状态

   会改变任务状态的动作，例如恢复暂停草稿、切换新流程、修改待确认草稿，必须满足高置信结构化判断和真实任务 ID 命中。低置信、多个候选接近、target task 不存在时，必须 `ASK_USER`。

7. 文案可以自然，协议必须稳定

   用户可见文案可以简洁、轻快、非模板感；业务系统识别必须依赖结构化事件和 `interaction` 字段。文案修改不能破坏前端协议，前端也不能解析文案来驱动业务。

8. 渠道入口只能适配协议，不能复制 Agent 业务状态机

   Web、飞书、后续企业微信/钉钉都必须进入统一 `AgentApplicationService`。IM Gateway 只做用户绑定、消息归一、@ 过滤、引用/表情绑定、确认/拒绝结构化输入映射，不做 CRM 语义判断。

9. 真实场景回归必须覆盖多轮和分叉

   fake parser 单测只能验证图和业务代码。上线前还必须用真实模型跑 20-50 个 CRM 场景，覆盖多客户、多草稿、暂停恢复、字段修改、确认/拒绝、IM 引用/群聊等路径。

## 当前架构

- Channel Adapter：Web SSE、飞书事件、后续 IM 平台事件适配。只处理鉴权、协议解析、SSE/IM 回复编码。
- IM Agent Gateway：归一化 IM 文本、引用消息、reaction、群聊 @ 过滤和会话绑定。禁止做 CRM 自然语言语义分析。
- AgentApplicationService：统一一轮 Agent 交互，负责会话、消息、pending graph 入口、确认执行、新流程 runtime 和事件落库。
- PendingTaskGraph：LangGraph 业务状态机，负责 active task、suspended task、打断、恢复、字段补全、选择和确认前路由。
- CRMAgentGraphService：LangGraph 新流程编排，负责 memory、语义解析、客户搜索、跟进质检、客户上下文、业务建议和响应事件。
- AI Capability：基于 LangChain structured output 优先输出结构化结果；失败时才走 JSON fallback。
- Interaction Contract：统一生成 `choice/form/text` 交互协议，供 Web 和 IM 共用。
- Tool Runtime：统一执行 CRM tool，所有写入走 HITL、权限、幂等、审计和现有 CRM API。
- CRM Domain Policy：承载 Agent 内部业务规则，例如去重、字段缺失、商机建议、采购方式、上下文前置条件。
- Copy Layer：集中管理用户可见文案，避免散落在 runtime、graph、tool 中。

## LangGraph 与 LangChain 分工

LangGraph 适合：

- 多轮任务状态管理。
- 当前任务和暂停草稿之间的路由。
- 分支、回退、追问和终止条件。
- 编排确定性节点，例如客户搜索、质检、上下文加载、建议生成。
- 统一 stream/runtime 路径，避免手写流程绕过图。

LangChain 适合：

- LLM structured output。
- Prompt 模板和模型调用封装。
- 语义解析、任务关系判断、确认意图、跟进质量评估、建议生成。
- 在失败时提供清晰 fallback 元数据。

代码确定性执行适合：

- 任务 ID 校验、权限校验、状态迁移阈值。
- CRM API tool 调用。
- 字段安全合并。
- 前端 interaction 协议生成。
- IM 事件去重和 session 绑定。

## 任务关系模型

每一轮用户输入和当前业务状态必须显式分类，不能隐式沿用当前 pending task。

`AgentTurnRelationDecision.relation` 包括：

- `CONTINUE_ACTIVE_TASK`：继续当前等待任务。
- `PATCH_ACTIVE_DRAFT`：修改当前草稿。
- `RESUME_SUSPENDED_DRAFT`：恢复或修改暂停草稿。
- `START_NEW_FLOW`：开启新客户或新业务流程。
- `ASK_USER`：关系不确定，需要用户选择。
- `CHITCHAT`：寒暄或无业务动作。

执行层硬约束：

- `target_task_id` 只能来自 active task 或 suspended task snapshots。
- 低于高置信阈值时不能自动恢复或修改任务。
- target task 不存在、状态不匹配、不可恢复时必须追问或走新流程，不能编造。
- 多个暂停草稿并存时，snapshot 必须提供 `summary`、`action`、`customer_name`、`missing_fields`、`status`、时间字段和原始 `state/input`，让模型基于任务卡片选择，而不是翻不稳定的内部 JSON。
- LLM 的选择只是“候选判断”；执行层仍必须校验 `target_task_id` 属于候选集合、置信度达到阈值、任务状态可恢复。
- 多个候选语义接近、只有“继续/改一下/补一下”等弱指代、或者本轮没有足够业务线索时，必须 `ASK_USER`，不能因为只有最近任务就自动恢复。
- 默认澄清问题最多展示 1-2 个候选摘要，问题要短，不暴露 `task_id/session_id` 等内部标识。

## 客户记忆原则

会话记忆用于承接，不用于覆盖用户本轮显式表达。

- 用户说“这个客户、继续、那边”且没有新客户名称时，可以继承 `session_context.current_customer`。
- 用户明确说出新客户时，必须重新搜索客户，不能继续使用旧客户。
- 如果模型漏识别显式客户，允许使用保守 hint 触发客户搜索，但 hint 不直接决定写入对象。
- 客户搜索结果 0 个或多个时，必须走澄清/选择，不能自动写到记忆客户。

## IM 会话原则

- 群聊消息必须在后端校验是否 @ 当前机器人；飞书后台关闭群消息订阅只能减少事件，不能替代后端保护。
- p2p 使用用户维度 session；群聊使用 `team_id + provider + chat_id + thread_id + user_id` 绑定，避免不同用户和不同线程串线。
- 文本回复引用机器人消息时，优先用隐藏 reply binding 定位 session/task。
- reaction 只处理机器人回复上的确认/拒绝表情，未知表情忽略。
- 文本“是/确认/取消”只有在引用命中，或当前/群聊 30 分钟窗口内存在唯一可执行确认任务时才绑定；多个候选时不能随机选择。
- IM Gateway 不解析 CRM 业务意图，不判断客户、商机、回款等业务动作。
- Web 端 session 由前端显式传入；端内 IM 和飞书群聊 session 由后端 scope 生成。所有渠道最终必须进入同一个 `AgentApplicationService`，同一轮输出必须包含统一事件和 interaction 协议。
- 用户可见文案不得显示内部 `session_id`、`task_id`。这些 ID 只能放在结构化事件、隐藏绑定、审计日志或前端协议中。

## 用户文案与前端协议

用户可见文案目标口吻：简洁精准、轻快自然。示例：

- “好嘞，跟进已记录。”
- “商机信息齐了。要为「客户名」创建商机吗？”
- “还差商机的这些信息：预计成交日期、采购方式。”

前端必须依赖结构化协议：

- `schema_version`
- `business_action`
- `status`
- `type`
- `fields`
- `choices`
- `payload`
- `task_id`
- `task_key`

文案集中化要求：

- 新增用户可见文案优先进入 `agent_copy.py` 或 response/copy builder。
- graph、runtime、IM adapter 中只允许少量通道错误提示和日志文案。
- 测试优先断言事件、状态、interaction 协议，不应死绑完整自然语言句子。
- 通道错误提示如果会发给用户，也应优先复用 `agent_copy.py`；日志和 prompt 不属于用户可见文案。
- LLM 可以生成自然语言候选文案，但业务最终回复应经过 response builder/copy 层整形，保证口吻统一、长度可控、结构化协议稳定。

## 当前应用边界

安全与权限边界 > 业务需求文档 > Agent 设计规范 > 具体实现细节。

- 禁止直接操作客户、商机、合同、回款、发票等业务数据库表。
- 禁止绕过 CRM API、权限体系和审批流程。
- 写入类 tool 必须经过用户确认。
- 创建合同第一版不支持，因为现有创建合同流程需要合同附件。
- 合同、回款、发票和 License 写入闭环不是当前阶段主目标。
- Agent 自有会话、消息、任务、tool 调用、幂等记录可以使用 Agent 自有表。

当前实现模块：

- `session_state.py`：会话归属、当前客户记忆、pending task、suspended task、任务关系判断入口。
- `input.py`：Web、IM 文本和 reaction 的通道无关输入模型。
- `confirmation_intent.py`：可执行任务确认/拒绝/未知判断。
- `pending_graph.py`：active/suspended task 的 LangGraph 状态机。
- `graph.py`：新流程 LangGraph 编排。
- `semantic.py` / `prompts.py`：LangChain structured output 和 JSON fallback。
- `interactions.py`：统一构造端内和 IM 可复用的交互描述。
- `response_builder.py`：新流程响应和事件构造。
- `agent_copy.py`：用户可见短文案。
- `task_factory.py`：从图事件创建等待确认的 Agent task。
- `field_common.py`：字段补全过程共用解析和安全合并。
- `follow_up_fields.py`、`lead_fields.py`、`customer_fields.py`、`opportunity_fields.py`、`customer_related_fields.py`、`payment_fields.py`：各业务补字段状态推进。
- `selection.py`：客户、合同、回款计划等候选项选择。
- `task_actions.py`：Agent action 到 CRM tool/payload 的映射。
- `task_execution.py`：确认后执行 tool、HITL guardrails、幂等和结果转下一步任务。
- `im_agent_gateway.py`：IM 引用、reaction、session 绑定和结构化输入映射。
- `im_feishu.py`：飞书事件适配、@ 过滤、消息回复和隐藏绑定记录。

## 回归要求

Agent 相关基础回归：

```bash
cd CRM-Server
venv/bin/python -m pytest tests/unit/test_agent_*.py -q --no-cov
```

业务场景回归应至少覆盖：

- 单客户跟进记录创建。
- 跟进后建议商机并延后处理。
- 暂停商机草稿后恢复并修改字段。
- 多个暂停草稿并存时明确恢复其中一个。
- 多个暂停草稿并存且语义不清时追问。
- 当前客户记忆承接。
- 显式新客户覆盖旧客户记忆。
- 客户搜索 0 个、1 个、多个候选。
- Web 确认/拒绝。
- IM 引用补字段。
- IM reaction 确认/拒绝。
- 飞书群聊非 @ 忽略。
- 飞书群聊不同 thread 不串 session。
- 飞书同一群聊存在多个等待确认任务时，未引用的“确认/是”不能随机绑定。

真实模型回归入口：

```bash
cd CRM-Server
CRMWOLF_AGENT_REAL_MODEL_REGRESSION=1 OPENAI_API_KEY=... OPENAI_MODEL=gpt-4o-mini \
  venv/bin/python -m pytest tests/unit/test_agent_real_model_regression.py -q --no-cov
```

真实模型回归必须作为上线前验收项，不替代 fake parser 单测；fake parser 验证状态机和业务代码，真实模型验证语义理解、草稿选择、显式客户覆盖和追问策略。

## 领域索引

- [基础原则](foundations/README.md)
- [运行时规范](runtime/README.md)
- [治理规范](governance/README.md)
- [实施路线](roadmap/README.md)

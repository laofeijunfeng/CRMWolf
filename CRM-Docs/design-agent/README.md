# CRMWolf Agent 设计规范

这是 CRM AI Agent 的目标状态规范库根入口。Agent 面向“围绕客户跟进记录的智能客户关系管理系统”，当前重点是销售跟进记录、客户识别、商机创建/推进、客户资料补充、IM 协作入口，以及通过现有 CRM API 执行业务动作。

## 核心原则

这些原则来自 LangChain 迁移到 LangGraph 过程中暴露的问题，后续设计、实现和评审必须优先按这些原则校验。当前目标不是完成某个单点业务动作，而是把 Agent 底层升级为 LangGraph 原生、可恢复、可观测、可分支演进的运行时。

1. LangGraph 管状态，不做包装层

   LangGraph 必须承载业务状态机：新流程、当前待办、字段补全、确认执行、暂停草稿、恢复草稿、跨渠道确认、用户追问。不能只是把原来的线性函数调用搬进图节点里。

   任何跨轮、等待用户、可恢复、会影响业务写入的 Agent 状态，都必须进入 LangGraph checkpoint，并通过 `interrupt()` / `Command(resume=...)` 暂停和恢复。`crm_agent_tasks` 和消息表只能作为前端展示与审计投影；session context 只能保存非 HITL 记忆，不能承载等待态恢复。

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

10. 减少模型猜测，暴露必须猜测的地方

   Agent 可靠性取决于系统消除了多少个“模型必须猜”的决策点。模型只负责理解自然语言中的意图、实体、时间表达、业务信号和候选建议；客户选择、对象 ID、权限、字段必填、枚举映射、日期换算、状态迁移、tool 执行和结果判定必须由代码、schema、业务 API 和 guardrail 完成。

   不要把“让模型更准确”作为第一解法。优先收窄参数、拆开语义重叠的工具、只返回业务需要的字段、让错误直接暴露可修复信息，并把循环、过滤、聚合、排序、阈值和状态检查交给确定性代码。

11. 猜错必须可发现，不能指数衰减

   模型判断不可能清零错误，因此所有模型输出都必须留下可审计证据：结构化来源、模型名称、Prompt 版本、fallback 原因、置信度、缺失字段、候选对象、guardrail 决策和 tool 结果。trace 应能让排查者逐步回答：“这一步是在读取事实，还是在猜测？”

   失败必须尽早暴露在 schema 校验、业务校验、HITL、测试或外部 trace 中。不得让模型把 API 错误、权限失败、对象不唯一、字段缺失或 tool 静默失败改写成成功文案。

## 目标架构

- Channel Adapter：Web SSE、飞书事件、后续 IM 平台事件适配。只处理鉴权、协议解析、SSE/IM 回复编码。
- IM Agent Gateway：归一化 IM 文本、引用消息、reaction、群聊 @ 过滤和会话绑定。禁止做 CRM 自然语言语义分析。
- AgentApplicationService：统一一轮 Agent 交互的应用入口，只负责会话/thread 映射、消息落库、权限上下文注入、root graph 调用和事件投影，不拥有图外业务 pending 状态机。
- Agent Root Graph：LangGraph 原生运行时入口，负责 checkpoint state 读取、语义路由、全局 guardrail、领域 subgraph 调用、interrupt/resume 和最终响应聚合。
- Domain Subgraphs：客户识别、跟进记录、商机、客户资料维护、回款、tool 执行等领域子图。复杂业务分支必须沉淀为 subgraph，不得堆在单个线性 runtime 中。
- Interrupt Runtime：所有选择、补字段、确认、编辑、拒绝和暂停恢复都通过 LangGraph interrupt 表达，并通过 `Command(resume=...)` 继续原图执行。
- Task Projection：`crm_agent_tasks` 保存等待动作投影、前端展示和审计；运行时恢复以 LangGraph checkpoint 为准。
- AI Capability：基于 LangChain structured output 优先输出结构化结果；失败时才走 JSON fallback。
- Interaction Contract：统一生成 `choice/form/text` 交互协议，供 Web 和 IM 共用。
- Tool Runtime：统一执行 CRM tool，所有写入走 HITL、权限、幂等、审计和现有 CRM API。
- CRM Domain Policy：承载 Agent 内部业务规则，例如去重、字段缺失、商机建议、采购方式、上下文前置条件。
- Copy Layer：集中管理用户可见文案，避免散落在 runtime、graph、tool 中。

## LangGraph 与 LangChain 分工

LangGraph 适合：

- 多轮任务状态管理。
- 当前任务和暂停草稿之间的路由。
- checkpoint/thread 持久化和跨轮恢复。
- interrupt/resume 用户确认、选择、补字段、编辑和拒绝。
- 领域 subgraph 组合和复用。
- 分支、回退、追问和终止条件。
- 编排确定性节点，例如客户搜索、质检、上下文加载、建议生成。
- 统一 stream/runtime 路径、state history 和 trace，避免手写流程绕过图。

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

采用标准见 [LangGraph 原生运行时](runtime/langgraph-native-runtime.md)。评审时如果发现新能力只把 LangGraph 当作 service 外层包装，而没有使用 checkpoint、interrupt/resume、conditional edge 和 subgraph 解决真实跨轮分支问题，应判定为架构不合格。

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

当前实现模块与迁移方向：

- `root_runtime.py`：Agent Root Graph 的主入口，使用 `StateGraph`、`context_schema`、checkpoint thread id、conditional edges、`interrupt()` 和 `Command(resume=...)` 承载一轮 Agent 的运行时事实；`run_turn()` 是 application 正常路径唯一入口，负责 checkpoint interrupt 读取、pending subgraph、新流程 graph、确认执行、无待办确认等分支，并产出统一 `AgentRuntimeTurnOutput`。当 checkpoint interrupt 带有 task projection 时，root runtime 必须先按 checkpoint 对齐 runtime context task；没有 checkpoint interrupt 时，不得从 session context 或 waiting task 反向恢复旧等待态。
- `state.py`：定义 checkpoint-safe state、graph input、graph result、run-scoped runtime context、side effects 和应用层 turn output。Graph input 可以承接本轮 DB/session/task/authorization 等运行依赖；checkpoint state 只能保存结构化 JSON-ish 数据；Graph result 通过 side effects 合并本轮对象，不能反向污染可持久状态。
- `application.py`：只作为应用入口和 transport/message adapter，负责 session/user message/assistant message 落库、调用 `agent_root_runtime.run_turn()`、trace 投影和 SSE 事件输出；正常路径不得直接调用 `checkpoint_turn_start()`、`resume_interrupt()` 或重新实现 pending/new-flow/confirmed-task 业务分支。checkpoint 存储不可用时允许进入显式 fallback，但 fallback 只能作为故障隔离路径，并且必须通过 `agent_root_checkpoint_unavailable_fallback_started` 在 SSE 与 assistant trace 中显式暴露。
- `app/api/agent.py`：除会话、消息和 SSE 入口外，还提供 root runtime 的只读 checkpoint state/history 查询接口。诊断多分支、HITL 恢复和跨轮行为时必须优先读取 LangGraph checkpoint 投影，不应只依赖 message payload 或 `crm_agent_tasks`。
- `interrupts.py`：统一 `agent.interrupt.v1` 等待/恢复协议，把 confirm、form、choice、text 等等待态映射到 LangGraph interrupt payload；`WAITING_USER` task 只能作为新等待事件写入 checkpoint interrupt 时的展示/审计投影源，不作为恢复真相。
- `pending_effects.py`、`new_flow_effects.py`：Graph 节点内应用业务 side effects，例如创建等待任务投影、记忆当前客户、暂停/恢复 pending task、补充切换提示和最终回复；本轮产生的等待事件必须投影为 `current_interrupt` 并交回 root graph 写入 checkpoint。side effect handler 必须由 graph 节点调用，不能散落到 application 编排里。若业务子图已经产出原生 `current_interrupt`，side effect handler 必须优先使用子图 interrupt；事件投影只用于把本轮新等待事件标准化为 checkpoint payload。
- `confirmed_task_graph.py`：确认后的写入执行子图，由 root graph 调用；使用独立 `StateGraph`、`context_schema`、checkpoint thread 和 input/state/result 边界承载确认执行、tool 结果、任务完成/失败和最终回复事件。
- `checkpointer.py`：统一 checkpoint 存储错误识别和 fallback 审计事件；root/application、pending-task、confirmed-task 等长期运行路径进入 no-checkpointer fallback 时必须显式暴露 `checkpoint_unavailable` 与 `fallback_reason`。
- `confirmed_task_graph.py` / `confirmed_task_effects.py`：confirmed-task subgraph 直接拥有写任务执行节点，复用现有 tool registry、HITL guardrails、幂等和 CRM API；任务清理、下一步任务建议等非 checkpoint 副作用集中在 effects 层。application 正常路径不得绕过 subgraph 直接调用写任务执行。
- `session_projection.py`：session context 的非 HITL 记忆白名单，只允许向 runtime 暴露 `current_customer` 等记忆；等待态、挂起态和任务恢复不得从 session JSON 投影。
- `session_state.py`：当前用于会话归属、当前客户记忆、pending task、suspended task、任务关系判断入口；pending/suspended 的恢复只能从 LangGraph checkpoint interrupt 进入，`crm_agent_tasks` 只作为展示、审计和本轮 task projection 读取，session context 不再承载运行时 pending 真相。
- `input.py`：Web、IM 文本和 reaction 的通道无关输入模型。
- `confirmation_intent.py`：可执行任务确认/拒绝/未知判断。
- `pending_graph.py`：active/suspended task 子图，由 root graph 调用并通过 side effect handler 应用结果；已按 `context_schema` 拆分 input/state/result，避免 DB session、ORM task 和 authorization 进入 checkpoint。挂起草稿归属澄清、字段补充、客户选择、业务对象选择、文本补充和二段确认已进入子图原生 `interrupt()` 暂停点，并通过 root 传入的 `Command(resume=...)` 恢复同一 pending 子图 thread。
- `pending_interaction_graph.py`：pending interaction 领域子图，使用显式节点、handler registry 和 conditional edge 承载字段补充、客户选择和业务对象选择；字段类等待任务的 route/node/predicate/collector/event 归图注册表表达，等待恢复执行原语已并入子图节点边界，不再保留独立 pending interaction runtime。
- `graph.py`：新流程 LangGraph 编排，已经由 root graph 直接调用；已按 `AgentGraphInput`、`AgentGraphState`、`AgentGraphResult` 和 `AgentGraphRuntimeContext` 区分应用输入、checkpoint 状态、输出结果和运行依赖。客户识别、重复检查、业务上下文、行动规划、跟进质量、商机、联系人、发票抬头、部署信息、客户成员、回款登记等已拆为 domain subgraphs；后续新增业务必须继续按领域子图扩展，不能回到单流程 runtime。
- `*_graph.py` 领域子图：每个子图必须有 checkpoint-safe state、`context_schema`、明确 route event 和独立单测；只读/规划类子图可调用 LLM structured output，写入类子图只能生成候选 tool request 或等待确认，不能直接绕过 confirmed-task/tool 执行边界。
- `semantic.py` / `prompts.py`：LangChain structured output 和 JSON fallback。
- `interactions.py`：统一构造端内和 IM 可复用的交互描述。
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

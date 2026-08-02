# 客户智能档案整体方案

## 1. 方案结论

将“客户档案”升级为 **客户智能中枢**。

它不再只是客户详情页里的 AI 生成字段，而是由 Agent 统一维护、由业务事件持续触发、由知识库沉淀上下文、由 LangGraph 编排分析与更新流程的客户记忆系统。

最终目标：

- 客户档案自动保持更新
- Agent 能理解客户现状
- Agent 能解释判断依据
- 跟进、商机、合同、回款、业务流程都能触发客户档案更新
- 客户知识能反哺商机推进、合同处理、回款风险、销售建议和 IM 问答

## 2. 当前业务架构

当前客户相关信息分散在多个模块：

- 客户基础信息
- 跟进记录
- 商机
- 合同
- 回款
- 联系人 / 客户成员
- 业务流程
- Agent 对话与工具调用

目前已有能力：

- `customer_profile_service.py`
  - 生成公司背景、官网、主营业务、相似客户、项目背景等字段
- `customer_brief_service.py`
  - 结合客户、联系人、商机、合同、回款、跟进记录生成销售侧客户概况
- `deal_journey_service.py`
  - 记录商机创建、审批通过、阶段推进、赢单、输单等业务事件
- Agent runtime
  - 已具备 LangGraph 化的图编排、确认、中断恢复、工具调用、执行轨迹能力

当前主要问题：

- 客户档案偏静态，像“某次生成出来的资料”
- 客户档案生成和 Agent 架构还没有完全统一
- 跟进、商机、合同、回款、流程事件没有统一沉淀为客户知识
- Agent 使用客户上下文时，缺少统一的客户记忆底座
- 档案更新缺少来源、置信度、版本和审计

## 2.1 LangGraph 对齐原则

客户智能档案不能只是把现有 service 包一层图。LangGraph 在这里要承担“运行时”的职责：

- 图负责流程状态、分支、中断、恢复、执行轨迹
- service 负责确定性的业务能力，比如查询客户、写入事实、刷新字段
- LLM 只进入需要语义理解、归纳、冲突判断和置信度评估的节点
- checkpoint 保存一次 Agent 执行中的短期状态
- store 保存跨会话、跨入口复用的长期客户记忆
- 向量库保存可语义召回的证据文本和摘要
- 业务数据库仍然是客户、商机、合同、回款等强业务状态的事实来源

对应到实现原则：

- 每个子图必须定义清晰的 input state、internal state、output state
- 图 state 不使用松散字典承载核心业务数据
- 执行步骤、候选对象、抽取事实、置信度结果用 reducer 累积
- 最终决策、当前阶段、刷新范围用明确字段覆盖
- 节点可以失败、重跑、恢复，所以写库和外部副作用必须具备幂等键
- 用户可见内容必须由执行轨迹投影生成，不能直接暴露工具名和节点名

### 2.2 LangGraph 能力映射

客户智能档案必须按 LangGraph 官方能力设计，而不是只使用 `StateGraph` 的外壳。

能力映射：

- `StateGraph`
  - 承载客户智能更新的流程状态、节点、条件边和子图
  - 每个节点只做一类事情，返回结构化 state 更新
- `Reducers`
  - 累积执行步骤、证据、抽取事实、错误、候选对象
  - 避免节点之间互相覆盖过程信息
- `Command`
  - 用于带状态更新的动态跳转
  - 适合“分析后直接进入刷新 / 等待确认 / 跳过 / 后台重建”的分支
  - 同一段流程不要同时依赖静态边和 `Command` 跳转表达同一个路由意图
- `Interrupt`
  - 只用于必须人工参与的场景
  - 中断点必须可恢复，用户回复后通过 `Command(resume=...)` 回到图内继续执行
- `Checkpointer`
  - 保存一次运行的短期状态、等待点、重试位置和恢复上下文
  - 不能当客户档案、客户事实或审计表使用
- `Store`
  - 保存跨会话、跨入口复用的长期客户记忆
  - 不能替代业务数据库和向量数据库
- `Subgraphs`
  - 把客户上下文读取、记忆检索、事实抽取、事实融合、档案刷新拆成可复用能力
  - 被跟进、商机、合同、回款、IM、Web Agent 共同调用
- `Streaming`
  - 前台 Agent 必须实时输出用户可理解的执行过程
  - 子图内部关键步骤需要透出，技术节点需要屏蔽
- `Runtime Context`
  - 传递租户、用户、入口、权限、时区、graph 版本和 request id
  - 不把运行时身份信息混入 LLM 自然语言提示词
- `Durable Execution`
  - 每个写入节点具备幂等键
  - 失败后能从 checkpoint 继续
  - 用户确认、后台重试和运维诊断都能回到同一个 graph run
- `Observability`
  - 每次 graph run 要能看到输入、节点状态、LLM 结构化输出、工具调用、interrupt、resume、最终写入
  - 生产环境需要接入 LangSmith 或等价 trace 系统做回放、评估和问题定位

设计验收标准：

- 如果一个流程没有 checkpoint、interrupt/resume、streaming、typed state、subgraph、store 边界，就不能称为 LangGraph-native。
- 如果用户可见步骤来自工具名或节点名直出，说明 trace 投影不合格。
- 如果 LLM 自由文本结果被字符串解析后直接写库，说明结构化输出和确定性写入边界不合格。
- 如果后台业务事件和前台对话各维护一套客户档案更新逻辑，说明子图复用不合格。
- 如果客户长期记忆只存在会话上下文里，说明 Store / 向量库 / 业务事实库边界不合格。

## 3. 目标业务架构

客户档案应升级为四层结构。

### 3.1 基础档案层

保存相对稳定的信息：

- 公司背景
- 官网
- 所属行业
- 主营业务
- 公司规模
- 相似客户
- 项目背景

这类信息不应频繁覆盖，只有在证据明确、用户主动刷新或发生重大变化时更新。

### 3.2 销售动态层

保存销售过程中持续变化的信息：

- 当前客户诉求
- 当前采购进展
- 当前商机状态
- 关键人态度
- 决策链关系
- 风险点
- 下一步建议
- 最近重要变化

这部分应该随着业务动作持续更新。

### 3.3 客户知识层

沉淀客户级事实，不直接等同于页面字段。

每条客户知识包含：

- `customer_id`
- 来源类型：跟进、商机、合同、回款、审批、业务流程、IM 消息
- 来源对象
- 事实类型：需求、预算、风险、阶段、联系人态度、竞品、下一步
- 事实内容
- 置信度
- 生效状态
- 发生时间
- 提取时间
- 引用证据

### 3.4 语义检索层

使用向量数据库管理可检索内容。推荐实现使用 **Qdrant**。

- 跟进记录原文
- 业务流程记录
- 商机变化摘要
- 合同摘要
- 回款摘要
- 客户阶段性总结
- 历史 Agent 判断依据

结构化事实库负责准确状态，向量检索层负责语义召回。

Qdrant 在本方案中的定位：

- 只保存可语义召回的证据文本、摘要和历史判断依据
- 不保存商机阶段、合同状态、回款金额等强业务事实
- 不作为客户档案页面的最终展示来源
- 不直接决定是否更新客户档案
- 检索结果只作为 Agent 判断、归纳、引用依据的证据输入

推荐 collection：

```text
crm_customer_evidence
```

每条向量文档包含：

```text
id
tenant_id
team_id
customer_id
source_type
source_object_id
business_object_type
business_object_id
title
text
text_hash
occurred_at
created_at
updated_at
confidence
visibility_scope
metadata_version
```

检索策略：

- 先按 `tenant_id`、`team_id`、`customer_id` 做强过滤
- 再按 `source_type`、`business_object_type`、时间范围缩小候选
- 最后做语义 Top-K 召回
- 返回结果必须带来源对象和证据片段
- Agent 回答和档案刷新必须引用 evidence refs

这样可以避免跨租户、跨团队、跨客户污染，也能让用户看到“这个判断来自哪条跟进、哪个流程、哪个商机变化”。

### 3.5 LangGraph 长期记忆层

客户智能档案需要使用 LangGraph store 承载跨会话记忆，并和业务事实库、向量库保持清晰边界。

LangGraph Store 不是一款固定数据库，而是 LangGraph 的长期记忆接口。CRMWolf 不需要为了 Store 再引入一套新数据库，推荐使用 MySQL-backed Store 实现。

建议命名空间：

```text
(tenant_id, "customer", customer_id, "facts")
(tenant_id, "customer", customer_id, "summaries")
(tenant_id, "customer", customer_id, "preferences")
(tenant_id, "customer", customer_id, "retrieval")
```

存储职责：

- `facts`
  - 保存 Agent 提炼出的客户事实索引，指向业务事实库记录
- `summaries`
  - 保存阶段性客户摘要，供后续 Agent 快速读取
- `preferences`
  - 保存客户级沟通偏好、销售关注点等长期信息
- `retrieval`
  - 保存语义检索元数据，指向向量库文档

这样 Agent 在 Web、IM、业务流程中进入同一个客户时，可以读取同一套长期客户记忆，而不是依赖某个会话里的聊天历史。

Store 与其他存储的边界：

- MySQL 业务表保存正式业务数据和客户事实
- Qdrant 保存可语义召回的证据文本
- LangGraph Store 保存 Agent 长期记忆、摘要、偏好和检索索引
- Store 中的 `facts` 只保存事实索引，不复制完整业务事实
- Store 中的 `retrieval` 只保存向量文档索引，不复制完整向量文本

推荐 MySQL-backed Store 表：

```text
agent_memory_entries
```

核心字段：

```text
id
tenant_id
namespace
key
value_json
version
created_at
updated_at
expires_at
```

其中 `namespace` 保存 LangGraph Store namespace，`key` 保存记忆键，`value_json` 保存 JSON 可序列化的长期记忆内容。

## 4. 实现后的 Agent 架构

Agent 需要新增一个客户智能子图：

```text
Agent Root Graph
  ├─ 意图识别
  ├─ 业务对象解析
  ├─ 客户智能子图 Customer Intelligence Graph
  ├─ 商机子图
  ├─ 合同子图
  ├─ 回款子图
  ├─ 跟进记录子图
  └─ 用户确认 / 中断恢复
```

客户智能子图负责客户档案相关的一切更新和问答支撑。

核心流程：

```text
触发事件进入
  ↓
识别客户与业务对象
  ↓
加载结构化业务上下文
  ↓
向量检索历史语义证据
  ↓
LLM 抽取客户事实
  ↓
事实合并、去重、冲突判断
  ↓
置信度评估
  ↓
决定更新范围
  ↓
需要确认则 interrupt
  ↓
写入客户知识库
  ↓
刷新客户档案 / 客户概况
  ↓
输出执行轨迹
```

### 4.1 Graph 状态模型

客户智能子图的状态应拆成三类 schema。

```text
InputState
  trigger_event
  user_message
  customer_hint
  source_object_hint

InternalState
  runtime_context
  customer_context
  business_context
  retrieved_memories
  extracted_facts
  fact_conflicts
  confidence_report
  refresh_plan
  pending_review
  applied_updates
  execution_steps
  errors

OutputState
  user_summary
  updated_sections
  evidence_refs
  next_action
  visible_trace
```

其中：

- `trigger_event` 是业务事件入口
- `retrieved_memories` 来自 LangGraph store 和向量检索
- `extracted_facts` 是 LLM 结构化抽取结果
- `refresh_plan` 是图根据事实、置信度、业务规则生成的更新计划
- `pending_review` 是 interrupt 的用户确认载荷
- `visible_trace` 是给 Web / IM 展示的中文执行过程

状态更新规则：

- `execution_steps`、`extracted_facts`、`errors` 使用追加 reducer
- `customer_context`、`business_context` 使用覆盖更新
- `refresh_plan`、`confidence_report` 使用单次决策覆盖
- `messages` 如需要保留对话上下文，使用消息专用 reducer

## 5. 业务触发架构

统一定义 `CustomerIntelligenceEvent`，所有客户相关业务事件都进入客户智能图处理。

触发来源包括：

- 客户创建
- 线索转客户
- 新增跟进记录
- 修改跟进记录
- 创建商机
- 修改商机
- 商机阶段推进
- 商机赢单
- 商机输单
- 合同创建
- 合同审批通过
- 合同签署
- 回款计划创建
- 回款到账
- 回款逾期
- 新增联系人
- 修改联系人角色
- 业务流程节点完成
- 用户手动刷新客户档案
- Agent 对话中识别到客户关键信息

业务模块不直接各自更新客户档案，而是统一发事件，由客户智能图判断如何更新。

## 6. 技术架构

整体技术链路：

```text
业务系统
  ↓
Domain Event / Business Flow Event
  ↓
Customer Intelligence Event Bus
  ↓
Customer Intelligence LangGraph
  ↓
结构化数据查询
  ↓
向量检索
  ↓
LLM 结构化抽取
  ↓
客户事实库
  ↓
客户档案 / 客户概况 / Agent Memory
```

运行时数据边界：

```text
业务数据库
  保存客户、商机、合同、回款、业务流程等确定状态

LangGraph Checkpointer
  保存一次图执行的 thread state、interrupt 等待点、恢复位置、失败恢复状态

LangGraph Store
  保存跨会话可复用的客户长期记忆索引、阶段性摘要和偏好
  推荐使用 MySQL-backed Store，不额外引入新的 Store 数据库

Qdrant
  保存跟进、流程、摘要、证据文本的 embedding，用于语义召回

审计表
  保存客户智能事件、执行 run、用户确认、最终写入结果
```

关键边界：

- Checkpoint 不是业务数据表，不作为客户档案最终展示来源
- Store 不是强业务事实来源，只保存 Agent 长期记忆和检索索引
- 向量库不是业务状态来源，只负责语义召回
- 客户档案页面优先展示业务库和客户事实库中的稳定结果
- Agent 回答时可以结合结构化事实、store 摘要和向量证据

建议新增模块：

```text
app/services/agent/customer_intelligence_graph.py
app/services/agent/customer_memory_state.py
app/services/customer_intelligence_event_service.py
app/services/customer_fact_service.py
app/services/customer_vector_memory_service.py
app/services/customer_profile_refresh_service.py
app/services/customer_intelligence_trace_service.py
app/services/customer_qdrant_index_service.py
app/services/customer_memory_store_service.py
```

建议新增 Agent runtime 支撑模块：

```text
app/services/agent/customer_intelligence_state.py
app/services/agent/customer_intelligence_nodes.py
app/services/agent/customer_intelligence_edges.py
app/services/agent/customer_intelligence_store.py
app/services/agent/customer_intelligence_stream.py
app/services/agent/customer_intelligence_interrupts.py
```

模块职责：

- `customer_intelligence_state.py`
  - 定义 InputState、InternalState、OutputState、reducer 和 runtime context
- `customer_intelligence_nodes.py`
  - 实现图节点，节点只返回状态更新或 Command
- `customer_intelligence_edges.py`
  - 实现条件分支和路由规则
- `customer_intelligence_store.py`
  - 封装 LangGraph store 的 namespace、读写和召回
- `customer_intelligence_stream.py`
  - 将 graph updates/subgraphs/messages 转成用户可读执行过程
- `customer_intelligence_interrupts.py`
  - 定义确认、改写、选择、补充信息等 interrupt payload
- `customer_qdrant_index_service.py`
  - 封装 Qdrant collection、payload、upsert、delete、filter search
- `customer_memory_store_service.py`
  - 实现 LangGraph Store 的 MySQL-backed 读写适配

建议新增数据表：

```text
customer_facts
customer_fact_sources
customer_profile_snapshots
customer_intelligence_events
customer_vector_documents
customer_intelligence_runs
agent_memory_entries
```

表职责：

- `customer_facts`
  - 保存结构化客户事实
- `customer_fact_sources`
  - 绑定事实来源证据
- `customer_profile_snapshots`
  - 保存每次档案生成后的快照
- `customer_intelligence_events`
  - 保存触发事件
- `customer_vector_documents`
  - 保存向量化内容索引元数据
- `customer_intelligence_runs`
  - 保存客户智能图执行记录
- `agent_memory_entries`
  - 保存 LangGraph Store 长期记忆内容

## 7. LangGraph 使用方式

客户智能流程需要充分使用 LangGraph 的核心能力。

### 7.1 StateGraph

客户智能流程不写成一条长 service，而是拆成多个明确节点：

- 收集上下文
- 检索知识
- 抽取事实
- 合并事实
- 判断冲突
- 判断更新范围
- 用户确认
- 写入结果
- 输出轨迹

图结构建议：

```text
START
  ↓
normalize_trigger
  ↓
load_context
  ↓
retrieve_memory
  ↓
extract_facts
  ↓
merge_facts
  ↓
score_confidence
  ↓
plan_refresh
  ↓
route_refresh
  ├─ skip
  ├─ write_memory_only
  ├─ refresh_dynamic_brief
  ├─ refresh_base_profile
  └─ request_review
        ↓
      apply_resume
  ↓
persist_results
  ↓
emit_trace
  ↓
END
```

### 7.2 Conditional Edge

根据不同场景走不同分支：

- 只写知识库
- 刷新销售概况
- 刷新基础档案
- 触发人工确认
- 跳过低价值事件
- 延迟批量更新
- 全量重建

条件分支不只根据事件类型判断，还要结合：

- 业务对象是否明确
- 证据是否足够
- 是否命中历史客户记忆
- 是否存在新旧事实冲突
- 是否涉及基础档案稳定字段
- 更新影响范围是否较大
- 置信度是否达到自动执行阈值

### 7.2.1 Command 路由

客户智能图里的动态决策优先使用 `Command` 表达。

适用场景：

- 节点分析后需要同时更新 state 并决定下一个节点
- LLM 结构化判断后进入不同业务分支
- interrupt 恢复后根据用户选择继续写入、改写、跳过或重新分析
- 后台事件根据风险等级转同步更新、异步重建或人工复核

典型路由：

```text
score_confidence
  ├─ Command(update=confidence_report, goto=plan_refresh)
  ├─ Command(update=confidence_report, goto=request_review)
  └─ Command(update=confidence_report, goto=skip_low_value)

apply_resume
  ├─ Command(update=user_review, goto=persist_results)
  ├─ Command(update=user_review, goto=revise_summary)
  └─ Command(update=user_review, goto=cancel_update)
```

约束：

- 同一个节点的分支意图只保留一种表达方式
- 能用静态边清楚表达的固定流程使用 edge
- 需要根据运行时判断跳转的流程使用 `Command`
- `Command` 的 `goto` 目标必须是白名单节点，不能由 LLM 自由生成
- `Command` 的 `update` 必须符合 typed state schema

这样做的目的不是增加复杂度，而是让“分析后走哪个业务分支”成为图运行时的一部分，避免散落在 service 里的隐式 if/else。

### 7.3 Checkpoint

客户智能图需要支持可恢复执行。

典型场景：

- LLM 抽取完成，但写入失败
- 已经检索完上下文，但摘要生成失败
- 用户确认前流程暂停
- 用户确认后从中断点继续

checkpoint 设计：

- Web 对话使用 `thread_id = agent_session_id`
- IM 对话使用 `thread_id = im_channel + im_user_id + conversation_id`
- 后台业务事件使用 `thread_id = customer_intelligence_event_id`
- 同一客户的异步刷新使用 `customer_id + refresh_batch_id`
- 子图默认继承父图 checkpointer
- 需要跨多轮保持状态的客户智能子图才启用 per-thread subgraph checkpoint
- 纯函数式分析子图使用 per-invocation checkpoint，避免同一子图多次调用产生状态污染

### 7.4 Interrupt / Resume

只有在需要人工判断时才打断用户：

- 低置信度更新
- 多个客户 / 商机 / 合同无法确定
- 新旧事实冲突
- 要覆盖稳定字段
- 高影响业务建议

用户确认后，图从 checkpoint 继续运行。

interrupt 设计规则：

- interrupt payload 必须是 JSON 可序列化对象
- payload 只包含用户能看懂的信息，不包含工具名、表名、内部 ID
- 同一个节点里的 interrupt 顺序必须稳定
- interrupt 之前的副作用必须可幂等重放
- 涉及写库的节点不要在同一个节点里先写库再 interrupt
- 用户确认后使用 `Command(resume=...)` 恢复
- resume 内容进入 `apply_resume` 节点做结构化校验

典型 interrupt 类型：

```text
confirm_update
  确认是否更新客户档案或销售概况

review_and_edit
  让用户改写即将写入的摘要

choose_target
  多个客户、商机、合同候选无法可靠判断时让用户选择

provide_missing_info
  关键信息缺失时补充
```

### 7.5 Subgraph

客户智能子图需要被多个业务流程复用：

- 跟进记录子图
- 商机子图
- 合同子图
- 回款子图
- IM Agent
- Web Agent

子图拆分：

```text
customer_context_subgraph
  读取客户、联系人、商机、合同、回款、流程事件

customer_memory_retrieval_subgraph
  读取 LangGraph store 和向量库证据

customer_fact_extraction_subgraph
  LLM 结构化抽取事实

customer_fact_resolution_subgraph
  合并、去重、冲突判断、置信度评估

customer_profile_refresh_subgraph
  局部刷新或全量重建客户档案

customer_review_subgraph
  处理用户确认、改写、选择、补充信息
```

这几个子图后续也可以被商机推进、合同风险、回款预测等能力复用。

### 7.6 Tool Calling

LLM 不能直接改数据库。

它只能通过受控工具：

- 查询客户上下文
- 查询业务对象
- 写入客户事实
- 刷新客户档案
- 创建更新事件
- 输出执行轨迹

工具设计原则：

- 工具入参必须是业务语义字段，不要求用户提供内部 ID
- 候选对象解析由 resource resolution / customer intelligence 子图完成
- 写工具必须带幂等键
- 写工具必须返回业务结果和用户可读摘要
- 工具错误要写入 state 的 `errors`，由图决定重试、降级或中断
- 所有工具调用都要进入审计记录和 execution trace

### 7.7 Execution Trace

每次客户智能更新都要输出用户能看懂的执行过程：

```text
读取客户上下文
分析跟进内容
识别采购进展
更新客户知识
刷新客户概况
```

不要暴露技术名，比如 `create_customer_activity`、`customer_intelligence_graph`。

执行过程需要使用 graph streaming 实时输出，而不是流程结束后一次性拼接。

Web / IM 端消费规则：

- 使用 `updates` 展示节点级进度
- 使用 `messages` 展示 LLM 生成内容
- 使用 `subgraphs=True` 保留子图内关键步骤
- 只投影白名单步骤，屏蔽内部技术节点
- interrupt 出现时立即展示待确认卡片或 IM 确认消息
- resume 后继续追加后续步骤，不能新开一段割裂的流程

推荐中文步骤映射：

```text
normalize_trigger -> 理解触发来源
load_context -> 读取客户上下文
retrieve_memory -> 检索客户历史信息
extract_facts -> 分析客户关键信息
merge_facts -> 合并客户知识
score_confidence -> 评估更新可信度
plan_refresh -> 制定档案更新计划
persist_results -> 保存客户档案更新
emit_trace -> 整理执行结果
```

事件流实现要求：

- 新前台入口优先消费 `stream_events`
- 需要展示 LLM 生成过程时消费 message 事件
- 需要展示图状态变化时消费 update / value 事件
- 需要展示子图过程时开启 subgraph 事件
- interrupt 事件必须被即时投影为确认、选择、补充、改写等业务卡片
- 后台任务不需要实时展示，但必须记录同等粒度的 trace 供诊断

用户侧只展示业务动作，不展示：

- Python 模块名
- graph 节点名
- tool 名
- 数据表名
- 内部 ID
- LLM 原始 JSON
- checkpoint / thread / namespace 等运行时术语

### 7.8 Runtime Context

图调用必须传入 runtime context，用于隔离租户、权限、入口和版本。

```text
tenant_id
user_id
channel
agent_session_id
conversation_id
permissions
locale
timezone
graph_version
request_id
```

节点通过 runtime context 获取调用身份、权限、store 和 stream writer。不要把这些运行时信息混入 LLM prompt 或业务字段。

### 7.9 Durable Execution 与重放

客户智能更新可能包含 LLM、检索、数据库写入、用户确认和前端流式展示，必须按可重放方式设计。

要求：

- 每个外部副作用都有幂等键
- 每个写入节点能识别重复执行
- checkpoint 失败时显式返回降级状态
- 失败重试从最近成功 checkpoint 继续
- 后台事件失败可重新排队
- 用户确认超时不丢失图状态
- 运维可根据 thread_id 查看当时 state、候选、判断和错误

生产持久化要求：

- 本地开发可以使用内存 checkpointer
- 测试环境使用可清理的数据库 checkpointer
- 生产环境必须使用数据库持久化 checkpointer
- 生产环境 Store 必须是数据库持久化或等价可靠存储
- graph version 升级需要保留兼容读取策略
- 重放时不能重复创建客户事实、快照、事件和向量文档

### 7.10 Observability 与评估

客户智能档案是长期演进能力，不能只靠线上用户反馈判断好坏。

每次运行需要记录：

- graph name
- graph version
- thread id
- tenant id
- user id
- channel
- trigger event
- input state 摘要
- 每个节点的开始、结束、耗时和错误
- LLM structured output
- tool call 入参摘要和返回摘要
- interrupt payload
- resume payload
- 最终写入结果
- 用户可见 trace

评估样本需要覆盖：

- 新增跟进后轻量更新
- 商机阶段变化后局部刷新
- 合同创建后合作状态刷新
- 回款逾期后风险刷新
- 多事实冲突时触发确认
- 低置信度时不自动覆盖
- 用户在 IM 回复“第一个 / 招标那个 / 张总说的那个”时能恢复并正确解析
- 后台事件失败后可重试且不重复写入

指标：

- 自动更新准确率
- 人工确认触发率
- 低置信度误写率
- 档案更新延迟
- 重试成功率
- 重复写入率
- 用户可见 trace 完整率
- IM / Web 恢复成功率

这些观测数据用于调 prompt、调阈值、调检索、调子图，而不是把问题分散修在各个业务流程里。

## 8. LLM 参与节点

LLM 只参与需要语义判断的节点：

- 从自然语言中抽取客户事实
- 判断事实类型
- 判断客户需求、风险、态度、下一步
- 根据候选业务对象做语义匹配
- 归纳客户概况
- 生成销售建议
- 判断新旧信息是否冲突
- 评估置信度

LLM 输出必须使用结构化输出协议，不能依赖自由文本解析。

核心 schema：

```text
ExtractedCustomerFact
  fact_type
  content
  source_refs
  confidence
  freshness
  business_impact

CustomerConflict
  field
  previous_value
  new_value
  conflict_reason
  suggested_action

RefreshPlan
  scope
  target_sections
  requires_review
  reason
  confidence

CustomerSummaryDraft
  section
  content
  evidence_refs
  confidence
```

这些结构化结果进入 state，由后续节点判断分支和落库。

LLM 不负责：

- 直接改数据库
- 决定权限
- 绕过业务流程
- 伪造业务状态
- 直接覆盖强结构化字段
- 替代确定性业务规则

## 9. 更新策略

客户档案不能每次事件都全量重生成。

### 9.1 轻量更新

适用于：

- 新增跟进
- IM 中提到客户新信息
- 联系人态度变化
- 下一步计划变化

处理方式：

- 抽取事实
- 写入客户知识
- 局部刷新销售动态层

### 9.2 局部刷新

适用于：

- 商机阶段变化
- 合同状态变化
- 回款状态变化
- 业务流程节点完成

处理方式：

- 更新相关事实
- 刷新采购进展、合作状态、风险、下一步等相关段落

### 9.3 全量重建

适用于：

- 新客户初始化
- 线索转客户
- 用户手动刷新
- 长时间未更新
- 累积变化较多
- 事实冲突较多
- 模型或档案结构升级

### 9.4 防抖与幂等

需要支持：

- 同一客户短时间多个事件合并处理
- 同一业务对象重复事件去重
- 低价值事件只记录，不触发 LLM
- 使用 `customer_id + source_event_id + graph_version` 做幂等键

### 9.5 前台路径与后台路径

客户智能更新分两种运行方式。

前台路径：

- 用户在 Agent 中输入请求
- 图需要快速返回可见进度
- 可以同步完成轻量抽取、候选判断、必要确认
- 大段档案重建可以转后台继续执行

后台路径：

- 业务事件自动触发
- 图以事件为 thread 运行
- 多个事件可以合并成批处理
- 更新完成后写客户档案、客户知识和通知
- 失败时进入重试队列和诊断记录

前台路径重体验，后台路径重稳定。

## 10. 用户体验设计

页面上不暴露技术概念。

客户详情页展示：

```text
客户概况
最近更新：今天 15:20
更新来源：跟进记录、商机阶段变更
```

客户档案内容：

- 客户当前情况
- 当前需求
- 采购进展
- 关键联系人
- 风险点
- 下一步建议
- 相关商机
- 最近重要变化

重要结论支持查看依据：

```text
“客户已进入 POC 阶段”
依据：8月1日跟进记录，张总提到本周开始产品试用。
```

Agent 对话示例：

```text
用户：总结一下这个客户现在什么情况

Agent：
这个客户当前处于试用推进阶段，张总是主要推动人。
目前重点是完成 POC 验证，风险在于预算和招标方式还没有完全明确。
建议下一步确认试用验收标准和预计采购时间。
```

## 11. 与现有功能的关系

现有功能不推倒重来，而是升级归位。

### 11.1 `customer_profile_service.py`

从独立异步生成服务降级为客户智能图里的基础档案刷新引擎。

它只保留 `generate_profile(...)` 这类被图节点调用的业务生成能力，不再负责：

- 自己创建后台任务
- 自己决定何时刷新
- 自己级联触发客户概况
- 自己承担失败重试和运行审计

这些运行时职责统一收归 `CustomerIntelligenceRefreshService`、`CustomerIntelligenceRunService` 和 `CustomerIntelligenceGraphService`。

### 11.2 `customer_brief_service.py`

从客户概况生成服务降级为销售动态摘要刷新引擎。

它只负责根据统一客户智能上下文生成并写入 `customer_brief_markdown`，不再提供图外后台触发入口。客户概况刷新必须由客户智能图的 `refresh_brief_fields` 节点进入。

### 11.3 `deal_journey_service.py`

作为客户智能事件的重要来源。

### 11.4 现有 Agent 架构

增加 `customer_intelligence_graph`，让客户档案进入统一 Agent runtime。

### 11.5 现有业务流程

业务流程不直接写客户档案，而是发客户智能事件，由 Agent 图统一判断和更新。

## 12. 分阶段落地

### 当前已落地的底座

第一轮实现已经完成“统一读取 + 证据沉淀 + 异步同步”的底座，后续 LangGraph 客户智能子图必须基于这些边界继续做，不能再绕开另起一套客户上下文。

已落地模块：

```text
app/services/customer_intelligence_context_service.py
app/services/customer_intelligence_event_service.py
app/services/customer_evidence_builder.py
app/services/customer_fact_extraction_service.py
app/services/customer_fact_service.py
app/services/customer_intelligence_refresh_service.py
app/services/customer_intelligence_run_service.py
app/services/customer_intelligence_trace_service.py
app/services/customer_vector_document_service.py
app/services/customer_vector_sync_service.py
app/services/customer_qdrant_index_service.py
app/services/customer_memory_store_service.py
app/services/agent/customer_intelligence_graph.py
app/services/agent/customer_intelligence_trigger.py
app/tasks/customer_evidence_sync.py
app/tasks/customer_intelligence_refresh_retry.py
app/core/qdrant.py
app/models/agent.py
app/models/customer_fact.py
app/models/customer_vector_document.py
app/models/customer_intelligence_run.py
```

已落地的数据边界：

- `CustomerIntelligenceContextService`
  - 作为客户智能统一读侧
  - 从 MySQL 读取客户、联系人、商机、合同、回款、跟进、同业客户等强业务事实
  - 从 Qdrant 召回客户级语义证据
  - 输出 `strong_context`、`semantic_evidence`、`retrieval`
  - 明确 `strong_context` 是业务事实，`semantic_evidence` 只做可引用证据和语义线索
- `CustomerIntelligenceEventService`
  - 作为客户智能统一事件入口
  - 把客户创建、线索转客户、客户跟进、联系人变化、客户档案、客户概况、业务流程事件、手动刷新、批量重建、Agent 客户问答标准化为 `CustomerIntelligenceEvent`
  - 输出稳定 `event_key` 和 `thread_id`，供 LangGraph checkpoint、重试、审计和幂等使用
  - 事件 payload 只承载业务语义，不要求用户或 IM 输入内部 ID
- `CustomerIntelligenceGraphService`
  - 作为客户智能 LangGraph runtime 主干
  - 使用 `StateGraph`、typed state、reducer、conditional edge、checkpoint 和 checkpoint fallback
  - 当前已完成节点：事件标准化、客户上下文读取、长期记忆读取、刷新计划、LLM 事实提炼、事实复核、`interrupt()` 人工确认、客户事实沉淀、客户档案刷新、客户概况刷新、长期记忆写入、用户可见 trace
  - 已接入 `astream(..., stream_mode="updates")`，图内节点完成后实时投影 `visible_trace`，不再等整张图结束后批量补发执行过程
  - 需复核事实会在图内暂停，用户确认后通过 `Command(resume=...)` 回到同一个客户智能图继续沉淀或跳过
  - LLM 输出候选事实后，图内会调用确定性事实融合评估，把候选事实和 `strong_context.customer_facts` 中的当前强事实对齐；冲突、低置信或 LLM 标记复核的候选进入 HITL，不让 LLM 直接覆盖既有客户知识
  - 用户采纳、驳回或取消事实复核后，图恢复并继续同一条执行链；采纳会写客户事实和审核审计，驳回 / 取消只写审核审计，不写客户事实
  - LLM 事实提炼失败时降级继续写客户记忆，不阻断 CRM 主业务事件
  - 手动刷新、客户生命周期刷新、联系人变化、业务流程刷新、批量重建和后台重试都通过同一张客户智能图进入，不能绕开图写散点 service
- `AgentRootRuntime`
  - 作为 Web / IM 共用的 Agent 运行时入口
  - 已接入 `customer_intelligence_graph` 业务子图分支
  - 客户智能子图产生的审核中断会投影为 root `current_interrupt`
  - 用户确认、拒绝或取消后，root 使用同一套 `resume_interrupt(...)` 入口恢复，再路由回客户智能子图
  - root 优先消费客户智能子图 streaming contract，并把 `visible_trace` 投影为用户可读执行步骤，避免前端直出内部节点名和工具名
- `CustomerIntelligenceTraceService`
  - 统一负责客户智能 `visible_trace` 到 Web / IM `agent_step` 的用户可见投影
  - 客户智能图 streaming、root runtime 批量 fallback、后台 run 诊断后续都复用这一层，避免展示规则散落
- `CustomerFactExtractionService`
  - 作为 LLM 结构化事实提炼边界
  - 基于 `CustomerIntelligenceEvent`、统一客户上下文、LangGraph Store 长期记忆生成候选事实
  - 输出 `upsert` / `review` / `ignore` 三类动作，不直接写业务表
  - 使用 LangChain structured output，失败时才降级到 JSON object 兼容路径
- `CustomerMemoryStoreService`
  - 作为 MySQL-backed LangGraph Store 适配层
  - 实现 LangGraph `BaseStore` 的 `batch` / `abatch` / `get` / `put` / `search` / `delete` / `list_namespaces` contract
  - 使用客户级 namespace 保存 `facts`、`summaries`、`preferences`、`retrieval`
  - Store 只保存长期摘要、偏好、事实引用和证据引用，不复制 MySQL 强业务事实或 Qdrant 证据全文
- `CustomerFactService`
  - 作为客户智能事实库写入和读取边界
  - 使用 `customer_facts` 保存当前可用的结构化客户知识
  - 使用 `customer_fact_sources` 绑定来源业务对象和证据引用
  - 使用 `customer_fact_revisions` 保存事实创建和更新的版本审计
  - 使用 `customer_fact_review_audits` 保存人工采纳、驳回、取消候选事实的持久审计，覆盖未落库的被驳回候选
  - 支持幂等 upsert、来源绑定、版本递增、修订记录、候选事实融合评估、人工审核审计、上下文 payload 投影
  - 重复写入同一事实内容只补来源，不制造新的事实版本
  - 事实库是客户知识层，不直接等同于客户、商机、合同、回款主业务表
- `CustomerIntelligenceRunService`
  - 作为客户智能 graph 后台运行审计、同步事件入队和失败补偿边界
  - 使用 `customer_intelligence_runs` 记录每次客户智能刷新请求、事件快照、运行状态、尝试次数、最大尝试次数、下次重试时间、route、结果摘要和用户可见 trace
  - 页面手动刷新、批量重建、客户创建、线索转客户等后台 run 在进入 graph 前标记 `RUNNING`，成功后标记 `SUCCESS`，失败后标记 `RETRY_PENDING` 或 `FAILED`
  - 同步业务事务内产生的客户智能事件先落为 `PENDING` run，事务提交后由后台调度器读取并进入同一套 `CustomerIntelligenceGraphService`
  - `CustomerIntelligenceRefreshService.run_due_retries(...)` 可以从审计表中读取 `PENDING` 和到期的 `RETRY_PENDING` run，重建请求并重新进入同一套 `CustomerIntelligenceGraphService`
  - 已提供团队隔离的运行诊断查询、单 run 详情和到期重试调度入口，后台排查复用同一份 `visible_trace`
  - 运行审计只保存事件快照、结果摘要和可见轨迹，不替代 LangGraph checkpoint，不保存无界 graph state
- `CustomerIntelligenceRefreshService`
  - 作为页面、后台、业务服务触发客户智能图的统一调度边界
  - 手动刷新、客户生命周期刷新、批量重建、已提交业务事件都通过这里进入 `CustomerIntelligenceGraphService`
  - 已提交业务事件使用 `trigger_committed_event_refresh(...)`，API 层只负责权限校验和业务写库，不直接编排 LangGraph 节点
  - 同步业务事件使用 `enqueue_committed_event_refresh(...)`，只在当前业务事务内创建幂等 `PENDING` run，不直接启动异步任务，避免 graph 早于业务事务提交运行
- 商机、合同、回款计划、回款记录、开票抬头、发票申请、部署信息、License 申请这类普通页面 CRUD 变更使用 `trigger_business_object_change_refresh(...)` 或同步安全的 `enqueue_business_object_change_refresh(...)` 生成通用业务对象变更事件，再进入同一套 committed-event 调度入口
  - 后台待运行和失败重试都从 `customer_intelligence_runs.event_json` 恢复原始 `CustomerIntelligenceEvent`，不会把联系人、跟进、业务流程事件退化成手动刷新
- `CustomerBusinessObjectIntelligenceService`
- 作为商机、合同、回款计划、回款记录、开票抬头、发票申请、部署信息、License 申请直接 CRUD 的客户智能触发边界
  - API 层只在业务写入成功后发布对象类型、业务对象、变更类型和操作者，不再各自拼客户智能快照
  - 服务层通过类型化 `CustomerBusinessObjectIntelligenceSpec` 统一解析客户 ID、对象名、安全 payload 和业务可读摘要
  - 删除场景必须在删除前保留业务对象，删除成功后再投递快照事件，不能在提交后继续依赖已删除 ORM 对象读取客户上下文
  - API 层不拼接 graph 节点、不写 Qdrant、不暴露内部 ID 给用户；开票抬头、部署地址、License 授权码等敏感资料只传摘要和布尔完整性信息，强业务明细仍以 MySQL 权限查询为准
  - 服务统一生成业务可读摘要，例如“商机已更新”“合同已删除”“回款计划已更新”，并交给 `CustomerIntelligenceRefreshService`
  - 后续新增合同附件、实施交付、回款异常、第三方同步等客户相关业务对象时，只扩展同一个 spec registry，不能在 API / CRUD 中重新散落拼事件逻辑
- `CustomerApprovalIntelligenceService`
  - 作为通用审批引擎到客户智能刷新之间的旁路触发边界
  - 当前接入发票申请、License 申请的审批通过、驳回、撤回和多级审批流转
  - 审批主流程成功后再入队客户智能刷新；刷新入队失败只记录日志并回滚刷新副作用，不反向阻断审批结果
  - 只传审批状态、审批动作和业务对象摘要，不把审批内部节点 ID 或敏感业务内容暴露到用户侧
- `CustomerVectorDocumentService`
  - 作为向量证据元数据写入边界
  - 只写 MySQL 元数据和同步状态，不在业务事务中直接调用 Qdrant
  - 支持 `commit=False`，让业务流程事件可以把证据元数据纳入同一个业务事务
- `CustomerVectorSyncService`
  - 负责把待同步元数据异步写入 Qdrant
  - Qdrant / embedding 故障只影响语义检索，不阻塞 CRM 主业务写入
- `CustomerEvidenceBuilder`
  - 统一把客户活动、客户基础档案、客户概况、业务流程事件转换成可检索证据
  - 使用稳定 `document_key` 和 `qdrant_point_id` 保证幂等 upsert

已接入的业务触发：

- 新建客户后，生成 `customer_created` 事件并进入客户智能图全量刷新客户档案、客户概况和长期记忆
- 线索转客户后，生成 `customer_converted_from_lead` 事件并进入客户智能图全量刷新客户档案、客户概况和长期记忆
- 新增或更新跟进记录后，沉淀客户活动证据
- Agent 创建联系人、页面新增联系人、页面更新联系人、设置主联系人、删除联系人后，都会生成联系人事件并通过 committed-event 调度入口进入客户智能图刷新客户概况和长期记忆
- 页面直接编辑或删除商机、合同、回款计划、回款记录，以及新增、编辑、设置默认或删除开票抬头、发票申请、部署信息、License 申请后，都会通过 `CustomerBusinessObjectIntelligenceService` 统一生成业务对象变更快照，再通过 committed-event 调度入口进入客户智能图刷新客户概况和长期记忆；同步 API 只创建 `PENDING` run，由后台调度进入 LangGraph，避免异步任务抢跑业务事务
- 通用审批引擎完成发票申请、License 申请审批状态变化后，会通过 `CustomerApprovalIntelligenceService` 入队业务对象变更刷新；客户智能刷新失败不阻断审批成功结果
- 客户基础档案生成完成后，沉淀客户档案证据
- 客户概况生成完成后，沉淀客户概况证据
- `DealJourneyService.record_event(...)` 记录商机、合同、回款、审批相关业务流程事件后，先沉淀业务流程证据，再把 `CustomerDealJourneyEvent` 标准化为 `deal_journey_event_recorded` 客户智能事件，并同步入队 `PENDING` run，由后台调度进入客户智能图刷新客户概况、事实库和长期记忆；重复业务流程事件会幂等补齐证据和 run，不重复创建运行记录

已接入的 Agent 运行时触发：

- `CustomerIntelligenceTriggerPolicy`
  - 作为 Web / IM / 后台 Agent 共用的客户智能触发策略
  - 只消费已经结构化的 Agent 运行时事件和已经提交成功的业务写入结果
  - 不通过关键词硬解析原始用户输入，避免 Web、IM、中文表达差异导致触发逻辑分叉
- 新流程 Agent turn
  - 当语义理解输出 `CUSTOMER_QUERY`，且业务上下文已明确加载客户时，生成 `agent_customer_question` 事件
  - 事件进入 root runtime 的 `customer_intelligence_graph` 子图
- 已确认 / 自动执行的业务工具结果
  - 当 `create_customer_activity` 已成功写入数据库后，从真实业务对象重新构造客户智能事件
  - 当建商机、推进商机阶段、创建回款计划、登记回款等 Agent 写工具已产生成交旅程事件后，从 `CustomerDealJourneyEvent` 转成客户智能事件
  - 不信任前端输入或工具返回的临时文本作为最终事实来源
- `AgentRootRuntime`
  - 在 new-flow、确认任务执行、自动执行三条路径中统一调用触发策略
  - 通过 conditional edge 决定是否进入 `customer_intelligence_graph`
  - 客户智能中断、恢复、可见执行轨迹和输出 payload 都从 root runtime 投影，Web 和 IM 不再各维护一套客户档案触发流程

已收拢的读取入口：

- Agent `get_customer_context` 读取统一客户智能上下文
- 客户概况生成读取统一客户智能上下文
- 客户基础档案生成读取统一客户智能上下文
- 客户智能 LangGraph 主干读取统一客户智能上下文
- 客户智能 LangGraph 主干读取和写入客户级长期记忆 Store
- 客户智能 LangGraph 主干通过 LLM 结构化提炼客户事实，并由确定性节点写入客户事实库
- 客户智能 LangGraph 主干在写库前统一做候选事实融合评估
  - 新事实：按候选动作自动沉淀或进入复核
  - 与既有事实内容一致：幂等补来源，不制造新版本
  - 与既有事实冲突：按置信度和候选动作决定自动更新或进入人工复核
  - 复核结果通过 `Command(resume=...)` 回到同一张图继续沉淀、刷新概况和写长期记忆
- 客户智能事实审核通过 root runtime 统一中断 / 恢复，Web 和 IM 不需要各维护一套确认流程
- 统一客户智能上下文读取结构化客户事实和事实来源
- 客户智能 LangGraph 主干已加入客户档案和客户概况刷新写入节点
  - `manual_refresh_requested` 进入 `refresh_profile`：读取上下文 / 记忆 -> 制定计划 -> 提炼事实 -> 必要时人工复核 -> 沉淀事实 -> 刷新客户档案 -> 刷新客户概况 -> 写入长期记忆
  - 跟进记录和业务流程事件进入 `refresh_brief`：读取上下文 / 记忆 -> 制定计划 -> 提炼事实 -> 必要时人工复核 -> 沉淀事实 -> 刷新客户概况 -> 写入长期记忆
  - `CustomerProfileService.generate_profile(...)` 被图内节点调用时只刷新客户基础档案，不再自行异步触发客户概况；客户概况由 graph 显式编排，避免图内 / 图外重复刷新
- 页面客户档案 / 客户概况手动刷新入口已接入 `CustomerIntelligenceRefreshService`
  - 页面接口只做权限校验、状态置为待生成、发出 `manual_refresh_requested` 事件
  - 后台 run 统一进入 `CustomerIntelligenceGraphService`
  - 后台 run 同步写入 `customer_intelligence_runs`，失败后保留 retry metadata，可由补偿入口重放
  - `refresh_scope=full` 刷新客户档案和客户概况；`refresh_scope=brief` 只刷新客户概况和长期记忆
- 客户智能批量重建入口已接入 `CustomerIntelligenceRefreshService`
  - 后台接口 `POST /v1/customers/intelligence/batch-rebuild` 只做权限校验和参数收口
  - `CustomerIntelligenceRefreshService.trigger_batch_rebuild(...)` 选择目标客户、标记待刷新、创建运行审计并调度后台 graph run
  - 每个客户仍复用同一套 `CustomerIntelligenceGraphService`、`CustomerIntelligenceRunService`、失败重试和可见 trace 投影，不另起批处理专用链路
  - API 返回调度结果和 request_id；内部 source object id、数据库 id 只留在服务端审计和事件 payload，不作为用户输入要求
- 客户智能运行诊断入口已接入 `CustomerIntelligenceRunService`
  - `GET /v1/customers/intelligence/runs` 查询当前团队下的客户智能运行记录，可按客户、request、状态过滤
  - `GET /v1/customers/intelligence/runs/{run_id}` 查询单次运行详情和可回放执行轨迹
  - `POST /v1/customers/intelligence/retries/run-due` 只调度当前团队已到期的 retryable run，避免跨团队重试
  - 诊断接口只投影用户可读 trace、中文运行类型、结果摘要和错误信息，不把 LangGraph checkpoint state 或内部 graph route 作为业务 API 暴露
- 客户创建 / 线索转客户 / AI 解析创建客户入口已接入 `CustomerIntelligenceRefreshService`
  - API 和 AI parser 只负责完成客户主数据写入并发出客户生命周期刷新请求
  - 后台 run 统一进入 `CustomerIntelligenceGraphService`
  - 客户生命周期 run 使用同一套运行审计和失败补偿，不再只依赖日志排查
  - `customer_created` 和 `customer_converted_from_lead` 都进入 `refresh_profile`，由图内节点刷新客户档案、客户概况和长期记忆

当前实现约束：

- Qdrant 中只放可检索证据，不放商机阶段、合同状态、回款金额等强业务事实
- 页面最终展示字段仍来自 MySQL 客户档案 / 客户概况字段
- 页面客户档案 / 客户概况字段的刷新由 `CustomerIntelligenceGraphService` 编排，生成服务只保留确定性写库职责
- Agent 回答客户问题时必须优先引用 `strong_context`
- Store 不是强业务事实源，不能直接覆盖商机、合同、回款、客户主数据
- 客户事实库保存 Agent 可复用的客户知识，不替代商机阶段、合同状态、回款金额等业务状态
- 语义证据检索失败时返回降级状态，不让客户档案、概况、业务流程失败
- 业务流程事件是多点触发的当前中心入口，后续新增触发点优先接入业务事件 / 客户智能事件，不直接在 CRUD 中散落调用 LLM

下一阶段不能做的事：

- 不能在商机、合同、回款 CRUD 中直接写 Qdrant
- 不能让 LLM 自由文本结果直接覆盖客户强业务字段
- 不能把客户长期记忆继续塞进会话上下文
- 不能让 Web 和 IM 各维护一套客户档案逻辑
- 不能把工具名、节点名、内部 ID 暴露给用户作为执行过程

下一阶段应继续补齐：

- `customer_intelligence_event_service.py`：新增业务入口时继续优先发统一客户智能事件，不能在入口处直接编排 LLM、Qdrant 或客户档案生成服务
- `customer_fact_service.py`：继续补齐更强的语义冲突评估、事实合并策略和复核后台查询能力
- `customer_intelligence_trace_service.py`：继续保持 Web / IM / 后台 run 诊断共用同一套 trace 投影规则
- 业务流程触发面：继续排查批量导入、数据修复、第三方同步等非交互路径，避免绕过事件入口；联系人、商机、合同、回款计划、回款记录、开票抬头、发票申请、部署信息、License 申请页面直接 CRUD 已接入 committed-event 入口
- 后台刷新入口：定时补偿调度已接到 `CustomerIntelligenceRefreshService.run_due_retries(...)`，同时处理同步业务事件产生的 `PENDING` run 和失败后到期的 `RETRY_PENDING` run；批量重建已接到 `CustomerIntelligenceRefreshService.trigger_batch_rebuild(...)`

### 当前代码落地顺序

后续实现按下面顺序推进，避免先做页面或 prompt 调优导致架构再次发散。前 7 项已作为当前底座落地：事实冲突融合、人工确认、采纳 / 驳回审计、事实沉淀、客户档案刷新节点、客户概况刷新节点、后台运行审计、retryable 失败补偿入口、批量重建入口、客户智能图实时 streaming trace、后台 trace 统一投影、运行诊断接口和团队隔离的重试调度入口都已接入。后续扩展重点转为更完整的业务触发面和事实语义合并质量：

```text
1. CustomerIntelligenceEvent 标准化入口
2. CustomerIntelligenceGraph typed state / subgraph / streaming
3. LangGraph Store MySQL-backed 长期记忆
4. CustomerFact / FactSource 事实库
5. LLM 结构化事实提炼节点并入 CustomerIntelligenceGraph
6. 事实冲突融合、人工确认、客户档案和客户概况刷新节点并入 graph
7. Web / IM 统一消费 visible trace、interrupt 和 customer intelligence payload
```

### 第一阶段：统一入口

目标：

- 把客户档案生成、客户概况生成收拢到 Agent 的客户智能子图
- 先复用现有字段和服务能力
- 让 Agent 成为客户档案更新的统一入口

交付：

- `Customer Intelligence Graph`
- 客户档案刷新工具
- 客户概况刷新工具
- Agent 执行轨迹统一展示

### 第二阶段：建设客户事实库

目标：

- 新增客户事实、来源、快照、事件表
- 让客户档案从“生成文本”变成“基于证据的客户记忆”

交付：

- `customer_facts`
- `customer_fact_sources`
- `customer_profile_snapshots`
- `customer_intelligence_events`
- 事实合并与冲突判断逻辑

### 第三阶段：接入多点触发

目标：

- 接入跟进、商机、合同、回款、联系人、业务流程事件
- 形成自动更新机制

交付：

- 跟进触发：已接入客户活动事件和 Agent 跟进写入结果触发
- 商机触发：已通过成交旅程事件和 Agent 商机工具结果触发
- 合同触发：已通过成交旅程事件和 Agent 合同工具结果触发
- 回款触发：已通过成交旅程事件和 Agent 回款工具结果触发
- 联系人触发：已接入 Agent 写入、页面新增、页面更新、设置主联系人、页面删除后的联系人事件触发
- 业务流程触发：已接入 `DealJourneyService.record_event(...)` 统一业务流程事件触发；同步事务内只创建客户智能 `PENDING` run，后台调度在事务提交后进入 LangGraph
- 直接 CRUD 触发：商机编辑 / 删除、合同编辑 / 删除、回款计划编辑 / 删除、回款记录编辑 / 删除、开票抬头新增 / 编辑 / 设默认 / 删除、发票申请新增 / 编辑 / 删除 / 标记已开票、部署信息新增 / 编辑 / 设默认 / 删除、License 申请新增 / 编辑 / 删除 / 提交 / 发放已通过 `CustomerBusinessObjectIntelligenceService` 接入通用业务对象变更快照事件；删除场景不依赖删除后的 ORM 对象恢复上下文
- 审批状态触发：发票申请和 License 申请的通用审批流转已通过 `CustomerApprovalIntelligenceService` 接入客户智能刷新，审批写入成功后触发，刷新失败不阻断审批主流程

继续补齐：

- 对批量导入、数据修复、第三方同步这类非交互路径，统一发 `CustomerIntelligenceEvent`，不要直接调用 LLM 或 Qdrant
- 为后台运营继续补充更细的失败处理动作，例如指定 request 或指定客户的重放入口，复用 `customer_intelligence_runs` 和 `visible_trace`

### 第四阶段：接入向量检索

目标：

- 把跟进原文、业务事件摘要、历史客户总结向量化
- 支撑 Agent 问答、归纳和上下文补全
- 使用 Qdrant 建设客户级语义证据库

交付：

- Qdrant collection：`crm_customer_evidence`
- Qdrant payload filter：租户、团队、客户、来源、业务对象、时间范围
- 客户向量文档索引
- 客户级语义检索工具
- 业务事件到向量文档的增量同步
- 向量文档删除 / 重建 / 幂等 upsert
- RAG 上下文组装
- 证据引用能力

### 第四点五阶段：接入 LangGraph Store 持久化

目标：

- 把客户长期记忆从会话上下文中独立出来
- Web、IM、后台事件共享同一套客户级 Agent 记忆
- 不新增独立 Store 数据库，优先使用 MySQL-backed Store

交付：

- `agent_memory_entries`
- `customer_memory_store_service.py`
- LangGraph Store namespace 规范
- 客户摘要、客户偏好、事实索引、检索索引读写能力
- Store 与 Qdrant / 客户事实库之间的引用关系

### 第五阶段：优化前端体验

目标：

- 让用户看到可信、自然、可解释的客户档案

交付：

- 更新时间
- 更新来源
- 引用依据
- 冲突确认
- 手动刷新
- 执行轨迹展示

## 13. 最终形态

最终客户档案模块会变成：

```text
业务动作发生
  ↓
Agent 自动理解
  ↓
沉淀客户知识
  ↓
更新客户档案
  ↓
支撑销售问答
  ↓
反哺商机、合同、回款、流程推进
```

客户档案不再是一个孤立页面，而是整个 CRM Agent 的客户记忆底座。

这套架构会同时提升：

- 客户档案质量
- Agent 理解能力
- 商机推进准确性
- 销售建议质量
- IM 端问答体验
- 业务流程自动化能力

## 14. 官方能力依据

本方案对齐的 LangGraph 能力：

- Overview
  - LangGraph 是低层编排框架和长期运行 Agent runtime，适合确定性步骤和 Agent 步骤混合的复杂流程
- Graph API
  - 使用 `StateGraph`、typed state、reducers、conditional edges、`Command` 和 runtime context
- Persistence
  - 使用 checkpointer 保存 thread 内短期状态、中断点和恢复上下文
- Memory
  - 使用 store 保存跨 thread 的长期记忆
- Interrupts
  - 使用 `interrupt()` 暂停图，通过 `Command(resume=...)` 恢复
  - interrupt payload 保持 JSON 可序列化，中断前副作用必须可重放
- Streaming
  - 使用事件流把节点进度、LLM 输出、子图过程和 interrupt 投影给 Web / IM
- Subgraphs
  - 使用子图复用客户上下文、记忆检索、事实抽取、事实融合和档案刷新能力

官方文档：

- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/add-memory
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/streaming
- https://docs.langchain.com/oss/python/langgraph/use-subgraphs

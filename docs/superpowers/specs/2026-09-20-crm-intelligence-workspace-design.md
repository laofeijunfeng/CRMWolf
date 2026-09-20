# CRM Intelligence Workspace：独立多 CRM 数据分析与报告 Agent

- 日期：2026-09-20
- 状态：产品设计已确认，待实施规划
- 产品形态：独立多租户 SaaS；CRMWolf、Salesforce、HubSpot 为首批连接器
- 核心用户：销售管理者与企业老板；销售运营与 RevOps
- 数据策略：源 CRM 为业务事实源；平台保存可重建的托管分析副本、历史事实、配置和分析产物
- 行动边界：第一版只读分析、诊断、报告、监控与建议，不修改源 CRM
- 默认体验：CRM Intelligence Workspace，即主动经营情报首页 + 任务型 Agent 分析空间
- 参考产品：火山引擎 Data Agent / iDA 的数据接入、语义层、智能问数、深度研究、Artifact、定时任务、权限、审计、评测和开放集成体系
- 与 CRMWolf 的关系：独立产品；CRMWolf 是首个原生连接器及接入方，不与 CRMWolf 事务型 Agent 共用运行时

## 1. 背景与机会

通用企业 Data Agent 已经证明一条可行产品链路：连接企业数据与知识，通过自然语言完成查询、分析、研究和报告，再用权限、审计、评测和开放接口支撑企业部署。火山引擎 Data Agent / iDA 的核心价值不是单个大模型，而是把数据接入、语义治理、智能问数、深度研究、交付物、定时任务和企业治理组织成完整平台。

通用平台的主要缺点是客户需要自行完成大量建设：识别 CRM 对象、映射字段、定义销售漏斗、维护指标口径、配置分析方法、准备报告模板并建立评测集。CRM 场景具有高度稳定的核心对象、指标和诊断方法，可以把这部分专业能力提前产品化。

本产品的机会是：

1. 用统一 CRM 领域模型连接不同 CRM，屏蔽 Salesforce、HubSpot、CRMWolf 及后续自研 CRM 的对象和字段差异。
2. 预置销售经营指标、漏斗定义、诊断树和管理报告模板，降低客户从零建设数据智能体的成本。
3. 把传统 BI 的固定看板推进为“主动发现问题 → 可解释诊断 → 证据清单 → 正式报告 → 周期监控”的经营情报工作空间。
4. 与源 CRM 保持松耦合：源 CRM 继续负责业务事实、权限、审批和事务；本平台负责分析事实、历史变化、诊断和报告。
5. 通过 OpenAPI、SDK 和安全 iframe 向 CRMWolf 及其他 CRM 提供可嵌入能力，同时保留独立 SaaS 产品体验。

## 2. 一句话定位

> 面向销售管理者、企业老板和 RevOps 的独立 CRM 数据智能平台；连接多个 CRM 后，自动统一业务语义，持续发现经营问题，并交付可验证的数据问答、诊断、报告和建议。

本产品售卖的不是一个通用聊天机器人，而是一套预先产品化的 CRM 数据模型、指标体系、诊断方法、报告模板和 Agent 执行能力。

## 3. 目标用户与职责

### 3.1 销售管理者与企业老板

核心诉求：

- 当前业绩和目标差距是什么。
- 销售漏斗是否健康，风险集中在哪里。
- 经营指标为什么变化，哪些团队、人员、来源、产品或客户贡献最大。
- 哪些客户或商机需要优先关注。
- 本周、本月应向管理层汇报什么。
- 数据结论是否可靠，能否追溯到对象、口径和更新时间。

主要能力：

- 今日经营简报。
- 异常与风险清单。
- 自然语言问数。
- 经营诊断和深度研究。
- 周报、月报和专题报告。
- 周期监控、订阅和推送。
- 从任意指标、异常或报告段落继续追问。

### 3.2 销售运营与 RevOps

核心诉求：

- 快速接入不同 CRM，并知道同步是否可靠。
- 统一不同系统中的客户、商机、阶段、Owner、活动和金额语义。
- 维护业务指标、目标、漏斗和分析口径。
- 控制不同管理者、团队和用户的数据范围。
- 配置报告模板、监控和推送计划。
- 评测 Agent 的准确性、稳定性、延迟和成本。

主要能力：

- CRM 连接和同步运维。
- 字段、Pipeline、Stage、币种、时区和组织映射。
- 数据质量管理。
- 指标目录和版本管理。
- 诊断框架及报告模板配置。
- 权限、审计、评测和配置发布。

## 4. 核心产品原则

1. **源 CRM 是业务事实源。** 分析副本可重建，不取代 CRM 中的正式客户、商机、合同或回款事实。
2. **第一版只读。** 平台输出数据、诊断、报告和建议，不写回 CRMWolf、Salesforce 或 HubSpot。
3. **证据优先。** 每个重要结论都必须绑定指标、查询、对象清单、筛选条件和数据更新时间。
4. **语义闭世界。** Agent 只能使用已注册的指标、维度、关系、诊断框架和权限范围；不能自由猜测数据库字段和业务口径。
5. **模型理解，代码裁决。** 模型理解问题、选择分析框架并组织解释；代码负责权限、SQL、指标公式、聚合、统计、数据质量和成功失败判定。
6. **历史变化是一等事实。** 从第一天保存阶段、金额、Owner、预计成交日期等变化，支持可靠的漏斗和趋势分析。
7. **建设端与消费端分离。** RevOps 建设和发布配置；管理者消费已发布能力。
8. **CRM 垂直优先。** 不做任意行业数据平台，不建设通用 BI 编辑器，不以 Skill 市场作为第一版核心。
9. **跨 CRM 统一但不抹平差异。** 核心分析依赖标准字段，CRM 特有字段保留在扩展区，并允许提升为租户级维度或指标。
10. **权限端到端继承。** 页面、查询、图表、明细、报告、导出、分享和推送都执行同一数据范围策略。

## 5. 范围与非目标

### 5.0 发布阶段术语

- **Phase 1 / 设计伙伴验证版：**仅以 CRMWolf 完成端到端闭环，用于验证独立产品的数据合同、指标、Agent、报告与开放集成；只向受控设计伙伴开放，不对外宣称已经完成多 CRM 第一版。
- **第一版 / V1 GA / 首个正式版本：**必须完成 Phase 1 与 Phase 2，正式支持 CRMWolf、Salesforce、HubSpot，并满足本节第一版范围、第二十六节验收、第二十七节成功标准和第三十节发布门禁。
- **Phase 3：**V1 GA 后的规模化、企业级隔离、高级预测和生态能力。

因此，文档中的“第一版”“首版”和“首个正式版本”均指 V1 GA；Phase 1 只是它的前置验证里程碑。

### 5.1 第一版范围

- 独立多租户 SaaS。
- CRMWolf、Salesforce、HubSpot 三个连接器。
- 托管分析副本。
- 标准 CRM 数据模型。
- 历史事实与快照。
- 20–30 个核心销售经营指标。
- 自然语言问数。
- 六类 CRM 经营诊断。
- 十类标准报告。
- 定时任务、监控和推送。
- RevOps 数据、指标和报告配置后台。
- OpenAPI、JS SDK 和安全 iframe。
- 租户、角色、对象、字段和数据范围权限。
- 审计、评测、用量和配置版本。

### 5.2 第一版非目标

- 不修改源 CRM 数据。
- 不自动创建任务、备注、客户、商机或推进阶段。
- 不开放通用自由 SQL 给最终用户或模型。
- 不支持任意行业数据分析。
- 不提供完整 BI 仪表盘拖拽设计器。
- 不建设开放式通用 Skill 市场。
- 不支持所有 CRM 的私有对象和全部自定义业务逻辑。
- 不基于客户数据训练跨客户共享模型。
- 不提供跨租户行业基准，除非后续取得单独授权并完成不可逆匿名化。
- 不面向不特定公众提供通用生成式 AI 服务。

## 6. 方案选择

采用：**CRM Intelligence Workspace + 托管分析副本 + Canonical CRM Model + 受控 Agent 执行层。**

放弃：

1. **纯 Agent 工作台。** 完全依赖用户主动提问，管理者不知道该问什么，难以形成稳定日常价值。
2. **传统驾驶舱 + AI 侧栏。** 容易退化为 BI 加聊天框，无法发挥任务规划、深度分析、Artifact 和定时执行价值。
3. **首版同时支持托管副本和 Query-in-place。** 两套执行链会放大同步、权限、性能和测试复杂度；大客户原地查询或私有化留到后续。
4. **以 CRMWolf 数据模型直接建设。** 上线快但无法证明多 CRM 产品成立，也会阻碍 Salesforce/HubSpot 映射。
5. **通用 Text-to-SQL。** 无法稳定处理 CRM 指标口径、权限和历史漏斗，也会让模型承担不应承担的数据库裁决。
6. **首版写回 CRM。** 同时适配三套权限、审批、幂等和异常语义，风险超过首版收益。

## 7. 总体架构

```text
外部 CRM
  ├── CRMWolf
  ├── Salesforce
  └── HubSpot
        ↓
CRM Connector Layer
  ├── OAuth / API Token
  ├── 首次全量同步
  ├── Webhook 增量
  ├── 增量轮询兜底
  └── 对账 / 重试 / 死信
        ↓
CRM Data Plane
  ├── Raw Zone
  ├── Canonical CRM Model
  ├── 历史变化事实
  ├── 数据质量
  └── 预聚合指标
        ↓
CRM Intelligence Plane
  ├── 指标与语义目录
  ├── 诊断框架
  ├── Agent Orchestrator
  ├── 确定性查询执行器
  ├── 深度研究执行器
  └── 报告与 Artifact 引擎
        ↓
Delivery Plane
  ├── CRM Intelligence Workspace
  ├── OpenAPI
  ├── JS SDK / Web Component
  ├── 安全 iframe
  └── 邮件 / 飞书 / 钉钉 / Webhook
```

### 7.1 控制平面

控制平面保存平台自己的配置和治理状态：

- 租户、用户、角色、席位和套餐。
- CRM 连接器、授权状态和加密凭证。
- 字段、Stage、Pipeline、币种、时区、Owner、Team 和区域映射。
- 指标、漏斗、目标、诊断框架和报告模板。
- 权限策略和外部用户映射。
- Agent 配置版本、发布、回滚和评测结果。
- 定时任务、监控规则和推送目标。
- 用量、成本和审计。

所有影响分析结果的配置必须版本化。一个已生成报告必须永久记录：

- 数据截止时间。
- 数据快照或证据查询引用。
- 指标目录版本。
- 映射版本。
- 诊断模板版本。
- Agent 配置版本。

### 7.2 数据平面

数据平面只保存从源 CRM 同步来的分析副本和其派生事实，不拥有业务事务真相。

数据分层：

1. **Raw Zone**：保存源对象、源 ID、原字段、源更新时间、同步时间、删除和合并状态。
2. **Canonical Zone**：映射为统一 CRM 对象和字段。
3. **Historical Fact Zone**：保存阶段、金额、Owner、预计成交日期等变化事件。
4. **Metric Zone**：保存高频指标的可重建预聚合结果。
5. **Artifact Zone**：保存任务证据、图表、报告、导出和版本。

### 7.3 智能平面

智能平面禁止模型直接访问生产库或自由生成并执行 SQL。执行链为：

```text
用户目标
→ 闭世界意图识别
→ CRM Semantic Plan
→ 权限与数据质量检查
→ 确定性查询计划
→ SQL / 指标服务执行
→ 结构化证据
→ 诊断 / 研究
→ 解释和报告
```

## 8. Connector 设计

每个 CRM Connector 实现统一合同：

```text
authorize()
discover_schema()
initial_backfill()
pull_changes(cursor)
handle_webhook(event)
reconcile()
revoke()
```

### 8.1 同步策略

- 首次连接执行全量回填。
- 日常以 Webhook 为主，增量轮询为兜底。
- 每日全量对账检查漏事件、删除、合并、归属变更和字段漂移。
- 同步游标持久化并具备幂等。
- 连接器使用指数退避、限流和死信。
- 人工修复映射或凭证后可从游标重放。
- 删除连接时停止同步、撤销令牌，并按租户策略删除或冻结分析副本。

### 8.2 Raw Zone 不变量

每条原始记录至少包含：

```text
tenant_id
source_system
source_connection_id
source_object_type
source_record_id
source_updated_at
synced_at
payload
is_deleted
merge_target_id
```

Raw Zone 的作用是可重放和可重建；Canonical 映射错误不能要求重新访问源 CRM 才能修复。

### 8.3 CRMWolf 首批对象

- 客户、联系人、线索。
- 商机、采购方式、商机阶段。
- 跟进记录、会议纪要、待办。
- 产品。
- 合同。
- 回款计划、回款记录。
- 发票。
- 用户、团队和权限信息。

### 8.4 Salesforce 首批对象

- Account、Contact、Lead。
- Opportunity、OpportunityStage、OpportunityHistory。
- Task、Event。
- User。
- Product、Pricebook。
- Campaign。
- 自定义字段发现和映射。

### 8.5 HubSpot 首批对象

- Company、Contact、Deal。
- Pipeline、Stage。
- Engagement / Activity。
- Owner、Team。
- Product、Line Item。
- Campaign / Source。
- 自定义属性发现和映射。

第一版不承诺 Salesforce Custom Object 和 HubSpot Custom Object 的通用分析；仅允许发现并保存为源扩展，后续再提供正式提升机制。

## 9. Canonical CRM Model

首版标准对象：

```text
Tenant
CRMUser
Team
Account
Contact
Lead
Opportunity
Pipeline
Stage
Activity
Meeting
Email
Call
Task
Product
Quote
Contract
Payment
Invoice
Campaign
AcquisitionSource
Target
Quota
```

每条标准对象必须包含：

```text
tenant_id
canonical_id
source_system
source_connection_id
source_object_type
source_record_id
source_updated_at
synced_at
canonical_fields
source_extensions
```

### 9.1 映射原则

- 核心指标只依赖标准字段。
- 源 CRM 特有字段保存在 `source_extensions`。
- RevOps 可将高价值自定义字段发布为租户级维度或指标输入。
- Stage 映射必须明确 Open、Won、Lost，以及标准漏斗序位。
- 金额必须携带币种；跨币种指标使用租户配置的汇率和折算时间。
- 所有时间保存 UTC，并保留源时区；分析按租户时区计算自然日、周、月和季度。
- 合并、删除和 Owner 变更必须形成可追溯事件。

### 9.2 历史事实

同步时必须生成以下变化事实：

- 商机阶段变更。
- 金额变化。
- 预计成交日期变化。
- Owner 和 Team 变更。
- 赢单、输单和重新打开。
- 活动发生。
- 客户状态变化。
- 合同状态变化。
- 回款计划和回款状态变化。

没有历史事实层，不允许宣称支持：

- 历史漏斗。
- 阶段转化率。
- 阶段停留时间。
- 商机滑期。
- 预测准确率。
- 销售周期变化。

## 10. 指标与语义目录

Agent 只能使用已发布的指标、维度、时间口径、关系路径和诊断框架。

指标定义至少包含：

```text
key
name
description
formula
time_field
default_filters
allowed_dimensions
required_objects
required_fields
owner
version
effective_at
```

示例：

```yaml
key: opportunity_win_rate
name: 商机赢率
formula: won_opportunity_count / closed_opportunity_count
time_field: closed_at
allowed_dimensions:
  - owner
  - team
  - region
  - acquisition_source
  - product
```

任何问数结果必须返回：

- 指标名称和定义。
- 时间范围。
- 筛选条件。
- 对比基准。
- 数据更新时间。
- 样本量或对象数量。
- 证据查询 ID。

## 11. 首版核心指标

### 11.1 经营结果

- 新增客户数。
- 新增线索数。
- 新增商机数。
- 新增 Pipeline 金额。
- 赢单金额。
- 赢率。
- 平均客单价。
- 目标达成率。
- Pipeline Coverage。
- Forecast Commit / Best Case / Pipeline。

### 11.2 漏斗

- 各阶段商机数和金额。
- 阶段转化率。
- 阶段流失率。
- 阶段停留时间。
- 销售周期。
- 商机滑期率。
- 赢单/输单原因。
- Pipeline Aging。

### 11.3 活动与执行

- 跟进覆盖率。
- 客户/商机活动频率。
- 长期未跟进商机。
- 首次响应时间。
- 活动到商机转化。
- 会议到下一阶段转化。
- 每销售人员有效活动数。

### 11.4 结构分析

- 团队和人员表现。
- 区域表现。
- 行业表现。
- 产品表现。
- 来源转化。
- 新老客户贡献。
- 大客户集中度。
- 客户风险分布。

### 11.5 合同与回款

仅在源 CRM 提供相应数据时启用：

- 合同金额。
- 已回款金额。
- 回款完成率。
- 逾期金额。
- 预计回款。
- 开票金额。
- 应收账龄。

## 12. Agent 能力与执行边界

首版闭世界意图：

```text
QUERY_METRIC
COMPARE_SEGMENTS
LIST_OBJECTS
EXPLAIN_CHANGE
DIAGNOSE_FUNNEL
DIAGNOSE_FORECAST
DIAGNOSE_TEAM
DIAGNOSE_CUSTOMER
GENERATE_REPORT
REFINE_REPORT
CREATE_SCHEDULE
EXPLAIN_DEFINITION
```

不支持的请求返回明确能力边界，不允许模型自行发明新工具或扩大查询范围。

### 12.1 模块职责

| 模块 | 职责 |
|---|---|
| Query Planner | 将问题转成标准指标、维度、筛选、时间范围和对比基准 |
| Query Executor | 生成并执行确定性查询，执行权限和成本限制 |
| Diagnostic Engine | 依据 CRM 诊断树计算原因贡献和证据 |
| Research Orchestrator | 规划复杂分析、组合多次查询、管理异步任务和中间发现 |
| Report Composer | 依据结构化证据生成报告章节和图表解释 |

### 12.2 模型与代码分工

模型负责：

- 理解自然语言表达。
- 选择已注册的指标和分析框架。
- 将中间发现组织成解释。
- 根据证据撰写报告。
- 判断是否需要澄清分析范围。

代码负责：

- 租户与权限。
- 指标公式。
- SQL 和指标服务执行。
- 过滤、聚合、排序和统计计算。
- 样本量、显著性和数据质量。
- 对象 ID 和源 CRM 引用。
- 证据绑定。
- 状态机、重试和成功失败判定。

首版不展示模型完整思维链，仅展示业务可审计步骤，例如：

```text
1. 检查新增商机规模
2. 分析阶段转化变化
3. 对比销售周期
4. 定位贡献最大的团队、产品和来源
5. 汇总受影响商机
```

## 13. CRM 诊断框架

### 13.1 业绩达成诊断

```text
目标差距
├── 赢单金额
│   ├── 赢单数量
│   └── 平均客单价
├── Pipeline 供给
│   ├── 新增商机
│   └── 新增金额
├── 转化效率
│   ├── 阶段转化
│   └── 赢率
└── 速度
    ├── 销售周期
    └── 商机滑期
```

### 13.2 漏斗健康诊断

- Pipeline Coverage。
- 阶段结构。
- 阶段积压。
- 阶段流失。
- Pipeline Aging。
- 缺少下一步动作。
- 预计成交日期集中风险。

### 13.3 销售预测诊断

- 历史预测偏差。
- 当前 Pipeline 质量。
- 阶段概率。
- 商机活跃度。
- 滑期模式。
- Owner 偏差。
- 风险调整后的预测区间。

第一版只输出基础预测、风险调整值、置信区间和风险因素，不宣传确定性成交预测。

### 13.4 团队效能诊断

- 新增 Pipeline。
- 赢单结果。
- 赢率。
- 销售周期。
- 活动质量。
- 跟进覆盖。
- 预测准确度。
- 客户集中度。

禁止只使用活动数量评价销售人员；必须结合结果、客户结构和销售阶段。

### 13.5 客户健康诊断

- 最近互动。
- 活动趋势。
- 商机状态。
- 合同与回款。
- 关键联系人覆盖。
- 问题和承诺。
- 风险事件。

### 13.6 来源与产品诊断

- 来源贡献。
- 来源到商机和赢单转化。
- 获客后的销售周期。
- 产品赢率。
- 产品组合。
- 行业与区域适配度。

## 14. 产品信息架构

```text
经营情报
├── 今日概览
├── 异常与风险
└── 推荐分析

分析工作台
├── 新建分析
├── 历史会话
└── 分析模板

报告中心
├── 自动报告
├── 专题报告
├── 已分享
└── 报告模板

监控与订阅
├── 监控规则
├── 定时任务
└── 推送记录

数据管理（RevOps）
├── CRM 连接
├── 数据映射
├── 同步与质量
├── 指标目录
├── 漏斗与目标
└── 自定义字段

平台治理（管理员）
├── 用户与权限
├── Agent 配置版本
├── 审计
├── 评测
└── 用量与套餐
```

## 15. CRM Intelligence Workspace

### 15.1 第一屏

第一屏不是静态 BI 大屏，也不是空白聊天框，包含：

- 统一自然语言任务入口。
- 今日经营简报。
- 需要关注的异常与风险。
- 最新周报、月报和专题报告。
- 推荐分析任务。
- 最近会话和定时任务。

快捷任务：

- 分析本月业绩变化。
- 检查漏斗健康度。
- 找出高风险商机。
- 对比各团队表现。
- 生成本周经营报告。

### 15.2 今日经营简报

首版默认展示：

- 目标达成率。
- Pipeline Coverage。
- 预计成交金额。
- 本月赢率。
- 商机滑期金额。
- 长期未跟进商机。
- 回款风险（数据可用时）。

每项显示当前值、对比基准、变化幅度、数据截止时间、指标口径和“分析原因”入口。

### 15.3 经营异常

异常必须包含事实、影响和证据，例如：

```text
华东团队本月赢率下降 8.4 个百分点
主要贡献：
- 方案阶段流失增加
- 新增商机质量下降
- 制造业客户销售周期延长
影响：约 ¥1,280,000 预测金额
```

允许操作：

- 查看证据。
- 深入分析。
- 查看相关客户和商机。
- 忽略或标记已知。
- 保存为监控规则。

## 16. Agent 分析工作台

工作台按任务组织：

```text
左：会话、任务、模板、报告
中：用户目标、分析计划、执行步骤、中间发现和最终结论
右：指标口径、图表、对象明细和报告 Artifact
```

复杂分析流程：

```text
用户目标
→ 确认范围
→ 展示分析计划
→ 执行确定性查询
→ 展示中间发现
→ 形成原因贡献度
→ 生成结论和建议
→ 保存为报告、模板或监控
```

用户可修改：

- 时间范围。
- Team 或 Owner。
- Pipeline。
- 产品。
- 地区。
- 来源。
- 对比基准。
- 报告深度。

## 17. 证据化回答与可信度

每个重要结论绑定：

- 指标值和公式。
- 基准和变化幅度。
- 查询条件。
- 影响对象清单。
- 数据更新时间。
- 查询执行 ID。
- 数据质量提示。

结果可信度状态：

```text
VERIFIED
PARTIAL
INSUFFICIENT_DATA
STALE_DATA
MAPPING_REQUIRED
PERMISSION_LIMITED
FAILED
```

规则：

- 数据不全不输出完整结论。
- 同步过期显式提示。
- 映射未完成不计算依赖指标。
- 样本量过小不报告趋势或贡献度。
- 相关性不能表述为因果。
- 权限不足只说明结果受限，不暴露被过滤对象。
- 每个结论至少绑定一个查询证据。
- 重要报告可要求 RevOps 或 Manager 复核后发布。

## 18. 报告中心

报告是一等资源，而不是聊天消息附件。

状态：

```text
草稿 → 生成中 → 待复核 → 已发布 → 已归档
```

报告包含：

- 周期和分析范围。
- 数据截止时间。
- 配置版本。
- 执行摘要。
- 核心指标。
- 趋势和漏斗。
- 异常与归因。
- 重点对象清单。
- 建议。
- 数据口径和证据附录。

支持：

- 在线阅读。
- 评论与复核。
- 历史版本。
- Word、PDF、图片和原始数据导出。
- 分享链接。
- CRM 内嵌展示。
- 邮件、飞书、钉钉和 Webhook 推送。
- 从报告段落继续追问。

### 18.1 首版报告模板

1. 销售经营日报。
2. 销售经营周报。
3. 销售经营月报。
4. 漏斗健康报告。
5. 销售预测报告。
6. 销售团队效能报告。
7. 重点客户风险报告。
8. 输单原因分析。
9. 来源转化报告。
10. 产品销售表现报告。

模板由结构化章节、指标、图表和诊断框架构成；模型只能在证据之上撰写解释。

## 19. 监控与订阅

### 19.1 确定性规则

- 商机 14 天未跟进。
- 预计成交日期已过。
- Pipeline Coverage 低于阈值。
- 阶段停留超过历史 P90。
- 本周新增 Pipeline 低于目标。
- 回款逾期。

### 19.2 Agent 周期分析

示例：

```text
每周一分析上周销售漏斗变化，
定位贡献最大的团队、来源和产品，
生成管理层周报并推送。
```

每次执行产生独立运行记录和 Artifact。监控结果必须按问题、对象和时间窗口去重，避免重复推送同一风险。

## 20. RevOps 建设后台

### 20.1 CRM 连接

展示：

- 授权状态。
- 连接健康。
- 同步游标。
- Webhook 状态。
- 最近成功时间。
- 错误、重试和死信。
- Schema 漂移。
- 删除连接和数据清理。

### 20.2 映射向导

系统给出自动建议，RevOps 确认：

- 标准字段。
- 自定义字段。
- Pipeline 和 Stage。
- Open、Won、Lost 状态。
- 币种和时区。
- Owner、Team 和区域。
- 活动类型。
- 赢单、输单原因。

映射发布前显示样例、覆盖率和影响预览。

### 20.3 指标目录

每个指标支持：

- 查看定义和公式。
- 绑定 Owner。
- 配置允许维度和默认过滤。
- 编辑草稿。
- 使用样例数据验证。
- 运行 Golden Questions。
- 发布版本和回滚。

### 20.4 数据质量

自动检测：

- 缺失 Owner。
- 无效 Stage。
- 重复客户。
- 金额或币种异常。
- Closed 状态但无关闭时间。
- Won 但金额为空。
- 长期不同步。
- 历史阶段链断裂。

数据质量问题进入报告可信度计算，并在管理者结果中显式披露。

### 20.5 评测与运营

RevOps 维护：

- 标准问题集。
- 预期指标和答案。
- 查询计划验证。
- 权限场景。
- 证据覆盖率。
- 报告完整度。
- 延迟和成本。
- 用户反馈。
- 失败原因分类。

新指标、诊断模板和 Agent 配置必须通过评测门禁后发布。

## 21. 权限与多租户隔离

### 21.1 平台角色

- Owner。
- Admin。
- RevOps。
- Manager。
- Viewer。

### 21.2 权限维度

- 数据范围：全公司、团队、本人、自定义范围。
- 对象权限：客户、联系人、商机、活动、合同、回款。
- 字段权限：金额、成本、利润、联系人敏感信息。
- 功能权限：连接、映射、指标、报告、定时任务、导出和分享。
- 报告权限：私有、指定成员、团队、租户。
- API Scope。

权限在以下环节重复执行：

```text
同步映射
→ 查询计划
→ SQL
→ Agent 上下文
→ 对象明细
→ 图表
→ 报告
→ 导出
→ 分享
→ 推送
```

### 21.3 隔离策略

- 所有数据强制携带 `tenant_id`。
- 每租户独立 CRM 凭证。
- 分析存储按租户分区。
- 缓存、向量、报告、对象存储和导出都携带租户作用域。
- 后台任务缺少租户上下文即拒绝执行。
- 大客户后续可升级独立数据库或集群。
- 普通租户管理员不能删除平台级不可篡改审计证据。

## 22. OpenAPI 与嵌入

### 22.1 身份

- OAuth 2.0 / OIDC。
- 短时嵌入 Token。
- 外部用户与平台用户映射。
- Token 包含租户、角色、数据范围和 API Scope。
- 前端不得持有长期 Connector Secret。

### 22.2 分析任务 API

```text
POST /analysis/tasks
GET  /analysis/tasks/{id}
GET  /analysis/tasks/{id}/events
GET  /analysis/tasks/{id}/artifacts
POST /analysis/tasks/{id}/follow-ups
```

普通查询可同步返回首个结果，但统一创建任务记录；深度分析始终异步。

### 22.3 报告 API

```text
POST /reports
GET  /reports/{id}
GET  /reports/{id}/versions
POST /reports/{id}/exports
```

### 22.4 嵌入方式

- JS SDK / Web Component。
- 安全 iframe。
- 深链接到分析任务、异常或报告。
- Webhook 通知。

CRMWolf 首选原生 OpenAPI 和事件流集成；第三方 CRM 厂商可先用安全 iframe 或 SDK。

## 23. CRMWolf 集成边界

CRMWolf Agent 和本产品不共用运行时：

| CRMWolf Agent | CRM Intelligence Workspace |
|---|---|
| 客户跟进和业务操作 | 数据分析和报告 |
| 强事务、强状态 | 查询、研究和 Artifact |
| LangGraph checkpoint、interrupt、HITL | 分析任务、查询证据、报告版本 |
| 通过 CRM API 写入 | 读取托管分析副本 |
| 服务 CRMWolf 业务流程 | 服务多个 CRM |

CRMWolf Root 可将只读分析请求路由到本产品：

```text
用户请求
→ CRMWolf Root 判断为分析类
→ 调用 CRM Intelligence OpenAPI
→ 接收进度、图表、证据和报告
→ 在 CRMWolf Agent UI 展示
```

客户、商机、跟进、回款等写入仍由 CRMWolf 自己的 Workflow、HITL、权限和幂等体系执行。

## 24. 错误处理与恢复

### 24.1 Connector

- OAuth 失效：停止同步并通知管理员，不删除现有分析副本。
- 限流：指数退避并保存游标。
- Webhook 漏失：每日对账修复。
- Schema 漂移：Raw 继续保存，受影响映射进入 `MAPPING_REQUIRED`。
- 部分对象失败：按对象和游标重试，不回滚已成功批次。
- 删除或合并：保存 tombstone 和重定向事实。

### 24.2 查询和 Agent

- 指标未发布：不生成临时 SQL，返回定义缺失。
- 数据过期：返回 `STALE_DATA`，允许用户查看旧值但禁止强结论。
- 数据不足：返回 `INSUFFICIENT_DATA`。
- 权限受限：返回 `PERMISSION_LIMITED`，不暴露过滤前数量和对象。
- 查询成本过高：要求缩小范围或改用异步任务。
- 模型失败：保留结构化查询结果；解释和报告阶段可独立重试。
- 报告失败：已有查询证据和章节进度保留，继续原任务恢复。

### 24.3 幂等

- Connector 事件以源事件 ID 或对象版本幂等。
- 分析任务支持 `client_request_id`。
- 定时任务一次计划窗口只生成一个运行。
- 报告重试不新增逻辑报告，只生成新版本或继续原版本。
- 导出请求重复时复用有效 Artifact。

## 25. 非功能要求

### 25.1 性能

- 首页预聚合摘要 P95 < 3 秒。
- 普通问数首个进度事件 < 2 秒。
- 普通问数完整结果 P95 < 15 秒。
- 深度分析和大报告使用异步任务和事件流。
- 长任务持续显示业务步骤，禁止长 HTTP 请求阻塞。

### 25.2 同步

- Webhook 型连接目标延迟 < 5 分钟。
- 轮询型连接目标延迟 < 15 分钟。
- 每日执行全量对账。
- 同步失败不丢游标。
- 数据重建不破坏历史报告的证据引用。

### 25.3 可靠性

- 所有分析任务可重试。
- 报告生成具备阶段 checkpoint。
- Connector 支持限流、退避和死信。
- 后台服务重启可恢复同步、分析、报告和导出任务。
- 重试不得重复产生逻辑任务、报告或推送。

### 25.4 安全

- Connector Secret 使用 KMS 加密。
- 租户密钥和数据分区隔离。
- 导出和报告 URL 短时有效。
- 审计日志由普通租户管理员不可删除。
- 报告、导出和推送继承数据权限。
- 默认不使用客户数据训练共享模型。
- 明确会话、分析副本、文件、报告和审计的保留与删除策略。

## 26. 测试与验收

### 26.1 Connector

- CRMWolf、Salesforce、HubSpot 首次全量同步。
- Webhook 与轮询重复事件幂等。
- 漏事件由 reconciliation 补齐。
- OAuth 过期和刷新。
- 限流与退避。
- 删除、合并、Owner 变更和 Schema 漂移。
- 断点重放不重复数据。

### 26.2 Canonical Model

- 同一业务事实从三个 CRM 映射到相同 Canonical 语义。
- Stage Open/Won/Lost 及序位正确。
- 币种、时区和金额折算一致。
- 自定义字段未发布时不影响核心指标。
- 历史阶段、金额和 Owner 变化完整。

### 26.3 指标与查询

- 每个指标有固定样例和边界用例。
- Golden Questions 的 Metric、Dimension、Filter、Time Range 解析正确。
- SQL 与手工基准一致。
- 小样本、空数据、过期数据和缺映射正确降级。
- 重复提问产生稳定结果。

### 26.4 权限

- 租户间零泄漏。
- Manager 只看到授权 Team。
- Owner 只看到本人范围。
- 敏感字段在问数、明细、图表、报告、导出和推送中均隐藏。
- 权限不足不泄漏过滤前数量和对象存在性。
- 嵌入 Token 不得扩大平台内权限。

### 26.5 Agent 与诊断

- 闭世界意图外请求明确拒绝或澄清。
- 诊断框架按确定性贡献计算，不依赖模型编数字。
- 相关性不表述为因果。
- 每个结论有证据。
- 查询成功但模型解释失败时，数据结果仍可交付。
- 深度研究中断后可恢复。

### 26.6 报告与监控

- 十类模板章节和指标完整。
- 数据更新时间、配置版本和证据附录存在。
- 报告版本可回读。
- 定时任务只执行一次。
- 同一异常按规则去重。
- 推送失败可重试，不重复发送已成功目标。

## 27. 首版成功标准

### 27.1 接入成功

- 90% 标准字段自动映射。
- 关键对象历史同步完整。
- Connector 失败可恢复。
- 数据质量问题可定位到源对象和映射。
- 连接 CRM 后 7 天内交付首份有效经营报告。

### 27.2 查询可信

- Golden Questions 指标正确率 ≥ 95%。
- 权限越界为 0。
- 每个重要结果包含口径、时间、筛选和证据。
- 重复问题结果稳定。
- 不足数据和配置缺失不伪装为成功。

### 27.3 业务价值

- 管理者每周至少消费一份自动报告。
- RevOps 手工取数时间降低 50%。
- 管理例会准备时间降低 50%。
- 异常发现从周级缩短到日级。
- 报告被查看、追问、分享或转成监控，而不是只生成不用。

### 27.4 产品留存

- 30 天内至少配置一个定时报告。
- 管理者周活跃率。
- Agent 任务成功率。
- 报告复用率。
- 异常洞察采纳率。
- Connector 健康租户占比。

## 28. 分期建议

### Phase 1：CRMWolf 设计伙伴验证闭环（非 V1 GA）

- CRMWolf Connector。
- 核心 Canonical 对象和历史事实。
- 20–30 个指标。
- 智能问数、经营周报、漏斗诊断。
- Workspace、报告中心和 RevOps 映射后台。
- OpenAPI 接入 CRMWolf。

Phase 1 的代码边界仍按独立产品设计，不直接依赖 CRMWolf ORM 或内部表。

### Phase 2：完成 V1 GA，证明多 CRM

- Salesforce Connector。
- HubSpot Connector。
- 跨 CRM 映射向导。
- 全部六类诊断和十类报告。
- JS SDK、安全 iframe、飞书/邮件推送。

### Phase 3：V1 GA 后规模化运营

- 高级预测和评测。
- 租户级自定义指标和诊断模板。
- 独立数据库/集群选项。
- 合作伙伴和 CRM 厂商嵌入管理。
- 经明确授权的匿名行业基准。

### 28.1 实施子项目与依赖顺序

本文是产品与总体架构总纲，不得直接转成一个覆盖全部范围的单体实施计划。Phase 1 必须拆成以下独立规格和实施计划，每个子项目分别评审、验收和发布：

1. **平台基础与租户安全。** 租户、身份、角色、数据范围、加密凭证、审计、durable task、Artifact 和配置版本基础设施。
2. **Canonical CRM 数据合同。** 标准对象、源引用、历史事实、币种/时区、删除/合并、证据引用和数据质量合同。
3. **Connector Runtime 与 CRMWolf Connector。** 统一 Connector 接口、游标、全量/增量、Webhook、reconciliation、重试、死信及 CRMWolf 首个适配器。
4. **RevOps 映射与数据质量。** 字段/Stage/组织映射、影响预览、发布版本、Schema 漂移和质量问题工作台。
5. **指标目录与权限查询引擎。** 首批指标、维度、漏斗、权限裁剪、确定性查询计划、SQL/指标执行和证据合同。
6. **经营情报与智能问数。** Workspace 首页、Golden Questions、闭世界意图、Query Planner、结果图表和可信度状态。
7. **漏斗诊断与经营周报。** 首个 Diagnostic Engine、报告 Artifact、版本、复核、导出和证据附录。
8. **定时任务与推送。** 调度、运行记录、去重、邮件/Webhook，以及后续飞书/钉钉适配边界。
9. **CRMWolf 开放集成。** OpenAPI、事件流、嵌入身份、权限映射、CRMWolf Agent 分析路由和端到端验收。

依赖关系：

```text
平台基础与租户安全
  → Canonical CRM 数据合同
  → Connector Runtime 与 CRMWolf Connector
  → RevOps 映射与数据质量
  → 指标目录与权限查询引擎
  → 经营情报与智能问数
  → 漏斗诊断与经营周报
  → 定时任务与推送
  → CRMWolf 开放集成与发布验收
```

允许在接口冻结后并行建设 UI 和底层实现，但不得跳过上游数据、权限和证据合同，用 mock 数据宣称后续产品闭环完成。

### 28.2 总纲明确不冻结的决策

以下决策不属于本总纲，必须在对应子项目规格中基于规模、合规和成本单独确认；未确认前不得由实施者自行选择并形成长期事实：

- 编程语言、服务框架和具体仓库布局。
- OLTP、分析数据库、对象存储、队列和工作流引擎选型。
- SaaS 地域、数据驻留、多地域复制和私有化拓扑。
- 模型供应商、模型路由、Token 预算和降级策略。
- 数据、会话、文件、报告、导出和审计的具体保留期限。
- KMS/BYOK、租户独立密钥和独立集群的套餐边界。
- Salesforce、HubSpot API 套餐限制及 Custom Object 正式支持范围。
- 套餐、计费、试用、配额和商业定价。
- 行业基准、跨租户聚合和任何数据训练用途。
- 源 CRM 写回、任务创建和自动化动作；这些能力必须另立产品设计。

## 29. 风险与控制

- **连接器范围失控。** 首版只支持标准对象；自定义对象不进入通用承诺。
- **同步历史不足。** 从首次接入起保存变化事实；不能凭当前状态伪造历史漏斗。
- **不同 CRM 语义差异。** Canonical 核心字段稳定，差异进入映射和扩展区。
- **指标争议。** 指标有 Owner、版本、测试样例和生效时间；报告记录版本。
- **Agent 幻觉。** 模型不能生成事实；所有数字和结论绑定查询证据。
- **相关性误判因果。** 产品文案使用“贡献、相关、伴随变化”，无实验或业务证据时不写因果。
- **权限泄漏。** 权限贯穿查询、Artifact 和推送；高风险路径纳入专门回归。
- **源 CRM 限流。** Webhook、增量同步、缓存和 reconciliation 降低 API 压力。
- **托管数据合规。** 明确数据驻留、加密、保留、删除、子处理方和不训练承诺。
- **产品退化成 BI。** 固定图表只服务入口和证据；核心对象始终是分析任务、诊断和报告。
- **产品退化成聊天框。** 首页主动展示经营简报、异常、报告和推荐任务。
- **过早写回 CRM。** 首版只读；写回必须另立规格，逐连接器实现权限、HITL、幂等和审计。

## 30. 合并与发布门禁

首个正式版本必须同时具备：

1. 独立租户、身份和权限体系。
2. Connector durable 同步、游标、重试、死信和 reconciliation。
3. Raw Zone、Canonical Model 和历史事实层。
4. 已发布指标目录及 Golden Questions。
5. 确定性 Query Executor 和证据合同。
6. 至少智能问数、漏斗诊断、经营周报三条端到端链路。
7. Workspace、报告中心和 RevOps 映射后台。
8. 报告 Artifact、版本、导出和权限继承。
9. 审计、评测和数据质量反馈。
10. CRMWolf OpenAPI 集成验收。
11. 租户隔离和敏感字段全链路安全测试。
12. 备份、恢复、数据删除和退出方案。

不允许只实现对话 UI、自由 SQL 或静态报告模板就宣称完成 CRM 数据智能平台。

## 31. 参考产品与官方资料

本设计参考火山引擎官方文档中的产品模式和能力边界，不依赖其闭源实现：

- [什么是数据智能体 Data Agent](https://docs.volcengine.com/docs/Dataagent/Whatisadataagent?lang=zh)
- [什么是 iDA](https://docs.volcengine.com/docs/Dataagent/what-is-ida?lang=zh)
- [iDA 界面介绍](https://docs.volcengine.com/docs/Dataagent/IntroductiontoiDAinterface?lang=zh)
- [快速使用 iDA](https://docs.volcengine.com/docs/Dataagent/QuicklyuseiDA?lang=zh)
- [智能体类型说明](https://docs.volcengine.com/docs/Dataagent/Agenttypedescription?lang=zh)
- [智能问数 Agent](https://docs.volcengine.com/docs/Dataagent/IntelligentQueryAgent?lang=zh)
- [深度研究 Agent](https://docs.volcengine.com/docs/Dataagent/DepthResearchAgent?lang=zh)
- [数据连接概述](https://docs.volcengine.com/docs/Dataagent/Dataconnectionoverview?lang=zh)
- [数据资产](https://docs.volcengine.com/docs/Dataagent/Dataassets?lang=zh)
- [数据行列权限](https://docs.volcengine.com/docs/Dataagent/Datarowandcolumnpermissions-1?lang=zh)
- [权限管理](https://docs.volcengine.com/docs/Dataagent/rightsmanagement?lang=zh)
- [技能中心](https://docs.volcengine.com/docs/Dataagent/SkillsCentre?lang=zh)
- [定时任务](https://docs.volcengine.com/docs/Dataagent/Scheduledtasks?lang=zh)
- [开放性说明](https://docs.volcengine.com/docs/Dataagent/IntelligentAnalysisAgentOpennessExplanation?lang=zh)
- [JS SDK 集成方案](https://docs.volcengine.com/docs/Dataagent/JSSDKintegrationsolution-1?lang=zh)
- [智能问数 OpenAPI](https://docs.volcengine.com/docs/Dataagent/IntelligentQueryAPIDescriptionandPublicParametersNewVersion-1?lang=zh)
- [执行深度研究任务](https://docs.volcengine.com/docs/Dataagent/Performin-depthresearchtasks?lang=zh)
- [审计](https://docs.volcengine.com/docs/Dataagent/Audit?lang=zh)
- [评测工具](https://docs.volcengine.com/docs/Dataagent/overview-of-evaluation-tools?lang=zh)
- [产品计费](https://docs.volcengine.com/docs/Dataagent/DataAgentProductServiceBilling?lang=zh)

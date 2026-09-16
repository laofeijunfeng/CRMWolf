# 客户档案主张出处与产品强事实

- 日期：2026-09-16
- 状态：已确认，待实施
- 范围：客户智能上下文、档案需求叙事、发布校验、档案页「项目需求背景 / 当前业务状态」
- 上游决定：档案正文里的专有名词和具体情节，必须能在「被引用的原文 ∪ 该客户/商机已绑定产品」里找到；找不到就不能写成确定结论。分类模板可以留，主题套话整组下线。产品进入 `strong_context`。栏目拆开，前端禁止用需求主张填业务状态。
- 相关规范：`CRM-Docs/design-agent/runtime/customer-intelligence-profile.md`、`CRM-Docs/requirements/2026-08-28-customer-intelligence-profile-trd.md`、`docs/superpowers/specs/2026-09-15-lead-customer-product-association-design.md`
- 相关实现：`CRM-Server/app/services/customer_profile_projection_service.py`、`CRM-Server/app/services/customer_profile_projection_validator.py`、`CRM-Server/app/services/customer_intelligence_context_service.py`、`CRM-Server/app/services/agent/customer_profile_projection_graph.py`、`CRM-Server/app/crud/product_intent.py`、`CRM-Client/src/components/panels/CustomerProfileContent.vue`

## 1. 背景与目标

协鑫数智这条客户的跟进原文写的是 Hifox 和私有化部署。档案「项目需求背景」和「当前业务状态」却写成：

> 客户正在重新评估 Apifox 私有化部署方案，需要私有环境安装包和试用方案。

引用弹层读跟进原文，所以弹窗仍是 Hifox。这不是模型听错，也不是前端改写。

当前实现：

1. `_activity_topic` 用关键词把跟进打成 `private_solution` / `poc` / `usage_expansion` 等主题。
2. `_demand_statement` 按主题返回固定中文。`private_solution` 写死 Apifox、安装包、试用方案；同函数还写死「账号已用满」「向 CTO 汇报」「轻量交互页面」「人员出差」。
3. 发布校验只检查 `evidence_refs` 的 key 是否在登记表里，不核对句子是否被原文支持。
4. 前端在没有 `business_status_rows` 时，用同一批 `demand_items.statement` 填「当前业务状态」。
5. `CustomerIntelligenceContext` 的客户/商机事实不含意向产品或商机产品。Agent 录线索能匹配 Hifox，档案组稿看不到产品目录。

档案 PRD 要求：事实层只能提炼、不能编造；叙事层可以归纳、必须可追溯；不得猜测缺失业务状态。当前需求句违反这条。

目标：

1. 需求正文变成带出处的主张，不再是 `topic → 固定句子`。
2. 产品作为强事实进入档案上下文；跟进原文用现有 `match_active_product` 解析提到的产品。
3. 发布门禁拒绝「引用里没有、客户/商机也没绑定」的产品名和具体情节。
4. 「项目需求背景」和「当前业务状态」各写各的。
5. 模型不可用时，退回「引用片段 + 已绑定/已匹配产品名」，禁止退回样例话术。

## 2. 非目标

- 不在本期把 `compose_profile_sections` 做成完整 LLM 叙事节点。事实抽取继续走现有 LLM；需求主张先由确定性组稿 + 出处门禁落地。以后模型只允许改写已通过门禁的主张。
- 不改线索/客户/商机的产品写入契约。
- 不把商机改成多产品，也不在档案里发明模块选择。
- 不自动纠偏历史已发布快照。旧版本保留；新刷新按新契约生成。
- 不把 License 导出标题 `Apifox私有化授权文件` 纳入本期。那是另一条运行时硬编码，与档案叙事无关。
- 不让档案代替商机/合同/任务成为状态真相。
- 不把「当前业务状态」做成销售建议或下一步行动。
- 不在出处门禁里做模糊语义 entailment 或向量相似度。本期只做专有名词和绑定产品的确定性核对。

## 3. 方案选择

采用「主张图 + 出处门禁 + 产品进强事实」。

放弃：

- 只把 Apifox 改成从原文替换产品名：同函数里其它套话仍会编造 CTO、安装包、出差。
- 删掉全部模板、需求栏直接贴跟进原文：不再编造，但档案退化成跟进列表，产品仍进不了上下文。
- 先让模型写需求、校验仍只查 evidence key：和现在同类，只是编造更像人写的。

## 4. 不变量

档案正文（`statement` / `summary` / `content` 等销售可读句子）中：

- 团队产品名只允许来自：该主张 `evidence_refs` 对应原文经产品目录匹配命中的启用产品，或该客户 `products[]`，或该主张范围内商机的已绑定产品。
- 具体情节（安装包、试用方案、CTO、账号已用满、出差、轻量交互页面等）只允许在对应引用原文中出现后写入。
- 主题标签（`private_solution` 等）只用于分类和维度名，不得单独决定句子。
- 无产品出处时，写「私有化部署」这类通用需求，不写任何产品名。
- 无情节出处时，不得补「重新评估」「需要安装包」等模板细节。
- 组稿负责不写无出处的专有名词。出处门禁是后门：草稿里一旦出现无出处产品名或套话情节，整份档案拒绝发布，保留上一成功版本。`INSUFFICIENT_EVIDENCE` 只用于「有跟进但还构不成可读需求」，不是把编造句标成尚未确认后放行。

## 5. 领域分层

| 层 | 职责 | 禁止 |
|---|---|---|
| 强上下文 | 客户意向产品、商机产品、团队启用产品目录、跟进原文 | 用目录第一项冒充该客户产品 |
| 事实层 | 从跟进/事件提炼 `need` 等候选；绑定 `evidence_keys` | 无 quote / 无 key 的产品事实 |
| 状态层 | 旅程、商机、合同、任务、回款 | 用需求句冒充业务状态 |
| 主张层 | 把跟进/事实收成 `DemandClaim`：topic + products + statement + evidence | `topic → 固定中文` |
| 叙事层 | 用主张的 statement 填需求背景；用状态层填当前业务状态 | 两栏共用同一句 |
| 发布门禁 | schema、证据 key、水位、**出处** | 只查 key 不查名词 |

## 6. 产品进入强上下文

`CustomerIntelligenceContextService._build_strong_context` 补产品，不改权限过滤。

### 6.1 客户

`CustomerFact` / `to_dict()` 增加与客户 API 同形的只读产品字段：

```text
product_public_id
product_name
products: [{ public_id, name }]
```

来源：`product_intent_payload(customer.product_links)`。历史无产品时三者为 `null` / `null` / `[]`。停用产品仍展示名称，与列表只读规则一致。

### 6.2 商机

`OpportunityFact` / `to_dict()` 增加：

```text
product_public_id
product_name
```

来源：`opportunity.product`。无产品时为 `null`。本期档案不展示模块；模块仍只属于商机成交配置。

### 6.3 团队目录

`CustomerIntelligenceContext.to_dict()` 增加：

```text
product_catalog: [{ public_id, name, is_active }]
```

只含当前团队启用产品，供组稿匹配，不写入档案正文。空目录时为 `[]`，需求句不写产品名。

### 6.4 跟进上的产品引用

组稿时对每条活动的 `content` / `summary` / `source_content` 按 `match_active_product` 同一套规则匹配 `product_catalog`（精确唯一产品名，或原文唯一包含某启用产品名）。`draft_from_context` 不另查库：产品目录和客户/商机产品已在 context 里。

规则：

- 精确命中唯一启用产品名，或原文唯一包含某启用产品名 → 采用
- 零命中或多命中 → 该条活动不贡献产品
- 不得用客户意向产品或目录第一项填进「原文提到的产品」；客户/商机绑定产品只能写入主张的 `product_public_ids`，句子里必须标明来源是「客户意向 / 商机」，不能写成「本次跟进提到」

一条主张的 `product_public_ids`：

1. 先收该主张证据活动上匹配到的产品
2. 若为空，且该主张能归到唯一商机，用该商机产品
3. 若仍为空，且客户只有一个意向产品，用客户意向产品
4. 仍为空则不写产品名

第 2、3 步写出的句子必须能看出不是跟进原文里的产品词，例如「客户意向产品为 Hifox，正在了解私有化部署」。不得写成「看到了 Hifox」除非原文有这句话。

## 7. 需求主张

下线 `_demand_statement` 和 `_fact_demand_statement` 里按 topic 返回的固定句子，以及 `_process_change` 里同类套话。主题规则 `_TOPIC_RULES` 可保留，只用于 `topic`。

每条需求主张：

```text
topic                分类键，如 private_solution
statement            销售可读的一句，必须通过出处门禁
claim_status         AVAILABLE | INSUFFICIENT_EVIDENCE
product_public_ids   已解析产品
product_names        与上项对应的当时名称
evidence_refs        支持该主张的 activity/fact key
source_quotes        组稿用的原文片段，不作为前端主文案
```

`generic_demand` 且活动有意义时：`statement` 用该组去重后的跟进原文（现有 `_unique_activity_texts`，限 1 句、截断到现有 `_text` 上限），不另写主题套话。

确定性组稿规则（模型不可用或未启用叙事 LLM 时必须走这条，禁止退回样例表）：

| topic | 有产品 | 无产品 |
|---|---|---|
| `private_solution` | `{product} 相关跟进提到私有化/本地部署`；原文有安装包/试用等词才可追加这些词 | `跟进提到私有化或本地部署` |
| `poc` | 原文有已部署/正式试用/暂无问题等标记才写对应状态；否则 `{product} 相关跟进提到试用或 POC` | 同上，不写产品 |
| `usage_expansion` | 仅当原文出现账号/增购/授权/扩大使用等词时写这些词 | 不得写「账号已用满」除非原文有 |
| `reporting` | 仅复述原文出现的报表/导出/按部门 | 不得写「按部门导出」除非原文有 |
| `internal_validation` | 仅复述原文出现的试用项目数、CTO、汇报 | 不得写 CTO |
| `procurement` | 仅复述原文出现的预算/招标/付款等 | 不得写「内部审批和付款安排」除非原文有 |
| `acceptance` | 仅复述原文 | 不得写「轻量交互页面」除非原文有 |
| `approval` / `project_blocked` | 仅复述原文 | 不得写「立项材料已提交」或「出差暂缓」除非原文有 |

协鑫数智这条跟进命中 `private_solution` + Hifox 后，合法句子类似：

> 跟进记录显示客户对 Hifox 感兴趣，公司层面使用需要私有化部署。

非法：Apifox、重新评估、安装包、试用方案——原文没有这些词，客户也没绑定 Apifox。

`demand_background.summary` 仍由主张 `statement` 拼接（现有 `_demand_background_summary`），拼接结果也必须能通过出处门禁（专有名词并集 ⊆ 各主张出处并集）。

## 8. 出处门禁

现有校验保留：schema、证据 key 在登记表、禁止销售建议字段、scope、水位。

新增硬门禁，放在 `CustomerProfileProjectionValidator`，发布前 `assess_draft` 必跑。质量 linter 仍只做销售建议 WARNING，不承担出处。

扫描范围：`current_situation.demand_background` 的 `summary` / `items[].statement`，以及 `follow_up_process` 里由主题套话改写的变化句。`current_situation.summary`（客户摘要）若包含团队产品名，必须能在 demand 主张的 `product_names` 或摘要自身证据原文中找到；摘要不得独立发明产品名。

对每个被扫描字符串：

1. 收集该对象 `evidence_refs` 对应 registry 条目的原文（活动：`source_content` 或 `summary` 或 `content`；事实：`content`）。draft 组稿时必须把这些原文放进 `evidence_refs` 条目的 `snippet`（或主张上的 `source_quotes`），校验器不二次查库。draft 同时携带本次使用的 `product_catalog` 名称列表（可放在 `source_watermark.product_catalog_names`，供校验对照）。
2. **产品名**：`product_catalog` 中每个启用产品名，若出现在陈述里，则必须出现在第 1 步原文中，或出现在该主张 `product_names` 且 `product_public_ids` 按第 6.4 节合法。陈述写了目录里没有的其它品牌名（大小写不敏感，对照 catalog）→ 拒绝。
3. **模板情节词**：固定词表（安装包、试用方案、轻量交互页面、账号已用满、向上级CTO汇报、立项材料已提交、人员出差）。陈述出现则原文必须出现同一词，或该 topic 规则已列出的同义标记（如 POC 的「已部署 / 正式试用 / 暂无问题」）。词表与下线的套话一一对应，防止旧模板改个同义词回流。
4. 失败码：`PROFILE_CLAIM_UNGROUNDED`。不得发布。refresh run 记失败并保留上一成功版本，与现有硬校验一致。不得把无出处句子改成 `INSUFFICIENT_EVIDENCE` 后发布。

不得用「句子和原文字符重叠 ≥ 0.86」这类现有 `_similar_text` 当出处。那是去重，不是接地。

## 9. 栏目拆分

后端：

- `current_situation.demand_background`：只放需求主张。
- `current_situation.business_status`：继续只放旅程/商机/合同/回款计数。
- 新增 `current_situation.business_status_rows`：由状态层生成。有开放旅程则写阶段；有跟进中商机则写商机数量与主要阶段；有合同则写合同数。没有这些对象时为 `[]`，不从 `demand_items` 生成行。

前端 `CustomerProfileContent.vue`：

- 「项目需求背景」继续渲染 `demand_background.summary` / items。
- 「当前业务状态」**只**渲染 `business_status_rows`。数组为空则不渲染该卡片。
- 删除 `currentAssessmentRows` 在 `configured.length === 0` 时 `demandItems.map(statement)` 的回退。
- 引用弹层仍解析 `evidence_refs` 到原文，不改。

协鑫数智在只有跟进、没有商机/合同时：需求栏有 Hifox 私有化主张；当前业务状态卡片不出现，而不是再贴同一句。

## 10. Graph 与刷新

`CustomerProfileProjectionGraphService` 节点顺序不变：

```text
load_context → extract_facts → persist_facts → compose_draft → validate → publish
```

变化在 `compose` 和 `validate`：

- `draft_from_context` 使用带产品的 context 生成主张，不再调用主题套话函数。
- `assess_draft` 跑出处门禁。
- `_compose_profile_draft` 继续确定性。以后若加 LLM 叙事，输入只能是已生成的 `DemandClaim[]`，输出仍走同一校验；失败则退回确定性 statement，禁止套话。

刷新：代码上线后，已有错误快照不会自己变。该客户需一次成功 refresh（页面刷新按钮、新跟进触发、或运维重建）。同一套旧代码刷新会再生成 Apifox 句。

## 11. 测试与验收

后端：

- 协鑫数智原文（Hifox + 私有化，无安装包/试用方案）→ 主张含 Hifox、topic=`private_solution`、不含 Apifox、不含「安装包」「试用方案」「重新评估」。
- 原文无产品名、客户意向为 Hifox → 句子可写客户意向 Hifox，须能区分来源；仍不得写 Apifox。
- 原文写 Hifox、客户意向 Apifox → 跟进提到的产品以原文匹配为准，不得因客户意向改写成 Apifox。
- 旧套话「客户正在重新评估 Apifox…」作为 draft statement 时，validate 抛 `PROFILE_CLAIM_UNGROUNDED`。
- `draft_from_context` 不再产生任何 `_demand_statement` 旧固定句（对 Apifox 句、CTO 句、账号已用满句做断言）。
- context 客户/商机 dict 含产品字段；空产品客户为 null/[]。
- 无旅程/商机/合同时 `business_status_rows == []`。

前端：

- 有 `business_status_rows` 时渲染这些行。
- 只有 demand items、没有 `business_status_rows` 时不出现「当前业务状态」卡片，需求栏仍在。
- 不得在测试里把 demand statement 当作业务状态。

验证：

- `pytest` 定向：`test_customer_profile_projection_contracts.py` 及新增出处/产品上下文测试
- 前端 `CustomerProfileContent` 定向 Vitest
- 不得再把 Apifox 写进「私有化」正向 fixture 当期望正文

## 12. 风险

- 出处门禁过严：跟进用「本地化部署」而规则只认「私有化」时，topic 可能仍命中（现有关键词含「本地部署」），但情节词表不包含的同义写法不会被当模板打击。产品名仍必须匹配目录。
- `match_active_product` 在「Hifox」「HiFox」大小写不同时靠 `casefold`；「狐」这类过短子串可能误匹配，沿用现有 Agent 规则，不在本期放宽或收紧。
- 客户摘要若仍直接复制 demand summary，出处门禁覆盖 demand 后摘要会一起变对。若摘要另有模板，需在实现时纳入同一扫描；本设计要求摘要不得独立发明产品名。
- 历史档案会暂时保留错误句，直到 refresh。页面 STALE 条不自动修内容。
- `_demand_statement` 删除后，依赖「私有化部署」子串但不钉产品名的旧测试必须改成钉 Hifox/原文，避免再把错误品牌测成绿色。

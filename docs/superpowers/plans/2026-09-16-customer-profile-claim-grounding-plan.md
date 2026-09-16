# 客户档案主张出处与产品强事实 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 档案需求句只写跟进原文或该客户/商机已绑定产品里有的专有名词和情节；Hifox 私有化跟进不得再写成 Apifox 套话；需求栏和业务状态栏拆开。

**Architecture:** 产品进入 `CustomerIntelligenceContext`。`draft_from_context` 用目录纯函数匹配跟进原文，生成 `DemandClaim`，下线 `_demand_statement` 主题套话。发布校验新增出处门禁。前端「当前业务状态」只读 `business_status_rows`。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, pytest, Vue 3, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-16-customer-profile-claim-grounding-design.md`

## Global Constraints

- 不改无关脏工作区。不改线索/客户/商机产品写入契约。不改 License 导出标题。
- 不把 `compose_profile_sections` 做成 LLM 叙事节点。模型不可用时禁止退回样例话术。
- 不自动纠偏历史快照。不把无出处句子标成 `INSUFFICIENT_EVIDENCE` 后发布。
- 出处门禁不做向量相似度，不用 `_similar_text`。
- 主题规则 `_TOPIC_RULES` 可留，只用于分类。
- `draft_from_context` 不另查库；产品目录和客户/商机产品只来自 context。
- 前端禁止 `any`、`as any`、`@ts-ignore`、无必要非空断言。
- 中间任务只跑步骤里的定向测试。全量 lint / 浏览器 smoke 不在中间任务跑。
- 失败码逐字：`PROFILE_CLAIM_UNGROUNDED`。
- 协鑫数智跟进原文（测试夹具必须用这一句）：
  `联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。`

## 文件结构与职责

- Modify: `CRM-Server/app/crud/product_intent.py` — 抽出 `match_catalog_product`，`match_active_product` 复用它。
- Modify: `CRM-Server/app/services/customer_intelligence_context_service.py` — 客户/商机产品字段、`product_catalog`。
- Create: `CRM-Server/app/services/customer_profile_demand_claims.py` — `DemandClaim` 与确定性组稿。
- Create: `CRM-Server/app/services/customer_profile_claim_grounding.py` — 出处检查纯函数。
- Modify: `CRM-Server/app/services/customer_profile_projection_service.py` — 用主张组稿、证据 snippet、`business_status_rows`、下线套话。
- Modify: `CRM-Server/app/services/customer_profile_projection_validator.py` — 调用出处门禁。
- Modify: `CRM-Client/src/components/panels/CustomerProfileContent.vue` — 业务状态不再回退需求句。
- Test: `CRM-Server/tests/unit/test_product_intent.py`（或新建 `test_catalog_product_match.py`）
- Test: `CRM-Server/tests/unit/test_customer_intelligence_context_service.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_demand_claims.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_claim_grounding.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_projection_contracts.py`
- Test: `CRM-Client/src/components/panels/__tests__/CustomerProfileContent.test.ts`

---

### Task 1: 产品进入强上下文，目录匹配纯函数

**Files:**
- Modify: `CRM-Server/app/crud/product_intent.py`
- Modify: `CRM-Server/app/services/customer_intelligence_context_service.py`
- Test: `CRM-Server/tests/unit/test_catalog_product_match.py`
- Test: `CRM-Server/tests/unit/test_customer_intelligence_context_service.py`

**Interfaces:**
- Consumes: `product_crud.list` / `get_by_public_id`、`product_intent_payload`、`Customer.product_links`、`Opportunity.product`
- Produces:
  - `match_catalog_product(products: Sequence[Any], raw: object) -> Any | None`
  - `match_active_product` 改为 list 后交给 `match_catalog_product`；public_id 精确命中仍可先走 `get_by_public_id`
  - `CustomerFact.product_public_id: str | None = None`、`product_name: str | None = None`、`products: list[JsonObject] = field(default_factory=list)`
  - `OpportunityFact.product_public_id: str | None = None`、`product_name: str | None = None`
  - `CustomerIntelligenceContext.to_dict()` 增加 `product_catalog: list[{public_id, name, is_active}]`（仅启用产品）
  - `_build_strong_context` 组装目录时 `product_crud.list(db, team_id, is_active=True)`

- [ ] **Step 1: Write failing catalog-match tests**

Create `CRM-Server/tests/unit/test_catalog_product_match.py`:

```python
from types import SimpleNamespace

from app.crud.product_intent import match_catalog_product


def _p(public_id: str, name: str, *, is_active: bool = True):
    return SimpleNamespace(public_id=public_id, name=name, is_active=is_active)


def test_match_catalog_product_exact_name_and_contained_unique():
    catalog = [_p("prd_hifox", "Hifox"), _p("prd_apifox", "Apifox")]
    assert match_catalog_product(catalog, "Hifox").public_id == "prd_hifox"
    assert match_catalog_product(catalog, "今天看到了 Hifox，比较感兴趣").public_id == "prd_hifox"
    assert match_catalog_product(catalog, "prd_apifox").public_id == "prd_apifox"


def test_match_catalog_product_zero_or_multiple_is_none():
    catalog = [_p("prd_hifox", "Hifox"), _p("prd_apifox", "Apifox")]
    assert match_catalog_product(catalog, "私有化部署") is None
    assert match_catalog_product(catalog, "Hifox 和 Apifox") is None
    assert match_catalog_product(catalog, "") is None
    assert match_catalog_product([_p("prd_x", "X", is_active=False)], "X") is None
```

- [ ] **Step 2: Run catalog-match test to verify it fails**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_catalog_product_match.py -q`

Expected: FAIL，`match_catalog_product` 未定义。

- [ ] **Step 3: Implement `match_catalog_product` and reuse it**

In `app/crud/product_intent.py`:

```python
def match_catalog_product(products: Sequence[Any], raw: object) -> Any | None:
    text = str(raw).strip() if raw is not None else ""
    if not text:
        return None
    folded = text.casefold()
    active = [item for item in products if bool(getattr(item, "is_active", True))]
    by_id = [item for item in active if str(getattr(item, "public_id", "")) == text]
    if len(by_id) == 1:
        return by_id[0]
    exact = [item for item in active if str(getattr(item, "name", "")).casefold() == folded]
    if len(exact) == 1:
        return exact[0]
    contained = [
        item
        for item in active
        if (name := str(getattr(item, "name", "")).casefold())
        and (name in folded or folded in name)
    ]
    if len(contained) == 1:
        return contained[0]
    return None
```

`match_active_product`：先 `get_by_public_id` 且 `is_active`；否则 `match_catalog_product(product_crud.list(db, team_id, is_active=True), raw)`。

- [ ] **Step 4: Write failing context product tests**

In `tests/unit/test_customer_intelligence_context_service.py`:

- `_session()` 的 `create_all` 增加 `Product.__table__`、`CustomerProduct.__table__`。
- `_seed_customer_context` 创建 `Product(id=801, public_id="prd_hifox", team_id=2, code="HIFOX", name="Hifox", is_active=True, created_by="9")`，`CustomerProduct(customer_id=101, product_id=801, team_id=2)`，并把 `Opportunity.id=301` 的 `product_id=801`。
- 在 `test_customer_intelligence_context_combines_strong_facts_and_semantic_evidence` 增加：

```python
customer = payload["strong_context"]["customer"]
assert customer["product_public_id"] == "prd_hifox"
assert customer["product_name"] == "Hifox"
assert customer["products"] == [{"public_id": "prd_hifox", "name": "Hifox"}]
assert payload["strong_context"]["opportunities"][0]["product_public_id"] == "prd_hifox"
assert payload["strong_context"]["opportunities"][0]["product_name"] == "Hifox"
assert payload["product_catalog"] == [{"public_id": "prd_hifox", "name": "Hifox", "is_active": True}]
```

另加：

```python
def test_customer_intelligence_context_empty_product_is_null_list() -> None:
    engine, db = _session()
    service = CustomerIntelligenceContextService(
        embedding_service=FakeEmbeddingService(),
        qdrant_index_service=FakeQdrantIndexService(),
    )
    try:
        _seed_industries(db)
        customer = Customer(
            id=101, team_id=2, account_name="无产品客户", creator_id="9",
        )
        db.add(customer)
        db.commit()
        payload = service.build_context(db, team_id=2, customer_id=101).to_dict()
        assert payload["strong_context"]["customer"]["product_public_id"] is None
        assert payload["strong_context"]["customer"]["product_name"] is None
        assert payload["strong_context"]["customer"]["products"] == []
        assert payload["product_catalog"] == []
    finally:
        db.close()
        engine.dispose()
```

导入 `Product`、`CustomerProduct`。

- [ ] **Step 5: Run context tests to verify they fail**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_intelligence_context_service.py::test_customer_intelligence_context_combines_strong_facts_and_semantic_evidence tests/unit/test_customer_intelligence_context_service.py::test_customer_intelligence_context_empty_product_is_null_list -q`

Expected: FAIL，payload 无产品字段。

- [ ] **Step 6: Implement context product fields**

`CustomerFact` 增加三个字段，`to_dict()` 输出。`_customer_fact` 用 `product_intent_payload(customer.product_links)`。加载客户时 `joinedload(Customer.product_links).joinedload(CustomerProduct.product)`，或在 `_customer_fact` 前访问 `product_links`。

`OpportunityFact` 增加产品两字段。`_opportunity_fact`：`product = opportunity.product`，有则 `public_id`/`name`，否则 `None`。查询商机 `joinedload(Opportunity.product)`。

`_build_strong_context` 末尾：

```python
from app.crud.product import product_crud
from app.crud.product_intent import product_intent_payload

catalog = [
    {"public_id": item.public_id, "name": item.name, "is_active": True}
    for item in product_crud.list(db, team_id, is_active=True)
]
```

`CustomerIntelligenceContext.to_dict()` / `to_agent_payload()` 都带 `product_catalog`（`to_agent_payload` 基于 `to_dict` 则只改一处）。

- [ ] **Step 7: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_catalog_product_match.py tests/unit/test_customer_intelligence_context_service.py -q`

Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add CRM-Server/app/crud/product_intent.py CRM-Server/app/services/customer_intelligence_context_service.py CRM-Server/tests/unit/test_catalog_product_match.py CRM-Server/tests/unit/test_customer_intelligence_context_service.py
git commit -m "$(cat <<'EOF'
feat(profile): put intent products into intelligence context

EOF
)"
```

---

### Task 2: 需求主张组稿，下线主题套话

**Files:**
- Create: `CRM-Server/app/services/customer_profile_demand_claims.py`
- Modify: `CRM-Server/app/services/customer_profile_projection_service.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_demand_claims.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_projection_contracts.py`

**Interfaces:**
- Consumes: `match_catalog_product`（Task 1）；活动/事实 dict
- Produces:
  - `CatalogProductRef(public_id: str, name: str, is_active: bool = True)`
  - `DemandClaim(topic, statement, claim_status, product_public_ids, product_names, evidence_refs, source_quotes, occurred_at, latest_at, journey_id, journey_ids, activity_count)`
  - `compose_demand_claims(activities, *, facts=None, catalog=(), customer_products=(), opportunities=None) -> list[DemandClaim]`
  - `_demand_items` 改为调用 `compose_demand_claims` 再 `as_item()`
  - `_process_change` 返回 `_unique_activity_texts(activities, limit=1)[-1]`（该 helper 取最新），禁止固定套话。立项组原文含「已提交立项材料」，`test_profile_follow_up_process_is_phase_summary_not_one_row_per_activity` 的 `business_change` 断言仍可通过
  - `draft_from_context` 把 context `product_catalog`、客户 `products`、商机列表传入组稿；`source_watermark["product_catalog_names"]` 为启用产品名列表

禁止循环 import：`customer_profile_demand_claims.py` 不得 import `customer_profile_projection_service`。把 `_DEMAND_KEYWORDS`、`_TOPIC_RULES`、`_TOPIC_TITLES`、`_activity_topic`、`_group_activities`、`_unique_activity_texts` 迁到 demand_claims，并自带最小 `_text` / `_activity_text` / `_timeline_sort_key` / `_similar_text`（与 projection_service 现有实现同文）。`projection_service` 从 demand_claims import `compose_demand_claims`、`_group_activities`、`_unique_activity_texts`、`_TOPIC_TITLES`。`_follow_up_process` 留在 projection_service。

组稿产品优先级（规格 6.4）：活动匹配 → 主张内唯一商机产品 → 客户唯一意向产品 → 不写产品名。第 2/3 步句子必须含「客户意向产品」或「商机产品」，不得写成「看到了 {name}」。

`private_solution` 有原文匹配产品时，statement 用：

`跟进记录显示客户对 {name} 感兴趣，公司层面使用需要私有化部署。`

仅当原文出现对应词才追加「安装包」「试用方案」。无产品：`跟进提到私有化或本地部署。`

其它 topic：只把原文里实际出现的关键词写进句子；没有细节就写短分类句，例如 `跟进提到试用或 POC。`，禁止 CTO / 账号已用满 / 轻量交互页面 / 立项材料已提交 / 出差暂缓，除非原文有这些词。

`generic_demand`：`statement = _unique_activity_texts(...)[-1]`。

- [ ] **Step 1: Write failing demand-claim tests**

Create `CRM-Server/tests/unit/test_customer_profile_demand_claims.py`：

```python
from app.services.customer_profile_demand_claims import CatalogProductRef, compose_demand_claims

XIE_XIN = (
    "联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，"
    "在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，"
    "会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，"
    "客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。"
)

HIFOX = CatalogProductRef(public_id="prd_hifox", name="Hifox")
APIFOX = CatalogProductRef(public_id="prd_apifox", name="Apifox")


def test_xiexin_hifox_private_follow_up_does_not_invent_apifox():
    claims = compose_demand_claims(
        [{"id": 1, "content": XIE_XIN, "source_content": XIE_XIN, "occurred_at": "2026-09-16T10:00:00"}],
        catalog=(HIFOX, APIFOX),
    )
    assert len(claims) == 1
    claim = claims[0]
    assert claim.topic == "private_solution"
    assert "Hifox" in claim.statement
    assert "Apifox" not in claim.statement
    assert "安装包" not in claim.statement
    assert "试用方案" not in claim.statement
    assert "重新评估" not in claim.statement
    assert claim.product_public_ids == ("prd_hifox",)


def test_bound_customer_product_is_labeled_intent_not_mentioned():
    claims = compose_demand_claims(
        [{"id": 1, "content": "公司层面需要私有化部署。", "occurred_at": "2026-09-16T10:00:00"}],
        catalog=(HIFOX, APIFOX),
        customer_products=(HIFOX,),
    )
    assert "Hifox" in claims[0].statement
    assert "客户意向" in claims[0].statement
    assert "看到了 Hifox" not in claims[0].statement
    assert "Apifox" not in claims[0].statement


def test_mentioned_hifox_wins_over_customer_apifox_intent():
    claims = compose_demand_claims(
        [{"id": 1, "content": "今天看到了 Hifox，需要私有化部署。", "occurred_at": "2026-09-16T10:00:00"}],
        catalog=(HIFOX, APIFOX),
        customer_products=(APIFOX,),
    )
    assert claims[0].product_public_ids == ("prd_hifox",)
    assert "Apifox" not in claims[0].statement


def test_cto_template_is_not_emitted_without_cto_in_source():
    claims = compose_demand_claims(
        [{"id": 1, "content": "内部先试用两个项目。", "occurred_at": "2026-09-16T10:00:00"}],
        catalog=(),
    )
    assert claims
    assert "CTO" not in claims[0].statement
```

把 `test_profile_demand_items_merge_near_duplicates_and_keep_all_evidence` 的 fixture 改成 Hifox 原文（不要再用「重新评估 Apifox」当正向期望）。断言改为：`topic == private_solution`、`"Hifox" in statement`、`"Apifox" not in statement`。POC 那组活动保留，断言仍含「正式试用」仅当原文有。

- [ ] **Step 2: Run demand-claim tests to verify they fail**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_profile_demand_claims.py -q`

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement `compose_demand_claims`**

新文件只做组稿。匹配活动产品：

```python
def _mentioned_products(text: str, catalog: Sequence[CatalogProductRef]) -> tuple[CatalogProductRef, ...]:
    matched = match_catalog_product(catalog, text)
    return (CatalogProductRef(matched.public_id, matched.name, True),) if matched is not None else ()
```

`CatalogProductRef` 给 `match_catalog_product` 当有 `public_id`/`name`/`is_active` 的对象即可。

主题规则和分组函数按本 Task Interfaces 迁到 `customer_profile_demand_claims.py`。本文件只 import `match_catalog_product`。

`_demand_items`：

```python
def _demand_items(activities, *, facts=None, catalog=(), customer_products=(), opportunities=None):
    claims = compose_demand_claims(
        activities,
        facts=facts,
        catalog=catalog,
        customer_products=customer_products,
        opportunities=opportunities,
    )
    return [claim.as_item() for claim in claims]
```

`DemandClaim.as_item()` 返回现有 item 字典，另含 `claim_status`、`product_public_ids`、`product_names`、`source_quotes`。保留 `status` 字段给前端旧判断句：有产品/私有化时用 `方案仍在评估` 仅当原文有「评估」；否则 `已记录`。不要用旧句「相关部署支持需求已被记录」。

`_process_change`：

```python
def _process_change(topic: str, activities: list[dict[str, object]]) -> str:
    del topic
    texts = _unique_activity_texts(activities, limit=1)
    return texts[-1] if texts else ""
```

`draft_from_context` 组装：

```python
catalog_rows = [
    CatalogProductRef(str(item["public_id"]), str(item["name"]), bool(item.get("is_active", True)))
    for item in _json_dict_list(context.get("product_catalog"))
    if item.get("public_id") and item.get("name")
]
customer_products = [
    CatalogProductRef(str(item["public_id"]), str(item["name"]))
    for item in _json_dict_list(customer.get("products"))
    if item.get("public_id") and item.get("name")
]
demand_items = _demand_items(
    activities,
    facts=facts,
    catalog=catalog_rows,
    customer_products=customer_products,
    opportunities=opportunities,
)
watermark["product_catalog_names"] = [item.name for item in catalog_rows if item.is_active]
```

删除 `_demand_statement` / `_fact_demand_statement` 里全部固定 return 字符串。事实主题若无活动、只有 fact，`statement` 用 fact `content` 原文拼接（已有 `_fact_demand_statement` 的 generic 分支），不要套话。

- [ ] **Step 4: Run demand-claim and updated contract tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_profile_demand_claims.py tests/unit/test_customer_profile_projection_contracts.py::test_profile_demand_items_merge_near_duplicates_and_keep_all_evidence tests/unit/test_customer_profile_projection_contracts.py::test_profile_demand_items_integrate_structured_facts_without_fact_dump tests/unit/test_customer_profile_projection_contracts.py::test_profile_follow_up_process_is_phase_summary_not_one_row_per_activity -q`

Expected: PASS。`business_change` 断言继续用原文「立项材料已提交」（来自活动 3，不是套话函数）。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_profile_demand_claims.py CRM-Server/app/services/customer_profile_projection_service.py CRM-Server/tests/unit/test_customer_profile_demand_claims.py CRM-Server/tests/unit/test_customer_profile_projection_contracts.py
git commit -m "$(cat <<'EOF'
feat(profile): compose demand claims from evidence not templates

EOF
)"
```

---

### Task 3: 证据原文进 registry，出处门禁拒绝无根陈述

**Files:**
- Create: `CRM-Server/app/services/customer_profile_claim_grounding.py`
- Modify: `CRM-Server/app/services/customer_profile_projection_service.py`（`_build_evidence_registry` 写 `snippet`）
- Modify: `CRM-Server/app/services/customer_profile_projection_validator.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_claim_grounding.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_projection_contracts.py`

**Interfaces:**
- Consumes: `CustomerProfileProjectionDraft`、`CustomerProfileProjectionValidationError`
- Produces:
  - `PROFILE_CLAIM_UNGROUNDED = "PROFILE_CLAIM_UNGROUNDED"`
  - `TEMPLATE_PLOT_TERMS = ("安装包", "试用方案", "轻量交互页面", "账号已用满", "向上级CTO汇报", "立项材料已提交", "人员出差")`
  - `assert_claims_grounded(sections, *, evidence_refs, product_catalog_names) -> None`
  - validator `validate_draft` 在现有检查之后调用它
  - registry 活动项带 `snippet`: `_activity_text(item, limit=800)`；事实项 `snippet` 为 fact `content`

扫描：`demand_background.summary`、`items[].statement`、`follow_up_process[].business_change`、`current_situation.summary` 里的产品名。

产品名规则：`product_catalog_names` 里每个名字若出现在陈述（casefold），则必须出现在该对象 `evidence_refs` 对应 snippet 并集，或该 item 的 `product_names`。

情节词：陈述出现 `TEMPLATE_PLOT_TERMS` 之一，则 snippet 并集必须含同一词。

- [ ] **Step 1: Write failing grounding tests**

```python
import pytest
from app.schemas.customer_profile import CustomerProfileSections
from app.services.customer_profile_claim_grounding import (
    PROFILE_CLAIM_UNGROUNDED,
    assert_claims_grounded,
)
from app.services.customer_profile_projection_service import (
    CustomerProfileProjectionDraft,
    CustomerProfileProjectionError,
    CustomerProfileProjectionService,
)
from app.services.customer_profile_projection_validator import (
    CustomerProfileProjectionValidationError,
)

OLD = "客户正在重新评估 Apifox 私有化部署方案，需要私有环境安装包和试用方案。"
QUOTE = "今天看到了 Hifox，需要私有化部署。"


def test_assert_claims_grounded_rejects_apifox_template():
    sections = CustomerProfileSections(
        current_situation={
            "summary": OLD,
            "demand_background": {
                "summary": OLD,
                "items": [{
                    "statement": OLD,
                    "evidence_refs": ["activity:1"],
                    "product_names": [],
                }],
            },
        },
        current_journeys=[],
        important_changes=[],
        long_term_context={},
        follow_up_process=[],
        recorded_follow_ups=[],
    )
    with pytest.raises(CustomerProfileProjectionValidationError) as exc:
        assert_claims_grounded(
            sections,
            evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
            product_catalog_names=["Hifox", "Apifox"],
        )
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_validate_draft_rejects_ungrounded_demand_statement():
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={
                "demand_background": {
                    "summary": OLD,
                    "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
                }
            },
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.validate_draft(draft)
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_xiexin_draft_passes_grounding():
    service = CustomerProfileProjectionService()
    text = (
        "联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，"
        "在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，"
        "会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，"
        "客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。"
    )
    draft = service.draft_from_context(
        context={
            "product_catalog": [
                {"public_id": "prd_hifox", "name": "Hifox", "is_active": True},
                {"public_id": "prd_apifox", "name": "Apifox", "is_active": True},
            ],
            "strong_context": {
                "customer": {"account_name": "成都协鑫数智科技有限责任公司", "products": []},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [{
                    "id": 1,
                    "content": text,
                    "source_content": text,
                    "occurred_at": "2026-09-16T10:00:00",
                    "title": "电话跟进",
                }],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
        },
        source_event_key="repro",
    )
    service.validate_draft(draft)
    item = draft.sections.current_situation["demand_background"]["items"][0]
    assert "Hifox" in item["statement"]
    assert "Apifox" not in item["statement"]
    assert draft.evidence_refs[0]["snippet"]
```

`CustomerProfileProjectionError` 若包装了 validation，断言 `exc.value.code`。

- [ ] **Step 2: Run grounding tests to verify they fail**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_profile_claim_grounding.py -q`

Expected: FAIL。

- [ ] **Step 3: Implement grounding and wire validator + snippets**

`assert_claims_grounded` 遍历 sections dict。收集文本与其邻近 `evidence_refs`。registry map：`evidence_key -> snippet`。

```python
def _fold(value: str) -> str:
    return value.casefold()
```

产品：对每个 catalog 名，若 `_fold(name)` in `_fold(statement)`，则 `any(_fold(name) in _fold(snippet or "") for snippet in quotes)` 或 `name in item.get("product_names") or []`。否则 raise `CustomerProfileProjectionValidationError("档案陈述缺少出处", code=PROFILE_CLAIM_UNGROUNDED)`。

情节词同理。

`_build_evidence_registry` 的 `add(...)` 增加 `snippet` 参数，活动传入 `_activity_text(item)`，事实传入 `_text(item.get("content"))`。

validator：

```python
from app.services.customer_profile_claim_grounding import assert_claims_grounded

names = draft.source_watermark.get("product_catalog_names") if isinstance(draft.source_watermark, dict) else []
assert_claims_grounded(
    sections,
    evidence_refs=draft.evidence_refs,
    product_catalog_names=[str(name) for name in names or [] if str(name).strip()],
)
```

- [ ] **Step 4: Run grounding and xiexin draft tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_profile_claim_grounding.py tests/unit/test_customer_profile_demand_claims.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_profile_claim_grounding.py CRM-Server/app/services/customer_profile_projection_service.py CRM-Server/app/services/customer_profile_projection_validator.py CRM-Server/tests/unit/test_customer_profile_claim_grounding.py
git commit -m "$(cat <<'EOF'
feat(profile): reject ungrounded demand statements at publish

EOF
)"
```

---

### Task 4: 业务状态行与前端拆栏

**Files:**
- Modify: `CRM-Server/app/services/customer_profile_projection_service.py`
- Modify: `CRM-Client/src/components/panels/CustomerProfileContent.vue`
- Test: `CRM-Server/tests/unit/test_customer_profile_projection_contracts.py`
- Test: `CRM-Client/src/components/panels/__tests__/CustomerProfileContent.test.ts`

**Interfaces:**
- Consumes: `active_journeys`、`opportunities`、`contracts`、`_status_label`
- Produces:
  - `_business_status_rows(*, active_journeys, opportunities, contracts) -> list[dict]`
  - `current_situation["business_status_rows"]` 始终为 list，无对象时 `[]`
  - 前端 `currentAssessmentRows` 只 map `business_status_rows`，删除 `demandItems.map`

行规则：

```python
def _business_status_rows(*, active_journeys, opportunities, contracts) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    stages = list(dict.fromkeys(
        _text(item.get("current_stage"), limit=40)
        for item in active_journeys
        if _text(item.get("current_stage"), limit=40)
    ))
    if active_journeys:
        current = f"{len(active_journeys)} 条进行中的业务旅程"
        if stages:
            current += f"，当前阶段主要为{'、'.join(stages)}"
        rows.append({"dimension": "业务旅程", "current": current, "judgement": ""})
    open_opportunities = [item for item in opportunities if str(item.get("status")) in {"0", "FOLLOWING", "None"}]
    if open_opportunities:
        rows.append({
            "dimension": "商业推进",
            "current": f"{len(open_opportunities)} 条跟进中的商机",
            "judgement": "",
        })
    if contracts:
        rows.append({"dimension": "合同", "current": f"{len(contracts)} 份合同记录", "judgement": ""})
    return rows
```

无旅程/商机/合同 → `[]`。禁止从 `demand_items` 生成。

前端：

```typescript
const currentAssessmentRows = computed(() =>
  arrayValue(currentSituation.value['business_status_rows'])
    .map((item) => ({
      dimension: stringValue(item['dimension']) || stringValue(item['label']),
      current: stringValue(item['current']) || stringValue(item['status']),
      judgement: stringValue(item['judgement']) || stringValue(item['assessment'])
    }))
    .filter((row) => row.dimension && (row.current || row.judgement))
)
```

删掉 `topicLabels` 和 `demandItems` 回退，以及用 `opportunities` / `licenseLabel` 补行的逻辑（改由后端 rows 提供；License 不属于本期业务状态）。

- [ ] **Step 1: Write failing backend and frontend tests**

Backend：

```python
def test_draft_without_business_objects_has_empty_status_rows():
    service = CustomerProfileProjectionService()
    draft = service.draft_from_context(
        context={
            "product_catalog": [{"public_id": "prd_hifox", "name": "Hifox", "is_active": True}],
            "strong_context": {
                "customer": {"account_name": "成都协鑫数智科技有限责任公司", "products": []},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [{
                    "id": 1,
                    "content": "今天看到了 Hifox，需要私有化部署。",
                    "source_content": "今天看到了 Hifox，需要私有化部署。",
                    "occurred_at": "2026-09-16T10:00:00",
                }],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
        },
        source_event_key="rows",
    )
    assert draft.sections.current_situation["business_status_rows"] == []
    assert draft.sections.current_situation["demand_background"]["items"]
```

Frontend 在 `CustomerProfileContent.test.ts`：

1. 360 用例的 `current_situation` 增加 `business_status_rows: [{ dimension: '商业推进', current: '1 条跟进中的商机' }]`，继续期望「当前业务状态」。
2. 新增：

```typescript
it('does not reuse demand statements as current business status', () => {
  const wrapper = mountProfile(baseProfile({
    current_situation: {
      demand_background: {
        summary: '跟进记录显示客户对 Hifox 感兴趣，公司层面使用需要私有化部署。',
        items: [{
          topic: 'private_solution',
          statement: '跟进记录显示客户对 Hifox 感兴趣，公司层面使用需要私有化部署。',
        }]
      }
    },
    current_journeys: [],
    important_changes: [],
    long_term_context: {},
    follow_up_process: [],
    recorded_follow_ups: []
  }))
  const text = wrapper.text()
  expect(text).toContain('项目需求背景')
  expect(text).toContain('Hifox')
  expect(text).not.toContain('当前业务状态')
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_profile_projection_contracts.py::test_draft_without_business_objects_has_empty_status_rows -q
cd ../CRM-Client && npx vitest run src/components/panels/__tests__/CustomerProfileContent.test.ts
```

Expected: 后端 FAIL（无 `business_status_rows`）；前端新用例 FAIL（回退仍渲染「当前业务状态」）。

- [ ] **Step 3: Implement rows and remove UI fallback**

`draft_from_context` 的 `current_situation` 增加 `"business_status_rows": _business_status_rows(...)`。改 `CustomerProfileContent.vue` 如上。

- [ ] **Step 4: Run focused tests**

Run: 同 Step 2，外加 `tests/unit/test_customer_profile_claim_grounding.py`。

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_profile_projection_service.py CRM-Server/tests/unit/test_customer_profile_projection_contracts.py CRM-Client/src/components/panels/CustomerProfileContent.vue CRM-Client/src/components/panels/__tests__/CustomerProfileContent.test.ts
git commit -m "$(cat <<'EOF'
fix(profile): stop rendering demand claims as business status

EOF
)"
```

---

### Task 5: 扫掉旧套话测试并做定向回归

**Files:**
- Modify: `CRM-Server/tests/unit/test_customer_profile_projection_contracts.py`（及 grep 到的其它引用）
- 不改生产代码，除非测试暴露漏网套话

**Interfaces:**
- Consumes: Task 2–4 行为
- Produces: 仓库内档案测试不再把 Apifox 套话当正向期望

- [ ] **Step 1: Find leftover canned-copy assertions**

Search `CRM-Server/tests` 和 `CRM-Client`：

- `重新评估 Apifox`
- `账号已用满`
- `向上级CTO`
- `轻量交互页面`
- `立项材料已提交`
- `相关部署支持需求`

把正向 `assert ... in statement` 改成原文断言，或删掉依赖套话的断言。`test_profile_current_situation_summary_prefers_business_state_over_process_label` 不测 demand 套话，可保留。

- [ ] **Step 2: Run the focused profile suite**

```bash
cd CRM-Server && .venv/bin/python -m pytest \
  tests/unit/test_catalog_product_match.py \
  tests/unit/test_customer_intelligence_context_service.py \
  tests/unit/test_customer_profile_demand_claims.py \
  tests/unit/test_customer_profile_claim_grounding.py \
  tests/unit/test_customer_profile_projection_contracts.py -q
cd ../CRM-Client && npx vitest run src/components/panels/__tests__/CustomerProfileContent.test.ts
```

Expected: PASS。

- [ ] **Step 3: Commit leftover test-only fixes if any**

```bash
git add CRM-Server/tests CRM-Client/src/components/panels/__tests__/CustomerProfileContent.test.ts
git commit -m "$(cat <<'EOF'
test(profile): pin demand claims to source products not canned copy

EOF
)"
```

若无文件变化则跳过 commit。

---

## 规格覆盖

| 规格 | 任务 |
|---|---|
| 6.1–6.3 客户/商机/目录进 context | Task 1 |
| 6.4 跟进匹配、绑定产品标注来源 | Task 2 |
| 7 主张组稿、下线套话、`_process_change` | Task 2 |
| 8 出处门禁、snippet、失败码 | Task 3 |
| 9 `business_status_rows`、前端禁止回退 | Task 4 |
| 10 Graph 顺序不变、确定性 compose | 无新节点；Task 2/3 改 compose/validate |
| 11 协鑫数智 / 意向 / 原文优先 / 拒发旧套话 | Task 2、3、4 |
| 不自动 refresh 历史快照 | 无任务，符合非目标 |

## 执行交接

计划写在 `docs/superpowers/plans/2026-09-16-customer-profile-claim-grounding-plan.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个 Task 新开子代理，Task 之间复查
2. **Inline Execution** — 本会话按 executing-plans 逐 Task 做，中间设检查点

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

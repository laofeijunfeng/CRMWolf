from app.services.agent.customer_mentions import explicit_customer_hint_from_message


def test_customer_hint_extracts_customer_fragment_after_new_opportunity_intent():
    hint = explicit_customer_hint_from_message(
        "创建个商机，中移动信息，采购人数是10万，授权模式是买断，采购类型是新购，采购方式是公开招投标。项目金额是5537000元",
        memory_customer_name="东风康明斯发动机有限公司",
    )

    assert hint == "中移动信息"


def test_customer_hint_extracts_customer_before_action():
    hint = explicit_customer_hint_from_message(
        "给中移动信息创建个商机，采购人数是10万",
        memory_customer_name="东风康明斯发动机有限公司",
    )

    assert hint == "中移动信息"


def test_customer_hint_does_not_treat_field_supplement_as_customer():
    hint = explicit_customer_hint_from_message(
        "采购人数是10万，授权模式是买断，采购类型是新购",
        memory_customer_name="东风康明斯发动机有限公司",
    )

    assert hint is None


def test_customer_hint_extracts_lookup_target_without_company_marker():
    hint = explicit_customer_hint_from_message(
        "搜索客户 南银法巴",
        memory_customer_name=None,
    )

    assert hint == "南银法巴"


def test_customer_hint_does_not_extract_generic_lookup_region():
    hint = explicit_customer_hint_from_message(
        "搜索客户 上海",
        memory_customer_name=None,
    )

    assert hint is None

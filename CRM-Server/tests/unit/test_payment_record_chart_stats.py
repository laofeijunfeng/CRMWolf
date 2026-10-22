# ruff: noqa: RUF001
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.payment_record_chart_stats import (
    build_payment_record_chart,
    list_chart_bucket_records,
)

TODAY = date(2026, 10, 20)


def _record(
    *,
    id=1,
    record_number="HK001",
    amount=Decimal("100"),
    payment_date=date(2026, 10, 2),
    license_type="SUBSCRIPTION",
    purchase_type="NEW",
    customer_name="甲",
    contract="present",
    opportunity="present",
    subscription_years=1,
):
    if contract is None:
        plan = SimpleNamespace(contract=None)
    else:
        if opportunity is None:
            opp = None
        elif opportunity == "present":
            opp = SimpleNamespace(purchase_type=purchase_type)
        else:
            opp = opportunity
        customer = None if customer_name is None else SimpleNamespace(account_name=customer_name)
        plan = SimpleNamespace(
            contract=SimpleNamespace(
                license_type=license_type,
                subscription_years=subscription_years,
                opportunity=opp,
                customer=customer,
            )
        )
    return SimpleNamespace(
        id=id,
        record_number=record_number,
        actual_amount=amount,
        payment_date=payment_date,
        payment_plan=plan,
    )


def _card(chart, key):
    return next(card for card in chart["cards"] if card["key"] == key)


def _bucket(card, key):
    return next(bucket for bucket in card["buckets"] if bucket["key"] == key)


def test_groups_license_purchase_amount_and_keeps_blank_rows():
    rows = [
        _record(
            id=1,
            record_number="HK001",
            amount=Decimal("100000"),
            purchase_type="NEW",
            license_type="SUBSCRIPTION",
            payment_date=date(2026, 10, 2),
            customer_name="甲",
        ),
        _record(
            id=2,
            record_number="HK002",
            amount=Decimal("500000"),
            purchase_type="RENEWAL",
            license_type="PERPETUAL",
            payment_date=date(2025, 11, 1),
            customer_name="乙",
        ),
        _record(
            id=3,
            record_number="HK003",
            amount=Decimal("1000000"),
            purchase_type="EXPANSION",
            license_type="SUBSCRIPTION",
            payment_date=date(2024, 5, 1),
            customer_name="丙",
        ),
        _record(
            id=4,
            record_number="HK004",
            amount=Decimal("1000000.01"),
            purchase_type="OTHER",
            license_type="",
            payment_date=date(2026, 11, 1),
            customer_name="丁",
        ),
        _record(
            id=5, record_number="HK005", amount=None, contract=None, payment_date=date(2026, 9, 30), customer_name=None
        ),
    ]
    chart = build_payment_record_chart(rows, today=TODAY)

    assert chart["population"] == 5
    assert [card["key"] for card in chart["cards"]] == [
        "license_type",
        "purchase_type",
        "amount_band",
        "payment_month",
        "arr_ratio",
    ]
    license_card = _card(chart, "license_type")
    assert [bucket["label"] for bucket in license_card["buckets"]] == ["订阅", "买断", "未填写"]
    assert [bucket["count"] for bucket in license_card["buckets"]] == [2, 1, 2]
    assert sum(bucket["count"] for bucket in license_card["buckets"]) == 5

    purchase = _card(chart, "purchase_type")
    assert [bucket["label"] for bucket in purchase["buckets"]] == ["新购", "续购", "增购", "未填写"]
    assert _bucket(purchase, "EXPANSION")["count"] == 1
    assert _bucket(purchase, "blank")["count"] == 2
    assert sum(bucket["count"] for bucket in purchase["buckets"]) == 5

    amount = _card(chart, "amount_band")
    assert [bucket["label"] for bucket in amount["buckets"]] == [
        "10 万以下",
        "10–50 万",
        "50–100 万",
        "100 万以上",
    ]
    assert [bucket["count"] for bucket in amount["buckets"]] == [2, 1, 1, 1]
    assert sum(bucket["count"] for bucket in amount["buckets"]) == 5


def test_exact_boundaries_fall_into_the_lower_band():
    rows = [
        _record(id=1, amount=Decimal("100000")),
        _record(id=2, amount=Decimal("100000.01")),
        _record(id=3, amount=Decimal("500000")),
        _record(id=4, amount=Decimal("500000.01")),
        _record(id=5, amount=Decimal("1000000")),
        _record(id=6, amount=Decimal("1000000.01")),
    ]
    amount = _card(build_payment_record_chart(rows, today=TODAY), "amount_band")
    assert _bucket(amount, "under_100k")["count"] == 1
    assert _bucket(amount, "100k_500k")["count"] == 2
    assert _bucket(amount, "500k_1m")["count"] == 2
    assert _bucket(amount, "over_1m")["count"] == 1


def test_month_window_is_oldest_first_and_drops_older_and_future_rows():
    rows = [
        _record(id=1, payment_date=date(2025, 10, 31), amount=Decimal("10")),
        _record(id=2, payment_date=date(2025, 11, 1), amount=Decimal("20")),
        _record(id=3, payment_date=date(2026, 10, 31), amount=Decimal("30")),
        _record(id=4, payment_date=date(2026, 11, 1), amount=Decimal("40")),
    ]
    chart = build_payment_record_chart(rows, today=TODAY)
    month = _card(chart, "payment_month")
    assert [bucket["key"] for bucket in month["buckets"]] == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    assert month["buckets"][0]["label"] == "11月"
    assert month["buckets"][-1]["label"] == "10月"
    assert "更早" not in [bucket["label"] for bucket in month["buckets"]]
    assert sum(bucket["count"] for bucket in month["buckets"]) == 2
    assert _bucket(month, "2025-11")["count"] == 1
    assert _bucket(month, "2026-10")["count"] == 1
    assert chart["population"] == 4
    assert sum(bucket["count"] for bucket in _card(chart, "license_type")["buckets"]) == 4


def test_zero_purchase_bucket_stays_and_preview_is_capped():
    rows = [
        _record(id=index, record_number=f"HK{index:03d}", purchase_type="NEW", amount=Decimal("10"))
        for index in range(1, 7)
    ]
    purchase = _card(build_payment_record_chart(rows, today=TODAY), "purchase_type")
    expansion = _bucket(purchase, "EXPANSION")
    assert expansion["count"] == 0
    assert expansion["label"] == "增购"
    new = _bucket(purchase, "NEW")
    assert new["preview_total"] == 6
    assert [item["id"] for item in new["preview"]] == [1, 2, 3, 4, 5]
    assert new["preview"][0]["customer_name"] == "甲"
    assert new["preview"][0]["payment_date"] == date(2026, 10, 2)
    total, listed = list_chart_bucket_records(rows, "purchase_type", "NEW", today=TODAY)
    assert total == 6
    assert [item["id"] for item in listed] == [1, 2, 3, 4, 5, 6]


def test_missing_contract_and_opportunity_are_blank_and_bucket_rejects_unknown():
    rows = [
        _record(id=8, contract=None),
        _record(id=9, opportunity=None, license_type="SUBSCRIPTION"),
    ]
    chart = build_payment_record_chart(rows, today=TODAY)
    license_card = _card(chart, "license_type")
    purchase = _card(chart, "purchase_type")
    assert _bucket(license_card, "blank")["count"] == 1
    assert _bucket(license_card, "SUBSCRIPTION")["count"] == 1
    assert _bucket(purchase, "blank")["count"] == 2
    with pytest.raises(ValueError, match="未知图表"):
        list_chart_bucket_records(rows, "approval", "blank", today=TODAY)
    with pytest.raises(ValueError, match="图表分段不存在"):
        list_chart_bucket_records(rows, "payment_month", "earlier", today=TODAY)


def test_amount_ratio_uses_half_up_and_descriptions_stay_factual():
    rows = [
        _record(id=1, amount=Decimal("1"), license_type="SUBSCRIPTION"),
        _record(id=2, amount=Decimal("1"), license_type="PERPETUAL"),
        _record(id=3, amount=Decimal("1"), license_type="SUBSCRIPTION"),
    ]
    chart = build_payment_record_chart(rows, today=TODAY)
    license_card = _card(chart, "license_type")
    assert _bucket(license_card, "SUBSCRIPTION")["amount_ratio"] == 67
    assert _bucket(license_card, "PERPETUAL")["amount_ratio"] == 33
    assert license_card["description"] == "按回款金额看订阅和买断。没关联到的单独列出。"
    assert _card(chart, "payment_month")["description"] == "最近 12 个月，每个月回了多少。更早的不在这张图上。"
    assert _bucket(license_card, "blank")["count"] == 0


def test_arr_ratio_annualizes_subscription_and_keeps_buyout_whole():
    rows = [
        _record(
            id=1,
            amount=Decimal("300000"),
            subscription_years=3,
            license_type="SUBSCRIPTION",
            payment_date=date(2026, 10, 2),
        ),
        _record(
            id=2,
            amount=Decimal("100000"),
            subscription_years=1,
            license_type="SUBSCRIPTION",
            payment_date=date(2026, 10, 3),
        ),
        _record(
            id=3,
            amount=Decimal("120000"),
            subscription_years=2,
            license_type="SUBSCRIPTION",
            payment_date=date(2026, 10, 4),
        ),
        _record(
            id=4,
            amount=Decimal("200000"),
            license_type="PERPETUAL",
            subscription_years=5,
            payment_date=date(2026, 10, 5),
        ),
    ]
    october = _bucket(_card(build_payment_record_chart(rows, today=TODAY), "arr_ratio"), "2026-10")
    assert october["plotted_ratio"] == 57
    assert october["annualized_subscription"] == 260000
    assert october["buyout_amount"] == 200000
    assert october["amount"] == 720000
    assert [item["amount"] for item in october["preview"]] == [300000, 100000, 120000, 200000]


def test_arr_ratio_excludes_prepaid_years_from_both_sides():
    rows = [
        _record(id=1, amount=Decimal("300000"), subscription_years=3, license_type="SUBSCRIPTION"),
        _record(id=2, amount=Decimal("200000"), license_type="PERPETUAL"),
    ]
    october = _bucket(_card(build_payment_record_chart(rows, today=TODAY), "arr_ratio"), "2026-10")
    assert october["plotted_ratio"] == 33
    assert october["annualized_subscription"] == 100000
    assert october["buyout_amount"] == 200000


def test_arr_ratio_breaks_empty_months_and_drops_excluded_rows():
    rows = [
        _record(id=1, amount=Decimal("200000"), license_type="PERPETUAL", payment_date=date(2026, 4, 2)),
        _record(id=2, contract=None, amount=Decimal("900000"), payment_date=date(2026, 10, 2)),
        _record(
            id=3,
            license_type="SUBSCRIPTION",
            subscription_years=None,
            amount=Decimal("300000"),
            payment_date=date(2026, 10, 3),
        ),
        _record(
            id=4,
            license_type="SUBSCRIPTION",
            subscription_years=0,
            amount=Decimal("100000"),
            payment_date=date(2026, 10, 4),
        ),
        _record(id=5, license_type="", amount=Decimal("50000"), payment_date=date(2026, 10, 5)),
        _record(
            id=6,
            license_type="SUBSCRIPTION",
            subscription_years=3,
            amount=Decimal("300000"),
            payment_date=date(2026, 5, 2),
            opportunity=SimpleNamespace(subscription_years=1, purchase_type="NEW"),
        ),
    ]
    chart = build_payment_record_chart(rows, today=TODAY)
    arr = _card(chart, "arr_ratio")
    assert arr["title"] == "ARR 占比"
    assert arr["description"] == (
        "和回款月份同一种面积加线。纵轴是占比。没有回款的月份也连过去，不写成 0%。只有买断落到 0%。"
    )
    assert _card(chart, "payment_month")["description"] == "最近 12 个月，每个月回了多少。更早的不在这张图上。"
    february = _bucket(arr, "2026-02")
    assert february["plotted_ratio"] is None
    assert february["count"] == 0
    assert february["preview"] == []
    april = _bucket(arr, "2026-04")
    assert april["plotted_ratio"] == 0
    assert april["annualized_subscription"] == 0
    assert april["buyout_amount"] == 200000
    assert [item["id"] for item in april["preview"]] == [1]
    october = _bucket(arr, "2026-10")
    assert october["plotted_ratio"] is None
    assert october["count"] == 0
    may = _bucket(arr, "2026-05")
    assert may["plotted_ratio"] == 100
    assert may["annualized_subscription"] == 100000
    april_total, april_listed = list_chart_bucket_records(rows, "arr_ratio", "2026-04", today=TODAY)
    assert april_total == 1
    assert [item["id"] for item in april_listed] == [1]
    assert list_chart_bucket_records(rows, "arr_ratio", "2026-10", today=TODAY) == (0, [])
    assert list_chart_bucket_records(rows, "arr_ratio", "2026-02", today=TODAY) == (0, [])


def test_bucket_window_orders_payment_date_newest_first_and_keeps_total():
    rows = [
        _record(id=1, record_number="HK001", payment_date=date(2026, 10, 1), purchase_type="NEW"),
        _record(id=2, record_number="HK002", payment_date=date(2026, 10, 9), purchase_type="NEW"),
        _record(id=3, record_number="HK000", payment_date=None, purchase_type="NEW"),
        _record(id=4, record_number="HK003", payment_date=None, purchase_type="NEW"),
    ]

    total, first = list_chart_bucket_records(rows, "purchase_type", "NEW", today=TODAY, skip=0, limit=2)
    _total, second = list_chart_bucket_records(rows, "purchase_type", "NEW", today=TODAY, skip=2, limit=2)

    assert total == 4
    assert [item["id"] for item in first] == [2, 1]
    assert [item["record_number"] for item in second] == ["HK000", "HK003"]

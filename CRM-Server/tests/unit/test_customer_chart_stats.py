from datetime import date, datetime
from types import SimpleNamespace

from app.services.customer_chart_stats import build_customer_chart, list_chart_bucket_customers
from app.services.customer_derived_status import CustomerDerivedStatus, DerivedCustomerStatus


class _Query:
    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return []


class _Db:
    def query(self, *_args, **_kwargs):
        return _Query()


def _customer(**overrides):
    values = {
        "id": 1,
        "team_id": 7,
        "public_id": "cus_1",
        "account_name": "甲",
        "owner_id": "3",
        "industry": "software",
        "city": "上海",
        "company_scale": "1-50人",
        "license_expiry_date": None,
        "license_type": None,
        "created_time": datetime(2026, 10, 2),
        "status": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_rows(monkeypatch, statuses):
    def fake_derive(_db, team_id, customers):
        assert team_id == 7
        derived = {}
        for index, customer in enumerate(customers):
            if index >= len(statuses):
                break
            derived[int(customer.id)] = DerivedCustomerStatus(statuses[index])
        return derived

    monkeypatch.setattr(
        "app.services.customer_chart_stats.derive_customer_statuses_for_list",
        fake_derive,
    )
    monkeypatch.setattr(
        "app.services.customer_chart_stats._industry_names",
        lambda _db, codes: {code: code for code in codes if code},
    )
    monkeypatch.setattr(
        "app.services.customer_chart_stats._owner_names",
        lambda _db, _ids: {"3": "王明"},
    )


def _card(chart, key):
    return next(card for card in chart["cards"] if card["key"] == key)


def test_status_license_and_scale_cover_every_customer(monkeypatch):
    _patch_rows(monkeypatch, [
        CustomerDerivedStatus.FOLLOWING,
        CustomerDerivedStatus.PUBLIC_POOL,
        CustomerDerivedStatus.WON,
    ])
    customers = [
        _customer(id=1, public_id="cus_1", license_expiry_date=date(2026, 12, 1), license_type="OFFICIAL"),
        _customer(id=2, public_id="cus_2", account_name="乙", company_scale=None, city=""),
        _customer(id=3, public_id="cus_3", account_name="丙", company_scale="  ", license_expiry_date=date(2020, 1, 1)),
    ]

    chart = build_customer_chart(_Db(), 7, customers, today=date(2026, 10, 16))

    assert chart["population"] == 3
    status = _card(chart, "status")
    assert sum(bucket["count"] for bucket in status["buckets"]) == 3
    assert [bucket["label"] for bucket in status["buckets"]] == [
        "未启动", "跟进中", "复购中", "已成交", "已流失", "公海", "未填写",
    ]
    assert _card(chart, "license")["buckets"][0]["count"] == 1
    assert _card(chart, "license")["buckets"][1]["count"] == 1
    assert sum(bucket["count"] for bucket in _card(chart, "scale")["buckets"]) == 3
    assert _card(chart, "scale")["buckets"][-1]["count"] == 2


def test_named_charts_keep_top_eight_other_and_blank_without_merging_cities(monkeypatch):
    statuses = [CustomerDerivedStatus.NOT_STARTED] * 12
    _patch_rows(monkeypatch, statuses)
    customers = []
    industries = ["软件", "制造", "教育", "金融", "医疗", "零售", "物流", "能源", "农业", "交通", "传媒"]
    for index, industry in enumerate(industries):
        customers.append(_customer(
            id=index + 1,
            public_id=f"cus_{index + 1}",
            account_name=f"客户{index:02d}",
            industry=industry,
            city="上海" if index < 2 else "上海市",
        ))
    customers.append(_customer(id=12, public_id="cus_12", account_name="空行业", industry=None, city=None))

    chart = build_customer_chart(_Db(), 7, customers, today=date(2026, 10, 16))
    industry = _card(chart, "industry")
    city = _card(chart, "city")

    assert [bucket["label"] for bucket in industry["buckets"][:8]] == [
        "交通", "传媒", "农业", "制造", "医疗", "教育", "物流", "能源",
    ]
    assert industry["buckets"][-2]["label"] == "其他"
    assert industry["buckets"][-2]["count"] == 3
    assert industry["buckets"][-1] == {
        "key": "blank",
        "label": "未填写",
        "count": 1,
        "ratio": 8,
        "preview": [{"id": "cus_12", "name": "空行业", "owner_name": "王明"}],
        "preview_total": 1,
    }
    assert [bucket["label"] for bucket in city["buckets"] if bucket["count"]] == ["上海市", "上海", "未填写"]
    assert sum(bucket["count"] for bucket in industry["buckets"]) == 12
    assert sum(bucket["count"] for bucket in city["buckets"]) == 12


def test_created_month_keeps_six_months_oldest_first(monkeypatch):
    _patch_rows(monkeypatch, [CustomerDerivedStatus.FOLLOWING, CustomerDerivedStatus.FOLLOWING])
    customers = [
        _customer(id=1, created_time=datetime(2026, 10, 3)),
        _customer(id=2, public_id="cus_old", account_name="老客户", created_time=datetime(2025, 1, 1)),
    ]

    chart = build_customer_chart(_Db(), 7, customers, today=date(2026, 10, 16))
    months = _card(chart, "created_month")["buckets"]

    assert [bucket["key"] for bucket in months] == [
        "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
    ]
    assert [bucket["label"] for bucket in months] == ["5月", "6月", "7月", "8月", "9月", "10月"]
    assert months[-1]["count"] == 1
    assert sum(bucket["count"] for bucket in months) == 1


def test_other_bucket_lists_every_overflow_customer(monkeypatch):
    _patch_rows(monkeypatch, [CustomerDerivedStatus.FOLLOWING] * 9)
    customers = [
        _customer(
            id=index + 1,
            public_id=f"cus_{index + 1}",
            account_name=f"客户{index:02d}",
            industry=f"行业{index:02d}",
        )
        for index in range(9)
    ]

    listed = list_chart_bucket_customers(_Db(), 7, customers, "industry", "other", today=date(2026, 10, 16))

    assert [item["name"] for item in listed] == ["客户08"]


    _patch_rows(monkeypatch, [CustomerDerivedStatus.FOLLOWING, CustomerDerivedStatus.FOLLOWING])
    customers = [_customer(team_id=8), _customer(id=2, public_id="cus_2", account_name="本团队")]
    chart = build_customer_chart(_Db(), 7, customers, today=date(2026, 10, 16))

    assert chart["population"] == 1
    assert _card(chart, "status")["buckets"][1]["preview"][0]["id"] == "cus_2"

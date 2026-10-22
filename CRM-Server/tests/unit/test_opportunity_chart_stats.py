from datetime import date
from types import SimpleNamespace

from app.services.opportunity_chart_stats import build_opportunity_chart, list_chart_bucket_opportunities


class _Db:
    """Rows expose their display names directly; no database lookup is needed."""


def _opportunity(**overrides):
    values = {
        "id": 1,
        "team_id": 7,
        "public_id": "opp-01",
        "opportunity_name": "Alpha",
        "customer_name": "客户甲",
        "owner_name": "王明",
        "product_name": "P01",
        "status": 0,
        "purchase_type": "NEW",
        "license_type": "SUBSCRIPTION",
        "total_amount": 100_000,
        "win_probability": 0,
        "expected_closing_date": date(2026, 10, 3),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rows():
    return [
        _opportunity(
            id=1,
            public_id="opp-01",
            opportunity_name="Alpha",
            product_name="P01",
            total_amount=100_000,
            win_probability=0,
            expected_closing_date=date(2026, 10, 3),
        ),
        _opportunity(
            id=2,
            public_id="opp-02",
            opportunity_name="Beta",
            product_name="P02",
            status=1,
            purchase_type="RENEWAL",
            license_type="PERPETUAL",
            total_amount=500_000,
            win_probability=49,
            expected_closing_date=date(2026, 11, 5),
        ),
        _opportunity(
            id=3,
            public_id="opp-03",
            opportunity_name="Gamma",
            product_name="P03",
            status=2,
            purchase_type="EXPANSION",
            total_amount=1_000_000,
            win_probability=50,
            expected_closing_date=date(2026, 12, 1),
        ),
        _opportunity(
            id=4,
            public_id="opp-04",
            opportunity_name="Delta",
            product_name="P04",
            total_amount=1_000_001,
            win_probability=79,
            expected_closing_date=date(2027, 1, 10),
        ),
        _opportunity(
            id=5,
            public_id="opp-05",
            opportunity_name="Epsilon",
            product_name="P05",
            status=1,
            purchase_type="RENEWAL",
            total_amount=10,
            win_probability=80,
            expected_closing_date=date(2027, 2, 2),
        ),
        _opportunity(
            id=6,
            public_id="opp-06",
            opportunity_name="Zeta",
            product_name="P06",
            status=2,
            purchase_type="EXPANSION",
            license_type="PERPETUAL",
            total_amount=2_000_000,
            win_probability=99,
            expected_closing_date=date(2027, 3, 8),
        ),
        _opportunity(
            id=7,
            public_id="opp-07",
            opportunity_name="Eta",
            product_name="P07",
            total_amount=25,
            win_probability=100,
            expected_closing_date=date(2027, 4, 1),
        ),
        _opportunity(
            id=8,
            public_id="opp-08",
            opportunity_name="Theta",
            product_name="P08",
            status=1,
            purchase_type="RENEWAL",
            license_type="PERPETUAL",
            total_amount=300_000,
            win_probability=20,
            expected_closing_date=None,
        ),
        _opportunity(
            id=9,
            public_id="opp-09",
            opportunity_name="Iota",
            product_name="P09",
            status=2,
            purchase_type="EXPANSION",
            total_amount=600_000,
            win_probability=60,
            expected_closing_date=date(2026, 9, 30),
        ),
        _opportunity(
            id=10,
            public_id="opp-10",
            opportunity_name="Kappa",
            product_name="P10",
            status=0,
            total_amount=700_000,
            win_probability=25,
            expected_closing_date=date(2026, 10, 20),
        ),
        _opportunity(
            id=11,
            public_id="opp-11",
            opportunity_name="Lambda",
            product_name="P11",
            status=0,
            total_amount=800_000,
            win_probability=40,
            expected_closing_date=date(2026, 11, 20),
        ),
        _opportunity(
            id=12,
            public_id="opp-12",
            opportunity_name="Mu",
            product_name="P12",
            status=2,
            purchase_type="EXPANSION",
            total_amount=900_000,
            win_probability=70,
            expected_closing_date=date(2026, 12, 20),
        ),
        _opportunity(
            id=13,
            public_id="opp-13",
            opportunity_name="Nu",
            product_name=None,
            status=2,
            purchase_type="EXPANSION",
            total_amount=1_200_000,
            win_probability=90,
            expected_closing_date=date(2027, 1, 20),
        ),
        _opportunity(
            id=14,
            public_id="opp-14",
            opportunity_name="Alpha",
            product_name="P08",
            total_amount=50,
            win_probability=25,
            expected_closing_date=date(2026, 10, 25),
        ),
        _opportunity(
            id=15,
            team_id=8,
            public_id="opp-outside",
            opportunity_name="Outside",
            product_name="P01",
            total_amount=9_999,
            win_probability=100,
            expected_closing_date=date(2026, 10, 1),
        ),
    ]


def _card(chart, key):
    return next(card for card in chart["cards"] if card["key"] == key)


def _bucket(card, label):
    return next(bucket for bucket in card["buckets"] if bucket["label"] == label)


def test_build_opportunity_chart_covers_all_cards_boundaries_ratios_and_previews():
    chart = build_opportunity_chart(_Db(), 7, _rows(), today=date(2026, 10, 16))

    assert chart["total_amount"] == 9_100_086
    assert [card["key"] for card in chart["cards"]] == [
        "status",
        "purchase_type",
        "license_type",
        "amount_band",
        "product",
        "win_probability",
        "expected_closing_month",
    ]

    status = _card(chart, "status")

    assert [bucket["label"] for bucket in status["buckets"]] == ["跟进中", "已赢单", "已输单"]
    assert [bucket["count"] for bucket in status["buckets"]] == [6, 3, 5]
    assert [bucket["ratio"] for bucket in status["buckets"]] == [43, 21, 36]
    assert [bucket["amount_ratio"] for bucket in status["buckets"]] == [29, 9, 63]
    assert [item["id"] for item in status["buckets"][0]["preview"]] == [
        "opp-01", "opp-14", "opp-04", "opp-07", "opp-10",
    ]

    purchase = _card(chart, "purchase_type")
    assert [bucket["label"] for bucket in purchase["buckets"]] == ["新购", "续购", "增购"]
    assert [bucket["count"] for bucket in purchase["buckets"]] == [6, 3, 5]
    assert [bucket["amount_ratio"] for bucket in purchase["buckets"]] == [29, 9, 63]

    license_type = _card(chart, "license_type")
    assert [bucket["label"] for bucket in license_type["buckets"]] == ["订阅", "买断"]
    assert [bucket["count"] for bucket in license_type["buckets"]] == [11, 3]
    assert [bucket["amount_ratio"] for bucket in license_type["buckets"]] == [69, 31]

    amount_band = _card(chart, "amount_band")
    assert [bucket["label"] for bucket in amount_band["buckets"]] == [
        "10 万以下", "10\u201350 万", "50\u2013100 万", "100 万以上",
    ]
    assert [bucket["count"] for bucket in amount_band["buckets"]] == [4, 2, 5, 3]
    assert [bucket["amount"] for bucket in amount_band["buckets"]] == [
        100_085, 800_000, 4_000_000, 4_200_001,
    ]

    product = _card(chart, "product")
    assert [bucket["label"] for bucket in product["buckets"]] == [
        "P08", "P01", "P02", "P03", "P04", "P05", "P06", "P07", "其他", "未填写",
    ]
    assert [bucket["count"] for bucket in product["buckets"]] == [2, 1, 1, 1, 1, 1, 1, 1, 4, 1]
    assert product["buckets"][0]["amount"] == 300_050
    assert product["buckets"][-2]["amount"] == 3_000_000

    win_probability = _card(chart, "win_probability")
    assert [bucket["label"] for bucket in win_probability["buckets"]] == [
        "0\u201349%", "50\u201379%", "80\u201399%", "100%",
    ]
    assert [bucket["count"] for bucket in win_probability["buckets"]] == [6, 4, 3, 1]

    closing = _card(chart, "expected_closing_month")
    assert [bucket["key"] for bucket in closing["buckets"]] == [
        "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "unscheduled",
    ]
    assert [bucket["count"] for bucket in closing["buckets"]] == [3, 2, 2, 2, 1, 1, 1]
    assert sum(bucket["count"] for bucket in closing["buckets"]) == 12

    expected_preview = {
        "id": "opp-01",
        "name": "Alpha",
        "customer_name": "客户甲",
        "owner_name": "王明",
        "amount": 100_000,
        "expected_closing_date": "2026-10-03",
    }
    assert status["buckets"][0]["preview"][0] == expected_preview
    assert len(status["buckets"][0]["preview"]) == 5
    assert status["buckets"][0]["preview_total"] == 6
    for card in chart["cards"]:
        for bucket in card["buckets"]:
            assert set(bucket) == {
                "key", "label", "count", "amount", "ratio", "amount_ratio", "preview", "preview_total",
            }
            for preview in bucket["preview"]:
                assert set(preview) == {
                    "id", "name", "customer_name", "owner_name", "amount", "expected_closing_date",
                }


def test_list_chart_bucket_opportunities_returns_only_product_overflow_rows():
    total, listed = list_chart_bucket_opportunities(
        _Db(),
        7,
        _rows(),
        "product",
        "other",
        today=date(2026, 10, 16),
    )

    assert total == 4
    assert [item["id"] for item in listed] == ["opp-09", "opp-10", "opp-11", "opp-12"]
    assert [item["name"] for item in listed] == ["Iota", "Kappa", "Lambda", "Mu"]
    assert all(item["id"] != "opp-outside" and item["id"] != "opp-13" for item in listed)


def test_list_chart_bucket_opportunities_returns_all_matching_rows_not_preview_limit():
    rows = [
        *_rows(),
        _opportunity(id=16, public_id="opp-16", opportunity_name="Nu-2"),
        _opportunity(id=17, public_id="opp-17", opportunity_name="Nu-3"),
    ]

    total, listed = list_chart_bucket_opportunities(
        _Db(),
        7,
        rows,
        "status",
        "0",
        today=date(2026, 10, 16),
        limit=20,
    )

    assert total == 8
    assert len(listed) == 8
def test_product_ranking_is_computed_once_per_chart_request(monkeypatch):
    from app.services import opportunity_chart_stats

    calls = 0
    original = opportunity_chart_stats._product_segments

    def tracked(rows):
        nonlocal calls
        calls += 1
        return original(rows)

    monkeypatch.setattr(opportunity_chart_stats, "_product_segments", tracked)
    rows = [_opportunity(id=index, public_id=f"opp-{index}", product_name=f"P{index % 9}") for index in range(200)]

    build_opportunity_chart(_Db(), 7, rows, today=date(2026, 10, 16))
    assert calls == 1

    calls = 0
    list_chart_bucket_opportunities(_Db(), 7, rows, "product", "other", today=date(2026, 10, 16))
    assert calls == 1


class _BatchQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_conditions):
        return self

    def all(self):
        return self.rows


class _BatchLookupDb:
    def __init__(self):
        self.models = []

    def query(self, model):
        self.models.append(model.__name__)
        if model.__name__ == "Customer":
            return _BatchQuery([SimpleNamespace(id=101, account_name="批量客户")])
        return _BatchQuery([SimpleNamespace(id=42, name="批量负责人")])


def test_build_opportunity_chart_batches_missing_preview_names():
    row = _opportunity(
        customer_name=None,
        owner_name=None,
        customer_id=101,
        owner_id="42",
    )
    db = _BatchLookupDb()

    chart = build_opportunity_chart(db, 7, [row], today=date(2026, 10, 16))

    assert db.models == ["Customer", "User"]
    preview = chart["cards"][0]["buckets"][0]["preview"][0]
    assert preview["customer_name"] == "批量客户"
    assert preview["owner_name"] == "批量负责人"


def test_bucket_window_orders_created_time_newest_first():
    rows = [
        _opportunity(id=1, public_id="opp-a", opportunity_name="早", status=0, created_time=date(2026, 1, 2)),
        _opportunity(id=2, public_id="opp-b", opportunity_name="晚", status=0, created_time=date(2026, 9, 2)),
        _opportunity(id=3, public_id="opp-c", opportunity_name="中", status=0, created_time=date(2026, 5, 2)),
    ]

    total, listed = list_chart_bucket_opportunities(
        _Db(), 7, rows, "status", "0", today=date(2026, 10, 16), skip=0, limit=2,
    )

    assert total == 3
    assert [item["name"] for item in listed] == ["晚", "中"]

from datetime import date
from types import SimpleNamespace

from app.services.contract_chart_stats import build_contract_chart, list_chart_bucket_contracts

TODAY = date(2026, 10, 20)


def _contract(**overrides):
    values = {
        "id": 1,
        "team_id": 7,
        "contract_name": "合同甲",
        "customer_id": 11,
        "customer_name": "客户甲",
        "owner_id": "9",
        "owner_name": "王明",
        "opportunity_id": 21,
        "purchase_type": "NEW",
        "license_type": "SUBSCRIPTION",
        "total_amount": 100_000,
        "signing_date": date(2026, 10, 3),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _card(payload, key):
    return next(card for card in payload["cards"] if card["key"] == key)


def _bucket(card, key):
    return next(bucket for bucket in card["buckets"] if bucket["key"] == key)


def test_population_matches_visible_contracts_and_keeps_drafts():
    rows = [
        _contract(id=1, total_amount=5_200_000, purchase_type="NEW", signing_date=date(2026, 10, 2)),
        _contract(
            id=2,
            license_type="PERPETUAL",
            total_amount=3_400_000,
            purchase_type="RENEWAL",
            signing_date=date(2026, 5, 2),
        ),
        _contract(id=3, team_id=8, total_amount=9_999_999),
    ]

    payload = build_contract_chart(object(), 7, rows, today=TODAY)

    assert payload["population"] == 2
    assert payload["total_amount"] == 8_600_000
    assert [card["key"] for card in payload["cards"]] == [
        "license_type",
        "purchase_type",
        "amount_band",
        "signing_month",
    ]
    license_card = _card(payload, "license_type")
    assert sum(bucket["count"] for bucket in license_card["buckets"]) == 2
    assert _bucket(license_card, "SUBSCRIPTION")["amount"] == 5_200_000
    assert _bucket(license_card, "PERPETUAL")["amount"] == 3_400_000


def test_missing_purchase_type_stays_visible_as_blank():
    rows = [
        _contract(id=1, opportunity_id=21, purchase_type="NEW"),
        _contract(id=2, opportunity_id=22, purchase_type=None),
        _contract(id=3, opportunity_id=None, purchase_type=None),
        _contract(id=4, opportunity_id=24, purchase_type="UNKNOWN"),
    ]

    card = _card(build_contract_chart(object(), 7, rows, today=TODAY), "purchase_type")

    assert [bucket["key"] for bucket in card["buckets"]] == ["NEW", "RENEWAL", "EXPANSION", "blank"]
    assert _bucket(card, "blank")["count"] == 3
    assert _bucket(card, "RENEWAL")["count"] == 0
    assert sum(bucket["count"] for bucket in card["buckets"]) == 4


def test_amount_boundaries_use_contract_amount():
    rows = [
        _contract(id=1, total_amount=100_000),
        _contract(id=2, total_amount=100_000.01),
        _contract(id=3, total_amount=500_000),
        _contract(id=4, total_amount=1_000_000),
        _contract(id=5, total_amount=1_000_000.01),
    ]

    card = _card(build_contract_chart(object(), 7, rows, today=TODAY), "amount_band")

    assert _bucket(card, "under_100k")["count"] == 1
    assert _bucket(card, "100k_500k")["count"] == 2
    assert _bucket(card, "500k_1m")["count"] == 1
    assert _bucket(card, "over_1m")["count"] == 1
    assert sum(bucket["count"] for bucket in card["buckets"]) == 5


def test_signing_month_keeps_earlier_unsigned_and_future_apart():
    rows = [
        _contract(id=1, signing_date=date(2026, 4, 30)),
        _contract(id=2, signing_date=date(2026, 5, 1)),
        _contract(id=3, signing_date=date(2026, 10, 31)),
        _contract(id=4, signing_date=None),
        _contract(id=5, signing_date=date(2026, 11, 1)),
    ]

    card = _card(build_contract_chart(object(), 7, rows, today=TODAY), "signing_month")

    assert [bucket["label"] for bucket in card["buckets"]][:2] == ["更早", "5月"]
    assert [bucket["key"] for bucket in card["buckets"][-2:]] == ["future", "unsigned"]
    assert _bucket(card, "earlier")["count"] == 1
    assert _bucket(card, "2026-05")["count"] == 1
    assert _bucket(card, "2026-10")["count"] == 1
    assert _bucket(card, "unsigned")["count"] == 1
    assert _bucket(card, "future")["count"] == 1
    assert sum(bucket["count"] for bucket in card["buckets"]) == 5


def test_bucket_list_returns_the_whole_segment_and_rejects_unknown_keys():
    rows = [_contract(id=index, contract_name=f"合同{index}", purchase_type=None) for index in range(1, 7)]

    listed = list_chart_bucket_contracts(object(), 7, rows, "purchase_type", "blank", today=TODAY)
    preview = _bucket(_card(build_contract_chart(object(), 7, rows, today=TODAY), "purchase_type"), "blank")

    assert len(listed) == 6
    assert preview["preview_total"] == 6
    assert len(preview["preview"]) == 5
    try:
        list_chart_bucket_contracts(object(), 7, rows, "status", "DRAFT", today=TODAY)
    except ValueError as exc:
        assert str(exc) == "未知图表"
    else:
        raise AssertionError("unknown chart was accepted")


class _Row:
    def __init__(self, **values):
        self.__dict__.update(values)


class _Query:
    def __init__(self, items):
        self.items = items
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def all(self):
        return self.items


class _Db:
    def __init__(self, opportunities):
        self.opportunities = opportunities
        self.queries = []

    def query(self, model):
        query = _Query(self.opportunities if model.__name__ == "Opportunity" else [])
        query.model_name = model.__name__
        self.queries.append(query)
        return query


def test_purchase_type_is_read_from_the_same_team_only():
    rows = [_Row(
        id=1,
        team_id=7,
        contract_name="合同甲",
        customer_id=11,
        customer_name="客户甲",
        owner_id="9",
        owner_name="王明",
        opportunity_id=21,
        license_type="SUBSCRIPTION",
        total_amount=100_000,
        signing_date=date(2026, 10, 3),
    )]
    opportunity = _Row(id=21, team_id=7, purchase_type="EXPANSION")
    db = _Db([opportunity])

    card = _card(build_contract_chart(db, 7, rows, today=TODAY), "purchase_type")

    assert _bucket(card, "EXPANSION")["count"] == 1
    opportunity_query = next(query for query in db.queries if query.model_name == "Opportunity")
    rendered = " ".join(str(item) for item in opportunity_query.criteria)
    assert "team_id" in rendered
    assert "crm_opportunities.id" in rendered or "opportunity" in rendered.lower() or "IN" in rendered

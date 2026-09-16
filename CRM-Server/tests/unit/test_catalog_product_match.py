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

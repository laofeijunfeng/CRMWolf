from app.constants.business_types import (
    BusinessType, ALL_BUSINESS_TYPES, BUSINESS_TYPE_DISPLAY_NAMES, is_valid_business_type
)

def test_business_type_constants():
    assert BusinessType.CONTRACT == "CONTRACT"
    assert BusinessType.PAYMENT == "PAYMENT"
    assert BusinessType.INVOICE == "INVOICE"

def test_all_business_types():
    assert set(ALL_BUSINESS_TYPES) == {"CONTRACT", "PAYMENT", "INVOICE"}

def test_display_names():
    for bt in ALL_BUSINESS_TYPES:
        assert bt in BUSINESS_TYPE_DISPLAY_NAMES
    assert BUSINESS_TYPE_DISPLAY_NAMES["PAYMENT"] == "回款登记"

def test_is_valid():
    assert is_valid_business_type("CONTRACT") is True
    assert is_valid_business_type("UNKNOWN") is False
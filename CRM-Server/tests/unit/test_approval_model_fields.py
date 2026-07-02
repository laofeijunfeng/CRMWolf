from app.models.approval import Approval
from app.constants.business_types import BusinessType

def test_approval_has_business_columns():
    cols = {c.name for c in Approval.__table__.columns}
    assert "business_type" in cols
    assert "business_id" in cols
    assert "contract_id" in cols  # 保留兼容

def test_approval_business_type_default():
    bt_col = Approval.__table__.columns.business_type
    assert bt_col.default is not None
    assert bt_col.default.arg == BusinessType.CONTRACT

def test_approval_business_index():
    idx_names = {idx.name for idx in Approval.__table__.indexes}
    assert "idx_approval_business" in idx_names

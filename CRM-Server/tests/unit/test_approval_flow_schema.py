# tests/unit/test_approval_flow_schema.py
import pytest
from pydantic import ValidationError

from app.schemas.approval import ApprovalFlowCreate


def test_approval_flow_create_requires_business_type():
    """ApprovalFlowCreate 必须显式传 business_type。"""
    from app.schemas.approval import ApprovalNodeCreate

    node = ApprovalNodeCreate(
        node_name="测试节点",
        node_code="TEST_NODE",
        node_order=1,
        approve_role="SALES_DIRECTOR"
    )

    with pytest.raises(ValidationError):
        ApprovalFlowCreate(
            flow_name="测试流程",
            flow_code="TEST",
            nodes=[node]
        )


def test_approval_flow_create_custom_business_type():
    """ApprovalFlowCreate 可自定义 business_type"""
    from app.schemas.approval import ApprovalNodeCreate

    node = ApprovalNodeCreate(
        node_name="回款审批",
        node_code="PAYMENT_NODE",
        node_order=1,
        approve_role="FINANCE"
    )

    schema = ApprovalFlowCreate(
        flow_name="回款审批流程",
        flow_code="PAYMENT_FLOW",
        business_type="PAYMENT",
        nodes=[node]
    )

    assert schema.business_type == "PAYMENT"


def test_approval_flow_create_license_business_type():
    """ApprovalFlowCreate 支持 License 审批流程。"""
    from app.schemas.approval import ApprovalNodeCreate

    node = ApprovalNodeCreate(
        node_name="License审批",
        node_code="LICENSE_NODE",
        node_order=1,
        approve_role="SALES_DIRECTOR"
    )

    schema = ApprovalFlowCreate(
        flow_name="License审批流程",
        flow_code="LICENSE_FLOW",
        business_type="LICENSE",
        nodes=[node]
    )

    assert schema.business_type == "LICENSE"


def test_approval_flow_create_invalid_business_type_rejected():
    """ApprovalFlowCreate 非法 business_type 直接报错。"""
    from app.schemas.approval import ApprovalNodeCreate

    node = ApprovalNodeCreate(
        node_name="测试",
        node_code="TEST",
        node_order=1,
        approve_role="SALES_DIRECTOR"
    )

    with pytest.raises(ValidationError):
        ApprovalFlowCreate(
            flow_name="测试",
            flow_code="TEST",
            business_type="UNKNOWN_TYPE",
            nodes=[node]
        )


def test_approval_flow_update_has_optional_business_type():
    """ApprovalFlowUpdate 必须有可选 business_type 字段"""
    from app.schemas.approval import ApprovalFlowUpdate

    schema = ApprovalFlowUpdate(business_type="PAYMENT")
    assert schema.business_type == "PAYMENT"

    schema_empty = ApprovalFlowUpdate()
    assert schema_empty.business_type is None


def test_approval_flow_response_has_business_type():
    """ApprovalFlowResponse 必须返回 business_type"""
    from app.schemas.approval import ApprovalFlowResponse
    from datetime import datetime

    fields = ApprovalFlowResponse.model_fields
    assert "business_type" in fields

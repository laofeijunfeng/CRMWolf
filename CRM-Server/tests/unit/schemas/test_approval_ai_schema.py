import json

from app.schemas.approval_ai import ApprovalAIParsedFlow, ApprovalAIParsedNode


def test_float_amount_serialization():
    """float 金额在无需 SSEJsonEncoder 的情况下可被 JSON 序列化。"""
    flow = ApprovalAIParsedFlow(
        flow_name="测试流程",
        flow_code="TEST",
        description="测试描述",
        min_amount=100000.0,  # float
        max_amount=500000.0,  # float
        nodes=[
            ApprovalAIParsedNode(
                node_name="审批节点",
                node_code="TEST_NODE",
                node_order=1,
                approve_role="SALES_DIRECTOR",
            )
        ],
    )

    # 未实现 to_sse_dict 前会抛 AttributeError；实现后应可被 json 直接序列化
    sse_dict = flow.to_sse_dict()
    json_str = json.dumps(sse_dict)

    assert json_str is not None
    assert "100000" in json_str
    assert "500000" in json_str


def test_null_amount_allowed():
    """null 金额应被允许。"""
    flow = ApprovalAIParsedFlow(
        flow_name="测试",
        flow_code="TEST",
        min_amount=None,
        max_amount=None,
        nodes=[
            ApprovalAIParsedNode(
                node_name="审批节点",
                node_code="TEST_NODE",
                node_order=1,
                approve_role="SALES_DIRECTOR",
            )
        ],
    )

    sse_dict = flow.to_sse_dict()
    assert sse_dict["min_amount"] is None
    assert sse_dict["max_amount"] is None
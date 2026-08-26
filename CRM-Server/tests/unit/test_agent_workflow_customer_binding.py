import pytest

from app.services.agent.query.schemas import EntityRef
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.workflow.customer_binding import bind_workflow_customer

CONTEXT_CUSTOMER = EntityRef(
    ref_id="eref_customer_cus_context_001",
    resource="customer",
    public_id="cus_context_001",
    display_name="上下文客户有限公司",
)


def semantic(
    *,
    customer_name: str | None = None,
    customer_source: str = "NONE",
    intent: str = "CUSTOMER_ACTIVITY",
    invoice_title: dict[str, object] | None = None,
) -> AgentSemanticParseResult:
    return AgentSemanticParseResult.model_validate(
        {
            "intent": intent,
            "customer": {
                "name_text": customer_name,
                "resolution_source": customer_source,
            },
            "invoice_title": invoice_title or {},
        }
    )


def test_explicit_customer_mention_wins_over_context_and_action_field() -> None:
    binding = bind_workflow_customer(
        semantic=semantic(
            customer_name="用户明确客户有限公司",
            customer_source="EXPLICIT",
            intent="CREATE_INVOICE_TITLE",
            invoice_title={
                "title_type": "COMPANY",
                "title": "发票法律主体有限公司",
            },
        ),
        trusted_context_customer=CONTEXT_CUSTOMER,
        selected_customer_id=None,
    )

    assert binding.lookup_name == "用户明确客户有限公司"
    assert binding.trusted_context_customer == CONTEXT_CUSTOMER
    assert [item.source for item in binding.name_evidence] == ["USER_EXPLICIT", "ACTION_FIELD"]


def test_canonical_context_wins_over_action_field_fallback() -> None:
    binding = bind_workflow_customer(
        semantic=semantic(
            intent="CREATE_INVOICE_TITLE",
            invoice_title={
                "title_type": "COMPANY",
                "title": "发票法律主体有限公司",
            },
        ),
        trusted_context_customer=CONTEXT_CUSTOMER,
        selected_customer_id=None,
    )

    assert binding.lookup_name is None
    assert binding.trusted_context_customer == CONTEXT_CUSTOMER


def test_semantic_contract_rejects_model_claimed_session_memory() -> None:
    with pytest.raises(ValueError, match="resolution_source"):
        semantic(customer_name="模型猜测客户有限公司", customer_source="MEMORY")


def test_company_invoice_title_is_last_resort_customer_identity_evidence() -> None:
    binding = bind_workflow_customer(
        semantic=semantic(
            intent="CREATE_INVOICE_TITLE",
            invoice_title={
                "title_type": "COMPANY",
                "title": "广州凡亚信息科技有限公司",
            },
        ),
        trusted_context_customer=None,
        selected_customer_id=None,
    )

    assert binding.lookup_name == "广州凡亚信息科技有限公司"
    assert binding.trusted_context_customer is None
    assert [item.field_path for item in binding.name_evidence] == ["invoice_title.title"]


def test_personal_invoice_title_is_not_customer_identity_evidence() -> None:
    binding = bind_workflow_customer(
        semantic=semantic(
            intent="CREATE_INVOICE_TITLE",
            invoice_title={
                "title_type": "PERSONAL",
                "title": "张三",
            },
        ),
        trusted_context_customer=None,
        selected_customer_id=None,
    )

    assert binding.lookup_name is None
    assert binding.name_evidence == ()


def test_invoice_title_is_ignored_for_unrelated_intent() -> None:
    binding = bind_workflow_customer(
        semantic=semantic(
            intent="CREATE_CONTACT",
            invoice_title={
                "title_type": "COMPANY",
                "title": "不应被绑定的公司有限公司",
            },
        ),
        trusted_context_customer=None,
        selected_customer_id=None,
    )

    assert binding.lookup_name is None
    assert binding.name_evidence == ()

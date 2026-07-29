"""CRM agent business rule tests."""
from __future__ import annotations

from app.services.agent import business_rules


def test_extract_customer_candidates_limits_and_normalizes_items():
    data = {
        "items": [
            {
                "id": index,
                "account_name": f"客户{index}",
                "owner_info": {"id": index + 100},
            }
            for index in range(12)
        ]
        + ["bad"],
    }

    candidates = business_rules.extract_customer_candidates(data)

    assert len(candidates) == 10
    assert candidates[0] == {
        "id": 0,
        "account_name": "客户0",
        "owner_info": {"id": 100},
        "collaborator_infos": [],
    }


def test_creation_duplicate_keywords_deduplicates_normalized_name():
    assert business_rules.creation_duplicate_keywords("广州越秀金融有限公司") == [
        "广州越秀金融有限公司",
        "广州越秀金融",
    ]
    assert business_rules.creation_duplicate_keywords("越秀金融") == ["越秀金融"]


def test_build_creation_duplicate_response_includes_visible_and_hidden_matches():
    response = business_rules.build_creation_duplicate_response({
        "customers": [{"account_name": "越秀金融"}, {"account_name": "越秀资本"}],
        "leads": [{"lead_name": "越秀项目"}],
        "hidden_customer_count": 1,
        "hidden_lead_count": 0,
    })

    assert response == "已存在：客户 「越秀金融」、「越秀资本」、线索 「越秀项目」、团队内客户。"


def test_missing_opportunity_fields_respects_subscription_and_procurement_requirement():
    fields = business_rules.missing_opportunity_fields(
        {
            "total_amount": 100000,
            "user_count": 20,
            "license_type": "SUBSCRIPTION",
            "purchase_type": "NEW",
            "expected_closing_date": "2026-08-01",
        },
        require_procurement_method=True,
    )

    assert fields == ["procurement_method_id", "subscription_years"]


def test_resolve_customer_member_handles_existing_member_and_single_candidate():
    business_context = {
        "member_candidates": {
            "items": [
                {"id": 8, "name": "张三", "already_member": False},
                {"id": 9, "name": "李四", "already_member": True},
            ],
        },
    }

    resolved, error = business_rules.resolve_customer_member(
        {"user_name": "张三", "member_role": "SALES", "access_level": "EDIT"},
        business_context,
    )
    assert error is None
    assert resolved == {
        "user_id": 8,
        "member_role": "SALES",
        "access_level": "EDIT",
        "user_name": "张三",
    }

    _, existing_error = business_rules.resolve_customer_member(
        {"user_name": "李四"},
        business_context,
    )
    assert existing_error == "「李四」已经是这个客户的负责人或成员，不需要重复添加。"


def test_payment_payload_builders_keep_api_contract_shape():
    payment = {
        "actual_amount": 1200,
        "actual_payer_name": "越秀金融",
        "payment_date_iso": "2026-07-29",
        "notes": "首款",
    }

    assert business_rules.payment_record_payload({"id": 3}, payment, "7") == {
        "payment_plan_id": 3,
        "actual_amount": 1200,
        "payment_date": "2026-07-29",
        "actual_payer_name": "越秀金融",
        "commission_member_id": "7",
        "notes": "首款",
    }
    assert business_rules.payment_plan_payload({"id": 4}, payment, "7") == {
        "contract_id": 4,
        "stage_name": "AI登记回款计划",
        "planned_amount": 1200,
        "due_date": "2026-07-29",
        "notes": "首款",
        "pending_payment_record": {
            "actual_amount": 1200,
            "payment_date": "2026-07-29",
            "actual_payer_name": "越秀金融",
            "commission_member_id": "7",
            "notes": "首款",
        },
    }

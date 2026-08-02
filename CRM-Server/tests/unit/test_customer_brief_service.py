from __future__ import annotations

from app.services.customer_brief_service import CustomerBriefService


def test_customer_brief_service_builds_degraded_brief_from_business_context() -> None:
    context = {
        "customer": {
            "source_id": "1",
            "account_name": "广州测试科技有限公司",
            "city": "广州",
            "company_scale": "100-499人",
            "source": "客户推荐",
            "industry_code": "software",
            "industry_name": "软件服务",
        },
        "contacts": [
            {
                "source_id": "2",
                "name": "张总",
                "position": "总经理",
                "is_primary": True,
                "is_decision_maker": True,
            }
        ],
        "opportunities": [
            {
                "source_id": "3",
                "id": 301,
                "name": "研发平台采购",
                "stage": "POC",
                "status": 0,
                "amount": 120000,
                "user_count": 80,
                "expected_closing_date": "2026-12-31",
            }
        ],
        "follow_ups": [
            {
                "source_id": "4",
                "content": "张总反馈今天开始 POC，预计月底确认采购预算。",
                "next_action": "准备 POC 支撑材料并确认预算范围",
            }
        ],
        "same_industry_customers": ["同行客户 A"],
        "citation_map": {},
    }

    brief = CustomerBriefService()._build_degraded_brief(context)
    markdown = CustomerBriefService()._render_markdown(brief)

    assert brief["generation_mode"] == "business_data_fallback"
    assert "广州测试科技有限公司" in markdown
    assert "当前已记录 1 位联系人" in markdown
    assert "POC" in markdown
    assert "准备 POC 支撑材料" in markdown


def test_customer_brief_markdown_does_not_render_internal_industry_code() -> None:
    service = CustomerBriefService()
    context = {
        "customer": {
            "source_id": "1",
            "account_name": "广州公共服务中心",
            "industry_code": "government_public",
            "industry_name": "政府/公共机构",
        },
        "citation_map": {},
    }
    brief = service._normalize_brief(
        {
            "overview": {
                "industry": {"content": "government_public", "citations": ["1"]},
                "similar_customers": {"items": ["同行客户 A"], "citations": ["1"]},
            },
            "opportunity_summaries": [],
        },
        context,
    )
    markdown = service._render_markdown(brief)

    assert "### 同行业客户" in markdown
    assert "政府/公共机构" in markdown
    assert "同行客户 A" in markdown
    assert "government_public" not in markdown

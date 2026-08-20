from app.services.agent.read_query_presenters import work_summary_tool_response


def test_work_summary_presenter_uses_new_coverage_contract_without_raw_facts():
    response = work_summary_tool_response({
        "narrative": {"answer": "", "coverage": {"available_total": 7}},
        "coverage": {"available_total": 7},
        "facts": {"available_total": 99},
    })

    assert response == "已查询到 7 条可确认工作事实，但暂时没有生成可展示的总结。"


def test_work_summary_presenter_can_read_coverage_from_validated_outcome():
    response = work_summary_tool_response({
        "narrative": {"answer": "", "coverage": {"available_total": 3}},
    })

    assert response == "已查询到 3 条可确认工作事实，但暂时没有生成可展示的总结。"

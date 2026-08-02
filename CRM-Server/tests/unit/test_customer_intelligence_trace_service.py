from app.services.customer_intelligence_trace_service import visible_trace_events


def test_visible_trace_events_projects_business_steps_without_internal_names():
    events = visible_trace_events({
        "visible_trace": [
            {"title": " 读取客户上下文 ", "content": " 已读取客户智能上下文 "},
            {"title": "customer_intelligence_graph", "content": ""},
            {"title": "制定更新计划", "content": "本次用于回答客户问题"},
        ]
    })

    assert events == [
        {
            "event": "agent_step",
            "step": "customer_intelligence",
            "status": "completed",
            "content": "读取客户上下文：已读取客户智能上下文",
        },
        {
            "event": "agent_step",
            "step": "customer_intelligence",
            "status": "completed",
            "content": "制定更新计划：本次用于回答客户问题",
        },
    ]

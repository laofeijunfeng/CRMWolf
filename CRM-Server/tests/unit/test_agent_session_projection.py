from types import SimpleNamespace

from app.services.agent.session_projection import (
    project_session_runtime,
    with_current_customer,
)


def test_session_runtime_projection_normalizes_current_customer_memory():
    session = SimpleNamespace(
        context_json={
            "current_customer": {
                "id": 17,
                "account_name": "广州睿狐科技有限公司",
                "created_time": object(),
            },
        },
    )

    projection = project_session_runtime(session)

    assert projection.session_context["current_customer"]["id"] == 17
    assert projection.current_customer == {
        "id": 17,
        "account_name": "广州睿狐科技有限公司",
        "created_time": str(session.context_json["current_customer"]["created_time"]),
    }


def test_session_runtime_projection_ignores_non_customer_context():
    projection = project_session_runtime(SimpleNamespace(context_json={"view": "agent"}))

    assert projection.session_context == {}
    assert projection.current_customer == {}


def test_session_projection_persists_current_customer_without_runtime_objects():
    context = with_current_customer(
        {"theme": "dark"},
        {
            "id": 17,
            "account_name": "广州睿狐科技有限公司",
            "owner_info": {"id": object()},
            "collaborator_infos": [{"id": 1}, object()],
        },
    )

    assert context["theme"] == "dark"
    assert context["current_customer"] == {
        "id": 17,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": str(context["current_customer"]["owner_info"]["id"])},
        "collaborator_infos": [{"id": 1}, str(context["current_customer"]["collaborator_infos"][1])],
    }

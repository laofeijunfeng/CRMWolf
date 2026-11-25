from types import SimpleNamespace


def test_enqueue_opportunity_loss_side_effects_preserves_business_payload(monkeypatch):
    from app.services import opportunity_loss_side_effect_service as service

    calls = []
    opportunity = SimpleNamespace(
        id=17,
        team_id=3,
        customer_id=29,
        owner_id="41",
        opportunity_name="年度续费项目",
    )
    customer = SimpleNamespace(account_name="北方科技")

    monkeypatch.setattr(
        service.customer_business_object_intelligence_service,
        "build_change",
        lambda *args, **kwargs: calls.append(("build", args, kwargs)) or "change",
    )
    monkeypatch.setattr(
        service.customer_business_object_intelligence_service,
        "enqueue_change_refresh_after_commit",
        lambda change: calls.append(("refresh", change)),
    )
    monkeypatch.setattr(service.customer_crud, "get_by_id", lambda *args: customer)
    monkeypatch.setattr(
        service.outbound_notification_job_service,
        "queue_committed",
        lambda db, **kwargs: calls.append(("notify", kwargs)),
    )

    service.enqueue_opportunity_loss_side_effects(
        object(), opportunity, actor_id="41", loss_reason="预算冻结"
    )

    assert calls[0][0] == "build"
    assert calls[0][2] == {
        "source_type": "opportunity",
        "business_object": opportunity,
        "change_type": "updated",
        "actor_id": "41",
    }
    assert calls[1] == ("refresh", "change")
    assert calls[2] == (
        "notify",
        {
            "team_id": 3,
            "event_type": service.OutboundNotificationEventType.OPPORTUNITY_LOST,
            "business_type": "OPPORTUNITY",
            "business_id": 17,
            "recipient_user_ids": ["41"],
            "actor_id": "41",
            "payload_json": {
                "opportunity_name": "年度续费项目",
                "customer_name": "北方科技",
                "loss_reason": "预算冻结",
            },
        },
    )

import pytest

from app.services.reminder_rule_dsl import describe_reminder_rule, validate_reminder_rule


def rule(**overrides):
    payload = {
        "object_type": "opportunity",
        "trigger": "schedule",
        "status": "FOLLOWING",
        "inactive_days": 7,
        "require_no_new_activity": True,
        "recipients": ["owner", "user:8"],
        "message_template": "{商机名称} 在{当前阶段}已停留 {天数} 天，期间没有新的客户活动。",  # noqa: RUF001
        "channels": ["in_app", "feishu"],
    }
    payload.update(overrides)
    return payload


def test_opportunity_stage_silence_rule_is_accepted():
    assert validate_reminder_rule(rule()) == []


def test_follow_up_due_date_rule_is_accepted():
    errors = validate_reminder_rule(
        rule(
            object_type="follow_up_task",
            trigger="date",
            status="OPEN",
            date_field="due_at",
            offset_days=0,
            inactive_days=None,
            require_no_new_activity=False,
            recipients=["owner"],
            message_template="{任务标题} 今天到期，仍待处理。",  # noqa: RUF001
        )
    )
    assert errors == []


def test_unknown_role_recipient_is_rejected():
    errors = validate_reminder_rule(rule(recipients=["sales_manager"]))
    assert any("销售经理" in error for error in errors)


def test_explicit_team_member_recipient_is_accepted():
    assert validate_reminder_rule(rule(recipients=["owner", "user:8"])) == []


def test_schedule_without_inactivity_window_is_rejected():
    errors = validate_reminder_rule(rule(inactive_days=None))
    assert any("天数" in error for error in errors)


def test_recipient_must_belong_to_the_object():
    errors = validate_reminder_rule(rule(object_type="payment_plan", recipients=["submitter"]))
    assert any("提交人" in error for error in errors)


def test_message_template_cannot_reference_unknown_field():
    errors = validate_reminder_rule(rule(message_template="{合同编号}已停留 {天数} 天"))
    assert any("合同编号" in error for error in errors)


def test_description_reads_as_one_sentence():
    sentence = describe_reminder_rule(rule())
    assert sentence == "当跟进中的商机进入当前阶段满 7 天，且期间没有新的客户活动，通知负责人和指定成员。"  # noqa: RUF001


@pytest.mark.parametrize("channels", [[], ["email"]])
def test_channels_stay_inside_existing_delivery_options(channels):
    assert validate_reminder_rule(rule(channels=channels)) != []


def test_business_journey_inactivity_rule_is_accepted():
    payload = {
        "object_type": "business_journey",
        "trigger": "schedule",
        "inactive_days": 7,
        "offset_days": 0,
        "trigger_time": "09:00",
        "conditions": [{"field": "status", "operator": "in", "value": ["ACTIVE", "WON"]}],
        "recipients": ["primary_opportunity_owner", "customer_owner", "customer_members", "user:8"],
        "message_title": "业务旅程已连续 {静默天数} 天无新动态",
        "message_template": "{客户名称} 的业务旅程「{业务旅程名称}」已连续 {静默天数} 天无新动态。",
        "channels": ["feishu"],
        "notify_once_per_window": True,
    }
    assert validate_reminder_rule(payload) == []


def test_business_journey_rejects_unknown_condition_field():
    payload = {
        "object_type": "business_journey",
        "trigger": "schedule",
        "inactive_days": 7,
        "offset_days": 0,
        "trigger_time": "09:00",
        "conditions": [{"field": "updated_time", "operator": "older_than_days", "value": 7}],
        "recipients": ["customer_owner"],
        "message_title": "提醒",
        "message_template": "旅程停滞",
        "channels": ["feishu"],
    }
    assert validate_reminder_rule(payload) != []


@pytest.mark.parametrize("trigger_time", ["08:30", "09:15", "19:30", "20:00"])
def test_business_journey_rejects_unsupported_trigger_time(trigger_time):
    payload = {
        "object_type": "business_journey",
        "trigger": "schedule",
        "inactive_days": 7,
        "offset_days": 0,
        "trigger_time": trigger_time,
        "conditions": [{"field": "status", "operator": "in", "value": ["ACTIVE"]}],
        "recipients": ["customer_owner"],
        "message_title": "提醒",
        "message_template": "旅程停滞",
        "channels": ["feishu"],
    }
    assert validate_reminder_rule(payload) != []


def test_business_journey_accepts_all_canonical_status_values():
    payload = {
        "object_type": "business_journey",
        "trigger": "schedule",
        "inactive_days": 7,
        "offset_days": 0,
        "trigger_time": "09:00",
        "conditions": [
            {
                "field": "status",
                "operator": "in",
                "value": ["ACTIVE", "WON", "LOST", "COMPLETED", "ARCHIVED"],
            }
        ],
        "recipients": ["customer_owner"],
        "message_title": "提醒",
        "message_template": "旅程停滞",
        "channels": ["feishu"],
    }
    assert validate_reminder_rule(payload) == []


@pytest.mark.parametrize("invalid_status", ["UNKNOWN", {"unexpected": "value"}])
def test_business_journey_rejects_unknown_status_value(invalid_status):
    payload = {
        "object_type": "business_journey",
        "trigger": "schedule",
        "inactive_days": 7,
        "offset_days": 0,
        "trigger_time": "09:00",
        "conditions": [{"field": "status", "operator": "in", "value": [invalid_status]}],
        "recipients": ["customer_owner"],
        "message_title": "提醒",
        "message_template": "旅程停滞",
        "channels": ["feishu"],
    }
    assert validate_reminder_rule(payload) != []


def test_v2_catalog_conditions_are_exact_and_supported_for_all_objects():
    from app.services.reminder_rule_dsl import reminder_rule_catalog

    catalog = reminder_rule_catalog()
    assert {item["object_type"] for item in catalog} == {
        "business_journey",
        "opportunity",
        "customer",
        "lead",
        "follow_up_task",
        "approval",
        "payment_plan",
    }
    for object_spec in catalog:
        status = next(field for field in object_spec["fields"] if field["value"] == "status")
        payload = rule(
            version=2,
            object_type=object_spec["object_type"],
            trigger="schedule",
            status=None,
            inactive_days=None,
            date_field=None,
            offset_days=0,
            require_no_new_activity=False,
            trigger_time="09:30",
            recipients=[object_spec["recipients"][0]["value"]],
            message_title="提醒",
            message_template="提醒",
            channels=["feishu"],
            conditions=[{"field": "status", "operator": "in", "value": [status["options"][0]["value"]]}],
        )
        assert validate_reminder_rule(payload) == [], object_spec["object_type"]
        assert validate_reminder_rule({**payload, "conditions": []})
        assert validate_reminder_rule({**payload, "trigger": "change"})
        assert validate_reminder_rule({**payload, "conditions": [*payload["conditions"], *payload["conditions"]]})
        for invalid in (
            {"field": "status", "operator": "in", "value": []},
            {"field": "status", "operator": "in", "value": ["UNKNOWN"]},
            {"field": "status", "operator": "older_than_days", "value": 0},
            {"field": "status", "operator": "in", "value": [status["options"][0]["value"]], "extra": 1},
            {"field": "unknown", "operator": "not_empty", "value": True},
        ):
            assert validate_reminder_rule({**payload, "conditions": [invalid]})
        for field in object_spec["fields"]:
            if field["value"] == "status":
                continue
            for operator in field["operators"]:
                value = True if operator["value"] == "not_empty" else 0
                assert (
                    validate_reminder_rule(
                        {
                            **payload,
                            "conditions": [{"field": field["value"], "operator": operator["value"], "value": value}],
                        }
                    )
                    == []
                )
            if any(op["value"] == "older_than_days" for op in field["operators"]):
                assert validate_reminder_rule(
                    {**payload, "conditions": [{"field": field["value"], "operator": "older_than_days", "value": True}]}
                )
                assert validate_reminder_rule(
                    {**payload, "conditions": [{"field": field["value"], "operator": "older_than_days", "value": -1}]}
                )


def test_legacy_rule_does_not_acquire_v2_condition_requirements():
    assert validate_reminder_rule(rule()) == []
    assert validate_reminder_rule(rule(version=1)) == []

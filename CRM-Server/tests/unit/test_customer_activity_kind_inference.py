from app.services.agent.follow_up_fields import _customer_activity_create_payload
from app.services.customer_activity_kinds import CustomerActivityKind, infer_activity_kind, normalize_activity_kind


MEETING_VISIT_CONTENT = """今天线下拜访广州睿狐科技
2026-07-29 时间：10:30-12:00
我方：Harry、Rayson
对接方：12号人，整个公司研发+测试预计50+人
会议内容：
1、系统化介绍公司的基本信息；
2、演示讲解产品功能；
备注：
客户需要内部深度拿1-2个项目试用。
下一步计划：
跟进内部积极试用，推动上级汇报，把项目扩大；
"""


def test_infer_activity_kind_treats_structured_offline_visit_as_offline_meeting():
    assert infer_activity_kind("线下拜访", MEETING_VISIT_CONTENT) == CustomerActivityKind.OFFLINE_MEETING


def test_normalize_activity_kind_maps_plain_offline_visit_to_visit_follow_up():
    assert normalize_activity_kind("线下拜访") == CustomerActivityKind.VISIT_FOLLOW_UP


def test_infer_activity_kind_treats_online_exchange_as_online_meeting():
    assert (
        infer_activity_kind("线上交流", "今天和客户线上交流了项目进展")
        == CustomerActivityKind.ONLINE_MEETING
    )


def test_agent_customer_activity_payload_keeps_raw_content_for_meeting_visit():
    payload = _customer_activity_create_payload(
        17,
        {
            "method": "线下拜访",
            "content": MEETING_VISIT_CONTENT,
            "next_action": "跟进内部积极试用，推动上级汇报",
        },
        quality=type("Quality", (), {"suggested_revision": "压缩后的建议稿"})(),
    )

    assert payload["activity_kind"] == CustomerActivityKind.OFFLINE_MEETING
    assert payload["source_content"] == MEETING_VISIT_CONTENT

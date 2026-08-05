from datetime import datetime

from app.api.leads import _build_lead_follow_up_response
from app.models.lead import FollowUpMethod
from app.schemas.lead import LeadFollowUpCreate


class ExpiredLikeFollowUp:
    __slots__ = (
        "id",
        "content",
        "method",
        "next_follow_time",
        "next_action",
        "creator_id",
        "created_time",
    )

    def __init__(self):
        self.id = 17
        self.content = "客户表示项目搁置了，后续有需要再联系"
        self.method = FollowUpMethod.PHONE
        self.next_follow_time = datetime(2026, 9, 8)
        self.next_action = None
        self.creator_id = "3"
        self.created_time = datetime(2026, 8, 5, 11, 36, 58)


def test_build_lead_follow_up_response_reads_attributes_not_instance_dict():
    response = _build_lead_follow_up_response(
        ExpiredLikeFollowUp(),
        "lead_0b9bce14b74744ceb762a068babc5add",
    )

    assert response.id == 17
    assert response.lead_id == "lead_0b9bce14b74744ceb762a068babc5add"
    assert response.content == "客户表示项目搁置了，后续有需要再联系"
    assert response.method == FollowUpMethod.PHONE
    assert response.next_follow_time == datetime(2026, 9, 8)
    assert response.creator_id == "3"


def test_lead_follow_up_create_accepts_date_only_next_follow_time():
    payload = LeadFollowUpCreate(
        content="客户表示项目搁置了，后续有需要再联系",
        method=FollowUpMethod.PHONE,
        next_follow_time="2026-09-08",
        next_action=None,
    )

    assert payload.next_follow_time == datetime(2026, 9, 8)

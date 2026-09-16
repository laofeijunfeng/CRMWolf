import pytest

from app.models.lead import FollowUpMethod
from app.services.agent.workflow.write_enums import (
    UnmappedLeadFollowUpMethod,
    canonicalize_company_scale,
    canonicalize_lead_follow_up_method,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, FollowUpMethod.OTHER),
        ("", FollowUpMethod.OTHER),
        ("  ", FollowUpMethod.OTHER),
        ("电话", FollowUpMethod.PHONE),
        ("PHONE", FollowUpMethod.PHONE),
        ("phone", FollowUpMethod.PHONE),
        ("电话联系", FollowUpMethod.PHONE),
        ("电话沟通", FollowUpMethod.PHONE),
        ("来电", FollowUpMethod.PHONE),
        ("微信", FollowUpMethod.WECHAT),
        ("WECHAT", FollowUpMethod.WECHAT),
        ("wechat", FollowUpMethod.WECHAT),
        ("拜访", FollowUpMethod.VISIT),
        ("VISIT", FollowUpMethod.VISIT),
        ("邮件", FollowUpMethod.EMAIL),
        ("EMAIL", FollowUpMethod.EMAIL),
        ("email", FollowUpMethod.EMAIL),
        ("其他", FollowUpMethod.OTHER),
        ("OTHER", FollowUpMethod.OTHER),
        ("other", FollowUpMethod.OTHER),
        ("会议", FollowUpMethod.OTHER),
        ("线上会议", FollowUpMethod.OTHER),
        ("线下会议", FollowUpMethod.OTHER),
        ("视频会议", FollowUpMethod.OTHER),
    ],
)
def test_canonicalize_lead_follow_up_method(raw, expected):
    assert canonicalize_lead_follow_up_method(raw) is expected


def test_unmapped_lead_follow_up_method_raises():
    with pytest.raises(UnmappedLeadFollowUpMethod) as exc:
        canonicalize_lead_follow_up_method("传真")
    assert exc.value.raw == "传真"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("10~29", "1-50人"),
        ("10-29", "1-50人"),
        ("15人左右", "1-50人"),
        ("1-50人", "1-50人"),
        ("51-200人", "51-200人"),
        ("SCALE_1_50", "1-50人"),
        ("无法识别的规模", None),
    ],
)
def test_canonicalize_company_scale(raw, expected):
    assert canonicalize_company_scale(raw) == expected

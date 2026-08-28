"""Deterministic intent and risk checks applied after model classification."""

from __future__ import annotations

import re

_EXPLICIT_MUTATION_PATTERNS = (
    re.compile(
        r"^(?:(?:我想|我要|请|麻烦)?(?:帮我)?(?:新建|创建|新增|添加|修改|更新|删除|移除|变更|调整|设置|推进|取消|拒绝|提交|保存|录入|分配|转移|关闭|标记))"
    ),
    re.compile(r"(?:帮我|把).+(?:改成|改为|更新为|设置为|删除|移除|分配给|转给|推进到|推进至|关闭)"),
    re.compile(r"给.+(?:新建|创建|新增|添加|录入|设置|分配)"),
)

_CONTEXT_DEPENDENT_REFERENCES = re.compile(
    r"(?:这个|那个|这些|那些|该|当前|上述|上面|刚才|上次|前面|其中|第[一二三四五六七八九十\d]+(?:个|条|家)?)"
)
_CRM_READ_RESOURCES = (
    r"(?:客户|公司|联系人|跟进记录|跟进任务|待办|商机|合同|回款计划|回款|发票|授权|许可)"
)
_EXPLICIT_READ_QUERY_PATTERNS = (
    re.compile(rf"(?:查询|查找|筛选|列出|查看|看看|看下).{{0,24}}{_CRM_READ_RESOURCES}"),
    re.compile(rf"(?:有哪些|有多少|多少(?:个|家|条)?).{{0,12}}{_CRM_READ_RESOURCES}"),
    re.compile(rf"{_CRM_READ_RESOURCES}.{{0,12}}(?:有哪些|有多少|多少(?:个|家|条)?|列表)$"),
)

_COMPLETED_CUSTOMER_CONTACT = re.compile(
    r"(?:微信|电话|邮件|短信|飞书|钉钉|线上|现场)?(?:联系|沟通|拜访|回访)(?:了|过|完成)"
)
_FOLLOW_UP_BUSINESS_UPDATE = re.compile(
    r"(?:反馈|表示|告知|确认|提到|说明|项目|需求|预算|立项|采购|招标|合同|报价|方案|测试|验收|上线|付款|回款)"
)
_FUTURE_FOLLOW_UP_PLAN = re.compile(
    r"(?:今天|明天|后天|大后天|本周|下周|下下周|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,2}月\d{1,2}日|\d{1,2}[/-]\d{1,2}|月底|月初)"
    r".{0,16}(?:(?:继续|再|再次|安排|计划).{0,6})?(?:跟进|联系|沟通|拜访|回访)"
)
_FOLLOW_UP_QUESTION_MARKERS = re.compile(
    r"(?:是否|有没有|怎么|如何|为什么|什么(?:状态|情况|进展)?|进展(?:如何|怎样|怎么样)|"
    r"状态(?:如何|怎样|怎么样)|何时|谁|哪些|多少|查询|查找|查看|看看|看下|"
    r"吗[\uFF1F?]?$|么[\uFF1F?]?$|[\uFF1F?])"
)

# A free-text turn may resume a suspended native Workflow only when the user
# explicitly points at that conversational flow. Business Cases (for example
# a pending follow-up confirmation) are resolved by their own matcher and must
# never be inferred from a generic session-local phrase.
_EXPLICIT_WORKFLOW_CONTINUATION = re.compile(
    r"(?:继续|接着|恢复|回到|返回|补充|提交)"
    r".{0,12}"
    r"(?:刚才|上面|上一个|当前|这个|该|前面)"
    r".{0,12}"
    r"(?:任务|流程|操作|工作流|步骤|信息|表单)"
    r"|(?:刚才|上面|上一个|当前|这个|该|前面)"
    r".{0,12}"
    r"(?:继续|接着|恢复|补充|提交)"
)


def has_context_dependent_reference(text: str) -> bool:
    """Return whether the utterance explicitly points at prior session context."""

    return _CONTEXT_DEPENDENT_REFERENCES.search(text.strip()) is not None


def has_explicit_follow_up_record_intent(text: str) -> bool:
    """Return whether text is a self-contained CRM follow-up write statement.

    CRM users commonly record work by stating a completed customer contact and its
    business outcome or next follow-up plan, without saying "create a record".
    Questions about historical contacts remain read-only and are intentionally
    excluded from this deterministic write signal.
    """

    normalized = text.strip()
    if not normalized or _FOLLOW_UP_QUESTION_MARKERS.search(normalized) is not None:
        return False
    if _COMPLETED_CUSTOMER_CONTACT.search(normalized) is None:
        return False
    return (
        _FOLLOW_UP_BUSINESS_UPDATE.search(normalized) is not None
        or _FUTURE_FOLLOW_UP_PLAN.search(normalized) is not None
    )


def has_explicit_write_intent(text: str) -> bool:
    """Return whether text contains an unambiguous CRM mutation request."""

    normalized = text.strip()
    return has_explicit_follow_up_record_intent(normalized) or any(
        pattern.search(normalized) is not None for pattern in _EXPLICIT_MUTATION_PATTERNS
    )


def has_explicit_workflow_continuation_intent(text: str) -> bool:
    """Return whether text explicitly resumes a suspended conversational Workflow."""

    normalized = text.strip()
    return bool(normalized and _EXPLICIT_WORKFLOW_CONTINUATION.search(normalized))


def has_explicit_independent_read_intent(text: str) -> bool:
    """Return whether text is a self-contained CRM read request, not a session reference."""

    normalized = text.strip()
    if not normalized or has_context_dependent_reference(normalized):
        return False
    return any(pattern.search(normalized) is not None for pattern in _EXPLICIT_READ_QUERY_PATTERNS)

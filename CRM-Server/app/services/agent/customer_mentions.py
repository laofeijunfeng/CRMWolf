"""Conservative customer mention guardrails for CRM agent routing."""
from __future__ import annotations

import re
from typing import Optional


_BUSINESS_INTENT_PATTERN = re.compile(
    r"(创建|新建|新增|建|补|录入|登记|记录|跟进|沟通|回款|到账|开票|发票|部署|license|License|联系人|商机)"
)
_CUSTOMER_LOOKUP_PATTERN = re.compile(
    r"(搜索|查找|查询|找一下|找下|找出|找|匹配|识别).{0,8}(客户|公司)"
)
_CUSTOMER_LOOKUP_PREFIX_PATTERN = re.compile(
    r"^(帮我|请|麻烦|先|再)?\s*"
    r"(搜索|查找|查询|找一下|找下|找出|找|匹配|识别)\s*"
    r"(一下|下)?\s*(相关的|关联的)?\s*(客户|公司)?\s*"
)
_CUSTOMER_LABEL_PREFIX_PATTERN = re.compile(
    r"^(客户名称|客户名|客户|公司名称|公司名|公司)\s*(是|为|叫|:|：)?\s*"
)
_FIELD_LABEL_PATTERN = re.compile(
    r"(采购人数|授权模式|采购类型|采购方式|项目金额|金额|人数|预计|成交|日期|时间|方式|类型|模式|年限|联系人|角色|职位|电话|手机|邮箱)\s*(是|为|:|：)?"
)
_CUSTOMER_MARKER_PATTERN = re.compile(
    r"(公司|集团|银行|证券|科技|信息|移动|电信|联通|医院|大学|政府|局|院|厂|中心|平台|股份|有限|客户|人才|财经|金融|研究所)"
)
_LEADING_FILLER_PATTERN = re.compile(r"^(帮我|请|麻烦|先|再|然后|那|这个客户|该客户|客户|给|为|向|和|跟|对|把|一个|个)+")
_TRAILING_ACTION_PATTERN = re.compile(
    r"(创建|新建|新增|建|补|录入|登记|记录|跟进|沟通|回款|到账|开票|发票|部署|license|License|联系人|商机|相关的|关联的).*$"
)
_GENERIC_LOOKUP_TOKEN_PATTERN = re.compile(
    r"^(上海|深圳|北京|广州|南京|杭州|成都|武汉|西安|苏州|青岛|重庆|天津|厦门|宁波|佛山|东莞|科技|信息|信息科技|公司|客户)$"
)


def explicit_customer_hint_from_message(content: str, *, memory_customer_name: Optional[str] = None) -> Optional[str]:
    """Return a likely explicit customer mention that should outrank session memory.

    This is intentionally conservative. It only extracts short organization-like
    fragments near CRM business actions or sentence starts, and it never tries to
    resolve the customer itself. Resolution still goes through the customer API.
    """
    text = (content or "").strip()
    has_business_intent = bool(_BUSINESS_INTENT_PATTERN.search(text))
    has_lookup_intent = bool(_CUSTOMER_LOOKUP_PATTERN.search(text))
    if not text or not (has_business_intent or has_lookup_intent):
        return None

    memory_name = (memory_customer_name or "").strip()
    for raw_part in re.split(r"[,，。；;\n]", text):
        candidate, from_lookup = _candidate_from_part(raw_part)
        if _is_valid_customer_hint(
            candidate,
            memory_name=memory_name,
            allow_plain_lookup_name=from_lookup,
        ):
            return candidate
    return None


def _candidate_from_part(part: str) -> tuple[str, bool]:
    value = (part or "").strip()
    from_lookup = False
    if _CUSTOMER_LOOKUP_PATTERN.search(value):
        value = _CUSTOMER_LOOKUP_PREFIX_PATTERN.sub("", value).strip()
        from_lookup = True
    return _clean_candidate(value), from_lookup


def _clean_candidate(part: str) -> str:
    value = (part or "").strip()
    if not value:
        return ""
    value = _FIELD_LABEL_PATTERN.sub("", value).strip()
    value = _LEADING_FILLER_PATTERN.sub("", value).strip()
    value = _TRAILING_ACTION_PATTERN.sub("", value).strip()
    value = _CUSTOMER_LABEL_PREFIX_PATTERN.sub("", value).strip()
    value = re.sub(r"(的|这边|那边)$", "", value).strip()
    return value


def _is_valid_customer_hint(
    candidate: str,
    *,
    memory_name: str,
    allow_plain_lookup_name: bool = False,
) -> bool:
    if not candidate or len(candidate) < 2 or len(candidate) > 30:
        return False
    if _FIELD_LABEL_PATTERN.fullmatch(candidate):
        return False
    if re.search(r"\d", candidate):
        return False
    if memory_name and (candidate == memory_name or candidate in memory_name or memory_name in candidate):
        return False
    if _GENERIC_LOOKUP_TOKEN_PATTERN.fullmatch(candidate):
        return False
    if allow_plain_lookup_name and len(candidate) >= 4:
        return True
    return bool(_CUSTOMER_MARKER_PATTERN.search(candidate))

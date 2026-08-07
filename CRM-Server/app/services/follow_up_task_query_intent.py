from __future__ import annotations

FOLLOW_UP_TASK_RETRIEVAL_MODES = {"structured", "semantic_filter"}
FOLLOW_UP_TASK_GENERIC_QUERY_PHRASES = (
    "客户要跟进",
    "需要跟进",
    "还有哪些客户",
    "还有哪些",
    "还有什么",
    "待跟进",
    "要跟进",
    "有哪些",
    "有什么",
    "未完成",
    "没完成",
    "今天",
    "今日",
    "本周",
    "这周",
    "下周",
    "工作安排",
    "任务",
    "待办",
    "安排",
    "要做",
    "逾期",
    "延期",
    "过期",
    "哪些",
    "我的",
    "还有",
    "跟进",
    "我",
    "？",
    "?",
)
FOLLOW_UP_TASK_GENERIC_QUERY_RESIDUALS = {
    "",
    "有",
    "还",
    "客户",
    "跟进",
    "待跟进",
    "要做",
    "做",
    "的",
    "相关",
    "工作",
}


def extract_follow_up_task_semantic_query_text(value: object, *, customer_name: str | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(value.strip().split())
    if not text:
        return None

    normalized_customer_name = "".join(str(customer_name or "").strip().split())
    reduced = text
    if normalized_customer_name:
        reduced = reduced.replace(normalized_customer_name, "")
    for phrase in sorted(FOLLOW_UP_TASK_GENERIC_QUERY_PHRASES, key=len, reverse=True):
        reduced = reduced.replace(phrase, "")
    reduced = reduced.strip(" ，。；;、")
    if reduced in FOLLOW_UP_TASK_GENERIC_QUERY_RESIDUALS:
        return None
    return reduced or None


def normalize_follow_up_task_retrieval_mode(retrieval_mode: str | None, query_text: str | None) -> str:
    clean_mode = retrieval_mode.strip() if isinstance(retrieval_mode, str) else ""
    semantic_query_text = extract_follow_up_task_semantic_query_text(query_text)
    if clean_mode:
        if clean_mode not in FOLLOW_UP_TASK_RETRIEVAL_MODES:
            raise ValueError("未知任务检索模式")
        if clean_mode == "semantic_filter" and not semantic_query_text:
            return "structured"
        return clean_mode
    return "semantic_filter" if semantic_query_text else "structured"

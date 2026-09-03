"""Canonical question construction for historical follow-up task confirmations."""

from __future__ import annotations


def build_follow_up_task_confirmation_question(*, task_label: str, title: str) -> str:
    """Build the single question used to confirm a historical task's completion."""

    return f"{task_label}的「{title or '这项跟进任务'}」现在完成了吗?"

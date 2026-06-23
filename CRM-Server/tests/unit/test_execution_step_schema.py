"""
Test ExecutionStep and Conversation Schemas

验证 Pydantic schema 校验是否正确处理 execution_steps
"""
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime
from app.schemas.ai_conversation import (
    ExecutionStepSchema,
    ExecutionStepType,
    MessageItemSchema,
    ConversationDetailSchema
)


def test_execution_step_schema():
    """测试 ExecutionStep schema"""
    step_data = {
        "id": "step-001",
        "type": "TOOL_CALL",
        "title": "查找客户信息",
        "description": "用户想跟进光大证券，需要先找到客户...",
        "timestamp": datetime.now(),
        "round": 1,
        "tool": "search_customer",
        "params": {"keyword": "光大证券"},
        "businessParams": "正在搜索：光大证券",
        "success": True
    }

    step = ExecutionStepSchema(**step_data)
    assert step.id == "step-001"
    assert step.type == ExecutionStepType.TOOL_CALL
    assert step.title == "查找客户信息"
    assert step.businessParams == "正在搜索：光大证券"
    print("✓ ExecutionStep schema validation works")


def test_message_item_with_execution_steps():
    """测试 MessageItem schema 包含 execution_steps"""
    step_data = {
        "id": "step-001",
        "type": "TOOL_CALL",
        "title": "查找客户信息",
        "timestamp": datetime.now()
    }

    message_data = {
        "role": "assistant",
        "content": "已为您找到客户信息",
        "timestamp": "2026-06-23T10:00:00",
        "execution_steps": [step_data]
    }

    message = MessageItemSchema(**message_data)
    assert message.role == "assistant"
    assert message.content == "已为您找到客户信息"
    assert message.execution_steps is not None
    assert len(message.execution_steps) == 1
    assert message.execution_steps[0].title == "查找客户信息"
    print("✓ MessageItem schema with execution_steps works")


def test_message_item_without_execution_steps():
    """测试 MessageItem schema 不包含 execution_steps"""
    message_data = {
        "role": "user",
        "content": "帮我跟进光大证券",
        "timestamp": "2026-06-23T10:00:00"
    }

    message = MessageItemSchema(**message_data)
    assert message.role == "user"
    assert message.content == "帮我跟进光大证券"
    assert message.execution_steps is None
    print("✓ MessageItem schema without execution_steps works")


def test_conversation_detail_with_execution_steps():
    """测试 ConversationDetail schema 包含 execution_steps"""
    step_data = {
        "id": "step-001",
        "type": "TOOL_CALL",
        "title": "查找客户信息",
        "timestamp": datetime.now()
    }

    message_data = {
        "role": "assistant",
        "content": "已为您找到客户信息",
        "timestamp": "2026-06-23T10:00:00",
        "execution_steps": [step_data]
    }

    conversation_data = {
        "id": 1,
        "title": "跟进光大证券",
        "messages": [message_data],
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }

    conversation = ConversationDetailSchema(**conversation_data)
    assert conversation.id == 1
    assert conversation.title == "跟进光大证券"
    assert len(conversation.messages) == 1
    assert conversation.messages[0].execution_steps is not None
    assert len(conversation.messages[0].execution_steps) == 1
    print("✓ ConversationDetail schema with execution_steps works")


if __name__ == "__main__":
    print("=== Running Schema Validation Tests ===")
    test_execution_step_schema()
    test_message_item_with_execution_steps()
    test_message_item_without_execution_steps()
    test_conversation_detail_with_execution_steps()
    print("\n=== All Tests Passed ===")
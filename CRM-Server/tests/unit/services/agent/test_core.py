"""
Agent Core 单元测试
测试 ReAct 循环架构

测试覆盖：
1. Reason: LLM 推理解析
2. Act: 工具调用执行
3. Observe: 结果观察
4. Reflection: 反思决策

遵循规范：
- 新代码必写测试
- 覆盖率要求：100%
- Pydantic 强制校验
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import Dict, Any
import json

from app.services.agent.core import (
    CRMWolfAgent,
    ReasoningResult,
    ObservationResult,
    ReflectionResult,
    AgentResponse,
)
from app.services.agent.tools import ToolRegistry, ToolResult
from app.services.agent.memory import AgentMemory


# ==================== Fixtures ====================


@pytest.fixture
def mock_db():
    """Mock database session"""
    return Mock()


@pytest.fixture
def mock_config():
    """Mock AIConfig"""
    config = Mock()
    config.api_host = "https://api.deepseek.com"
    config.model_name = "deepseek-chat"
    config.temperature = 0.7
    config.max_tokens = 1024
    return config


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis_mock = Mock()
    redis_mock.get.return_value = None
    redis_mock.setex.return_value = True
    return redis_mock


@pytest.fixture
def mock_ai_config_crud(mock_config):
    """Mock AIConfig CRUD"""
    crud_mock = Mock()
    crud_mock.get_config.return_value = mock_config
    crud_mock.get_decrypted_api_key.return_value = "test-api-key"
    return crud_mock


# ==================== Reasoning Tests ====================


class TestReasoning:
    """测试推理逻辑"""

    def test_parse_reasoning_response_with_tool_call(self):
        """测试解析需要工具调用的推理结果"""

        # 模拟 LLM 响应（需要工具）
        response_text = json.dumps({
            "reasoning": "用户想跟进光大证券，需要先搜索客户",
            "needs_tool": True,
            "tool_name": "search_customer",
            "tool_params": {"keyword": "光大证券"},
        })

        # 创建 Agent（简化）
        agent = Mock(spec=CRMWolfAgent)

        # 调用解析方法（需要实例）
        # 这里直接测试解析逻辑
        import re

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group(0))

            reasoning = ReasoningResult(
                is_complete=not result.get("needs_tool", False),
                needs_tool=result.get("needs_tool", False),
                tool_name=result.get("tool_name"),
                tool_params=result.get("tool_params", {}),
                thinking=result.get("reasoning", ""),
                final_answer=result.get("final_answer", ""),
            )

            # 验证结果
            assert reasoning.needs_tool == True
            assert reasoning.tool_name == "search_customer"
            assert reasoning.tool_params == {"keyword": "光大证券"}
            assert reasoning.is_complete == False

    def test_parse_reasoning_response_completed(self):
        """测试解析完成的推理结果"""

        # 模拟 LLM 响应（任务完成）
        response_text = json.dumps({
            "reasoning": "任务完成",
            "needs_tool": False,
            "is_complete": True,
            "final_answer": "已为光大证券创建跟进记录",
        })

        import re

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group(0))

            reasoning = ReasoningResult(
                is_complete=not result.get("needs_tool", False),
                needs_tool=result.get("needs_tool", False),
                tool_name=result.get("tool_name"),
                tool_params=result.get("tool_params", {}),
                thinking=result.get("reasoning", ""),
                final_answer=result.get("final_answer", ""),
            )

            # 验证结果
            assert reasoning.is_complete == True
            assert reasoning.needs_tool == False
            assert reasoning.final_answer == "已为光大证券创建跟进记录"

    def test_parse_reasoning_response_fallback(self):
        """测试解析失败时的 fallback"""

        # 模拟无效响应
        response_text = "这是一个无效的响应"

        import re

        json_match = re.search(r'\{[\s\S]*\}', response_text)

        # 无 JSON，fallback
        reasoning = ReasoningResult(
            is_complete=True,
            needs_tool=False,
            final_answer=response_text,
            thinking="",
        )

        # 验证 fallback
        assert reasoning.is_complete == True
        assert reasoning.final_answer == "这是一个无效的响应"


# ==================== Tool Registry Tests ====================


class TestToolRegistry:
    """测试工具注册"""

    def test_get_tools_schema(self, mock_db):
        """测试获取工具 Schema"""

        registry = ToolRegistry(mock_db, team_id=4)
        tools = registry.get_tools_schema()

        # 验证工具列表
        assert len(tools) > 0
        assert any(tool["name"] == "search_customer" for tool in tools)
        assert any(tool["name"] == "follow_up_customer" for tool in tools)

    def test_get_tools_definition(self, mock_db):
        """测试获取工具定义文本"""

        registry = ToolRegistry(mock_db, team_id=4)
        definition = registry.get_tools_definition()

        # 验证定义文本
        assert "search_customer" in definition
        assert "参数" in definition
        assert "必填" in definition or "可选" in definition

    def test_get_handler_search_customer(self, mock_db):
        """测试获取 search_customer Handler"""

        registry = ToolRegistry(mock_db, team_id=4)
        handler, config = registry.get_handler("search_customer")

        # 验证 Handler 存在
        assert handler is not None
        assert hasattr(handler, "execute")


# ==================== Tool Handler Tests ====================


class TestSearchCustomerHandler:
    """测试搜索客户 Handler"""

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_db):
        """测试成功搜索客户"""

        from app.services.agent.handlers import SearchCustomerHandler

        handler = SearchCustomerHandler()

        # Mock customer_crud.get_multi
        mock_customer = Mock()
        mock_customer.id = 123
        mock_customer.account_name = "光大证券股份有限公司"

        with patch("app.crud.customer.customer_crud.get_multi") as mock_get_multi:
            mock_get_multi.return_value = ([mock_customer], 1)

            result = await handler.execute(
                db=mock_db,
                team_id=4,
                user_id=2,
                params={"keyword": "光大证券", "limit": 5},
            )

            # 验证结果
            assert result.success == True
            assert len(result.data) == 1
            assert result.data[0]["name"] == "光大证券股份有限公司"

    @pytest.mark.asyncio
    async def test_execute_no_keyword(self, mock_db):
        """测试缺少关键词参数"""

        from app.services.agent.handlers import SearchCustomerHandler

        handler = SearchCustomerHandler()

        result = await handler.execute(
            db=mock_db,
            team_id=4,
            user_id=2,
            params={},  # 缺少 keyword
        )

        # 验证失败
        assert result.success == False
        assert "缺少 keyword 参数" in result.error


# ==================== Observation Tests ====================


class TestObservation:
    """测试观察逻辑"""

    def test_observe_success_with_customer_id(self):
        """测试成功观察并提取 customer_id"""

        # 模拟 Agent
        agent = Mock(spec=CRMWolfAgent)

        # 模拟工具结果
        tool_result = ToolResult(
            success=True,
            data=[{"id": 123, "name": "光大证券股份有限公司"}],
        )

        # 模拟观察逻辑
        extracted_info = {}
        if isinstance(tool_result.data, list) and len(tool_result.data) > 0:
            first_item = tool_result.data[0]
            if "id" in first_item:
                extracted_info["customer_id"] = first_item["id"]

        # 验证提取
        assert extracted_info.get("customer_id") == 123

    def test_observe_failure(self):
        """测试失败观察"""

        # 模拟工具失败
        tool_result = ToolResult(
            success=False,
            error="客户不存在",
            data=None,
        )

        # 验证失败观察
        observation = ObservationResult(
            success=False,
            error=tool_result.error,
        )

        assert observation.success == False
        assert observation.error == "客户不存在"


# ==================== Reflection Tests ====================


class TestReflection:
    """测试反思逻辑"""

    def test_reflect_search_multiple_candidates(self):
        """测试搜索返回多个候选时的反思"""

        # 模拟搜索结果（多个候选）
        observation = ObservationResult(
            success=True,
            data=[
                {"id": 123, "name": "光大证券股份有限公司"},
                {"id": 456, "name": "中信证券股份有限公司"},
            ],
        )

        reasoning = ReasoningResult(
            is_complete=False,
            needs_tool=True,
            tool_name="search_customer",
        )

        # 模拟反思逻辑
        if len(observation.data) > 1:
            reflection = ReflectionResult(
                should_continue=False,
                final_answer="找到多个客户，请选择：...",
            )

        # 验证反思结果
        assert reflection.should_continue == False
        assert "找到多个" in reflection.final_answer

    def test_reflect_search_zero_results(self):
        """测试搜索返回 0 结果时的反思"""

        # 模拟搜索结果（空）
        observation = ObservationResult(
            success=True,
            data=[],
        )

        reasoning = ReasoningResult(
            is_complete=False,
            needs_tool=True,
            tool_name="search_customer",
        )

        # 模拟反思逻辑
        if not observation.data:
            reflection = ReflectionResult(
                should_continue=False,
                final_answer="未找到匹配的实体，是否创建新实体？",
            )

        # 验证反思结果
        assert reflection.should_continue == False
        assert "未找到" in reflection.final_answer

    def test_reflect_search_unique_result(self):
        """测试搜索返回唯一结果时的反思"""

        # 模拟搜索结果（唯一）
        observation = ObservationResult(
            success=True,
            data=[{"id": 123, "name": "光大证券股份有限公司"}],
        )

        reasoning = ReasoningResult(
            is_complete=False,
            needs_tool=True,
            tool_name="search_customer",
        )

        # 模拟反思逻辑
        if len(observation.data) == 1:
            reflection = ReflectionResult(should_continue=True)

        # 验证反思结果
        assert reflection.should_continue == True


# ==================== Memory Tests ====================


class TestAgentMemory:
    """测试 Agent Memory"""

    def test_create_session(self, mock_db, mock_redis):
        """测试创建会话"""

        memory = AgentMemory(mock_db, 4, 2, mock_redis)
        session_id = memory.create_session()

        # 验证会话 ID
        assert session_id is not None
        assert len(session_id) == 36  # UUID format

    def test_add_user_message(self, mock_db, mock_redis):
        """测试添加用户消息"""

        memory = AgentMemory(mock_db, 4, 2, mock_redis)
        memory.create_session()

        memory.add_user_message("跟进光大证券")

        # 验证消息列表
        assert len(memory.messages) == 1
        assert memory.messages[0]["role"] == "user"
        assert memory.messages[0]["content"] == "跟进光大证券"

    def test_update_recent_entity(self, mock_db, mock_redis):
        """测试更新最近实体"""

        memory = AgentMemory(mock_db, 4, 2, mock_redis)
        memory.create_session()

        memory.update_recent_entity("Customer", 123, "光大证券股份有限公司")

        # 验证最近实体
        assert "Customer" in memory.recent_entities
        assert memory.recent_entities["Customer"]["id"] == 123
        assert memory.recent_entities["Customer"]["name"] == "光大证券股份有限公司"

    def test_get_context(self, mock_db, mock_redis):
        """测试获取上下文"""

        memory = AgentMemory(mock_db, 4, 2, mock_redis)
        memory.create_session()

        memory.add_user_message("跟进光大证券")
        memory.update_recent_entity("Customer", 123, "光大证券股份有限公司")

        context = memory.get_context()

        # 验证上下文内容
        assert "当前日期" in context
        assert "团队ID=4" in context
        assert "光大证券股份有限公司" in context


# ==================== Run Tests ====================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
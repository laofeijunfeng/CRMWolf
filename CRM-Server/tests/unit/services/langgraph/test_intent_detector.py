"""LangGraph Intent Detector 单元测试

测试关键词预处理层能正确识别 Intent。
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

from app.services.langgraph.nodes.intent import (
    intent_detector_node,
    IntentResult,
)
from app.services.langgraph.state import AgentState
from langchain_core.runnables import RunnableConfig


class TestIntentDetectorKeywordPreprocessing:
    """测试 Intent Detector 关键词预处理"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def mock_config(self, mock_db):
        """Mock RunnableConfig"""
        return {
            "configurable": {
                "db": mock_db,
                "team_id": 4,
            }
        }

    @pytest.fixture
    def state_with_follow_up_message(self):
        """AgentState 包含跟进消息"""
        return {
            "messages": [{"type": "human", "content": "跟进一下光大证券，最近还在走立项的流程"}],
            "session_id": "test-session-id",
            "user_id": 2,
            "team_id": 4,
            "round_num": 0,
            "entity_context": None,
        }

    def test_keyword_follow_up_detection(
        self,
        mock_db,
        mock_config,
        state_with_follow_up_message,
    ):
        """
        RED 测试：关键词"跟进"应该触发 create_follow_up Intent

        Expected behavior:
        - 输入包含"跟进"关键词
        - Intent Detector 应返回 create_follow_up
        - Confidence 应 ≥ 0.9（关键词匹配高置信度）
        - needs_entity_resolution = True（需要找到客户）
        """

        # 调用 Intent Detector
        result = intent_detector_node(state_with_follow_up_message, mock_config)

        # 验证 Intent 结果
        intent_result = result.get("intent_result")

        # 🔴 RED: 当前代码会调用 LLM，返回 query_customer（错误）
        # ✅ GREEN: 添加关键词预处理后，应返回 create_follow_up
        assert intent_result is not None
        assert intent_result["action"] == "create_follow_up"
        assert intent_result["confidence"] >= 0.9
        assert intent_result["needs_entity_resolution"] == True
        assert intent_result["entity_type"] == "Customer"

    def test_keyword_create_opportunity_detection(self, mock_db, mock_config):
        """
        测试关键词"创建商机"应该触发 create_opportunity Intent
        """

        state = {
            "messages": [{"type": "human", "content": "为光大证券创建商机，预计金额50万"}],
            "session_id": "test-session-id",
            "user_id": 2,
            "team_id": 4,
        }

        result = intent_detector_node(state, mock_config)
        intent_result = result.get("intent_result")

        assert intent_result["action"] == "create_opportunity"
        assert intent_result["confidence"] >= 0.9

    def test_keyword_win_opportunity_detection(self, mock_db, mock_config):
        """
        测试关键词"赢单"应该触发 win_opportunity Intent
        """

        state = {
            "messages": [{"type": "human", "content": "光大证券这个商机赢单了"}],
            "session_id": "test-session-id",
            "user_id": 2,
            "team_id": 4,
        }

        result = intent_detector_node(state, mock_config)
        intent_result = result.get("intent_result")

        assert intent_result["action"] == "win_opportunity"
        assert intent_result["confidence"] >= 0.9

    def test_no_keyword_fallback_to_llm(self, mock_db, mock_config):
        """
        测试无关键词时应该 fallback 到 LLM 解析
        """

        state = {
            "messages": [{"type": "human", "content": "帮我看看光大证券的状态"}],
            "session_id": "test-session-id",
            "user_id": 2,
            "team_id": 4,
        }

        # Mock AIConfig
        with patch("app.services.langgraph.nodes.intent.ai_config_crud") as mock_crud:
            mock_config_obj = Mock()
            mock_config_obj.model_name = "deepseek-chat"
            mock_config_obj.temperature = 0.7
            mock_config_obj.max_tokens = 500
            mock_config_obj.api_host = "https://api.deepseek.com"

            mock_crud.get_config.return_value = mock_config_obj
            mock_crud.get_decrypted_api_key.return_value = "test-api-key"

            # Mock httpx client
            with patch("app.services.langgraph.nodes.intent.httpx.Client") as mock_client:
                mock_response = Mock()
                mock_response.json.return_value = {
                    "choices": [{
                        "message": {
                            "content": '{"action": "query_customer", "confidence": 0.8, "needs_entity_resolution": true}'
                        }
                    }]
                }
                mock_response.raise_for_status = Mock()

                mock_client_instance = Mock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__enter__.return_value = mock_client_instance

                result = intent_detector_node(state, mock_config)
                intent_result = result.get("intent_result")

                # LLM 解析结果（置信度可能低于关键词匹配）
                assert intent_result["action"] == "query_customer"
                # 关键词匹配应该是 0.95，LLM 解析通常 0.7-0.9
                assert intent_result["confidence"] < 0.95


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
"""
合同工具测试

测试合同相关的 4 个工具定义和 Handler 配置
"""
import pytest
from app.constants.tools import TOOLS, TOOL_HANDLER_MAP, get_tools_schema, get_tool_handler_config


class TestContractToolsDefinition:
    """测试合同工具定义"""

    def test_create_contract_tool_exists(self):
        """测试 create_contract 工具存在"""
        tool_names = [t["function"]["name"] for t in TOOLS]
        assert "create_contract" in tool_names

    def test_query_contracts_tool_exists(self):
        """测试 query_contracts 工具存在"""
        tool_names = [t["function"]["name"] for t in TOOLS]
        assert "query_contracts" in tool_names

    def test_get_contract_detail_tool_exists(self):
        """测试 get_contract_detail 工具存在"""
        tool_names = [t["function"]["name"] for t in TOOLS]
        assert "get_contract_detail" in tool_names

    def test_update_contract_status_tool_exists(self):
        """测试 update_contract_status 工具存在"""
        tool_names = [t["function"]["name"] for t in TOOLS]
        assert "update_contract_status" in tool_names

    def test_create_contract_tool_structure(self):
        """测试 create_contract 工具结构正确"""
        tool = next((t for t in TOOLS if t["function"]["name"] == "create_contract"), None)
        assert tool is not None
        assert tool["type"] == "function"
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params

        # 检查必填字段
        assert "customer_name" in params["required"]
        assert "opportunity_name" in params["required"]

        # 检查字段定义
        assert "customer_name" in params["properties"]
        assert "opportunity_name" in params["properties"]
        assert "total_amount" in params["properties"]
        assert "user_count" in params["properties"]
        assert "license_type" in params["properties"]

    def test_create_contract_license_type_enum(self):
        """测试 license_type 枚举定义正确"""
        tool = next((t for t in TOOLS if t["function"]["name"] == "create_contract"), None)
        license_type = tool["function"]["parameters"]["properties"]["license_type"]
        assert license_type["type"] == "string"
        assert "enum" in license_type
        assert "订阅制" in license_type["enum"]
        assert "买断制" in license_type["enum"]

    def test_query_contracts_status_enum(self):
        """测试 query_contracts 状态枚举定义正确"""
        tool = next((t for t in TOOLS if t["function"]["name"] == "query_contracts"), None)
        status = tool["function"]["parameters"]["properties"]["status"]
        assert status["type"] == "string"
        assert "enum" in status
        assert "草稿" in status["enum"]
        assert "待审核" in status["enum"]
        assert "已签署" in status["enum"]
        assert "生效中" in status["enum"]

    def test_update_contract_status_enum(self):
        """测试 update_contract_status 状态枚举定义正确"""
        tool = next((t for t in TOOLS if t["function"]["name"] == "update_contract_status"), None)
        status = tool["function"]["parameters"]["properties"]["status"]
        assert status["type"] == "string"
        assert "enum" in status
        assert "status" in tool["function"]["parameters"]["required"]


class TestContractHandlerConfig:
    """测试合同 Handler 配置"""

    def test_create_contract_handler_exists(self):
        """测试 create_contract Handler 配置存在"""
        config = get_tool_handler_config("create_contract")
        assert config is not None
        assert len(config) > 0

    def test_create_contract_handler_type(self):
        """测试 create_contract Handler 类型正确"""
        config = get_tool_handler_config("create_contract")
        assert config["handler"] == "CreateHandler"

    def test_create_contract_crud_mapping(self):
        """测试 create_contract CRUD 映射正确"""
        config = get_tool_handler_config("create_contract")
        assert config["config"]["crud_mapping"] == "contract"

    def test_create_contract_parent_lookup(self):
        """测试 create_contract 父实体查找配置正确"""
        config = get_tool_handler_config("create_contract")
        parent_lookup = config["config"]["parent_lookup"]
        assert parent_lookup["parent_crud_mapping"] == "customer"
        assert parent_lookup["parent_lookup_field"] == "customer_name"
        assert parent_lookup["parent_result_field"] == "customer_id"

    def test_create_contract_secondary_parent_lookup(self):
        """测试 create_contract 第二个父实体查找配置正确"""
        config = get_tool_handler_config("create_contract")
        secondary_lookup = config["config"]["secondary_parent_lookup"]
        assert secondary_lookup["parent_crud_mapping"] == "opportunity"
        assert secondary_lookup["parent_lookup_field"] == "opportunity_name"
        assert secondary_lookup["parent_result_field"] == "opportunity_id"
        assert secondary_lookup["parent_filter_status"] == "WON"

    def test_query_contracts_handler_config(self):
        """测试 query_contracts Handler 配置"""
        config = get_tool_handler_config("query_contracts")
        assert config["handler"] == "QueryListHandler"
        assert config["config"]["crud_mapping"] == "contract"

    def test_get_contract_detail_handler_config(self):
        """测试 get_contract_detail Handler 配置"""
        config = get_tool_handler_config("get_contract_detail")
        assert config["handler"] == "QueryDetailHandler"
        assert config["config"]["crud_mapping"] == "contract"

    def test_update_contract_status_handler_config(self):
        """测试 update_contract_status Handler 配置"""
        config = get_tool_handler_config("update_contract_status")
        assert config["handler"] == "StatusChangeHandler"
        assert config["config"]["crud_mapping"] == "contract"
        assert config["config"]["action_type"] == "update_status"


class TestGetToolsSchema:
    """测试 get_tools_schema 函数"""

    def test_get_tools_schema_returns_list(self):
        """测试返回类型是列表"""
        schema = get_tools_schema()
        assert isinstance(schema, list)
        assert len(schema) > 0

    def test_get_tools_schema_contains_contract_tools(self):
        """测试 schema 包含合同工具"""
        schema = get_tools_schema()
        tool_names = [t["function"]["name"] for t in schema]
        assert "create_contract" in tool_names
        assert "query_contracts" in tool_names
        assert "get_contract_detail" in tool_names
        assert "update_contract_status" in tool_names
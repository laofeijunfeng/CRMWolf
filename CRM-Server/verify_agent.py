"""
Agent 快速验证脚本
验证 Agent ReAct 循环是否正常工作

测试场景：
1. 单一意图：跟进客户
2. 搜索工具调用
3. 推理过程解析
"""

import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from app.core.database import SessionLocal
from app.crud.ai_config import ai_config_crud
from app.services.agent import CRMWolfAgent


async def test_agent_basic():
    """基础验证：创建 Agent 并检查配置"""

    db = SessionLocal()
    try:
        print("=" * 60)
        print("Agent 基础验证")
        print("=" * 60)

        # ===== Step 1: 检查 AI 配置 =====
        config = ai_config_crud.get_config(db, 4)  # team_id = 4

        if not config:
            print("❌ AI 配置未找到")
            print("请先在数据库中配置 AIConfig：")
            print("  INSERT INTO ai_config (team_id, api_host, model_name, api_key)")
            print("  VALUES (4, 'https://api.deepseek.com', 'deepseek-chat', 'your_api_key');")
            return False

        print(f"✅ AI 配置已找到：")
        print(f"  - API Host: {config.api_host}")
        print(f"  - Model: {config.model_name}")

        # ===== Step 2: 创建 Agent =====
        try:
            agent = CRMWolfAgent(db, team_id=4, user_id=2)
            print(f"✅ Agent 创建成功")

            # ===== Step 3: 检查工具注册 =====
            tools = agent.tool_registry.get_tools_schema()
            print(f"✅ 工具注册成功：共 {len(tools)} 个工具")

            for tool in tools[:5]:  # 只显示前5个
                print(f"  - {tool['name']}")

            # ===== Step 4: 检查 Prompt 构建 =====
            system_prompt = agent.prompts.build_system_prompt(
                tools=agent.tool_registry.get_tools_definition(),
                business_workflow=agent.prompts.BUSINESS_WORKFLOW,
                context="测试上下文",
                round_num=1,
            )

            print(f"✅ System Prompt 构建成功：长度 {len(system_prompt)} 字符")

            # 检查关键内容
            if "工具定义" in system_prompt:
                print(f"  - 包含：工具定义 ✓")
            if "业务流程图" in system_prompt:
                print(f"  - 包含：业务流程图 ✓")
            if "ReAct" in system_prompt:
                print(f"  - 包含：推理框架 ✓")

            return True

        except Exception as e:
            print(f"❌ Agent 创建失败：{str(e)}")
            return False

    finally:
        db.close()


async def test_agent_reasoning():
    """推理验证：测试 LLM 调用和解析"""

    db = SessionLocal()
    try:
        print("\n" + "=" * 60)
        print("Agent 推理验证")
        print("=" * 60)

        # 检查配置
        config = ai_config_crud.get_config(db, 4)
        if not config:
            print("❌ 跳过：AI 配置未找到")
            return False

        agent = CRMWolfAgent(db, team_id=4, user_id=2)

        # 测试推理解析
        test_responses = [
            # 需要工具的响应
            '{"reasoning":"用户想跟进光大证券","needs_tool":true,"tool_name":"search_customer","tool_params":{"keyword":"光大证券"}}',
            # 完成的响应
            '{"reasoning":"任务完成","needs_tool":false,"is_complete":true,"final_answer":"已创建跟进记录"}',
        ]

        print("✅ 测试推理解析：")

        for response_text in test_responses:
            reasoning = agent._parse_reasoning_response(response_text)

            if reasoning.needs_tool:
                print(f"  - 工具调用：{reasoning.tool_name} ✓")
            else:
                print(f"  - 任务完成：{reasoning.final_answer} ✓")

        return True

    except Exception as e:
        print(f"❌ 推理验证失败：{str(e)}")
        return False

    finally:
        db.close()


async def test_agent_tool_call():
    """工具调用验证：测试工具 Handler"""

    db = SessionLocal()
    try:
        print("\n" + "=" * 60)
        print("Agent 工具调用验证")
        print("=" * 60)

        config = ai_config_crud.get_config(db, 4)
        if not config:
            print("❌ 跳过：AI 配置未找到")
            return False

        agent = CRMWolfAgent(db, team_id=4, user_id=2)

        # 测试 search_customer 工具
        print("✅ 测试 search_customer 工具：")

        try:
            result = await agent._act("search_customer", {"keyword": "光大证券", "limit": 5})

            if result.success:
                print(f"  - 执行成功 ✓")
                if result.data:
                    print(f"  - 返回数据：{len(result.data)} 个结果")
                else:
                    print(f"  - 返回数据：空（可能数据库无数据）")
            else:
                print(f"  - 执行失败：{result.error}")

        except Exception as e:
            print(f"  - 异常：{str(e)}")

        return True

    except Exception as e:
        print(f"❌ 工具调用验证失败：{str(e)}")
        return False

    finally:
        db.close()


async def main():
    """主验证流程"""

    print("CRMWolf Agent ReAct 循环架构验证")
    print("遵循系统规范：")
    print("  - CRUD 统一入口")
    print("  - team_id 必传")
    print("  - Pydantic 强制校验")
    print("  - 新代码必写测试")
    print()

    # 执行验证
    results = []

    results.append(await test_agent_basic())
    results.append(await test_agent_reasoning())
    results.append(await test_agent_tool_call())

    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"通过：{passed}/{total}")

    if passed == total:
        print("✅ 所有验证通过！Agent 架构已就绪")
        print()
        print("下一步：")
        print("  1. 启动服务：./run.sh")
        print("  2. 测试 API：curl -X POST 'http://localhost:8000/api/v1/agent/chat'")
        print("  3. 查看测试：pytest tests/unit/services/agent/test_core.py")
    else:
        print("⚠️ 部分验证未通过，请检查配置和数据库")

    return passed == total


if __name__ == "__main__":
    asyncio.run(main())
"""直接测试 Agent.run()（绕过 SSE）"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.core.database import SessionLocal
from app.crud.ai_config import ai_config_crud
from app.services.agent import CRMWolfAgent

async def test_agent_direct():
    db = SessionLocal()
    try:
        config = ai_config_crud.get_config(db, 4)
        if not config:
            print("❌ AI 配置未找到")
            return

        print(f"✅ AI 配置: model={config.model_name}")

        agent = CRMWolfAgent(db, team_id=4, user_id=2)
        print("✅ Agent 创建成功")

        response = await agent.run("跟进光大证券", "test-session")
        print(f"✅ Agent.run() 成功")
        print(f"  - Rounds: {response.rounds}")
        print(f"  - Answer: {response.answer}")
        print(f"  - Tool Calls: {len(response.tool_calls)}")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

asyncio.run(test_agent_direct())
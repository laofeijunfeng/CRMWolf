"""
Workflow Session Recovery 测试

验证 Redis Session 持久化功能：
1. Session 创建并保存到 Redis
2. Session 从 Redis 恢复
3. 模拟进程重启后 Session 仍然存在

运行方式：
cd CRM-Server && python3 tests/integration/test_workflow_session_recovery.py
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.workflow.session_store import (
    WorkflowSession,
    WorkflowSessionStore,
    get_session_store,
)
from app.core.redis import get_async_redis_client


async def test_session_create_and_load():
    """测试 Session 创建和加载"""
    print("=" * 50)
    print("Test 1: Session 创建和加载")
    print("=" * 50)

    store = await get_session_store()

    # 创建 Session
    session = await store.create(
        workflow_id="test_workflow",
        entity_context={"customer_id": 123, "customer_name": "测试客户"},
        user_id=1,
        team_id=1,
    )

    print(f"✅ Session 创建成功: {session.session_id}")
    print(f"   workflow_id: {session.workflow_id}")
    print(f"   entity_context: {session.entity_context}")
    print(f"   created_time: {session.created_time}")

    # 从 Redis 加载
    loaded = await store.load(session.session_id)

    assert loaded is not None, "Session 加载失败"
    assert loaded.session_id == session.session_id, "session_id 不匹配"
    assert loaded.workflow_id == session.workflow_id, "workflow_id 不匹配"
    assert loaded.entity_context == session.entity_context, "entity_context 不匹配"

    print(f"✅ Session 加载成功: {loaded.session_id}")
    print(f"   数据一致性验证通过")

    # 清理
    await store.delete(session.session_id)
    print(f"✅ Session 已清理")

    return True


async def test_session_update_and_recovery():
    """测试 Session 更新和恢复"""
    print("\n" + "=" * 50)
    print("Test 2: Session 更新和恢复")
    print("=" * 50)

    store = await get_session_store()

    # 创建 Session
    session = await store.create(
        workflow_id="convert_customer",
        entity_context={"customer_id": 456},
        user_id=2,
        team_id=1,
    )

    print(f"✅ Session 创建: {session.session_id}")

    # 模拟流程执行，更新 Session
    session.completed_steps = ["step_1", "step_2"]
    session.current_step_id = "step_3"
    session.waiting_for_user = True
    session.pending_step_id = "ask_select_opportunity"
    session.pending_question = "请选择商机"
    session.pending_options = ["商机A", "商机B"]

    await store.save(session)

    print(f"✅ Session 更新成功")
    print(f"   completed_steps: {session.completed_steps}")
    print(f"   waiting_for_user: {session.waiting_for_user}")

    # 模拟进程重启：重新获取 store，加载 Session
    store2 = await get_session_store()
    recovered = await store2.load(session.session_id)

    assert recovered is not None, "Session 恢复失败"
    assert recovered.completed_steps == ["step_1", "step_2"], "completed_steps 不匹配"
    assert recovered.waiting_for_user == True, "waiting_for_user 不匹配"
    assert recovered.pending_step_id == "ask_select_opportunity", "pending_step_id 不匹配"

    print(f"✅ Session 恢复成功（模拟进程重启）")
    print(f"   completed_steps: {recovered.completed_steps}")
    print(f"   waiting_for_user: {recovered.waiting_for_user}")
    print(f"   pending_question: {recovered.pending_question}")

    # 清理
    await store.delete(session.session_id)
    print(f"✅ Session 已清理")

    return True


async def test_session_ttl():
    """测试 Session TTL"""
    print("\n" + "=" * 50)
    print("Test 3: Session TTL 检查")
    print("=" * 50)

    redis_client = await get_async_redis_client()
    store = WorkflowSessionStore(redis_client)

    # 创建 Session
    session = await store.create(
        workflow_id="test_ttl",
        entity_context={},
        user_id=3,
        team_id=1,
    )

    print(f"✅ Session 创建: {session.session_id}")

    # 检查 TTL
    key = store._session_key(session.session_id)
    ttl = await redis_client.ttl(key)

    print(f"   TTL: {ttl} 秒 (预期 ~1800)")
    assert ttl > 0, "TTL 未设置"
    assert ttl <= 1800, "TTL 过长"

    print(f"✅ TTL 设置正确")

    # 清理
    await store.delete(session.session_id)
    print(f"✅ Session 已清理")

    return True


async def test_session_execution_history():
    """测试执行历史记录"""
    print("\n" + "=" * 50)
    print("Test 4: 执行历史记录")
    print("=" * 50)

    store = await get_session_store()

    session = await store.create(
        workflow_id="test_history",
        entity_context={"customer_id": 789},
        user_id=4,
        team_id=1,
    )

    # 添加执行历史
    session.execution_history = [
        {"step_id": "step_1", "result": {"success": True}, "timestamp": "2026-06-10T10:00:00"},
        {"step_id": "step_2", "result": {"success": True, "data": {"contract_id": 123}}, "timestamp": "2026-06-10T10:01:00"},
    ]

    await store.save(session)

    # 恢复
    recovered = await store.load(session.session_id)

    assert len(recovered.execution_history) == 2, "execution_history 长度不匹配"
    assert recovered.execution_history[1]["step_id"] == "step_2", "第二条历史不匹配"

    print(f"✅ 执行历史记录正确")
    print(f"   execution_history length: {len(recovered.execution_history)}")

    # 清理
    await store.delete(session.session_id)

    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Workflow Session Recovery 测试")
    print("=" * 60)

    results = []

    try:
        results.append(("test_session_create_and_load", await test_session_create_and_load()))
    except Exception as e:
        results.append(("test_session_create_and_load", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_session_update_and_recovery", await test_session_update_and_recovery()))
    except Exception as e:
        results.append(("test_session_update_and_recovery", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_session_ttl", await test_session_ttl()))
    except Exception as e:
        results.append(("test_session_ttl", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_session_execution_history", await test_session_execution_history()))
    except Exception as e:
        results.append(("test_session_execution_history", False))
        print(f"❌ 失败: {e}")

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！Session 恢复功能正常。")
        return 0
    else:
        print("\n⚠️  存在失败的测试，请检查 Redis 连接和配置。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
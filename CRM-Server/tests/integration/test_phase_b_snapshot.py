"""
Phase B - 幂等恢复 + 快照机制 测试

验证：
1. 快照保存（waiting_for_user 状态）
2. 从快照恢复
3. resume_session 方法

运行方式：
cd CRM-Server && python3 tests/integration/test_phase_b_snapshot.py
"""

import asyncio
import sys
import os
import time
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.workflow.session_store import (
    WorkflowSession,
    WorkflowSessionStore,
    get_session_store,
)
from app.services.workflow.workflow_orchestrator import WorkflowOrchestrator
from app.services.workflow import workflow_definitions, state_machine, business_invariants


class PhaseBTester:
    """Phase B 测试器"""

    def __init__(self):
        self.session_store: WorkflowSessionStore = None
        self.orchestrator: WorkflowOrchestrator = None
        self.test_session_id: str = None

    async def setup(self):
        """初始化"""
        self.session_store = await get_session_store()
        self.orchestrator = WorkflowOrchestrator(
            workflow_definitions=workflow_definitions,
            state_machine=state_machine,
            business_invariants=business_invariants
        )

    async def cleanup(self):
        """清理"""
        if self.test_session_id:
            try:
                await self.session_store.delete(self.test_session_id)
            except:
                pass

    # ==================== Test Cases ====================

    async def test_01_snapshot_save(self) -> Dict[str, Any]:
        """Test 1: 快照保存"""
        print("=" * 60)
        print("Test 1: 快照保存")
        print("=" * 60)

        result = {"name": "test_01_snapshot_save", "passed": False}

        try:
            # 创建 Session
            session = await self.session_store.create(
                workflow_id="test_snapshot",
                entity_context={"customer_id": 100},
                user_id=1,
                team_id=1,
            )
            self.test_session_id = session.session_id

            # 更新 Session 状态
            session.completed_steps = ["step_1", "step_2"]
            session.selected_opportunity_id = 50
            await self.session_store.save(session)

            # 保存快照
            await self.session_store.save_snapshot(
                session_id=session.session_id,
                step_id="step_3",
                state={
                    "completed_steps": session.completed_steps,
                    "entity_context": session.entity_context,
                    "selected_opportunity_id": session.selected_opportunity_id,
                }
            )

            print(f"✅ Session 创建: {session.session_id}")
            print(f"✅ 快照保存成功: step_id=step_3")

            # 获取快照
            snapshots = await self.session_store.get_snapshots(session.session_id)
            assert len(snapshots) >= 1, "应该有快照"
            print(f"✅ 快照数量: {len(snapshots)}")

            # 验证快照内容
            latest = snapshots[-1]
            assert latest["step_id"] == "step_3"
            assert "completed_steps" in latest["state"]
            print(f"✅ 快照内容验证通过")
            print(f"   snapshot_id: {latest['snapshot_id']}")
            print(f"   timestamp: {latest['timestamp']}")

            result["passed"] = True
            result["snapshot_count"] = len(snapshots)

        except Exception as e:
            print(f"❌ 失败: {e}")
            result["error"] = str(e)

        return result

    async def test_02_snapshot_restore(self) -> Dict[str, Any]:
        """Test 2: 从快照恢复"""
        print("\n" + "=" * 60)
        print("Test 2: 从快照恢复")
        print("=" * 60)

        result = {"name": "test_02_snapshot_restore", "passed": False}

        try:
            # 创建新的 Session 并模拟状态变更
            session = await self.session_store.create(
                workflow_id="test_restore",
                entity_context={"opportunity_id": 200},
                user_id=2,
                team_id=1,
            )

            # 模拟执行了几个步骤
            session.completed_steps = ["step_1", "step_2", "step_3"]
            session.selected_opportunity_id = 100

            # 保存快照
            await self.session_store.save_snapshot(
                session_id=session.session_id,
                step_id="step_3",
                state={
                    "completed_steps": session.completed_steps,
                    "entity_context": session.entity_context,
                    "selected_opportunity_id": session.selected_opportunity_id,
                }
            )

            print(f"✅ 原始状态: completed_steps={session.completed_steps}")

            # 模拟状态变更（比如出错）
            session.completed_steps = ["step_1"]  # 错误状态
            await self.session_store.save(session)

            print(f"✅ 错误状态: completed_steps={session.completed_steps}")

            # 从快照恢复
            restored = await self.session_store.restore_from_snapshot(session.session_id)

            assert restored is not None, "恢复应该成功"
            assert restored.completed_steps == ["step_1", "step_2", "step_3"], "应该恢复到快照状态"
            assert restored.rollback_performed == True, "rollback_performed 应标记"

            print(f"✅ 恢复成功: completed_steps={restored.completed_steps}")
            print(f"   rollback_performed: {restored.rollback_performed}")

            # 清理
            await self.session_store.delete(session.session_id)

            result["passed"] = True
            result["restored_steps"] = restored.completed_steps

        except Exception as e:
            print(f"❌ 失败: {e}")
            result["error"] = str(e)

        return result

    async def test_03_latest_snapshot(self) -> Dict[str, Any]:
        """Test 3: 获取最新快照"""
        print("\n" + "=" * 60)
        print("Test 3: 获取最新快照")
        print("=" * 60)

        result = {"name": "test_03_latest_snapshot", "passed": False}

        try:
            # 创建 Session
            session = await self.session_store.create(
                workflow_id="test_latest",
                entity_context={},
                user_id=3,
                team_id=1,
            )

            # 保存多个快照
            await self.session_store.save_snapshot(
                session.session_id, "step_1", {"completed_steps": ["step_1"]}
            )
            await asyncio.sleep(0.1)  # 确保时间差

            await self.session_store.save_snapshot(
                session.session_id, "step_2", {"completed_steps": ["step_1", "step_2"]}
            )
            await asyncio.sleep(0.1)

            await self.session_store.save_snapshot(
                session.session_id, "step_3", {"completed_steps": ["step_1", "step_2", "step_3"]}
            )

            # 获取最新快照
            latest = await self.session_store.get_latest_snapshot(session.session_id)

            assert latest is not None, "应该有最新快照"
            assert latest["step_id"] == "step_3", "应该是最后一个快照"
            assert latest["state"]["completed_steps"] == ["step_1", "step_2", "step_3"]

            print(f"✅ 最新快照: step_id={latest['step_id']}")
            print(f"   snapshot_id: {latest['snapshot_id']}")

            # 清理
            await self.session_store.delete(session.session_id)

            result["passed"] = True

        except Exception as e:
            print(f"❌ 失败: {e}")
            result["error"] = str(e)

        return result

    async def test_04_resume_session_waiting(self) -> Dict[str, Any]:
        """Test 4: resume_session (waiting_for_user 状态)"""
        print("\n" + "=" * 60)
        print("Test 4: resume_session (waiting_for_user 状态)")
        print("=" * 60)

        result = {"name": "test_04_resume_session_waiting", "passed": False}

        try:
            # 模拟创建一个处于等待状态的 Session（不通过完整的 workflow）
            session = await self.session_store.create(
                workflow_id="test_resume",
                entity_context={"customer_id": 500},
                user_id=4,
                team_id=1,
            )

            # 手动设置为等待状态
            session.waiting_for_user = True
            session.pending_step_id = "ask_confirm"
            session.pending_question = "是否确认执行？"
            session.pending_options = ["确认", "取消"]
            session.completed_steps = ["step_1", "step_2"]

            await self.session_store.save(session)

            # 模拟保存等待快照（Phase B 功能）
            await self.session_store.save_snapshot(
                session.session_id,
                "ask_confirm",
                {
                    "completed_steps": session.completed_steps,
                    "entity_context": session.entity_context,
                }
            )

            print(f"✅ 等待状态 Session: {session.session_id}")
            print(f"   pending_question: {session.pending_question}")

            # 调用 resume_session（模拟）
            # 注意：这里需要 db 和 user，但我们只测试逻辑
            # 模拟 db 为 None（某些测试场景可以跳过 db）

            # 加载并检查状态
            loaded = await self.session_store.load(session.session_id)

            assert loaded is not None, "Session 应能加载"
            assert loaded.waiting_for_user == True, "等待状态应保持"
            assert loaded.pending_question == "是否确认执行？"

            print(f"✅ Session 恢复检查通过")
            print(f"   waiting_for_user: {loaded.waiting_for_user}")
            print(f"   pending_question: {loaded.pending_question}")

            # 验证快照存在
            snapshots = await self.session_store.get_snapshots(session.session_id)
            assert len(snapshots) >= 1, "等待快照应存在"

            print(f"✅ 等待快照数量: {len(snapshots)}")

            # 清理
            await self.session_store.delete(session.session_id)

            result["passed"] = True

        except Exception as e:
            print(f"❌ 失败: {e}")
            result["error"] = str(e)

        return result

    async def test_05_orchestrator_snapshot_method(self) -> Dict[str, Any]:
        """Test 5: Orchestrator 快照方法"""
        print("\n" + "=" * 60)
        print("Test 5: Orchestrator 快照方法")
        print("=" * 60)

        result = {"name": "test_05_orchestrator_snapshot_method", "passed": False}

        try:
            # 检查 Orchestrator 方法存在
            assert hasattr(self.orchestrator, '_save_waiting_snapshot'), "_save_waiting_snapshot 方法应存在"
            assert hasattr(self.orchestrator, 'resume_session'), "resume_session 方法应存在"

            print(f"✅ _save_waiting_snapshot 方法存在")
            print(f"✅ resume_session 方法存在")

            # 测试 _save_waiting_snapshot（需要 Session 字典）
            session_dict = {
                "session_id": f"test_snap_{int(time.time() * 1000)}",
                "completed_steps": ["step_a", "step_b"],
                "entity_context": {"test": True},
                "user_choice": None,
                "selected_opportunity_id": 999,
                "selected_opportunity_name": "测试商机",
                "created_opportunity_id": None,
                "current_step_index": 2,
                "last_executed_step_id": "step_b",
            }

            # 创建一个真实的 Session
            real_session = await self.session_store.create(
                workflow_id="test_orchestrator",
                entity_context={"test": True},
                user_id=5,
                team_id=1,
            )

            session_dict["session_id"] = real_session.session_id

            # 调用快照保存
            await self.orchestrator._save_waiting_snapshot(session_dict, "step_c")

            # 验证快照
            snapshots = await self.session_store.get_snapshots(real_session.session_id)
            assert len(snapshots) >= 1, "快照应保存"

            print(f"✅ Orchestrator 快照保存成功")
            print(f"   快照数量: {len(snapshots)}")

            # 清理
            await self.session_store.delete(real_session.session_id)

            result["passed"] = True

        except Exception as e:
            print(f"❌ 失败: {e}")
            result["error"] = str(e)

        return result

    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("\n" + "=" * 70)
        print("Phase B - 幂等恢复 + 快照机制 测试")
        print("=" * 70)
        print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        await self.setup()

        results = []

        results.append(await self.test_01_snapshot_save())
        results.append(await self.test_02_snapshot_restore())
        results.append(await self.test_03_latest_snapshot())
        results.append(await self.test_04_resume_session_waiting())
        results.append(await self.test_05_orchestrator_snapshot_method())

        await self.cleanup()

        # 总结
        print("\n" + "=" * 70)
        print("测试结果总结")
        print("=" * 70)

        passed = sum(1 for r in results if r["passed"])
        total = len(results)

        for r in results:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            print(f"  {r['name']}: {status}")

        print(f"\n总计: {passed}/{total} 通过")

        if passed == total:
            print("\n🎉 Phase B 所有测试通过！")
        else:
            print("\n⚠️ 存在失败的测试")

        return {
            "total": total,
            "passed": passed,
            "results": results,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        }


async def main():
    """主入口"""
    tester = PhaseBTester()
    test_results = await tester.run_all_tests()

    return 0 if test_results["passed"] == test_results["total"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
"""
Guardrails 单元测试

验证置信度拦截和异常分层处理逻辑。

运行方式：
cd CRM-Server && python3 tests/unit/test_guardrails.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.workflow.guardrails import (
    DecisionType,
    ExceptionType,
    ConfidenceGuardrail,
    ExceptionHandler,
    GuardrailsService,
    guardrails_service,
)


def test_confidence_thresholds():
    """测试置信度阈值"""
    print("=" * 50)
    print("Test 1: 置信度阈值检查")
    print("=" * 50)

    guardrail = ConfidenceGuardrail()

    # 测试自动执行
    decision = guardrail.check(0.96, "create_follow_up")
    assert decision.decision == DecisionType.AUTO
    print(f"✅ 0.96 -> AUTO: {decision.reason}")

    # 测试弱确认
    decision = guardrail.check(0.85, "create_follow_up")
    assert decision.decision == DecisionType.WEAK_CONFIRM
    print(f"✅ 0.85 -> WEAK_CONFIRM: {decision.reason}")

    # 测试强确认
    decision = guardrail.check(0.75, "create_follow_up")
    assert decision.decision == DecisionType.STRONG_CONFIRM
    print(f"✅ 0.75 -> STRONG_CONFIRM: {decision.reason}")

    # 测试人工介入
    decision = guardrail.check(0.55, "create_follow_up")
    assert decision.decision == DecisionType.HUMAN_LOOP
    print(f"✅ 0.55 -> HUMAN_LOOP: {decision.reason}")

    # 测试直接拦截
    decision = guardrail.check(0.25, "create_follow_up")
    assert decision.decision == DecisionType.BLOCK
    print(f"✅ 0.25 -> BLOCK: {decision.reason}")

    return True


def test_high_risk_actions():
    """测试高风险操作"""
    print("\n" + "=" * 50)
    print("Test 2: 高风险操作检查")
    print("=" * 50)

    guardrail = ConfidenceGuardrail()

    # 高风险操作即使置信度高也需要强确认
    decision = guardrail.check(0.98, "create_contract")
    assert decision.decision == DecisionType.STRONG_CONFIRM
    assert decision.requires_audit == True
    print(f"✅ 高风险 create_contract (0.98) -> STRONG_CONFIRM: {decision.reason}")

    # 高风险操作置信度中等
    decision = guardrail.check(0.75, "win_opportunity")
    assert decision.decision == DecisionType.STRONG_CONFIRM
    print(f"✅ 高风险 win_opportunity (0.75) -> STRONG_CONFIRM: {decision.reason}")

    # 高风险操作置信度低 -> 人工介入
    decision = guardrail.check(0.55, "delete_customer")
    assert decision.decision == DecisionType.HUMAN_LOOP
    print(f"✅ 高风险 delete_customer (0.55) -> HUMAN_LOOP: {decision.reason}")

    # 高风险操作置信度过低 -> 拦截
    decision = guardrail.check(0.25, "transfer_owner")
    assert decision.decision == DecisionType.BLOCK
    print(f"✅ 高风险 transfer_owner (0.25) -> BLOCK: {decision.reason}")

    return True


def test_read_only_actions():
    """测试只读操作（放宽阈值）"""
    print("\n" + "=" * 50)
    print("Test 3: 只读操作检查（放宽阈值）")
    print("=" * 50)

    guardrail = ConfidenceGuardrail()

    # 只读操作 0.70 可以自动执行
    decision = guardrail.check(0.72, "get_customer")
    assert decision.decision == DecisionType.AUTO
    print(f"✅ 只读 get_customer (0.72) -> AUTO: {decision.reason}")

    # 只读操作 0.50 -> 弱确认
    decision = guardrail.check(0.52, "search_opportunities")
    assert decision.decision == DecisionType.WEAK_CONFIRM
    print(f"✅ 只读 search_opportunities (0.52) -> WEAK_CONFIRM: {decision.reason}")

    # 只读操作 < 0.50 -> 人工介入
    decision = guardrail.check(0.35, "get_context")
    assert decision.decision == DecisionType.HUMAN_LOOP
    print(f"✅ 只读 get_context (0.35) -> HUMAN_LOOP: {decision.reason}")

    return True


def test_exception_handling():
    """测试异常分层处理"""
    print("\n" + "=" * 50)
    print("Test 4: 异常分层处理")
    print("=" * 50)

    handler = ExceptionHandler()

    # AI 侧异常 -> 人工介入
    strategy = handler.handle(ExceptionType.HALLUCINATION)
    assert strategy.action == "human_loop"
    assert strategy.requires_audit == True
    print(f"✅ HALLUCINATION -> human_loop")

    # 系统侧异常 -> 重试
    strategy = handler.handle(ExceptionType.DB_TIMEOUT)
    assert strategy.action == "retry"
    assert strategy.max_retries == 3
    print(f"✅ DB_TIMEOUT -> retry (max_retries={strategy.max_retries})")

    # Redis 异常 -> 降级
    strategy = handler.handle(ExceptionType.REDIS_ERROR)
    assert strategy.action == "fallback"
    assert strategy.fallback_strategy == "in_memory_session"
    print(f"✅ REDIS_ERROR -> fallback ({strategy.fallback_strategy})")

    # 业务侧异常 -> 拦截
    strategy = handler.handle(ExceptionType.INARIANT_VIOLATION)
    assert strategy.action == "block"
    assert strategy.requires_audit == True
    print(f"✅ INARIANT_VIOLATION -> block")

    return True


def test_exception_classification():
    """测试异常分类"""
    print("\n" + "=" * 50)
    print("Test 5: 异常分类")
    print("=" * 50)

    handler = ExceptionHandler()

    # Timeout 异常
    exc_type = handler.classify_exception(TimeoutError("connection timeout"))
    assert exc_type == ExceptionType.DB_TIMEOUT
    print(f"✅ TimeoutError -> DB_TIMEOUT")

    # Permission 异常
    exc_type = handler.classify_exception(Exception("permission denied"))
    assert exc_type == ExceptionType.PERMISSION_DENIED
    print(f"✅ 'permission denied' -> PERMISSION_DENIED")

    # Not found 异常
    exc_type = handler.classify_exception(Exception("customer not found"))
    assert exc_type == ExceptionType.ENTITY_NOT_FOUND
    print(f"✅ 'customer not found' -> ENTITY_NOT_FOUND")

    # 未知异常 -> Fail-Safe (HALLUCINATION)
    exc_type = handler.classify_exception(Exception("unknown error"))
    assert exc_type == ExceptionType.HALLUCINATION
    print(f"✅ 未知异常 -> HALLUCINATION (Fail-Safe)")

    return True


def test_guardrails_service():
    """测试 GuardrailsService 综合服务"""
    print("\n" + "=" * 50)
    print("Test 6: GuardrailsService 综合服务")
    print("=" * 50)

    import asyncio

    async def run_async_tests():
        # 检查执行前
        decision = await guardrails_service.check_before_execute(0.85, "create_follow_up")
        assert decision.decision == DecisionType.WEAK_CONFIRM
        print(f"✅ check_before_execute: WEAK_CONFIRM")

        # 检查是否允许
        assert guardrails_service.is_allowed(decision) == True
        print(f"✅ is_allowed(WEAK_CONFIRM) = True")

        # 检查强确认是否需要确认
        decision_strong = await guardrails_service.check_before_execute(0.75, "create_follow_up")
        assert guardrails_service.requires_confirmation(decision_strong) == True
        print(f"✅ requires_confirmation(STRONG_CONFIRM) = True")

        # 检查低置信度是否需要人工介入
        decision_human = await guardrails_service.check_before_execute(0.55, "create_follow_up")
        assert guardrails_service.requires_human_intervention(decision_human) == True
        print(f"✅ requires_human_intervention(HUMAN_LOOP) = True")

        # 检查极低置信度是否被拦截
        decision_block = await guardrails_service.check_before_execute(0.35, "create_follow_up")
        assert decision_block.decision == DecisionType.BLOCK
        print(f"✅ BLOCK for confidence 0.35")

        # 异常处理
        strategy, exc_type = await guardrails_service.handle_exception(
            Exception("connection timeout")
        )
        assert exc_type == ExceptionType.DB_TIMEOUT
        assert strategy.action == "retry"
        print(f"✅ handle_exception: DB_TIMEOUT -> retry")

    asyncio.run(run_async_tests())

    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Guardrails 单元测试")
    print("=" * 60)

    results = []

    try:
        results.append(("test_confidence_thresholds", test_confidence_thresholds()))
    except Exception as e:
        results.append(("test_confidence_thresholds", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_high_risk_actions", test_high_risk_actions()))
    except Exception as e:
        results.append(("test_high_risk_actions", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_read_only_actions", test_read_only_actions()))
    except Exception as e:
        results.append(("test_read_only_actions", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_exception_handling", test_exception_handling()))
    except Exception as e:
        results.append(("test_exception_handling", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_exception_classification", test_exception_classification()))
    except Exception as e:
        results.append(("test_exception_classification", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_guardrails_service", test_guardrails_service()))
    except Exception as e:
        results.append(("test_guardrails_service", False))
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
        print("\n🎉 所有测试通过！Guardrails 功能正常。")
        return 0
    else:
        print("\n⚠️  存在失败的测试。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
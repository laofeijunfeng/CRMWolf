"""
TraceContext 测试

验证全链路 TraceId 和 AI Decision Audit 功能。

运行方式：
cd CRM-Server && python3 tests/unit/test_trace_context.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.workflow.trace_context import (
    TraceContext,
    TraceLogger,
    generate_trace_id,
    generate_span_id,
    start_trace,
    end_trace,
    get_current_trace_context,
    trace_logger,
)


def test_trace_id_generation():
    """Test 1: TraceId 生成"""
    print("=" * 60)
    print("Test 1: TraceId 生成")
    print("=" * 60)

    # 生成 TraceId
    trace_id = generate_trace_id(user_id=2)
    print(f"✅ TraceId: {trace_id}")

    # 验证格式
    assert trace_id.startswith("trace_"), "TraceId 应以 trace_ 开头"
    parts = trace_id.split("_")
    assert len(parts) == 4, "TraceId 应有 4 部分"
    print(f"✅ 格式正确: trace_{parts[1]}_{parts[2]}_{parts[3]}")

    # 生成 SpanId
    span_id = generate_span_id()
    print(f"✅ SpanId: {span_id}")
    assert span_id.startswith("span_"), "SpanId 应以 span_ 开头"

    return True


def test_trace_context_basic():
    """Test 2: TraceContext 基本操作"""
    print("\n" + "=" * 60)
    print("Test 2: TraceContext 基本操作")
    print("=" * 60)

    # 创建 TraceContext
    ctx = TraceContext(user_id=3)
    print(f"✅ TraceContext 创建: {ctx.trace_id}")

    # 开始 Span
    span1 = ctx.start_span("workflow_start", {"workflow_id": "test_workflow"})
    print(f"✅ Span 开始: {span1.span_id}, operation={span1.operation}")

    # 结束 Span
    ctx.end_span(span1, status="success", result={"message": "完成"})
    print(f"✅ Span 结束: duration={span1.duration_ms:.2f}ms")

    # 获取摘要
    summary = ctx.get_summary()
    print(f"✅ 摘要: {summary}")

    assert summary["span_count"] == 1
    assert summary["operations"] == ["workflow_start"]

    return True


def test_nested_spans():
    """Test 3: 嵌套 Span"""
    print("\n" + "=" * 60)
    print("Test 3: 嵌套 Span")
    print("=" * 60)

    ctx = TraceContext(user_id=4)

    # 父 Span
    parent = ctx.start_span("workflow_start")
    print(f"✅ 父 Span: {parent.span_id}")

    # 子 Span
    child1 = ctx.start_span("tool_call", {"tool": "get_customer"}, parent_span_id=parent.span_id)
    print(f"✅ 子 Span 1: {child1.span_id}, parent={child1.parent_span_id}")

    # 更深层的 Span
    grandchild = ctx.start_span("db_query", {"query": "SELECT"}, parent_span_id=child1.span_id)
    print(f"✅ 孙 Span: {grandchild.span_id}, parent={grandchild.parent_span_id}")

    # 结束各层
    ctx.end_span(grandchild, status="success")
    ctx.end_span(child1, status="success")
    ctx.end_span(parent, status="success")

    print(f"✅ 嵌套结构完成")

    summary = ctx.get_summary()
    assert summary["span_count"] == 3
    print(f"✅ Span 数量: {summary['span_count']}")

    return True


def test_ai_decision_audit():
    """Test 4: AI Decision Audit"""
    print("\n" + "=" * 60)
    print("Test 4: AI Decision Audit")
    print("=" * 60)

    ctx = TraceContext(user_id=5)

    span = ctx.start_span("ai_intent_recognition")

    # 记录 AI 决策
    ctx.record_ai_decision(
        span,
        thought="用户想赢单，因为提到'成交'和'合同'",
        evidence="对话历史第3条",
        confidence=0.85,
        action_type="win_opportunity",
        params={"opportunity_id": 123},
        reasoning_trace=["识别关键词", "匹配意图", "提取实体"]
    )

    print(f"✅ AI Decision 已记录")

    ctx.end_span(span, status="success")

    # 验证记录
    assert span.ai_decision is not None
    assert span.ai_decision["confidence"] == 0.85
    assert span.ai_decision["action_type"] == "win_opportunity"
    assert len(span.ai_decision["reasoning_trace"]) == 3

    print(f"✅ AI Decision 数据验证通过")
    print(f"   thought: {span.ai_decision['thought']}")
    print(f"   confidence: {span.ai_decision['confidence']}")
    print(f"   action_type: {span.ai_decision['action_type']}")

    return True


def test_context_var():
    """Test 5: ContextVar 跨异步传递"""
    print("\n" + "=" * 60)
    print("Test 5: ContextVar 跨异步传递")
    print("=" * 60)

    import asyncio

    async def inner_function():
        ctx = get_current_trace_context()
        assert ctx is not None, "ContextVar 应能获取 TraceContext"
        print(f"✅ inner_function 获取 TraceContext: {ctx.trace_id}")
        return ctx.trace_id

    async def test_async():
        ctx = start_trace(user_id=6)
        print(f"✅ start_trace: {ctx.trace_id}")

        trace_id = await inner_function()

        result = end_trace()
        assert result is not None, "end_trace 应返回 Trace 数据"
        print(f"✅ end_trace: {result['trace_id']}")

        assert trace_id == ctx.trace_id

    asyncio.run(test_async())

    return True


def test_trace_logger():
    """Test 6: TraceLogger 日志记录"""
    print("\n" + "=" * 60)
    print("Test 6: TraceLogger 日志记录")
    print("=" * 60)

    logger = TraceLogger()

    ctx = TraceContext(user_id=7)
    span = ctx.start_span("test_operation")
    ctx.end_span(span, status="success")

    # 记录 Trace
    logger.log_trace(ctx)
    print(f"✅ Trace 已记录到 Logger")

    # 记录 AI Decision Audit
    span2 = ctx.start_span("ai_decision")
    ctx.record_ai_decision(span2, "test thought", "test evidence", 0.75, "test_action")
    ctx.end_span(span2, status="success")

    logger.log_ai_decision_audit(ctx)
    print(f"✅ AI Decision Audit 已记录")

    # 验证存储
    assert len(logger.traces) >= 1
    print(f"✅ Logger 中有 {len(logger.traces)} 条 Trace")

    return True


def test_serialization():
    """Test 7: 序列化输出"""
    print("\n" + "=" * 60)
    print("Test 7: 序列化输出")
    print("=" * 60)

    ctx = TraceContext(user_id=8)
    span = ctx.start_span("test_span")
    ctx.end_span(span, status="success")

    # to_dict
    data = ctx.to_dict()
    print(f"✅ to_dict: {data.keys()}")
    assert "trace_id" in data
    assert "spans" in data

    # to_json
    json_str = ctx.to_json()
    print(f"✅ to_json: {json_str[:100]}...")
    assert "{" in json_str

    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("TraceContext 单元测试")
    print("=" * 70)

    results = []

    try:
        results.append(("test_trace_id_generation", test_trace_id_generation()))
    except Exception as e:
        results.append(("test_trace_id_generation", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_trace_context_basic", test_trace_context_basic()))
    except Exception as e:
        results.append(("test_trace_context_basic", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_nested_spans", test_nested_spans()))
    except Exception as e:
        results.append(("test_nested_spans", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_ai_decision_audit", test_ai_decision_audit()))
    except Exception as e:
        results.append(("test_ai_decision_audit", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_context_var", test_context_var()))
    except Exception as e:
        results.append(("test_context_var", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_trace_logger", test_trace_logger()))
    except Exception as e:
        results.append(("test_trace_logger", False))
        print(f"❌ 失败: {e}")

    try:
        results.append(("test_serialization", test_serialization()))
    except Exception as e:
        results.append(("test_serialization", False))
        print(f"❌ 失败: {e}")

    # 总结
    print("\n" + "=" * 70)
    print("测试结果总结")
    print("=" * 70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！TraceContext 功能正常。")
        return 0
    else:
        print("\n⚠️  存在失败的测试。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
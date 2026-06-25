# Task 3: SSE tool_call/tool_result 补充字段

**Files:**
- Modify: `CRM-Server/app/services/langgraph/sse_wrapper.py`
- Test: `CRM-Server/tests/test_sse_wrapper.py`

**Interfaces:**
- Consumes: `build_tool_call_event()`, `build_tool_result_event()` 现有签名
- Produces: `thinking` (tool_call), `summary` (tool_result)

## Steps

### Step 1: Write the failing tests

```python
# CRM-Server/tests/test_sse_wrapper.py

def test_tool_call_v2_thinking_field():
    """测试 tool_call 事件包含 AI 推理过程"""
    event = build_tool_call_event(
        tool="search_customer",
        params={"keyword": "光大证券"},
        thinking="用户想跟进光大证券，需要先找到客户..."
    )
    
    data = json.loads(event.split("data: ")[1])
    
    assert data["tool"] == "search_customer"
    assert data["params"]["keyword"] == "光大证券"
    assert data["thinking"] == "用户想跟进光大证券，需要先找到客户..."

def test_tool_result_v2_summary_field():
    """测试 tool_result 事件包含业务化摘要"""
    event = build_tool_result_event(
        tool="search_customer",
        result={"count": 1, "customers": [{"name": "光大证券"}]},
        summary="找到 1 个客户：光大证券股份有限公司"
    )
    
    data = json.loads(event.split("data: ")[1])
    
    assert data["tool"] == "search_customer"
    assert data["result"]["count"] == 1
    assert data["summary"] == "找到 1 个客户：光大证券股份有限公司"
```

### Step 2: Run tests to verify they fail

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_tool_call_v2_thinking_field -v`
Expected: FAIL with "TypeError: unexpected keyword argument 'thinking'"

### Step 3: Write minimal implementation

```python
# CRM-Server/app/services/langgraph/sse_wrapper.py

def build_tool_call_event(
    tool: str,
    params: Optional[Dict[str, Any]] = None,
    thinking: Optional[str] = None  # ← V2 新增：AI 推理过程
) -> str:
    return build_sse_event(
        SSE_EVENT_TYPES["TOOL_CALL"],
        {
            "tool": tool,
            "params": params or {},
            "thinking": thinking
        }
    )

def build_tool_result_event(
    tool: str,
    result: Dict[str, Any],
    summary: Optional[str] = None  # ← V2 新增：业务化摘要
) -> str:
    display_result = filter_result_for_display(result)
    return build_sse_event(
        SSE_EVENT_TYPES["TOOL_RESULT"],
        {
            "tool": tool,
            "result": display_result,
            "summary": summary
        }
    )
```

### Step 4: Run tests to verify they pass

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_tool_call_v2_thinking_field CRM-Server/tests/test_sse_wrapper.py::test_tool_result_v2_summary_field -v`
Expected: PASS (both tests)

### Step 5: Commit

```bash
git add CRM-Server/app/services/langgraph/sse_wrapper.py CRM-Server/tests/test_sse_wrapper.py
git commit -m "feat(sse): add thinking/summary fields to tool_call/tool_result events"
```
# Task 1: SSE waiting_for_user 事件补充字段

**Files:**
- Modify: `CRM-Server/app/services/langgraph/sse_wrapper.py`
- Test: `CRM-Server/tests/test_sse_wrapper.py`

**Interfaces:**
- Consumes: `build_waiting_for_user_event()` 现有签名
- Produces: 新字段 `confirmationType`, `riskLevel`, `params`, `options` (Dict格式)

## Steps

### Step 1: Write the failing test

```python
# CRM-Server/tests/test_sse_wrapper.py

def test_waiting_for_user_v2_fields():
    """测试 V2 SSE waiting_for_user 事件包含所有必需字段"""
    event = build_waiting_for_user_event(
        question="请选择目标客户",
        confirmationType="disambiguation",
        options=[
            {"id": 16, "name": "光大证券", "entity_info_inline": "ID:16 · 金融 · 活跃"}
        ],
        riskLevel="low",
        params={"action": "create_follow_up", "customer": "光大证券"}
    )
    
    data = json.loads(event.split("data: ")[1])
    
    assert data["confirmationType"] == "disambiguation"
    assert data["riskLevel"] == "low"
    assert data["params"]["action"] == "create_follow_up"
    assert len(data["options"]) == 1
    assert data["options"][0]["entity_info_inline"] == "ID:16 · 金融 · 活跃"
```

### Step 2: Run test to verify it fails

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_waiting_for_user_v2_fields -v`
Expected: FAIL with "TypeError: build_waiting_for_user_event() got unexpected keyword argument 'confirmationType'"

### Step 3: Write minimal implementation

```python
# CRM-Server/app/services/langgraph/sse_wrapper.py

def build_waiting_for_user_event(
    question: str,
    confirmationType: str,  # ← V2 新增："disambiguation" | "confirmation" | "info_gap"
    options: Optional[List[Dict[str, Any]]] = None,  # ← V2 改为 Dict 格式
    missing_fields: Optional[List[str]] = None,
    field_options: Optional[Dict[str, Any]] = None,
    riskLevel: Optional[str] = None,  # ← V2 新增："low" | "medium" | "high"
    params: Optional[Dict[str, Any]] = None,  # ← V2 新增：当前操作参数
) -> str:
    data = {
        "question": question,
        "confirmationType": confirmationType,
        "options": options or [],
        "missing_fields": missing_fields or [],
        "field_options": field_options or {},
        "riskLevel": riskLevel,
        "params": params,
    }
    return build_sse_event(SSE_EVENT_TYPES["WAITING_FOR_USER"], data)
```

### Step 4: Run test to verify it passes

Run: `pytest CRM-Server/tests/test_sse_wrapper.py::test_waiting_for_user_v2_fields -v`
Expected: PASS

### Step 5: Commit

```bash
git add CRM-Server/app/services/langgraph/sse_wrapper.py CRM-Server/tests/test_sse_wrapper.py
git commit -m "feat(sse): add V2 fields to waiting_for_user event (confirmationType/riskLevel/params)"
```
# Task 2: EntityCandidate 补充字段

**Files:**
- Modify: `CRM-Server/app/services/langgraph/state.py`
- Test: `CRM-Server/tests/test_state.py`

**Interfaces:**
- Consumes: `EntityCandidate` 现有字段（id, name, hint, matched_by, entity_type）
- Produces: 新字段 `industry`, `status`, `amount`, `stage`, `entity_info_inline`, `entity_info_detail`

## Steps

### Step 1: Write the failing test

```python
# CRM-Server/tests/test_state.py

def test_entity_candidate_v2_fields():
    """测试 EntityCandidate V2 字段完整性"""
    candidate: EntityCandidate = {
        "id": 16,
        "name": "光大证券股份有限公司",
        "hint": "金融行业客户",
        "matched_by": "name",
        "entity_type": "customer",
        "industry": "金融",
        "status": "活跃",
        "amount": None,
        "stage": None,
        "entity_info_inline": "ID:16 · 金融 · 活跃",
        "entity_info_detail": {
            "industry": "金融服务业",
            "status": "活跃",
            "address": "上海市静安区"
        }
    }
    
    assert candidate["industry"] == "金融"
    assert candidate["status"] == "活跃"
    assert candidate["entity_info_inline"] == "ID:16 · 金融 · 活跃"
    assert candidate["entity_info_detail"]["address"] == "上海市静安区"
```

### Step 2: Run test to verify it fails

Run: `pytest CRM-Server/tests/test_state.py::test_entity_candidate_v2_fields -v`
Expected: FAIL with "KeyError: 'industry'" (TypedDict 字段不存在)

### Step 3: Write minimal implementation

```python
# CRM-Server/app/services/langgraph/state.py

class EntityCandidate(TypedDict):
    id: int
    name: str
    hint: str
    matched_by: str
    entity_type: str
    # ← V2 新增字段
    industry: Optional[str]       # 行业
    status: Optional[str]         # 状态
    amount: Optional[float]       # 金额（商机）
    stage: Optional[str]          # 阶段（商机）
    entity_info_inline: Optional[str]  # 格式化 Inline 文本
    entity_info_detail: Optional[Dict[str, Any]]  # Hover 详情
```

### Step 4: Run test to verify it passes

Run: `pytest CRM-Server/tests/test_state.py::test_entity_candidate_v2_fields -v`
Expected: PASS

### Step 5: Commit

```bash
git add CRM-Server/app/services/langgraph/state.py CRM-Server/tests/test_state.py
git commit -m "feat(state): add V2 fields to EntityCandidate (industry/status/entity_info_inline)"
```
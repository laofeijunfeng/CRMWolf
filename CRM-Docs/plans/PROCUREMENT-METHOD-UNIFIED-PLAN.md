---
status: active
created: 2026-06-11
updated: 2026-06-11
related_requirements: -
related_pr: -
---

# 采购方式 + AI 结构化输出 - 统一方案

## 问题根源

1. **两套系统不一致** - Workflow 和 ReAct 处理逻辑分散
2. **三个数据来源冲突** - 数据库、tools.py、前端都定义采购方式
3. **AI 行为不稳定** - 有时调用工具，有时返回自由文本

---

## 统一方案

### 核心原则

1. **唯一数据源** - 采购方式只从数据库查询
2. **统一处理入口** - 所有动态选项在 `ai_tool_service.py` 一处处理
3. **工具定义不含静态选项** - tools.py 只定义结构，不写具体值
4. **前端完全依赖后端** - 删除前端 fallback 配置

---

## 数据流设计

```
用户请求 → AI 判断意图 → 调用 ask_user 工具
                              ↓
                     返回 missing_fields（AI 必须填写）
                              ↓
                     后端检测字段 → 动态查询数据库 → 填充 field_options
                              ↓
                     返回 waiting_for_user 事件（结构化）
                              ↓
                     前端显示表单（下拉选项已填充）
```

---

## 改动清单

### 1. tools.py - 工具定义清理

**改动**：删除 `ask_user` 工具中的 `field_options` 参数定义

```python
# 改动前
"field_options": {
    "type": "object",
    "description": "字段的选项配置（用于下拉选择字段）",
    ...
}

# 改动后 - 删除此参数，后端动态填充
# AI 只返回 missing_fields，field_options 由后端补充
```

**原因**：AI 不需要知道具体选项，后端会动态查询数据库填充。

---

### 2. ai_tool_service.py - 统一处理入口

**改动**：统一动态选项获取逻辑

```python
# 统一处理入口（ai_tool_service.py）
def _enrich_field_options(self, missing_fields: list, field_options: dict, db: Session, team_id: int, entity_context: dict = None):
    """统一处理：根据 missing_fields 动态填充 field_options"""
    
    # 采购方式字段处理
    procurement_fields = ["procurement_method_name", "采购方式"]
    if any(f in missing_fields for f in procurement_fields):
        from app.crud.procurement import procurement_method_crud
        items, _ = procurement_method_crud.get_multi(db, team_id=team_id, is_active=1, limit=100)
        options = [item.name for item in items]
        
        for f in procurement_fields:
            if f in missing_fields:
                field_options[f] = {
                    "type": "select",
                    "options": options,
                    "default": options[0] if options else ""
                }
        
        # 客户默认采购方式
        if entity_context and entity_context.get("entity_type") == "customer":
            from app.crud.customer import customer_crud
            customer = customer_crud.get_by_id(db, entity_context["entity_id"], team_id)
            if customer and customer.default_procurement_method_id:
                default_method = procurement_method_crud.get(db, customer.default_procurement_method_id)
                if default_method and default_method.name in options:
                    for f in procurement_fields:
                        if f in missing_fields:
                            field_options[f]["default"] = default_method.name
    
    # 采购类型字段处理（固定选项）
    purchase_type_fields = ["purchase_type", "采购类型"]
    for f in purchase_type_fields:
        if f in missing_fields:
            field_options[f] = {
                "type": "select",
                "options": ["新购", "续购", "增购"],
                "default": "新购"
            }
    
    return field_options

# 在处理 ask_user 工具时调用
field_options = self._enrich_field_options(
    missing_fields=result.get("missing_fields", []),
    field_options=result.get("field_options", {}),
    db=db,
    team_id=team_id,
    entity_context=entity_context
)
```

---

### 3. workflow_orchestrator.py - 统一调用

**改动**：调用统一方法，删除重复逻辑

```python
# 在 _execute_ask_user_step 中
from app.services.ai_tool_service import AIToolService

# 调用统一方法
field_options = AIToolService()._enrich_field_options(
    missing_fields=missing_fields,
    field_options=field_options,
    db=db,
    team_id=session.get("team_id"),
    entity_context=session.get("entity_context")
)
```

---

### 4. workflow_definitions.py - 清理配置

**改动**：删除 `options_from_db` 标记，简化配置

```python
# 改动前
"field_options": {
    "procurement_method_name": {
        "type": "select",
        "options_from_db": "procurement_methods",
        "default_from": "customer_procurement_method"
    }
}

# 改动后 - 只声明字段，后端统一处理
"field_options": {}  # 空对象，后端会填充
```

---

### 5. 前端 MagicWandDialog.vue - 删除 fallback

**改动**：删除前端硬编码的采购方式默认值

```typescript
// 删除以下代码
const defaultFieldOptions = {
    '采购方式': {
        options: ['公开招标', '竞争性谈判', ...]  // 删除
    }
}

// 改为：完全依赖后端传的 field_options
if (!workflowFieldOptions.value[field]) {
    // 没有选项配置 → 显示普通输入框（不硬编码选项）
}
```

---

## 验证清单

1. **数据库查询唯一** - 只有 `procurement_method_crud.get_multi` 查询
2. **处理入口唯一** - `_enrich_field_options` 方法一处调用
3. **tools.py 不写死** - 无静态选项定义
4. **前端不 fallback** - 无硬编码默认值
5. **完整流程测试** - 创建商机 → ask_user → 显示表单 → 下拉选项正确

---

## 执行顺序

1. ai_tool_service.py - 添加统一方法
2. workflow_orchestrator.py - 调用统一方法
3. tools.py - 清理工具定义
4. workflow_definitions.py - 清理配置
5. 前端 - 删除 fallback
6. 测试验证
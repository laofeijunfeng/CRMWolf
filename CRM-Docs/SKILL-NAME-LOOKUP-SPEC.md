"""
Handler 名称查找规范

定义各类型 Handler 的默认配置和行为规范

## 核心原则

1. **用户友好**：用户输入名称即可操作，无需查询 ID
2. **智能匹配**：名称唯一时直接操作，多条时提示选择
3. **向后兼容**：ID 参数始终可选，作为精确定位方式

## Handler 分类

### 需要名称查找的 Handler（实体操作类）

| Handler | 典型场景 | 需要名称查找 |
|---------|---------|-------------|
| FollowUpHandler | 线索跟进、客户跟进、商机跟进 | ✓ 必需 |
| StatusChangeHandler | 线索转化、商机赢单、商机输单 | ✓ 必需 |
| LeadConvertHandler | 线索转化为客户 | ✓ 必需 |
| QueryDetailHandler | 查询线索详情、客户详情、商机详情 | ✓ 必需 |
| UpdateHandler | 更新客户信息、更新商机信息 | ✓ 必需（待开发） |
| DeleteHandler | 删除线索、删除客户 | ✓ 必需（待开发） |

### 不需要名称查找的 Handler

| Handler | 典型场景 | 原因 |
|---------|---------|------|
| QueryListHandler | 线索列表、客户列表 | 列表查询，支持 keyword 搜索 |
| CreateHandler | 新建线索、新建客户 | 创建操作，输入名称作为新实体名称 |
| AggregateHandler | 统计数据 | 统计类，无特定实体 |

## 配置规范

### 1. CRUD Mapping 必须配置 name_field

已配置 name_field 的实体：
- lead: lead_name
- customer: account_name
- opportunity: opportunity_name
- contract: contract_name
- invoice_title: title_name

无 name_field 的实体（不能通过名称查找）：
- lead_follow_up, customer_follow_up, opportunity_follow_up（跟进记录）
- payment_plan, payment_record, invoice_application（流程记录）
- 日志类、配置类

### 2. Action 创建时的默认配置

```json
{
  "handler_config": {
    "crud_mapping": "lead",
    "name_lookup_field": "lead_name",  // 用户输入的参数名（与 name_field 相同）
    "name_field": "lead_name",          // 实体的名称字段（从 CRUD Mapping 读取）
    "exclude_status": ["CONVERTED", "INVALID"]
  },
  "required_params": [],                // 不强制要求 ID
  "optional_params": ["lead_name", "lead_id"]
}
```

### 3. Handler 执行时的查找逻辑

```
1. 尝试名称查找 → 匹配结果
   - 无匹配 → 返回错误："未找到..."
   - 唯一匹配 → 使用该实体
   - 多条匹配 → 返回列表让用户选择（显示 ID、状态、创建时间）

2. 名称查找失败 → 尝试 ID 查找
   - 有 ID → 直接使用

3. 都失败 → 返回错误："缺少参数：lead_name 或 lead_id"
```

## 其他场景考虑

### 1. 名称变更问题
- **场景**：客户名称修改后，历史对话中提到的旧名称无法匹配
- **方案**：名称查找使用模糊匹配，支持部分匹配

### 2. 无名称字段的实体
- **场景**：payment_plan、invoice_application 等无名称字段
- **方案**：这类实体只能通过 ID 操作，前端创建时提示

### 3. 跨模块操作
- **场景**："为广州益晟创建商机" - 需先查客户 ID，再创建商机
- **方案**：CreateHandler 支持关联实体名称查找（待开发）

### 4. 批量操作
- **场景**："批量跟进所有跟进中线索"
- **方案**：批量类 Handler 不支持名称查找，使用状态筛选

### 5. 名称精确度问题
- **场景**：用户输入"广州益晟"，实际名称"广州益晟项目管理咨询有限公司"
- **方案**：使用模糊匹配（LIKE '%keyword%')

### 6. 名称歧义问题
- **场景**：多个客户名称相似（如"广州分公司"）
- **方案**：多条匹配时返回详细信息（ID、状态、创建时间、负责人）

## 前端创建规范

### Action 创建表单

1. **选择 Handler 类型后自动配置**：
   - 实体操作类 Handler → 自动填充 name_lookup_field, name_field
   - 非实体操作类 Handler → 不显示名称查找配置

2. **配置项联动**：
   - 选择 crud_mapping → 自动读取 name_field
   - name_lookup_field 默认 = name_field

3. **提示信息**：
   - 实体有 name_field → 提示"用户可通过名称操作"
   - 实体无 name_field → 提示"该实体无名称字段，只能通过 ID 操作"

---

**版本：1.0 | 创建时间：2026-04-27**
"""
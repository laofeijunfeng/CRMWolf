# 合同审批流程优化实施总结

## 1. 优化概述

已成功实现完整的合同审批工作流系统，与现有合同状态流转解耦但协同工作，满足企业级多级审批、权限控制、完整审计等需求。

## 2. 核心数据模型

### 2.1 新增数据表

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `crm_approval_flows` | 审批流程模板表 | flow_code, min_amount, max_amount, license_type |
| `crm_approval_nodes` | 审批节点表 | flow_id, node_order, approve_role, is_required |
| `crm_contract_approvals` | 合同审批实例表 | contract_id, flow_id, current_node_id, status |
| `crm_contract_approval_records` | 审批记录表 | approval_id, node_id, approver_id, action, comment |

### 2.2 预置审批流程

系统已预置三个默认审批流程：

1. **小额合同审批** (`SMALL_CONTRACT`)
   - 条件：金额 < 10万
   - 节点：销售总监审批

2. **中等金额合同审批** (`MEDIUM_CONTRACT`)
   - 条件：10万 ≤ 金额 < 50万
   - 节点：销售总监审批 → 财务审批

3. **大额合同审批** (`LARGE_CONTRACT`)
   - 条件：金额 ≥ 50万
   - 节点：销售总监审批 → 财务审批 → 系统管理员审批

## 3. 审批状态流转

### 3.1 审批实例状态

```
PENDING (审批中)
    ↓
APPROVED (已通过) / REJECTED (已拒绝) / CANCELLED (已撤回)
```

### 3.2 合同状态与审批状态协同

```
合同 DRAFT → 提交审批 → 合同 PENDING_REVIEW + 审批 PENDING
    ↓
审批通过 → 合同 SIGNED + 审批 APPROVED
    ↓
审批拒绝 → 合同 DRAFT + 审批 REJECTED
```

## 4. API接口

### 4.1 审批流程管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/approvals/flows` | 获取审批流程列表 |
| GET | `/api/v1/approvals/flows/{id}` | 获取审批流程详情 |
| POST | `/api/v1/approvals/flows` | 创建审批流程（管理员） |
| PUT | `/api/v1/approvals/flows/{id}` | 更新审批流程（管理员） |

### 4.2 合同审批操作

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/approvals/contracts/{id}/submit` | 提交合同审批 |
| POST | `/api/v1/approvals/contracts/{id}/approve` | 审批通过/拒绝 |
| POST | `/api/v1/approvals/contracts/{id}/cancel` | 撤回审批 |
| GET | `/api/v1/approvals/contracts/{id}/detail` | 获取审批详情 |

## 5. 权限控制

### 5.1 提交权限
- 任何用户都可以提交自己创建的合同

### 5.2 审批权限
- 基于角色的权限控制
- 当前节点的 `approve_role` 决定谁可以审批
- 预置角色：`SALES_DIRECTOR`, `SYSTEM_ADMIN`

### 5.3 撤回权限
- 只有提交人可以撤回审批
- 只能撤回审批中的流程

## 6. 飞书通知集成

系统已集成飞书通知服务，在以下节点发送通知：

1. **提交审批时**
   - 通知第一级审批人
   - 内容：合同名称、审批流程、当前节点

2. **审批通过时**
   - 如果是最终节点通过：通知提交人
   - 如果有下一节点：通知下一级审批人

3. **审批拒绝时**
   - 通知提交人
   - 内容：拒绝原因

## 7. 测试验证

### 7.1 测试脚本

已创建测试脚本 `test_approval_workflow.py`，包含：

1. **单级审批测试**：小额合同（5万）
2. **多级审批测试**：大额合同（60万）

### 7.2 运行测试

```bash
python test_approval_workflow.py
```

## 8. 文件清单

### 8.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `app/models/approval.py` | 审批流程数据模型 |
| `app/schemas/approval.py` | 审批流程Schema定义 |
| `app/crud/approval.py` | 审批流程CRUD操作 |
| `app/api/approvals.py` | 审批流程API接口 |
| `migrate_create_approval_tables.sql` | 数据库迁移脚本（SQL） |
| `migrate_approval_simple.py` | 数据库迁移脚本（Python） |
| `test_approval_workflow.py` | 审批流程测试脚本 |

### 8.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `app/main.py` | 注册审批API路由 |
| `app/services/feishu.py` | 添加审批相关通知方法 |

## 9. 使用示例

### 9.1 提交合同审批

```bash
curl -X POST "http://localhost:8000/api/v1/approvals/contracts/1/submit" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "请审批"}'
```

### 9.2 审批通过

```bash
curl -X POST "http://localhost:8000/api/v1/approvals/contracts/1/approve" \
  -H "Authorization: Bearer APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "APPROVE", "comment": "同意"}'
```

### 9.3 审批拒绝

```bash
curl -X POST "http://localhost:8000/api/v1/approvals/contracts/1/approve" \
  -H "Authorization: Bearer APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "REJECT", "comment": "需要修改"}'
```

## 10. 后续扩展建议

1. **审批流程配置界面**：提供UI界面动态配置审批规则
2. **条件表达式**：支持更复杂的条件判断（部门、产品类型等）
3. **并行审批**：支持某些节点需要多人同时审批
4. **抄送通知**：在关键节点抄送给相关人员
5. **超时提醒**：审批超时自动提醒
6. **审批代理**：支持审批人设置代理审批人
7. **批量审批**：支持批量审批多个合同
8. **审批统计**：审批时效统计、审批通过率分析

## 11. 注意事项

1. **数据库依赖**：确保 `crm_contracts` 表已存在
2. **权限配置**：确保预置的角色（SALES_DIRECTOR等）已创建
3. **飞书集成**：飞书通知功能需要配置有效的飞书应用凭证
4. **审计追溯**：所有审批操作都会记录在 `crm_contract_approval_records` 表中

---

**实施状态**：✅ 已完成  
**最后更新**：2025-02-07  
**实施人员**：AI Assistant

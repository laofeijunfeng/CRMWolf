# 合同审批流程功能说明

> **版本：v1.0 | 最后更新：2026-06-30**
>
> 本文档提供 CRMWolf 系统审批流程功能的完整说明，包括用户操作指南、API 接口文档、权限模型和设计决策。

---

## 目录

- [功能概述](#功能概述)
- [用户操作指南（How-to）](#用户操作指南how-to)
- [API 接口文档（Reference）](#api-接口文档reference)
- [数据模型](#数据模型)
- [权限模型](#权限模型)
- [设计决策](#设计决策explanation)
- [常见问题](#常见问题)

---

## 功能概述

CRMWolf 审批流程系统支持合同的多级审批，管理员可配置审批流程模板，系统自动根据合同金额、授权类型匹配对应的审批流程。

**核心能力：**
- 多级审批节点配置（支持顺序审批）
- 基于角色的审批权限控制
- 自动流程匹配（金额、授权类型条件）
- 完整审批记录追溯
- 飞书通知集成
- AI 辅助创建审批流程

---

## 用户操作指南（How-to）

### 1. 提交合同审批

**适用角色：** 合同创建人（销售人员）

**操作步骤：**

1. 进入合同详情页面（合同状态必须是「草稿」）
2. 点击「提交审批」按钮
3. （可选）填写提交说明
4. 系统自动匹配审批流程，创建审批实例
5. 第一级审批人收到飞书通知

**业务规则：**
- 只有草稿（DRAFT）状态的合同可提交审批
- 系统根据合同金额和授权类型自动匹配审批流程
- 同一合同不能重复提交审批（需等待现有审批完成）

**预期结果：**
- 合同状态变为「审批中」（PENDING_REVIEW）
- 审批实例创建，流转到第一个审批节点

---

### 2. 审批通过/拒绝

**适用角色：** 当前审批节点的审批人

**操作步骤：**

1. 收到飞书审批通知
2. 进入合同详情页面
3. 查看合同信息、审批历史
4. 点击「同意」或「拒绝」按钮
5. 填写审批意见（拒绝时必填）

**同意后的流转：**
- 流转到下一审批节点 → 通知下一级审批人
- 全部节点通过 → 合同状态变为「已签署」→ 通知提交人

**拒绝后的流转：**
- 审批流程终止
- 合同状态回到「草稿」
- 提交人收到拒绝通知（含拒绝原因）
- 可修改后重新提交审批

**权限限制：**
- 必须拥有当前审批节点的角色权限
- 审批自己创建的合同需要 `contract:approve:own` 权限

---

### 3. 撤回审批

**适用角色：** 审批提交人

**操作步骤：**

1. 进入合同详情页面（审批状态必须是「审批中」）
2. 点击「撤回审批」按钮
3. 系统终止审批流程

**业务规则：**
- 只有审批提交人可以撤回
- 只能撤回审批中（PENDING）的流程
- 已通过或已拒绝的流程无法撤回

**预期结果：**
- 审批状态变为「已撤回」（CANCELLED）
- 合同状态回到「草稿」
- 可修改后重新提交审批

---

### 4. 管理员配置审批流程

**适用角色：** 系统管理员（需 `approval:flow:create` 权限）

**操作步骤：**

1. 进入「设置」→「审批流程管理」
2. 点击「新建流程」
3. 配置流程基本信息：
   - 流程名称（如：大额合同审批）
   - 流程编码（如：LARGE_CONTRACT）
   - 适用条件（金额范围、授权类型）
4. 添加审批节点：
   - 节点名称（如：销售总监审批）
   - 节点编码（如：SALES_DIRECTOR）
   - 审批角色（如：SALES_DIRECTOR）
   - 节点顺序（决定审批流转顺序）
5. 点击「创建」保存流程

**流程匹配规则：**
系统按以下优先级匹配审批流程：
1. 金额范围（min_amount ≤ 合同金额 ≤ max_amount）
2. 授权类型（license_type）

**预置审批流程：**

| 流程名称 | 流程编码 | 金额条件 | 审批节点 |
|---------|---------|---------|---------|
| 小额合同审批 | SMALL_CONTRACT | < 10万 | 销售总监审批 |
| 中等金额审批 | MEDIUM_CONTRACT | 10万-50万 | 销售总监 → 财务 |
| 大额合同审批 | LARGE_CONTRACT | ≥ 50万 | 销售总监 → 财务 → 系统管理员 |

---

### 5. AI 辅助创建审批流程

**适用角色：** 系统管理员

**操作步骤：**

1. 进入「设置」→「审批流程管理」
2. 点击「新建流程」
3. 使用 AI 辅助功能（未来版本支持）
4. 输入自然语言描述，如：「创建一个金额超过50万的合同审批流程，需要销售总监和财务审批」
5. AI 解析后生成流程配置预览
6. 确认后创建流程

**API 端点：**（已实现，前端待接入）
- `POST /v1/approval-ai/parse` - AI 解析审批流程配置
- `POST /v1/approval-ai/create` - 从解析结果创建流程

---

## API 接口文档（Reference）

### 审批流程管理 API

#### 获取审批流程列表

```
GET /v1/approvals/flows
```

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| skip | int | 否 | 跳过记录数，默认 0 |
| limit | int | 否 | 每页记录数，默认 100 |
| is_active | bool | 否 | 筛选启用状态 |

**响应示例：**

```json
[
  {
    "id": 1,
    "flow_name": "大额合同审批",
    "flow_code": "LARGE_CONTRACT",
    "description": "金额超过50万的合同审批流程",
    "min_amount": 500000,
    "max_amount": null,
    "license_type": null,
    "is_active": 1,
    "created_time": "2025-01-01T10:00:00"
  }
]
```

---

#### 获取审批流程详情

```
GET /v1/approvals/flows/{flow_id}
```

**响应示例：**

```json
{
  "id": 1,
  "flow_name": "大额合同审批",
  "flow_code": "LARGE_CONTRACT",
  "description": "...",
  "min_amount": 500000,
  "max_amount": null,
  "license_type": null,
  "is_active": 1,
  "nodes": [
    {
      "id": 1,
      "flow_id": 1,
      "node_name": "销售总监审批",
      "node_code": "SALES_DIRECTOR",
      "node_order": 1,
      "approve_role": "SALES_DIRECTOR",
      "is_required": 1
    },
    {
      "id": 2,
      "flow_name": "财务审批",
      "node_code": "FINANCE",
      "node_order": 2,
      "approve_role": "FINANCE",
      "is_required": 1
    }
  ]
}
```

---

#### 创建审批流程

```
POST /v1/approvals/flows
```

**权限要求：** `approval:flow:create`

**请求体：**

```json
{
  "flow_name": "大额合同审批",
  "flow_code": "LARGE_CONTRACT",
  "description": "金额超过50万的合同审批流程",
  "min_amount": 500000,
  "max_amount": null,
  "license_type": null,
  "nodes": [
    {
      "node_name": "销售总监审批",
      "node_code": "SALES_DIRECTOR",
      "node_order": 1,
      "approve_role": "SALES_DIRECTOR",
      "is_required": 1
    }
  ]
}
```

**校验规则：**
- `flow_code` 不能重复
- `nodes` 至少包含 1 个节点
- `approve_role` 必须是预定义角色（见权限模型）

---

#### 更新审批流程

```
PUT /v1/approvals/flows/{flow_id}
```

**权限要求：** `approval:flow:update`

**请求体：**（所有字段可选）

```json
{
  "flow_name": "更新后的流程名称",
  "is_active": 0,
  "nodes": [
    {
      "id": 1,
      "node_name": "更新后的节点名称"
    }
  ]
}
```

---

### 合同审批操作 API

#### 提交合同审批

```
POST /v1/approvals/contracts/{contract_id}/submit
```

**请求体：**

```json
{
  "comment": "请审批此合同"
}
```

**响应：** 审批实例详情（见审批详情响应）

**错误情况：**
- 合同不存在 → 404
- 合同状态不是草稿 → 400
- 未找到匹配的审批流程 → 400
- 已有待审批流程 → 400

---

#### 审批通过/拒绝

```
POST /v1/approvals/contracts/{contract_id}/approve
```

**请求体：**

```json
{
  "action": "APPROVE",
  "comment": "同意此合同"
}
```

```json
{
  "action": "REJECT",
  "comment": "合同条款需修改"
}
```

**权限要求：**
- 必须拥有当前审批节点的角色
- 审批自己的合同需要 `contract:approve:own` 权限

**错误情况：**
- 审批流程不存在 → 404
- 不是当前审批节点的审批人 → 403
- 审批自己的合同（无权限）→ 403

---

#### 撤回审批

```
POST /v1/approvals/contracts/{contract_id}/cancel
```

**业务规则：**
- 只有提交人可以撤回
- 只能撤回审批中（PENDING）的流程

**响应：**

```json
{
  "message": "审批已撤回"
}
```

---

#### 获取审批详情

```
GET /v1/approvals/contracts/{contract_id}/detail
```

**响应示例：**

```json
{
  "id": 1,
  "contract_id": 123,
  "flow_id": 1,
  "flow_name": "大额合同审批",
  "current_node_id": 2,
  "current_node_name": "财务审批",
  "status": "PENDING",
  "submitter_id": "ou_xxxx",
  "submitter_name": "张三",
  "created_time": "2025-01-01T10:00:00",
  "updated_time": "2025-01-02T14:00:00",
  "flow": {
    "id": 1,
    "flow_name": "大额合同审批",
    "nodes": [...]
  },
  "records": [
    {
      "id": 1,
      "node_id": 1,
      "node_name": "销售总监审批",
      "approver_id": "ou_yyyy",
      "approver_name": "李四",
      "action": "APPROVE",
      "comment": "同意",
      "created_time": "2025-01-01T12:00:00"
    }
  ]
}
```

---

### AI 审批流程解析 API

#### AI 解析审批流程配置

```
POST /v1/approval-ai/parse
```

**请求体：**

```json
{
  "content": "创建一个金额超过50万的合同审批流程，需要销售总监和财务审批"
}
```

**响应：** SSE 流式响应

**事件类型：**
- `status` - 状态更新
- `content` - AI 思考过程片段
- `parsed` - 解析完成，返回结构化配置
- `error` - 错误信息

---

#### 从 AI 解析结果创建流程

```
POST /v1/approval-ai/create
```

**权限要求：** `approval:flow:create`

**请求体：**（AI 解析后的结构化配置）

```json
{
  "flow_name": "大额合同审批",
  "flow_code": "LARGE_CONTRACT",
  "min_amount": 500000,
  "nodes": [
    {
      "node_name": "销售总监审批",
      "node_code": "SALES_DIRECTOR",
      "node_order": 1,
      "approve_role": "SALES_DIRECTOR"
    }
  ]
}
```

---

## 数据模型

### 审批状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 审批中 | PENDING | 审批流程进行中 |
| 已通过 | APPROVED | 全部节点审批通过 |
| 已拒绝 | REJECTED | 任一节点拒绝 |
| 已撤回 | CANCELLED | 提交人撤回审批 |

### 审批动作枚举

| 动作 | 编码 | 说明 |
|------|------|------|
| 提交 | SUBMIT | 提交审批 |
| 同意 | APPROVE | 审批通过 |
| 拒绝 | REJECT | 审批拒绝 |
| 回退 | ROLLBACK | 审批回退（预留） |

### 审批角色预定义

| 角色编码 | 显示名称 | 说明 |
|---------|---------|------|
| TEAM_ADMIN | 团队所有者 | 最高审批权限 |
| SALES_DIRECTOR | 销售总监 | 销售部门审批 |
| FINANCE | 财务人员 | 财务审批 |
| SALES_MEMBER | 销售成员 | 基础审批 |

**定义文件：** `CRM-Server/app/constants/approval_roles.py`

---

### 数据表结构

#### crm_approval_flows（审批流程模板表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| team_id | bigint | 团队ID（团队隔离） |
| flow_name | string | 流程名称 |
| flow_code | string | 流程编码（唯一） |
| description | text | 流程描述 |
| min_amount | decimal | 最小金额（条件） |
| max_amount | decimal | 最大金额（条件） |
| license_type | string | 授权类型（条件） |
| is_active | int | 是否启用（0/1） |

#### crm_approval_nodes（审批节点表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| flow_id | bigint | 关联流程ID |
| node_name | string | 节点名称 |
| node_code | string | 节点编码 |
| node_order | int | 节点顺序（决定流转顺序） |
| approve_role | string | 审批角色编码 |
| is_required | int | 是否必须审批（预留） |

#### crm_contract_approvals（审批实例表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| contract_id | bigint | 关联合同ID |
| flow_id | bigint | 关联流程模板ID |
| current_node_id | bigint | 当前审批节点ID |
| status | string | 审批状态 |
| submitter_id | string | 提交人飞书用户ID |

#### crm_contract_approval_records（审批记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| approval_id | bigint | 关联审批实例ID |
| node_id | bigint | 关联审批节点ID |
| approver_id | string | 审批人飞书用户ID |
| action | string | 审批动作 |
| comment | text | 审批意见 |

---

## 权限模型

### 权限码定义

| 权限码 | 说明 | 所属角色 |
|--------|------|---------|
| approval:flow:create | 创建审批流程 | TEAM_ADMIN |
| approval:flow:update | 更新审批流程 | TEAM_ADMIN |
| contract:approve:own | 审批自己创建的合同 | SALES_DIRECTOR |
| contract:approve:all | 审批所有合同 | TEAM_ADMIN |

**定义文件：** `CRM-Docs/system/GLOSSARY.md`

---

### 审批权限逻辑

```
┌─────────────────────────────────────────┐
│         审批权限检查流程                  │
└─────────────────────────────────────────┘

用户请求审批操作
    │
    ├─→ 检查用户是否拥有当前节点的审批角色
    │       │
    │       ├─ 有 → 继续
    │       └─ 无 → 403 拒绝访问
    │
    ├─→ 检查是否审批自己创建的合同
    │       │
    │       ├─ 是 → 检查 contract:approve:own 权限
    │       │         ├─ 有 → 允许
    │       │         └─ 无 → 403 拒绝访问
    │       │
    │       └─ 否 → 允许
    │
    └─→ 执行审批操作
```

---

## 设计决策（Explanation）

### 1. 为什么审批流程与合同状态解耦？

**设计决策：**
审批流程使用独立的数据表（`crm_contract_approvals`），而不是直接修改合同状态字段。

**原因：**
1. **审计追溯：** 审批记录完整保留在独立表中，即使合同删除也能追溯审批历史
2. **多审批并行：** 未来可支持同一合同发起多个审批流程（如合同审批 + 发票审批）
3. **状态同步：** 审批状态与合同状态通过业务逻辑同步，而非数据库约束

**合同状态与审批状态映射：**

| 合同状态 | 审批状态 | 说明 |
|---------|---------|------|
| DRAFT | 无审批 | 草稿状态 |
| PENDING_REVIEW | PENDING | 提交审批后 |
| SIGNED | APPROVED | 审批通过后 |
| DRAFT | REJECTED | 审批拒绝后 |
| DRAFT | CANCELLED | 撤回审批后 |

---

### 2. 为什么使用基于角色的审批而非基于用户？

**设计决策：**
审批节点配置的是「审批角色」（如 SALES_DIRECTOR），而非具体用户。

**原因：**
1. **人员变动：** 审批人离职或调岗时，只需调整角色归属，无需修改审批流程配置
2. **多审批人：** 同一角色可能有多个用户，任一用户均可审批
3. **权限复用：** 角色权限体系与系统其他权限统一管理

**示例：**
```
审批节点：销售总监审批（approve_role: SALES_DIRECTOR）
审批人：用户 A（SALES_DIRECTOR 角色）、用户 B（SALES_DIRECTOR 角色）
结果：用户 A 或 用户 B 均可审批此节点
```

---

### 3. 为什么审批流程需要条件匹配？

**设计决策：**
审批流程模板支持配置金额范围（min_amount, max_amount）和授权类型（license_type）条件。

**原因：**
1. **风险控制：** 大额合同需要更高层级审批
2. **业务分类：** 不同授权类型（订阅/买断）可能需要不同审批流程
3. **自动化：** 系统自动匹配审批流程，减少人工配置错误

**匹配逻辑：**
```
系统按以下顺序匹配审批流程：
1. 金额范围：min_amount ≤ 合同金额 ≤ max_amount
2. 授权类型：license_type == 合同授权类型
3. 启用状态：is_active == 1
4. 团队隔离：team_id == 当前团队

匹配失败 → 返回错误：未找到匹配的审批流程
```

---

### 4. 为什么设计多级审批而非并行审批？

**当前设计：**
审批节点按顺序（node_order）流转，必须逐级审批。

**原因：**
1. **业务流程：** 合同审批通常需要逐级审核（销售 → 财务 → 总经理）
2. **简化实现：** 顺序审批易于理解和追溯
3. **预留扩展：** `is_required` 字段预留，未来可支持「跳过可选节点」

**未来扩展方向：**
- 并行审批：某些节点需要多人同时审批（如财务 + 法务）
- 条件分支：根据合同属性选择不同审批路径
- 审批代理：审批人设置代理审批人

---

### 5. 为什么集成飞书通知而非站内通知？

**设计决策：**
审批通知使用飞书即时通知，而非系统站内消息。

**原因：**
1. **即时性：** 飞书通知能快速触达审批人，提高审批效率
2. **移动办公：** 飞书移动端推送，审批人随时随地处理
3. **集成生态：** CRMWolf 已集成飞书用户体系，通知渠道统一

**通知节点：**
- 提交审批 → 通知第一级审批人
- 审批通过（有下一节点）→ 通知下一级审批人
- 审批通过（全部节点）→ 通知提交人
- 审批拒绝 → 通知提交人（含拒绝原因）

---

## 常见问题

### Q1: 审批流程匹配失败怎么办？

**原因：**
- 未配置匹配条件的审批流程
- 合同金额超出所有流程的金额范围

**解决方案：**
1. 检查审批流程配置（金额范围、授权类型）
2. 创建一个「默认审批流程」（无条件限制）作为兜底

---

### Q2: 审批人离职了怎么办？

**解决方案：**
1. 在角色管理中移除离职用户的角色
2. 将角色分配给新的审批人
3. 审批流程配置无需修改（因为配置的是角色而非用户）

---

### Q3: 如何修改已审批通过的合同？

**当前限制：**
审批通过后合同状态为「已签署」，无法直接修改。

**解决方案：**
1. 创建新合同（复制原合同内容）
2. 或联系系统管理员特殊处理

---

### Q4: 如何查看审批历史？

**方法：**
1. 进入合同详情页面
2. 查看「审批详情」区域
3. 审批记录按时间顺序展示所有审批操作

**API 查询：**
```
GET /v1/approvals/contracts/{contract_id}/detail
```

---

### Q5: AI 辅助创建审批流程什么时候可用？

**当前状态：**
- API 已实现（`POST /v1/approval-ai/parse`, `/v1/approval-ai/create`）
- 前端界面待接入（未来版本）

---

## 相关文档

- [权限码定义](../system/GLOSSARY.md#权限码)
- [合同状态流转](../system/BUSINESS-CHAIN-API.md#合同)
- [飞书集成说明](../integrations/feishu.md)

---

**文档维护：** 请随功能更新同步维护此文档。如有疑问请联系系统管理员。
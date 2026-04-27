# 飞书轻量化CRM - 审批流程管理PRD（前端开发版）

## 文档信息

| 项目 | 内容 |
|------|------|
| **文档名称** | 飞书轻量化CRM审批流程管理PRD |
| **版本** | v1.0 |
| **创建日期** | 2026-02-10 |
| **目标读者** | 前端开发人员 |
| **文档目的** | 提供审批流程的前端开发指南，包括接口说明、状态流转、交互流程 |

---

## 目录

1. [审批流程概述](#1-审批流程概述)
2. [合同审批流程](#2-合同审批流程)
3. [发票审批流程](#3-发票审批流程)
4. [回款审批流程](#4-回款审批流程)
5. [前端开发指南](#5-前端开发指南)
6. [API接口清单](#6-api接口清单)
7. [状态码说明](#7-状态码说明)
8. [常见问题](#8-常见问题)

---

## 1. 审批流程概述

### 1.1 审批类型

系统目前支持三种审批流程：

| 审批类型 | 审批方式 | 审批角色 | 涉及模块 |
|---------|---------|---------|---------|
| **合同审批** | 工作流审批（多节点） | 销售总监、系统管理员 | 合同管理 |
| **发票审批** | 单级审批 | 财务人员、系统管理员 | 发票管理 |
| **回款审批** | 财务确认审批 | 财务人员、系统管理员 | 回款管理 |

### 1.2 审批流程特点

#### 合同审批（工作流审批）
- ✅ 支持多节点审批流程
- ✅ 支持条件匹配（金额、授权类型）
- ✅ 支持回退和撤回
- ✅ 完整的审批记录追踪
- ✅ 飞书消息通知

#### 发票审批（单级审批）
- ✅ 简单的审批流程
- ✅ 财务人员直接审批
- ✅ 支持关联合同和回款计划
- ✅ 支持关联回款记录

#### 回款审批（财务确认）
- ✅ 销售登记回款
- ✅ 财务确认入账
- ✅ 支持关联发票
- ✅ 支持争议处理

### 1.3 审批权限要求

| 操作 | 合同审批 | 发票审批 | 回款审批 |
|------|---------|---------|---------|
| **提交申请** | 合同创建者 | 销售成员 | 销售成员 |
| **审批通过** | 销售总监/系统管理员 | 财务人员 | 财务人员 |
| **审批拒绝** | 销售总监/系统管理员 | 财务人员 | 财务人员 |
| **撤回申请** | 提交人 | - | - |
| **查看记录** | 相关人员 | 相关人员 | 相关人员 |

---

## 2. 合同审批流程

### 2.1 流程概述

合同审批采用**工作流审批模式**，支持多节点、多角色的复杂审批流程。

#### 核心概念

```
合同（草稿）→ 提交审批 → 匹配流程 → 逐级审批 → 审批通过 → 合同生效
                ↓
              可撤回
                ↓
            审批拒绝 → 可重新提交
```

### 2.2 数据模型

#### 审批流程模板（ApprovalFlow）

```typescript
interface ApprovalFlow {
  id: number;                      // 流程ID
  flow_name: string;               // 流程名称
  flow_code: string;               // 流程编码
  description?: string;            // 流程描述
  min_amount?: number;             // 最小金额（条件）
  max_amount?: number;             // 最大金额（条件）
  license_type?: string;           // 授权类型（条件）
  is_active: number;               // 是否启用
  nodes: ApprovalNode[];           // 审批节点列表
  created_time: string;            // 创建时间
}
```

#### 审批节点（ApprovalNode）

```typescript
interface ApprovalNode {
  id: number;                      // 节点ID
  flow_id: number;                 // 流程ID
  node_name: string;               // 节点名称
  node_code: string;               // 节点编码
  node_order: number;              // 节点顺序
  description?: string;            // 节点描述
  approve_role: string;            // 审批角色
  is_required: number;             // 是否必须审批
  created_time: string;            // 创建时间
}
```

#### 审批实例（Approval）

```typescript
interface Approval {
  id: number;                      // 审批实例ID
  contract_id: number;             // 合同ID
  flow_id: number;                 // 流程模板ID
  flow_name?: string;              // 流程名称
  current_node_id?: number;        // 当前节点ID
  current_node_name?: string;      // 当前节点名称
  status: ApprovalStatus;          // 审批状态
  submitter_id: string;            // 提交人ID
  submitter_name?: string;         // 提交人姓名
  created_time: string;            // 创建时间
  updated_time: string;            // 更新时间
  flow?: ApprovalFlow;             // 流程详情
  records: ApprovalRecord[];       // 审批记录
}
```

#### 审批记录（ApprovalRecord）

```typescript
interface ApprovalRecord {
  id: number;                      // 记录ID
  approval_id: number;             // 审批实例ID
  node_id?: number;                // 节点ID
  node_name?: string;              // 节点名称
  approver_id: string;             // 审批人ID
  approver_name?: string;          // 审批人姓名
  action: ApprovalAction;          // 操作类型
  comment?: string;                // 审批意见
  created_time: string;            // 操作时间
}
```

### 2.3 审批状态

| 状态 | 代码 | 描述 | 可执行操作 |
|------|------|------|-----------|
| **审批中** | `PENDING` | 审批流程进行中 | 审批、撤回 |
| **已通过** | `APPROVED` | 审批通过 | - |
| **已拒绝** | `REJECTED` | 审批拒绝 | 重新提交 |
| **已撤回** | `CANCELLED` | 申请人撤回 | 重新提交 |

### 2.4 审批操作

| 操作 | 代码 | 描述 | 执行角色 |
|------|------|------|---------|
| **提交** | `SUBMIT` | 提交审批 | 合同创建者 |
| **同意** | `APPROVE` | 审批通过 | 当前节点审批人 |
| **拒绝** | `REJECT` | 审批拒绝 | 当前节点审批人 |
| **回退** | `ROLLBACK` | 回退到上一节点 | 系统管理员 |

### 2.5 审批流程图

```
┌─────────────┐
│ 合同草稿状态 │
└──────┬──────┘
       │ 提交审批
       ▼
┌─────────────┐
│  匹配流程    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│     节点1（如：销售总监审批）    │
│  ┌─────────────────────────┐  │
│  │  审批人：销售总监         │  │
│  │  操作：同意 / 拒绝        │  │
│  └─────────────────────────┘  │
└──────────┬──────────────────┘
           │ 同意
           ▼
┌─────────────────────────────┐
│     节点2（如：财务审批）       │
│  ┌─────────────────────────┐  │
│  │  审批人：财务人员         │  │
│  │  操作：同意 / 拒绝        │  │
│  └─────────────────────────┘  │
└──────────┬──────────────────┘
           │ 同意
           ▼
     ┌──────────┐
     │ 审批通过   │
     │合同生效    │
     └──────────┘
```

### 2.6 流程匹配规则

系统根据合同信息自动匹配审批流程：

```typescript
// 流程匹配逻辑
interface FlowMatchRule {
  contract_amount: number;      // 合同金额
  min_amount?: number;          // 流程最小金额
  max_amount?: number;          // 流程最大金额
  license_type?: string;        // 授权类型
  is_active: boolean;           // 是否启用
}
```

**匹配规则**：
1. 按金额范围匹配（`min_amount <= 合同金额 <= max_amount`）
2. 按授权类型匹配（如适用）
3. 选择启用的流程（`is_active = 1`）
4. 如果没有匹配的流程，返回错误

### 2.7 特殊权限规则

#### 审批自己创建的合同

| 角色 | 权限 | 说明 |
|------|------|------|
| **销售成员** | ❌ | 不能审批自己创建的合同 |
| **销售总监** | ✅ | 可以审批自己创建的合同 |
| **系统管理员** | ✅ | 可以审批所有合同 |

**实现逻辑**：
```typescript
// 检查是否可以审批自己创建的合同
function canApproveOwnContract(userRole: string, hasPermission: boolean): boolean {
  // 销售总监需要特殊权限：contract:approve_own
  if (userRole === 'SALES_DIRECTOR') {
    return hasPermission; // 检查是否有 contract:approve_own 权限
  }
  
  // 系统管理员始终可以审批
  if (userRole === 'SYSTEM_ADMIN') {
    return true;
  }
  
  return false;
}
```

### 2.8 前端交互流程

#### 提交合同审批

```typescript
// 1. 检查合同状态
if (contract.status !== 'DRAFT') {
  showToast('只有草稿状态的合同可以提交审批');
  return;
}

// 2. 检查是否已有审批流程
const existingApproval = await checkApprovalExists(contractId);
if (existingApproval) {
  showToast('该合同已有审批流程');
  return;
}

// 3. 提交审批
try {
  const result = await submitContractApproval(contractId, {
    comment: '请审批' // 可选的提交说明
  });
  
  showToast('提交成功');
  // 刷新合同详情
  refreshContractDetail();
} catch (error) {
  showToast(error.message);
}
```

#### 审批操作

```typescript
// 1. 获取待审批列表
const pendingApprovals = await getPendingApprovals();

// 2. 审批操作
async function handleApproval(approvalId: number, action: 'APPROVE' | 'REJECT') {
  try {
    const result = await approvalAction(approvalId, {
      action: action,
      comment: '同意' // 或 '拒绝原因...'
    });
    
    showToast(action === 'APPROVE' ? '审批通过' : '已拒绝');
    // 刷新审批列表
    refreshApprovalList();
  } catch (error) {
    showToast(error.message);
  }
}
```

#### 撤回审批

```typescript
// 只有提交人可以撤回，且只能撤回审批中的申请
async function cancelApproval(approvalId: number) {
  try {
    await cancelContractApproval(approvalId);
    showToast('已撤回审批');
    // 刷新合同详情
    refreshContractDetail();
  } catch (error) {
    showToast(error.message);
  }
}
```

---

## 3. 发票审批流程

### 3.1 流程概述

发票审批采用**单级审批模式**，由财务人员直接审批。

```
发票申请（草稿）→ 提交审批 → 财务审批 → 审批通过 → 标记已开票
                        ↓
                     审批拒绝 → 可重新提交
```

### 3.2 数据模型

#### 发票申请（InvoiceApplication）

```typescript
interface InvoiceApplication {
  id: number;                      // 申请ID
  application_number: string;      // 申请单号
  customer_id: number;             // 客户ID
  contract_id: number;             // 合同ID
  opportunity_id: number;          // 商机ID
  payment_plan_id: number;         // 回款计划ID
  payment_record_id?: number;      // 回款记录ID
  invoice_title_id: number;        // 开票抬头ID
  invoice_amount: number;          // 开票金额
  invoice_type: string;            // 发票类型
  status: InvoiceStatus;           // 申请状态
  applicant_id: string;            // 申请人ID
  reviewer_id?: string;            // 审批人ID
  review_comment?: string;         // 审批意见
  reviewed_time?: string;          // 审批时间
  created_time: string;            // 创建时间
}
```

### 3.3 发票状态

| 状态 | 代码 | 描述 | 可执行操作 |
|------|------|------|-----------|
| **草稿** | `DRAFT` | 草稿状态 | 编辑、提交审批 |
| **待审核** | `PENDING_REVIEW` | 等待财务审批 | 审批 |
| **已通过** | `APPROVED` | 审批通过 | 标记已开票 |
| **已拒绝** | `REJECTED` | 审批拒绝 | 重新提交 |
| **已开票** | `ISSUED` | 已开票 | - |

### 3.4 发票类型

| 类型 | 代码 | 描述 |
|------|------|------|
| **增值税专用发票** | `VAT_SPECIAL` | 需要纳税人识别号 |
| **普通发票** | `VAT_NORMAL` | 普通发票 |

### 3.5 前端交互流程

#### 提交发票申请

```typescript
// 1. 创建发票申请（草稿状态）
const invoiceApplication = await createInvoiceApplication({
  customer_id: customerId,
  contract_id: contractId,
  opportunity_id: opportunityId,
  payment_plan_id: paymentPlanId,
  invoice_title_id: invoiceTitleId,
  invoice_amount: 10000,
  invoice_type: 'VAT_SPECIAL'
});

// 2. 提交审批
try {
  const result = await submitInvoiceApplication(invoiceApplication.id, {
    comment: '请审批'
  });
  
  showToast('提交成功');
} catch (error) {
  showToast(error.message);
}
```

#### 财务审批

```typescript
// 1. 获取待审批发票列表
const pendingInvoices = await getPendingInvoices();

// 2. 审批操作
async function reviewInvoice(invoiceId: number, action: 'approve' | 'reject') {
  try {
    const result = await reviewInvoiceApplication(invoiceId, {
      action: action,
      review_comment: action === 'approve' ? '同意' : '拒绝原因...'
    });
    
    showToast(action === 'approve' ? '审批通过' : '已拒绝');
  } catch (error) {
    showToast(error.message);
  }
}
```

#### 标记已开票

```typescript
// 只有已通过的发票申请可以标记为已开票
async function markAsIssued(invoiceId: number) {
  try {
    await markInvoiceAsIssued(invoiceId);
    showToast('已标记为开票');
  } catch (error) {
    showToast(error.message);
  }
}
```

---

## 4. 回款审批流程

### 4.1 流程概述

回款审批采用**财务确认模式**，由销售登记回款，财务确认入账。

```
销售登记回款 → 财务确认入账 → 回款完成
                    ↓
                 有争议 → 退回销售处理
```

### 4.2 数据模型

#### 回款记录（PaymentRecord）

```typescript
interface PaymentRecord {
  id: number;                      // 记录ID
  payment_plan_id: number;         // 回款计划ID
  expected_amount: number;         // 应收金额
  actual_amount: number;           // 实际回款金额
  payment_date: string;            // 回款日期
  payment_method: string;          // 回款方式
  status: string;                  // 回款状态
  confirmation_status?: string;    // 确认状态
  registrant_id: string;           // 登记人ID
  registrant_name?: string;        // 登记人姓名
  confirmer_id?: string;           // 确认人ID
  confirmer_name?: string;         // 确认人姓名
  confirmation_time?: string;      // 确认时间
  confirmation_notes?: string;     // 确认备注
  invoice_application_ids?: number[]; // 关联发票ID列表
  created_time: string;            // 创建时间
}
```

### 4.3 回款状态

| 状态 | 代码 | 描述 | 可执行操作 |
|------|------|------|-----------|
| **待确认** | `PENDING` | 等待财务确认 | 确认、争议 |
| **已确认** | `CONFIRMED` | 财务已确认 | - |
| **有争议** | `DISPUTED` | 存在争议 | 重新登记 |

### 4.4 前端交互流程

#### 销售登记回款

```typescript
// 1. 登记回款
const paymentRecord = await registerPayment({
  payment_plan_id: paymentPlanId,
  actual_amount: 10000,
  payment_date: '2026-02-10',
  payment_method: 'BANK_TRANSFER',
  payment_voucher_url: 'https://...'
});

showToast('登记成功，等待财务确认');
```

#### 财务确认回款

```typescript
// 1. 获取待确认回款列表
const pendingPayments = await getPendingConfirmations();

// 2. 确认回款
async function confirmPayment(recordId: number) {
  try {
    const result = await confirmPaymentRecord(recordId, {
      action: 'confirm',
      notes: '已核对，确认入账',
      invoice_application_ids: [1, 2] // 可选：关联发票
    });
    
    showToast('确认成功');
  } catch (error) {
    showToast(error.message);
  }
}

// 3. 标记争议
async function disputePayment(recordId: number) {
  try {
    const result = await confirmPaymentRecord(recordId, {
      action: 'dispute',
      notes: '金额不符，请核对'
    });
    
    showToast('已标记为争议');
  } catch (error) {
    showToast(error.message);
  }
}
```

---

## 5. 前端开发指南

### 5.1 权限控制

#### 检查审批权限

```typescript
// 获取当前用户权限
const { permissions } = await getUserPermissions();

// 检查是否有审批权限
function hasApprovalPermission(): boolean {
  return permissions.some(p => 
    p.code === 'contract:approve_own' || 
    p.code === 'contract:approve_all'
  );
}
```

#### 显示/隐藏操作按钮

```typescript
// 根据权限和状态控制按钮显示
function renderApprovalButtons(approval: Approval) {
  const buttons = [];
  
  // 提交审批按钮（仅草稿状态，且是创建者）
  if (contract.status === 'DRAFT' && isCreator) {
    buttons.push(
      <Button onClick={handleSubmitApproval}>提交审批</Button>
    );
  }
  
  // 审批操作按钮（待审批状态，且有审批权限）
  if (approval.status === 'PENDING' && canApprove) {
    buttons.push(
      <Button onClick={() => handleApprove('APPROVE')}>同意</Button>,
      <Button onClick={() => handleApprove('REJECT')}>拒绝</Button>
    );
  }
  
  // 撤回按钮（待审批状态，且是提交人）
  if (approval.status === 'PENDING' && isSubmitter) {
    buttons.push(
      <Button onClick={handleCancel}>撤回</Button>
    );
  }
  
  return buttons;
}
```

### 5.2 状态展示

#### 审批状态标签

```typescript
// 审批状态标签组件
function ApprovalStatusTag({ status }: { status: ApprovalStatus }) {
  const statusMap = {
    'PENDING': { color: 'blue', text: '审批中' },
    'APPROVED': { color: 'green', text: '已通过' },
    'REJECTED': { color: 'red', text: '已拒绝' },
    'CANCELLED': { color: 'gray', text: '已撤回' }
  };
  
  const { color, text } = statusMap[status] || { color: 'gray', text: status };
  
  return <Tag color={color}>{text}</Tag>;
}
```

#### 审批进度条

```typescript
// 审批进度展示
function ApprovalProgress({ approval }: { approval: Approval }) {
  if (!approval.flow) return null;
  
  const nodes = approval.flow.nodes;
  const currentIndex = nodes.findIndex(n => n.id === approval.current_node_id);
  
  return (
    <Steps current={currentIndex}>
      {nodes.map((node, index) => (
        <Step 
          key={node.id}
          title={node.node_name}
          description={node.approve_role}
          status={getStepStatus(index, currentIndex, approval.status)}
        />
      ))}
    </Steps>
  );
}
```

### 5.3 列表页面

#### 待审批列表

```typescript
// 获取待审批列表
async function fetchPendingApprovals() {
  try {
    const response = await axios.get('/api/v1/approvals/pending');
    setPendingApprovals(response.data);
  } catch (error) {
    console.error('获取待审批列表失败', error);
  }
}

// 列表渲染
function PendingApprovalList() {
  return (
    <Table 
      dataSource={pendingApprovals}
      columns={[
        { title: '合同名称', dataIndex: 'contract_name' },
        { title: '当前节点', dataIndex: 'current_node_name' },
        { title: '提交人', dataIndex: 'submitter_name' },
        { title: '提交时间', dataIndex: 'created_time' },
        { 
          title: '操作',
          render: (_, record) => (
            <Space>
              <Button onClick={() => handleApprove(record.id)}>同意</Button>
              <Button onClick={() => handleReject(record.id)}>拒绝</Button>
            </Space>
          )
        }
      ]}
    />
  );
}
```

### 5.4 详情页面

#### 审批详情页面

```typescript
// 审批详情
function ApprovalDetail({ approvalId }: { approvalId: number }) {
  const [approval, setApproval] = useState<ApprovalDetailResponse | null>(null);
  
  useEffect(() => {
    fetchApprovalDetail(approvalId).then(setApproval);
  }, [approvalId]);
  
  if (!approval) return <Loading />;
  
  return (
    <div>
      {/* 基本信息 */}
      <Card title="审批信息">
        <Descriptions>
          <Descriptions.Item label="合同名称">{approval.contract_name}</Descriptions.Item>
          <Descriptions.Item label="审批状态">
            <ApprovalStatusTag status={approval.status} />
          </Descriptions.Item>
          <Descriptions.Item label="当前节点">{approval.current_node_name}</Descriptions.Item>
          <Descriptions.Item label="提交人">{approval.submitter_name}</Descriptions.Item>
          <Descriptions.Item label="提交时间">{approval.created_time}</Descriptions.Item>
        </Descriptions>
      </Card>
      
      {/* 审批流程 */}
      {approval.flow && (
        <Card title="审批流程">
          <ApprovalProgress approval={approval} />
        </Card>
      )}
      
      {/* 审批记录 */}
      <Card title="审批记录">
        <Timeline>
          {approval.records.map(record => (
            <Timeline.Item key={record.id}>
              <p><strong>{record.approver_name}</strong> - {record.action}</p>
              <p>{record.comment}</p>
              <p>{record.created_time}</p>
            </Timeline.Item>
          ))}
        </Timeline>
      </Card>
      
      {/* 操作按钮 */}
      {renderActionButtons(approval)}
    </div>
  );
}
```

### 5.5 表单处理

#### 提交审批表单

```typescript
// 提交审批表单
function SubmitApprovalForm({ contractId }: { contractId: number }) {
  const [form] = Form.useForm();
  
  const handleSubmit = async (values: any) => {
    try {
      await submitContractApproval(contractId, {
        comment: values.comment
      });
      
      message.success('提交成功');
      // 跳转到审批详情页
      history.push(`/approvals/${contractId}`);
    } catch (error) {
      message.error(error.message);
    }
  };
  
  return (
    <Form form={form} onFinish={handleSubmit}>
      <Form.Item 
        label="提交说明" 
        name="comment"
        rules={[{ required: true, message: '请输入提交说明' }]}
      >
        <TextArea rows={4} placeholder="请输入提交说明" />
      </Form.Item>
      
      <Form.Item>
        <Button type="primary" htmlType="submit">提交审批</Button>
      </Form.Item>
    </Form>
  );
}
```

---

## 6. API接口清单

### 6.1 合同审批接口

#### 获取审批流程列表

```
GET /api/v1/approvals/flows
```

**响应示例**：
```json
{
  "id": 1,
  "flow_name": "标准合同审批流程",
  "flow_code": "STANDARD_CONTRACT",
  "description": "金额在10万-50万之间的合同审批流程",
  "min_amount": 100000,
  "max_amount": 500000,
  "is_active": 1,
  "created_time": "2026-02-10T10:00:00"
}
```

#### 获取审批流程详情

```
GET /api/v1/approvals/flows/{flow_id}
```

**响应示例**：
```json
{
  "id": 1,
  "flow_name": "标准合同审批流程",
  "flow_code": "STANDARD_CONTRACT",
  "nodes": [
    {
      "id": 1,
      "node_name": "销售总监审批",
      "node_code": "SALES_DIRECTOR_APPROVAL",
      "node_order": 1,
      "approve_role": "SALES_DIRECTOR",
      "is_required": 1
    },
    {
      "id": 2,
      "node_name": "财务审批",
      "node_code": "FINANCE_APPROVAL",
      "node_order": 2,
      "approve_role": "finance",
      "is_required": 1
    }
  ]
}
```

#### 提交合同审批

```
POST /api/v1/approvals/contracts/{contract_id}/submit
```

**请求体**：
```json
{
  "comment": "请审批"
}
```

**响应示例**：
```json
{
  "id": 1,
  "contract_id": 10,
  "flow_id": 1,
  "flow_name": "标准合同审批流程",
  "current_node_id": 1,
  "current_node_name": "销售总监审批",
  "status": "PENDING",
  "submitter_id": "ou_xxx",
  "submitter_name": "张三",
  "created_time": "2026-02-10T10:00:00"
}
```

#### 审批操作

```
POST /api/v1/approvals/contracts/{contract_id}/approve
```

**请求体**：
```json
{
  "action": "APPROVE",
  "comment": "同意"
}
```

**响应示例**：
```json
{
  "message": "审批成功"
}
```

#### 撤回审批

```
POST /api/v1/approvals/contracts/{contract_id}/cancel
```

**响应示例**：
```json
{
  "message": "已撤回审批"
}
```

#### 获取合同审批详情

```
GET /api/v1/approvals/contracts/{contract_id}/detail
```

**响应示例**：
```json
{
  "id": 1,
  "contract_id": 10,
  "status": "PENDING",
  "flow": {
    "id": 1,
    "flow_name": "标准合同审批流程",
    "nodes": [...]
  },
  "records": [
    {
      "id": 1,
      "node_name": "销售总监审批",
      "approver_name": "李四",
      "action": "APPROVE",
      "comment": "同意",
      "created_time": "2026-02-10T11:00:00"
    }
  ]
}
```

### 6.2 发票审批接口

#### 提交发票申请审批

```
POST /api/v1/invoice-applications/{application_id}/submit
```

#### 审批发票申请

```
POST /api/v1/invoice-applications/{application_id}/review
```

**请求体**：
```json
{
  "action": "approve",
  "review_comment": "同意"
}
```

#### 标记发票已开票

```
PATCH /api/v1/invoice-applications/{application_id}/mark-issued
```

### 6.3 回款审批接口

#### 登记回款

```
POST /api/v1/payments/payment-records
```

**请求体**：
```json
{
  "payment_plan_id": 1,
  "actual_amount": 10000,
  "payment_date": "2026-02-10",
  "payment_method": "BANK_TRANSFER",
  "payment_voucher_url": "https://..."
}
```

#### 确认回款入账

```
POST /api/v1/finance/payment-records/{record_id}/confirm
```

**请求体**：
```json
{
  "action": "confirm",
  "notes": "已核对，确认入账",
  "invoice_application_ids": [1, 2]
}
```

---

## 7. 状态码说明

### 7.1 审批状态

| 状态 | 代码 | 颜色建议 |
|------|------|---------|
| 审批中 | `PENDING` | 蓝色 |
| 已通过 | `APPROVED` | 绿色 |
| 已拒绝 | `REJECTED` | 红色 |
| 已撤回 | `CANCELLED` | 灰色 |

### 7.2 发票状态

| 状态 | 代码 | 颜色建议 |
|------|------|---------|
| 草稿 | `DRAFT` | 灰色 |
| 待审核 | `PENDING_REVIEW` | 橙色 |
| 已通过 | `APPROVED` | 绿色 |
| 已拒绝 | `REJECTED` | 红色 |
| 已开票 | `ISSUED` | 蓝色 |

### 7.3 回款确认状态

| 状态 | 代码 | 颜色建议 |
|------|------|---------|
| 待确认 | `PENDING` | 橙色 |
| 已确认 | `CONFIRMED` | 绿色 |
| 有争议 | `DISPUTED` | 红色 |

---

## 8. 常见问题

### Q1: 如何判断当前用户是否可以审批某个合同？

**A**: 检查以下条件：
1. 审批状态为 `PENDING`
2. 当前用户具有当前节点要求的角色
3. 如果是审批自己创建的合同，需要特殊权限

```typescript
function canApprove(approval: Approval, user: User): boolean {
  if (approval.status !== 'PENDING') return false;
  
  const userRoles = user.roles.map(r => r.code);
  if (!userRoles.includes(approval.current_node?.approve_role)) {
    return false;
  }
  
  // 检查是否是自己创建的合同
  if (approval.contract.creator_id === user.id) {
    return user.permissions.includes('contract:approve_own');
  }
  
  return true;
}
```

### Q2: 如何实现审批进度条？

**A**: 使用Ant Design的Steps组件，根据当前节点索引展示进度：

```typescript
<Steps current={currentNodeIndex}>
  {nodes.map((node, index) => (
    <Step 
      key={node.id}
      title={node.node_name}
      status={getStepStatus(index, currentNodeIndex, approval.status)}
    />
  ))}
</Steps>
```

### Q3: 发票申请被拒绝后如何处理？

**A**: 
1. 显示拒绝原因
2. 允许修改后重新提交
3. 重新提交时创建新的审批记录

### Q4: 回款确认时如何关联发票？

**A**: 
```typescript
// 确认回款时传入发票ID列表
await confirmPaymentRecord(recordId, {
  action: 'confirm',
  invoice_application_ids: [1, 2, 3] // 关联的发票ID
});
```

### Q5: 如何实现实时通知？

**A**: 
1. 使用WebSocket监听审批状态变更
2. 使用轮询定期刷新待审批列表
3. 使用飞书消息通知（后端已实现）

---

## 附录

### A. 完整的数据类型定义

```typescript
// 合同审批
interface Approval {
  id: number;
  contract_id: number;
  flow_id?: number;
  flow_name?: string;
  current_node_id?: number;
  current_node_name?: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
  submitter_id: string;
  submitter_name?: string;
  created_time: string;
  updated_time: string;
}

// 发票申请
interface InvoiceApplication {
  id: number;
  application_number: string;
  customer_id: number;
  contract_id: number;
  opportunity_id: number;
  payment_plan_id: number;
  payment_record_id?: number;
  invoice_title_id: number;
  invoice_amount: number;
  invoice_type: 'VAT_SPECIAL' | 'VAT_NORMAL';
  status: 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'ISSUED';
  applicant_id: string;
  reviewer_id?: string;
  review_comment?: string;
  reviewed_time?: string;
  created_time: string;
}

// 回款记录
interface PaymentRecord {
  id: number;
  payment_plan_id: number;
  expected_amount: number;
  actual_amount: number;
  payment_date: string;
  payment_method: string;
  status: string;
  confirmation_status?: 'PENDING' | 'CONFIRMED' | 'DISPUTED';
  registrant_id: string;
  registrant_name?: string;
  confirmer_id?: string;
  confirmer_name?: string;
  confirmation_time?: string;
  confirmation_notes?: string;
  invoice_application_ids?: number[];
  created_time: string;
}
```

### B. 相关文档链接

- [权限系统说明](/Users/eddie/Code/CRM/docs/technical/permission-system.md)
- [合同管理API](/Users/eddie/Code/CRM/docs/api/contract-api.md)
- [发票管理API](/Users/eddie/Code/CRM/docs/api/invoice-api.md)
- [回款管理API](/Users/eddie/Code/CRM/docs/api/payment-api.md)

---

## 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|---------|
| 2026-02-10 | v1.0 | 初始版本，包含合同、发票、回款三种审批流程 |

---

**文档结束**

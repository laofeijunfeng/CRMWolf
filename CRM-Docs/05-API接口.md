# API 接口文档

## 1. 接口规范

### 1.1 基础信息

| 项目 | 说明 |
|------|------|
| 基础路径 | `/api/v1` |
| 协议 | HTTP/HTTPS |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |

### 1.2 认证方式

使用 JWT Bearer Token 认证：

```
Authorization: Bearer <token>
```

### 1.3 通用响应格式

**成功响应：**
```json
{
  "id": 1,
  "name": "数据名称",
  "created_time": "2024-01-01T00:00:00"
}
```

**错误响应：**
```json
{
  "detail": "错误信息描述"
}
```

**列表响应：**
```json
{
  "items": [...],
  "total": 100
}
```

### 1.4 分页参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| skip | int | 0 | 跳过记录数 |
| limit | int | 100 | 每页记录数 |

---

## 2. 认证接口

### 2.1 飞书登录

**GET** `/auth/feishu/login`

**说明：** 重定向到飞书 OAuth 授权页面

### 2.2 飞书回调

**GET** `/auth/feishu/callback`

**参数：**
- `code` - 飞书授权码

**响应：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 2.3 获取当前用户

**GET** `/auth/me`

**响应：**
```json
{
  "id": 1,
  "name": "用户名",
  "email": "user@example.com",
  "feishu_open_id": "ou_xxx",
  "roles": [
    {"id": 1, "name": "销售成员", "code": "SALES_MEMBER"}
  ]
}
```

---

## 3. 线索接口

### 3.1 获取线索列表

**GET** `/api/v1/leads/`

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| skip | int | 跳过记录数 |
| limit | int | 每页记录数 |
| status | int | 线索状态 |
| owner_id | string | 负责人ID |
| me | bool | 仅查询当前用户负责的线索 |

**响应：**
```json
{
  "leads": [
    {
      "id": 1,
      "lead_name": "线索名称",
      "source": "线上注册",
      "city": "北京",
      "contact_name": "联系人",
      "contact_phone": "13800138000",
      "owner_id": "ou_xxx",
      "owner_name": "负责人姓名",
      "status": 0,
      "created_time": "2024-01-01T00:00:00"
    }
  ],
  "total": 100
}
```

### 3.2 创建线索

**POST** `/api/v1/leads/`

**请求体：**
```json
{
  "lead_name": "线索名称",
  "source": "线上注册",
  "city": "北京",
  "contact_name": "联系人",
  "contact_phone": "13800138000",
  "company_scale": "51-200人"
}
```

### 3.3 获取线索详情

**GET** `/api/v1/leads/{lead_id}`

### 3.4 更新线索

**PUT** `/api/v1/leads/{lead_id}`

### 3.5 转化线索

**POST** `/api/v1/leads/{lead_id}/convert`

**请求体：**
```json
{
  "account_name": "客户公司名称",
  "industry": "互联网",
  "city": "北京",
  "opportunity_name": "商机名称",
  "user_count": 100,
  "total_amount": 50000,
  "expected_closing_date": "2024-06-30"
}
```

### 3.6 添加跟进记录

**POST** `/api/v1/leads/{lead_id}/follow-ups`

**请求体：**
```json
{
  "content": "跟进内容",
  "method": "电话",
  "next_follow_time": "2024-01-15T10:00:00"
}
```

---

## 4. 客户接口

### 4.1 获取客户列表

**GET** `/api/v1/customers/`

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| skip | int | 跳过记录数 |
| limit | int | 每页记录数 |
| status | int | 客户状态 |
| owner_id | string | 负责人ID |
| me | bool | 仅查询当前用户负责的客户 |

### 4.2 创建客户

**POST** `/api/v1/customers/`

**请求体：**
```json
{
  "account_name": "客户公司名称",
  "industry": "互联网",
  "city": "北京",
  "address": "详细地址",
  "company_scale": "51-200人",
  "source": "客户推荐"
}
```

### 4.3 获取客户详情

**GET** `/api/v1/customers/{customer_id}`

**响应：**
```json
{
  "id": 1,
  "account_name": "客户公司名称",
  "industry": "互联网",
  "city": "北京",
  "status": 0,
  "owner_id": "ou_xxx",
  "owner_name": "负责人姓名",
  "contacts": [...],
  "opportunities": [...],
  "contracts": [...],
  "created_time": "2024-01-01T00:00:00"
}
```

### 4.4 更新客户

**PUT** `/api/v1/customers/{customer_id}`

### 4.5 添加联系人

**POST** `/api/v1/customers/{customer_id}/contacts`

**请求体：**
```json
{
  "name": "联系人姓名",
  "position": "技术总监",
  "mobile": "13800138000",
  "email": "contact@example.com",
  "is_decision_maker": true,
  "is_primary": true
}
```

### 4.6 添加跟进记录

**POST** `/api/v1/customers/{customer_id}/follow-ups`

---

## 5. 商机接口

### 5.1 获取商机列表

**GET** `/api/v1/opportunities/`

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| customer_id | int | 客户ID |
| status | int | 商机状态 |
| owner_id | string | 负责人ID |
| me | bool | 仅查询当前用户负责的商机 |

### 5.2 创建商机

**POST** `/api/v1/opportunities/`

**请求体：**
```json
{
  "opportunity_name": "商机名称",
  "customer_id": 1,
  "user_count": 100,
  "total_amount": 50000,
  "license_type": "SUBSCRIPTION",
  "subscription_years": 1,
  "purchase_type": "NEW",
  "expected_closing_date": "2024-06-30"
}
```

### 5.3 获取商机详情

**GET** `/api/v1/opportunities/{opportunity_id}`

### 5.4 更新商机

**PUT** `/api/v1/opportunities/{opportunity_id}`

### 5.5 推进商机阶段

**POST** `/api/v1/opportunities/{opportunity_id}/advance`

**请求体：**
```json
{
  "stage_name": "商务谈判"
}
```

### 5.6 赢单

**POST** `/api/v1/opportunities/{opportunity_id}/win`

**请求体：**
```json
{
  "actual_amount": 48000,
  "actual_closing_date": "2024-05-15"
}
```

### 5.7 输单

**POST** `/api/v1/opportunities/{opportunity_id}/lose`

**请求体：**
```json
{
  "loss_reason": "选择了竞争对手"
}
```

---

## 6. 合同接口

### 6.1 获取合同列表

**GET** `/api/v1/contracts/`

### 6.2 创建合同

**POST** `/api/v1/contracts/`

**请求体：**
```json
{
  "contract_name": "合同名称",
  "customer_id": 1,
  "opportunity_id": 1,
  "signing_contact_id": 1,
  "user_count": 100,
  "total_amount": 50000,
  "license_type": "SUBSCRIPTION",
  "subscription_years": 1,
  "signing_date": "2024-05-01",
  "effective_date": "2024-05-01"
}
```

### 6.3 根据商机创建合同

**POST** `/api/v1/contracts/from-opportunity/{opportunity_id}`

### 6.4 获取合同详情

**GET** `/api/v1/contracts/{contract_id}`

### 6.5 提交审批

**POST** `/api/v1/contracts/{contract_id}/submit`

### 6.6 撤回审批

**POST** `/api/v1/contracts/{contract_id}/withdraw`

### 6.7 审批合同

**POST** `/api/v1/contracts/{contract_id}/review`

**请求体：**
```json
{
  "action": "approve",
  "comment": "审批意见"
}
```

**action 取值：** `approve`（通过）、`reject`（拒绝）

---

## 7. 回款接口

### 7.1 获取回款计划列表

**GET** `/api/v1/payment-plans/`

### 7.2 创建回款计划

**POST** `/api/v1/contracts/{contract_id}/payment-plans`

**请求体：**
```json
{
  "stage_name": "首付款",
  "planned_amount": 20000,
  "due_date": "2024-06-01"
}
```

### 7.3 登记回款

**POST** `/api/v1/payment-plans/{plan_id}/payment-records`

**请求体：**
```json
{
  "actual_amount": 20000,
  "payment_date": "2024-05-28",
  "proof_attachment": "https://xxx.com/proof.pdf",
  "notes": "备注"
}
```

### 7.4 确认回款

**POST** `/api/v1/payment-records/{record_id}/confirm`

**请求体：**
```json
{
  "confirmation_notes": "确认备注"
}
```

---

## 8. 发票接口

### 8.1 发票抬头管理

#### 获取发票抬头列表

**GET** `/api/v1/invoice-titles`

**参数：** `customer_id` - 客户ID

#### 创建发票抬头

**POST** `/api/v1/invoice-titles?customer_id={customer_id}`

**请求体：**
```json
{
  "title_type": "COMPANY",
  "title": "公司抬头",
  "taxpayer_id": "91110105MA0056PG04",
  "bank_name": "开户行",
  "bank_account": "账号",
  "address": "地址",
  "phone": "电话"
}
```

#### 设置默认抬头

**PATCH** `/api/v1/invoice-titles/{title_id}/set-default`

#### 删除发票抬头

**DELETE** `/api/v1/invoice-titles/{title_id}`

### 8.2 发票申请管理

#### 获取发票申请列表

**GET** `/api/v1/invoice-applications`

#### 创建发票申请

**POST** `/api/v1/invoice-applications`

**请求体：**
```json
{
  "customer_id": 1,
  "contract_id": 1,
  "payment_plan_id": 1,
  "invoice_title_id": 1,
  "invoice_type": "VAT_SPECIAL",
  "invoice_amount": 10000
}
```

#### 提交审批

**POST** `/api/v1/invoice-applications/{application_id}/submit`

#### 撤回申请

**POST** `/api/v1/invoice-applications/{application_id}/withdraw`

#### 审批发票

**POST** `/api/v1/invoice-applications/{application_id}/review`

**请求体：**
```json
{
  "action": "approve",
  "comment": "审批意见"
}
```

#### 标记已开票

**POST** `/api/v1/invoice-applications/{application_id}/mark-issued`

---

## 9. 用户与权限接口

### 9.1 用户管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/users/` | GET | 获取用户列表 |
| `/api/v1/users/{user_id}` | GET | 获取用户详情 |
| `/api/v1/users/{user_id}/roles` | PUT | 分配用户角色 |

### 9.2 角色管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/roles/` | GET | 获取角色列表 |
| `/api/v1/roles/{role_id}` | GET | 获取角色详情 |
| `/api/v1/roles/{role_id}/permissions` | PUT | 配置角色权限 |

### 9.3 权限管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/permissions/` | GET | 获取权限列表 |
| `/api/v1/permissions/me` | GET | 获取当前用户权限 |

---

## 10. 错误码

| HTTP 状态码 | 说明 |
|-------------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 参数验证失败 |
| 500 | 服务器内部错误 |
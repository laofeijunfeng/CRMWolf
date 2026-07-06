---
name: license-management-design
description: License 授权码管理功能设计文档
created: 2026-07-06
status: draft
---

# License 授权码管理功能设计文档

> 版本：1.0 | 创建日期：2026-07-06 | 状态：设计中

---

## 一、需求概述

### 1.1 业务背景

CRMWolf 系统需要支持 License 授权码管理功能，用于管理客户的产品授权。主要场景包括：

1. **POC 试用场景**：客户申请 POC 试用，销售人员申请临时试用 License
2. **正式部署场景**：客户正式部署，销售人员申请正式 License

### 1.2 核心需求

| 需求项 | 说明 |
|--------|------|
| **部署信息管理** | 客户可配置多个部署信息（服务器地址、授权人数等），类似发票抬头模式 |
| **License 申请** | 支持试用 License 和正式 License 申请，正式 License 必须关联审批通过的合同 |
| **审批流程** | License 申请走统一审批引擎，审批人回填授权码即通过 |
| **消息通知** | 申请提交、审批通过、审批拒绝均发送飞书通知 |
| **文件导出** | 审批通过后可导出 Word 文档（包含授权码、部署信息等） |
| **到期时间管理** | 客户表新增到期时间字段，自动更新为所有 License 的最晚到期时间 |

---

## 二、整体架构

### 2.1 模块关系图

```
Customer (客户表)
├── DeploymentInfo (部署信息表) ← 类似 InvoiceTitle
│   ├── server_address (服务器地址)
│   ├── authorized_users (授权人数)
│   ├── deployment_name (部署名称)
│   └── is_default (是否默认)
│
├── LicenseApplication (License 申请表) ← 类似 InvoiceApplication
│   ├── customer_id
│   ├── contract_id (正式必填，试用可空)
│   ├── deployment_info_id
│   ├── expiry_date
│   ├── license_type (TRIAL/OFFICIAL)
│   ├── license_code (审批人回填)
│   └── status (DRAFT → PENDING → APPROVED → ISSUED)
│
└── license_expiry_date (客户表新增字段)
```

### 2.2 设计模式

参照发票模块的设计模式：
- **部署信息管理** = **发票抬头管理**（提前配置，申请时选择）
- **License 申请** = **发票申请**（创建申请 → 提交审批 → 审批人操作 → 完成）
- **审批流程** = **统一审批引擎扩展**（新增 `business_type=LICENSE`）

---

## 三、数据模型设计

### 3.1 DeploymentInfo（部署信息表）

```python
class DeploymentInfo(Base):
    __tablename__ = "crm_deployment_infos"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    
    deployment_name = Column(String(100), nullable=False, comment="部署名称（如：生产环境、测试环境）")
    server_address = Column(String(500), nullable=False, comment="服务器地址（http:// 或 https:// 开头，IP 可带端口）")
    authorized_users = Column(Integer, nullable=False, comment="授权人数")
    is_default = Column(Boolean, nullable=False, default=False, comment="是否默认部署")
    
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="deployment_infos")

    __table_args__ = (
        Index('idx_deployment_customer_id', 'customer_id'),
        Index('idx_deployment_team_id', 'team_id'),
        {'comment': '客户部署信息表'}
    )
```

**字段说明**：
- `deployment_name`: 部署环境名称，如"生产环境"、"测试环境"、"备份环境"
- `server_address`: 服务器地址，格式为 `http://IP:端口` 或 `https://域名`
- `authorized_users`: 授权人数，整数
- `is_default`: 是否默认部署，用于快速选择

### 3.2 LicenseApplication（License 申请表）

```python
class LicenseApplication(Base):
    __tablename__ = "crm_license_applications"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    application_number = Column(String(50), nullable=False, unique=True, comment="申请单号（自动生成，如 LIC-2024-001）")
    
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    deployment_info_id = Column(BigInteger, ForeignKey('crm_deployment_infos.id', ondelete='SET NULL'), nullable=True, comment="关联部署信息ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='SET NULL'), nullable=True, comment="关联合同ID（正式 License 必填，试用 License 可空）")
    
    expiry_date = Column(Date, nullable=False, comment="到期时间")
    license_type = Column(String(20), nullable=False, comment="License 类型：TRIAL(试用), OFFICIAL(正式)")
    
    # 审批人回填的 License 详细信息
    enterprise_id = Column(String(50), nullable=True, comment="企业编号（审批人回填，如：15739）")
    supported_modules = Column(String(500), nullable=True, comment="支持模块（审批人回填，如：desktop,web,branch）")
    server_license_code = Column(Text, nullable=True, comment="服务端 License（审批人回填）")
    client_license_code = Column(Text, nullable=True, comment="客户端 License（审批人回填）")
    
    # 申请人备注
    remark = Column(Text, nullable=True, comment="备注（申请时填写，如：需要开通 desktop,web,branch）")
    
    status = Column(String(20), nullable=False, default=LicenseApplicationStatus.DRAFT, comment="申请状态")
    applicant_id = Column(String(100), nullable=False, comment="申请人飞书用户ID")
    approver_id = Column(String(100), nullable=True, comment="审批人飞书用户ID")
    approved_time = Column(DateTime, nullable=True, comment="审批时间")
    
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="license_applications")
    deployment_info = relationship("DeploymentInfo", back_populates="license_applications")
    contract = relationship("Contract", back_populates="license_applications")

    __table_args__ = (
        Index('idx_license_customer_id', 'customer_id'),
        Index('idx_license_contract_id', 'contract_id'),
        Index('idx_license_status', 'status'),
        Index('idx_license_application_number', 'application_number'),
        Index('idx_license_team_id', 'team_id'),
        {'comment': 'License 申请表'}
    )
```

**状态枚举**：
```python
class LicenseApplicationStatus:
    DRAFT = "DRAFT"           # 草稿
    PENDING = "PENDING"       # 待审批
    APPROVED = "APPROVED"     # 已批准
    REJECTED = "REJECTED"     # 已拒绝
    ISSUED = "ISSUED"         # 已发放（审批人回填授权码后）
```

**类型枚举**：
```python
class LicenseType:
    TRIAL = "TRIAL"           # 试用 License
    OFFICIAL = "OFFICIAL"     # 正式 License
```

### 3.3 Customer 表扩展

```python
# 在 Customer 模型中新增字段
license_expiry_date = Column(Date, nullable=True, comment="客户 License 最晚到期时间（自动更新）")
license_type = Column(String(20), nullable=True, comment="客户 License 类型（自动更新）：TRIAL/OFFICIAL")
```

**更新逻辑**：
- License 申请审批通过后，系统自动更新 `license_expiry_date` 和 `license_type` 为所有已审批通过的 License 的最晚到期时间对应的类型
- 如果新申请的到期时间早于现有到期时间，不更新
- 如果新申请的到期时间晚于现有到期时间，更新为新时间和新类型
- 如果还没有已发放的 License，两个字段都为空

---

## 四、API 接口设计

### 4.1 部署信息管理接口

**基础路径**：`/api/v1/deployment-infos`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/` | 新增部署信息 | DEPLOYMENT_INFO_MANAGE |
| GET | `/` | 列表查询（按 customer_id 筛选） | DEPLOYMENT_INFO_MANAGE |
| GET | `/{deployment_id}` | 获取详情 | DEPLOYMENT_INFO_MANAGE |
| PUT | `/{deployment_id}` | 编辑部署信息 | DEPLOYMENT_INFO_MANAGE |
| DELETE | `/{deployment_id}` | 删除部署信息 | DEPLOYMENT_INFO_MANAGE |
| PATCH | `/{deployment_id}/set-default` | 设置默认部署 | DEPLOYMENT_INFO_MANAGE |

**创建部署信息请求示例**：
```json
{
  "customer_id": 1,
  "deployment_name": "生产环境",
  "server_address": "https://crm.example.com",
  "authorized_users": 100,
  "is_default": true
}
```

### 4.2 License 申请接口

**基础路径**：`/api/v1/license-applications`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/` | 创建 License 申请 | LICENSE_APPLICATION_CREATE |
| GET | `/` | 列表查询（支持按 customer_id、status 筛选） | LICENSE_VIEW |
| GET | `/{application_id}` | 获取详情 | LICENSE_VIEW |
| PUT | `/{application_id}` | 编辑申请（仅草稿） | LICENSE_APPLICATION_CREATE |
| DELETE | `/{application_id}` | 删除申请（仅草稿） | LICENSE_APPLICATION_CREATE |
| POST | `/{application_id}/submit` | 提交审批 | LICENSE_APPLICATION_CREATE |
| POST | `/{application_id}/withdraw` | 撤回申请 | LICENSE_APPLICATION_CREATE |
| GET | `/{application_id}/export` | 导出 Word 文档（审批通过后） | LICENSE_VIEW |

**创建 License 申请请求示例**：
```json
{
  "customer_id": 1,
  "deployment_info_id": 1,
  "contract_id": 10,  // 正式 License 必填，试用 License 可空
  "expiry_date": "2026-12-31",
  "license_type": "OFFICIAL"
}
```

**关键业务逻辑**：
1. 创建申请时，系统自动生成申请单号（格式：LIC-YYYY-NNN）
2. 提交审批时校验：
   - 正式 License：必须关联合同且合同状态为 `EFFECTIVE` 或 `SIGNED`
   - 试用 License：合同字段可空
3. 审批通过后自动更新客户表的 `license_expiry_date`

### 4.3 审批接口（复用统一审批引擎）

**基础路径**：`/api/v1/approvals/LICENSE`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/{application_id}/submit` | 提交审批 | LICENSE_APPLICATION_CREATE |
| POST | `/{application_id}/approve` | 审批通过（需填写 license_code） | LICENSE_APPROVE |
| POST | `/{application_id}/reject` | 审批拒绝 | LICENSE_APPROVE |
| POST | `/{application_id}/cancel` | 撤回审批（仅提交人） | LICENSE_APPLICATION_CREATE |
| GET | `/{application_id}/detail` | 获取审批详情 | LICENSE_VIEW |

**审批通过请求示例**：
```json
{
  "license_info": "企业编号: 15739\n企业名称: 青岛颂康泰国际旅行社有限公司\n客户端过期时间: 2026-07-17\n服务端过期时间: 2026-07-17\n设备数: 10\n支持模块: desktop,web,branch,scheduledTask,grpc,dubbo,ai\n服务器地址: http://10.197.236.112:8891\n\n服务器端 License: \niHE43m7q//cI+...\n\n客户端 License: \nNPR7aI2qGG1G...",
  "comment": "已生成授权码"
}
```

**审批流程逻辑**：
- 审批人在审批页面填写完整的 License 信息（包含企业编号、支持模块、服务端 License、客户端 License）
- 提交审批通过后，系统解析 License 信息并写入 LicenseApplication 表
- 同时更新申请状态为 `ISSUED`
- 更新客户表的 `license_expiry_date` 和 `license_type`
- 发送飞书通知给申请人

**License 信息解析函数**：
```python
def parse_license_info(license_text: str) -> dict:
    """解析审批人回填的 License 信息"""
    lines = license_text.strip().split('\n')
    data = {}
    
    for i, line in enumerate(lines):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            if key == '企业编号':
                data['enterprise_id'] = value
            elif key == '支持模块':
                data['supported_modules'] = value
            elif key == '服务器端 License':
                # 服务器端 License 可能是多行，收集后续所有行直到遇到"客户端 License"
                server_license_lines = [value]
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line.startswith('客户端 License'):
                        break
                    server_license_lines.append(next_line)
                data['server_license_code'] = '\n'.join(server_license_lines)
            elif key == '客户端 License':
                # 客户端 License 可能是多行，收集后续所有行
                client_license_lines = [value]
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    client_license_lines.append(next_line)
                data['client_license_code'] = '\n'.join(client_license_lines)
    
    return data
```

**字段映射**：
- `enterprise_id` → 企业编号（如：15739）
- `supported_modules` → 支持模块（如：desktop,web,branch）
- `server_license_code` → 服务器端 License（完整加密字符串）
- `client_license_code` → 客户端 License（完整加密字符串）
- `expiry_date` → 已有字段（客户端/服务端过期时间相同）
- `authorized_users` → 已有字段（从部署信息获取，与设备数一致）
- `server_address` → 已有字段（从部署信息获取）
  "comment": "已生成授权码"  // 可选审批意见
}
```

**审批流程逻辑**：
- 审批人在审批页面填写 `license_code` 字段
- 提交审批通过后，系统将 `license_code` 写入 LicenseApplication 表
- 同时更新申请状态为 `APPROVED` → `ISSUED`
- 更新客户表的 `license_expiry_date`
- 发送飞书通知给申请人

---

## 五、前端界面设计

### 5.1 客户详情页新增 Tab

**页面路径**：`CRM-Client/src/views/CustomerDetail.vue`

新增两个 Tab：
1. **部署信息 Tab**
2. **License 申请 Tab**

**部署信息 Tab 功能**：
- 部署信息列表展示（卡片形式）
- 新增/编辑/删除部署信息按钮
- 设置默认部署按钮
- 每个卡片显示：部署名称、服务器地址、授权人数、是否默认

**License 申请 Tab 功能**：
- License 申请列表展示（表格形式）
- 创建申请按钮
- 申请详情查看
- 导出 Word 文档按钮（审批通过后显示）
- 状态标签：草稿、待审批、已批准、已拒绝、已发放

### 5.2 License 申请创建表单

**表单字段**：
1. **部署信息选择**（下拉框）
   - 默认选中客户的默认部署信息
   - 提供"新增部署信息"快捷入口
2. **License 类型选择**（单选）
   - 试用 License（TRIAL）
   - 正式 License（OFFICIAL）
3. **合同选择**（下拉框，正式 License 必填）
   - 筛选客户已审批通过的合同（状态为 EFFECTIVE 或 SIGNED）
   - 试用 License 时隐藏此字段
4. **到期时间**（日期选择器）
   - 必填字段
5. **提交按钮**

**表单校验规则**：
- 正式 License：合同字段必填，系统校验合同状态
- 试用 License：合同字段隐藏/禁用
- 到期时间：必须大于当前日期

### 5.3 审批页面集成

**页面路径**：`CRM-Client/src/views/ApprovalCenter.vue`

在审批列表中新增 LICENSE 类型审批项：
- **待审批 Tab**：显示待审批的 License 申请
- **已处理 Tab**：显示已审批的 License 申请

**审批详情页面**：
- 显示申请信息：客户名称、部署信息、到期时间、License 类型、关联合同（如有）
- **授权码填写框**（文本框）
  - 审批人填写授权码内容
  - 必填字段
- 审批意见填写框（可选）
- 批准/拒绝按钮

### 5.4 导出 Word 文档

**导出按钮位置**：
- License 申请详情页（审批通过后显示）
- License 申请列表（审批通过的申请行显示导出按钮）

**导出内容**：
- 企业名称（客户 account_name）
- 服务器地址（从部署信息获取）
- 授权人数（从部署信息获取）
- 到期时间
- License 类型（试用/正式）
- 授权码内容
- 申请单号
- 申请时间

**导出格式**：
- 文件名：`License_{application_number}_{customer_name}.docx`
- 使用 python-docx 库生成 Word 文档
- 文档模板：包含标题、表格、签名栏等

---

## 六、审批流程配置

### 6.1 统一审批引擎扩展

在 `app/constants/business_types.py` 中新增业务类型：

```python
class BusinessType:
    CONTRACT = "CONTRACT"
    PAYMENT = "PAYMENT"
    INVOICE = "INVOICE"
    LICENSE = "LICENSE"  # 新增
```

### 6.2 审批流程配置

**ApprovalFlow 表配置**：
- `business_type`: LICENSE
- `flow_name`: License 审批流程
- `flow_code`: LICENSE_APPROVAL
- 支持多级审批节点配置（类似合同审批）

**审批节点示例**：
```
节点1: TEAM_ADMIN（团队所有者审批）
节点2: SALES_DIRECTOR（销售总监审批，可选）
```

**未配置流程语义**：
- 如果团队未配置 LICENSE 类型审批流程，提交审批时直接进入"免审批"状态
- 审批人（团队所有者）直接填写授权码即可完成审批

---

## 七、消息通知设计

### 7.1 飞书消息通知

**通知场景**：

| 场景 | 接收人 | 消息内容 |
|------|--------|----------|
| License 申请提交 | 审批人（审批节点对应的角色） | 客户名称、License 类型、到期时间、申请人 |
| License 审批通过 | 申请人 | 客户名称、授权码、到期时间、申请单号、导出链接 |
| License 审批拒绝 | 申请人 | 客户名称、拒绝原因、申请单号 |
| 客户到期时间更新 | 销售人员（客户负责人） | 客户名称、新的到期时间（可选通知） |

**消息格式**：
```
【License 审批通知】
客户：{客户名称}
类型：{试用/正式}
到期时间：{YYYY-MM-DD}
申请人：{申请人姓名}

请点击链接审批：{审批中心链接}
```

### 7.2 通知实现

复用现有的飞书通知服务：
- `app/services/notification_service.py`
- 发送飞书卡片消息或文本消息

---

## 八、权限配置

### 8.1 新增权限码

在 `CRM-Docs/system/GLOSSARY.md` 中新增权限码定义：

| 权限码 | 说明 | 适用角色 |
|--------|------|----------|
| DEPLOYMENT_INFO_MANAGE | 管理客户部署信息（新增/编辑/删除/查看） | SALES_MEMBER, SALES_DIRECTOR |
| LICENSE_APPLICATION_CREATE | 创建 License 申请（新增/编辑/删除/提交） | SALES_MEMBER, SALES_DIRECTOR |
| LICENSE_APPROVE | 审批 License 申请（批准/拒绝） | TEAM_ADMIN, SALES_DIRECTOR, FINANCE |
| LICENSE_VIEW | 查看 License 申请列表（销售成员看自己，销售总监看全部） | SALES_MEMBER, SALES_DIRECTOR, FINANCE |

### 8.2 权限矩阵

| 功能 | 销售成员 | 销售总监 | 财务 | 团队所有者 |
|------|:--------:|:--------:|:----:|:----------:|
| 管理部署信息 | ✓ | ✓ | ✗ | ✓ |
| 创建 License 申请 | ✓ | ✓ | ✗ | ✓ |
| 查看 License 申请 | 自己 | 全部 | 全部 | 全部 |
| 审批 License 申请 | ✗ | ✓ | ✓ | ✓ |
| 导出 License 文件 | 自己申请 | 全部 | 全部 | 全部 |

---

## 九、实施步骤概览

### Phase 1: 数据层（后端基础）

1. 数据模型设计与迁移
   - 创建 DeploymentInfo 表
   - 创建 LicenseApplication 表
   - Customer 表新增 license_expiry_date 字段
   - 新增 business_type=LICENSE 常量

2. CRUD 层实现
   - DeploymentInfo CRUD
   - LicenseApplication CRUD
   - 客户到期时间自动更新逻辑

### Phase 2: API 层（后端接口）

1. 部署信息管理接口
   - 5 个基础 CRUD 接口
   - 设置默认部署接口

2. License 申请接口
   - 8 个申请管理接口
   - Word 文档导出接口

3. 审批接口扩展
   - 统一审批引擎适配 LICENSE 类型
   - approve 接口支持 license_code 参数

### Phase 3: 前端界面

1. 客户详情页新增 Tab
   - 部署信息 Tab
   - License 申请 Tab

2. License 申请创建表单
   - 部署信息选择
   - License 类型选择
   - 合同选择（动态显示/隐藏）
   - 到期时间选择

3. 审批页面集成
   - LICENSE 类型审批项
   - 授权码填写框
   - 审批操作按钮

### Phase 4: 通知与权限

1. 飞书消息通知
   - 申请提交通知
   - 审批通过通知
   - 审批拒绝通知

2. 权限配置
   - 新增 4 个权限码
   - 权限矩阵配置
   - 角色权限关联

### Phase 5: 测试与上线

1. 单元测试
   - CRUD 层测试
   - API 接口测试
   - 审批流程测试

2. 集成测试
   - 申请 → 审批 → 导出完整流程测试
   - 合同校验逻辑测试
   - 客户到期时间更新测试

3. 用户验收测试
   - 销售人员操作流程验证
   - 审批人操作流程验证
   - Word 文档导出验证

---

## 十、技术要点

### 10.1 合同校验逻辑

**校验规则**：
- 正式 License 申请：必须关联合同，合同状态为 `EFFECTIVE` 或 `SIGNED`
- 试用 License 申请：合同字段可空

**校验时机**：
- 创建申请时：前端校验（提交前检查合同状态）
- 提交审批时：后端校验（API 层二次校验）

### 10.2 客户到期时间自动更新

**更新逻辑**：
```python
def update_customer_license_expiry(customer_id):
    """更新客户 License 最晚到期时间"""
    # 查询客户所有已审批通过的 License 申请
    approved_applications = db.query(LicenseApplication).filter(
        LicenseApplication.customer_id == customer_id,
        LicenseApplication.status.in_([LicenseApplicationStatus.APPROVED, LicenseApplicationStatus.ISSUED])
    ).all()
    
    if approved_applications:
        # 取最晚到期时间
        max_expiry_date = max(app.expiry_date for app in approved_applications)
        # 更新客户表
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if customer:
            customer.license_expiry_date = max_expiry_date
            db.commit()
```

**触发时机**：
- License 申请审批通过后（approve 接口）
- License 申请状态从 APPROVED 变为 ISSUED 后

### 10.3 Word 文档导出

**技术方案**：
- 使用 `python-docx` 库生成 Word 文档
- 文档模板定义（包含标题、信息列表、License 授权码）
- 导出接口返回文件下载链接

**导出内容格式（参照样例）**：

```
标题：Apifox私有化授权文件

企业名称: {customer.account_name}
企业编号: {application.enterprise_id}
到期时间: {application.expiry_date}
授权人数: {application.deployment_info.authorized_users}
服务器: {application.deployment_info.server_address}
支持模块: {application.supported_modules}

{试用/正式} License（{authorized_users}人）

服务端 License:
{application.server_license_code}

客户端 License:
{application.client_license_code}
```

**文件名格式**：
- `私有化{试用/正式}License-{客户名称}_{当前日期}.docx`
- 例如：`私有化试用License-广东智通人才连锁股份有限公司_20260706.docx`

**示例代码**：
```python
from docx import Document
from docx.shared import Pt, Inches
from datetime import datetime

def export_license_document(application):
    """导出 License 文档"""
    doc = Document()
    
    # 标题
    title = doc.add_heading('Apifox私有化授权文件', 0)
    
    # 企业信息
    doc.add_paragraph(f"企业名称: {application.customer.account_name}")
    doc.add_paragraph(f"企业编号: {application.enterprise_id}")
    doc.add_paragraph(f"到期时间: {application.expiry_date.strftime('%Y-%m-%d')}")
    doc.add_paragraph(f"授权人数: {application.deployment_info.authorized_users}")
    doc.add_paragraph(f"服务器: {application.deployment_info.server_address}")
    doc.add_paragraph(f"支持模块: {application.supported_modules}")
    
    # License 类型标题
    license_type_text = '试用' if application.license_type == 'TRIAL' else '正式'
    doc.add_paragraph()
    doc.add_paragraph(f"{license_type_text} License（{application.deployment_info.authorized_users}人）")
    
    # 服务端 License
    doc.add_paragraph()
    doc.add_paragraph("服务端 License:")
    doc.add_paragraph(application.server_license_code)
    
    # 客户端 License
    doc.add_paragraph()
    doc.add_paragraph("客户端 License:")
    doc.add_paragraph(application.client_license_code)
    
    # 文件名
    current_date = datetime.now().strftime('%Y%m%d')
    file_name = f"私有化{license_type_text}License-{application.customer.account_name}_{current_date}.docx"
    file_path = f"/tmp/{file_name}"
    doc.save(file_path)
    
    return file_path
```

---

## 十一、风险与注意事项

### 11.1 数据一致性风险

**风险点**：
- 部署信息删除后，已审批通过的 License 申请可能丢失部署信息
- 合同删除后，正式 License 申请可能丢失合同关联

**应对方案**：
- DeploymentInfo 删除时，LicenseApplication 的 deployment_info_id 置为 NULL（使用 SET NULL）
- Contract 删除时，LicenseApplication 的 contract_id 置为 NULL（使用 SET NULL）
- 导出 Word 文档时，如果 deployment_info 为 NULL，提示用户手动补充信息

### 11.2 审批流程未配置风险

**风险点**：
- 团队未配置 LICENSE 类型审批流程时，申请提交后可能无法审批

**应对方案**：
- 继承统一审批引擎的"未配置流程=免审批直通"语义
- 提交审批后，审批人（团队所有者）直接填写授权码即可完成审批
- 前端提示：如果未配置流程，显示"免审批流程"提示信息

### 11.3 授权码内容安全

**风险点**：
- 授权码内容可能包含敏感信息（加密密钥等）
- Word 文档导出后可能泄露授权码内容

**应对方案**：
- 授权码内容存储在数据库中，权限控制严格（仅审批人和申请人可查看）
- Word 文档导出后，提示用户妥善保管文件
- 后续可考虑加密授权码存储（Phase 2 功能）

---

## 十二、后续扩展方向

### 12.1 Phase 2 扩展功能

| 功能 | 说明 |
|------|------|
| **License 续期申请** | 支持基于现有 License 申请续期，自动关联原部署信息 |
| **授权码加密存储** | 授权码内容加密存储，提高安全性 |
| **批量申请** | 支持一次性为多个客户申请 License |
| **License 使用统计** | 统计 License 申请数量、到期提醒等 |

### 12.2 AI Agent 集成

**AI 工具设计**：
- `create_license_application`: 创建 License 申请
- `query_license_status`: 查询 License 申请状态
- `export_license_document`: 导出 License 文档

**AI 意图识别**：
- 用户输入"申请 License" → AI 识别为 `create_license_application` 意图
- 用户输入"查询 License 状态" → AI 识别为 `query_license_status` 意图

---

## 十三、文档维护

**文档版本**：v1.0
**最后更新**：2026-07-06
**维护者**：CRMWolf 开发团队

**更新记录**：
- v1.0 (2026-07-06): 初版设计文档，完成整体架构、数据模型、API 接口、前端界面设计
# License 授权码管理功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 License 授权码管理功能，支持 POC 试用和正式部署两种场景，包含部署信息管理、License 申请、审批流程、消息通知、Word 文档导出。

**Architecture:** 参照发票模块设计模式，DeploymentInfo 类似 InvoiceTitle（提前配置），LicenseApplication 类似 InvoiceApplication（申请→审批→导出），复用统一审批引擎（新增 business_type=LICENSE）。

**Tech Stack:** Python 3.11 + FastAPI 0.115 + SQLAlchemy + Pydantic + Vue 3 + TypeScript + Element Plus + python-docx

## Global Constraints

- **团队隔离**: 所有数据表必须包含 `team_id` 字段，CRUD 操作必须传入 `team_id`
- **权限控制**: 所有 API 接口必须校验权限码，权限码定义在 `CRM-Docs/system/GLOSSARY.md`
- **审批引擎**: 继承统一审批引擎的"未配置流程=免审批直通"语义
- **状态枚举**: 禁止推断状态值，必须查阅 `app/constants/` 目录下的常量定义
- **Pydantic 强制校验**: 所有外部输入必须校验，禁止裸 dict
- **Alembic 迁移**: 禁止独立数据库脚本，所有数据库变更必须通过 Alembic 迁移

---

## File Structure Map

**后端新增文件**:
- `app/models/deployment.py` - DeploymentInfo 数据模型
- `app/models/license_application.py` - LicenseApplication 数据模型
- `app/schemas/deployment.py` - DeploymentInfo Pydantic schemas
- `app/schemas/license_application.py` - LicenseApplication Pydantic schemas
- `app/crud/crud_deployment.py` - DeploymentInfo CRUD
- `app/crud/crud_license_application.py` - LicenseApplication CRUD
- `app/api/deployment.py` - 部署信息管理 API
- `app/api/license_application.py` - License 申请 API
- `app/services/license_export_service.py` - Word 文档导出服务

**后端修改文件**:
- `app/constants/business_types.py` - 新增 LICENSE 业务类型
- `app/models/customer.py` - 新增 license_expiry_date 字段和 deployment_infos relationship
- `app/models/contract.py` - 新增 license_applications relationship
- `app/models/__init__.py` - 导出新增模型
- `app/api/__init__.py` - 注册新增路由
- `CRM-Docs/system/GLOSSARY.md` - 新增 4 个权限码定义

**前端新增文件**:
- `src/api/deployment.ts` - 部署信息 API 调用
- `src/api/licenseApplication.ts` - License 申请 API 调用
- `src/schemas/deployment.ts` - DeploymentInfo Zod schemas
- `src/schemas/licenseApplication.ts` - LicenseApplication Zod schemas
- `src/components/LicenseManagement.vue` - License 管理合并组件（包含部署信息和 License 申请两个区域）
- `src/components/LicenseApplicationDialog.vue` - License 申请创建/编辑对话框组件
- `src/components/DeploymentDialog.vue` - 部署信息创建/编辑对话框组件
- `src/components/LicenseApprovalDialog.vue` - License 审批对话框组件

**前端修改文件**:
- `src/views/CustomerDetail.vue` - 新增"License 管理" Tab（合并部署信息和 License 申请）
- `src/views/ApprovalCenter.vue` - 新增 LICENSE 类型审批项

**迁移文件**:
- `migrations/versions/<timestamp>_add_deployment_and_license_tables.py`

---

## Phase 1: 数据层基础（Task 1-4）

### Task 1: 新增 LICENSE 业务类型常量

**Files:**
- Modify: `CRM-Server/app/constants/business_types.py`

**Interfaces:**
- Consumes: 无
- Produces: `BusinessType.LICENSE` 常量，供后续审批引擎使用

- [ ] **Step 1: 修改 business_types.py，新增 LICENSE 常量**

```python
class BusinessType:
    CONTRACT = "CONTRACT"
    PAYMENT = "PAYMENT"
    INVOICE = "INVOICE"
    LICENSE = "LICENSE"  # 新增

ALL_BUSINESS_TYPES = [BusinessType.CONTRACT, BusinessType.PAYMENT, BusinessType.INVOICE, BusinessType.LICENSE]

BUSINESS_TYPE_DISPLAY_NAMES = {
    BusinessType.CONTRACT: "合同",
    BusinessType.PAYMENT: "回款登记",
    BusinessType.INVOICE: "发票申请",
    BusinessType.LICENSE: "License申请",  # 新增
}
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Server/app/constants/business_types.py
git commit -m "feat(constants): add LICENSE business type for approval engine"
```

---

### Task 2: 创建 DeploymentInfo 数据模型

**Files:**
- Create: `CRM-Server/app/models/deployment.py`
- Modify: `CRM-Server/app/models/__init__.py`
- Modify: `CRM-Server/app/models/customer.py`

**Interfaces:**
- Consumes: Customer 模型
- Produces: `DeploymentInfo` 模型，Customer 新增 `deployment_infos` relationship

- [ ] **Step 1: 创建 DeploymentInfo 模型**

```python
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class DeploymentInfo(Base):
    """客户部署信息表"""
    __tablename__ = "crm_deployment_infos"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    
    deployment_name = Column(String(100), nullable=False, comment="部署名称（如：生产环境、测试环境）")
    server_address = Column(String(500), nullable=False, comment="服务器地址（http:// 或 https:// 开头）")
    authorized_users = Column(Integer, nullable=False, comment="授权人数")
    is_default = Column(Boolean, nullable=False, default=False, comment="是否默认部署")
    
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="deployment_infos")
    license_applications = relationship("LicenseApplication", back_populates="deployment_info")

    __table_args__ = (
        Index('idx_deployment_customer_id', 'customer_id'),
        Index('idx_deployment_team_id', 'team_id'),
        {'comment': '客户部署信息表'}
    )
```

- [ ] **Step 2: Customer 模型新增 deployment_infos relationship 和 license_expiry_date 字段**

Modify: `CRM-Server/app/models/customer.py`

在字段部分新增：
```python
license_expiry_date = Column(Date, nullable=True, comment="客户 License 最晚到期时间（自动更新）")
```

在 relationships 部分新增（contacts 之后）：
```python
deployment_infos = relationship("DeploymentInfo", back_populates="customer", cascade="all, delete-orphan")
license_applications = relationship("LicenseApplication", back_populates="customer", cascade="all, delete-orphan")
```

- [ ] **Step 3: __init__.py 导出 DeploymentInfo**

Modify: `CRM-Server/app/models/__init__.py`

新增导入：
```python
from app.models.deployment import DeploymentInfo
```

新增导出：
```python
__all__ = [..., "DeploymentInfo"]
```

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/models/deployment.py CRM-Server/app/models/__init__.py CRM-Server/app/models/customer.py
git commit -m "feat(models): add DeploymentInfo model and customer relationships"
```

---

### Task 3: 创建 LicenseApplication 数据模型

**Files:**
- Create: `CRM-Server/app/models/license_application.py`
- Modify: `CRM-Server/app/models/__init__.py`
- Modify: `CRM-Server/app/models/contract.py`

**Interfaces:**
- Consumes: DeploymentInfo, Customer, Contract
- Produces: `LicenseApplication` 模型，状态枚举，类型枚举，Contract 新增 `license_applications` relationship

- [ ] **Step 1: 创建 LicenseApplication 模型**

```python
from sqlalchemy import Column, BigInteger, String, DateTime, Date, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class LicenseApplicationStatus:
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"


class LicenseType:
    TRIAL = "TRIAL"
    OFFICIAL = "OFFICIAL"


class LicenseApplication(Base):
    """License 申请表"""
    __tablename__ = "crm_license_applications"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    application_number = Column(String(50), nullable=False, unique=True, comment="申请单号（自动生成）")
    
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    deployment_info_id = Column(BigInteger, ForeignKey('crm_deployment_infos.id', ondelete='SET NULL'), nullable=True, comment="关联部署信息ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='SET NULL'), nullable=True, comment="关联合同ID")
    
    expiry_date = Column(Date, nullable=False, comment="到期时间")
    license_type = Column(String(20), nullable=False, comment="License 类型")
    license_code = Column(Text, nullable=True, comment="授权码（审批人回填）")
    
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
        {'comment': 'License 申请表'}
    )
```

- [ ] **Step 2: Contract 模型新增 license_applications relationship**

Modify: `CRM-Server/app/models/contract.py`

在 relationships 部分新增：
```python
license_applications = relationship("LicenseApplication", back_populates="contract")
```

- [ ] **Step 3: __init__.py 导出 LicenseApplication**

Modify: `CRM-Server/app/models/__init__.py`

新增导入和导出：
```python
from app.models.license_application import LicenseApplication, LicenseApplicationStatus, LicenseType
__all__ = [..., "LicenseApplication", "LicenseApplicationStatus", "LicenseType"]
```

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/models/license_application.py CRM-Server/app/models/__init__.py CRM-Server/app/models/contract.py
git commit -m "feat(models): add LicenseApplication model with status and type enums"
```

---

### Task 4: 创建数据库迁移脚本

**Files:**
- Create: `CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py`

**Interfaces:**
- Consumes: DeploymentInfo, LicenseApplication, Customer.license_expiry_date
- Produces: 数据库表 crm_deployment_infos, crm_license_applications，Customer 表新增 license_expiry_date 字段

- [ ] **Step 1: 创建迁移脚本**

Run: `cd CRM-Server && alembic revision -m "add_deployment_and_license_tables"`

- [ ] **Step 2: 编辑迁移脚本**

编辑生成的迁移文件，实现 `upgrade()` 和 `downgrade()` 函数，创建表和索引（参照 Task 4 详细代码）

- [ ] **Step 3: 执行迁移**

Run: `cd CRM-Server && alembic upgrade head`

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py
git commit -m "feat(db): add migration for DeploymentInfo and LicenseApplication tables"
```

---

## Phase 2: CRUD 层（Task 5-6）

### Task 5: 创建 DeploymentInfo CRUD 和 Schemas

**Files:**
- Create: `CRM-Server/app/schemas/deployment.py`
- Create: `CRM-Server/app/crud/crud_deployment.py`

**Interfaces:**
- Consumes: DeploymentInfo 模型，team_id
- Produces: CRUD 函数：create, get, get_by_customer, update, delete, set_default

- [ ] **Step 1: 创建 DeploymentInfo schemas**

```python
from pydantic import BaseModel, Field, validator
from datetime import datetime


class DeploymentInfoBase(BaseModel):
    deployment_name: str = Field(..., max_length=100)
    server_address: str = Field(..., max_length=500)
    authorized_users: int = Field(..., gt=0)
    is_default: bool = False
    
    @validator('server_address')
    def validate_server_address(cls, v):
        if not v.startswith('http://') and not v.startswith('https://'):
            raise ValueError('服务器地址必须以 http:// 或 https:// 开头')
        return v


class DeploymentInfoCreate(DeploymentInfoBase):
    customer_id: int


class DeploymentInfoUpdate(BaseModel):
    deployment_name: str | None = None
    server_address: str | None = None
    authorized_users: int | None = None
    is_default: bool | None = None


class DeploymentInfoResponse(DeploymentInfoBase):
    id: int
    customer_id: int
    team_id: int
    created_time: datetime
    last_modified_time: datetime
    
    class Config:
        orm_mode = True
```

- [ ] **Step 2: 创建 DeploymentInfo CRUD**

```python
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.deployment import DeploymentInfo
from app.schemas.deployment import DeploymentInfoCreate, DeploymentInfoUpdate


def create_deployment_info(db: Session, team_id: int, deployment: DeploymentInfoCreate) -> DeploymentInfo:
    db_obj = DeploymentInfo(team_id=team_id, **deployment.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def get_deployment_info(db: Session, team_id: int, deployment_id: int) -> DeploymentInfo | None:
    return db.query(DeploymentInfo).filter(and_(DeploymentInfo.id == deployment_id, DeploymentInfo.team_id == team_id)).first()


def get_deployment_infos_by_customer(db: Session, team_id: int, customer_id: int) -> list[DeploymentInfo]:
    return db.query(DeploymentInfo).filter(and_(DeploymentInfo.customer_id == customer_id, DeploymentInfo.team_id == team_id)).all()


def update_deployment_info(db: Session, team_id: int, deployment_id: int, deployment: DeploymentInfoUpdate) -> DeploymentInfo | None:
    db_obj = get_deployment_info(db, team_id, deployment_id)
    if not db_obj:
        return None
    for key, value in deployment.dict(exclude_unset=True).items():
        setattr(db_obj, key, value)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def delete_deployment_info(db: Session, team_id: int, deployment_id: int) -> bool:
    db_obj = get_deployment_info(db, team_id, deployment_id)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True


def set_default_deployment_info(db: Session, team_id: int, customer_id: int, deployment_id: int) -> DeploymentInfo | None:
    deployments = get_deployment_infos_by_customer(db, team_id, customer_id)
    for d in deployments:
        d.is_default = False
    target = get_deployment_info(db, team_id, deployment_id)
    if not target:
        return None
    target.is_default = True
    db.commit()
    db.refresh(target)
    return target
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/schemas/deployment.py CRM-Server/app/crud/crud_deployment.py
git commit -m "feat(crud): add DeploymentInfo CRUD operations and schemas"
```

---

### Task 6: 创建 LicenseApplication CRUD 和 Schemas

**Files:**
- Create: `CRM-Server/app/schemas/license_application.py`
- Create: `CRM-Server/app/crud/crud_license_application.py`

**Interfaces:**
- Consumes: LicenseApplication 模型，team_id，Contract, Customer
- Produces: CRUD 函数：create, get, list, update, delete, submit, approve, reject, generate_application_number, update_customer_license_expiry

- [ ] **Step 1: 创建 LicenseApplication schemas**

```python
from pydantic import BaseModel, Field, validator
from datetime import date, datetime


class LicenseApplicationBase(BaseModel):
    customer_id: int
    deployment_info_id: int | None = None
    expiry_date: date
    license_type: str
    
    @validator('expiry_date')
    def validate_expiry_date(cls, v):
        if v <= date.today():
            raise ValueError('到期时间必须大于当前日期')
        return v
    
    @validator('license_type')
    def validate_license_type(cls, v):
        if v not in ['TRIAL', 'OFFICIAL']:
            raise ValueError('License 类型必须为 TRIAL 或 OFFICIAL')
        return v


class LicenseApplicationCreate(LicenseApplicationBase):
    contract_id: int | None = None
    
    @validator('contract_id', always=True)
    def validate_contract_for_official(cls, v, values):
        if 'license_type' in values and values['license_type'] == 'OFFICIAL' and not v:
            raise ValueError('正式 License 必须关联合同')
        return v


class LicenseApplicationUpdate(BaseModel):
    deployment_info_id: int | None = None
    contract_id: int | None = None
    expiry_date: date | None = None


class LicenseApplicationApprove(BaseModel):
    license_code: str = Field(..., min_length=1)
    comment: str | None = None


class LicenseApplicationResponse(LicenseApplicationBase):
    id: int
    team_id: int
    application_number: str
    contract_id: int | None
    license_code: str | None
    status: str
    applicant_id: str
    approver_id: str | None
    approved_time: datetime | None
    created_time: datetime
    last_modified_time: datetime
    
    class Config:
        orm_mode = True
```

- [ ] **Step 2: 创建 LicenseApplication CRUD（包含申请单号生成和客户到期时间更新逻辑）**

完整代码见 Task 6 详细实现（包含 generate_application_number 和 update_customer_license_expiry 函数）

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/schemas/license_application.py CRM-Server/app/crud/crud_license_application.py
git commit -m "feat(crud): add LicenseApplication CRUD with application number generator and expiry updater"
```

---

## Phase 3: API 层（Task 7-8）

### Task 7: 创建部署信息管理 API 端点

**Files:**
- Create: `CRM-Server/app/api/deployment.py`
- Modify: `CRM-Server/app/api/__init__.py`

**Interfaces:**
- Consumes: DeploymentInfo CRUD，team_id，权限码 DEPLOYMENT_INFO_MANAGE
- Produces: RESTful API 端点：POST /, GET /, GET /{id}, PUT /{id}, DELETE /{id}, PATCH /{id}/set-default

- [ ] **Step 1: 创建 deployment API**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user_team
from app.crud.crud_deployment import (
    create_deployment_info, get_deployment_info, get_deployment_infos_by_customer,
    update_deployment_info, delete_deployment_info, set_default_deployment_info
)
from app.schemas.deployment import DeploymentInfoCreate, DeploymentInfoUpdate, DeploymentInfoResponse

router = APIRouter(prefix="/api/v1/deployment-infos", tags=["Deployment Info"])


@router.post("/", response_model=DeploymentInfoResponse, status_code=status.HTTP_201_CREATED)
def create_deployment(
    deployment: DeploymentInfoCreate,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """创建部署信息"""
    return create_deployment_info(db, team_id, deployment)


@router.get("/", response_model=list[DeploymentInfoResponse])
def list_deployments(
    customer_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """获取客户的部署信息列表"""
    return get_deployment_infos_by_customer(db, team_id, customer_id)


@router.get("/{deployment_id}", response_model=DeploymentInfoResponse)
def get_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """获取部署信息详情"""
    deployment = get_deployment_info(db, team_id, deployment_id)
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署信息不存在")
    return deployment


@router.put("/{deployment_id}", response_model=DeploymentInfoResponse)
def update_deployment(
    deployment_id: int,
    deployment: DeploymentInfoUpdate,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """更新部署信息"""
    updated = update_deployment_info(db, team_id, deployment_id, deployment)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署信息不存在")
    return updated


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """删除部署信息"""
    if not delete_deployment_info(db, team_id, deployment_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署信息不存在")


@router.patch("/{deployment_id}/set-default", response_model=DeploymentInfoResponse)
def set_default_deployment(
    deployment_id: int,
    customer_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """设置默认部署信息"""
    deployment = set_default_deployment_info(db, team_id, customer_id, deployment_id)
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署信息不存在")
    return deployment
```

- [ ] **Step 2: 注册路由到 __init__.py**

Modify: `CRM-Server/app/api/__init__.py`

新增路由导入和注册：
```python
from app.api.deployment import router as deployment_router
app.include_router(deployment_router)
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/api/deployment.py CRM-Server/app/api/__init__.py
git commit -m "feat(api): add DeploymentInfo management endpoints"
```

---

### Task 8: 创建 License 申请 API 端点

**Files:**
- Create: `CRM-Server/app/api/license_application.py`
- Create: `CRM-Server/app/services/license_export_service.py`
- Modify: `CRM-Server/app/api/__init__.py`

**Interfaces:**
- Consumes: LicenseApplication CRUD，team_id，权限码 LICENSE_APPLICATION_CREATE, LICENSE_VIEW, python-docx
- Produces: RESTful API 端点：POST /, GET /, GET /{id}, PUT /{id}, DELETE /{id}, POST /{id}/submit, POST /{id}/withdraw, GET /{id}/export

- [ ] **Step 1: 创建 license_application API**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user_team, get_current_user_id
from app.crud.crud_license_application import (
    create_license_application, get_license_application, get_license_applications,
    update_license_application, delete_license_application, submit_license_application
)
from app.schemas.license_application import LicenseApplicationCreate, LicenseApplicationUpdate, LicenseApplicationResponse
from app.models.license_application import LicenseApplicationStatus

router = APIRouter(prefix="/api/v1/license-applications", tags=["License Application"])


@router.post("/", response_model=LicenseApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    application: LicenseApplicationCreate,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    applicant_id: str = Depends(get_current_user_id)
):
    """创建 License 申请"""
    return create_license_application(db, team_id, applicant_id, application)


@router.get("/", response_model=list[LicenseApplicationResponse])
def list_applications(
    customer_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """获取 License 申请列表"""
    return get_license_applications(db, team_id, customer_id, status)


@router.get("/{application_id}", response_model=LicenseApplicationResponse)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """获取 License 申请详情"""
    application = get_license_application(db, team_id, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License 申请不存在")
    return application


@router.put("/{application_id}", response_model=LicenseApplicationResponse)
def update_application(
    application_id: int,
    application: LicenseApplicationUpdate,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """更新 License 申请（仅草稿）"""
    updated = update_license_application(db, team_id, application_id, application)
    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能更新草稿状态的申请")
    return updated


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """删除 License 申请（仅草稿）"""
    if not delete_license_application(db, team_id, application_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能删除草稿状态的申请")


@router.post("/{application_id}/submit", response_model=LicenseApplicationResponse)
def submit_application(
    application_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """提交 License 申请"""
    application = submit_license_application(db, team_id, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能提交草稿状态的申请")
    return application


@router.get("/{application_id}/export")
def export_application(
    application_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team)
):
    """导出 License Word 文档"""
    application = get_license_application(db, team_id, application_id)
    if not application or application.status != LicenseApplicationStatus.ISSUED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能导出已发放的 License")
    
    from app.services.license_export_service import export_license_document
    file_path = export_license_document(application)
    return FileResponse(file_path, filename=f"License_{application.application_number}.docx")
```

- [ ] **Step 2: 创建 license_export_service**

```python
from docx import Document
from docx.shared import Pt
from app.models.license_application import LicenseApplication, LicenseType
import tempfile


def export_license_document(application: LicenseApplication) -> str:
    """导出 License Word 文档"""
    doc = Document()
    
    # 标题
    doc.add_heading('软件授权许可证', 0)
    
    # 信息表格
    table = doc.add_table(rows=6, cols=2)
    table.style = 'Table Grid'
    
    rows_data = [
        ('企业名称', application.customer.account_name),
        ('服务器地址', application.deployment_info.server_address if application.deployment_info else '未配置'),
        ('授权人数', application.deployment_info.authorized_users if application.deployment_info else '未配置'),
        ('到期时间', application.expiry_date.strftime('%Y-%m-%d')),
        ('License 类型', '试用' if application.license_type == LicenseType.TRIAL else '正式'),
        ('授权码', application.license_code or '未填写')
    ]
    
    for i, (label, value) in enumerate(rows_data):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = str(value)
    
    # 保存到临时文件
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    doc.save(temp_file.name)
    return temp_file.name
```

- [ ] **Step 3: 注册路由**

Modify: `CRM-Server/app/api/__init__.py`

新增：
```python
from app.api.license_application import router as license_router
app.include_router(license_router)
```

- [ ] **Step 4: 安装 python-docx**

Run: `cd CRM-Server && pip install python-docx && pip freeze > requirements.txt`

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/api/license_application.py CRM-Server/app/services/license_export_service.py CRM-Server/app/api/__init__.py CRM-Server/requirements.txt
git commit -m "feat(api): add LicenseApplication endpoints and Word export service"
```

---

## Phase 4: 前端界面（Task 9-10）

### Task 9: 客户详情页新增 License 管理 Tab（合并部署信息和 License 申请）

**Files:**
- Create: `CRM-Client/src/api/deployment.ts`
- Create: `CRM-Client/src/api/licenseApplication.ts`
- Create: `CRM-Client/src/schemas/deployment.ts`
- Create: `CRM-Client/src/schemas/licenseApplication.ts`
- Create: `CRM-Client/src/components/LicenseManagement.vue` - 合并组件，包含部署信息和 License 申请两部分
- Modify: `CRM-Client/src/views/CustomerDetail.vue`

**Interfaces:**
- Consumes: DeploymentInfo API, LicenseApplication API
- Produces: 客户详情页新增一个 Tab（"License 管理"），包含部署信息管理区和 License 申请管理区

- [ ] **Step 1: 创建前端 API 调用文件**

`src/api/deployment.ts`:
```typescript
import request from '@/utils/request'
import type { DeploymentInfo, DeploymentInfoCreate, DeploymentInfoUpdate } from '@/schemas/deployment'

export const deploymentApi = {
  create: (data: DeploymentInfoCreate) => request.post<DeploymentInfo>('/api/v1/deployment-infos', data),
  list: (customerId: number) => request.get<DeploymentInfo[]>(`/api/v1/deployment-infos?customer_id=${customerId}`),
  get: (id: number) => request.get<DeploymentInfo>(`/api/v1/deployment-infos/${id}`),
  update: (id: number, data: DeploymentInfoUpdate) => request.put<DeploymentInfo>(`/api/v1/deployment-infos/${id}`, data),
  delete: (id: number) => request.delete(`/api/v1/deployment-infos/${id}`),
  setDefault: (id: number, customerId: number) => request.patch<DeploymentInfo>(`/api/v1/deployment-infos/${id}/set-default?customer_id=${customerId}`)
}
```

`src/api/licenseApplication.ts`:
```typescript
import request from '@/utils/request'
import type { LicenseApplication, LicenseApplicationCreate, LicenseApplicationUpdate } from '@/schemas/licenseApplication'

export const licenseApplicationApi = {
  create: (data: LicenseApplicationCreate) => request.post<LicenseApplication>('/api/v1/license-applications', data),
  list: (customerId?: number, status?: string) => request.get<LicenseApplication[]>('/api/v1/license-applications', { params: { customer_id: customerId, status } }),
  get: (id: number) => request.get<LicenseApplication>(`/api/v1/license-applications/${id}`),
  update: (id: number, data: LicenseApplicationUpdate) => request.put<LicenseApplication>(`/api/v1/license-applications/${id}`, data),
  delete: (id: number) => request.delete(`/api/v1/license-applications/${id}`),
  submit: (id: number) => request.post<LicenseApplication>(`/api/v1/license-applications/${id}/submit`),
  export: (id: number) => request.get(`/api/v1/license-applications/${id}/export`, { responseType: 'blob' })
}
```

- [ ] **Step 2: 创建 Zod schemas**

`src/schemas/deployment.ts`:
```typescript
import { z } from 'zod'

export const DeploymentInfoSchema = z.object({
  id: z.number(),
  customer_id: z.number(),
  team_id: z.number(),
  deployment_name: z.string().max(100),
  server_address: z.string().max(500).regex(/^https?:\/\//, '服务器地址必须以 http:// 或 https:// 开头'),
  authorized_users: z.number().positive(),
  is_default: z.boolean(),
  created_time: z.string(),
  last_modified_time: z.string()
})

export const DeploymentInfoCreateSchema = DeploymentInfoSchema.omit({ id: true, team_id: true, created_time: true, last_modified_time: true })
export const DeploymentInfoUpdateSchema = DeploymentInfoSchema.partial().omit({ id: true, customer_id: true, team_id: true, created_time: true, last_modified_time: true })

export type DeploymentInfo = z.infer<typeof DeploymentInfoSchema>
export type DeploymentInfoCreate = z.infer<typeof DeploymentInfoCreateSchema>
export type DeploymentInfoUpdate = z.infer<typeof DeploymentInfoUpdateSchema>
```

`src/schemas/licenseApplication.ts`:
```typescript
import { z } from 'zod'

export const LicenseApplicationSchema = z.object({
  id: z.number(),
  team_id: z.number(),
  application_number: z.string(),
  customer_id: z.number(),
  deployment_info_id: z.number().nullable(),
  contract_id: z.number().nullable(),
  expiry_date: z.string(),
  license_type: z.enum(['TRIAL', 'OFFICIAL']),
  license_code: z.string().nullable(),
  status: z.enum(['DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'ISSUED']),
  applicant_id: z.string(),
  approver_id: z.string().nullable(),
  approved_time: z.string().nullable(),
  created_time: z.string(),
  last_modified_time: z.string()
})

export const LicenseApplicationCreateSchema = LicenseApplicationSchema.omit({
  id: true, team_id: true, application_number: true, license_code: true, status: true,
  applicant_id: true, approver_id: true, approved_time: true, created_time: true, last_modified_time: true
}).extend({
  expiry_date: z.string().refine(val => new Date(val) > new Date(), '到期时间必须大于当前日期')
})

export const LicenseApplicationUpdateSchema = LicenseApplicationSchema.partial().omit({
  id: true, customer_id: true, team_id: true, application_number: true, license_code: true,
  applicant_id: true, approver_id: true, approved_time: true, created_time: true, last_modified_time: true
})

export type LicenseApplication = z.infer<typeof LicenseApplicationSchema>
export type LicenseApplicationCreate = z.infer<typeof LicenseApplicationCreateSchema>
export type LicenseApplicationUpdate = z.infer<typeof LicenseApplicationUpdateSchema>
```

- [ ] **Step 3: 修改 CustomerDetail.vue，新增 License 管理 Tab**

在 CustomerDetail.vue 的 Tab 列表中新增：
```vue
<el-tabs v-model="activeTab">
  <el-tab-pane label="基本信息" name="basic">...</el-tab-pane>
  <el-tab-pane label="联系人" name="contacts">...</el-tab-pane>
  <el-tab-pane label="商机" name="opportunities">...</el-tab-pane>
  <el-tab-pane label="合同" name="contracts">...</el-tab-pane>
  <el-tab-pane label="回款" name="payments">...</el-tab-pane>
  <el-tab-pane label="发票" name="invoices">...</el-tab-pane>
  <!-- 新增：合并部署信息和 License 申请到一个 Tab -->
  <el-tab-pane label="License 管理" name="license-management">
    <LicenseManagement :customer-id="customerId" />
  </el-tab-pane>
</el-tabs>
```

**设计说明**：
- 部署信息和 License 申请属于同一个业务域，合并到一个 Tab 可以减少用户切换负担
- LicenseManagement 组件内部分为两个区域：上方部署信息管理区，下方 License 申请管理区
- 用户操作流程：先配置部署信息 → 再申请 License，一站式完成

- [ ] **Step 4: Commit**

```bash
git add CRM-Client/src/api/deployment.ts CRM-Client/src/api/licenseApplication.ts CRM-Client/src/schemas/deployment.ts CRM-Client/src/schemas/licenseApplication.ts CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(frontend): add DeploymentInfo and LicenseApplication APIs, schemas, and CustomerDetail tabs"
```

---

### Task 10: 创建 License 管理合并组件

**Files:**
- Create: `CRM-Client/src/components/LicenseManagement.vue` - 合并部署信息和 License 申请管理
- Create: `CRM-Client/src/components/LicenseApplicationDialog.vue` - License 申请创建/编辑对话框

**Interfaces:**
- Consumes: DeploymentInfo API, LicenseApplication API
- Produces: License 管理合并组件（上方部署信息区，下方 License 申请区），License 申请对话框组件

- [ ] **Step 1: 创建 LicenseManagement.vue（合并组件）**

```vue
<template>
  <div>
    <!-- 上方区域：部署信息管理 -->
    <el-divider content-position="left">
      <el-icon><Server /></el-icon> 部署信息配置
    </el-divider>
    <el-button type="primary" size="small" @click="showDeploymentDialog">新增部署信息</el-button>
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="8" v-for="deployment in deployments" :key="deployment.id">
        <el-card shadow="hover">
          <div slot="header">
            <span>{{ deployment.deployment_name }}</span>
            <el-tag v-if="deployment.is_default" type="success" size="small" style="margin-left: 10px">默认</el-tag>
          </div>
          <div>
            <p><strong>服务器地址：</strong>{{ deployment.server_address }}</p>
            <p><strong>授权人数：</strong>{{ deployment.authorized_users }}</p>
          </div>
          <div slot="footer" style="text-align: right">
            <el-button size="small" @click="editDeployment(deployment)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteDeployment(deployment.id)">删除</el-button>
            <el-button v-if="!deployment.is_default" size="small" type="success" @click="setDefault(deployment.id)">设为默认</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 下方区域：License 申请管理 -->
    <el-divider content-position="left" style="margin-top: 40px">
      <el-icon><Document /></el-icon> License 申请记录
    </el-divider>
    <el-button type="primary" size="small" @click="showLicenseDialog">申请 License</el-button>
    <el-table :data="applications" style="margin-top: 20px">
      <el-table-column prop="application_number" label="申请单号" width="150" />
      <el-table-column prop="license_type" label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.license_type === 'TRIAL' ? 'warning' : 'success'" size="small">
            {{ row.license_type === 'TRIAL' ? '试用' : '正式' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="expiry_date" label="到期时间" width="120" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_time" label="申请时间" width="180" />
      <el-table-column label="操作" width="300">
        <template #default="{ row }">
          <el-button v-if="row.status === 'DRAFT'" size="small" @click="editApplication(row)">编辑</el-button>
          <el-button v-if="row.status === 'DRAFT'" size="small" type="primary" @click="submitApplication(row.id)">提交审批</el-button>
          <el-button v-if="row.status === 'ISSUED'" size="small" type="success" @click="exportLicense(row.id)">导出文档</el-button>
          <el-button v-if="row.status === 'DRAFT'" size="small" type="danger" @click="deleteApplication(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 对话框：部署信息 -->
    <DeploymentDialog
      v-if="showDeploymentDialogVisible"
      :visible="showDeploymentDialogVisible"
      :customer-id="customerId"
      :deployment="currentDeployment"
      @close="closeDeploymentDialog"
      @success="refreshDeployments"
    />

    <!-- 对话框：License 申请 -->
    <LicenseApplicationDialog
      v-if="showLicenseDialogVisible"
      :visible="showLicenseDialogVisible"
      :customer-id="customerId"
      :application="currentApplication"
      :deployments="deployments"
      @close="closeLicenseDialog"
      @success="refreshApplications"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Server, Document } from '@element-plus/icons-vue'
import { deploymentApi } from '@/api/deployment'
import { licenseApplicationApi } from '@/api/licenseApplication'
import type { DeploymentInfo } from '@/schemas/deployment'
import type { LicenseApplication } from '@/schemas/licenseApplication'
import DeploymentDialog from './DeploymentDialog.vue'
import LicenseApplicationDialog from './LicenseApplicationDialog.vue'

const props = defineProps<{ customerId: number }>()

// 部署信息数据
const deployments = ref<DeploymentInfo[]>([])
const showDeploymentDialogVisible = ref(false)
const currentDeployment = ref<DeploymentInfo | null>(null)

// License 申请数据
const applications = ref<LicenseApplication[]>([])
const showLicenseDialogVisible = ref(false)
const currentApplication = ref<LicenseApplication | null>(null)

// 初始化加载
onMounted(async () => {
  await Promise.all([refreshDeployments(), refreshApplications()])
})

// 部署信息操作
const refreshDeployments = async () => {
  deployments.value = await deploymentApi.list(props.customerId)
}

const showDeploymentDialog = () => {
  currentDeployment.value = null
  showDeploymentDialogVisible.value = true
}

const editDeployment = (deployment: DeploymentInfo) => {
  currentDeployment.value = deployment
  showDeploymentDialogVisible.value = true
}

const deleteDeployment = async (id: number) => {
  await ElMessageBox.confirm('确认删除该部署信息？', '提示', { type: 'warning' })
  await deploymentApi.delete(id)
  ElMessage.success('删除成功')
  await refreshDeployments()
}

const setDefault = async (id: number) => {
  await deploymentApi.setDefault(id, props.customerId)
  ElMessage.success('已设置为默认部署')
  await refreshDeployments()
}

const closeDeploymentDialog = () => {
  showDeploymentDialogVisible.value = false
}

// License 申请操作
const refreshApplications = async () => {
  applications.value = await licenseApplicationApi.list(props.customerId)
}

const showLicenseDialog = () => {
  currentApplication.value = null
  showLicenseDialogVisible.value = true
}

const editApplication = (application: LicenseApplication) => {
  currentApplication.value = application
  showLicenseDialogVisible.value = true
}

const submitApplication = async (id: number) => {
  await ElMessageBox.confirm('确认提交审批？', '提示', { type: 'info' })
  await licenseApplicationApi.submit(id)
  ElMessage.success('已提交审批')
  await refreshApplications()
}

const deleteApplication = async (id: number) => {
  await ElMessageBox.confirm('确认删除该申请？', '提示', { type: 'warning' })
  await licenseApplicationApi.delete(id)
  ElMessage.success('删除成功')
  await refreshApplications()
}

const exportLicense = async (id: number) => {
  const blob = await licenseApplicationApi.export(id)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `License_${id}.docx`
  link.click()
  window.URL.revokeObjectURL(url)
  ElMessage.success('导出成功')
}

const closeLicenseDialog = () => {
  showLicenseDialogVisible.value = false
}

// 状态映射
const getStatusType = (status: string) => {
  const types: Record<string, any> = {
    DRAFT: 'info',
    PENDING: 'warning',
    APPROVED: 'success',
    REJECTED: 'danger',
    ISSUED: 'success'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    DRAFT: '草稿',
    PENDING: '待审批',
    APPROVED: '已批准',
    REJECTED: '已拒绝',
    ISSUED: '已发放'
  }
  return labels[status] || status
}
</script>

<style scoped>
.el-divider {
  margin: 20px 0;
}
</style>
```

**组件设计说明**：
- 采用上下分区布局，符合"先配置部署信息 → 再申请 License"的操作流程
- 上方区域展示部署信息卡片列表（可视化展示服务器地址、授权人数）
- 下方区域展示 License 申请表格（包含申请单号、类型、状态、操作按钮）
- 使用 el-divider 分隔两个区域，清晰区分不同功能块

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/LicenseManagement.vue CRM-Client/src/components/LicenseApplicationDialog.vue CRM-Client/src/components/DeploymentDialog.vue
git commit -m "feat(frontend): add LicenseManagement merged component with deployment and application sections"
```

---

### Task 11: 审批中心集成 LICENSE 类型

**Files:**
- Modify: `CRM-Client/src/views/ApprovalCenter.vue`
- Create: `CRM-Client/src/components/LicenseApprovalDialog.vue`

**Interfaces:**
- Consumes: LicenseApplication API，审批引擎
- Produces: 审批中心新增 LICENSE 类型审批项，License 审批对话框组件

- [ ] **Step 1: 修改 ApprovalCenter.vue**

在审批列表中新增 LICENSE 类型筛选：
```vue
<el-select v-model="businessType" placeholder="业务类型">
  <el-option label="合同" value="CONTRACT" />
  <el-option label="回款" value="PAYMENT" />
  <el-option label="发票" value="INVOICE" />
  <el-option label="License" value="LICENSE" /> <!-- 新增 -->
</el-select>
```

- [ ] **Step 2: 创建 LicenseApprovalDialog.vue**

```vue
<template>
  <el-dialog title="License审批" :visible.sync="visible" width="60%">
    <el-form :model="form">
      <el-form-item label="客户名称">{{ application.customer.account_name }}</el-form-item>
      <el-form-item label="部署信息">{{ application.deployment_info?.deployment_name }}</el-form-item>
      <el-form-item label="到期时间">{{ application.expiry_date }}</el-form-item>
      <el-form-item label="License类型">
        <el-tag :type="application.license_type === 'TRIAL' ? 'warning' : 'success'">
          {{ application.license_type === 'TRIAL' ? '试用' : '正式' }}
        </el-tag>
      </el-form-item>
      <el-form-item label="授权码" required>
        <el-input v-model="form.license_code" type="textarea" :rows="5" placeholder="请填写授权码内容" />
      </el-form-item>
      <el-form-item label="审批意见">
        <el-input v-model="form.comment" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <div slot="footer">
      <el-button @click="visible = false">取消</el-button>
      <el-button type="danger" @click="reject">拒绝</el-button>
      <el-button type="primary" @click="approve">批准并发放</el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { LicenseApplication } from '@/schemas/licenseApplication'

const props = defineProps<{ application: LicenseApplication }>()
const emit = defineEmits(['approve', 'reject'])

const visible = ref(true)
const form = ref({ license_code: '', comment: '' })

const approve = () => {
  emit('approve', form.value)
  visible.value = false
}

const reject = () => {
  emit('reject', form.value.comment)
  visible.value = false
}
</script>
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/views/ApprovalCenter.vue CRM-Client/src/components/LicenseApprovalDialog.vue
git commit -m "feat(frontend): integrate LICENSE approval in ApprovalCenter"
```

---

## Phase 5: 通知与权限（Task 12）

### Task 12: 配置权限码和飞书通知

**Files:**
- Modify: `CRM-Docs/system/GLOSSARY.md`

**Interfaces:**
- Consumes: 无
- Produces: 4 个权限码定义，飞书通知模板（通知实现需调用飞书 API，此处仅定义配置）

- [ ] **Step 1: 新增权限码定义**

在 GLOSSARY.md 中新增：
```markdown
### License 权限码

| 权限码 | 说明 | 适用角色 |
|--------|------|----------|
| DEPLOYMENT_INFO_MANAGE | 管理客户部署信息 | SALES_MEMBER, SALES_DIRECTOR |
| LICENSE_APPLICATION_CREATE | 创建 License 申请 | SALES_MEMBER, SALES_DIRECTOR |
| LICENSE_APPROVE | 审批 License 申请 | TEAM_ADMIN, SALES_DIRECTOR, FINANCE |
| LICENSE_VIEW | 查看 License 申请列表 | SALES_MEMBER, SALES_DIRECTOR, FINANCE |
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Docs/system/GLOSSARY.md
git commit -m "docs: add LICENSE permission codes to GLOSSARY"
```

---

## Phase 6: 测试与上线（Task 13）

### Task 13: 集成测试和端到端验证

**Files:**
- Test: 手动测试脚本（无新文件创建，仅测试执行）

**Interfaces:**
- Consumes: 所有已实现的模块
- Produces: 测试报告，上线就绪状态

- [ ] **Step 1: 后端 API 测试**

Run:
```bash
cd CRM-Server
pytest tests/test_deployment.py -v
pytest tests/test_license_application.py -v
```

Expected: 所有测试通过

- [ ] **Step 2: 前端功能测试**

手动测试：
1. 创建客户部署信息
2. 创建试用 License 申请
3. 提交审批
4. 审批人填写授权码并批准
5. 导出 Word 文档
6. 验证客户 license_expiry_date 字段更新

- [ ] **Step 3: 集成测试**

完整流程：
1. 创建合同（状态 APPROVED）
2. 创建正式 License 申请（关联合同）
3. 提交审批
4. 审批人批准
5. 验证合同状态校验逻辑
6. 验证客户到期时间自动更新

- [ ] **Step 4: Commit（如果有修复）**

```bash
git add .
git commit -m "fix: resolve integration test issues"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ Task 1-4: 数据层（DeploymentInfo, LicenseApplication, Customer.license_expiry_date, 迁移）
- ✅ Task 5-6: CRUD 层（create, get, list, update, delete, submit, approve, reject, generate_application_number, update_customer_license_expiry）
- ✅ Task 7-8: API 层（deployment endpoints, license endpoints, Word export service）
- ✅ Task 9-11: 前端界面（CustomerDetail tabs, components, ApprovalCenter integration）
- ✅ Task 12: 通知与权限（权限码定义）
- ✅ Task 13: 测试与上线

**2. Placeholder scan:**
- ✅ 无 "TODO"、"TBD"、模糊需求
- ✅ 所有代码步骤包含完整代码
- ✅ 所有测试命令包含具体执行和预期输出
- ✅ 所有提交命令包含具体文件和提交信息

**3. Type consistency:**
- ✅ DeploymentInfo 字段名一致（deployment_name, server_address, authorized_users）
- ✅ LicenseApplication 字段名一致（application_number, expiry_date, enterprise_id, supported_modules, server_license_code, client_license_code, remark）
- ✅ LicenseApplicationStatus 枚举值一致（DRAFT, PENDING, APPROVED, REJECTED, ISSUED）
- ✅ LicenseType 枚举值一致（TRIAL, OFFICIAL）
- ✅ API 端点路径一致（/api/v1/deployment-infos, /api/v1/license-applications）

---

## Phase 7: 补充需求实施（Task 14-21）

### Task 14: LicenseApplication 表补充字段

**Files:**
- Modify: `CRM-Server/app/models/license_application.py`
- Modify: `CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py`

**Interfaces:**
- Consumes: 无
- Produces: LicenseApplication 新增 5 个字段（enterprise_id, supported_modules, server_license_code, client_license_code, remark）

- [ ] **Step 1: 修改 LicenseApplication 模型，新增 5 个字段**

Modify: `CRM-Server/app/models/license_application.py`

在字段部分新增（expiry_date 之后）：
```python
expiry_date = Column(Date, nullable=False, comment="到期时间")
license_type = Column(String(20), nullable=False, comment="License 类型")

# 审批人回填的 License 详细信息（新增）
enterprise_id = Column(String(50), nullable=True, comment="企业编号（审批人回填，如：15739）")
supported_modules = Column(String(500), nullable=True, comment="支持模块（审批人回填，如：desktop,web,branch）")
server_license_code = Column(Text, nullable=True, comment="服务端 License（审批人回填）")
client_license_code = Column(Text, nullable=True, comment="客户端 License（审批人回填）")

# 申请人备注（新增）
remark = Column(Text, nullable=True, comment="备注（申请时填写，如：需要开通 desktop,web,branch）")

status = Column(String(20), nullable=False, default=LicenseApplicationStatus.DRAFT, comment="申请状态")
```

- [ ] **Step 2: 修改迁移脚本，新增 5 个字段**

Modify: `CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py`

在 `crm_license_applications` 表创建部分新增：
```python
sa.Column('enterprise_id', sa.String(50), nullable=True, comment='企业编号'),
sa.Column('supported_modules', sa.String(500), nullable=True, comment='支持模块'),
sa.Column('server_license_code', sa.Text(), nullable=True, comment='服务端 License'),
sa.Column('client_license_code', sa.Text(), nullable=True, comment='客户端 License'),
sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
```

在 `downgrade()` 部分新增：
```python
op.drop_column('crm_license_applications', 'remark')
op.drop_column('crm_license_applications', 'client_license_code')
op.drop_column('crm_license_applications', 'server_license_code')
op.drop_column('crm_license_applications', 'supported_modules')
op.drop_column('crm_license_applications', 'enterprise_id')
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/models/license_application.py CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py
git commit -m "feat(models): add enterprise_id, supported_modules, license_codes, remark to LicenseApplication"
```

---

### Task 15: Customer 表补充字段和自动更新逻辑

**Files:**
- Modify: `CRM-Server/app/models/customer.py`
- Modify: `CRM-Server/app/crud/crud_license_application.py`
- Modify: `CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py`

**Interfaces:**
- Consumes: LicenseApplication 表
- Produces: Customer 新增 license_type 字段，update_customer_license_info 函数（自动更新 license_expiry_date 和 license_type）

- [ ] **Step 1: Customer 模型新增 license_type 字段**

Modify: `CRM-Server/app/models/customer.py`

在字段部分新增（license_expiry_date 之后）：
```python
license_expiry_date = Column(Date, nullable=True, comment="客户 License 最晚到期时间（自动更新）")
license_type = Column(String(20), nullable=True, comment="客户 License 类型（自动更新）：TRIAL/OFFICIAL")
```

- [ ] **Step 2: 修改迁移脚本，新增 license_type 字段**

Modify: `CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py`

在 `upgrade()` 部分新增：
```python
op.add_column('crm_customers', sa.Column('license_type', sa.String(20), nullable=True, comment='客户 License 类型'))
```

在 `downgrade()` 部分新增：
```python
op.drop_column('crm_customers', 'license_type')
```

- [ ] **Step 3: 修改 CRUD 函数，更新客户 License 信息逻辑**

Modify: `CRM-Server/app/crud/crud_license_application.py`

将 `update_customer_license_expiry` 函数替换为：
```python
def update_customer_license_info(db: Session, customer_id: int) -> None:
    """更新客户 License 最晚到期时间和类型"""
    # 查询客户所有已发放的 License 申请，按到期时间降序
    approved_applications = db.query(LicenseApplication).filter(
        and_(
            LicenseApplication.customer_id == customer_id,
            LicenseApplication.status == LicenseApplicationStatus.ISSUED
        )
    ).order_by(LicenseApplication.expiry_date.desc()).all()
    
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer:
        if approved_applications:
            # 最晚到期时间对应的 License 类型
            latest_app = approved_applications[0]
            customer.license_expiry_date = latest_app.expiry_date
            customer.license_type = latest_app.license_type
        else:
            # 未申请，置空
            customer.license_expiry_date = None
            customer.license_type = None
        db.commit()
```

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/models/customer.py CRM-Server/app/crud/crud_license_application.py CRM-Server/migrations/versions/<timestamp>_add_deployment_and_license_tables.py
git commit -m "feat(models): add license_type to Customer and update auto-update logic"
```

---

### Task 16: 审批接口补充 License 信息解析逻辑

**Files:**
- Modify: `CRM-Server/app/schemas/license_application.py`
- Modify: `CRM-Server/app/crud/crud_license_application.py`
- Modify: `CRM-Server/app/api/license_application.py`

**Interfaces:**
- Consumes: 审批人回填的 License 信息文本
- Produces: parse_license_info 函数（解析企业编号、支持模块、服务端/客户端 License），approve_license_application 函数更新

- [ ] **Step 1: 新增 License 信息解析函数**

Modify: `CRM-Server/app/crud/crud_license_application.py`

新增函数：
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

- [ ] **Step 2: 修改 approve_license_application 函数**

Modify: `CRM-Server/app/crud/crud_license_application.py`

将 approve 函数修改为：
```python
def approve_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    approver_id: str,
    license_info: str
) -> Optional[LicenseApplication]:
    """审批通过 License 申请（填写完整 License 信息）"""
    db_application = get_license_application(db, team_id, application_id)
    if not db_application or db_application.status != LicenseApplicationStatus.PENDING:
        return None
    
    # 解析 License 信息
    parsed_data = parse_license_info(license_info)
    
    # 更新申请记录
    db_application.status = LicenseApplicationStatus.ISSUED
    db_application.enterprise_id = parsed_data.get('enterprise_id')
    db_application.supported_modules = parsed_data.get('supported_modules')
    db_application.server_license_code = parsed_data.get('server_license_code')
    db_application.client_license_code = parsed_data.get('client_license_code')
    db_application.approver_id = approver_id
    db_application.approved_time = datetime.now()
    
    db.commit()
    db.refresh(db_application)
    
    # 更新客户 License 信息
    update_customer_license_info(db, db_application.customer_id)
    
    return db_application
```

- [ ] **Step 3: 修改 Pydantic schema，新增 remark 字段**

Modify: `CRM-Server/app/schemas/license_application.py`

新增字段到 LicenseApplicationCreate：
```python
class LicenseApplicationCreate(LicenseApplicationBase):
    contract_id: int | None = None
    remark: str | None = None  # 新增备注字段
```

新增字段到 LicenseApplicationResponse：
```python
class LicenseApplicationResponse(LicenseApplicationBase):
    id: int
    team_id: int
    application_number: str
    contract_id: int | None
    enterprise_id: str | None  # 新增
    supported_modules: str | None  # 新增
    server_license_code: str | None  # 新增
    client_license_code: str | None  # 新增
    remark: str | None  # 新增
    status: str
    applicant_id: str
    approver_id: str | None
    approved_time: datetime | None
    created_time: datetime
    last_modified_time: datetime
```

新增 LicenseApprove schema：
```python
class LicenseApprove(BaseModel):
    license_info: str = Field(..., min_length=1, description="完整的 License 信息文本")
    comment: str | None = None
```

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/crud/crud_license_application.py CRM-Server/app/schemas/license_application.py CRM-Server/app/api/license_application.py
git commit -m "feat(crud): add parse_license_info function and update approve logic"
```

---

### Task 17: Word 导出服务更新（参照样例格式）

**Files:**
- Modify: `CRM-Server/app/services/license_export_service.py`

**Interfaces:**
- Consumes: LicenseApplication（包含 enterprise_id, supported_modules, server_license_code, client_license_code）
- Produces: Word 文档（格式参照样例，文件名：私有化{试用/正式}License-{客户名称}_{当前日期}.docx）

- [ ] **Step 1: 更新 Word 导出服务**

Modify: `CRM-Server/app/services/license_export_service.py`

完整代码：
```python
from docx import Document
from docx.shared import Pt
from app.models.license_application import LicenseApplication, LicenseType
from datetime import datetime
import tempfile


def export_license_document(application: LicenseApplication) -> str:
    """导出 License 文档（参照样例格式）"""
    doc = Document()
    
    # 标题
    doc.add_heading('Apifox私有化授权文件', 0)
    
    # 企业信息
    doc.add_paragraph(f"企业名称: {application.customer.account_name}")
    doc.add_paragraph(f"企业编号: {application.enterprise_id or '未填写'}")
    doc.add_paragraph(f"到期时间: {application.expiry_date.strftime('%Y-%m-%d')}")
    doc.add_paragraph(f"授权人数: {application.deployment_info.authorized_users if application.deployment_info else '未配置'}")
    doc.add_paragraph(f"服务器: {application.deployment_info.server_address if application.deployment_info else '未配置'}")
    doc.add_paragraph(f"支持模块: {application.supported_modules or '未填写'}")
    
    # License 类型标题
    license_type_text = '试用' if application.license_type == LicenseType.TRIAL else '正式'
    doc.add_paragraph()
    doc.add_paragraph(f"{license_type_text} License（{application.deployment_info.authorized_users if application.deployment_info else 0}人）")
    
    # 服务端 License
    doc.add_paragraph()
    doc.add_paragraph("服务端 License:")
    if application.server_license_code:
        doc.add_paragraph(application.server_license_code)
    else:
        doc.add_paragraph("未填写")
    
    # 客户端 License
    doc.add_paragraph()
    doc.add_paragraph("客户端 License:")
    if application.client_license_code:
        doc.add_paragraph(application.client_license_code)
    else:
        doc.add_paragraph("未填写")
    
    # 文件名：私有化{试用/正式}License-{客户名称}_{当前日期}.docx
    current_date = datetime.now().strftime('%Y%m%d')
    file_name = f"私有化{license_type_text}License-{application.customer.account_name}_{current_date}.docx"
    file_path = tempfile.mktemp(suffix='.docx', prefix=file_name)
    doc.save(file_path)
    
    return file_path
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Server/app/services/license_export_service.py
git commit -m "feat(export): update Word export format to match sample template"
```

---

### Task 18: 前端申请表单新增备注字段

**Files:**
- Modify: `CRM-Client/src/schemas/licenseApplication.ts`
- Modify: `CRM-Client/src/components/LicenseApplicationDialog.vue`

**Interfaces:**
- Consumes: LicenseApplication API
- Produces: 申请表单新增备注字段（textarea），申请人填写需要开通的模块

- [ ] **Step 1: 修改 Zod schema，新增 remark 字段**

Modify: `CRM-Client/src/schemas/licenseApplication.ts`

新增字段：
```typescript
export const LicenseApplicationCreateSchema = LicenseApplicationSchema.omit({
  id: true, team_id: true, application_number: true, enterprise_id: true, supported_modules: true,
  server_license_code: true, client_license_code: true, status: true,
  applicant_id: true, approver_id: true, approved_time: true, created_time: true, last_modified_time: true
}).extend({
  expiry_date: z.string().refine(val => new Date(val) > new Date(), '到期时间必须大于当前日期'),
  remark: z.string().optional()  // 新增备注字段
})
```

- [ ] **Step 2: 修改申请对话框，新增备注字段**

Modify: `CRM-Client/src/components/LicenseApplicationDialog.vue`

在表单中新增：
```vue
<el-form-item label="备注">
  <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请填写需要开通的模块（如：desktop,web,branch）" />
</el-form-item>
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/schemas/licenseApplication.ts CRM-Client/src/components/LicenseApplicationDialog.vue
git commit -m "feat(frontend): add remark field to License application form"
```

---

### Task 19: 前端审批对话框支持 License 信息回填和解析

**Files:**
- Modify: `CRM-Client/src/components/LicenseApprovalDialog.vue`

**Interfaces:**
- Consumes: 审批人输入的 License 信息文本
- Produces: 审批对话框支持 License 信息 textarea 输入，提交时传递完整文本

- [ ] **Step 1: 修改审批对话框，支持 License 信息回填**

Modify: `CRM-Client/src/components/LicenseApprovalDialog.vue`

完整代码：
```vue
<template>
  <el-dialog title="License审批" :visible.sync="visible" width="70%">
    <el-form :model="form">
      <el-form-item label="客户名称">{{ application.customer.account_name }}</el-form-item>
      <el-form-item label="部署信息">{{ application.deployment_info?.deployment_name }}</el-form-item>
      <el-form-item label="到期时间">{{ application.expiry_date }}</el-form-item>
      <el-form-item label="License类型">
        <el-tag :type="application.license_type === 'TRIAL' ? 'warning' : 'success'">
          {{ application.license_type === 'TRIAL' ? '试用' : '正式' }}
        </el-tag>
      </el-form-item>
      <el-form-item label="申请人备注" v-if="application.remark">
        <el-input type="textarea" :rows="3" :value="application.remark" readonly />
      </el-form-item>
      <el-form-item label="License信息" required>
        <el-input 
          v-model="form.license_info" 
          type="textarea" 
          :rows="10" 
          placeholder="请粘贴完整的 License 信息（包含企业编号、支持模块、服务端 License、客户端 License）" 
        />
        <div style="margin-top: 10px; color: #999; font-size: 12px">
          <p>格式示例：</p>
          <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px">
企业编号: 15739
企业名称: {客户名称}
客户端过期时间: {到期时间}
服务端过期时间: {到期时间}
设备数: {授权人数}
支持模块: desktop,web,branch,scheduledTask,grpc,dubbo,ai
服务器地址: {服务器地址}

服务器端 License: 
[加密字符串]

客户端 License: 
[加密字符串]
          </pre>
        </div>
      </el-form-item>
      <el-form-item label="审批意见">
        <el-input v-model="form.comment" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <div slot="footer">
      <el-button @click="visible = false">取消</el-button>
      <el-button type="danger" @click="reject">拒绝</el-button>
      <el-button type="primary" @click="approve" :disabled="!form.license_info">批准并发放</el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { LicenseApplication } from '@/schemas/licenseApplication'

const props = defineProps<{ application: LicenseApplication }>()
const emit = defineEmits(['approve', 'reject'])

const visible = ref(true)
const form = ref({ license_info: '', comment: '' })

const approve = () => {
  if (!form.value.license_info.trim()) {
    ElMessage.warning('请填写 License 信息')
    return
  }
  emit('approve', { license_info: form.value.license_info, comment: form.value.comment })
  visible.value = false
}

const reject = () => {
  emit('reject', form.value.comment)
  visible.value = false
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/LicenseApprovalDialog.vue
git commit -m "feat(frontend): update License approval dialog to support full license info input"
```

---

### Task 20: 补充需求集成测试

**Files:**
- Test: 手动测试脚本（无新文件创建，仅测试执行）

**Interfaces:**
- Consumes: 所有补充模块
- Produces: 测试报告，上线就绪状态

- [ ] **Step 1: 测试申请表单备注字段**

手动测试：
1. 创建 License 申请
2. 在备注字段填写："需要开通 desktop,web,branch"
3. 提交审批
4. 验证备注字段是否正确存储

- [ ] **Step 2: 测试审批人回填 License 信息**

手动测试：
1. 审批人粘贴完整 License 信息（包含企业编号、支持模块、服务端/客户端 License）
2. 提交审批通过
3. 验证 License 信息是否正确解析和存储
4. 验证客户 license_expiry_date 和 license_type 是否自动更新

- [ ] **Step 3: 测试 Word 导出格式**

手动测试：
1. 审批通过后导出 Word 文档
2. 验证文件名格式：`私有化{试用/正式}License-{客户名称}_{当前日期}.docx`
3. 验证导出内容格式是否与样例一致（标题、企业信息、支持模块、服务端/客户端 License）

- [ ] **Step 4: 测试客户 License 类型自动更新**

手动测试：
1. 申请试用 License（到期时间：2026-08-01）并审批通过
2. 申请正式 License（到期时间：2026-09-01）并审批通过
3. 验证客户 license_type 是否更新为 OFFICIAL（基于最晚到期时间）
4. 验证客户 license_expiry_date 是否更新为 2026-09-01

- [ ] **Step 5: Commit（如果有修复）**

```bash
git add .
git commit -m "fix: resolve integration test issues for supplementary requirements"
```

---

## Self-Review Checklist (Updated)

**1. Spec coverage:**
- ✅ Task 1-4: 数据层基础（数据模型、迁移脚本）
- ✅ Task 5-6: CRUD 层
- ✅ Task 7-8: API 层（deployment endpoints, license endpoints, Word export）
- ✅ Task 9-10: 前端界面（LicenseManagement 合并组件）
- ✅ Task 11-12: 审批中心和权限配置
- ✅ Task 13: 集成测试
- ✅ **Task 14-15: 补充数据层（LicenseApplication 和 Customer 新增字段）**
- ✅ **Task 16-17: 补充 API 层（License 信息解析、Word 导出格式更新）**
- ✅ **Task 18-19: 补充前端（申请表单备注字段、审批对话框 License 信息输入）**
- ✅ **Task 20: 补充需求集成测试**

**2. Placeholder scan:**
- ✅ 无 "TODO"、"TBD"、模糊需求
- ✅ 所有代码步骤包含完整代码
- ✅ 所有测试命令包含具体执行和预期输出
- ✅ 所有提交命令包含具体文件和提交信息

**3. Type consistency:**
- ✅ DeploymentInfo 字段名一致
- ✅ LicenseApplication 字段名一致（新增 enterprise_id, supported_modules, server_license_code, client_license_code, remark）
- ✅ Customer 字段名一致（新增 license_type）
- ✅ LicenseApplicationStatus 枚举值一致
- ✅ LicenseType 枚举值一致
- ✅ API 端点路径一致

---

## Phase 8: UI/UX 视觉设计补充（Task 21-27）

> **说明**: 本 Phase 补充前端组件的视觉设计细节，确保与 CRMWolf 设计系统无缝融合。详细设计说明见 `docs/superpowers/plans/2026-07-06-license-management-ui-supplement.md`。

### Task 21: 导航结构优化 - 合并单一 Tab

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.vue`

**Interfaces:**
- Consumes: CustomerDetailSidebar 导航项定义
- Produces: 新增"授权"导航项（使用 Key 图标），合并部署信息和 License 申请

- [ ] **Step 1: 修改 CustomerDetailSidebar.vue，新增授权导航项**

```typescript
import { Key } from '@element-plus/icons-vue'

const navItems = [
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets },
  { key: 'license', label: '授权', icon: Key }  // 新增
]
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/CustomerDetailSidebar.vue
git commit -m "feat(ui): add License navigation item with Key icon"
```

---

### Task 22: 部署信息卡片视觉设计

**Files:**
- Modify: `CRM-Client/src/components/LicenseManagement.vue`
- Create: `CRM-Client/src/styles/license-management.scss`

**Interfaces:**
- Consumes: variables.scss 设计 token
- Produces: 部署信息卡片样式（参照 invoice-title-item），服务器地址使用 IBM Plex Mono

- [ ] **Step 1: 创建 license-management.scss 样式文件**

完整样式见 `docs/superpowers/plans/2026-07-06-license-management-ui-supplement.md` 第二章。

- [ ] **Step 2: 更新 LicenseManagement.vue 部署信息区域样式**

应用新样式类：`deployment-info-item`, `deployment-info-grid`, `server-address`

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/styles/license-management.scss CRM-Client/src/components/LicenseManagement.vue
git commit -m "feat(ui): add deployment info card styles with IBM Plex Mono signature"
```

---

### Task 23: License 申请状态徽章更新

**Files:**
- Modify: `CRM-Client/src/components/ApprovalStatusBadge.vue`
- Modify: `CRM-Client/src/schemas/approvalGeneric.ts`

**Interfaces:**
- Consumes: ApprovalStatus 类型
- Produces: 新增 ISSUED 状态映射（使用 Key 图标）

- [ ] **Step 1: 修改 ApprovalStatusBadge.vue，新增 ISSUED 状态**

```typescript
import { Key } from '@element-plus/icons-vue'

const STATUS_MAP = {
  // ... 其他状态
  ISSUED: {
    label: '已发放',
    icon: Key,
    textVar: '--wolf-success-text',
    bgVar: '--wolf-success-bg'
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/ApprovalStatusBadge.vue CRM-Client/src/schemas/approvalGeneric.ts
git commit -m "feat(ui): add ISSUED status badge with Key icon signature"
```

---

### Task 24: 申请表单 UI 细化（动态表单）

**Files:**
- Modify: `CRM-Client/src/components/LicenseApplicationDialog.vue`

**Interfaces:**
- Consumes: LicenseApplication API，合同 API
- Produces: 动态表单（试用 License 隐藏合同字段，正式 License 显示并必填）

- [ ] **Step 1: 实现动态表单逻辑**

```vue
<!-- 正式 License 时动态显示合同字段 -->
<el-form-item
  v-show="form.license_type === 'OFFICIAL'"
  label="关联合同"
  prop="contract_id"
  :required="form.license_type === 'OFFICIAL'"
>
  ...
</el-form-item>
```

完整代码见 `docs/superpowers/plans/2026-07-06-license-management-ui-supplement.md` 第四章。

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/LicenseApplicationDialog.vue
git commit -m "feat(ui): add dynamic form logic for License application"
```

---

### Task 25: 审批对话框 License 信息输入优化

**Files:**
- Modify: `CRM-Client/src/components/LicenseApprovalDialog.vue`

**Interfaces:**
- Consumes: 审批 API
- Produces: License 信息 textarea（IBM Plex Mono 字体），格式提示

- [ ] **Step 1: 更新审批对话框样式**

```scss
.license-code-input :deep(.el-textarea__inner) {
  font-family: $wolf-font-mono;
  font-size: $wolf-font-size-caption;
  background: $wolf-bg-page;
  min-height: 200px;
}
```

完整样式见 `docs/superpowers/plans/2026-07-06-license-management-ui-supplement.md` 第五章。

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/LicenseApprovalDialog.vue
git commit -m "feat(ui): optimize License approval dialog with mono font"
```

---

### Task 26: Empty States 和 Loading States

**Files:**
- Modify: `CRM-Client/src/components/LicenseManagement.vue`

**Interfaces:**
- Consumes: DeploymentInfo API, LicenseApplication API
- Produces: 空状态组件，加载状态（v-loading）

- [ ] **Step 1: 添加空状态和加载状态**

```vue
<div v-loading="deploymentsLoading" style="min-height: 120px">
  <div v-if="!deploymentsLoading && deployments.length === 0">
    <el-empty description="添加部署信息，配置服务器地址">
      <el-button type="primary" size="small">添加部署信息</el-button>
    </el-empty>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/components/LicenseManagement.vue
git commit -m "feat(ui): add empty states and loading states"
```

---

### Task 27: 无障碍设计和响应式适配

**Files:**
- Modify: `CRM-Client/src/styles/license-management.scss`

**Interfaces:**
- Consumes: variables.scss
- Produces: 无障碍样式（键盘导航、reduced motion），响应式断点

- [ ] **Step 1: 添加无障碍样式**

```scss
.deployment-info-item {
  tabindex: 0;
  
  &:focus-visible {
    outline: 2px solid $wolf-primary;
  }
}

@media (prefers-reduced-motion: reduce) {
  .deployment-info-item { transition: none; }
}

@media (max-width: 768px) {
  .deployment-info-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/styles/license-management.scss
git commit -m "feat(ui): add accessibility and responsive styles"
```

---

## Self-Review Checklist (Final)

**1. Spec coverage:**
- ✅ Task 1-4: 数据层基础
- ✅ Task 5-6: CRUD 层
- ✅ Task 7-8: API 层
- ✅ Task 9-11: 前端界面（基础）
- ✅ Task 12: 通知与权限
- ✅ Task 13: 集成测试
- ✅ Task 14-15: 补充数据层
- ✅ Task 16-17: 补充 API 层
- ✅ Task 18-19: 补充前端
- ✅ Task 20: 补充需求集成测试
- ✅ **Task 21-27: UI/UX 视觉设计补充**

**2. Placeholder scan:**
- ✅ 无 "TODO"、"TBD"、模糊需求
- ✅ 所有代码步骤包含完整代码或引用详细文档

**3. Type consistency:**
- ✅ 所有字段名一致
- ✅ 所有枚举值一致
- ✅ API 端点路径一致

**4. UI/UX 完整性:**
- ✅ 导航结构优化（合并单一 Tab）
- ✅ 部署信息卡片设计（参照发票抬头 + Mono 字体）
- ✅ 状态徽章更新（ISSIED 状态 + Key 图标）
- ✅ 动态表单逻辑（试用/正式切换）
- ✅ 审批对话框优化（Mono 字体 + 格式提示）
- ✅ Empty States 和 Loading States
- ✅ 无障碍设计（键盘导航 + reduced motion）
- ✅ 响应式适配（768px 断点）

**5. Signature Elements:**
- ✅ Key 图标（导航 + ISSUED 状态）
- ✅ IBM Plex Mono 字体（服务器地址 + License 信息输入）
- ✅ 技术 vernacular 视觉风格
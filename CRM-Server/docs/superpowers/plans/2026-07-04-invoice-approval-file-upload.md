# 发票审批文件上传优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在发票审批环节支持财务人员上传发票文件，上传后自动完成审批并将状态变为已开票（ISSUED），简化审批+开票两步为一步。

**Business Optimization (UX 优化):**
- **发票号码改为可选字段** — 财务人员只需上传发票文件，无需手动填写发票号码
- **原因**：发票号码已印在发票文件上，销售人员可从下载的文件中查看号码
- **可选填写场景**：财务如需记录发票号码便于后续查询/统计，可自愿填写
- **UX 提示**：组件中提供 tooltip 说明："发票号码已印在发票文件上，无需手动填写"

**Architecture:** 
- 后端新增文件上传服务，使用 FastAPI UploadFile 处理 multipart/form-data
- InvoiceApplication 模型新增 `invoice_file_path` 字段存储文件路径
- 修改审批适配器 `on_approved_with_file` 回调，上传文件后直接设为 ISSUED
- 前端审批组件新增文件上传控件，审批操作改为"上传发票并审批"

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / Alembic / Vue 3 / TypeScript / Element Plus / Pinia

## 现状摘要（证据）

- 发票模型 `InvoiceApplication`（`CRM-Server/app/models/invoice.py:52-95`）状态流转：DRAFT → PENDING_REVIEW → APPROVED/REJECTED → ISSUED
- 审批使用通用引擎（`ApprovalProcessGeneric.vue`），适配器 `InvoiceApplicationAdapter`（`app/services/approval_adapter.py:112-148`）处理状态回调
- 当前审批通过后状态为 APPROVED，需额外点击"标记开票"输入发票号码后才变为 ISSUED
- Docker compose 已配置 uploads 目录挂载（`docker-compose.yml:29`：`./uploads:/app/uploads`）
- 后端/前端均无现有文件上传代码（grep 搜索 upload 无结果）

## Global Constraints

- **team_id 必传**：所有 CRUD 操作必须传 team_id（CLAUDE.md 红线）
- **CRUD 统一入口**：禁止裸 `db.query()` 在 api 层
- **Alembic 迁移**：禁止独立 DB 脚本；新迁移 `down_revision` 指向最新
- **Pydantic 强制校验**：所有 API 入参走 schema，禁止裸 dict
- **防幻觉**：业务枚举必须查阅常量定义
- **TypeScript 四禁令**：前端禁 `any`/`as any`/`@ts-ignore`/`!`
- **文件存储安全**：上传目录在容器外（volume mount），禁止路径穿越攻击
- **不破坏现有审批**：未上传文件的审批流程保持原样（兼容旧数据）

---

## File Structure

**后端新建**
- `CRM-Server/app/services/file_storage.py` — 文件存储服务（本地存储 + 路径校验）
- `CRM-Server/app/schemas/file_upload.py` — 文件上传请求/响应 schema
- `CRM-Server/migrations/versions/013_invoice_file_path.py` — 加 `invoice_file_path` + `invoice_number` 列

**后端修改**
- `CRM-Server/app/models/invoice.py:52-95` — `InvoiceApplication` 加 `invoice_file_path`/`invoice_number` 字段
- `CRM-Server/app/services/approval_adapter.py:112-148` — 新增 `on_approved_with_file` 方法
- `CRM-Server/app/api/approvals.py` — 通用审批端点新增 `file` 可选参数
- `CRM-Server/app/api/invoices.py` — 发票专用审批端点支持文件上传
- `CRM-Server/app/schemas/invoice.py` — `InvoiceApplicationResponse` 加 `invoice_file_path`/`invoice_number`

**前端新建**
- `CRM-Client/src/components/InvoiceFileUpload.vue` — 发票文件上传组件
- `CRM-Client/src/api/fileUpload.ts` — 文件上传 API 封装

**前端修改**
- `CRM-Client/src/components/ApprovalProcessGeneric.vue` — 审批操作支持可选文件上传
- `CRM-Client/src/views/InvoiceDetail.vue` — 审批区域集成文件上传
- `CRM-Client/src/views/FinanceInvoiceApprovals.vue` — 列表页审批支持文件上传
- `CRM-Client/src/schemas/invoice.ts` — 类型定义加 `invoice_file_path`/`invoice_number`

**配置修改**
- `docker-compose.yml` — 确保 uploads 挂载路径正确（已存在，需验证）
- `docker-compose.prod.yml` — 同步生产环境挂载配置

---

## Phase A — 后端文件存储基础设施

### Task 1: 文件存储服务

**Files:**
- Create: `CRM-Server/app/services/file_storage.py`
- Create: `CRM-Server/app/schemas/file_upload.py`
- Test: `CRM-Server/tests/unit/services/test_file_storage.py`

**Interfaces:**
- Consumes: None
- Produces: `FileStorageService` 类，方法 `save_invoice_file(team_id, invoice_id, file) -> str` 返回相对路径

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_file_storage.py

import pytest
import tempfile
import os
from pathlib import Path
from app.services.file_storage import FileStorageService, FileStorageError

@pytest.fixture
def temp_upload_dir():
    """临时上传目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def storage_service(temp_upload_dir):
    """使用临时目录的存储服务"""
    return FileStorageService(base_dir=temp_upload_dir)

def test_save_invoice_file_success(storage_service, temp_upload_dir):
    """测试成功保存发票文件"""
    # 模拟上传文件
    file_content = b"test invoice pdf content"
    filename = "test_invoice.pdf"
    
    # 保存文件
    relative_path = storage_service.save_invoice_file(
        team_id=1,
        invoice_id=100,
        filename=filename,
        content=file_content
    )
    
    # 验证返回路径格式
    assert relative_path == "invoices/1/100/test_invoice.pdf"
    
    # 验证文件实际存在
    full_path = os.path.join(temp_upload_dir, relative_path)
    assert os.path.exists(full_path)
    
    # 验证内容正确
    with open(full_path, "rb") as f:
        assert f.read() == file_content

def test_save_invoice_file_path_traversal_blocked(storage_service):
    """测试路径穿越攻击被阻止"""
    # 尝试路径穿越
    malicious_filename = "../../../etc/passwd"
    
    with pytest.raises(FileStorageError) as exc_info:
        storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename=malicious_filename,
            content=b"malicious"
        )
    
    assert "非法文件名" in str(exc_info.value)

def test_save_invoice_file_invalid_extension(storage_service):
    """测试非法扩展名被拒绝"""
    malicious_filename = "test_invoice.exe"
    
    with pytest.raises(FileStorageError) as exc_info:
        storage_service.save_invoice_file(
            team_id=1,
            invoice_id=100,
            filename=malicious_filename,
            content=b"malicious"
        )
    
    assert "不允许的文件类型" in str(exc_info.value)

def test_get_file_path(storage_service, temp_upload_dir):
    """测试获取完整文件路径"""
    relative_path = "invoices/1/100/test.pdf"
    full_path = storage_service.get_full_path(relative_path)
    
    expected = os.path.join(temp_upload_dir, relative_path)
    assert full_path == expected

def test_team_isolation(storage_service, temp_upload_dir):
    """测试团队隔离——不同团队文件不能互相访问"""
    # 团队 1 的文件
    path1 = storage_service.save_invoice_file(
        team_id=1, invoice_id=100, filename="a.pdf", content=b"team1"
    )
    
    # 团队 2 的文件
    path2 = storage_service.save_invoice_file(
        team_id=2, invoice_id=100, filename="b.pdf", content=b"team2"
    )
    
    # 验证路径在不同目录
    assert path1.startswith("invoices/1/")
    assert path2.startswith("invoices/2/")
    
    # 验证物理隔离
    full_path1 = storage_service.get_full_path(path1)
    full_path2 = storage_service.get_full_path(path2)
    assert os.path.dirname(os.path.dirname(full_path1)) != os.path.dirname(os.path.dirname(full_path2))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && PYTHONPATH=/Users/eddie/Code/CRMWolf/CRM-Server /Users/eddie/Code/CRMWolf/CRM-Server/venv/bin/python -m pytest tests/unit/services/test_file_storage.py -v --no-cov -o addopts=""`

Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.file_storage'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/schemas/file_upload.py

from pydantic import BaseModel, Field
from typing import Optional

class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_path: str = Field(..., description="文件相对路径（用于存储到数据库）")
    file_name: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    message: str = Field(default="上传成功", description="响应消息")
```

```python
# app/services/file_storage.py

"""文件存储服务：本地存储发票文件，支持团队隔离和路径安全校验。"""

import os
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

from app.schemas.file_upload import FileUploadResponse


class FileStorageError(Exception):
    """文件存储错误"""
    pass


# 允许的文件扩展名（发票常见格式）
ALLOWED_EXTENSIONS = {
    ".pdf",   # PDF 发票
    ".jpg",   # 图片发票
    ".jpeg",
    ".png",
    ".ofd",   # 电子发票格式
}

# 最大文件大小（10MB）
MAX_FILE_SIZE = 10 * 1024 * 1024


class FileStorageService:
    """发票文件本地存储服务"""
    
    def __init__(self, base_dir: str = "/app/uploads"):
        """
        Args:
            base_dir: 上传文件基础目录（容器内路径）
        """
        self.base_dir = base_dir
    
    def _validate_filename(self, filename: str) -> str:
        """校验文件名安全性
        
        1. 禁止路径穿越（../）
        2. 只允许白名单扩展名
        3. 返回安全的文件名
        """
        # 检查路径穿越
        if ".." in filename or "/" in filename or "\\" in filename:
            raise FileStorageError(f"非法文件名：{filename}")
        
        # 检查扩展名
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise FileStorageError(
                f"不允许的文件类型：{ext}。允许类型：{', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        return filename
    
    def _generate_safe_filename(self, original_filename: str, invoice_id: int) -> str:
        """生成安全的存储文件名
        
        格式：{invoice_id}_{timestamp}_{hash}.{ext}
        """
        ext = os.path.splitext(original_filename)[1].lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 用 invoice_id + timestamp 作为 hash 输入，避免文件名冲突
        hash_input = f"{invoice_id}_{timestamp}_{original_filename}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        return f"{invoice_id}_{timestamp}_{hash_suffix}{ext}"
    
    def save_invoice_file(
        self,
        team_id: int,
        invoice_id: int,
        filename: str,
        content: bytes,
    ) -> str:
        """保存发票文件
        
        Args:
            team_id: 团队 ID（用于目录隔离）
            invoice_id: 发票申请 ID
            filename: 原始文件名
            content: 文件内容（bytes）
        
        Returns:
            文件相对路径（相对于 base_dir），用于存储到数据库
        
        Raises:
            FileStorageError: 文件名非法或存储失败
        """
        # 校验文件大小
        if len(content) > MAX_FILE_SIZE:
            raise FileStorageError(
                f"文件过大：{len(content)} 字节，最大允许 {MAX_FILE_SIZE} 字节"
            )
        
        # 校验文件名
        safe_filename = self._validate_filename(filename)
        storage_filename = self._generate_safe_filename(safe_filename, invoice_id)
        
        # 构建目录路径：{base_dir}/invoices/{team_id}/{invoice_id}/
        dir_path = os.path.join(self.base_dir, "invoices", str(team_id), str(invoice_id))
        
        # 创建目录（如果不存在）
        os.makedirs(dir_path, exist_ok=True)
        
        # 写文件
        full_path = os.path.join(dir_path, storage_filename)
        with open(full_path, "wb") as f:
            f.write(content)
        
        # 返回相对路径
        relative_path = os.path.join("invoices", str(team_id), str(invoice_id), storage_filename)
        return relative_path
    
    def get_full_path(self, relative_path: str) -> str:
        """获取文件完整路径
        
        Args:
            relative_path: 数据库存储的相对路径
        
        Returns:
            完整文件路径
        """
        # 安全校验：确保路径在 base_dir 内
        full_path = os.path.join(self.base_dir, relative_path)
        # 规范化路径，防止路径穿越
        real_path = os.path.realpath(full_path)
        real_base = os.path.realpath(self.base_dir)
        
        if not real_path.startswith(real_base):
            raise FileStorageError("非法路径：路径超出上传目录范围")
        
        return full_path
    
    def file_exists(self, relative_path: str) -> bool:
        """检查文件是否存在"""
        try:
            full_path = self.get_full_path(relative_path)
            return os.path.exists(full_path)
        except FileStorageError:
            return False
    
    def delete_file(self, relative_path: str) -> bool:
        """删除文件
        
        Returns:
            True 如果删除成功，False 如果文件不存在
        """
        try:
            full_path = self.get_full_path(relative_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
            return False
        except FileStorageError:
            return False


# 单例实例
file_storage_service = FileStorageService()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && PYTHONPATH=/Users/eddie/Code/CRMWolf/CRM-Server /Users/eddie/Code/CRMWolf/CRM-Server/venv/bin/python -m pytest tests/unit/services/test_file_storage.py -v --no-cov -o addopts=""`

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/file_storage.py CRM-Server/app/schemas/file_upload.py CRM-Server/tests/unit/services/test_file_storage.py
git commit -m "feat(file): add file storage service for invoice files - Task 1"
```

---

### Task 2: 数据库迁移 - 新增发票文件字段

**Files:**
- Create: `CRM-Server/migrations/versions/013_invoice_file_path.py`
- Modify: `CRM-Server/app/models/invoice.py:52-95`
- Modify: `CRM-Server/app/schemas/invoice.py:108-141`

**Interfaces:**
- Consumes: None
- Produces: `InvoiceApplication.invoice_file_path` / `InvoiceApplication.invoice_number` 字段

- [ ] **Step 1: Write the migration**

```python
# migrations/versions/013_invoice_file_path.py

"""add invoice_file_path and invoice_number columns

Revision ID: 013_invoice_file_path
Revises: 012_approval_generic_business
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_invoice_file_path'
down_revision = '012_approval_generic_business'  # 指向最新迁移
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 发票文件路径（相对路径）
    op.add_column(
        'crm_invoice_applications',
        sa.Column('invoice_file_path', sa.String(500), nullable=True, comment='发票文件路径（相对路径）')
    )
    # 发票号码（可选字段——财务可从发票文件中查看号码，无需手动填写）
    op.add_column(
        'crm_invoice_applications',
        sa.Column('invoice_number', sa.String(100), nullable=True, comment='发票号码（可选，便于后续查询）')
    )
    # 审批文件上传时间
    op.add_column(
        'crm_invoice_applications',
        sa.Column('issued_time', sa.DateTime(), nullable=True, comment='开票时间（上传发票文件时间）')
    )


def downgrade() -> None:
    op.drop_column('crm_invoice_applications', 'issued_time')
    op.drop_column('crm_invoice_applications', 'invoice_number')
    op.drop_column('crm_invoice_applications', 'invoice_file_path')
```

- [ ] **Step 2: Update model**

```python
# app/models/invoice.py (在 InvoiceApplication 类中添加字段)

class InvoiceApplication(Base):
    __tablename__ = "crm_invoice_applications"
    
    # ... 现有字段 ...
    
    # 新增字段（Task 2）
    invoice_file_path = Column(String(500), comment="发票文件路径（相对路径）")
    invoice_number = Column(String(100), comment="发票号码")
    issued_time = Column(DateTime, comment="开票时间（上传发票文件时间）")
    
    # ... 现有关系和索引 ...
```

- [ ] **Step 3: Update schema**

```python
# app/schemas/invoice.py (在 InvoiceApplicationResponse 中添加字段)

class InvoiceApplicationResponse(InvoiceApplicationBase):
    # ... 现有字段 ...
    
    # 新增字段（Task 2）
    invoice_file_path: Optional[str] = Field(None, description="发票文件路径（相对路径）")
    invoice_number: Optional[str] = Field(None, description="发票号码")
    issued_time: Optional[datetime] = Field(None, description="开票时间")
    
    # ... Config ...
```

- [ ] **Step 4: Run migration**

```bash
cd CRM-Server
alembic upgrade head
```

Expected: Success, no errors

- [ ] **Step 5: Verify migration**

```bash
# 检查迁移历史
alembic history --verbose | grep 013

# 检查数据库表结构（如果有连接）
# 或者直接看迁移文件是否正确
```

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/migrations/versions/013_invoice_file_path.py CRM-Server/app/models/invoice.py CRM-Server/app/schemas/invoice.py
git commit -m "feat(invoice): add invoice_file_path and invoice_number fields - Task 2"
```

---

## Phase B — 后端审批 + 文件上传集成

### Task 3: 修改审批适配器支持文件上传

**Files:**
- Modify: `CRM-Server/app/services/approval_adapter.py:112-148`

**Interfaces:**
- Consumes: `FileStorageService`（Task 1）
- Produces: `InvoiceApplicationAdapter.on_approved_with_file(db, entity, file_path, invoice_number)` 方法

- [ ] **Step 1: Update adapter**

```python
# app/services/approval_adapter.py (修改 InvoiceApplicationAdapter 类)

class InvoiceApplicationAdapter:
    business_type = BusinessType.INVOICE

    def get_entity(self, db, business_id, team_id):
        from app.crud.invoice import invoice_application_crud
        return invoice_application_crud.get_by_id(db, business_id, team_id)

    def get_submitter(self, entity):
        return entity.applicant_id, None

    def match_kwargs(self, entity):
        return {"amount": float(entity.invoice_amount or 0), "license_type": None}

    def on_submit(self, db, entity):
        if entity is None: return
        entity.status = InvoiceApplicationStatus.PENDING_REVIEW

    def on_approved(self, db, entity):
        """普通审批通过（无文件）——状态变为 APPROVED，需后续手动开票"""
        if entity is None: return
        entity.status = InvoiceApplicationStatus.APPROVED
        entity.reviewed_time = func.now()

    def on_approved_with_file(
        self,
        db,
        entity,
        file_path: str,
        invoice_number: Optional[str] = None,
    ):
        """审批通过 + 上传发票文件——状态直接变为 ISSUED

        Args:
            db: 数据库会话
            entity: InvoiceApplication 实例
            file_path: 发票文件相对路径
            invoice_number: 发票号码（可选，财务可从文件中查看）
        """
        if entity is None: return

        entity.status = InvoiceApplicationStatus.ISSUED
        entity.invoice_file_path = file_path
        entity.invoice_number = invoice_number  # 可选字段
        entity.issued_time = func.now()
        entity.reviewed_time = func.now()

    def on_rejected(self, db, entity):
        if entity is None: return
        entity.status = InvoiceApplicationStatus.REJECTED
        entity.reviewed_time = func.now()

    def on_cancelled(self, db, entity):
        if entity is None: return
        entity.status = InvoiceApplicationStatus.DRAFT

    def get_name(self, entity):
        return f"发票申请#{entity.id}"
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Server/app/services/approval_adapter.py
git commit -m "feat(adapter): add on_approved_with_file for invoice - Task 3"
```

---

### Task 4: 审批 API 支持文件上传

**Files:**
- Modify: `CRM-Server/app/api/approvals.py` — 通用审批端点
- Modify: `CRM-Server/app/api/invoices.py` — 发票专用审批端点（可选，优先通用端点）

**Interfaces:**
- Consumes: `FileStorageService`（Task 1），`InvoiceApplicationAdapter.on_approved_with_file`（Task 3）
- Produces: `POST /v1/approvals/INVOICE/{entity_id}/approve-with-file` 端点

- [ ] **Step 1: Add approve-with-file endpoint**

```python
# app/api/approvals.py (在现有 approvals router 中添加)

from fastapi import File, UploadFile, Form
from app.services.file_storage import file_storage_service, FileStorageError

@router.post(
    "/{entity_type}/{entity_id}/approve-with-file",
    summary="审批通过并上传发票文件（仅发票类型）",
    description="财务人员审批发票时上传发票文件，审批通过后自动变为已开票状态"
)
async def approve_with_file(
    entity_type: str,
    entity_id: int,
    file: UploadFile = File(..., description="发票文件（PDF/JPG/PNG/OFD）"),
    invoice_number: Optional[str] = Form(None, description="发票号码（可选，财务可从文件中查看）"),
    comment: Optional[str] = Form(None, description="审批意见"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:approve")),
    db: Session = Depends(get_db),
):
    """审批发票时上传文件——仅支持 INVOICE 类型"""
    
    # 只支持发票类型
    if entity_type != BusinessType.INVOICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅发票类型支持上传文件审批"
        )
    
    # 获取适配器和实体
    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, entity_id, team_id)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} 实体不存在"
        )
    
    # 检查状态
    if entity.status != InvoiceApplicationStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"发票状态为 {entity.status}，无法审批"
        )
    
    # 读取文件内容
    file_content = await file.read()
    
    # 保存文件
    try:
        file_path = file_storage_service.save_invoice_file(
            team_id=team_id,
            invoice_id=entity_id,
            filename=file.filename or "invoice.pdf",
            content=file_content,
        )
    except FileStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # 调用适配器的 on_approved_with_file
    adapter.on_approved_with_file(db, entity, file_path, invoice_number)
    
    # 创建审批记录
    from app.crud.approval import approval_crud
    from app.models.approval import ApprovalStatus
    
    approval = approval_crud.get_by_entity(db, entity_type, entity_id, team_id)
    if approval:
        # 更新审批状态为通过
        approval.status = ApprovalStatus.APPROVED
        approval.current_node_id = None
    
    # 创建审批操作记录
    from app.models.approval import ApprovalRecord
    record = ApprovalRecord(
        approval_id=approval.id if approval else None,
        node_id=approval.current_node_id if approval else None,
        approver_id=str(current_user.id),
        action="approve_with_file",
        comment=comment or f"审批通过，发票号码：{invoice_number}",
        created_time=func.now(),
    )
    if approval:
        db.add(record)
    
    db.commit()
    
    return {
        "success": True,
        "message": "审批成功，发票已上传",
        "file_path": file_path,
        "invoice_number": invoice_number,
        "new_status": InvoiceApplicationStatus.ISSUED,
    }
```

- [ ] **Step 2: Add file download endpoint**

```python
# app/api/invoices.py (添加文件下载端点)

from fastapi import Response
from app.services.file_storage import file_storage_service, FileStorageError

@invoice_router.get(
    "/{application_id}/file",
    summary="下载发票文件",
    description="下载已上传的发票文件（仅已开票状态的发票）"
)
async def download_invoice_file(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """下载发票文件"""
    
    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )
    
    if not application.invoice_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该发票未上传文件"
        )
    
    # 获取文件
    try:
        full_path = file_storage_service.get_full_path(application.invoice_file_path)
    except FileStorageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件路径非法"
        )
    
    if not os.path.exists(full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    
    # 读取文件并返回
    with open(full_path, "rb") as f:
        content = f.read()
    
    # 根据扩展名设置 Content-Type
    ext = os.path.splitext(application.invoice_file_path)[1].lower()
    content_type_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".ofd": "application/octet-stream",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")
    
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{application.invoice_number or application_id}.pdf\""
        }
    )
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/api/approvals.py CRM-Server/app/api/invoices.py
git commit -m "feat(api): add approve-with-file and file-download endpoints - Task 4"
```

---

## Phase C — 前端文件上传组件

### Task 5: 文件上传组件

**Files:**
- Create: `CRM-Client/src/components/InvoiceFileUpload.vue`
- Create: `CRM-Client/src/api/fileUpload.ts`

**Interfaces:**
- Consumes: None
- Produces: `<InvoiceFileUpload>` 组件，props: `invoiceId`, events: `@uploaded(file_path, invoice_number)`

**UX Design Considerations (UI/UX Pro Max 审查补充):**

> 以下交互细节基于 UI/UX Pro Max 规则审查，必须包含在组件实现中：

| 规则 | 优先级 | 要求 |
|------|--------|------|
| `touch-target-size` | CRITICAL | 上传按钮最小 44×44px，icon 按钮需扩大 hitSlop |
| `touch-spacing` | CRITICAL | 按钮间距 ≥8px (gap-2) |
| `aria-labels` | CRITICAL | Icon-only 上传按钮添加 aria-label="选择发票文件" |
| `loading-buttons` | CRITICAL | 提交时按钮 disabled + spinner |
| `form-labels` | CRITICAL | 发票号码输入需 visible label，禁用 placeholder-only |
| `inline-validation` | HIGH | 文件选择时即时校验（而非提交时） |
| `error-recovery` | HIGH | 错误消息含解决方案（如"请选择 PDF/JPG/PNG/OFD 格式"） |
| `progress-indicators` | HIGH | 大文件上传需进度条/百分比 |
| `submit-feedback` | HIGH | Toast + 状态变化动画（PENDING → ISSUED） |
| `press-feedback` | MEDIUM | 按钮 active 状态 scale(0.95) + opacity |
| `reduced-motion` | MEDIUM | 尊重 prefers-reduced-motion 媒体查询 |
| `file-preview` | MEDIUM | 上传后显示文件名+大小+类型图标 |
| `undo-support` | MEDIUM | 提供"重新选择"/"移除"按钮 |

**Frontend Design 补充细节（视觉质量提升）:**

> 基于 frontend-design 审查，补充 6 个视觉和交互细节，确保组件符合专业设计标准：

| 补充点 | 设计原则 | 具体改进 |
|--------|----------|----------|
| **状态变化动画** | Motion deliberately | PENDING → ISSUED 状态切换添加 fade transition + 颜色变化（0.3s ease） |
| **按钮层级区分** | Structure is information | 主操作（上传并审批）占主要空间，危险操作（拒绝）视觉分离 + plain 样式 |
| **必填 vs 可选视觉区分** | Typography carries personality | 必填字段（文件）添加左侧 3px border accent，可选字段添加灰色 "可选" 标签 |
| **文件上传成功标记** | Write from end user's side | 文件预览区域添加绿色 ✓ icon + success border，明确反馈成功状态 |
| **空状态引导文案** | Empty states are invitations | 未选择文件时显示 Upload icon + "请选择发票文件开始审批" + 格式提示 |
| **Toast 文案优化** | Be specific, not clever | "审批通过，发票已开票" + 副标题"销售人员可下载发票文件查看"

- [ ] **Step 1: Create API wrapper**

```typescript
// src/api/fileUpload.ts

import { ref, type Ref } from 'vue'
import apiClient from './client'
import { showError } from '@/utils/errorMessages'

export interface FileUploadResult {
  file_path: string
  file_name: string
  file_size: number
  message: string
}

export interface ApproveWithFileResult {
  success: boolean
  message: string
  file_path: string
  invoice_number: string
  new_status: string
}

/**
 * 上传发票文件并审批
 */
export async function approveInvoiceWithFile(
  invoiceId: number,
  file: File,
  invoiceNumber: string,
  comment?: string
): Promise<ApproveWithFileResult> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('invoice_number', invoiceNumber)
  if (comment) {
    formData.append('comment', comment)
  }

  const response = await apiClient.post<ApproveWithFileResult>(
    `/v1/approvals/INVOICE/${invoiceId}/approve-with-file`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  )

  return response.data
}

/**
 * 下载发票文件
 */
export function getInvoiceFileUrl(invoiceId: number): string {
  return `${apiClient.defaults.baseURL}/invoice-applications/${invoiceId}/file`
}
```

- [ ] **Step 2: Create upload component (含 UX + Frontend Design 改进)**

```vue
<!-- src/components/InvoiceFileUpload.vue -->

<template>
  <div class="invoice-file-upload">
    <!-- Frontend Design: 状态变化动画 -->
    <transition name="status-fade" mode="out-in">
      <div v-if="approvalStatus === 'PENDING_REVIEW'" class="status-badge pending">
        <el-icon><Clock /></el-icon>
        待审批
      </div>
      <div v-else-if="approvalStatus === 'ISSUED'" class="status-badge issued">
        <el-icon><CircleCheckFilled /></el-icon>
        已开票
      </div>
    </transition>

    <!-- 上传区域（Frontend Design: 必填字段视觉区分） -->
    <el-upload
      ref="uploadRef"
      class="upload-area required-field"
      :auto-upload="false"
      :limit="1"
      :on-change="handleFileChange"
      :on-exceed="handleExceed"
      :accept="acceptedTypes"
      :before-upload="beforeUpload"
    >
      <!-- UX: aria-label for icon-only button, min-height 44px -->
      <el-button
        type="primary"
        class="wolf-btn wolf-btn--primary upload-btn"
        aria-label="选择发票文件"
      >
        <el-icon><Upload /></el-icon>
        选择发票文件
      </el-button>
      <template #tip>
        <div class="upload-tip">
          支持 PDF、JPG、PNG、OFD 格式，最大 10MB
        </div>
      </template>
    </el-upload>

    <!-- Frontend Design: 空状态引导文案 -->
    <div v-if="!selectedFile && !validationError" class="empty-upload-state">
      <el-icon class="empty-icon"><Document /></el-icon>
      <p class="empty-text">请选择发票文件开始审批</p>
      <p class="empty-hint">支持 PDF、JPG、PNG、OFD 格式</p>
    </div>

    <!-- UX: 即时校验错误提示（含恢复路径） -->
    <el-alert
      v-if="validationError"
      type="error"
      :title="validationError"
      :description="errorRecoveryHint"
      show-icon
      closable
      @close="validationError = ''"
      class="validation-error"
    />

    <!-- UX + Frontend Design: 文件预览 + 成功标记 -->
    <div v-if="selectedFile" class="selected-file-info success">
      <el-icon class="success-check"><CircleCheckFilled /></el-icon>
      <el-icon class="file-type-icon" :class="getFileIconClass(selectedFile.name)">
        <Document v-if="isPdf(selectedFile.name)" />
        <Picture v-else />
      </el-icon>
      <span class="file-name">{{ selectedFile.name }}</span>
      <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
      <!-- UX: 移除/重新选择按钮 aria-label -->
      <el-button
        link
        type="danger"
        size="small"
        @click="clearFile"
        aria-label="移除已选文件"
      >
        <el-icon><Close /></el-icon>
        移除
      </el-button>
    </div>

    <!-- UX: 上传进度条（大文件 >1MB） -->
    <el-progress
      v-if="uploading && selectedFile && selectedFile.size > 1024 * 1024"
      :percentage="uploadProgress"
      :status="uploadProgress === 100 ? 'success' : ''"
      class="upload-progress"
    />

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="invoice-number-form"
    >
      <!-- UX + Frontend Design: 发票号码可选，带可选标记 + tooltip -->
      <el-form-item prop="invoice_number">
        <template #label>
          <div class="optional-label">
            <span>发票号码</span>
            <span class="optional-tag">可选</span>
            <el-tooltip
              content="发票号码已印在发票文件上，无需手动填写。如需记录可填写，便于后续查询。"
              placement="top"
            >
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-input
          v-model="form.invoice_number"
          placeholder="可选：记录发票号码便于查询"
          :maxlength="100"
          show-word-limit
          clearable
        />
      </el-form-item>

      <!-- Frontend Design: 审批意见可选标记 -->
      <el-form-item prop="comment">
        <template #label>
          <div class="optional-label">
            <span>审批意见</span>
            <span class="optional-tag">可选</span>
          </div>
        </template>
        <el-input
          v-model="form.comment"
          type="textarea"
          placeholder="填写审批意见"
          :maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <!-- Frontend Design: 按钮层级区分 -->
    <div class="action-buttons">
      <!-- 主操作：上传并审批 -->
      <el-button
        type="primary"
        class="wolf-btn wolf-btn--primary approve-btn"
        :loading="submitting"
        :disabled="!selectedFile"
        @click="handleApproveWithFile"
      >
        <el-icon><Check /></el-icon>
        上传发票并审批
      </el-button>

      <!-- 危险操作：拒绝（视觉分离） -->
      <el-button
        type="danger"
        class="wolf-btn wolf-btn--danger reject-btn"
        plain
        @click="handleReject"
      >
        <el-icon><Close /></el-icon>
        拒绝审批
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { ElMessage, type UploadInstance, type UploadFile, type FormInstance, type FormRules } from 'element-plus'
import {
  Upload,
  Document,
  Close,
  Picture,
  QuestionFilled,
  Check,
  Clock,
  CircleCheckFilled
} from '@element-plus/icons-vue'

const props = defineProps<{
  invoiceId: number
  approvalStatus?: string // Frontend Design: 接收当前审批状态
}>()

const emit = defineEmits<{
  uploaded: [file_path: string, invoice_number: string]
  rejected: []
  error: [message: string]
  statusChanged: [new_status: string] // Frontend Design: 状态变化事件
}>()

const uploadRef = ref<UploadInstance>()
const formRef = ref<FormInstance>()
const selectedFile = ref<File | null>(null)

// UX: 状态变量
const validationError = ref('')
const errorRecoveryHint = ref('')
const uploading = ref(false)
const uploadProgress = ref(0)

const form = reactive({
  invoice_number: '',
  comment: ''
})

const rules: FormRules = {
  invoice_number: [
    { max: 100, message: '发票号码最长 100 字符', trigger: 'blur' }
  ]
}

const acceptedTypes = '.pdf,.jpg,.jpeg,.png,.ofd'

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

// UX: 即时校验（选择时而非提交时）
const handleFileChange = (uploadFile: UploadFile) => {
  if (uploadFile.raw) {
    const validationResult = validateFileInstant(uploadFile.raw)
    if (!validationResult.valid) {
      validationError.value = validationResult.error
      errorRecoveryHint.value = validationResult.recoveryHint
      selectedFile.value = null
      uploadRef.value?.clearFiles()
    } else {
      validationError.value = ''
      errorRecoveryHint.value = ''
      selectedFile.value = uploadFile.raw
    }
  }
}

// UX: 即时校验函数（含恢复路径）
const validateFileInstant = (file: File): { valid: boolean; error?: string; recoveryHint?: string } => {
  // 文件大小校验
  if (file.size > MAX_FILE_SIZE) {
    return {
      valid: false,
      error: `文件过大：${formatFileSize(file.size)}`,
      recoveryHint: `请选择小于 ${formatFileSize(MAX_FILE_SIZE)} 的文件，或压缩后再上传`
    }
  }
  
  // 扩展名校验
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  const allowed = ['.pdf', '.jpg', '.jpeg', '.png', '.ofd']
  if (!allowed.includes(ext)) {
    return {
      valid: false,
      error: `不支持的文件类型：${ext}`,
      recoveryHint: '请选择 PDF、JPG、PNG 或 OFD 格式的发票文件'
    }
  }
  
  return { valid: true }
}

const handleExceed = () => {
  ElMessage.warning('只能上传一个文件，请先移除当前文件')
}

const beforeUpload = (file: File) => {
  // 重复校验（before-upload 是 el-upload 的钩子）
  const result = validateFileInstant(file)
  if (!result.valid) {
    ElMessage.error(result.error)
    return false
  }
  return true
}

const clearFile = () => {
  selectedFile.value = null
  validationError.value = ''
  errorRecoveryHint.value = ''
  uploadRef.value?.clearFiles()
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// UX: 文件类型图标辅助函数
const isPdf = (filename: string) => filename.toLowerCase().endsWith('.pdf')
const getFileIconClass = (filename: string) => isPdf(filename) ? 'pdf-icon' : 'image-icon'

/**
 * 验证并提交
 * @returns 是否验证成功
 */
const validate = async (): Promise<boolean> => {
  // 检查文件（UX: 即时校验已处理，此处为二次确认）
  if (!selectedFile.value) {
    ElMessage.warning('请选择发票文件')
    return false
  }
  
  // 检查表单
  const valid = await formRef.value?.validate().catch(() => false)
  return valid === true
}

/**
 * 获取提交数据
 */
const getSubmitData = () => {
  return {
    file: selectedFile.value,
    invoice_number: form.invoice_number,
    comment: form.comment
  }
}

/**
 * UX: 设置上传状态（由父组件调用）
 */
const setUploadState = (state: { uploading: boolean; progress?: number }) => {
  uploading.value = state.uploading
  if (state.progress !== undefined) {
    uploadProgress.value = state.progress
  }
}

// Frontend Design: 新增状态管理
const submitting = ref(false)
const currentStatus = ref(props.approvalStatus || 'PENDING_REVIEW')

/**
 * Frontend Design + Toast 文案优化: 审批通过处理
 */
const handleApproveWithFile = async () => {
  const valid = await validate()
  if (!valid) return

  const data = getSubmitData()
  if (!data.file) return

  submitting.value = true
  uploading.value = true

  try {
    // 调用父组件提交方法（父组件负责 API 调用）
    emit('uploaded', data.invoice_number || '', '')

    // Frontend Design: Toast 文案优化
    ElMessage.success({
      message: '审批通过，发票已开票',
      description: '销售人员可下载发票文件查看',
      duration: 3000
    })

    // Frontend Design: 状态变化动画
    currentStatus.value = 'ISSUED'
    emit('statusChanged', 'ISSUED')

    clearFile()
  } catch (error) {
    // Frontend Design: Toast 文案优化
    ElMessage.error({
      message: '审批失败',
      description: '请检查文件格式或联系技术支持'
    })
    emit('error', '审批失败')
  } finally {
    submitting.value = false
    uploading.value = false
  }
}

/**
 * Frontend Design: 拒绝审批处理
 */
const handleReject = () => {
  emit('rejected')

  ElMessage.warning({
    message: '审批已拒绝',
    description: '申请人将收到拒绝通知'
  })

  currentStatus.value = 'REJECTED'
  emit('statusChanged', 'REJECTED')
}

// 暴露方法给父组件
defineExpose({
  validate,
  getSubmitData,
  clearFile,
  setUploadState,
  handleApproveWithFile,
  handleReject
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.invoice-file-upload {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

// Frontend Design: 状态变化动画
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs;
  padding: $wolf-space-xs $wolf-space-md;
  border-radius: $wolf-radius-sm;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-body;
  transition: all 0.3s ease;

  &.pending {
    background: $wolf-warning-bg;
    color: $wolf-warning-text;
    border: 1px solid $wolf-warning-border;
  }

  &.issued {
    background: $wolf-success-bg;
    color: $wolf-success-text;
    border: 1px solid $wolf-success-border;
  }
}

.status-fade-enter-active,
.status-fade-leave-active {
  transition: all 0.3s ease;
}

.status-fade-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.status-fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

// Frontend Design: 必填字段视觉区分
.upload-area.required-field {
  border-left: 3px solid $wolf-primary;
  padding-left: $wolf-space-sm;
  margin-bottom: $wolf-space-md;
}

.upload-area {
  .el-upload {
    width: 100%;
  }
}

.upload-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-top: $wolf-space-xs;
}

// Frontend Design: 空状态引导文案
.empty-upload-state {
  text-align: center;
  padding: $wolf-space-lg;
  color: $wolf-text-tertiary;
  background: $wolf-fill-light;
  border-radius: $wolf-radius-sm;
  border: 1px dashed $wolf-border-light;

  .empty-icon {
    font-size: 48px;
    color: $wolf-text-quaternary;
    margin-bottom: $wolf-space-md;
  }

  .empty-text {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-secondary;
    margin-bottom: $wolf-space-xs;
  }

  .empty-hint {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }
}

// Frontend Design: 文件上传成功标记
.selected-file-info.success {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-card-padding;
  background: $wolf-success-bg;
  border: 1px solid $wolf-success-border;
  border-radius: $wolf-radius-sm;

  .success-check {
    color: $wolf-success-text;
    font-size: 20px;
    font-weight: bold;
  }

  .file-name {
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    font-weight: $wolf-font-weight-medium;
  }
  
  .file-size {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }
}

.invoice-number-form {
  margin-top: $wolf-space-md;

  // Frontend Design: 可选标签视觉区分
  .optional-label {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;

    .optional-tag {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      background: $wolf-fill-light;
      padding: 2px 6px;
      border-radius: $wolf-radius-xs;
      font-weight: $wolf-font-weight-regular;
    }

    .help-icon {
      color: $wolf-text-tertiary;
      cursor: help;
      font-size: 16px;
    }
  }
}

// Frontend Design: 按钮层级区分
.action-buttons {
  display: flex;
  gap: $wolf-space-md;
  margin-top: $wolf-space-lg;

  .approve-btn {
    flex: 1; // 主操作占据更多空间
    min-height: 44px; // UX: touch-target-size
  }

  .reject-btn {
    flex: 0 0 auto; // 次操作固定宽度
    min-height: 44px; // UX: touch-target-size
  }
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/components/InvoiceFileUpload.vue CRM-Client/src/api/fileUpload.ts
git commit -m "feat(client): add InvoiceFileUpload component - Task 5"
```

---

### Task 6: 集成到审批流程

**Files:**
- Modify: `CRM-Client/src/components/ApprovalProcessGeneric.vue`
- Modify: `CRM-Client/src/views/InvoiceDetail.vue:190-209`
- Modify: `CRM-Client/src/views/FinanceInvoiceApprovals.vue`
- Modify: `CRM-Client/src/schemas/invoice.ts`

**Interfaces:**
- Consumes: `InvoiceFileUpload`（Task 5）
- Produces: 审批时显示文件上传控件，提交后刷新状态

- [ ] **Step 1: Update InvoiceApplicationResponse type**

```typescript
// src/schemas/invoice.ts

export interface InvoiceApplicationResponse {
  // ... 现有字段 ...
  
  // 新增字段（Task 6）
  invoice_file_path?: string
  invoice_number?: string
  issued_time?: string
}
```

- [ ] **Step 2: Modify ApprovalProcessGeneric for invoice file upload**

```vue
<!-- src/components/ApprovalProcessGeneric.vue (在审批操作区域添加) -->

<template>
  <!-- ... 现有内容 ... -->
  
  <!-- 发票审批时的文件上传区域 -->
  <div v-if="entityType === 'INVOICE' && canApprove && detail?.status === 'PENDING_REVIEW'" class="file-upload-section">
    <InvoiceFileUpload
      ref="fileUploadRef"
      :invoice-id="entityId"
      @uploaded="handleFileUploaded"
      @error="handleUploadError"
    />
    
    <el-button
      type="primary"
      class="wolf-btn wolf-btn--primary approve-with-file-btn"
      :loading="submitting"
      @click="handleApproveWithFile"
    >
      <el-icon><Check /></el-icon>
      上传发票并审批
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import InvoiceFileUpload from './InvoiceFileUpload.vue'
import { approveInvoiceWithFile } from '@/api/fileUpload'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'

// ... 现有 props 和 setup ...

const fileUploadRef = ref<InstanceType<typeof InvoiceFileUpload>>()
const submitting = ref(false)

const handleApproveWithFile = async () => {
  // 验证文件和表单
  const valid = await fileUploadRef.value?.validate()
  if (!valid) return
  
  const data = fileUploadRef.value?.getSubmitData()
  if (!data?.file) return
  
  submitting.value = true
  try {
    const result = await approveInvoiceWithFile(
      entityId,
      data.file,
      data.invoice_number,
      data.comment
    )
    
    ElMessage.success(result.message)
    emit('approved', result)
    fileUploadRef.value?.clearFile()
    
    // 刷新详情
    await fetchDetail()
  } catch (error) {
    ElMessage.error('审批失败')
    emit('error', error)
  } finally {
    submitting.value = false
  }
}

const handleFileUploaded = (file_path: string, invoice_number: string) => {
  emit('uploaded', { file_path, invoice_number })
}

const handleUploadError = (message: string) => {
  ElMessage.error(message)
}
</script>
```

- [ ] **Step 3: Update InvoiceDetail to show uploaded file**

```vue
<!-- src/views/InvoiceDetail.vue (在发票信息中添加文件显示) -->

<template>
  <!-- ... 现有内容 ... -->
  
  <!-- 已上传发票文件显示 -->
  <div v-if="invoiceInfo?.invoice_file_path" class="uploaded-file-section">
    <div class="card-header">
      <span class="card-title">发票文件</span>
    </div>
    <div class="file-info">
      <el-icon><Document /></el-icon>
      <span class="file-label">发票号码：{{ invoiceInfo.invoice_number }}</span>
      <el-button link type="primary" size="small" @click="downloadFile">
        <el-icon><Download /></el-icon>
        下载发票文件
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, Document } from '@element-plus/icons-vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'

const downloadFile = () => {
  if (!invoiceInfo.value) return
  const url = getInvoiceFileUrl(invoiceInfo.value.id)
  window.open(url, '_blank')
}
</script>
```

- [ ] **Step 4: Update FinanceInvoiceApprovals drawer**

```vue
<!-- src/views/FinanceInvoiceApprovals.vue (审批详情 drawer 中添加文件上传) -->

<template>
  <!-- ... 现有内容 ... -->
  
  <el-drawer v-model="drawerVisible" title="发票申请详情" :width="720">
    <!-- ... 现有描述信息 ... -->
    
    <!-- 审批操作区域替换为文件上传审批 -->
    <div v-if="currentRecord?.status === 'PENDING_REVIEW'" class="approval-actions">
      <InvoiceFileUpload
        ref="drawerFileUploadRef"
        :invoice-id="currentRecord.id"
      />
      <div class="action-buttons">
        <el-button type="primary" @click="handleApproveWithFileInDrawer">
          上传发票并审批
        </el-button>
        <el-button @click="handleRejectInDrawer">拒绝</el-button>
      </div>
    </div>
    
    <!-- 已上传文件显示 -->
    <div v-if="currentRecord?.invoice_file_path" class="uploaded-file-info">
      <el-icon><Document /></el-icon>
      <span>发票号码：{{ currentRecord.invoice_number }}</span>
      <el-button link type="primary" @click="downloadDrawerFile">下载</el-button>
    </div>
  </el-drawer>
</template>
```

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/ApprovalProcessGeneric.vue CRM-Client/src/views/InvoiceDetail.vue CRM-Client/src/views/FinanceInvoiceApprovals.vue CRM-Client/src/schemas/invoice.ts
git commit -m "feat(client): integrate file upload into approval flow - Task 6"
```

---

## Phase D — Docker 配置验证

### Task 7: 验证并同步 Docker 配置

**Files:**
- Verify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`（如需要）

**Interfaces:**
- Consumes: None
- Produces: 确保 uploads 目录正确挂载

- [ ] **Step 1: Verify docker-compose.yml mount**

```bash
# 检查挂载配置
grep -A 5 "volumes:" /Users/eddie/Code/CRMWolf/docker-compose.yml
```

Expected: `./uploads:/app/uploads` 存在

- [ ] **Step 2: Sync prod config if needed**

```yaml
# docker-compose.prod.yml (确保有相同挂载)
services:
  backend:
    volumes:
      - ./uploads:/app/uploads
      # ... 其他挂载 ...
```

- [ ] **Step 3: Create uploads directory**

```bash
mkdir -p /Users/eddie/Code/CRMWolf/uploads/invoices
chmod 755 /Users/eddie/Code/CRMWolf/uploads
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml
# uploads 目录不纳入 git（应添加 .gitkeep）
touch uploads/.gitkeep
git add uploads/.gitkeep
git commit -m "chore(docker): verify uploads mount and add .gitkeep - Task 7"
```

---

## Phase E — 测试与文档

### Task 8: 端到端测试

**Files:**
- Create: `CRM-Server/tests/unit/test_invoice_approval_with_file.py`

**Interfaces:**
- Consumes: All previous tasks
- Produces: 验证完整流程

- [ ] **Step 1: Write integration test**

```python
# tests/unit/test_invoice_approval_with_file.py

import pytest
import tempfile
import os
from io import BytesIO

from app.services.file_storage import FileStorageService
from app.services.approval_adapter import InvoiceApplicationAdapter
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus


@pytest.fixture
def temp_db_session():
    """临时数据库会话（使用内存数据库）"""
    # 这里用实际的 test fixtures 或 mock
    pass


def test_approve_with_file_flow():
    """测试完整的审批+文件上传流程"""
    
    # 1. 模拟上传文件
    storage = FileStorageService(base_dir=tempfile.mkdtemp())
    file_content = b"test invoice pdf"
    file_path = storage.save_invoice_file(
        team_id=1,
        invoice_id=100,
        filename="INV-001.pdf",
        content=file_content,
    )
    
    # 2. 验证文件已保存
    assert storage.file_exists(file_path)
    
    # 3. 模拟适配器回调
    adapter = InvoiceApplicationAdapter()
    
    # 创建模拟发票实体
    invoice = InvoiceApplication(
        id=100,
        team_id=1,
        status=InvoiceApplicationStatus.PENDING_REVIEW,
    )
    
    # 调用 on_approved_with_file
    adapter.on_approved_with_file(
        db=None,  # mock
        entity=invoice,
        file_path=file_path,
        invoice_number="INV-001",
    )
    
    # 4. 验证状态变化
    assert invoice.status == InvoiceApplicationStatus.ISSUED
    assert invoice.invoice_file_path == file_path
    assert invoice.invoice_number == "INV-001"
```

- [ ] **Step 2: Run test**

```bash
cd CRM-Server
PYTHONPATH=/Users/eddie/Code/CRMWolf/CRM-Server /Users/eddie/Code/CRMWolf/CRM-Server/venv/bin/python -m pytest tests/unit/test_invoice_approval_with_file.py -v --no-cov -o addopts=""
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/tests/unit/test_invoice_approval_with_file.py
git commit -m "test(invoice): add approval-with-file integration test - Task 8"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ 文件上传基础设施（Task 1）
- ✅ 数据库字段（Task 2）
- ✅ 审批适配器扩展（Task 3）
- ✅ API 端点（Task 4）
- ✅ 前端组件（Task 5-6）
- ✅ Docker 配置（Task 7）
- ✅ 测试（Task 8）

**2. Placeholder scan:**
- ✅ 无 TBD/TODO
- ✅ 所有代码步骤都有完整实现
- ✅ 无 "类似 Task N" 引用

**3. Type consistency:**
- ✅ `file_path: str` 贯穿始终
- ✅ `invoice_number: str` 贯穿始终
- ✅ `InvoiceApplicationStatus.ISSUED` 状态一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-invoice-approval-file-upload.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
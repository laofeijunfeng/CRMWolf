# License 申请流程优化实施计划

**创建时间**：2026-07-07  
**问题描述**：License 申请流程存在两个问题：  
1. 前端点击"申请 License"按钮保存草稿，需要二次点击提交  
2. 配置了审批流程但没有触发，审批人收不到通知，审批中心看不到申请记录  

---

## 一、问题根因分析

### 问题 1：前端流程设计不合理

**现状**：
- 前端按钮文本为"保存草稿"（`LicenseApplicationDialog.vue:52`）
- `handleSubmit()` 只调用 `create()` API，创建状态为 `DRAFT` 的申请
- 需要在列表中点击"提交"按钮，调用 `submitApplication(id)` API

**对比其他业务单据**：
- 合同、回款、发票使用统一审批入口：`POST /v1/approvals/{entity_type}/{entity_id}/submit`
- 创建草稿 → 提交审批一步完成，无需二次点击

### 问题 2：后端审批流程触发机制缺失

**现状**：
- License 提交 API（`POST /v1/license-applications/{id}/submit`）只修改状态 `DRAFT → PENDING`
- 没有调用审批引擎：
  - ❌ `approval_flow_crud.match_flow_generic()` - 匹配审批流程
  - ❌ `approval_crud.create_approval_generic()` - 创建审批实例
  - ❌ 通知服务 - 发送飞书消息给审批人

**对比其他业务单据**：
- 回款提交时会：
  1. 匹配审批流程（`match_flow_generic(BusinessType.PAYMENT, team_id, amount, None)`）
  2. 创建审批实例（`create_approval_generic()`）
  3. 发送通知给审批人

**架构缺陷**：
- 虽然 `BusinessType.LICENSE` 已定义，但：
  - ❌ 审批适配器缺失（`approval_adapter.py` 的 `_REGISTRY` 没有 LICENSE）
  - ❌ 审批引擎未接入（没有调用匹配和创建函数）
  - ❌ 通知机制缺失

---

## 二、实施方案

### Step 1：创建 License 审批适配器

**文件**：`CRM-Server/app/services/approval_adapter.py`  
**修改内容**：在文件末尾添加 LicenseApplicationAdapter 类并注册

```python
from app.models.license_application import LicenseApplication, LicenseApplicationStatus

class LicenseApplicationAdapter:
    """License 申请审批适配器
    
    状态流转：
    - on_submit: DRAFT → PENDING（提交审批）
    - on_approved: PENDING → ISSUED（审批通过，由审批人在 approve_full API 中设置）
    - on_rejected: PENDING → REJECTED（审批拒绝）
    - on_cancelled: PENDING → DRAFT（撤回审批）
    """
    business_type = BusinessType.LICENSE
    
    def get_entity(self, db: Session, business_id: int, team_id: int) -> Optional[LicenseApplication]:
        """获取 License 申请实体"""
        from app.crud.crud_license_application import license_application_crud
        return license_application_crud.get(db, team_id, business_id)
    
    def get_submitter(self, entity: LicenseApplication) -> tuple[str, str | None]:
        """获取提交人信息
        
        Returns:
            (applicant_id, None) - License 申请只有 applicant_id，无姓名字段
        """
        if entity is None:
            return "", None
        return entity.applicant_id or "", None
    
    def match_kwargs(self, entity: LicenseApplication) -> dict:
        """匹配审批流程的维度参数
        
        License 申请按 license_type（试用/正式）匹配流程
        """
        return {
            "amount": 0,  # License 申请无金额概念
            "license_type": getattr(entity, "license_type", None),
        }
    
    def on_submit(self, db: Session, entity: LicenseApplication) -> None:
        """提交审批时的状态切换"""
        if entity is None: return  # E4 守卫
        entity.status = LicenseApplicationStatus.PENDING
    
    def on_approved(self, db: Session, entity: LicenseApplication) -> None:
        """审批通过时的状态切换
        
        注意：License 申请的审批通过需要审批人填写 License 信息，
        在 approve_full API 中手动设置状态为 ISSUED。
        此处预留回调逻辑（如需要可扩展）。
        """
        if entity is None: return  # E4 守卫
        # 审批通过后，状态由审批人在 approve_full API 中设置为 ISSUED
        # 此处不修改状态，避免与 approve_full 冲突
    
    def on_rejected(self, db: Session, entity: LicenseApplication) -> None:
        """审批拒绝时的状态切换"""
        if entity is None: return  # E4 守卫
        entity.status = LicenseApplicationStatus.REJECTED
    
    def on_cancelled(self, db: Session, entity: LicenseApplication) -> None:
        """撤回审批时的状态切换"""
        if entity is None: return  # E4 守卫
        entity.status = LicenseApplicationStatus.DRAFT
    
    def get_name(self, entity: LicenseApplication) -> str:
        """获取申请展示名称（用于通知）"""
        if entity is None:
            return "License申请"
        return f"License申请#{entity.application_number}"


# 注册适配器到全局注册表
_REGISTRY[BusinessType.LICENSE] = LicenseApplicationAdapter()
```

**影响范围**：
- 审批引擎现在可以处理 LICENSE 类型的业务单据
- 适配器提供状态流转、匹配维度、提交人信息等功能

---

### Step 2：修改 License 提交 API，接入审批引擎

**文件**：`CRM-Server/app/api/license_application.py`  
**修改内容**：替换原有的 submit_application 函数

**方案选择**：保留兼容 API，内部调用审批引擎

```python
@router.post("/{application_id}/submit", response_model=LicenseApplicationResponse, summary="提交License申请")
def submit_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    提交 License 申请（接入审批引擎）
    
    流程：
    1. 验证申请存在且状态为 DRAFT
    2. 匹配审批流程（按 license_type）
    3. 创建审批实例（Approval + ApprovalRecord）
    4. 发送通知给审批人（待 Task A8 泛化实现）
    5. 返回申请信息
    """
    from app.crud.approval import approval_flow_crud, approval_crud
    from app.services.approval_adapter import get_adapter
    from app.constants.business_types import BusinessType
    
    # 1. 获取申请并验证
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅草稿状态的申请可以提交"
        )
    
    # 2. 获取适配器
    adapter = get_adapter(BusinessType.LICENSE)
    
    # 3. 匹配审批流程
    flow, err = approval_flow_crud.match_flow_generic(
        db,
        BusinessType.LICENSE,
        team_id,
        **adapter.match_kwargs(existing)
    )
    
    if flow is None and err:
        # CONTRACT 分支：未匹配报错（沿用合同语义）
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err or "未匹配到审批流程"
        )
    
    if flow is None:
        # PAYMENT/INVOICE 分支：未匹配直通（决策1）
        # License 申请未配置流程时，直接批准（免审批）
        existing.status = LicenseApplicationStatus.ISSUED
        db.commit()
        db.refresh(existing)
        return existing
    
    # 4. 获取提交人信息
    submitter_id, submitter_name = adapter.get_submitter(existing)
    
    # 5. 创建审批实例（会自动调用 adapter.on_submit 切换状态）
    try:
        approval = approval_crud.create_approval_generic(
            db,
            BusinessType.LICENSE,
            application_id,
            team_id,
            flow,
            submitter_id,
            submitter_name or current_user.name,  # 补充姓名
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # 6. 发送通知给审批人（待 Task A8 泛化实现）
    # TODO: 调用通知服务发送飞书消息
    
    # 7. 返回申请信息（状态已由 adapter.on_submit 切换为 PENDING）
    db.refresh(existing)
    return existing
```

**关键修改点**：
- ✅ 匹配审批流程（`match_flow_generic`）
- ✅ 创建审批实例（`create_approval_generic`）
- ✅ 状态由适配器自动切换（`adapter.on_submit`）
- ⚠️ 通知机制待实现（Task A8 泛化）

**兼容性保证**：
- 前端仍可使用原有 API 路径 `/v1/license-applications/{id}/submit`
- 或者改用统一审批入口 `/v1/approvals/LICENSE/{id}/submit`

---

### Step 3：修改前端申请对话框，一步提交审批

**文件**：`CRM-Client/src/components/LicenseApplicationDialog.vue`  
**修改内容**：修改按钮文本和提交逻辑

#### 修改 1：按钮文本

```vue
<template #footer>
  <el-button @click="visible = false">取消</el-button>
  <!-- ✅ 改为"提交申请"，直接走审批流程 -->
  <el-button type="primary" @click="handleSubmit" :loading="loading">提交申请</el-button>
</template>
```

#### 修改 2：提交逻辑

```typescript
const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
    loading.value = true

    // 1. 先创建申请（草稿）
    const submitData = {
      ...formData.value,
      expiry_date: formData.value.expiry_date ? formatDate(formData.value.expiry_date) : ''
    }
    
    let applicationId: number
    if (props.application) {
      // 编辑模式：更新现有申请
      await licenseApplicationApi.updateApplication(props.application.id, submitData)
      applicationId = props.application.id
    } else {
      // 新建模式：创建申请
      const created = await licenseApplicationApi.create(submitData)
      applicationId = created.id
    }
    
    // 2. 立即提交审批（一步完成）
    await licenseApplicationApi.submitApplication(applicationId)
    
    // 3. 显示成功提示
    ElMessage.success('License 申请已提交，等待审批')
    emit('success')
  } catch (error: any) {
    if (error !== false) {
      ElMessage.error(error.message || '操作失败')
    }
  } finally {
    loading.value = false
  }
}
```

**用户体验改进**：
- ✅ 点击"申请 License" → 填写表单 → 提交审批（一步完成）
- ✅ 提交后自动关闭对话框，显示成功提示
- ✅ 无需在列表中二次点击"提交"按钮

---

### Step 4：删除前端列表的冗余"提交"按钮

**文件**：`CRM-Client/src/components/LicenseManagement.vue`  
**修改内容**：删除表格中的"提交"操作按钮

```vue
<!-- ❌ 删除冗余的"提交"按钮 -->
<el-table-column label="操作" width="200" fixed="right">
  <template #default="{ row }">
    <el-button size="small" text @click="showApplicationDialog(row)" v-if="row.status === 'DRAFT'">编辑</el-button>
    <!-- 删除：<el-button size="small" text @click="handleSubmitApplication(row.id)" v-if="row.status === 'DRAFT'">提交</el-button> -->
    <el-button size="small" text type="danger" @click="handleDeleteApplication(row.id)" v-if="row.status === 'DRAFT'">删除</el-button>
  </template>
</el-table-column>
```

**同时删除相关函数**：

```typescript
// ❌ 删除冗余的 handleSubmitApplication 函数（第 211-222 行）
// const handleSubmitApplication = async (id: number) => { ... }
```

**状态流转说明**：
- DRAFT 状态：用户点击"编辑"按钮 → 打开对话框 → 可以编辑并提交审批
- PENDING 状态：等待审批（审批人可在审批中心看到）
- ISSUED 状态：审批通过，已发放 License

---

### Step 5：创建测试用例，验证完整流程

**文件**：`CRM-Server/tests/unit/test_license_approval.py`  
**测试内容**：

```python
"""License 申请审批流程测试"""
import pytest
from datetime import date

from app.crud.approval import approval_flow_crud, approval_crud
from app.crud.crud_license_application import license_application_crud
from app.constants.business_types import BusinessType
from app.models.license_application import LicenseApplicationStatus
from app.schemas.license_application import LicenseApplicationCreate


def test_license_approval_adapter_registered():
    """测试 License 适配器已注册"""
    from app.services.approval_adapter import get_adapter
    
    adapter = get_adapter(BusinessType.LICENSE)
    assert adapter.business_type == BusinessType.LICENSE
    assert hasattr(adapter, 'on_submit')
    assert hasattr(adapter, 'on_approved')


def test_license_application_submit_creates_approval(db, test_team, test_user, test_customer):
    """测试 License 提交时创建审批实例"""
    # 1. 创建审批流程配置（LICENSE 类型）
    flow = approval_flow_crud.create(
        db,
        ApprovalFlowCreate(
            flow_code="LICENSE_DEFAULT",
            flow_name="License申请审批",
            business_type=BusinessType.LICENSE,
            is_active=True,
            nodes=[
                ApprovalNodeCreate(
                    node_name="团队所有者审批",
                    node_order=1,
                    approve_role="TEAM_OWNER",
                )
            ]
        ),
        test_team.id
    )
    
    # 2. 创建 License 申请（草稿）
    application = license_application_crud.create(
        db,
        test_team.id,
        str(test_user.id),
        LicenseApplicationCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            expiry_date=date(2026, 12, 31),
            remark="测试申请"
        )
    )
    assert application.status == LicenseApplicationStatus.DRAFT
    
    # 3. 提交申请（接入审批引擎）
    adapter = get_adapter(BusinessType.LICENSE)
    matched_flow, err = approval_flow_crud.match_flow_generic(
        db, BusinessType.LICENSE, test_team.id,
        **adapter.match_kwargs(application)
    )
    assert matched_flow is not None
    assert err is None
    
    # 4. 创建审批实例
    approval = approval_crud.create_approval_generic(
        db,
        BusinessType.LICENSE,
        application.id,
        test_team.id,
        matched_flow,
        str(test_user.id),
        test_user.name,
    )
    
    # 5. 验证审批实例创建成功
    assert approval.id is not None
    assert approval.business_type == BusinessType.LICENSE
    assert approval.business_id == application.id
    assert approval.status == ApprovalStatus.PENDING
    
    # 6. 验证申请状态已切换为 PENDING
    db.refresh(application)
    assert application.status == LicenseApplicationStatus.PENDING


def test_license_approval_flow_visible_in_approval_center(db, test_team, test_user):
    """测试 License 审批在审批中心可见"""
    # 创建审批实例后，审批人可以在审批中心看到
    # ...
```

---

## 三、风险评估

### 风险 1：现有审批流程配置冲突

**风险描述**：如果用户已配置了其他业务类型的审批流程，可能与 LICENSE 流程冲突  
**影响范围**：审批流程匹配逻辑  
**缓解措施**：
- `match_flow_generic` 会按 `business_type` 过滤，不会跨类型匹配
- License 流程配置需明确指定 `business_type = 'LICENSE'`

### 风险 2：状态流转冲突

**风险描述**：原有 `approve_license_application` API 直接设置状态为 ISSUED，可能与适配器冲突  
**影响范围**：审批通过逻辑  
**缓解措施**：
- 适配器 `on_approved` 不修改状态（预留扩展）
- 审批通过时，仍使用原有 `approve_full` API 设置状态

### 风险 3：前端兼容性

**风险描述**：修改前端按钮文本后，用户可能困惑  
**影响范围**：用户体验  
**缓解措施**：
- 提供用户指引文档，说明新流程
- 提交后显示明确的成功提示

---

## 四、回退方案

如果修复后出现问题，可按以下步骤回退：

### 回退 Step 1：删除 License 适配器

```python
# 从 approval_adapter.py 删除 LicenseApplicationAdapter 类
# 从 _REGISTRY 删除 LICENSE 注册
del _REGISTRY[BusinessType.LICENSE]
```

### 回退 Step 2：恢复 License 提交 API

```python
# 恢复原有的 submit_license_application 函数
def submit_license_application(db, team_id, application_id):
    application = get_license_application(db, team_id, application_id)
    if application and application.status == LicenseApplicationStatus.DRAFT:
        application.status = LicenseApplicationStatus.PENDING
        db.commit()
        db.refresh(application)
    return application
```

### 回退 Step 3：恢复前端按钮文本

```vue
<!-- 恢复为"保存草稿" -->
<el-button type="primary" @click="handleSubmit" :loading="loading">保存草稿</el-button>
```

---

## 五、验证方案

### 验证步骤

1. **单元测试**：运行 `pytest tests/unit/test_license_approval.py -v`
2. **集成测试**：
   - 创建 License 申请（草稿）
   - 提交申请，验证审批实例创建
   - 在审批中心查看申请记录
3. **通知验证**：审批人收到飞书通知（待 Task A8 实现）
4. **端到端测试**：前端完整流程测试

### 验证检查点

| 检查项 | 验证方法 | 预期结果 |
|--------|---------|---------|
| 适配器注册 | `get_adapter('LICENSE')` | 返回 LicenseApplicationAdapter |
| 审批流程匹配 | `match_flow_generic('LICENSE', ...)` | 返回匹配的 ApprovalFlow |
| 审批实例创建 | 提交申请后查询 Approval 表 | 存在 business_type='LICENSE' 的记录 |
| 状态流转 | 提交后查询 application.status | 状态为 'PENDING' |
| 审批中心可见 | 审批人登录查看待审批列表 | License 申请出现在列表中 |
| 通知发送 | 审批人收到飞书消息 | 收到审批通知（待实现） |

---

## 六、实施时间表

| 步骤 | 预计耗时 | 备注 |
|------|---------|------|
| Step 1：创建适配器 | 15 分钟 | 后端核心修改 |
| Step 2：修改提交 API | 20 分钟 | 后端核心修改 |
| Step 3：修改前端对话框 | 10 分钟 | 前端修改 |
| Step 4：删除冗余按钮 | 5 分钟 | 前端清理 |
| Step 5：创建测试用例 | 15 分钟 | 测试验证 |
| **总计** | **65 分钟** | 约 1 小时 |

---

## 七、后续改进建议

### 短期改进（本次实施）

1. ✅ 接入审批引擎，创建审批实例
2. ✅ 修改前端流程，一步提交审批
3. ⚠️ 通知机制暂缓（等待 Task A8 泛化实现）

### 中期改进（后续迭代）

1. 实现飞书通知机制（Task A8 泛化）
2. 支持多级审批流程配置
3. 审批历史记录追踪（ApprovalRecord 表）

### 长期改进（架构优化）

1. 统一所有业务单据的审批流程（完全使用审批引擎）
2. 审批流程可视化配置界面
3. 审批流程监控和统计报表

---

## 八、审批确认

请确认以下内容后，我开始实施：

- [ ] 实施方案是否符合预期？
- [ ] 风险评估是否充分？
- [ ] 回退方案是否可行？
- [ ] 验证方案是否完整？
- [ ] 是否需要调整实施步骤？

**确认方式**：回复 "开始实施" 或提出修改建议。
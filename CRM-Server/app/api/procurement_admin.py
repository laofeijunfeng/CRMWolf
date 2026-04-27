from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission
from app.models.user import User
from app.schemas.procurement import (
    BatchMigrateProcurementMethodRequest,
    ImpactAssessmentResponse,
    MessageResponse
)
from app.crud.procurement import procurement_management_tool_crud


router = APIRouter(prefix="/api/v1/procurement-admin", tags=["采购管理工具"])


@router.get("/assess-template-change/{template_id}", response_model=ImpactAssessmentResponse, summary="评估阶段模板变更影响", description="""
评估修改阶段模板会影响的商机数量和详情。

**业务规则：**
- 返回所有使用该阶段的活跃商机
- 包括商机基本信息和当前阶段
- 帮助管理员了解修改的影响范围

**使用场景：**
- 修改阶段前评估影响
- 判断修改是否会负面影响现有商机

**权限要求：**
- 需要采购管理评估权限
""")
def assess_template_change_impact(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement:admin:assess"))
):
    try:
        impact = procurement_management_tool_crud.assess_template_change_impact(
            db, template_id
        )
        return ImpactAssessmentResponse(**impact)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/batch-migrate-opportunities", response_model=MessageResponse, summary="批量迁移商机采购方式", description="""
将使用源采购方式的商机批量迁移到目标采购方式。

**业务规则：**
- 只迁移跟进中（status=0）的商机
- 迁移后商机会进入目标方式的默认起始阶段
- 原阶段快照会被标记为已退出
- 支持全部迁移或指定商机ID列表
- 迁移失败不影响其他商机的迁移

**使用场景：**
- 采购方式调整，需要迁移现有商机
- 客户采购方式变更，需要同步商机

**权限要求：**
- 需要采购管理迁移权限
""")
def batch_migrate_opportunities(
    request: BatchMigrateProcurementMethodRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement:admin:migrate"))
):
    try:
        result = procurement_management_tool_crud.batch_migrate_procurement_method(
            db,
            request.source_method_id,
            request.target_method_id,
            request.opportunity_ids,
            current_user.feishu_open_id
        )
        
        return MessageResponse(
            message=f"批量迁移完成。总数: {result['total']}, "
                   f"成功: {result['migrated']}, "
                   f"失败: {result['failed']}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/rollback-template/{template_id}", response_model=MessageResponse, summary="回滚阶段模板到指定版本", description="""
将阶段模板回滚到指定的历史版本。

**业务规则：**
- 根据变更日志中的历史数据恢复模板
- 回滚会创建新的变更日志（ROLLBACK类型）
- 回滚后会更新版本号
- 需要提供目标版本号

**使用场景：**
- 修改后发现错误，需要回滚
- 需要恢复到之前的某个版本

**权限要求：**
- 需要采购管理回滚权限

**注意事项：**
- 回滚操作本身不可逆
- 建议先查看变更日志，确认目标版本
""")
def rollback_template_version(
    template_id: int,
    target_version: int = Query(..., ge=1, description="目标版本号"),
    reason: Optional[str] = Query(None, description="回滚原因"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement:admin:rollback"))
):
    try:
        rolled_back_template = procurement_management_tool_crud.rollback_template_version(
            db,
            template_id,
            target_version,
            current_user.feishu_open_id,
            reason
        )
        
        return MessageResponse(
            message=f"已回滚阶段模板到版本 {target_version}。"
                   f"当前版本: {rolled_back_template.version}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/active-opportunities/{stage_template_id}", summary="获取使用指定阶段的活跃商机", description="""
获取当前使用指定阶段模板的所有活跃商机列表。

**业务规则：**
- 只返回跟进中（status=0）的商机
- 只返回当前阶段使用该模板的商机
- 包括商机基本信息和当前阶段状态

**使用场景：**
- 查看某阶段的使用情况
- 修改阶段前了解影响范围

**权限要求：**
- 需要采购管理评估权限
""")
def get_active_opportunities_by_stage(
    stage_template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement:admin:assess"))
):
    opportunities = procurement_management_tool_crud.get_active_opportunities_by_stage(
        db, stage_template_id
    )
    
    return {
        "stage_template_id": stage_template_id,
        "active_opportunities": opportunities,
        "count": len(opportunities)
    }

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.operation_log import (
    OperationLogCreate,
    OperationLogResponse,
    OperationLogListResponse
)
from app.crud.operation_log import operation_log_crud

router = APIRouter(prefix="/operation-logs", tags=["操作记录"])


@router.post("", response_model=OperationLogResponse, status_code=status.HTTP_201_CREATED, summary="记录操作事件", description="内部接口，记录操作事件到审计日志")
def create_operation_log(
    log_data: OperationLogCreate,
    db: Session = Depends(get_db)
):
    try:
        log = operation_log_crud.create(db, log_data)
        return log
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"记录操作失败: {str(e)}"
        )


@router.get("", response_model=OperationLogListResponse, summary="获取资源操作记录", description="""
### 获取指定资源的操作记录时间线

此接口用于查询客户、线索、商机、合同等资源的操作历史记录，形成完整的操作时间线。

**主要用途：**
- 客户详情页展示客户生命周期中的所有操作记录
- 线索详情页展示线索的跟进历史和状态变更
- 合同详情页展示合同的审批流程和状态变更

**资源类型说明：**
| 资源类型 | 代码 | 说明 |
|---------|------|------|
| 线索 | `LEAD` | 线索相关的操作记录 |
| 客户 | `CUSTOMER` | 客户相关的操作记录 |
| 商机 | `OPPORTUNITY` | 商机相关的操作记录 |
| 合同 | `CONTRACT` | 合同相关的操作记录 |
| 发票 | `INVOICE` | 发票相关的操作记录 |
| 回款计划 | `PAYMENT_PLAN` | 回款计划相关的操作记录 |
| 回款记录 | `PAYMENT_RECORD` | 回款记录相关的操作记录 |

**事件类型说明：**
| 事件类型 | 代码 | 所属资源 |
|---------|------|---------|
| 创建线索 | `LEAD_CREATED` | LEAD |
| 线索转化 | `LEAD_CONVERTED` | LEAD |
| 创建客户 | `CUSTOMER_CREATED` | CUSTOMER |
| 手动跟进 | `MANUAL_FOLLOW_UP` | CUSTOMER |
| 创建商机 | `OPPORTUNITY_CREATED` | OPPORTUNITY |
| 创建合同 | `CONTRACT_CREATED` | CONTRACT |
| 合同状态变更 | `CONTRACT_STATUS_CHANGED` | CONTRACT |

**使用示例：**
```bash
# 查询客户ID为1的所有操作记录
GET /api/v1/operation-logs?primary_resource_type=CUSTOMER&primary_resource_id=1

# 查询客户ID为1的跟进记录和商机创建记录
GET /api/v1/operation-logs?primary_resource_type=CUSTOMER&primary_resource_id=1&event_types=MANUAL_FOLLOW_UP,OPPORTUNITY_CREATED

# 分页查询，每页10条
GET /api/v1/operation-logs?primary_resource_type=CUSTOMER&primary_resource_id=1&page_no=1&page_size=10
```

**响应字段说明：**
- `event_id`: 事件唯一标识
- `event_type`: 事件类型（如：MANUAL_FOLLOW_UP）
- `event_action`: 事件动作（如：CREATE、UPDATE）
- `operator_id`: 操作人飞书ID
- `operator_name`: 操作人姓名
- `operated_at`: 操作时间
- `content`: 事件详细内容（JSON格式）
- `remark`: 备注
""")
def get_operation_logs(
    primary_resource_type: str = Query(..., description="主资源类型（LEAD/CUSTOMER/OPPORTUNITY/CONTRACT/INVOICE/PAYMENT_PLAN/PAYMENT_RECORD）"),
    primary_resource_id: int = Query(..., gt=0, description="主资源ID（如：客户ID、线索ID等）"),
    event_types: Optional[str] = Query(None, description="事件类型过滤，多个用逗号分隔（如：MANUAL_FOLLOW_UP,OPPORTUNITY_CREATED）"),
    page_no: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，默认20条，最大100条"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    event_type_list = None
    if event_types:
        event_type_list = [t.strip() for t in event_types.split(",")]
    
    skip = (page_no - 1) * page_size
    
    try:
        logs, total = operation_log_crud.get_by_resource(
            db=db,
            primary_resource_type=primary_resource_type,
            primary_resource_id=primary_resource_id,
            skip=skip,
            limit=page_size,
            event_types=event_type_list
        )
        
        return OperationLogListResponse(
            list=logs,
            total=total,
            page_no=page_no,
            page_size=page_size
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询操作记录失败: {str(e)}"
        )


@router.get("/my-logs", response_model=OperationLogListResponse, summary="获取我的操作记录", description="""
### 获取当前登录用户的操作记录

此接口用于查询当前用户在系统中的所有操作历史，包括创建的线索、客户、跟进记录等。

**主要用途：**
- 个人中心展示我的操作历史
- 统计我的工作量和活跃度
- 回顾我的日常工作记录

**使用场景：**
- 销售人员查看自己今日/本周/本月的工作记录
- 管理层查看自己的审批记录
- 用户回顾自己的操作历史

**使用示例：**
```bash
# 查询我的所有操作记录
GET /api/v1/operation-logs/my-logs

# 分页查询，每页10条
GET /api/v1/operation-logs/my-logs?page_no=1&page_size=10
```

**返回记录说明：**
- 按操作时间倒序排列，最新的操作在前
- 包含所有资源类型的操作记录
- 自动根据当前登录用户的飞书ID进行筛选

**权限说明：**
- 只能查询自己的操作记录
- 无法查看其他用户的操作记录
""")
def get_my_operation_logs(
    page_no: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，默认20条，最大100条"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    skip = (page_no - 1) * page_size
    
    try:
        logs, total = operation_log_crud.get_by_operator(
            db=db,
            operator_id=current_user.feishu_open_id,
            skip=skip,
            limit=page_size
        )
        
        return OperationLogListResponse(
            list=logs,
            total=total,
            page_no=page_no,
            page_size=page_size
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询操作记录失败: {str(e)}"
        )

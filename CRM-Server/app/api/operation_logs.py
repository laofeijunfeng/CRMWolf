
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.operation_log import operation_log_crud
from app.models.user import User
from app.schemas.operation_log import OperationLogCreate, OperationLogListResponse, OperationLogResponse

router = APIRouter(prefix="/operation-logs", tags=["操作记录"])


@router.post(
    "",
    response_model=OperationLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="记录操作事件",
    description="内部接口\uff0c记录操作事件到审计日志",
)
def create_operation_log(
    log_data: OperationLogCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    try:
        log = operation_log_crud.create(db, log_data, team_id)
        return log
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"记录操作失败: {e!s}"
        )


@router.get("", response_model=OperationLogListResponse, summary="获取资源操作记录", description="""
### 获取指定资源的操作记录时间线

此接口用于查询客户、线索、商机、合同等资源的操作历史记录\uff0c形成完整的操作时间线。

**主要用途\uff1a**
- 客户详情页展示客户生命周期中的所有操作记录
- 线索详情页展示线索的跟进历史和状态变更
- 合同详情页展示合同的审批流程和状态变更

**资源类型说明\uff1a**
| 资源类型 | 代码 | 说明 |
|---------|------|------|
| 线索 | `LEAD` | 线索相关的操作记录 |
| 客户 | `CUSTOMER` | 客户相关的操作记录 |
| 商机 | `OPPORTUNITY` | 商机相关的操作记录 |
| 合同 | `CONTRACT` | 合同相关的操作记录 |
| 发票 | `INVOICE` | 发票相关的操作记录 |
| 回款计划 | `PAYMENT_PLAN` | 回款计划相关的操作记录 |
| 回款记录 | `PAYMENT_RECORD` | 回款记录相关的操作记录 |

**事件类型说明\uff1a**
| 事件类型 | 代码 | 所属资源 |
|---------|------|---------|
| 创建线索 | `LEAD_CREATED` | LEAD |
| 线索转化 | `LEAD_CONVERTED` | LEAD |
| 创建客户 | `CUSTOMER_CREATED` | CUSTOMER |
| 手动跟进 | `MANUAL_FOLLOW_UP` | CUSTOMER |
| 创建商机 | `OPPORTUNITY_CREATED` | OPPORTUNITY |
| 创建合同 | `CONTRACT_CREATED` | CONTRACT |
| 合同状态变更 | `CONTRACT_STATUS_CHANGED` | CONTRACT |

**使用示例\uff1a**
```bash
# 查询客户ID为1的所有操作记录
GET /api/v1/operation-logs?primary_resource_type=CUSTOMER&primary_resource_id=1

# 查询客户ID为1的跟进记录和商机创建记录
GET /api/v1/operation-logs?primary_resource_type=CUSTOMER&primary_resource_id=1\
&event_types=MANUAL_FOLLOW_UP,OPPORTUNITY_CREATED

# 分页查询\uff0c每页10条
GET /api/v1/operation-logs?primary_resource_type=CUSTOMER&primary_resource_id=1&page_no=1&page_size=10
```

**响应字段说明\uff1a**
- `event_id`: 事件唯一标识
- `event_type`: 事件类型\uff08如\uff1aMANUAL_FOLLOW_UP\uff09
- `event_action`: 事件动作\uff08如\uff1aCREATE、UPDATE\uff09
- `operator_id`: 操作人飞书ID
- `operator_name`: 操作人姓名
- `operated_at`: 操作时间
- `content`: 事件详细内容\uff08JSON格式\uff09
- `remark`: 备注
""")
def get_operation_logs(
    primary_resource_type: str = Query(
        ...,
        description="主资源类型\uff08LEAD/CUSTOMER/OPPORTUNITY/CONTRACT/INVOICE/PAYMENT_PLAN/PAYMENT_RECORD\uff09",
    ),
    primary_resource_id: int = Query(..., gt=0, description="主资源ID\uff08如\uff1a客户ID、线索ID等\uff09"),
    event_types: str | None = Query(
        None,
        description="事件类型过滤\uff0c多个用逗号分隔\uff08如\uff1aMANUAL_FOLLOW_UP,OPPORTUNITY_CREATED\uff09",
    ),
    page_no: int = Query(1, ge=1, description="页码\uff0c从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量\uff0c默认20条\uff0c最大100条"),
    team_id: int = Depends(get_current_user_team),
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
            team_id=team_id,
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
            detail=f"查询操作记录失败: {e!s}"
        )


@router.get("/my-logs", response_model=OperationLogListResponse, summary="获取我的操作记录", description="""
### 获取当前登录用户的操作记录

此接口用于查询当前用户在系统中的所有操作历史\uff0c包括创建的线索、客户、跟进记录等。

**主要用途\uff1a**
- 个人中心展示我的操作历史
- 统计我的工作量和活跃度
- 回顾我的日常工作记录

**使用场景\uff1a**
- 销售人员查看自己今日/本周/本月的工作记录
- 管理层查看自己的审批记录
- 用户回顾自己的操作历史

**使用示例\uff1a**
```bash
# 查询我的所有操作记录
GET /api/v1/operation-logs/my-logs

# 分页查询\uff0c每页10条
GET /api/v1/operation-logs/my-logs?page_no=1&page_size=10
```

**返回记录说明\uff1a**
- 按操作时间倒序排列\uff0c最新的操作在前
- 包含所有资源类型的操作记录
- 自动根据当前登录用户的飞书ID进行筛选

**权限说明\uff1a**
- 只能查询自己的操作记录
- 无法查看其他用户的操作记录
""")
def get_my_operation_logs(
    page_no: int = Query(1, ge=1, description="页码\uff0c从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量\uff0c默认20条\uff0c最大100条"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    skip = (page_no - 1) * page_size

    try:
        logs, total = operation_log_crud.get_by_operator(
            db=db,
            operator_id=str(current_user.id),
            team_id=team_id,
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
            detail=f"查询操作记录失败: {e!s}"
        )

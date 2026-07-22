from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import date
from urllib.parse import quote
import logging
import os

from app.core.database import get_db
from app.core.deps import (
    get_current_active_user,
    get_current_user_team,
    check_contract_edit_permission,
    check_contract_delete_permission,
    check_contract_view_permission,
    check_customer_edit_permission,
    check_customer_view_permission,
)
from app.crud.contract import contract_crud, ApprovalService
from app.crud.customer import customer_crud, contact_crud
from app.crud.opportunity import opportunity_crud
from app.crud.role import role_crud
from app.schemas.contract import (
    ContractCreate, ContractUpdate,
    ContractResponse, ContractListResponse, ContractDetailResponse,
    ContractStatusEnum, LicenseTypeEnum, MessageResponse
)
from app.schemas.common import PaginatedResponse
from app.services.approval_adapter import get_approval_customer_name, get_approval_type_name
from app.services.feishu_notification import feishu_notification_service
from app.services.file_storage import file_storage_service, FileStorageError
from app.models.approval import BusinessType

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/v1/contracts", tags=["合同管理"])


def _get_approvers_by_role(db: Session, role_code: Optional[str], team_id: int) -> list:
    if not role_code:
        return []

    role = role_crud.get_by_code(db, role_code)
    if not role:
        return []

    return role_crud.get_role_users(db, role.id, team_id)


def _get_notification_users_for_node(db: Session, node, team_id: int) -> list:
    if not node:
        return []

    approvers = _get_approvers_by_role(db, node.approve_role, team_id)
    notify_user_ids = node.notify_user_ids or []
    if not notify_user_ids:
        return approvers

    notify_id_set = {int(user_id) for user_id in notify_user_ids}
    return [user for user in approvers if int(user.id) in notify_id_set]


def _get_user_basic_info(db: Session, user_id: Optional[str]) -> Optional[dict]:
    if not user_id:
        return None

    user_data = db.execute(text("""
        SELECT id, name, email, mobile, avatar_url
        FROM users
        WHERE id = CAST(:user_id AS SIGNED)
    """), {"user_id": user_id}).first()

    if not user_data:
        return None

    return {
        "id": str(user_data[0]),
        "name": user_data[1],
        "email": user_data[2],
        "mobile": user_data[3],
        "avatar_url": user_data[4]
    }


def _contract_response_base(contract) -> dict:
    return {
        "id": contract.id,
        "contract_number": contract.contract_number,
        "contract_name": contract.contract_name,
        "customer_id": contract.customer_id,
        "opportunity_id": contract.opportunity_id,
        "signing_contact_id": contract.signing_contact_id,
        "user_count": contract.user_count,
        "total_amount": float(contract.total_amount),
        "license_type": contract.license_type,
        "subscription_years": contract.subscription_years,
        "standard_unit_price": float(contract.standard_unit_price),
        "status": contract.status,
        "signing_date": contract.signing_date,
        "effective_date": contract.effective_date,
        "expiry_date": contract.expiry_date,
        "owner_id": contract.owner_id,
        "creator_id": contract.creator_id,
        "created_time": contract.created_time,
        "last_modified_time": contract.last_modified_time,
        "contract_file_path": contract.contract_file_path,
        "contract_file_name": contract.contract_file_name,
        "contract_file_size": contract.contract_file_size,
        "contract_file_mime_type": contract.contract_file_mime_type,
    }


def _parse_contract_payload(contract_payload: str) -> ContractCreate:
    try:
        return ContractCreate.model_validate_json(contract_payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"合同参数格式错误：{e}",
        )


def _contract_file_content_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    content_type_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return content_type_map.get(ext, "application/octet-stream")


def _content_disposition(filename: str) -> str:
    safe_filename = os.path.basename(filename).replace("\r", "").replace("\n", "")
    fallback_name = safe_filename.encode("ascii", "ignore").decode("ascii") or "contract_file"
    quoted_name = quote(safe_filename, safe="")
    return f"attachment; filename=\"{fallback_name}\"; filename*=UTF-8''{quoted_name}"


@router.post("/", response_model=ContractResponse, status_code=status.HTTP_201_CREATED, summary="创建合同", description="""
手动创建新合同，系统自动生成合同编号并计算标准单价。

**功能说明：**
- 创建合同实例，自动生成唯一合同编号
- 根据合同金额、用户数、授权模式计算标准单价
- 根据授权模式和订阅年限计算到期日期
- 初始状态为草稿（DRAFT），可编辑

**业务场景：**
- 销售人员为客户创建合同
- 商务谈判达成后建立合同记录
""")
async def create_contract(
    contract_payload: str = Form(..., description="合同 JSON 数据"),
    file: UploadFile = File(..., description="合同邮件附件（PDF/DOCX，必传）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = _parse_contract_payload(contract_payload)
    file_content = await file.read()
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传合同邮件附件"
        )

    check_customer_edit_permission(contract.customer_id, team_id, current_user, db)

    opportunity = opportunity_crud.get_by_id(db, contract.opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    contact = contact_crud.get_by_id(db, contract.signing_contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )

    if contact.customer_id != contract.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="签约人不属于该客户"
        )

    if opportunity.customer_id != contract.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="商机关联的客户与合同客户不一致"
        )

    try:
        db_contract = contract_crud.create(
            db=db,
            obj_in=contract,
            creator_id=str(current_user.id),
            team_id=team_id
        )

        try:
            contract_file_path = file_storage_service.save_contract_file(
                team_id=team_id,
                contract_id=db_contract.id,
                filename=file.filename,
                content=file_content,
            )
        except FileStorageError as file_error:
            db.delete(db_contract)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(file_error)
            )

        db_contract.contract_file_path = contract_file_path
        db_contract.contract_file_name = file.filename
        db_contract.contract_file_size = len(file_content)
        db_contract.contract_file_mime_type = file.content_type
        db.commit()
        db.refresh(db_contract)

        # 提交审批并发送通知
        approval = ApprovalService.submit_for_approval(db, db_contract.id)
        if approval and approval.current_node:
            try:
                notify_users = _get_notification_users_for_node(db, approval.current_node, team_id)
                result = await feishu_notification_service.notify_approval_pending(
                    db=db,
                    team_id=team_id,
                    user_ids=[user.id for user in notify_users],
                    entity_type=BusinessType.CONTRACT,
                    entity_name=db_contract.contract_name,
                    flow_name=approval.flow.flow_name if approval.flow else "",
                    node_name=approval.current_node.node_name,
                    business_id=db_contract.id,
                    submitter_name=current_user.name,
                    approval_type_name=get_approval_type_name(BusinessType.CONTRACT),
                    customer_name=get_approval_customer_name(db, BusinessType.CONTRACT, db_contract),
                )
                logger.info(f"合同审批通知发送完成（contract_id={db_contract.id}, result={result}）")
            except Exception as notify_error:
                # 通知失败不阻断业务流程
                logger.error(f"合同审批通知发送失败（contract_id={db_contract.id}）: {notify_error}", exc_info=True)

        return db_contract
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/{contract_id}/file",
    summary="下载合同附件",
    description="下载或预览合同邮件附件。仅支持 PDF / DOCX。",
)
async def download_contract_file(
    contract_id: int,
    contract = Depends(check_contract_view_permission),
):
    if not contract.contract_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该合同未上传附件",
        )

    try:
        full_path = file_storage_service.get_full_path(contract.contract_file_path)
    except FileStorageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件路径非法",
        )

    if not os.path.exists(full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    with open(full_path, "rb") as f:
        content = f.read()

    filename = contract.contract_file_name or f"contract_{contract_id}{os.path.splitext(contract.contract_file_path)[1].lower()}"
    return Response(
        content=content,
        media_type=contract.contract_file_mime_type or _contract_file_content_type(contract.contract_file_path),
        headers={
            "Content-Disposition": _content_disposition(filename)
        },
    )


@router.post("/from-opportunity/{opportunity_id}", response_model=ContractResponse, status_code=status.HTTP_201_CREATED, summary="根据商机创建合同", description="""
从赢单商机快速创建合同，简化销售流程。

**功能说明：**
- 根据赢单商机快速生成合同
- 自动使用商机的实际成交金额
- 自动关联客户和签约联系人
- 生成的合同为草稿状态

**业务场景：**
- 商机赢单后直接生成合同
- 减少手动创建合同的工作量
""")
async def create_contract_from_opportunity(
    opportunity_id: int,
    contract_name: str = Form(..., description="合同名称，如：XX公司软件采购合同"),
    signing_contact_id: int = Form(..., description="签约联系人ID，必须是该商机的客户下的联系人"),
    file: UploadFile = File(..., description="合同邮件附件（PDF/DOCX，必传）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.opportunity import OpportunityStatus

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    if opportunity.status != OpportunityStatus.WON.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能从赢单商机创建合同"
        )

    file_content = await file.read()
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传合同邮件附件"
        )

    contact = contact_crud.get_by_id(db, signing_contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )

    if contact.customer_id != opportunity.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="签约人不属于该商机关联的客户"
        )

    try:
        db_contract = contract_crud.create_from_opportunity(
            db=db,
            opportunity_id=opportunity_id,
            customer_id=opportunity.customer_id,
            signing_contact_id=signing_contact_id,
            contract_name=contract_name,
            creator_id=str(current_user.id),
            team_id=team_id
        )

        try:
            contract_file_path = file_storage_service.save_contract_file(
                team_id=team_id,
                contract_id=db_contract.id,
                filename=file.filename,
                content=file_content,
            )
        except FileStorageError as file_error:
            db.delete(db_contract)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(file_error)
            )

        db_contract.contract_file_path = contract_file_path
        db_contract.contract_file_name = file.filename
        db_contract.contract_file_size = len(file_content)
        db_contract.contract_file_mime_type = file.content_type
        db.commit()
        db.refresh(db_contract)

        # 提交审批并发送通知
        approval = ApprovalService.submit_for_approval(db, db_contract.id)
        if approval and approval.current_node:
            try:
                notify_users = _get_notification_users_for_node(db, approval.current_node, team_id)
                result = await feishu_notification_service.notify_approval_pending(
                    db=db,
                    team_id=team_id,
                    user_ids=[user.id for user in notify_users],
                    entity_type=BusinessType.CONTRACT,
                    entity_name=db_contract.contract_name,
                    flow_name=approval.flow.flow_name if approval.flow else "",
                    node_name=approval.current_node.node_name,
                    business_id=db_contract.id,
                    submitter_name=current_user.name,
                    approval_type_name=get_approval_type_name(BusinessType.CONTRACT),
                    customer_name=get_approval_customer_name(db, BusinessType.CONTRACT, db_contract),
                )
                logger.info(f"合同审批通知发送完成（contract_id={db_contract.id}, result={result}）")
            except Exception as notify_error:
                # 通知失败不阻断业务流程
                logger.error(f"合同审批通知发送失败（contract_id={db_contract.id}）: {notify_error}", exc_info=True)

        return db_contract
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=PaginatedResponse[ContractListResponse], summary="查询合同列表", description="""
查询合同列表，支持多条件筛选和分页。

**功能说明：**
- 支持分页查询合同列表
- 可按客户、状态、授权模式等多条件筛选
- 返回合同及其关联的客户、商机、创建人信息

**业务场景：**
- 查看所有合同
- 按客户筛选合同
- 按状态筛选待处理、已生效等合同
""")
def get_contracts(
    skip: int = Query(0, ge=0, description="分页跳过记录数，从0开始，默认为0表示第一页"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数，默认100，最大100"),
    customer_id: Optional[int] = Query(None, description="按客户ID筛选，传入客户ID后只返回该客户的合同"),
    contract_status: Optional[str] = Query(None, alias="status", description="按合同状态筛选，多个值用逗号分隔"),
    status_exclude: Optional[str] = Query(None, description="排除的合同状态，多个值用逗号分隔"),
    license_type: Optional[str] = Query(None, description="按授权模式筛选，多个值用逗号分隔"),
    license_type_exclude: Optional[str] = Query(None, description="排除的授权模式，多个值用逗号分隔"),
    contract_number: Optional[str] = Query(None, description="按合同编号模糊搜索，支持部分匹配"),
    keyword: Optional[str] = Query(None, description="关键词搜索，可搜索合同名称、合同编号等字段"),
    customer_keyword: Optional[str] = Query(None, description="客户名称关键词"),
    opportunity_keyword: Optional[str] = Query(None, description="商机名称关键词"),
    owner_id: Optional[str] = Query(None, description="按合同负责人ID筛选"),
    owner_id_exclude: Optional[str] = Query(None, description="排除的合同负责人ID，多个值用逗号分隔"),
    signing_date_start: Optional[date] = Query(None, description="签署日期起始"),
    signing_date_end: Optional[date] = Query(None, description="签署日期结束"),
    effective_date_start: Optional[date] = Query(None, description="生效日期起始"),
    effective_date_end: Optional[date] = Query(None, description="生效日期结束"),
    expiry_date_start: Optional[date] = Query(None, description="到期日期起始"),
    expiry_date_end: Optional[date] = Query(None, description="到期日期结束"),
    order_by: Optional[str] = Query(None, description="排序字段"),
    order_dir: Optional[str] = Query(None, description="排序方向（asc/desc）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "contract:view:all" in permission_codes

    # 权限验证：如果指定了其他人的 owner_id，必须有 view:all 权限
    actual_owner_id = owner_id
    requested_owner_ids = [item.strip() for item in actual_owner_id.split(",") if item.strip()] if actual_owner_id else []
    if requested_owner_ids and any(item != str(current_user.id) for item in requested_owner_ids):
        if not has_view_all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能查看自己负责的合同，或需要 contract:view:all 权限查看他人数据"
            )

    # 如果前端未指定 owner_id 且没有 view:all 权限，则限制为只看自己的合同
    if actual_owner_id is None and not has_view_all:
        actual_owner_id = str(current_user.id)

    contracts, total = contract_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        customer_id=customer_id,
        status=contract_status,
        status_exclude=status_exclude,
        license_type=license_type,
        license_type_exclude=license_type_exclude,
        contract_number=contract_number,
        keyword=keyword,
        customer_keyword=customer_keyword,
        opportunity_keyword=opportunity_keyword,
        owner_id=actual_owner_id,
        owner_id_exclude=owner_id_exclude,
        signing_date_start=signing_date_start,
        signing_date_end=signing_date_end,
        effective_date_start=effective_date_start,
        effective_date_end=effective_date_end,
        expiry_date_start=expiry_date_start,
        expiry_date_end=expiry_date_end,
        order_by=order_by,
        order_dir=order_dir
    )
    
    result = []
    for contract in contracts:
        customer_info = None
        if contract.customer_id:
            customer_data = db.execute(text("""
                SELECT id, account_name
                FROM crm_customers
                WHERE id = :customer_id
            """), {"customer_id": contract.customer_id}).first()
            
            if customer_data:
                customer_info = {
                    "id": customer_data[0],
                    "account_name": customer_data[1]
                }
        
        opportunity_info = None
        if contract.opportunity_id:
            opportunity_data = db.execute(text("""
                SELECT id, opportunity_name
                FROM crm_opportunities
                WHERE id = :opportunity_id
            """), {"opportunity_id": contract.opportunity_id}).first()
            
            if opportunity_data:
                opportunity_info = {
                    "id": opportunity_data[0],
                    "opportunity_name": opportunity_data[1]
                }
        
        contract_dict = _contract_response_base(contract)
        contract_dict.update({
            "customer_info": customer_info,
            "opportunity_info": opportunity_info,
            "owner_info": _get_user_basic_info(db, contract.owner_id),
            "creator_info": _get_user_basic_info(db, contract.creator_id)
        })
        
        result.append(ContractListResponse(**contract_dict))
    
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[ContractListResponse](
        items=result,
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


@router.get("/opportunity/{opportunity_id}", response_model=ContractListResponse, summary="根据商机获取合同", description="""
获取指定商机关联的合同信息。

**功能说明：**
- 根据商机ID查询其关联的合同
- 返回合同的完整列表信息

**业务场景：**
- 在商机详情页查看关联的合同
- 确认商机是否已生成合同
- 了解商机的合同转化情况
""")
def get_contract_by_opportunity(
    opportunity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = contract_crud.get_by_opportunity_id(db, opportunity_id, team_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该商机暂无合同"
        )

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )
    
    customer_info = None
    if contract.customer_id:
        customer_data = db.execute(text("""
            SELECT id, account_name
            FROM crm_customers
            WHERE id = :customer_id
        """), {"customer_id": contract.customer_id}).first()
        
        if customer_data:
            customer_info = {
                "id": customer_data[0],
                "account_name": customer_data[1]
            }
    
    opportunity_info = {
        "id": opportunity.id,
        "opportunity_name": opportunity.opportunity_name
    }
    
    contract_dict = _contract_response_base(contract)
    contract_dict.update({
        "customer_info": customer_info,
        "opportunity_info": opportunity_info,
        "owner_info": _get_user_basic_info(db, contract.owner_id),
        "creator_info": _get_user_basic_info(db, contract.creator_id)
    })
    
    return ContractListResponse(**contract_dict)


@router.get("/{contract_id}", response_model=ContractDetailResponse, summary="获取合同详情", description="""
获取指定合同的完整详情，包括关联的客户、商机、联系人等信息。

**功能说明：**
- 返回合同的完整信息
- 包含关联的客户、商机、签约联系人、创建人详情
- 支持查看合同的完整上下文信息

**业务场景：**
- 查看合同详情
- 核对合同关联信息
- 了解合同的完整上下文
""")
def get_contract(
    contract_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = check_contract_view_permission(contract_id, team_id, current_user, db)
    
    customer_info = None
    if contract.customer_id:
        customer_data = db.execute(text("""
            SELECT id, account_name
            FROM crm_customers
            WHERE id = :customer_id
        """), {"customer_id": contract.customer_id}).first()
        
        if customer_data:
            customer_info = {
                "id": customer_data[0],
                "account_name": customer_data[1]
            }
    
    opportunity_info = None
    if contract.opportunity_id:
        opportunity_data = db.execute(text("""
            SELECT id, opportunity_name
            FROM crm_opportunities
            WHERE id = :opportunity_id
        """), {"opportunity_id": contract.opportunity_id}).first()
        
        if opportunity_data:
            opportunity_info = {
                "id": opportunity_data[0],
                "opportunity_name": opportunity_data[1]
            }
    
    contact_info = None
    if contract.signing_contact_id:
        contact_data = db.execute(text("""
            SELECT id, name, mobile
            FROM crm_contacts
            WHERE id = :contact_id
        """), {"contact_id": contract.signing_contact_id}).first()
        
        if contact_data:
            contact_info = {
                "id": contact_data[0],
                "name": contact_data[1],
                "mobile": contact_data[2]
            }
    
    contract_dict = _contract_response_base(contract)
    contract_dict.update({
        "customer_info": customer_info,
        "opportunity_info": opportunity_info,
        "contact_info": contact_info,
        "owner_info": _get_user_basic_info(db, contract.owner_id),
        "creator_info": _get_user_basic_info(db, contract.creator_id)
    })
    
    return ContractDetailResponse(**contract_dict)


@router.get("/customer/{customer_id}", response_model=List[ContractListResponse], summary="获取客户合同列表", description="""
获取指定客户的所有合同记录。

**功能说明：**
- 按客户ID筛选该客户的所有合同
- 支持分页和状态筛选
- 返回合同及客户基本信息

**业务场景：**
- 在客户详情页查看该客户的合同列表
- 了解客户的历史合同情况
- 按状态查看客户的不同阶段合同
""")
def get_customer_contracts(
    customer_id: int,
    skip: int = Query(0, ge=0, description="分页跳过记录数，从0开始"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数，默认100，最大100"),
    status: Optional[ContractStatusEnum] = Query(None, description="按合同状态筛选，可选值：DRAFT(草稿)、PENDING_REVIEW(待审核)、SIGNED(已签署)、EFFECTIVE(已生效)、EXPIRED(已到期)、TERMINATED(已终止)"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    
    contracts, total = contract_crud.get_by_customer_id(
        db=db,
        customer_id=customer_id,
        team_id=team_id,
        skip=skip,
        limit=limit,
        status=status
    )
    
    result = []
    for contract in contracts:
        customer_info = {
            "id": customer.id,
            "account_name": customer.account_name
        }
        
        opportunity_info = None
        if contract.opportunity_id:
            opportunity_data = db.execute(text("""
                SELECT id, opportunity_name
                FROM crm_opportunities
                WHERE id = :opportunity_id
            """), {"opportunity_id": contract.opportunity_id}).first()
            
            if opportunity_data:
                opportunity_info = {
                    "id": opportunity_data[0],
                    "opportunity_name": opportunity_data[1]
                }
        
        contract_dict = _contract_response_base(contract)
        contract_dict.update({
            "customer_info": customer_info,
            "opportunity_info": opportunity_info,
            "owner_info": _get_user_basic_info(db, contract.owner_id),
            "creator_info": _get_user_basic_info(db, contract.creator_id)
        })
        
        result.append(ContractListResponse(**contract_dict))
    
    return result


@router.put("/{contract_id}", response_model=ContractResponse, summary="编辑合同", description="""
更新合同信息，仅草稿状态的合同可编辑。

**功能说明：**
- 修改草稿状态的合同信息
- 支持修改合同基本信息
- 修改后自动重新计算标准单价和到期日期

**业务场景：**
- 草拟阶段修改合同内容
- 调整合同金额或其他条款

**业务规则：**
- 只能编辑草稿（DRAFT）状态的合同
- 不能修改客户ID、商机ID等核心关联关系
- 修改金额或用户数会自动重新计算标准单价

**注意事项：**
- 已提交审批或已生效的合同不可编辑
- 修改后标准单价会自动更新
""")
def update_contract(
    contract_id: int,
    contract_update: ContractUpdate,
    contract = Depends(check_contract_edit_permission),
    db: Session = Depends(get_db)
):
    # check_contract_edit_permission 已处理存在性和权限检查
    # 这里只需检查状态
    
    from app.models.contract import ContractStatus
    if contract.status != ContractStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能编辑草稿状态的合同"
        )
    
    try:
        updated_contract = contract_crud.update(
            db=db,
            db_obj=contract,
            obj_in=contract_update
        )
        return updated_contract
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{contract_id}", response_model=MessageResponse, summary="删除合同", description="""
删除指定合同，仅草稿状态的合同可删除。

**功能说明：**
- 删除草稿状态的合同
- 删除后不可恢复，请谨慎操作

**业务场景：**
- 删除错误的草稿合同
- 清理无效的合同数据

**业务规则：**
- 只能删除草稿（DRAFT）状态的合同
- 已提交审批或已生效的合同不可删除

**注意事项：**
- 删除操作不可逆，请谨慎
- 建议在删除前确认合同状态
- 删除后合同相关的回款计划也会被清理
""")
def delete_contract(
    contract_id: int,
    contract = Depends(check_contract_delete_permission),
    db: Session = Depends(get_db)
):
    # check_contract_delete_permission 已处理存在性和权限检查
    # 这里只需检查状态
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )
    
    try:
        contract_crud.delete(db, contract_id)
        return MessageResponse(message="合同删除成功")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

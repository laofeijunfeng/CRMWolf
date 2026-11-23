"""License 申请 CRUD 模块

提供 License 申请的数据库操作。
"""

from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.crud.product_intent import resolve_writable_product
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.deployment import DeploymentInfo
from app.models.license_application import LicenseApplication, LicenseApplicationStatus, LicenseType
from app.models.opportunity import Opportunity
from app.models.product import Product
from app.schemas.license_application import (
    LicenseApplicationApprove,
    LicenseApplicationApproveFull,
    LicenseApplicationInternalCreate,
    LicenseApplicationUpdate,
    resolve_license_term,
)
from app.services.business_number_generator import BusinessNumberGenerator
from app.utils.approval_delete_guard import assert_deletable_approval_resource
from app.utils.time import business_now


def parse_license_info(license_text: str) -> dict[str, str]:
    """
    解析审批人回填的 License 信息文本

    格式示例\uff1a
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

    Args:
        license_text: 审批人粘贴的完整 License 信息文本

    Returns:
        Dict[str, str]: 解析后的字段字典\uff0c包含:
            - enterprise_id: 企业编号
            - supported_modules: 支持模块
            - server_license_code: 服务端 License
            - client_license_code: 客户端 License
    """
    lines = license_text.strip().split('\n')
    data: dict[str, str] = {}

    for i, line in enumerate(lines):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()

            if key == '企业编号':
                data['enterprise_id'] = value
            elif key == '支持模块':
                data['supported_modules'] = value
            elif key in ('服务器端 License', '服务端 License'):
                # 服务器端 License 可能是多行,收集后续所有行直到遇到"客户端 License"
                server_license_lines = [value] if value else []
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line.startswith('客户端 License'):
                        break
                    if next_line:
                        server_license_lines.append(next_line)
                data['server_license_code'] = '\n'.join(server_license_lines)
            elif key in ('客户端 License',):
                # 客户端 License 可能是多行,收集后续所有行
                client_license_lines = [value] if value else []
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith('企业') and ':' not in next_line[:10]:
                        client_license_lines.append(next_line)
                    elif next_line and ':' in next_line[:10]:
                        break
                data['client_license_code'] = '\n'.join(client_license_lines)

    return data


class LicenseApplicationCRUD:
    """License 申请 CRUD 操作类"""

    def generate_application_number(self, db: Session) -> str:
        """
        生成申请单号\uff1aLICYYYYMMDDXXXX

        Args:
            db: 数据库会话

        Returns:
            str: 生成的申请单号
        """
        return BusinessNumberGenerator.generate('LIC', db)

    def create(
        self,
        db: Session,
        team_id: int,
        applicant_id: str,
        obj_in: LicenseApplicationInternalCreate
    ) -> LicenseApplication:
        """
        创建 License 申请

        Args:
            db: 数据库会话
            team_id: 团队ID
            applicant_id: 申请人系统用户ID
            obj_in: 创建请求数据

        Returns:
            LicenseApplication: 创建的申请

        Raises:
            ValueError: 客户不存在或合同不存在
        """
        # 验证客户存在
        customer = db.query(Customer).filter(
            Customer.id == obj_in.customer_id,
            Customer.team_id == team_id
        ).first()
        if not customer:
            raise ValueError("客户不存在")

        # 验证部署信息存在(如果提供)
        if obj_in.deployment_info_id:
            deployment = db.query(DeploymentInfo).filter(
                DeploymentInfo.id == obj_in.deployment_info_id,
                DeploymentInfo.team_id == team_id,
                DeploymentInfo.customer_id == customer.id
            ).first()
            if not deployment:
                raise ValueError("部署信息不存在或不属于该客户")

        # 验证合同存在(如果提供)
        contract: Contract | None = None
        if obj_in.contract_id:
            contract = db.query(Contract).filter(
                Contract.id == obj_in.contract_id,
                Contract.team_id == team_id,
                Contract.customer_id == customer.id
            ).first()
            if not contract:
                raise ValueError("合同不存在或不属于该客户")

        product = self._resolve_product(db, team_id, obj_in, contract)

        # 生成申请单号
        application_number = self.generate_application_number(db)

        # 创建申请
        db_obj = LicenseApplication(
            team_id=team_id,
            application_number=application_number,
            customer_id=customer.id,
            deployment_info_id=obj_in.deployment_info_id,
            contract_id=obj_in.contract_id,
            product_id=product.id,
            product_name=product.name,
            expiry_date=obj_in.expiry_date,
            is_permanent=obj_in.is_permanent,
            license_type=obj_in.license_type.value,
            authorized_users=obj_in.authorized_users,
            remark=obj_in.remark,  # 补充需求:备注字段
            applicant_id=applicant_id,
            status=LicenseApplicationStatus.DRAFT
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def _resolve_product(
        db: Session,
        team_id: int,
        obj_in: LicenseApplicationInternalCreate,
        contract: Contract | None,
    ) -> Product:
        """正式版跟随合同对应商机的产品\uff08历史成交事实\uff0c不校验启用状态\uff09\uff1b否则按申请人选择解析。"""
        if obj_in.license_type == LicenseType.OFFICIAL and contract is not None:
            derived = (
                db.query(Product)
                .join(Opportunity, Opportunity.product_id == Product.id)
                .filter(
                    Opportunity.id == contract.opportunity_id,
                    Opportunity.team_id == team_id,
                    Product.team_id == team_id,
                )
                .first()
            )
            if derived is not None:
                return derived
        return resolve_writable_product(db, team_id, obj_in.product_public_id)

    def get(
        self,
        db: Session,
        team_id: int,
        application_id: int
    ) -> LicenseApplication | None:
        """
        获取单个 License 申请

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID

        Returns:
            Optional[LicenseApplication]: 申请\uff0c不存在则返回 None
        """
        return db.query(LicenseApplication).filter(
            LicenseApplication.id == application_id,
            LicenseApplication.team_id == team_id
        ).first()

    def get_by_application_number(
        self,
        db: Session,
        team_id: int,
        application_number: str
    ) -> LicenseApplication | None:
        """
        根据申请单号获取申请

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_number: 申请单号

        Returns:
            Optional[LicenseApplication]: 申请\uff0c不存在则返回 None
        """
        return db.query(LicenseApplication).filter(
            LicenseApplication.application_number == application_number,
            LicenseApplication.team_id == team_id
        ).first()

    def get_by_customer(
        self,
        db: Session,
        team_id: int,
        customer_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[list[LicenseApplication], int]:
        """
        获取客户的 License 申请列表

        Args:
            db: 数据库会话
            team_id: 团队ID
            customer_id: 客户ID
            skip: 跳过记录数
            limit: 返回记录数上限

        Returns:
            Tuple[List[LicenseApplication], int]: 申请列表和总数
        """
        query = db.query(LicenseApplication).filter(
            LicenseApplication.team_id == team_id,
            LicenseApplication.customer_id == customer_id
        )

        total = query.count()
        applications = query.order_by(
            LicenseApplication.created_time.desc()
        ).offset(skip).limit(limit).all()

        return applications, total

    def list_applications(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        customer_id: int | None = None,
        status: str | None = None,
        applicant_id: str | None = None
    ) -> tuple[list[LicenseApplication], int]:
        """
        获取 License 申请列表

        Args:
            db: 数据库会话
            team_id: 团队ID
            skip: 跳过记录数
            limit: 返回记录数上限
            customer_id: 客户ID\uff08可选\uff09
            status: 申请状态\uff08可选\uff09
            applicant_id: 申请人ID\uff08可选\uff09

        Returns:
            Tuple[List[LicenseApplication], int]: 申请列表和总数
        """
        query = db.query(LicenseApplication).filter(
            LicenseApplication.team_id == team_id
        )

        if customer_id:
            query = query.filter(LicenseApplication.customer_id == customer_id)

        if status:
            query = query.filter(LicenseApplication.status == status)

        if applicant_id:
            query = query.filter(LicenseApplication.applicant_id == applicant_id)

        total = query.count()
        applications = query.order_by(
            LicenseApplication.created_time.desc()
        ).offset(skip).limit(limit).all()

        return applications, total

    def update(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        obj_in: LicenseApplicationUpdate
    ) -> LicenseApplication | None:
        """
        更新 License 申请\uff08仅 DRAFT 状态\uff09

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            obj_in: 更新请求数据

        Returns:
            Optional[LicenseApplication]: 更新后的申请\uff0c不存在或状态不对则返回 None

        Raises:
            ValueError: 申请状态不是 DRAFT 或部署信息/合同不存在
        """
        application = self.get(db, team_id, application_id)
        if not application:
            return None

        # 仅 DRAFT 状态可编辑
        if application.status != LicenseApplicationStatus.DRAFT:
            raise ValueError("只有草稿状态的申请可以编辑")

        update_data = obj_in.model_dump(exclude_unset=True)

        # 期限跨字段校验:以已存储的 license_type 为准(License 类型不可编辑)
        if 'is_permanent' in update_data or 'expiry_date' in update_data:
            is_permanent = update_data.get('is_permanent')
            if is_permanent is None:
                is_permanent = bool(application.is_permanent)
            expiry_date = update_data.get('expiry_date', application.expiry_date)
            update_data['is_permanent'] = is_permanent
            update_data['expiry_date'] = resolve_license_term(
                application.license_type, is_permanent, expiry_date
            )

        # 验证部署信息存在(如果提供)
        if update_data.get('deployment_info_id'):
            deployment = db.query(DeploymentInfo).filter(
                DeploymentInfo.id == update_data['deployment_info_id'],
                DeploymentInfo.team_id == team_id,
                DeploymentInfo.customer_id == application.customer_id
            ).first()
            if not deployment:
                raise ValueError("部署信息不存在或不属于该客户")

        # 验证合同存在(如果提供)
        if update_data.get('contract_id'):
            contract = db.query(Contract).filter(
                Contract.id == update_data['contract_id'],
                Contract.team_id == team_id,
                Contract.customer_id == application.customer_id
            ).first()
            if not contract:
                raise ValueError("合同不存在或不属于该客户")

        for field, value in update_data.items():
            setattr(application, field, value)

        db.commit()
        db.refresh(application)
        return application

    def delete(
        self,
        db: Session,
        team_id: int,
        application_id: int
    ) -> bool:
        """
        删除 License 申请\uff08仅 DRAFT 状态\uff09

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID

        Returns:
            bool: 是否成功删除

        Raises:
            ValueError: 申请状态不是 DRAFT
        """
        application = self.get(db, team_id, application_id)
        if not application:
            return False

        assert_deletable_approval_resource(
            db,
            resource=application,
            business_type=BusinessType.LICENSE,
            business_id=application_id,
            team_id=team_id,
            resource_name="License申请",
            locked_business_statuses=(
                LicenseApplicationStatus.PENDING_REVIEW,
                LicenseApplicationStatus.APPROVED,
                LicenseApplicationStatus.ISSUED,
            ),
        )

        # 仅 DRAFT 状态可删除
        if application.status != LicenseApplicationStatus.DRAFT:
            raise ValueError("只有草稿状态的申请可以删除")

        db.delete(application)
        db.commit()
        return True

    def submit(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        submitter_id: str,
        submitter_name: str | None = None
    ) -> LicenseApplication | None:
        """
        提交 License 申请\uff08接入审批引擎\uff09

        流程\uff1a
        1. 验证申请存在且状态为 DRAFT
        2. 匹配审批流程\uff08按 license_type\uff09
        3. 创建审批实例\uff08Approval + ApprovalRecord\uff09
        4. 更新申请状态为 PENDING

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            submitter_id: 提交人系统用户ID
            submitter_name: 提交人姓名\uff08可选\uff09

        Returns:
            Optional[LicenseApplication]: 更新后的申请

        Raises:
            ValueError: 申请状态不是 DRAFT 或审批流程未匹配
        """
        from app.constants.business_types import BusinessType
        from app.crud.approval import approval_flow_crud
        from app.services.approval_adapter import get_adapter

        application = self.get(db, team_id, application_id)
        if not application:
            return None

        # 仅 DRAFT 状态可提交
        if application.status != LicenseApplicationStatus.DRAFT:
            raise ValueError("只有草稿状态的申请可以提交")

        # 获取适配器
        adapter = get_adapter(BusinessType.LICENSE)

        # 匹配审批流程
        flow, err = approval_flow_crud.match_flow_generic(
            db,
            BusinessType.LICENSE,
            team_id,
            **adapter.match_kwargs(application)
        )

        if flow is None:
            # 未匹配审批流程:保留草稿并提示管理员配置审批流程
            raise ValueError(err or "请先配置审批流程")

        # 使用 ApprovalTransactionManager 统一管理事务边界
        from app.services.approval_transaction_manager import approval_transaction_manager
        _approval, error_msg = approval_transaction_manager.submit_for_approval(
            db,
            BusinessType.LICENSE,
            application_id,
            team_id,
            submitter_id,
            submitter_name or ""
        )

        if error_msg and error_msg != "审批已在处理中":
            raise ValueError(error_msg)

        db.refresh(application)
        return application

    def _lock_issue_customer(self, db: Session, team_id: int, application_id: int) -> int | None:
        with db.no_autoflush:
            customer_id = db.query(LicenseApplication.customer_id).filter_by(
                id=application_id, team_id=team_id,
            ).scalar()
        return int(customer_id) if customer_id is not None else None

    def _ensure_approved_for_issue(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        customer_id: int | None,
    ) -> LicenseApplication | None:
        """Check the current approval and application while holding the customer lock."""
        from app.models.approval import Approval, ApprovalStatus

        if customer_id is None:
            return None

        # Approval writers lock Customer -> Approval -> LicenseApplication.
        # Lock in the same order and bypass any older RR identity-map values.
        with db.no_autoflush:
            approval = db.query(Approval).filter_by(
                business_type=BusinessType.LICENSE, business_id=application_id, team_id=team_id,
            ).order_by(Approval.id.desc()).populate_existing().with_for_update().first()
        if not approval or approval.status != ApprovalStatus.APPROVED:
            raise ValueError("License申请未通过审批\uff0c不可发放")
        with db.no_autoflush:
            application = db.query(LicenseApplication).filter_by(
                id=application_id, team_id=team_id,
            ).populate_existing().with_for_update().one_or_none()
        if application is None or int(application.customer_id) != customer_id:
            raise ValueError("License申请所属客户已变更\uff0c请重试")

        if application.status == LicenseApplicationStatus.ISSUED:
            raise ValueError("License申请已发放")

        return application

    def issue(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        issue_data: LicenseApplicationApprove,
        issuer_id: str
    ) -> LicenseApplication | None:
        """发放已审批通过的 License 申请\uff08简化版本\uff09。"""
        customer_id = self._lock_issue_customer(db, team_id, application_id)
        application = self._ensure_approved_for_issue(db, team_id, application_id, customer_id)
        if not application:
            return None

        application.status = LicenseApplicationStatus.ISSUED
        application.license_code = issue_data.license_code
        application.approver_id = issuer_id
        application.approved_time = business_now()

        self.update_customer_license_info(db, team_id, application, commit=False)
        db.commit()
        db.refresh(application)

        return application

    def issue_full(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        issue_data: LicenseApplicationApproveFull,
        issuer_id: str
    ) -> LicenseApplication | None:
        """发放已审批通过的 License 申请\uff08完整版本\uff0c解析 License 信息\uff09。"""
        customer_id = self._lock_issue_customer(db, team_id, application_id)
        application = self._ensure_approved_for_issue(db, team_id, application_id, customer_id)
        if not application:
            return None

        parsed_data = parse_license_info(issue_data.license_info)

        application.status = LicenseApplicationStatus.ISSUED
        application.enterprise_id = parsed_data.get('enterprise_id')
        application.supported_modules = parsed_data.get('supported_modules')
        application.server_license_code = parsed_data.get('server_license_code')
        application.client_license_code = parsed_data.get('client_license_code')
        application.approver_id = issuer_id
        application.approved_time = business_now()

        self.update_customer_license_info(db, team_id, application, commit=False)
        db.commit()
        db.refresh(application)

        return application

    def approve(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        approve_data: LicenseApplicationApprove,
        approver_id: str
    ) -> LicenseApplication | None:
        raise ValueError("License审批请使用通用审批接口\uff0c审批通过后调用发放接口")

    def approve_full(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        approve_data: LicenseApplicationApproveFull,
        approver_id: str
    ) -> LicenseApplication | None:
        raise ValueError("License审批请使用通用审批接口\uff0c审批通过后调用发放接口")

    def reject(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        reason: str
    ) -> LicenseApplication | None:
        raise ValueError("License驳回请使用通用审批接口")

    def update_customer_license_info(
        self,
        db: Session,
        team_id: int,
        issued_application: LicenseApplication,
        *,
        commit: bool = True,
    ) -> None:
        """
        Recompute and persist the customer's License snapshot from the winning issued application.

        The customer row is locked before selecting the single winning application.
        """
        if issued_application.team_id != team_id:
            return
        with db.no_autoflush:
            customer = db.query(Customer).filter_by(
                id=issued_application.customer_id, team_id=team_id
            ).populate_existing().with_for_update().one_or_none()
            if customer is None:
                return
            # issue()/issue_full() set ISSUED before calling with commit=False.
            # Flush only this application so the winner query sees the new status
            # without committing or flushing unrelated pending changes.
            db.flush([issued_application])


            selected_application = (
                db.query(LicenseApplication)
                .filter(
                    LicenseApplication.customer_id == customer.id,
                    LicenseApplication.team_id == team_id,
                    LicenseApplication.status == LicenseApplicationStatus.ISSUED,
                )
                .order_by(
                    LicenseApplication.is_permanent.desc(),
                    LicenseApplication.expiry_date.desc(),
                    LicenseApplication.last_modified_time.desc(),
                    LicenseApplication.id.desc(),
                )
                .first()
            )

            previous_values = (
                customer.license_type,
                customer.license_authorized_users,
                customer.license_expiry_date,
                bool(customer.license_is_permanent),
            )
            if selected_application is None:
                selected_values = (None, None, None, False)
            else:
                selected_values = (
                    selected_application.license_type,
                    selected_application.authorized_users,
                    None if selected_application.is_permanent else selected_application.expiry_date,
                    bool(selected_application.is_permanent),
                )

            (
                customer.license_type,
                customer.license_authorized_users,
                customer.license_expiry_date,
                customer.license_is_permanent,
            ) = selected_values
            if commit and selected_values != previous_values:
                db.commit()

# 创建全局实例
license_application_crud = LicenseApplicationCRUD()


# ============================================
# 便捷函数(供 API 直接导入使用)
# ============================================

def create_license_application(
    db: Session,
    team_id: int,
    obj_in: LicenseApplicationInternalCreate,
    applicant_id: str
) -> LicenseApplication:
    """创建 License 申请"""
    return license_application_crud.create(db, team_id, applicant_id, obj_in)


def get_license_application(
    db: Session,
    team_id: int,
    application_id: int
) -> LicenseApplication | None:
    """获取单个 License 申请"""
    return license_application_crud.get(db, team_id, application_id)


def get_license_applications_by_customer(
    db: Session,
    team_id: int,
    customer_id: int,
    skip: int = 0,
    limit: int = 100
) -> tuple[list[LicenseApplication], int]:
    """获取客户的 License 申请列表"""
    return license_application_crud.get_by_customer(db, team_id, customer_id, skip, limit)


def get_license_applications(
    db: Session,
    team_id: int,
    skip: int = 0,
    limit: int = 100,
    customer_id: int | None = None,
    status: str | None = None,
    applicant_id: str | None = None
) -> tuple[list[LicenseApplication], int]:
    """获取 License 申请列表"""
    return license_application_crud.list_applications(db, team_id, skip, limit, customer_id, status, applicant_id)


def update_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    obj_in: LicenseApplicationUpdate
) -> LicenseApplication | None:
    """更新 License 申请"""
    return license_application_crud.update(db, team_id, application_id, obj_in)


def delete_license_application(
    db: Session,
    team_id: int,
    application_id: int
) -> bool:
    """删除 License 申请"""
    return license_application_crud.delete(db, team_id, application_id)


def submit_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    submitter_id: str,
    submitter_name: str | None = None
) -> LicenseApplication | None:
    """提交 License 申请\uff08接入审批引擎\uff09"""
    return license_application_crud.submit(db, team_id, application_id, submitter_id, submitter_name)


def approve_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    approve_data: LicenseApplicationApprove,
    approver_id: str
) -> LicenseApplication | None:
    """已废弃\uff1aLicense 审批请使用通用审批接口。"""
    return license_application_crud.approve(db, team_id, application_id, approve_data, approver_id)


def approve_license_application_full(
    db: Session,
    team_id: int,
    application_id: int,
    approve_data: LicenseApplicationApproveFull,
    approver_id: str
) -> LicenseApplication | None:
    """已废弃\uff1aLicense 审批请使用通用审批接口。"""
    return license_application_crud.approve_full(db, team_id, application_id, approve_data, approver_id)


def reject_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    reason: str
) -> LicenseApplication | None:
    """已废弃\uff1aLicense 驳回请使用通用审批接口。"""
    return license_application_crud.reject(db, team_id, application_id, reason)


def issue_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    issue_data: LicenseApplicationApprove,
    issuer_id: str
) -> LicenseApplication | None:
    """发放已审批通过的 License 申请\uff08简化版本\uff09。"""
    return license_application_crud.issue(db, team_id, application_id, issue_data, issuer_id)


def issue_license_application_full(
    db: Session,
    team_id: int,
    application_id: int,
    issue_data: LicenseApplicationApproveFull,
    issuer_id: str
) -> LicenseApplication | None:
    """发放已审批通过的 License 申请\uff08完整版本\uff0c解析 License 信息\uff09。"""
    return license_application_crud.issue_full(db, team_id, application_id, issue_data, issuer_id)

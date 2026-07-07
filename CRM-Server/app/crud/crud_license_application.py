"""License 申请 CRUD 模块

提供 License 申请的数据库操作。
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List, Tuple, Dict
from datetime import date, datetime

from app.models.license_application import (
    LicenseApplication,
    LicenseApplicationStatus,
    LicenseType
)
from app.models.customer import Customer
from app.models.deployment import DeploymentInfo
from app.models.contract import Contract
from app.schemas.license_application import (
    LicenseApplicationCreate,
    LicenseApplicationUpdate,
    LicenseApplicationApprove,
    LicenseApplicationApproveFull
)


def parse_license_info(license_text: str) -> Dict[str, str]:
    """
    解析审批人回填的 License 信息文本

    格式示例：
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
        Dict[str, str]: 解析后的字段字典，包含:
            - enterprise_id: 企业编号
            - supported_modules: 支持模块
            - server_license_code: 服务端 License
            - client_license_code: 客户端 License
    """
    lines = license_text.strip().split('\n')
    data: Dict[str, str] = {}

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
                # 服务器端 License 可能是多行，收集后续所有行直到遇到"客户端 License"
                server_license_lines = [value] if value else []
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line.startswith('客户端 License'):
                        break
                    if next_line:
                        server_license_lines.append(next_line)
                data['server_license_code'] = '\n'.join(server_license_lines)
            elif key in ('客户端 License',):
                # 客户端 License 可能是多行，收集后续所有行
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
        生成申请单号：LIC-YYYYMM-XXX

        Args:
            db: 数据库会话

        Returns:
            str: 生成的申请单号
        """
        today = date.today()
        prefix = f"LIC-{today.strftime('%Y%m')}-"

        # 查询当月最大序号
        max_no = db.query(LicenseApplication.application_number).filter(
            LicenseApplication.application_number.like(f"{prefix}%")
        ).order_by(LicenseApplication.application_number.desc()).first()

        if max_no:
            seq = int(max_no[0].split('-')[-1]) + 1
        else:
            seq = 1

        return f"{prefix}{seq:03d}"

    def create(
        self,
        db: Session,
        team_id: int,
        applicant_id: str,
        obj_in: LicenseApplicationCreate
    ) -> LicenseApplication:
        """
        创建 License 申请

        Args:
            db: 数据库会话
            team_id: 团队ID
            applicant_id: 申请人飞书用户ID
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

        # 验证部署信息存在（如果提供）
        if obj_in.deployment_info_id:
            deployment = db.query(DeploymentInfo).filter(
                DeploymentInfo.id == obj_in.deployment_info_id,
                DeploymentInfo.team_id == team_id,
                DeploymentInfo.customer_id == obj_in.customer_id
            ).first()
            if not deployment:
                raise ValueError("部署信息不存在或不属于该客户")

        # 验证合同存在（如果提供）
        if obj_in.contract_id:
            contract = db.query(Contract).filter(
                Contract.id == obj_in.contract_id,
                Contract.team_id == team_id,
                Contract.customer_id == obj_in.customer_id
            ).first()
            if not contract:
                raise ValueError("合同不存在或不属于该客户")

        # 生成申请单号
        application_number = self.generate_application_number(db)

        # 创建申请
        db_obj = LicenseApplication(
            team_id=team_id,
            application_number=application_number,
            customer_id=obj_in.customer_id,
            deployment_info_id=obj_in.deployment_info_id,
            contract_id=obj_in.contract_id,
            expiry_date=obj_in.expiry_date,
            license_type=obj_in.license_type.value,
            remark=obj_in.remark,  # 补充需求：备注字段
            applicant_id=applicant_id,
            status=LicenseApplicationStatus.DRAFT
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(
        self,
        db: Session,
        team_id: int,
        application_id: int
    ) -> Optional[LicenseApplication]:
        """
        获取单个 License 申请

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID

        Returns:
            Optional[LicenseApplication]: 申请，不存在则返回 None
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
    ) -> Optional[LicenseApplication]:
        """
        根据申请单号获取申请

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_number: 申请单号

        Returns:
            Optional[LicenseApplication]: 申请，不存在则返回 None
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
    ) -> Tuple[List[LicenseApplication], int]:
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
        customer_id: Optional[int] = None,
        status: Optional[str] = None,
        applicant_id: Optional[str] = None
    ) -> Tuple[List[LicenseApplication], int]:
        """
        获取 License 申请列表

        Args:
            db: 数据库会话
            team_id: 团队ID
            skip: 跳过记录数
            limit: 返回记录数上限
            customer_id: 客户ID（可选）
            status: 申请状态（可选）
            applicant_id: 申请人ID（可选）

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
    ) -> Optional[LicenseApplication]:
        """
        更新 License 申请（仅 DRAFT 状态）

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            obj_in: 更新请求数据

        Returns:
            Optional[LicenseApplication]: 更新后的申请，不存在或状态不对则返回 None

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

        # 验证部署信息存在（如果提供）
        if 'deployment_info_id' in update_data and update_data['deployment_info_id']:
            deployment = db.query(DeploymentInfo).filter(
                DeploymentInfo.id == update_data['deployment_info_id'],
                DeploymentInfo.team_id == team_id,
                DeploymentInfo.customer_id == application.customer_id
            ).first()
            if not deployment:
                raise ValueError("部署信息不存在或不属于该客户")

        # 验证合同存在（如果提供）
        if 'contract_id' in update_data and update_data['contract_id']:
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
        删除 License 申请（仅 DRAFT 状态）

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
    ) -> Optional[LicenseApplication]:
        """
        提交 License 申请（接入审批引擎）

        流程：
        1. 验证申请存在且状态为 DRAFT
        2. 匹配审批流程（按 license_type）
        3. 创建审批实例（Approval + ApprovalRecord）
        4. 更新申请状态为 PENDING

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            submitter_id: 提交人飞书用户ID
            submitter_name: 提交人姓名（可选）

        Returns:
            Optional[LicenseApplication]: 更新后的申请

        Raises:
            ValueError: 申请状态不是 DRAFT 或审批流程未匹配
        """
        from app.crud.approval import approval_flow_crud, approval_crud
        from app.services.approval_adapter import get_adapter
        from app.constants.business_types import BusinessType

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

        if flow is None and err:
            # 未匹配且报错（类似 CONTRACT 语义）
            raise ValueError(err or "未匹配到审批流程")

        if flow is None:
            # 未匹配审批流程，直接批准（免审批直通）
            application.status = LicenseApplicationStatus.ISSUED
            db.commit()
            db.refresh(application)
            return application

        # 创建审批实例（会自动调用 adapter.on_submit 切换状态）
        approval_crud.create_approval_generic(
            db,
            BusinessType.LICENSE,
            application_id,
            team_id,
            flow,
            submitter_id,
            submitter_name or "",
        )

        db.refresh(application)
        return application

    def approve(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        approve_data: LicenseApplicationApprove,
        approver_id: str
    ) -> Optional[LicenseApplication]:
        """
        审批通过 License 申请（PENDING → ISSUED）- 简化版本

        审批通过时会：
        1. 更新状态为 ISSUED
        2. 填写 license_code 字段
        3. 记录 approver_id 和 approved_time
        4. 更新客户 license_expiry_date 和 license_type

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            approve_data: 审批数据（包含 license_code）
            approver_id: 审批人飞书用户ID

        Returns:
            Optional[LicenseApplication]: 更新后的申请，不存在或状态不对则返回 None

        Raises:
            ValueError: 申请状态不是 PENDING

        Note:
            推荐使用 approve_full 方法，支持完整 License 信息解析
        """
        application = self.get(db, team_id, application_id)
        if not application:
            return None

        # 仅 PENDING 状态可审批
        if application.status != LicenseApplicationStatus.PENDING:
            raise ValueError("只有待审批状态的申请可以审批")

        # 更新申请状态和信息
        application.status = LicenseApplicationStatus.ISSUED
        application.license_code = approve_data.license_code
        application.approver_id = approver_id
        application.approved_time = datetime.now()

        db.commit()
        db.refresh(application)

        # 更新客户 License 信息
        self.update_customer_license_info(db, application.customer_id)

        return application

    def approve_full(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        approve_data: LicenseApplicationApproveFull,
        approver_id: str
    ) -> Optional[LicenseApplication]:
        """
        审批通过 License 申请（PENDING → ISSUED）- 完整版本

        审批通过时会：
        1. 更新状态为 ISSUED
        2. 解析 license_info 文本，填充 enterprise_id、supported_modules、
           server_license_code、client_license_code 字段
        3. 记录 approver_id 和 approved_time
        4. 更新客户 license_expiry_date 和 license_type

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            approve_data: 审批数据（包含完整的 license_info 文本）
            approver_id: 审批人飞书用户ID

        Returns:
            Optional[LicenseApplication]: 更新后的申请，不存在或状态不对则返回 None

        Raises:
            ValueError: 申请状态不是 PENDING
        """
        application = self.get(db, team_id, application_id)
        if not application:
            return None

        # 仅 PENDING 状态可审批
        if application.status != LicenseApplicationStatus.PENDING:
            raise ValueError("只有待审批状态的申请可以审批")

        # 解析 License 信息
        parsed_data = parse_license_info(approve_data.license_info)

        # 更新申请状态和信息
        application.status = LicenseApplicationStatus.ISSUED
        application.enterprise_id = parsed_data.get('enterprise_id')
        application.supported_modules = parsed_data.get('supported_modules')
        application.server_license_code = parsed_data.get('server_license_code')
        application.client_license_code = parsed_data.get('client_license_code')
        application.approver_id = approver_id
        application.approved_time = datetime.now()

        db.commit()
        db.refresh(application)

        # 更新客户 License 信息
        self.update_customer_license_info(db, application.customer_id)

        return application

    def reject(
        self,
        db: Session,
        team_id: int,
        application_id: int,
        reason: str
    ) -> Optional[LicenseApplication]:
        """
        审批拒绝 License 申请（PENDING → REJECTED）

        拒绝时会将原因写入 license_code 字段（临时方案，后续可考虑增加 remark 字段）

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID
            reason: 拒绝原因

        Returns:
            Optional[LicenseApplication]: 更新后的申请，不存在或状态不对则返回 None

        Raises:
            ValueError: 申请状态不是 PENDING
        """
        application = self.get(db, team_id, application_id)
        if not application:
            return None

        # 仅 PENDING 状态可审批
        if application.status != LicenseApplicationStatus.PENDING:
            raise ValueError("只有待审批状态的申请可以审批")

        # 更新申请状态
        application.status = LicenseApplicationStatus.REJECTED
        application.approver_id = None  # 拒绝时清空审批人
        application.approved_time = None

        # 将拒绝原因写入 license_code 字段（临时方案）
        application.license_code = f"REJECTED: {reason}"

        db.commit()
        db.refresh(application)
        return application

    def update_customer_license_expiry(
        self,
        db: Session,
        customer_id: int,
        expiry_date: date
    ) -> bool:
        """
        更新客户 License 到期时间

        如果新的到期时间晚于当前客户的 license_expiry_date，则更新。

        Args:
            db: 数据库会话
            customer_id: 客户ID
            expiry_date: 新的到期时间

        Returns:
            bool: 是否成功更新

        Note:
            此方法已弃用，请使用 update_customer_license_info
        """
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            return False

        # 只有新的到期时间晚于当前时间才更新
        if customer.license_expiry_date is None or expiry_date > customer.license_expiry_date:
            customer.license_expiry_date = expiry_date
            db.commit()
            return True

        return False

    def update_customer_license_info(
        self,
        db: Session,
        customer_id: int
    ) -> None:
        """
        更新客户 License 最晚到期时间和类型

        查询客户所有已发放的 License 申请，按到期时间降序排列，
        将最晚到期时间和对应的 License 类型更新到客户表。

        Args:
            db: 数据库会话
            customer_id: 客户ID
        """
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


# 创建全局实例
license_application_crud = LicenseApplicationCRUD()


# ============================================
# 便捷函数（供 API 直接导入使用）
# ============================================

def create_license_application(
    db: Session,
    team_id: int,
    obj_in: LicenseApplicationCreate,
    applicant_id: str
) -> LicenseApplication:
    """创建 License 申请"""
    return license_application_crud.create(db, team_id, applicant_id, obj_in)


def get_license_application(
    db: Session,
    team_id: int,
    application_id: int
) -> Optional[LicenseApplication]:
    """获取单个 License 申请"""
    return license_application_crud.get(db, team_id, application_id)


def get_license_applications_by_customer(
    db: Session,
    team_id: int,
    customer_id: int,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[LicenseApplication], int]:
    """获取客户的 License 申请列表"""
    return license_application_crud.get_by_customer(db, team_id, customer_id, skip, limit)


def get_license_applications(
    db: Session,
    team_id: int,
    skip: int = 0,
    limit: int = 100,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    applicant_id: Optional[str] = None
) -> Tuple[List[LicenseApplication], int]:
    """获取 License 申请列表"""
    return license_application_crud.list_applications(db, team_id, skip, limit, customer_id, status, applicant_id)


def update_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    obj_in: LicenseApplicationUpdate
) -> Optional[LicenseApplication]:
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
) -> Optional[LicenseApplication]:
    """提交 License 申请（接入审批引擎）"""
    return license_application_crud.submit(db, team_id, application_id, submitter_id, submitter_name)


def approve_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    approve_data: LicenseApplicationApprove,
    approver_id: str
) -> Optional[LicenseApplication]:
    """审批通过 License 申请（简化版本）"""
    return license_application_crud.approve(db, team_id, application_id, approve_data, approver_id)


def approve_license_application_full(
    db: Session,
    team_id: int,
    application_id: int,
    approve_data: LicenseApplicationApproveFull,
    approver_id: str
) -> Optional[LicenseApplication]:
    """审批通过 License 申请（完整版本，解析 License 信息）"""
    return license_application_crud.approve_full(db, team_id, application_id, approve_data, approver_id)


def reject_license_application(
    db: Session,
    team_id: int,
    application_id: int,
    reason: str
) -> Optional[LicenseApplication]:
    """审批拒绝 License 申请"""
    return license_application_crud.reject(db, team_id, application_id, reason)
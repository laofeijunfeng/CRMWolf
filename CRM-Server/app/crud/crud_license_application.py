"""License 申请 CRUD 模块

提供 License 申请的数据库操作。
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List, Tuple
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
    LicenseApplicationApprove
)


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
        application_id: int
    ) -> Optional[LicenseApplication]:
        """
        提交 License 申请（DRAFT → PENDING）

        Args:
            db: 数据库会话
            team_id: 团队ID
            application_id: 申请ID

        Returns:
            Optional[LicenseApplication]: 更新后的申请，不存在或状态不对则返回 None

        Raises:
            ValueError: 申请状态不是 DRAFT
        """
        application = self.get(db, team_id, application_id)
        if not application:
            return None

        # 仅 DRAFT 状态可提交
        if application.status != LicenseApplicationStatus.DRAFT:
            raise ValueError("只有草稿状态的申请可以提交")

        application.status = LicenseApplicationStatus.PENDING
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
    ) -> Optional[LicenseApplication]:
        """
        审批通过 License 申请（PENDING → ISSUED）

        审批通过时会：
        1. 更新状态为 ISSUED
        2. 填写 license_code 字段
        3. 记录 approver_id 和 approved_time
        4. 更新客户 license_expiry_date

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

        # 更新客户 License 到期时间
        self.update_customer_license_expiry(
            db,
            application.customer_id,
            application.expiry_date
        )

        db.commit()
        db.refresh(application)
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


# 创建全局实例
license_application_crud = LicenseApplicationCRUD()
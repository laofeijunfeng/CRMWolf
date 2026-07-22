"""审批引擎业务单据适配器：把审批 CRUD 与具体单据（合同/回款/发票/License）的状态机解耦。

每个 business_type 注册一个 ApprovalEntityAdapter，负责：
- 取实体、取提交人、取匹配审批流的维度
- 提交/通过/驳回/撤回时的单据状态切换
- 取单据展示名（通知用）

E4 守卫规则（强制）：所有 on_submit/on_approved/on_rejected/on_cancelled 实现首行
`if entity is None: return`——业务单据被软删/跨 team 时 get_entity 返 None，
避免 `None.status` AttributeError（对齐现有合同 crud/approval.py 的 `if contract:` 守卫）。
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.models.contract import Contract, ContractStatus
from app.models.payment import PaymentPlan, PaymentRecord, PaymentConfirmationStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus
from app.models.license_application import LicenseApplication, LicenseApplicationStatus
from app.models.opportunity import Opportunity
from app.models.customer import Customer


_BUSINESS_TYPE_DISPLAY_NAMES = {
    BusinessType.CONTRACT: "合同",
    BusinessType.PAYMENT: "回款登记",
    BusinessType.INVOICE: "发票申请",
    BusinessType.LICENSE: "License申请",
    BusinessType.OPPORTUNITY: "商机",
}


class ApprovalEntityAdapter(Protocol):
    business_type: str

    def get_entity(self, db: Session, business_id: int, team_id: int) -> Any: ...
    def get_submitter(self, entity: Any) -> tuple[str, str | None]: ...
    def match_kwargs(self, entity: Any) -> dict: ...
    def on_submit(self, db: Session, entity: Any) -> None: ...
    def on_approved(self, db: Session, entity: Any) -> None: ...
    def on_rejected(self, db: Session, entity: Any) -> None: ...
    def on_cancelled(self, db: Session, entity: Any) -> None: ...
    def get_name(self, entity: Any) -> str: ...


class ContractAdapter:
    business_type = BusinessType.CONTRACT

    def get_entity(self, db, business_id, team_id):
        from app.crud.contract import contract_crud
        return contract_crud.get_by_id(db, business_id, team_id)

    def get_submitter(self, entity):
        # Contract 模型只有 creator_id，无 creator_name 列；姓名非必须，通知层 A8 处理
        return entity.creator_id, None

    def match_kwargs(self, entity):
        return {
            "amount": float(entity.total_amount) if entity.total_amount else 0,
            "license_type": getattr(entity, "license_type", None),
        }

    def on_submit(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.status = ContractStatus.PENDING_REVIEW

    def on_approved(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.status = ContractStatus.SIGNED

    def on_rejected(self, db, entity):
        if entity is None: return  # E4 守卫
        # 审批结果由 approval.status / approval_phase 保留；业务状态回到草稿，允许修改后重新提交。
        entity.status = ContractStatus.DRAFT

    def on_cancelled(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.status = ContractStatus.DRAFT

    def get_name(self, entity):
        # Contract 真实字段是 contract_name（非 name），否则 fallback 到 合同#{id}
        return getattr(entity, "contract_name", None) or f"合同#{entity.id}"


class PaymentRecordAdapter:
    business_type = BusinessType.PAYMENT

    def get_entity(self, db, business_id, team_id):
        from app.crud.payment import payment_record_crud
        return payment_record_crud.get_by_id(db, business_id, team_id)

    def get_submitter(self, entity):
        return entity.creator_id, getattr(entity, "creator_name", None)

    def match_kwargs(self, entity):
        return {
            "amount": float(entity.actual_amount) if entity.actual_amount else 0,
            "license_type": None,
        }

    def on_submit(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.confirmation_status = PaymentConfirmationStatus.PENDING

    def on_approved(self, db, entity):
        if entity is None: return  # E4 守卫
        # 审批通过即确认入账
        entity.confirmation_status = PaymentConfirmationStatus.CONFIRMED

    def on_rejected(self, db, entity):
        if entity is None: return  # E4 守卫
        # approval_phase 切换由 Approval Engine 管理（entity.approval_phase = REJECTED）
        # 此处不切换 confirmation_status（保持 PENDING）
        pass

    def on_cancelled(self, db, entity):
        if entity is None: return  # E4 守卫
        # approval_phase 切换由 Approval Engine 管理（entity.approval_phase = DRAFT）
        # 撤回后切回 DRAFT（允许重新提交）
        entity.confirmation_status = PaymentConfirmationStatus.DRAFT

    def get_name(self, entity):
        return f"回款登记#{entity.id}"


class InvoiceApplicationAdapter:
    business_type = BusinessType.INVOICE

    def get_entity(self, db, business_id, team_id):
        from app.crud.invoice import invoice_application_crud
        return invoice_application_crud.get_by_id(db, business_id, team_id)

    # 发票提交人字段是 applicant_id（非 creator_id），见决策 3
    def get_submitter(self, entity):
        # InvoiceApplication 无 applicant_name 列，只有 applicant_id；姓名非必须
        return entity.applicant_id, None

    def match_kwargs(self, entity):
        # 开票金额字段是 invoice_amount（非 amount），见决策 3
        return {"amount": float(entity.invoice_amount or 0), "license_type": None}

    def on_submit(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.status = InvoiceApplicationStatus.PENDING_REVIEW

    def on_approved(self, db, entity):
        if entity is None: return  # E4 守卫
        # 引擎终态回写快照，InvoiceDetail.vue 仍读这三字段，见决策 2(c)
        entity.status = InvoiceApplicationStatus.APPROVED
        entity.reviewed_time = func.now()

    def on_rejected(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.status = InvoiceApplicationStatus.REJECTED
        entity.reviewed_time = func.now()

    def on_cancelled(self, db, entity):
        if entity is None: return  # E4 守卫
        entity.status = InvoiceApplicationStatus.DRAFT

    def get_name(self, entity):
        return f"发票申请#{entity.id}"


class LicenseApplicationAdapter:
    """License 申请审批适配器

    状态流转：
    - on_submit: DRAFT → PENDING_REVIEW（提交审批）
    - on_approved: PENDING_REVIEW → APPROVED（审批通过）
    - on_rejected: PENDING_REVIEW → REJECTED（审批拒绝）
    - on_cancelled: PENDING_REVIEW → DRAFT（撤回审批）
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
        # 统一命名：PENDING → PENDING_REVIEW（与 InvoiceApplicationStatus 一致）
        entity.status = LicenseApplicationStatus.PENDING_REVIEW

    def on_approved(self, db: Session, entity: LicenseApplication) -> None:
        """审批通过时的状态切换

        审批只负责批准申请。License 信息填写和发放是审批通过后的后置业务动作，
        由 License issue 接口在确认 Approval.status=APPROVED 后执行。
        """
        if entity is None: return  # E4 守卫
        entity.status = LicenseApplicationStatus.APPROVED

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


class OpportunityAdapter:
    """商机审批适配器

    商机的 status 表示跟进中/赢单/输单，审批状态由 approval_phase 独立承载。
    因此审批提交、通过、驳回、撤回均不改写业务 status。
    """
    business_type = BusinessType.OPPORTUNITY

    def get_entity(self, db: Session, business_id: int, team_id: int) -> Optional[Opportunity]:
        from app.crud.opportunity import opportunity_crud
        return opportunity_crud.get_by_id(db, business_id, team_id)

    def get_submitter(self, entity: Opportunity) -> tuple[str, str | None]:
        if entity is None:
            return "", None
        return entity.creator_id or "", None

    def match_kwargs(self, entity: Opportunity) -> dict:
        return {
            "amount": float(entity.total_amount) if entity.total_amount else 0,
            "license_type": getattr(entity, "license_type", None),
        }

    def on_submit(self, db: Session, entity: Opportunity) -> None:
        if entity is None: return  # E4 守卫

    def on_approved(self, db: Session, entity: Opportunity) -> None:
        if entity is None: return  # E4 守卫

    def on_rejected(self, db: Session, entity: Opportunity) -> None:
        if entity is None: return  # E4 守卫

    def on_cancelled(self, db: Session, entity: Opportunity) -> None:
        if entity is None: return  # E4 守卫

    def get_name(self, entity: Opportunity) -> str:
        if entity is None:
            return "商机"
        return getattr(entity, "opportunity_name", None) or f"商机#{entity.id}"


_REGISTRY: dict[str, ApprovalEntityAdapter] = {
    BusinessType.CONTRACT: ContractAdapter(),
    BusinessType.PAYMENT: PaymentRecordAdapter(),
    BusinessType.INVOICE: InvoiceApplicationAdapter(),
    BusinessType.LICENSE: LicenseApplicationAdapter(),
    BusinessType.OPPORTUNITY: OpportunityAdapter(),
}


def get_adapter(business_type: str) -> ApprovalEntityAdapter:
    adapter = _REGISTRY.get(business_type)
    if adapter is None:
        raise ValueError(f"不支持的业务单据类型: {business_type}")
    return adapter


def get_approval_type_name(business_type: str) -> str:
    return _BUSINESS_TYPE_DISPLAY_NAMES.get(business_type, "审批")


def get_approval_action_path(business_type: str) -> str:
    paths = {
        BusinessType.CONTRACT: "/contracts",
        BusinessType.PAYMENT: "/payments/records",
        BusinessType.INVOICE: "/invoices",
        BusinessType.LICENSE: "/customers",
        BusinessType.OPPORTUNITY: "/opportunities",
    }
    return paths.get(business_type, "/approvals")


def get_approval_card_fields(db: Session, business_type: str, entity: Any) -> dict[str, str]:
    if entity is None:
        return {}

    if business_type == BusinessType.OPPORTUNITY:
        return {
            "客户名称": _customer_name(db, business_type, entity),
            "商机名称": getattr(entity, "opportunity_name", None),
            "商机金额": _format_currency(getattr(entity, "total_amount", None)),
            "采购数量": _format_count(getattr(entity, "user_count", None)),
            "授权模式": _license_mode_label(getattr(entity, "license_type", None)),
            "采购类型": _purchase_type_label(getattr(entity, "purchase_type", None)),
        }

    if business_type == BusinessType.CONTRACT:
        opportunity = getattr(entity, "opportunity", None)
        return {
            "客户名称": _customer_name(db, business_type, entity),
            "合同名称": getattr(entity, "contract_name", None),
            "合同金额": _format_currency(getattr(entity, "total_amount", None)),
            "采购数量": _format_count(getattr(entity, "user_count", None)),
            "授权模式": _license_mode_label(getattr(entity, "license_type", None)),
            "采购类型": _purchase_type_label(getattr(opportunity, "purchase_type", None)),
        }

    if business_type == BusinessType.INVOICE:
        return {
            "客户名称": _customer_name(db, business_type, entity),
            "开票抬头": getattr(entity, "invoice_title_text", None),
            "发票类型": _invoice_type_label(getattr(entity, "invoice_type", None)),
            "开票金额": _format_currency(getattr(entity, "invoice_amount", None)),
        }

    if business_type == BusinessType.PAYMENT:
        return {
            "客户名称": _customer_name(db, business_type, entity),
            "实际付款方": getattr(entity, "actual_payer_name", None),
            "回款金额": _format_currency(getattr(entity, "actual_amount", None)),
            "回款日期": _format_date(getattr(entity, "payment_date", None)),
            "备注": getattr(entity, "notes", None),
        }

    if business_type == BusinessType.LICENSE:
        deployment_info = getattr(entity, "deployment_info", None)
        return {
            "客户名称": _customer_name(db, business_type, entity),
            "授权类型": _license_application_type_label(getattr(entity, "license_type", None)),
            "服务地址": getattr(deployment_info, "server_address", None),
            "授权人数": _format_count(getattr(deployment_info, "authorized_users", None)),
            "到期日期": _format_date(getattr(entity, "expiry_date", None)),
            "备注": getattr(entity, "remark", None),
        }

    return {
        "客户名称": _customer_name(db, business_type, entity),
        f"{get_approval_type_name(business_type)}名称": get_adapter(business_type).get_name(entity),
    }


def get_approval_customer_name(db: Session, business_type: str, entity: Any) -> Optional[str]:
    if entity is None:
        return None

    customer = getattr(entity, "customer", None)
    if customer is not None:
        return getattr(customer, "account_name", None)

    if business_type == BusinessType.PAYMENT:
        payment_plan = getattr(entity, "payment_plan", None)
        contract = getattr(payment_plan, "contract", None) if payment_plan is not None else None
        customer = getattr(contract, "customer", None) if contract is not None else None
        if customer is not None:
            return getattr(customer, "account_name", None)

        payment_plan_id = getattr(entity, "payment_plan_id", None)
        if payment_plan_id:
            payment_plan = db.query(PaymentPlan).filter(
                PaymentPlan.id == payment_plan_id,
                PaymentPlan.team_id == getattr(entity, "team_id", None),
            ).first()
            contract = getattr(payment_plan, "contract", None) if payment_plan is not None else None
            customer = getattr(contract, "customer", None) if contract is not None else None
            if customer is not None:
                return getattr(customer, "account_name", None)

    customer_id = getattr(entity, "customer_id", None)
    if customer_id:
        customer = db.query(Customer).filter(
            Customer.id == customer_id,
            Customer.team_id == getattr(entity, "team_id", None),
        ).first()
        return customer.account_name if customer else None

    return None


def _customer_name(db: Session, business_type: str, entity: Any) -> str:
    name = get_approval_customer_name(db, business_type, entity)
    if name:
        return name
    customer = getattr(entity, "customer", None)
    if customer is not None:
        return getattr(customer, "account_name", None) or "-"
    customer_id = getattr(entity, "customer_id", None)
    if customer_id:
        customer = db.query(Customer).filter(
            Customer.id == customer_id,
            Customer.team_id == getattr(entity, "team_id", None),
        ).first()
        if customer:
            return customer.account_name or "-"
    return "-"


def _format_currency(value: Any) -> str:
    if value is None:
        return "-"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value) or "-"
    return f"¥{amount:,.2f}"


def _format_count(value: Any) -> str:
    if value is None:
        return "-"
    return f"{value}人"


def _format_date(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value) or "-"


def _license_mode_label(value: Any) -> str:
    return {
        "SUBSCRIPTION": "订阅制",
        "PERPETUAL": "买断制",
    }.get(str(value or ""), str(value or "-"))


def _purchase_type_label(value: Any) -> str:
    return {
        "NEW": "新购",
        "RENEWAL": "续购",
        "EXPANSION": "增购",
    }.get(str(value or ""), str(value or "-"))


def _invoice_type_label(value: Any) -> str:
    return {
        "VAT_SPECIAL": "增值税专用发票",
        "VAT_NORMAL": "普通发票",
    }.get(str(value or ""), str(value or "-"))


def _license_application_type_label(value: Any) -> str:
    return {
        "TRIAL": "试用",
        "OFFICIAL": "正式",
    }.get(str(value or ""), str(value or "-"))

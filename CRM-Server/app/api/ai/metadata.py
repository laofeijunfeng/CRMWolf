"""AI OpenAPI 元数据层路由

负责向 AI 暴露系统静态配置与业务规则。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.ai.deps import get_ai_user
from app.core.database import get_db
from app.models.user import User
from app.models.procurement import ProcurementStageTemplate, ProcurementMethod
from app.models.lead import Lead, LeadStatus
from app.models.customer import Customer
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.contract import Contract
from app.constants.ai_rules import BUSINESS_RULES

router = APIRouter()


@router.get("/stages", summary="商机阶段与赢率映射")
async def get_opportunity_stages(
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取商机阶段配置

    返回所有采购方式下的阶段及其赢率、允许的操作等。
    """
    # 获取所有活跃的采购方式
    methods = db.query(ProcurementMethod).filter(
        ProcurementMethod.is_active == 1
    ).order_by(ProcurementMethod.sort_order).all()

    result = {"procurement_methods": []}

    for method in methods:
        # 获取该采购方式下的所有阶段模板
        stages = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == method.id
        ).order_by(ProcurementStageTemplate.sort_order).all()

        method_data = {
            "method_id": method.id,
            "method_code": method.code,
            "method_name": method.name,
            "stages": []
        }

        for idx, stage in enumerate(stages):
            # 计算下一阶段（顺序推进）
            next_stages = []
            if idx + 1 < len(stages):
                next_stages.append(stages[idx + 1].stage_name)

            # 允许跳过的阶段
            skippable_stages = [
                s.stage_name for s in stages
                if s.can_skip == 1 and s.sort_order > stage.sort_order
            ]

            # 确定允许的操作
            allowed_actions = ["edit", "view"]
            if stage.is_default_start != 1:
                allowed_actions.append("advance")
            if stage.sort_order < max(s.sort_order for s in stages):
                allowed_actions.append("advance")
            # 输单可以在任意阶段执行
            allowed_actions.append("lose")

            method_data["stages"].append({
                "stage_id": stage.id,
                "template_code": stage.template_code,
                "name": stage.stage_name,
                "win_rate": stage.win_probability / 100.0,  # 转换为 0-1 范围
                "sort_order": stage.sort_order,
                "is_default_start": stage.is_default_start == 1,
                "can_skip": stage.can_skip == 1,
                "next_stages": next_stages,
                "skippable_stages": skippable_stages,
                "allowed_actions": allowed_actions,
                "description": stage.description,
            })

        result["procurement_methods"].append(method_data)

    return result


@router.get("/rules", summary="业务规则库")
async def get_business_rules(
    user: User = Depends(get_ai_user),
) -> Dict[str, Any]:
    """获取业务规则配置

    返回关键词触发规则、阶段变更规则等。
    """
    from app.constants.ai_rules import BUSINESS_RULES

    return {"rules": BUSINESS_RULES}


@router.get("/entities", summary="实体关系与必填字段")
async def get_entity_definitions(
    user: User = Depends(get_ai_user),
) -> Dict[str, Any]:
    """获取实体定义

    返回各实体的必填字段、可选字段、关联实体等。
    """
    return {
        "entities": [
            {
                "name": "Opportunity",
                "display_name": "商机",
                "required_fields": [
                    {"name": "customer_id", "type": "integer", "description": "关联客户ID"},
                    {"name": "opportunity_name", "type": "string", "description": "商机名称"},
                    {"name": "total_amount", "type": "decimal", "description": "预计总金额"},
                    {"name": "user_count", "type": "integer", "description": "采购用户数"},
                    {"name": "unit_price", "type": "decimal", "description": "标准单价"},
                    {"name": "license_type", "type": "enum", "values": ["SUBSCRIPTION", "PERPETUAL"], "description": "授权模式"},
                    {"name": "purchase_type", "type": "enum", "values": ["NEW", "RENEWAL", "EXPANSION"], "description": "采购类型"},
                    {"name": "expected_closing_date", "type": "date", "description": "预计成交日期"},
                ],
                "optional_fields": [
                    {"name": "procurement_method_id", "type": "integer", "description": "采购方式ID"},
                    {"name": "subscription_years", "type": "integer", "description": "订阅年限"},
                    {"name": "decision_maker_count", "type": "integer", "description": "决策人数"},
                ],
                "relations": [
                    {"name": "Customer", "type": "belongs_to", "field": "customer_id"},
                    {"name": "Contract", "type": "has_many"},
                    {"name": "OpportunityStageSnapshot", "type": "has_many"},
                ],
            },
            {
                "name": "FollowUp",
                "display_name": "跟进记录",
                "required_fields": [
                    {"name": "customer_id", "type": "integer", "description": "关联客户ID"},
                    {"name": "content", "type": "text", "description": "跟进内容"},
                ],
                "optional_fields": [
                    {"name": "follow_up_time", "type": "datetime", "description": "跟进时间"},
                    {"name": "opportunity_id", "type": "integer", "description": "关联商机ID"},
                    {"name": "next_action", "type": "text", "description": "下一步动作"},
                ],
                "relations": [
                    {"name": "Customer", "type": "belongs_to", "field": "customer_id"},
                    {"name": "Opportunity", "type": "belongs_to", "field": "opportunity_id", "optional": True},
                ],
            },
            {
                "name": "Lead",
                "display_name": "线索",
                "required_fields": [
                    {"name": "lead_name", "type": "string", "description": "线索名称"},
                    {"name": "contact_phone", "type": "string", "description": "联系人手机"},
                    {"name": "source", "type": "enum", "values": [
                        "线上注册", "市场活动", "客户推荐", "电话营销", "网站咨询", "展会", "其他"
                    ], "description": "线索来源"},
                    {"name": "city", "type": "string", "description": "所在城市"},
                ],
                "optional_fields": [
                    {"name": "contact_name", "type": "string", "description": "联系人姓名"},
                    {"name": "company_scale", "type": "enum", "values": [
                        "1-50人", "51-200人", "201-500人", "501-1000人", "1000人以上"
                    ], "description": "团队规模"},
                ],
                "relations": [
                    {"name": "Customer", "type": "converts_to"},
                ],
            },
            {
                "name": "Customer",
                "display_name": "客户",
                "required_fields": [
                    {"name": "account_name", "type": "string", "description": "客户公司名称"},
                    {"name": "city", "type": "string", "description": "所在城市"},
                ],
                "optional_fields": [
                    {"name": "industry", "type": "string", "description": "所属行业"},
                    {"name": "address", "type": "string", "description": "公司地址"},
                    {"name": "company_scale", "type": "string", "description": "公司规模"},
                    {"name": "source", "type": "string", "description": "客户来源"},
                ],
                "relations": [
                    {"name": "Contact", "type": "has_many"},
                    {"name": "Opportunity", "type": "has_many"},
                    {"name": "Contract", "type": "has_many"},
                ],
            },
            {
                "name": "Contract",
                "display_name": "合同",
                "required_fields": [
                    {"name": "customer_id", "type": "integer", "description": "关联客户ID"},
                    {"name": "opportunity_id", "type": "integer", "description": "关联商机ID"},
                    {"name": "contract_name", "type": "string", "description": "合同名称"},
                    {"name": "total_amount", "type": "decimal", "description": "合同总金额"},
                    {"name": "user_count", "type": "integer", "description": "采购用户数"},
                ],
                "optional_fields": [
                    {"name": "signing_date", "type": "date", "description": "签署日期"},
                    {"name": "effective_date", "type": "date", "description": "生效日期"},
                    {"name": "expiry_date", "type": "date", "description": "到期日期"},
                ],
                "relations": [
                    {"name": "Customer", "type": "belongs_to", "field": "customer_id"},
                    {"name": "Opportunity", "type": "belongs_to", "field": "opportunity_id"},
                    {"name": "PaymentPlan", "type": "has_many"},
                ],
            },
        ]
    }


@router.get("/permissions", summary="当前用户权限范围")
async def get_user_permissions(
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取当前用户的权限范围

    返回用户可操作的数据范围、允许/禁止的操作等。
    """
    from app.services.permission_service import permission_service

    # 获取用户权限列表
    permissions, from_cache = permission_service.get_user_permissions_with_cache(db, int(user.id))

    # 解析权限码，提取资源、动作、范围
    allowed_actions = []
    restricted_actions = []
    resources = {}

    for perm in permissions:
        resource = perm.resource or "all"
        action = perm.action or "all"
        scope = perm.scope or "own"

        # 记录资源权限
        if resource not in resources:
            resources[resource] = {"actions": [], "scope": scope}
        resources[resource]["actions"].append(action)

        # 判断是否受限操作
        if action in ["delete", "approve"]:
            restricted_actions.append(f"{resource}:{action}")
        else:
            allowed_actions.append(f"{resource}:{action}")

    # 判断数据范围
    data_scope = "own"  # 默认只能操作自己的数据
    if user.is_admin:
        data_scope = "all"
    elif any(p.scope == "team" for p in permissions if p.scope):
        data_scope = "team"

    return {
        "user_id": str(user.id),
        "is_admin": user.is_admin,
        "data_scope": data_scope,
        "resources": resources,
        "allowed_actions": allowed_actions,
        "restricted_actions": restricted_actions,
    }


@router.get("/enums", summary="状态枚举值")
async def get_status_enums(
    user: User = Depends(get_ai_user),
) -> Dict[str, Any]:
    """获取所有状态枚举值

    返回线索状态、客户状态、商机状态、合同状态等。
    """
    from app.models.lead import LeadStatus, LeadSource, CompanyScale, FollowUpMethod
    from app.models.customer import CustomerStatus, CustomerIndustry, CustomerSource
    from app.models.opportunity import OpportunityStatus, PurchaseType, LicenseType
    from app.models.contract import ContractStatus, PaymentStatus
    from app.models.approval import ApprovalStatus
    from app.models.payment import PaymentPlanStatus, PaymentConfirmationStatus
    from app.models.invoice import InvoiceApplicationStatus

    return {
        "lead_status": {
            "type": "enum",
            "values": [
                {"code": LeadStatus.NEW.name, "value": LeadStatus.NEW.value, "label": "新建"},
                {"code": LeadStatus.FOLLOWING.name, "value": LeadStatus.FOLLOWING.value, "label": "跟进中"},
                {"code": LeadStatus.CONVERTED.name, "value": LeadStatus.CONVERTED.value, "label": "已转化"},
                {"code": LeadStatus.INVALID.name, "value": LeadStatus.INVALID.value, "label": "无效"},
            ],
        },
        "lead_source": {
            "type": "enum",
            "values": [{"code": s.name, "label": s.value} for s in LeadSource],
        },
        "company_scale": {
            "type": "enum",
            "values": [{"code": s.name, "label": s.value} for s in CompanyScale],
        },
        "follow_up_method": {
            "type": "enum",
            "values": [{"code": m.name, "label": m.value} for m in FollowUpMethod],
        },
        "customer_status": {
            "type": "enum",
            "values": [
                {"code": CustomerStatus.FOLLOWING.name, "value": CustomerStatus.FOLLOWING.value, "label": "跟进中"},
                {"code": CustomerStatus.WON.name, "value": CustomerStatus.WON.value, "label": "已成交"},
                {"code": CustomerStatus.LOST.name, "value": CustomerStatus.LOST.value, "label": "已流失"},
                {"code": CustomerStatus.INACTIVE.name, "value": CustomerStatus.INACTIVE.value, "label": "非激活"},
            ],
        },
        "customer_industry": {
            "type": "enum",
            "values": [{"code": i.name, "label": i.value} for i in CustomerIndustry],
        },
        "customer_source": {
            "type": "enum",
            "values": [{"code": s.name, "label": s.value} for s in CustomerSource],
        },
        "opportunity_status": {
            "type": "enum",
            "values": [
                {"code": OpportunityStatus.FOLLOWING.name, "value": OpportunityStatus.FOLLOWING.value, "label": "跟进中"},
                {"code": OpportunityStatus.WON.name, "value": OpportunityStatus.WON.value, "label": "赢单"},
                {"code": OpportunityStatus.LOST.name, "value": OpportunityStatus.LOST.value, "label": "输单"},
            ],
        },
        "purchase_type": {
            "type": "enum",
            "values": [{"code": t.name, "label": t.value} for t in PurchaseType],
        },
        "license_type": {
            "type": "enum",
            "values": [{"code": t.name, "label": t.value} for t in LicenseType],
        },
        "contract_status": {
            "type": "enum",
            "values": [
                {"code": "DRAFT", "label": "草稿"},
                {"code": "PENDING_REVIEW", "label": "待审核"},
                {"code": "SIGNED", "label": "已签署"},
                {"code": "EFFECTIVE", "label": "已生效"},
                {"code": "EXPIRED", "label": "已过期"},
                {"code": "TERMINATED", "label": "已终止"},
            ],
        },
        "payment_status": {
            "type": "enum",
            "values": [
                {"code": "UNPAID", "label": "未付款"},
                {"code": "PARTIAL", "label": "部分付款"},
                {"code": "COMPLETED", "label": "已完成"},
                {"code": "OVERDUE", "label": "逾期"},
            ],
        },
    }


__all__ = ["router"]
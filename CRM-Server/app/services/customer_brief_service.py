"""
客户概况 AI 生成服务

生成销售侧客户经营概况：客户档案、联系人、商机、合同、回款和跟进记录。
不纳入发票、License、部署交付等财务/交付侧流程。
"""
import asyncio
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.crud.ai_config import ai_config_crud
from app.crud.customer import customer_crud
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_follow_up import CustomerFollowUp
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


class CustomerBriefService:
    """客户概况生成服务"""

    async def generate_brief(self, customer_id: int, team_id: int) -> Dict[str, Any]:
        logger.info("开始生成客户概况: customer_id=%s, team_id=%s", customer_id, team_id)
        async with ai_generation_semaphore:
            try:
                db = SessionLocal()
                try:
                    customer_crud.update_customer_brief_status(db, customer_id, "GENERATING")

                    customer = db.query(Customer).filter(
                        Customer.id == customer_id,
                        Customer.team_id == team_id
                    ).first()
                    if not customer:
                        raise ValueError("客户不存在")

                    config = ai_config_crud.get_config(db, team_id)
                    if not config:
                        raise ValueError("AI 配置未设置")

                    api_host = config.api_host
                    model_name = config.model_name
                    api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
                    if not api_key:
                        raise ValueError("无法获取 API Key")

                    context = self._build_context(db, customer, team_id)
                finally:
                    db.close()

                prompt = self._build_prompt(context)
                content = await ai_service._stream_chat_collect(
                    api_host=api_host,
                    api_key=api_key,
                    model=model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                    timeout=120.0,
                )

                brief_json = self._parse_response(content)
                citation_map = context["citation_map"]
                markdown = self._render_markdown(brief_json)

                db = SessionLocal()
                try:
                    customer_crud.update_customer_brief(
                        db,
                        customer_id,
                        {
                            "customer_brief_json": json.dumps(brief_json, ensure_ascii=False),
                            "customer_brief_markdown": markdown,
                            "customer_brief_citations": json.dumps(citation_map, ensure_ascii=False),
                            "customer_brief_status": "COMPLETED",
                            "customer_brief_generated_time": datetime.now(),
                            "customer_brief_error_message": None,
                        },
                    )
                finally:
                    db.close()
                logger.info("客户概况生成完成: customer_id=%s", customer_id)
                return {"success": True, "customer_id": customer_id}

            except Exception as exc:
                logger.exception("客户概况生成失败: customer_id=%s", customer_id)
                db = SessionLocal()
                try:
                    customer_crud.update_customer_brief_status(db, customer_id, "FAILED", str(exc))
                except Exception:
                    logger.exception("更新客户概况失败状态失败: customer_id=%s", customer_id)
                finally:
                    db.close()
                return {"success": False, "customer_id": customer_id, "error": str(exc)}

    async def trigger_generation(self, customer_id: int, team_id: int) -> None:
        asyncio.create_task(self.generate_brief(customer_id=customer_id, team_id=team_id))

    def _build_context(self, db: Session, customer: Customer, team_id: int) -> Dict[str, Any]:
        citation_map: Dict[str, Dict[str, str]] = {}
        citation_index = 1

        def add_source(source_type: str, source_id: Any, title: str, excerpt: Optional[str] = None) -> str:
            nonlocal citation_index
            key = str(citation_index)
            citation_index += 1
            citation_map[key] = {
                "source_type": source_type,
                "source_id": str(source_id),
                "title": title,
                "excerpt": (excerpt or "")[:240],
            }
            return key

        customer_source = add_source(
            "customer",
            customer.id,
            f"客户：{customer.account_name}",
            f"城市：{customer.city}，规模：{customer.company_scale or '未填写'}，来源：{customer.source or '未填写'}",
        )

        profile_sources: List[str] = []
        if customer.profile_status == "COMPLETED":
            profile_sources.append(add_source("customer_profile", customer.id, "客户档案", customer.company_background))

        contacts = db.query(Contact).filter(
            Contact.customer_id == customer.id,
            Contact.team_id == team_id,
        ).order_by(Contact.is_primary.desc(), Contact.is_decision_maker.desc(), Contact.created_time.asc()).all()

        contact_items = []
        for contact in contacts:
            source = add_source("contact", contact.id, f"联系人：{contact.name}", contact.remark)
            contact_items.append({
                "source_id": source,
                "id": contact.id,
                "name": contact.name,
                "position": contact.position,
                "is_primary": bool(contact.is_primary),
                "is_decision_maker": bool(contact.is_decision_maker),
                "remark": contact.remark,
                "reports_to": contact.reports_to,
            })

        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == customer.id,
            Opportunity.team_id == team_id,
        ).order_by(Opportunity.status.asc(), Opportunity.last_modified_time.desc()).all()

        opportunity_items = []
        opportunity_sources_by_id: Dict[int, str] = {}
        for opp in opportunities:
            source = add_source("opportunity", opp.id, f"商机：{opp.opportunity_name}", opp.current_stage_name)
            opportunity_sources_by_id[int(opp.id)] = source
            opportunity_items.append({
                "source_id": source,
                "id": opp.id,
                "name": opp.opportunity_name,
                "stage": opp.current_stage_name,
                "win_probability": opp.current_win_probability,
                "amount": self._number(opp.total_amount),
                "actual_amount": self._number(opp.actual_amount),
                "user_count": opp.user_count,
                "license_type": opp.license_type,
                "subscription_years": opp.subscription_years,
                "purchase_type": opp.purchase_type,
                "decision_maker_count": opp.decision_maker_count,
                "expected_closing_date": self._date(opp.expected_closing_date),
                "status": opp.status,
                "approval_phase": opp.approval_phase,
                "loss_reason": opp.loss_reason,
                "created_time": self._datetime(opp.created_time),
                "actual_closing_date": self._date(opp.actual_closing_date),
            })

        contracts = db.query(Contract).options(
            joinedload(Contract.payment_plans).joinedload(PaymentPlan.payment_records)
        ).filter(
            Contract.customer_id == customer.id,
            Contract.team_id == team_id,
            Contract.deleted_at.is_(None),
        ).order_by(Contract.created_time.desc()).all()

        contract_items = []
        payment_plan_items = []
        payment_record_items = []
        payment_milestones = []

        for contract in contracts:
            source = add_source("contract", contract.id, f"合同：{contract.contract_name}", contract.contract_number)
            contract_items.append({
                "source_id": source,
                "id": contract.id,
                "opportunity_id": contract.opportunity_id,
                "opportunity_source_id": (
                    opportunity_sources_by_id.get(int(contract.opportunity_id))
                    if contract.opportunity_id is not None else None
                ),
                "contract_number": contract.contract_number,
                "contract_name": contract.contract_name,
                "amount": self._number(contract.total_amount),
                "user_count": contract.user_count,
                "license_type": contract.license_type,
                "subscription_years": contract.subscription_years,
                "status": contract.status,
                "approval_phase": contract.approval_phase,
                "signing_date": self._date(contract.signing_date),
                "effective_date": self._date(contract.effective_date),
                "payment_status": contract.payment_status,
                "total_paid_amount": self._number(contract.total_paid_amount),
                "created_time": self._datetime(contract.created_time),
            })

            for plan in sorted(contract.payment_plans or [], key=lambda item: item.due_date or date.min):
                plan_source = add_source("payment_plan", plan.id, f"回款计划：{plan.stage_name}", plan.notes)
                payment_plan_items.append({
                    "source_id": plan_source,
                    "id": plan.id,
                    "contract_id": contract.id,
                    "opportunity_id": contract.opportunity_id,
                    "stage_name": plan.stage_name,
                    "planned_amount": self._number(plan.planned_amount),
                    "due_date": self._date(plan.due_date),
                    "status": plan.status,
                    "notes": plan.notes,
                })

                for record in sorted(plan.payment_records or [], key=lambda item: item.payment_date or date.min):
                    record_source = add_source("payment_record", record.id, f"回款记录：{record.record_number}", record.notes)
                    record_item = {
                        "source_id": record_source,
                        "id": record.id,
                        "payment_plan_id": plan.id,
                        "contract_id": contract.id,
                        "opportunity_id": contract.opportunity_id,
                        "actual_amount": self._number(record.actual_amount),
                        "payment_date": self._date(record.payment_date),
                        "confirmation_status": record.confirmation_status,
                        "approval_phase": record.approval_phase,
                        "notes": record.notes,
                    }
                    payment_record_items.append(record_item)
                    payment_milestones.append(record_item)

        latest_follow_ups = db.query(CustomerFollowUp).filter(
            CustomerFollowUp.customer_id == customer.id,
            CustomerFollowUp.team_id == team_id,
        ).order_by(CustomerFollowUp.created_time.desc()).limit(200).all()
        follow_ups = sorted(latest_follow_ups, key=lambda item: item.created_time or datetime.min)

        follow_up_items = []
        for follow_up in follow_ups:
            candidates = self._candidate_opportunities(
                follow_up=follow_up,
                opportunities=opportunity_items,
                payment_records=payment_milestones,
            )
            source = add_source("follow_up", follow_up.id, f"跟进记录：{self._datetime(follow_up.created_time)}", follow_up.content)
            follow_up_items.append({
                "source_id": source,
                "id": follow_up.id,
                "content": follow_up.content,
                "method": follow_up.method,
                "next_follow_time": self._datetime(follow_up.next_follow_time),
                "next_action": follow_up.next_action,
                "created_time": self._datetime(follow_up.created_time),
                "candidate_opportunity_refs": candidates,
            })

        similar_customers = db.query(Customer.account_name).filter(
            Customer.team_id == team_id,
            Customer.id != customer.id,
            Customer.industry == customer.industry,
        ).order_by(Customer.last_modified_time.desc()).limit(10).all() if customer.industry else []

        return {
            "mode": "full_generate",
            "customer": {
                "source_id": customer_source,
                "id": customer.id,
                "account_name": customer.account_name,
                "industry": customer.industry,
                "city": customer.city,
                "address": customer.address,
                "company_scale": customer.company_scale,
                "source": customer.source,
                "status": customer.status,
                "created_time": self._datetime(customer.created_time),
                "returned_time": self._datetime(customer.returned_time),
                "return_reason": customer.return_reason,
                "loss_reason": customer.loss_reason,
            },
            "profile": {
                "status": customer.profile_status,
                "source_ids": profile_sources,
                "company_background": customer.company_background if customer.profile_status == "COMPLETED" else None,
                "main_business": customer.main_business if customer.profile_status == "COMPLETED" else None,
                "project_background": customer.project_background if customer.profile_status == "COMPLETED" else None,
                "similar_customers": customer.similar_customers if customer.profile_status == "COMPLETED" else None,
            },
            "contacts": contact_items,
            "opportunities": opportunity_items,
            "contracts": contract_items,
            "payment_plans": payment_plan_items,
            "payment_records": payment_record_items,
            "follow_ups": follow_up_items,
            "same_industry_customers": [row[0] for row in similar_customers],
            "citation_map": citation_map,
        }

    def _candidate_opportunities(
        self,
        follow_up: CustomerFollowUp,
        opportunities: List[Dict[str, Any]],
        payment_records: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        if not opportunities:
            return []

        active_opps = [opp for opp in opportunities if opp.get("status") == 0]
        created_at = follow_up.created_time

        if len(active_opps) == 1 and not payment_records:
            return [{
                "source_id": active_opps[0]["source_id"],
                "confidence": "high",
                "reason": "客户暂无回款记录，且仅有一个跟进中商机",
            }]

        candidates: List[Dict[str, str]] = []
        sorted_payments = sorted(
            [item for item in payment_records if item.get("payment_date")],
            key=lambda item: item["payment_date"],
        )
        follow_up_date = created_at.date().isoformat() if created_at else None

        if follow_up_date:
            previous_payment = None
            next_payment = None
            for payment in sorted_payments:
                if payment["payment_date"] <= follow_up_date:
                    previous_payment = payment
                elif payment["payment_date"] > follow_up_date and next_payment is None:
                    next_payment = payment

            if next_payment:
                opportunity = self._find_opportunity(opportunities, next_payment.get("opportunity_id"))
                if opportunity:
                    candidates.append({
                        "source_id": opportunity["source_id"],
                        "confidence": "medium",
                        "reason": "跟进时间早于后续回款节点，可能服务于该成交商机",
                    })
            elif previous_payment and len(active_opps) == 1:
                candidates.append({
                    "source_id": active_opps[0]["source_id"],
                    "confidence": "medium",
                    "reason": "跟进时间晚于历史回款，且当前仅有一个跟进中商机",
                })

        if not candidates and len(active_opps) == 1:
            candidates.append({
                "source_id": active_opps[0]["source_id"],
                "confidence": "medium",
                "reason": "当前仅有一个跟进中商机",
            })

        return candidates[:3]

    def _find_opportunity(self, opportunities: List[Dict[str, Any]], opportunity_id: Any) -> Optional[Dict[str, Any]]:
        for opportunity in opportunities:
            if opportunity.get("id") == opportunity_id:
                return opportunity
        return None

    def _get_system_prompt(self) -> str:
        return """你是 CRM 系统中的销售客户概况助手，目标是帮助销售人员和销售管理者快速理解客户销售进展。

只总结销售侧经营信息：客户档案、联系人、商机、合同、回款节点、跟进记录。不需要总结发票、License、部署交付等财务或售后流程。

输出要求：
1. 必须输出严格 JSON，不要输出 Markdown 或解释文字。
2. 只能使用输入事实，不要编造；没有明确内容时用空字符串或空数组。
3. 所有判断、总结、风险和下一步建议都尽量附 citations，引用输入中的 source_id。
4. 跟进记录没有显式绑定商机。输入可能提供 candidate_opportunity_refs，你可以结合时间线、回款节点、商机状态、金额、人数、授权类型、订阅/买断、增购/续购关键词进行弱分析。
5. 弱归因不能表述为确定事实；置信度不足时归入客户级跟进。
6. 多商机场景必须区分客户级概况和每个商机的进展，不要混成一段。
7. 客户档案状态不是 COMPLETED 时，企业背景、主营业务、项目背景等档案来源章节留空。

JSON 结构：
{
  "overview": {
    "enterprise_background": {"content": "", "citations": []},
    "rd_team_scale": {"content": "", "citations": []},
    "industry": {"content": "", "citations": []},
    "similar_customers": {"items": [], "citations": []},
    "organization": {"content": "", "items": [], "citations": []},
    "project_need_background": {"content": "", "citations": []},
    "procurement_progress": {"content": "", "citations": []},
    "follow_up_progress": {"content": "", "citations": []},
    "risks": {"items": [], "citations": []},
    "next_steps": {"items": [], "citations": []}
  },
  "opportunity_summaries": [
    {
      "opportunity_id": 0,
      "opportunity_name": "",
      "summary": "",
      "procurement_progress": "",
      "latest_progress": "",
      "risks": [],
      "next_steps": [],
      "citations": []
    }
  ]
}"""

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        return "请基于以下客户销售侧上下文生成客户概况：\n" + json.dumps(context, ensure_ascii=False, default=str)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError:
            logger.warning("客户概况 AI 返回 JSON 解析失败: %s", clean_content[:300])
            parsed = {}

        parsed.setdefault("overview", {})
        parsed.setdefault("opportunity_summaries", [])
        return parsed

    def _render_markdown(self, brief: Dict[str, Any]) -> str:
        overview = brief.get("overview") or {}

        def content(key: str) -> str:
            item = overview.get(key) or {}
            text = str(item.get("content") or "").strip()
            citations = self._format_citations(item.get("citations") or [])
            return f"{text}{citations}".strip()

        lines = [
            "## 客户概况",
            "",
            f"### 企业背景\n{content('enterprise_background')}",
            "",
            f"### 研发团队规模\n{content('rd_team_scale')}",
            "",
            f"### 行业与同行客户\n{content('industry')}",
        ]

        similar = overview.get("similar_customers") or {}
        similar_items = similar.get("items") or []
        if similar_items:
            lines.append("同行业客户：" + "、".join(str(item) for item in similar_items) + self._format_citations(similar.get("citations") or []))

        lines.extend([
            "",
            f"### 组织关系\n{content('organization')}",
            "",
            f"### 项目需求背景\n{content('project_need_background')}",
            "",
            f"### 项目采购进度\n{content('procurement_progress')}",
            "",
            f"### 客户跟进进展\n{content('follow_up_progress')}",
        ])

        for section_key, title in [("risks", "风险"), ("next_steps", "下一步")]:
            section = overview.get(section_key) or {}
            items = section.get("items") or []
            lines.extend(["", f"### {title}"])
            if items:
                lines.extend([f"- {item}" for item in items])

        opportunities = brief.get("opportunity_summaries") or []
        if opportunities:
            lines.extend(["", "## 商机概况"])
            for opportunity in opportunities:
                name = opportunity.get("opportunity_name") or f"商机 {opportunity.get('opportunity_id')}"
                citations = self._format_citations(opportunity.get("citations") or [])
                lines.extend([
                    "",
                    f"### {name}{citations}",
                    str(opportunity.get("summary") or "").strip(),
                    str(opportunity.get("procurement_progress") or "").strip(),
                    str(opportunity.get("latest_progress") or "").strip(),
                ])

        return "\n".join(line for line in lines if line is not None)

    def _format_citations(self, citations: List[Any]) -> str:
        values = [str(item) for item in citations if str(item).strip()]
        if not values:
            return ""
        return " " + " ".join(f"[{item}]" for item in values)

    def _number(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _date(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
        return str(value)

    def _datetime(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)


customer_brief_service = CustomerBriefService()

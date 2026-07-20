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
from typing import Any, Dict, List, Optional, Tuple

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

                brief_json = self._normalize_brief(self._parse_response(content), context)
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
            contact_excerpt_parts = [
                f"职位：{contact.position or '未填写'}",
                "主联系人" if contact.is_primary else "",
                "决策人" if contact.is_decision_maker else "",
                f"备注：{contact.remark}" if contact.remark else "",
            ]
            source = add_source(
                "contact",
                contact.id,
                f"联系人：{contact.name}",
                "，".join(part for part in contact_excerpt_parts if part),
            )
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
            opportunity_excerpt_parts = [
                f"阶段：{opp.current_stage_name or '未填写'}",
                f"金额：{self._number(opp.total_amount)}" if opp.total_amount is not None else "",
                f"用户数：{opp.user_count}" if opp.user_count is not None else "",
                f"授权：{opp.license_type or '未填写'}",
                f"预计成交：{self._date(opp.expected_closing_date)}" if opp.expected_closing_date else "",
            ]
            source = add_source(
                "opportunity",
                opp.id,
                f"商机：{opp.opportunity_name}",
                "，".join(part for part in opportunity_excerpt_parts if part),
            )
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
2. 只能使用输入事实，不要编造；没有明确内容时用空字符串或空数组，但不要因为客户档案缺失而忽略商机、联系人、跟进记录中的事实。
3. 所有判断、总结、风险和下一步建议都必须尽量附 citations，引用输入中的 source_id。
4. 跟进记录没有显式绑定商机。输入可能提供 candidate_opportunity_refs，你可以结合时间线、回款节点、商机状态、金额、人数、授权类型、订阅/买断、增购/续购关键词进行弱分析。
5. 弱归因不能表述为确定事实；置信度不足时归入客户级跟进。
6. 多商机场景必须区分客户级概况和每个商机的进展，不要混成一段。
7. 客户档案状态不是 COMPLETED 时，企业背景、主营业务、项目背景等档案来源章节留空。
8. 不要机械复述原始字段。每个章节回答不同问题：
   - enterprise_background：企业背景，只使用客户档案/客户基础资料。
   - rd_team_scale：研发或采购使用规模。优先使用商机 user_count / 合同 user_count；没有时再使用客户 company_scale。只要商机里有 user_count，就必须输出。
   - industry：行业归类和同行客户线索，不要重复企业背景。
   - organization：联系人和组织关系。即使只有 1 个联系人，也要说明“当前已记录 1 位联系人”，并标出职位、主联系人、决策人等已知信息。
   - project_need_background：客户为什么需要采购/替换/增购，提炼需求背景，不要写采购时间表。
   - procurement_progress：采购所处阶段和关键节点。跟进记录出现“立项、招标、挂网、投标、合同、回款、首付款、预算”等词时，要提炼成阶段判断，例如“正在准备立项材料”“预计挂网投标”“目标签约/回款时间”。
   - follow_up_progress：最近跟进动作和已达成共识，避免重复 procurement_progress 的完整时间表。
   - risks：只输出对成交有影响的风险；没有明确风险可为空，不要凑字。
   - next_steps：输出可执行动作，最多 3 条，按优先级排序。
9. 客户级概况只放跨商机或当前主要商机的结论；商机概况补充该商机自己的阶段、金额、授权、下一步。不要把同一句跟进记录在客户级和商机级完整重复。
10. 单个商机时，可以把跟进记录归到该商机，但客户级章节要提炼结论，商机级章节要补充交易信息。

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

    def _normalize_brief(self, brief: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        overview = brief.setdefault("overview", {})

        def ensure_section(key: str) -> Dict[str, Any]:
            section = overview.get(key)
            if not isinstance(section, dict):
                section = {}
                overview[key] = section
            section.setdefault("content", "")
            section.setdefault("citations", [])
            return section

        def is_blank(value: Any) -> bool:
            return str(value or "").strip() == ""

        rd_section = ensure_section("rd_team_scale")
        if is_blank(rd_section.get("content")):
            scale_content, citations = self._fallback_rd_team_scale(context)
            if scale_content:
                rd_section["content"] = scale_content
                rd_section["citations"] = citations

        organization_section = ensure_section("organization")
        if is_blank(organization_section.get("content")):
            organization_content, citations = self._fallback_organization(context)
            if organization_content:
                organization_section["content"] = organization_content
                organization_section["citations"] = citations

        industry_section = ensure_section("industry")
        if is_blank(industry_section.get("content")):
            customer = context.get("customer") or {}
            if customer.get("industry"):
                industry_section["content"] = str(customer["industry"])
                industry_section["citations"] = [customer.get("source_id")]

        procurement_section = ensure_section("procurement_progress")
        if is_blank(procurement_section.get("content")):
            procurement_content, citations = self._fallback_procurement_progress(context)
            if procurement_content:
                procurement_section["content"] = procurement_content
                procurement_section["citations"] = citations

        return brief

    def _fallback_rd_team_scale(self, context: Dict[str, Any]) -> Tuple[str, List[str]]:
        opportunities = context.get("opportunities") or []
        contracts = context.get("contracts") or []
        customer = context.get("customer") or {}

        opportunity_scales = [
            (opportunity.get("user_count"), opportunity.get("source_id"))
            for opportunity in opportunities
            if opportunity.get("user_count") is not None
        ]
        if opportunity_scales:
            max_scale, source_id = max(opportunity_scales, key=lambda item: int(item[0] or 0))
            return f"当前商机记录的采购/使用规模为 {max_scale} 人，可作为本次项目规模参考。", [source_id]

        contract_scales = [
            (contract.get("user_count"), contract.get("source_id"))
            for contract in contracts
            if contract.get("user_count") is not None
        ]
        if contract_scales:
            max_scale, source_id = max(contract_scales, key=lambda item: int(item[0] or 0))
            return f"历史合同记录的授权使用规模为 {max_scale} 人，可作为客户既有使用规模参考。", [source_id]

        company_scale = customer.get("company_scale")
        if company_scale:
            return f"客户档案中的公司规模为 {company_scale}，当前暂无更细的研发团队人数。", [customer.get("source_id")]

        return "", []

    def _fallback_organization(self, context: Dict[str, Any]) -> Tuple[str, List[str]]:
        contacts = context.get("contacts") or []
        if not contacts:
            return "", []

        descriptions = []
        citations = []
        for contact in contacts[:5]:
            labels = []
            if contact.get("position"):
                labels.append(str(contact["position"]))
            if contact.get("is_primary"):
                labels.append("主联系人")
            if contact.get("is_decision_maker"):
                labels.append("决策人")
            suffix = f"（{'，'.join(labels)}）" if labels else ""
            descriptions.append(f"{contact.get('name')}{suffix}")
            if contact.get("source_id"):
                citations.append(contact["source_id"])

        count_text = f"当前已记录 {len(contacts)} 位联系人"
        return f"{count_text}：" + "、".join(descriptions) + "。上下级关系暂未记录。", citations

    def _fallback_procurement_progress(self, context: Dict[str, Any]) -> Tuple[str, List[str]]:
        follow_ups = context.get("follow_ups") or []
        opportunities = context.get("opportunities") or []
        latest_follow_up = follow_ups[-1] if follow_ups else None

        if latest_follow_up and latest_follow_up.get("content"):
            content = str(latest_follow_up["content"])
            stage_phrases = []
            for keyword, phrase in [
                ("立项", "正在推进立项准备"),
                ("挂网", "已出现挂网/招标时间预期"),
                ("投标", "已进入投标准备或投标预期阶段"),
                ("合同", "已有合同签署时间预期"),
                ("首付款", "已有首付款回款目标"),
                ("回款", "已有回款节点预期"),
                ("预算", "需要继续确认预算"),
            ]:
                if keyword in content and phrase not in stage_phrases:
                    stage_phrases.append(phrase)

            if stage_phrases:
                return "；".join(stage_phrases) + "。", [latest_follow_up.get("source_id")]

        active_opportunities = [opportunity for opportunity in opportunities if opportunity.get("status") == 0]
        if active_opportunities:
            opportunity = active_opportunities[0]
            stage = opportunity.get("stage") or "未填写阶段"
            expected_date = opportunity.get("expected_closing_date")
            amount = opportunity.get("amount")
            parts = [f"当前主要商机处于「{stage}」"]
            if amount is not None:
                parts.append(f"预计金额 {amount}")
            if expected_date:
                parts.append(f"预计成交日期 {expected_date}")
            return "，".join(parts) + "。", [opportunity.get("source_id")]

        return "", []

    def _render_markdown(self, brief: Dict[str, Any]) -> str:
        overview = brief.get("overview") or {}

        def content(key: str) -> str:
            item = overview.get(key) or {}
            text = str(item.get("content") or "").strip()
            citations = self._format_citations(item.get("citations") or [])
            return f"{text}{citations}".strip()

        rendered_overview_values = {
            content(key)
            for key in [
                "enterprise_background",
                "rd_team_scale",
                "industry",
                "organization",
                "project_need_background",
                "procurement_progress",
                "follow_up_progress",
            ]
            if content(key)
        }

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
            section_citations = self._format_citations(section.get("citations") or [])
            lines.extend(["", f"### {title}"])
            if items:
                lines.extend([f"- {item}{section_citations}" for item in items])

        opportunities = brief.get("opportunity_summaries") or []
        if opportunities:
            lines.extend(["", "## 商机概况"])
            for opportunity in opportunities:
                name = opportunity.get("opportunity_name") or f"商机 {opportunity.get('opportunity_id')}"
                citations = self._format_citations(opportunity.get("citations") or [])
                lines.extend(["", f"### {name}{citations}"])

                seen_values = set(rendered_overview_values)
                for label, field in [
                    ("交易信息", "summary"),
                    ("采购进度", "procurement_progress"),
                    ("最新进展", "latest_progress"),
                ]:
                    value = str(opportunity.get(field) or "").strip()
                    if not value:
                        continue
                    value_with_citations = f"{value}{citations}".strip()
                    if value_with_citations in seen_values or value in seen_values:
                        continue
                    seen_values.add(value_with_citations)
                    lines.append(f"- **{label}**：{value_with_citations}")

                for field, label in [("risks", "风险"), ("next_steps", "下一步")]:
                    items = opportunity.get(field) or []
                    if not items:
                        continue
                    for item in items[:3]:
                        item_text = str(item).strip()
                        if item_text:
                            lines.append(f"- **{label}**：{item_text}{citations}")

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

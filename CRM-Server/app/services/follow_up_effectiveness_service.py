"""AI evaluation service for customer follow-up effectiveness."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.crud.ai_config import ai_config_crud
from app.crud.customer_follow_up import customer_follow_up_crud
from app.models.customer import Contact, Customer
from app.models.customer_follow_up import CustomerFollowUp
from app.models.opportunity import Opportunity
from app.services.ai_service import ai_service
from app.services.ai_task_limiter import ai_generation_semaphore


logger = logging.getLogger(__name__)


class FollowUpEffectivenessService:
    """Evaluate whether a customer follow-up record is useful for sales handoff."""

    async def evaluate(self, follow_up_id: int, team_id: int) -> Dict[str, Any]:
        logger.info("开始评估跟进记录有效性: follow_up_id=%s, team_id=%s", follow_up_id, team_id)
        async with ai_generation_semaphore:
            try:
                db = SessionLocal()
                try:
                    customer_follow_up_crud.update_effectiveness_status(db, follow_up_id, "GENERATING")

                    follow_up = customer_follow_up_crud.get_by_id(db, follow_up_id, team_id)
                    if not follow_up:
                        raise ValueError("跟进记录不存在")

                    config = ai_config_crud.get_config(db, team_id)
                    if not config:
                        raise ValueError("AI 配置未设置")

                    api_host = config.api_host
                    model_name = config.model_name
                    api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
                    if not api_key:
                        raise ValueError("无法获取 API Key")

                    context = self._build_context(db, follow_up, team_id)
                finally:
                    db.close()

                content = await ai_service._stream_chat_collect(
                    api_host=api_host,
                    api_key=api_key,
                    model=model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": self._build_prompt(context)},
                    ],
                    temperature=0.1,
                    max_tokens=1800,
                    response_format={"type": "json_object"},
                    timeout=90.0,
                )

                result = self._normalize_result(self._parse_response(content))

                db = SessionLocal()
                try:
                    customer_follow_up_crud.update_effectiveness_result(
                        db=db,
                        follow_up_id=follow_up_id,
                        score=result["score"],
                        is_valid=result["is_valid"],
                        reason=result["reason"],
                        detail_json=json.dumps(result.get("principle_scores", {}), ensure_ascii=False),
                    )
                finally:
                    db.close()

                logger.info("跟进记录有效性评估完成: follow_up_id=%s, score=%s", follow_up_id, result["score"])
                return {"success": True, "follow_up_id": follow_up_id, "score": result["score"]}

            except Exception as exc:
                logger.exception("跟进记录有效性评估失败: follow_up_id=%s", follow_up_id)
                db = SessionLocal()
                try:
                    customer_follow_up_crud.update_effectiveness_status(db, follow_up_id, "FAILED", str(exc))
                except Exception:
                    logger.exception("更新跟进记录评估失败状态失败: follow_up_id=%s", follow_up_id)
                finally:
                    db.close()
                return {"success": False, "follow_up_id": follow_up_id, "error": str(exc)}

    async def trigger_evaluation(self, follow_up_id: int, team_id: int) -> None:
        asyncio.create_task(self.evaluate(follow_up_id=follow_up_id, team_id=team_id))

    def _build_context(self, db: Session, follow_up: CustomerFollowUp, team_id: int) -> Dict[str, Any]:
        customer = db.query(Customer).filter(
            Customer.id == follow_up.customer_id,
            Customer.team_id == team_id,
        ).first() if follow_up.customer_id else None

        contacts = db.query(Contact).filter(
            Contact.customer_id == follow_up.customer_id,
            Contact.team_id == team_id,
        ).order_by(Contact.is_primary.desc(), Contact.is_decision_maker.desc(), Contact.created_time.asc()).limit(20).all() if follow_up.customer_id else []

        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == follow_up.customer_id,
            Opportunity.team_id == team_id,
        ).order_by(Opportunity.status.asc(), Opportunity.last_modified_time.desc()).limit(20).all() if follow_up.customer_id else []

        previous_follow_ups = db.query(CustomerFollowUp).filter(
            CustomerFollowUp.customer_id == follow_up.customer_id,
            CustomerFollowUp.team_id == team_id,
            CustomerFollowUp.id != follow_up.id,
            CustomerFollowUp.created_time <= follow_up.created_time,
        ).order_by(CustomerFollowUp.created_time.desc()).limit(5).all() if follow_up.customer_id else []

        return {
            "current_follow_up": self._follow_up_to_dict(follow_up),
            "customer": {
                "id": customer.id,
                "account_name": customer.account_name,
                "industry": customer.industry,
                "city": customer.city,
                "company_scale": customer.company_scale,
                "source": customer.source,
            } if customer else None,
            "contacts": [
                {
                    "name": contact.name,
                    "position": contact.position,
                    "mobile": contact.mobile,
                    "email": contact.email,
                    "is_primary": bool(contact.is_primary),
                    "is_decision_maker": bool(contact.is_decision_maker),
                    "remark": contact.remark,
                }
                for contact in contacts
            ],
            "opportunities": [
                {
                    "id": opportunity.id,
                    "name": opportunity.opportunity_name,
                    "stage": opportunity.current_stage_name,
                    "win_probability": opportunity.current_win_probability,
                    "amount": self._number(opportunity.total_amount),
                    "user_count": opportunity.user_count,
                    "license_type": opportunity.license_type,
                    "subscription_years": opportunity.subscription_years,
                    "purchase_type": opportunity.purchase_type,
                    "expected_closing_date": self._date(opportunity.expected_closing_date),
                    "status": opportunity.status,
                }
                for opportunity in opportunities
            ],
            "previous_follow_ups": [
                self._follow_up_to_dict(item)
                for item in reversed(previous_follow_ups)
            ],
        }

    def _follow_up_to_dict(self, follow_up: CustomerFollowUp) -> Dict[str, Any]:
        return {
            "id": follow_up.id,
            "content": follow_up.content,
            "method": follow_up.method,
            "next_follow_time": self._datetime(follow_up.next_follow_time),
            "next_action": follow_up.next_action,
            "created_time": self._datetime(follow_up.created_time),
        }

    def _get_system_prompt(self) -> str:
        return """你是 CRM 系统中的销售跟进记录质检助手。你的任务是判断一条客户跟进记录是否对销售推进和团队接力有价值。

请按 6 大原则评分，满分 100 分：
1. 事实优先原则（20分）：只写客观事实、客户原话、已发生动作；不要把“感觉、应该、挺好、有戏”等主观判断当作有效信息。
2. 动作闭环原则（20分）：必须说明下一步什么时间、谁、做什么；“保持跟进、再联系、有消息再说”不得高分。
3. 阶段推进原则（15分）：结合当前商机和前序跟进，判断本次是否推动阶段、明确新节点或消除关键不确定性；连续原地询问不得高分。
4. 决策穿透原则（15分）：是否识别决策人、影响人、采购/技术/财务等角色和诉求；只写“客户说”不得高分。
5. 异议具象原则（15分）：是否具体记录价格、竞品、预算、流程、技术、安全等异议及原因；没有异议时可说明“本次未出现明确异议”，但不能编造。
6. 信息可接力原则（15分）：团队其他人看完后是否知道客户、对接人、当前进展、风险和下一步，不需要再问记录者。

评估要求：
- 只基于输入内容和上下文评分，不要编造。
- 当前记录本身最重要；客户、联系人、商机、历史跟进只用于判断上下文和阶段推进。
- 记录很短、缺少对接人/时间/下一步/风险时，即使语气积极，也要扣分。
- score 必须是 0-100 的整数；is_valid 必须按 score > 60 判断。
- reason 必须是一句话，优先说明扣分最多的 1-2 个原因，适合放在 tooltip 中，最长 80 个中文字符。
- 输出严格 JSON，不要 Markdown，不要解释文字。

JSON 结构：
{
  "score": 0,
  "is_valid": false,
  "reason": "",
  "principle_scores": {
    "facts": {"score": 0, "max_score": 20, "comment": ""},
    "action_closure": {"score": 0, "max_score": 20, "comment": ""},
    "stage_progression": {"score": 0, "max_score": 15, "comment": ""},
    "decision_chain": {"score": 0, "max_score": 15, "comment": ""},
    "specific_objection": {"score": 0, "max_score": 15, "comment": ""},
    "handoffability": {"score": 0, "max_score": 15, "comment": ""}
  }
}"""

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        return "请评估以下客户跟进记录是否有效：\n" + json.dumps(context, ensure_ascii=False, default=str)

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
            return json.loads(clean_content)
        except json.JSONDecodeError:
            logger.warning("跟进记录有效性 AI 返回 JSON 解析失败: %s", clean_content[:300])
            return {}

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        raw_score = result.get("score", 0)
        try:
            score = int(round(float(raw_score)))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))

        reason = str(result.get("reason") or "").strip()
        if not reason:
            reason = "缺少可接力的关键信息或明确下一步动作。"

        return {
            "score": score,
            "is_valid": score > 60,
            "reason": reason[:120],
            "principle_scores": result.get("principle_scores") if isinstance(result.get("principle_scores"), dict) else {},
        }

    def _datetime(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    def _date(self, value: Any) -> Optional[str]:
        return value.isoformat() if value else None

    def _number(self, value: Any) -> Optional[float]:
        return float(value) if value is not None else None


follow_up_effectiveness_service = FollowUpEffectivenessService()

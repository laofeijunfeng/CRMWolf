"""Run business/data-driven evaluations through the Agent HTTP interface.

The script intentionally uses the public Agent SSE endpoint instead of calling
Agent internals, so failures include auth, session persistence, LangGraph
routing, tool API calls, and answer generation boundaries.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import ValidationError

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.core.database import SessionLocal
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.deployment import DeploymentInfo
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity
from app.crud.customer_member import customer_member_crud
from app.models.payment import PaymentPlan, PaymentRecord
from app.schemas.agent import AgentSSEEventEnvelope


JSONDict = dict[str, Any]

@dataclass
class EvalCase:
    case_id: str
    category: str
    content: str
    expected_route: str | None = None
    expected_customer_name: str | None = None
    expected_action_status: str | None = None
    required_terms: list[str] = field(default_factory=list)
    forbidden_terms: list[str] = field(default_factory=list)
    confirm: bool = False
    second_turn: str = "确认执行"


@dataclass
class CaseResult:
    case_id: str
    category: str
    content: str
    passed: bool
    reasons: list[str]
    session_id: int | None
    events_seen: list[str]
    routes_seen: list[str]
    block_types_seen: list[str]
    action_statuses_seen: list[str]
    final_answer: str
    first_turn_event_count: int
    second_turn_event_count: int
    elapsed_seconds: float


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CRMWolf Agent business evaluation cases.")
    parser.add_argument("--base-url", default=os.getenv("CRM_AGENT_EVAL_BASE_URL", "http://127.0.0.1:8000/api"))
    parser.add_argument("--token", default=os.getenv("CRM_AGENT_EVAL_TOKEN"))
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--category", action="append", default=None, help="Run only cases in the given category. Can be repeated.")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--team-id",
        type=int,
        default=(int(os.environ["CRM_AGENT_EVAL_TEAM_ID"]) if os.getenv("CRM_AGENT_EVAL_TEAM_ID") else None),
        help="评测团队 ID；未提供时从认证用户的当前团队解析",
    )
    parser.add_argument("--confirm-writes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    if not args.token and not args.dry_run:
        raise SystemExit("Missing --token or CRM_AGENT_EVAL_TOKEN")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir or f"/tmp/crmwolf_agent_eval_{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    events_dir = out_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=httpx.Timeout(args.timeout, connect=20.0))
    try:
        team_id = resolve_team_id(client, token=args.token, explicit_team_id=args.team_id)
    finally:
        client.close()

    snapshot = build_data_snapshot(team_id)
    case_limit = 1000 if args.category else args.limit
    cases = build_cases(snapshot, limit=case_limit, confirm_writes=args.confirm_writes)
    if args.category:
        categories = set(args.category)
        cases = [case for case in cases if case.category in categories][: args.limit]
    write_json(out_dir / "cases.json", [asdict(case) for case in cases])

    if args.dry_run:
        write_markdown_report(out_dir / "report.md", snapshot=snapshot, results=[], dry_run=True)
        print(json.dumps({"ok": True, "dry_run": True, "case_count": len(cases), "out_dir": str(out_dir)}, ensure_ascii=False))
        return

    results: list[CaseResult] = []
    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=httpx.Timeout(args.timeout, connect=20.0))
    try:
        for index, case in enumerate(cases, start=1):
            started = time.monotonic()
            first_events = call_agent(client, token=args.token, content=case.content)
            session_id = extract_session_id(first_events)
            second_events: list[JSONDict] = []
            if case.confirm and args.confirm_writes and session_id:
                all_events = list(first_events)
                for _ in range(3):
                    if expected_action_succeeded(case, all_events):
                        break
                    resume_input = next_resume_input(all_events, fallback_confirmation=case.second_turn)
                    if not resume_input:
                        break
                    followup_events = call_agent(
                        client,
                        token=args.token,
                        request_input=resume_input,
                        session_id=session_id,
                    )
                    second_events.extend(followup_events)
                    all_events.extend(followup_events)
            result = evaluate_case(case, first_events, second_events, time.monotonic() - started)
            results.append(result)
            write_json(events_dir / f"{case.case_id}.json", {
                "case": asdict(case),
                "first_events": first_events,
                "second_events": second_events,
                "result": asdict(result),
            })
            print(
                json.dumps(
                    {
                        "index": index,
                        "case_id": case.case_id,
                        "passed": result.passed,
                        "reasons": result.reasons,
                        "routes": result.routes_seen,
                        "blocks": result.block_types_seen,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        client.close()

    write_json(out_dir / "results.json", [asdict(result) for result in results])
    write_markdown_report(out_dir / "report.md", snapshot=snapshot, results=results, dry_run=False)
    passed = sum(1 for item in results if item.passed)
    print(json.dumps({"ok": passed == len(results), "total": len(results), "passed": passed, "failed": len(results) - passed, "out_dir": str(out_dir)}, ensure_ascii=False))


def resolve_team_id(
    client: httpx.Client,
    *,
    token: str | None,
    explicit_team_id: int | None,
) -> int:
    """Resolve and validate the tenant scope used by the data snapshot.

    The evaluator must never silently fall back to a global or hard-coded team.
    When a token is available, the team endpoint also validates that an explicit
    team belongs to the authenticated user before the local snapshot is built.
    """
    if explicit_team_id is not None and explicit_team_id <= 0:
        raise SystemExit("--team-id must be greater than zero")
    if not token:
        if explicit_team_id is None:
            raise SystemExit("Dry-run without a token requires --team-id or CRM_AGENT_EVAL_TEAM_ID")
        return explicit_team_id

    headers = {"Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}"}
    path = f"/v1/teams/{explicit_team_id}" if explicit_team_id is not None else "/v1/teams/me"
    try:
        response = client.get(path, headers=headers)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SystemExit(f"无法解析认证用户的评测团队：{exc}") from exc
    resolved_team_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(resolved_team_id, int) or resolved_team_id <= 0:
        raise SystemExit("团队接口未返回有效 team_id")
    return resolved_team_id


def build_data_snapshot(team_id: int) -> JSONDict:
    db = SessionLocal()
    try:
        counts = {
            "customers": team_scoped_count(db, Customer, team_id),
            "contacts": team_scoped_count(db, Contact, team_id),
            "activities": team_scoped_count(db, CustomerActivity, team_id),
            "opportunities": team_scoped_count(db, Opportunity, team_id),
            "contracts": team_scoped_count(db, Contract, team_id),
            "payment_plans": team_scoped_count(db, PaymentPlan, team_id),
            "payment_records": team_scoped_count(db, PaymentRecord, team_id),
            "invoice_titles": team_scoped_count(db, InvoiceTitle, team_id),
            "invoice_applications": team_scoped_count(db, InvoiceApplication, team_id),
            "license_applications": team_scoped_count(db, LicenseApplication, team_id),
            "deployment_infos": team_scoped_count(db, DeploymentInfo, team_id),
            "vector_documents": team_scoped_count(db, CustomerVectorDocument, team_id),
        }
        customers = [
            {
                "id": customer.id,
                "public_id": customer.public_id,
                "account_name": customer.account_name,
                "industry": customer.industry,
                "city": customer.city,
                "status": customer.status,
                "activity_count": customer_object_count(db, CustomerActivity, customer.id, team_id),
                "opportunity_count": customer_object_count(db, Opportunity, customer.id, team_id),
                "contract_count": customer_object_count(db, Contract, customer.id, team_id),
            }
            for customer in db.query(Customer)
            .filter(Customer.team_id == team_id)
            .order_by(Customer.id.asc())
            .limit(30)
            .all()
        ]
        rich_customer_ids = [item["id"] for item in customers if item["activity_count"] or item["opportunity_count"] or item["contract_count"]]
        objects = {
            "contacts": rows_for_customer_objects(db, Contact, rich_customer_ids, team_id=team_id),
            "activities": rows_for_customer_objects(db, CustomerActivity, rich_customer_ids, team_id=team_id),
            "opportunities": rows_for_customer_objects(db, Opportunity, rich_customer_ids, team_id=team_id),
            "contracts": rows_for_customer_objects(db, Contract, rich_customer_ids, team_id=team_id),
            "payment_plans": rows_for_payment_plans(db, rich_customer_ids, team_id=team_id),
            "invoice_titles": rows_for_customer_objects(db, InvoiceTitle, rich_customer_ids, team_id=team_id),
            "deployments": rows_for_customer_objects(db, DeploymentInfo, rich_customer_ids, team_id=team_id),
            "licenses": rows_for_customer_objects(db, LicenseApplication, rich_customer_ids, team_id=team_id),
        }
        member_candidates_by_customer_id = {}
        for customer in customers:
            candidates = customer_member_crud.get_candidates(db, team_id, customer["id"])
            available = [item for item in candidates if not item.get("already_member")]
            if available:
                member_candidates_by_customer_id[str(customer["id"])] = available[0]
        return {
            "team_id": team_id,
            "counts": counts,
            "customers": customers,
            "objects": objects,
            "member_candidates_by_customer_id": member_candidates_by_customer_id,
        }
    finally:
        db.close()


def team_scoped_count(db: Any, model: Any, team_id: int) -> int:
    return db.query(model).filter(model.team_id == team_id).count()


def customer_object_count(db: Any, model: Any, customer_id: int, team_id: int) -> int:
    return db.query(model).filter(model.team_id == team_id, model.customer_id == customer_id).count()


def rows_for_customer_objects(
    db: Any,
    model: Any,
    customer_ids: list[int],
    *,
    team_id: int,
    limit: int = 12,
) -> list[JSONDict]:
    if not customer_ids:
        return []
    rows = (
        db.query(model)
        .filter(model.team_id == team_id, model.customer_id.in_(customer_ids))
        .order_by(model.id.asc())
        .limit(limit)
        .all()
    )
    return [{"id": row.id, "customer_id": row.customer_id, "label": object_label(row)} for row in rows]


def rows_for_payment_plans(
    db: Any,
    customer_ids: list[int],
    *,
    team_id: int,
    limit: int = 12,
) -> list[JSONDict]:
    if not customer_ids:
        return []
    rows = (
        db.query(PaymentPlan, Contract.customer_id)
        .join(Contract, Contract.id == PaymentPlan.contract_id)
        .filter(
            PaymentPlan.team_id == team_id,
            Contract.team_id == team_id,
            Contract.customer_id.in_(customer_ids),
        )
        .order_by(PaymentPlan.id.asc())
        .limit(limit)
        .all()
    )
    return [{"id": plan.id, "customer_id": customer_id, "label": object_label(plan)} for plan, customer_id in rows]


def object_label(row: Any) -> str:
    for attr in ("name", "title", "summary", "opportunity_name", "contract_name", "stage_name", "deployment_name", "application_number"):
        value = getattr(row, attr, None)
        if value:
            return str(value)[:80]
    return str(getattr(row, "id", ""))


def build_cases(snapshot: JSONDict, *, limit: int, confirm_writes: bool) -> list[EvalCase]:
    customers = snapshot["customers"]
    by_id = {item["id"]: item for item in customers}
    rich = [item for item in customers if item["activity_count"] or item["opportunity_count"] or item["contract_count"]] or customers
    tests = [item for item in customers if "测试公司" in item["account_name"]] or customers[-3:] or customers
    stamp = datetime.now().strftime("%m%d%H%M%S")
    cases: list[EvalCase] = []

    for customer in rich[:10]:
        name = customer["account_name"]
        cases.extend(
            [
                EvalCase(f"read_summary_{customer['id']}", "read_customer_summary", f"请总结一下{name}当前客户情况，包括业务背景、最近进展和下一步建议", "QUERY", name, required_terms=[short_name(name)]),
                EvalCase(f"read_contacts_{customer['id']}", "read_contacts", f"{name}现在有哪些联系人和关键决策人？", "QUERY", name, required_terms=[short_name(name), "联系人"]),
                EvalCase(f"read_followups_{customer['id']}", "read_followups", f"帮我看下{name}最近跟进记录和待办下一步", "QUERY", name, required_terms=[short_name(name)]),
            ]
        )
        if len(cases) >= 24:
            break

    for key, template, term in [
        ("opportunities", "{name}有哪些商机？阶段、金额、预计成交时间分别是什么？", "商机"),
        ("contracts", "{name}合同情况怎么样？合同金额、状态和回款状态是什么？", "合同"),
        ("payment_plans", "{name}回款计划和已回款情况怎么样？有没有风险？", "回款"),
        ("invoice_titles", "{name}现在有哪些发票抬头？", "发票"),
        ("deployments", "{name}部署信息是什么？", "部署"),
        ("licenses", "{name}License 申请和到期情况怎么样？", "License"),
    ]:
        seen: set[int] = set()
        for obj in snapshot["objects"].get(key, []):
            customer = by_id.get(obj["customer_id"])
            if not customer or customer["id"] in seen:
                continue
            seen.add(customer["id"])
            name = customer["account_name"]
            cases.append(EvalCase(f"read_{key}_{customer['id']}", f"read_{key}", template.format(name=name), "QUERY", name, required_terms=[term]))
            if len(seen) >= 3:
                break

    test_customer = tests[0]
    test_name = test_customer["account_name"]
    member_candidate = (snapshot.get("member_candidates_by_customer_id") or {}).get(str(test_customer["id"])) or {}
    member_name = str(member_candidate.get("name") or "Rayson").strip()
    write_templates = [
        ("write_activity", f"给{test_name}记录一条跟进：本地 Agent 评测 {stamp}，今天电话沟通了试用反馈，客户关注权限体系和数据报表，下周三继续确认采购预算。"),
        ("write_contact", f"给{test_name}新增联系人：评测联系人{stamp}，手机号 139{stamp[-8:] if len(stamp) >= 8 else '00000000'}，职位信息化经理，男，是关键决策人。"),
        ("write_opportunity", f"给{test_name}创建一个商机：本地评测新购 50 用户，订阅 1 年，预计金额 50000 元，预计 9 月 30 日成交，采购方式用默认采购方式，2 个决策人。"),
        ("write_invoice_title", f"给{test_name}新增单位发票抬头：{test_name}评测抬头{stamp}，税号 91310000{stamp[-8:] if len(stamp) >= 8 else '00000000'}，开户行 招商银行广州分行，账号 622588{stamp[-8:] if len(stamp) >= 8 else '00000000'}，设为默认。"),
        ("write_deployment", f"给{test_name}新增部署信息：评测环境{stamp}，服务器地址 https://eval-{stamp}.crmwolf.local，设为默认部署。"),
        ("write_member", f"把 {member_name} 加到{test_name}客户团队，角色售前，可跟进，备注本地 Agent 评测 {stamp}。"),
    ]
    for category, content in write_templates:
        cases.append(
            EvalCase(
                f"{category}_{stamp}",
                category,
                content,
                expected_customer_name=test_name,
                expected_route="WORKFLOW",
                expected_action_status="SUCCESS" if confirm_writes else None,
                confirm=confirm_writes,
            )
        )

    cases.extend(
        [
            EvalCase("ambiguous_test_company", "ambiguous_resolution", "帮我看下测试公司现在的客户情况", "QUERY", None, required_terms=["测试公司"]),
            EvalCase("unknown_customer", "unknown_customer", f"帮我查一下不存在的本地评测客户{stamp}的合同和回款", "QUERY", None, forbidden_terms=["已成交", "合同金额"]),
            EvalCase("generic_customer_query", "clarification", "这个客户最近怎么样？", "CLARIFY", None),
        ]
    )
    return cases[:limit]


def call_agent(
    client: httpx.Client,
    *,
    token: str,
    content: str | None = None,
    request_input: JSONDict | None = None,
    session_id: int | None = None,
) -> list[JSONDict]:
    if (content is None) == (request_input is None):
        raise ValueError("provide exactly one of content or request_input")
    payload: JSONDict = {
        "client_request_id": str(uuid4()),
        "input": request_input or {"type": "text", "text": content},
    }
    if session_id:
        payload["session_id"] = session_id
    headers = {"Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}"}
    events: list[JSONDict] = []
    try:
        with client.stream("POST", "/v1/agent/chat/stream", headers=headers, json=payload) as response:
            if response.status_code >= 400:
                response.read()
                events.append({"event": "http_error", "status_code": response.status_code, "message": response.text})
                return events
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError as exc:
                    events.append({"event": "decode_error", "message": str(exc), "line": line[:500]})
    except httpx.TimeoutException as exc:
        events.append({"event": "timeout", "message": str(exc)})
    except httpx.HTTPError as exc:
        events.append({"event": "http_client_error", "message": str(exc)})
    return events


def evaluate_case(
    case: EvalCase,
    first_events: list[JSONDict],
    second_events: list[JSONDict],
    elapsed: float,
) -> CaseResult:
    events = [*first_events, *second_events]
    names = [str(event.get("event")) for event in events if event.get("event")]
    envelopes = final_envelopes(events)
    routes = unique_strings(
        str(metadata.get("route"))
        for envelope in envelopes
        if isinstance(metadata := envelope.get("metadata"), dict) and metadata.get("route")
    )
    blocks = [
        block
        for envelope in envelopes
        for block in envelope.get("blocks", [])
        if isinstance(block, dict)
    ]
    block_types = unique_strings(str(block.get("type")) for block in blocks if block.get("type"))
    action_statuses = unique_strings(
        str(block.get("status"))
        for block in blocks
        if block.get("type") == "action_result" and block.get("status")
    )
    final_answer = extract_final_answer(events)
    entity_names = extract_entity_names(events)
    reasons: list[str] = []

    if "http_error" in names:
        reasons.append("HTTP 请求失败")
    if "http_client_error" in names:
        reasons.append("HTTP 客户端异常")
    if "timeout" in names:
        reasons.append("Agent SSE 响应超时")
    if "decode_error" in names:
        reasons.append("Agent SSE JSON 解析失败")
    for error in protocol_validation_errors(events):
        reasons.append(f"Agent UI v1 协议校验失败：{error}")
    transport_errors = [event for event in events if event.get("event") == "transport_error"]
    if transport_errors:
        reasons.append(f"Agent 返回 transport_error：{transport_errors[-1].get('code', 'UNKNOWN')}")
    if "done" not in names:
        reasons.append("未收到 done 事件")
    if case.expected_route and case.expected_route not in routes:
        reasons.append(f"未看到期望路由 {case.expected_route}")
    if case.expected_customer_name and not expected_customer_resolved(case, events):
        reasons.append(f"未解析到期望客户：{case.expected_customer_name}")
    for term in case.required_terms:
        if term and term not in final_answer and not any(term in name for name in entity_names):
            reasons.append(f"回复缺少关键词：{term}")
    for term in case.forbidden_terms:
        if term and term in final_answer:
            reasons.append(f"回复出现禁用词：{term}")
    if re.search(r"\b(crm_|tool_|Qdrant|LangGraph|evidence_id)\b", final_answer, flags=re.I):
        reasons.append("回复暴露内部实现词")
    if case.expected_action_status and case.expected_action_status not in action_statuses:
        reasons.append(f"未看到期望操作结果 {case.expected_action_status}")

    return CaseResult(
        case_id=case.case_id,
        category=case.category,
        content=case.content,
        passed=not reasons,
        reasons=reasons,
        session_id=extract_session_id(events),
        events_seen=names,
        routes_seen=routes,
        block_types_seen=block_types,
        action_statuses_seen=action_statuses,
        final_answer=final_answer[:2000],
        first_turn_event_count=len(first_events),
        second_turn_event_count=len(second_events),
        elapsed_seconds=round(elapsed, 2),
    )


def final_envelope(event: JSONDict) -> JSONDict | None:
    if event.get("event") != "agent_ui" or event.get("phase") != "final":
        return None
    try:
        parsed = AgentSSEEventEnvelope.model_validate(event).root
    except ValidationError:
        return None
    if getattr(parsed, "event", None) != "agent_ui" or getattr(parsed, "phase", None) != "final":
        return None
    return parsed.message.model_dump(mode="python")


_NON_PROTOCOL_EVENTS = {"http_error", "decode_error", "timeout", "http_client_error"}


def protocol_validation_errors(events: list[JSONDict]) -> list[str]:
    """Validate every public SSE event without masking malformed final events."""
    errors: list[str] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("event") in _NON_PROTOCOL_EVENTS:
            continue
        try:
            AgentSSEEventEnvelope.model_validate(event)
        except ValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else {}
            location = ".".join(str(item) for item in first_error.get("loc", ())) or "event"
            message = str(first_error.get("msg", "invalid event"))
            errors.append(f"event[{index}] {location}: {message}")
    return errors


def final_envelopes(events: list[JSONDict]) -> list[JSONDict]:
    return [envelope for event in events if (envelope := final_envelope(event)) is not None]


def unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        value = str(value)
        if value and value not in result:
            result.append(value)
    return result


def extract_entity_names(events: list[JSONDict]) -> list[str]:
    names: list[str] = []
    for envelope in final_envelopes(events):
        for block in envelope.get("blocks", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "entity_list":
                items = block.get("items", [])
                for item in items if isinstance(items, list) else []:
                    entity_ref = item.get("entity_ref") if isinstance(item, dict) else None
                    display_name = entity_ref.get("display_name") if isinstance(entity_ref, dict) else None
                    if display_name:
                        names.append(str(display_name))
            elif block.get("type") == "entity_card" and block.get("title"):
                names.append(str(block["title"]))
            elif block.get("type") == "action_result":
                entity_ref = block.get("entity_ref")
                display_name = entity_ref.get("display_name") if isinstance(entity_ref, dict) else None
                if display_name:
                    names.append(str(display_name))
    return unique_strings(names)


def extract_session_id(events: list[JSONDict]) -> int | None:
    for event in events:
        value = event.get("session_id")
        if isinstance(value, int):
            return value
    return None



def expected_action_succeeded(case: EvalCase, events: list[JSONDict]) -> bool:
    return bool(
        case.expected_action_status
        and case.expected_action_status in {
            str(block.get("status"))
            for envelope in final_envelopes(events)
            for block in envelope.get("blocks", [])
            if isinstance(block, dict) and block.get("type") == "action_result"
        }
    )


def expected_customer_resolved(case: EvalCase, events: list[JSONDict]) -> bool:
    if not case.expected_customer_name:
        return False
    return case.expected_customer_name in extract_entity_names(events)


def next_resume_input(events: list[JSONDict], *, fallback_confirmation: str) -> JSONDict | None:
    for envelope in reversed(final_envelopes(events)):
        blocks = envelope.get("blocks", [])
        for block in reversed(blocks if isinstance(blocks, list) else []):
            if not isinstance(block, dict) or block.get("type") != "interaction":
                continue
            if block.get("state") != "ACTIVE" or not block.get("submit_action_id"):
                continue
            values = interaction_values(block, fallback_confirmation=fallback_confirmation)
            if values is None:
                continue
            return {
                "type": "interaction_submission",
                "action_id": str(block["submit_action_id"]),
                "values": values,
            }
    return None


def interaction_values(block: JSONDict, *, fallback_confirmation: str) -> JSONDict | None:
    interaction_type = block.get("interaction_type")
    if interaction_type in {"choice", "confirmation"}:
        options = block.get("options")
        if not isinstance(options, list):
            return None
        enabled = [
            option
            for option in options
            if isinstance(option, dict) and option.get("disabled") is not True and option.get("value")
        ]
        if not enabled:
            return None
        if interaction_type == "confirmation":
            selected = next((item for item in enabled if item.get("value") == "confirm"), None)
            if selected is None:
                return None
        else:
            selected = enabled[0]
        return {"choice": str(selected["value"])}
    if interaction_type == "text_input":
        return {"text": fallback_confirmation}
    if interaction_type == "form":
        fields = block.get("fields")
        if not isinstance(fields, list):
            return None
        values: JSONDict = {}
        for field in fields:
            if not isinstance(field, dict):
                continue
            key = field.get("key")
            if not isinstance(key, str) or not key:
                continue
            if "default_value" in field and field["default_value"] is not None:
                values[key] = field["default_value"]
            elif field.get("required"):
                return None
        return values
    return None



def extract_final_answer(events: list[JSONDict]) -> str:
    for envelope in reversed(final_envelopes(events)):
        text_blocks = [
            str(block.get("text"))
            for block in envelope.get("blocks", [])
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ]
        if text_blocks:
            return "\n".join(text_blocks)
        metadata = envelope.get("metadata")
        if isinstance(metadata, dict) and metadata.get("accessibility_label"):
            return str(metadata["accessibility_label"])
    return ""


def short_name(name: str) -> str:
    return name.replace("有限公司", "").replace("股份有限公司", "").replace("有限责任公司", "")[:8]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_report(path: Path, *, snapshot: JSONDict, results: list[CaseResult], dry_run: bool) -> None:
    lines = [
        "# CRMWolf Agent Business Evaluation",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        f"- dry_run: {dry_run}",
        f"- team_id: `{snapshot.get('team_id', 'unknown')}`",
        f"- data_counts: `{json.dumps(snapshot['counts'], ensure_ascii=False)}`",
        "",
    ]
    if not results:
        lines.append("No cases were executed.")
    else:
        passed = sum(1 for item in results if item.passed)
        lines.extend(
            [
                f"- total: {len(results)}",
                f"- passed: {passed}",
                f"- failed: {len(results) - passed}",
                "",
                "## Failures",
                "",
            ]
        )
        failures = [item for item in results if not item.passed]
        if not failures:
            lines.append("No failures.")
        for item in failures:
            lines.extend(
                [
                    f"### {item.case_id}",
                    "",
                    f"- category: {item.category}",
                    f"- reasons: {'; '.join(item.reasons)}",
                    f"- routes: {', '.join(item.routes_seen) or '-'}",
                    f"- blocks: {', '.join(item.block_types_seen) or '-'}",
                    f"- action_statuses: {', '.join(item.action_statuses_seen) or '-'}",
                    f"- answer: {item.final_answer[:500].replace(chr(10), ' ')}",
                    "",
                ]
            )
        lines.extend(["## All Cases", ""])
        for item in results:
            status = "PASS" if item.passed else "FAIL"
            lines.append(f"- {status} `{item.case_id}` {item.category} ({item.elapsed_seconds}s)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

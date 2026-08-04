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
import time
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
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
from app.models.payment import PaymentPlan, PaymentRecord
from app.crud.customer_member import customer_member_crud


JSONDict = dict[str, Any]


@dataclass
class EvalCase:
    case_id: str
    category: str
    content: str
    expected_intent: str | None = None
    expected_customer_name: str | None = None
    expected_tools: list[str] = field(default_factory=list)
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
    intents_seen: list[str]
    tools_seen: list[str]
    successful_tools: list[str]
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

    snapshot = build_data_snapshot()
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
                    if expected_tool_succeeded(case, all_events):
                        break
                    resume_content = next_resume_content(all_events, fallback_confirmation=case.second_turn)
                    if not resume_content:
                        break
                    followup_events = call_agent(
                        client,
                        token=args.token,
                        content=resume_content,
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
                        "tools": result.tools_seen,
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


def build_data_snapshot() -> JSONDict:
    db = SessionLocal()
    try:
        counts = {
            "customers": db.query(Customer).count(),
            "contacts": db.query(Contact).count(),
            "activities": db.query(CustomerActivity).count(),
            "opportunities": db.query(Opportunity).count(),
            "contracts": db.query(Contract).count(),
            "payment_plans": db.query(PaymentPlan).count(),
            "payment_records": db.query(PaymentRecord).count(),
            "invoice_titles": db.query(InvoiceTitle).count(),
            "invoice_applications": db.query(InvoiceApplication).count(),
            "license_applications": db.query(LicenseApplication).count(),
            "deployment_infos": db.query(DeploymentInfo).count(),
            "vector_documents": db.query(CustomerVectorDocument).count(),
        }
        customers = [
            {
                "id": customer.id,
                "public_id": customer.public_id,
                "account_name": customer.account_name,
                "industry": customer.industry,
                "city": customer.city,
                "status": customer.status,
                "activity_count": db.query(CustomerActivity).filter(CustomerActivity.customer_id == customer.id).count(),
                "opportunity_count": db.query(Opportunity).filter(Opportunity.customer_id == customer.id).count(),
                "contract_count": db.query(Contract).filter(Contract.customer_id == customer.id).count(),
            }
            for customer in db.query(Customer)
            .filter(Customer.team_id == 1)
            .order_by(Customer.id.asc())
            .limit(30)
            .all()
        ]
        rich_customer_ids = [item["id"] for item in customers if item["activity_count"] or item["opportunity_count"] or item["contract_count"]]
        objects = {
            "contacts": rows_for_customer_objects(db, Contact, rich_customer_ids),
            "activities": rows_for_customer_objects(db, CustomerActivity, rich_customer_ids),
            "opportunities": rows_for_customer_objects(db, Opportunity, rich_customer_ids),
            "contracts": rows_for_customer_objects(db, Contract, rich_customer_ids),
            "payment_plans": rows_for_payment_plans(db, rich_customer_ids),
            "invoice_titles": rows_for_customer_objects(db, InvoiceTitle, rich_customer_ids),
            "deployments": rows_for_customer_objects(db, DeploymentInfo, rich_customer_ids),
            "licenses": rows_for_customer_objects(db, LicenseApplication, rich_customer_ids),
        }
        member_candidates_by_customer_id = {}
        for customer in customers:
            candidates = customer_member_crud.get_candidates(db, 1, customer["id"])
            available = [item for item in candidates if not item.get("already_member")]
            if available:
                member_candidates_by_customer_id[str(customer["id"])] = available[0]
        return {
            "counts": counts,
            "customers": customers,
            "objects": objects,
            "member_candidates_by_customer_id": member_candidates_by_customer_id,
        }
    finally:
        db.close()


def rows_for_customer_objects(db: Any, model: Any, customer_ids: list[int], limit: int = 12) -> list[JSONDict]:
    if not customer_ids:
        return []
    rows = db.query(model).filter(model.customer_id.in_(customer_ids)).order_by(model.id.asc()).limit(limit).all()
    return [{"id": row.id, "customer_id": row.customer_id, "label": object_label(row)} for row in rows]


def rows_for_payment_plans(db: Any, customer_ids: list[int], limit: int = 12) -> list[JSONDict]:
    if not customer_ids:
        return []
    rows = (
        db.query(PaymentPlan, Contract.customer_id)
        .join(Contract, Contract.id == PaymentPlan.contract_id)
        .filter(Contract.customer_id.in_(customer_ids))
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
                EvalCase(f"read_summary_{customer['id']}", "read_customer_summary", f"请总结一下{name}当前客户情况，包括业务背景、最近进展和下一步建议", "CUSTOMER_QUERY", name, required_terms=[short_name(name)]),
                EvalCase(f"read_contacts_{customer['id']}", "read_contacts", f"{name}现在有哪些联系人和关键决策人？", "CUSTOMER_QUERY", name, required_terms=[short_name(name), "联系人"]),
                EvalCase(f"read_followups_{customer['id']}", "read_followups", f"帮我看下{name}最近跟进记录和待办下一步", "CUSTOMER_QUERY", name, required_terms=[short_name(name)]),
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
            cases.append(EvalCase(f"read_{key}_{customer['id']}", f"read_{key}", template.format(name=name), "CUSTOMER_QUERY", name, required_terms=[term]))
            if len(seen) >= 3:
                break

    test_customer = tests[0]
    test_name = test_customer["account_name"]
    member_candidate = (snapshot.get("member_candidates_by_customer_id") or {}).get(str(test_customer["id"])) or {}
    member_name = str(member_candidate.get("name") or "Rayson").strip()
    write_templates = [
        ("write_activity", "create_customer_activity", f"给{test_name}记录一条跟进：本地 Agent 评测 {stamp}，今天电话沟通了试用反馈，客户关注权限体系和数据报表，下周三继续确认采购预算。"),
        ("write_contact", "create_contact", f"给{test_name}新增联系人：评测联系人{stamp}，手机号 139{stamp[-8:] if len(stamp) >= 8 else '00000000'}，职位信息化经理，男，是关键决策人。"),
        ("write_opportunity", "create_opportunity", f"给{test_name}创建一个商机：本地评测新购 50 用户，订阅 1 年，预计金额 50000 元，预计 9 月 30 日成交，采购方式用默认采购方式，2 个决策人。"),
        ("write_invoice_title", "create_invoice_title", f"给{test_name}新增单位发票抬头：{test_name}评测抬头{stamp}，税号 91310000{stamp[-8:] if len(stamp) >= 8 else '00000000'}，开户行 招商银行广州分行，账号 622588{stamp[-8:] if len(stamp) >= 8 else '00000000'}，设为默认。"),
        ("write_deployment", "create_deployment_info", f"给{test_name}新增部署信息：评测环境{stamp}，服务器地址 https://eval-{stamp}.crmwolf.local，设为默认部署。"),
        ("write_member", "create_customer_member", f"把 {member_name} 加到{test_name}客户团队，角色售前，可跟进，备注本地 Agent 评测 {stamp}。"),
    ]
    for category, expected_tool, content in write_templates:
        cases.append(
            EvalCase(
                f"{category}_{stamp}",
                category,
                content,
                expected_customer_name=test_name,
                expected_tools=[expected_tool],
                confirm=confirm_writes,
            )
        )

    cases.extend(
        [
            EvalCase("ambiguous_test_company", "ambiguous_resolution", "帮我看下测试公司现在的客户情况", "CUSTOMER_QUERY", None, required_terms=["测试公司"]),
            EvalCase("unknown_customer", "unknown_customer", f"帮我查一下不存在的本地评测客户{stamp}的合同和回款", "CUSTOMER_QUERY", None, forbidden_terms=["已成交", "合同金额"]),
            EvalCase("generic_customer_query", "clarification", "这个客户最近怎么样？", "CUSTOMER_QUERY", None),
        ]
    )
    return cases[:limit]


def call_agent(client: httpx.Client, *, token: str, content: str, session_id: int | None = None) -> list[JSONDict]:
    payload: JSONDict = {"content": content}
    if session_id:
        payload["session_id"] = session_id
    headers = {"Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}"}
    events: list[JSONDict] = []
    try:
        with client.stream("POST", "/v1/agent/chat/stream", headers=headers, json=payload) as response:
            if response.status_code >= 400:
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


def evaluate_case(case: EvalCase, first_events: list[JSONDict], second_events: list[JSONDict], elapsed: float) -> CaseResult:
    events = [*first_events, *second_events]
    names = [str(event.get("event")) for event in events if event.get("event")]
    intents = [str(event.get("intent")) for event in events if event.get("event") == "intent" and event.get("intent")]
    tool_events = [event for event in events if event.get("event") == "tool_result"]
    tools = [str(event.get("tool_name")) for event in tool_events if event.get("tool_name")]
    successful_tools = [str(event.get("tool_name")) for event in tool_events if event.get("tool_name") and event.get("success") is True]
    final_answer = extract_final_answer(events)
    reasons: list[str] = []

    if "http_error" in names:
        reasons.append("HTTP 请求失败")
    if "http_client_error" in names:
        reasons.append("HTTP 客户端异常")
    if "timeout" in names:
        reasons.append("Agent SSE 响应超时")
    if any(event.get("event") == "error" for event in events):
        reasons.append("Agent 返回 error 事件")
    if "done" not in names:
        reasons.append("未收到 done 事件")
    if case.expected_intent and case.expected_intent not in intents:
        reasons.append(f"未看到期望意图 {case.expected_intent}")
    for tool in case.expected_tools:
        if tool not in tools:
            reasons.append(f"未调用期望工具 {tool}")
        elif tool not in successful_tools:
            reasons.append(f"期望工具 {tool} 未成功执行")
    for term in case.required_terms:
        if term and term not in final_answer:
            reasons.append(f"回复缺少关键词：{term}")
    for term in case.forbidden_terms:
        if term and term in final_answer:
            reasons.append(f"回复出现禁用词：{term}")
    if case.expected_customer_name and "没能确定" in final_answer:
        reasons.append("已知客户未能解析")
    if re.search(r"\b(crm_|tool_|Qdrant|LangGraph|evidence_id)\b", final_answer, flags=re.I):
        reasons.append("回复暴露内部实现词")
    if case.confirm and second_events and not successful_tools:
        reasons.append("确认后没有成功 tool 写入")

    return CaseResult(
        case_id=case.case_id,
        category=case.category,
        content=case.content,
        passed=not reasons,
        reasons=reasons,
        session_id=extract_session_id(events),
        events_seen=names,
        intents_seen=intents,
        tools_seen=tools,
        successful_tools=successful_tools,
        final_answer=final_answer[:2000],
        first_turn_event_count=len(first_events),
        second_turn_event_count=len(second_events),
        elapsed_seconds=round(elapsed, 2),
    )


def extract_session_id(events: list[JSONDict]) -> int | None:
    for event in events:
        value = event.get("session_id")
        if isinstance(value, int):
            return value
    return None


def has_confirmation_required(events: list[JSONDict]) -> bool:
    return any(event.get("event") == "confirmation_required" for event in events)


def expected_tool_succeeded(case: EvalCase, events: list[JSONDict]) -> bool:
    if not case.expected_tools:
        return False
    successful_tools = {
        str(event.get("tool_name"))
        for event in events
        if event.get("event") == "tool_result" and event.get("success") is True and event.get("tool_name")
    }
    return any(tool in successful_tools for tool in case.expected_tools)


def next_resume_content(events: list[JSONDict], *, fallback_confirmation: str) -> str | None:
    for event in reversed(events):
        if event.get("event") == "confirmation_required":
            return fallback_confirmation
        if str(event.get("event") or "").endswith("_fields_required"):
            selected = default_field_selection(event)
            if selected:
                return selected
    return None


def default_field_selection(event: JSONDict) -> str | None:
    fields = event.get("fields")
    if not isinstance(fields, list):
        return None
    values: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        default_value = field.get("default_value")
        options = field.get("options")
        if default_value is not None and isinstance(options, list):
            for option in options:
                if isinstance(option, dict) and str(option.get("value")) == str(default_value):
                    label = option.get("label")
                    if label:
                        values.append(str(label))
                        break
        elif default_value is not None:
            values.append(str(default_value))
    if not values:
        return None
    return "，".join(values)


def extract_final_answer(events: list[JSONDict]) -> str:
    for event in reversed(events):
        if event.get("event") == "message" and event.get("role") == "ASSISTANT":
            return str(event.get("content") or "")
        if event.get("event") == "final":
            return str(event.get("content") or "")
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
                    f"- intents: {', '.join(item.intents_seen) or '-'}",
                    f"- tools: {', '.join(item.tools_seen) or '-'}",
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

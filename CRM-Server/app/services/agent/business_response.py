"""Business intent response/action construction for the CRM agent."""
from __future__ import annotations

from typing import Any, Dict, List

from app.services.agent import business_rules
from app.services.customer_activity_kinds import infer_activity_kind


class BusinessResponseBuilder:
    def __init__(self, rules: Any = business_rules) -> None:
        self.rules = rules

    def build(
        self,
        intent: str,
        parsed: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        business_context: Dict[str, Any],
    ):
        customer_name = parsed.get("customer_name")
        if intent == "CUSTOMER_ACTIVITY":
            return self._customer_activity(parsed, candidates, customer_name)
        if intent == "CREATE_LEAD":
            return self._create_lead(parsed)
        if intent == "CREATE_CUSTOMER":
            return self._create_customer(parsed)
        if intent == "PAYMENT_RECORD":
            return self._payment_record(parsed, candidates, business_context, customer_name)
        if intent == "CREATE_OPPORTUNITY":
            return self._create_opportunity(parsed, candidates, customer_name)
        if intent == "CREATE_CONTACT":
            return self._create_contact(parsed, candidates, customer_name)
        if intent == "CREATE_INVOICE_TITLE":
            return self._create_invoice_title(parsed, candidates, customer_name)
        if intent == "CREATE_DEPLOYMENT_INFO":
            return self._create_deployment_info(parsed, candidates, customer_name)
        if intent == "CREATE_CUSTOMER_MEMBER":
            return self._create_customer_member(parsed, candidates, business_context, customer_name)
        if intent == "CUSTOMER_QUERY":
            return "我识别到这是查询请求。下一步会接入客户上下文查询和汇总能力。", None
        return "我还不能可靠理解这条消息，请补充客户名称、业务内容或你希望我执行的动作。", None

    def _customer_activity(self, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], customer_name: Any):
        if not customer_name:
            return "我识别到这是客户活动，但还缺少明确客户名称。请补充客户名称。", None
        activity_payload = self._customer_activity_payload(parsed)
        if len(candidates) == 1:
            customer = candidates[0]
            return (
                f"我识别到客户「{customer.get('account_name')}」的客户活动。"
                "请确认是否创建这条客户活动？"
            ), {
                "action": "create_customer_activity",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    **activity_payload,
                },
            }
        if len(candidates) > 1:
            candidate_lines = [
                f"{index}. {customer.get('account_name')}"
                for index, customer in enumerate(candidates, start=1)
            ]
            return (
                "我找到了多个可能的客户，请回复序号或客户名称确认要记录到哪一个客户："
                + "；".join(candidate_lines)
            ), {
                "action": "select_customer_for_activity",
                "customers": candidates,
                "payload": activity_payload,
            }
        return self.rules.customer_not_found_response(customer_name), None

    @staticmethod
    def _customer_activity_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
        content = parsed.get("follow_up_content") or ""
        method = parsed.get("method") or "AI录入"
        original_content = parsed.get("original_content") or content
        activity_kind = infer_activity_kind(method, original_content or content)
        return {
            "activity_kind": activity_kind,
            "source_content": original_content,
            # Compatibility for field-supplement flows and existing UI trace payloads.
            "content": content,
            "method": method,
            "next_action": parsed.get("next_action"),
            "next_follow_time_text": parsed.get("next_follow_time_text"),
            "next_follow_time_iso": parsed.get("next_follow_time_iso"),
        }

    def _create_lead(self, parsed: Dict[str, Any]):
        lead = parsed.get("lead") or {}
        missing_fields = self.rules.missing_lead_fields(lead)
        if missing_fields:
            return (
                "我识别到要创建线索，"
                f"还需要补充：{self.rules.format_lead_missing_fields(missing_fields)}。"
            ), {
                "action": "collect_lead_fields",
                "payload": {
                    "lead": lead,
                    "lead_follow_up": parsed.get("lead_follow_up") or {},
                    "missing_fields": missing_fields,
                },
            }
        return (
            "我识别到要创建线索"
            f"「{lead.get('lead_name')}」，联系人「{lead.get('contact_name')}」，电话「{lead.get('contact_phone')}」。"
            "请确认是否创建？"
        ), {
            "action": "create_lead",
            "payload": {
                "lead": lead,
                "lead_follow_up": parsed.get("lead_follow_up") or {},
            },
        }

    def _create_customer(self, parsed: Dict[str, Any]):
        customer_create = parsed.get("customer_create") or {}
        missing_fields = self.rules.missing_customer_fields(customer_create)
        if missing_fields:
            return (
                "我识别到要创建客户，"
                f"还需要补充：{self.rules.format_customer_missing_fields(missing_fields)}。"
            ), {
                "action": "collect_customer_fields",
                "payload": {
                    "customer": customer_create,
                    "customer_activity": parsed.get("customer_activity") or parsed.get("customer_follow_up") or {},
                    "missing_fields": missing_fields,
                },
            }
        contact_name = customer_create.get("contact_name")
        contact_text = f"，主联系人「{contact_name}」" if contact_name else ""
        return (
            "我识别到要创建客户"
            f"「{customer_create.get('account_name')}」{contact_text}。"
            "请确认是否创建？"
        ), {
            "action": "create_customer",
            "payload": {
                "customer": customer_create,
                "customer_activity": parsed.get("customer_activity") or parsed.get("customer_follow_up") or {},
            },
        }

    def _payment_record(
        self,
        parsed: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        business_context: Dict[str, Any],
        customer_name: Any,
    ):
        if not customer_name:
            return "我识别到这是回款场景，但还缺少明确客户名称。请补充客户名称。", None
        if len(candidates) == 1:
            return self.build_payment_record_response(candidates[0], parsed, business_context)
        if len(candidates) > 1:
            candidate_lines = [
                f"{index}. {customer.get('account_name')}"
                for index, customer in enumerate(candidates, start=1)
            ]
            return (
                "我找到了多个可能的客户，请回复序号或客户名称确认要为哪一个客户处理回款："
                + "；".join(candidate_lines)
            ), {
                "action": "select_customer_for_payment_record",
                "customers": candidates,
                "payload": {
                    "payment": parsed.get("payment") or {},
                    "missing_fields": parsed.get("missing_payment_fields") or [],
                },
            }
        return self.rules.customer_not_found_response(customer_name), None

    def build_payment_record_response(
        self,
        customer: Dict[str, Any],
        parsed: Dict[str, Any],
        business_context: Dict[str, Any],
    ):
        payment = parsed.get("payment") or {}
        missing_fields = self.rules.missing_payment_fields(
            payment.get("actual_amount"),
            payment.get("payment_date_iso"),
        )
        contracts = self.rules.context_items(business_context.get("contracts"))
        opportunities = self.rules.context_items(business_context.get("opportunities"))
        payment_plans = [
            plan
            for plan in self.rules.context_items(business_context.get("payment_plans"))
            if self.rules.is_open_payment_plan(plan)
        ]
        commission_member_id = self.rules.resolve_commission_member_id(customer)

        if not contracts:
            if not opportunities:
                return (
                    f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到商机和可用于登记回款的合同。"
                    "按 CRM 业务链路，需要先补齐商机，再处理合同、回款计划和回款登记。"
                    "创建合同暂未接入 Agent，因为当前创建合同需要上传合同附件。"
                ), None
            return (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到可用于登记回款的合同。"
                "该客户已有商机，但合同环节还未补齐；创建合同暂未接入 Agent，因为当前创建合同需要上传合同附件。"
            ), None

        if missing_fields:
            return (
                f"我识别到「{customer.get('account_name')}」的回款信息，"
                f"还需要补充：{self.rules.format_payment_missing_fields(missing_fields)}。"
            ), {
                "action": "collect_payment_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": payment,
                    "contracts": contracts,
                    "payment_plans": payment_plans,
                    "missing_fields": missing_fields,
                    "commission_member_id": commission_member_id,
                },
            }

        if not commission_member_id:
            return (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到可用于登记的提成协作成员或负责人。"
                "请先在客户中配置协作成员或负责人后再登记。"
            ), None

        if len(payment_plans) == 1:
            plan = payment_plans[0]
            return (
                f"我识别到「{customer.get('account_name')}」已回款，匹配到回款计划「{plan.get('stage_name')}」。"
                "请确认是否登记这笔回款？"
            ), {
                "action": "create_payment_record",
                "customer": customer,
                "payload": self.rules.payment_record_payload(plan, payment, commission_member_id),
            }

        if len(payment_plans) > 1:
            plan_lines = [
                f"{index}. {plan.get('contract_name') or '未命名合同'} / {plan.get('stage_name')} / 待回款 {plan.get('remaining_amount')}"
                for index, plan in enumerate(payment_plans, start=1)
            ]
            return (
                "我找到了多个未完成回款计划，请回复序号确认登记到哪一个计划："
                + "；".join(plan_lines)
            ), {
                "action": "select_payment_plan_for_record",
                "customer": customer,
                "payment_plans": payment_plans,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": payment,
                    "commission_member_id": commission_member_id,
                },
            }

        if len(contracts) == 1:
            contract = contracts[0]
            return (
                f"我识别到「{customer.get('account_name')}」已回款，找到了合同「{contract.get('contract_name')}」，但没有找到回款计划。"
                "请确认是否先按本次回款金额创建一条回款计划？"
            ), {
                "action": "create_payment_plan",
                "customer": customer,
                "payload": self.rules.payment_plan_payload(contract, payment, commission_member_id),
            }

        contract_lines = [
            f"{index}. {contract.get('contract_name')} / 金额 {contract.get('total_amount')} / 状态 {contract.get('status')}"
            for index, contract in enumerate(contracts, start=1)
        ]
        return (
            "我找到了多个合同，但没有可直接登记的回款计划。请回复序号确认要基于哪一个合同创建回款计划："
            + "；".join(contract_lines)
        ), {
            "action": "select_contract_for_payment_plan",
            "customer": customer,
            "contracts": contracts,
            "payload": {
                "customer_id": customer.get("id"),
                "payment": payment,
                "commission_member_id": commission_member_id,
            },
        }

    def _create_opportunity(self, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], customer_name: Any):
        if not customer_name:
            return "我识别到这是创建商机，但还缺少明确客户名称。请补充客户名称。", None
        opportunity = parsed.get("opportunity") or {}
        opportunity.pop("opportunity_name", None)
        missing_fields = parsed.get("missing_opportunity_fields") or []
        if len(candidates) == 1:
            customer = candidates[0]
            opportunity["customer_id"] = customer.get("id")
            missing_fields = self.rules.missing_opportunity_fields(
                opportunity,
                require_procurement_method=self.rules.customer_requires_procurement_method(customer),
            )
            needs_procurement_review = not opportunity.get("procurement_method_id")
            if missing_fields or needs_procurement_review:
                content = (
                    f"我识别到要为「{customer.get('account_name')}」创建商机，"
                    f"还需要补充：{self.rules.format_opportunity_missing_fields(self.rules.opportunity_missing_display_fields(missing_fields))}。"
                    if missing_fields
                    else f"我识别到要为「{customer.get('account_name')}」创建商机，请确认采购方式。"
                )
                return content, {
                    "action": "collect_opportunity_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "opportunity": opportunity,
                        "missing_fields": missing_fields,
                        "interaction_fields": self.rules.opportunity_interaction_fields(missing_fields),
                        "field_defaults": self.rules.opportunity_field_defaults(customer),
                    },
                }
            return (
                f"我识别到要为「{customer.get('account_name')}」创建商机，"
                f"{self.rules.format_opportunity_summary(opportunity)}。请确认是否创建？"
            ), {
                "action": "create_opportunity",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "opportunity": opportunity,
                },
            }
        if len(candidates) > 1:
            candidate_lines = [
                f"{index}. {customer.get('account_name')}"
                for index, customer in enumerate(candidates, start=1)
            ]
            return (
                "我找到了多个可能的客户，请回复序号或客户名称确认要把商机创建到哪一个客户："
                + "；".join(candidate_lines)
            ), {
                "action": "select_customer_for_opportunity",
                "customers": candidates,
                "payload": {
                    "opportunity": opportunity,
                    "missing_fields": missing_fields,
                    "interaction_fields": self.rules.opportunity_interaction_fields(missing_fields),
                },
            }
        return self.rules.customer_not_found_response(customer_name), None

    def _create_contact(self, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], customer_name: Any):
        if not customer_name:
            return "我识别到这是创建联系人，但还缺少明确客户名称。请补充客户名称。", None
        contact = parsed.get("contact") or {}
        missing_fields = self.rules.missing_contact_fields(contact)
        if len(candidates) == 1:
            customer = candidates[0]
            if missing_fields:
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建联系人，"
                    f"还需要补充：{self.rules.format_contact_missing_fields(missing_fields)}。"
                ), {
                    "action": "collect_contact_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "contact": contact,
                        "missing_fields": missing_fields,
                    },
                }
            return (
                f"我识别到要为「{customer.get('account_name')}」创建联系人「{contact.get('name')}」。"
                "请确认是否创建？"
            ), {
                "action": "create_contact",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "contact": contact,
                },
            }
        if len(candidates) > 1:
            return self._customer_selection(
                "我找到了多个可能的客户，请回复序号或客户名称确认要把联系人创建到哪一个客户：",
                "select_customer_for_contact",
                candidates,
                {"contact": contact, "missing_fields": missing_fields},
            )
        return self.rules.customer_not_found_response(customer_name), None

    def _create_invoice_title(self, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], customer_name: Any):
        if not customer_name:
            return "我识别到这是创建发票抬头，但还缺少明确客户名称。请补充客户名称。", None
        invoice_title = parsed.get("invoice_title") or {}
        missing_fields = self.rules.missing_invoice_title_fields(invoice_title)
        set_default = bool(invoice_title.pop("set_default", False))
        if len(candidates) == 1:
            customer = candidates[0]
            if missing_fields:
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建发票抬头，"
                    f"还需要补充：{self.rules.format_invoice_title_missing_fields(missing_fields)}。"
                ), {
                    "action": "collect_invoice_title_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "invoice_title": invoice_title,
                        "missing_fields": missing_fields,
                        "set_default": set_default,
                    },
                }
            return (
                f"我识别到要为「{customer.get('account_name')}」创建发票抬头「{invoice_title.get('title')}」。"
                "请确认是否创建？"
            ), {
                "action": "create_invoice_title",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "invoice_title": invoice_title,
                    "set_default": set_default,
                },
            }
        if len(candidates) > 1:
            return self._customer_selection(
                "我找到了多个可能的客户，请回复序号或客户名称确认要把发票抬头创建到哪一个客户：",
                "select_customer_for_invoice_title",
                candidates,
                {"invoice_title": invoice_title, "missing_fields": missing_fields, "set_default": set_default},
            )
        return self.rules.customer_not_found_response(customer_name), None

    def _create_deployment_info(self, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], customer_name: Any):
        if not customer_name:
            return "我识别到这是创建部署信息，但还缺少明确客户名称。请补充客户名称。", None
        deployment_info = parsed.get("deployment_info") or {}
        missing_fields = self.rules.missing_deployment_info_fields(deployment_info)
        if len(candidates) == 1:
            customer = candidates[0]
            deployment_info["customer_id"] = customer.get("id")
            if missing_fields:
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建部署信息，"
                    f"还需要补充：{self.rules.format_deployment_info_missing_fields(missing_fields)}。"
                ), {
                    "action": "collect_deployment_info_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "deployment_info": deployment_info,
                        "missing_fields": missing_fields,
                    },
                }
            return (
                f"我识别到要为「{customer.get('account_name')}」创建部署信息「{deployment_info.get('deployment_name')}」。"
                "请确认是否创建？"
            ), {
                "action": "create_deployment_info",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "deployment_info": deployment_info,
                },
            }
        if len(candidates) > 1:
            return self._customer_selection(
                "我找到了多个可能的客户，请回复序号或客户名称确认要把部署信息创建到哪一个客户：",
                "select_customer_for_deployment_info",
                candidates,
                {"deployment_info": deployment_info, "missing_fields": missing_fields},
            )
        return self.rules.customer_not_found_response(customer_name), None

    def _create_customer_member(
        self,
        parsed: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        business_context: Dict[str, Any],
        customer_name: Any,
    ):
        if not customer_name:
            return "我识别到这是设置客户成员，但还缺少明确客户名称。请补充客户名称。", None
        member = parsed.get("customer_member") or {}
        missing_fields = self.rules.missing_customer_member_fields(member)
        if len(candidates) == 1:
            customer = candidates[0]
            if missing_fields:
                return (
                    f"我识别到要为「{customer.get('account_name')}」设置客户成员，"
                    f"还需要补充：{self.rules.format_customer_member_missing_fields(missing_fields)}。"
                ), {
                    "action": "collect_customer_member_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "customer_member": member,
                        "missing_fields": missing_fields,
                        "member_candidates": business_context.get("member_candidates"),
                    },
                }
            resolved_member, member_error = self.rules.resolve_customer_member(member, business_context)
            if member_error:
                return member_error, {
                    "action": "collect_customer_member_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "customer_member": member,
                        "missing_fields": ["user_name"],
                        "member_candidates": business_context.get("member_candidates"),
                    },
                }
            return (
                f"我识别到要为「{customer.get('account_name')}」添加客户成员「{resolved_member.get('user_name') or resolved_member.get('user_id')}」。"
                "请确认是否添加？"
            ), {
                "action": "create_customer_member",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "member": resolved_member,
                },
            }
        if len(candidates) > 1:
            return self._customer_selection(
                "我找到了多个可能的客户，请回复序号或客户名称确认要给哪一个客户设置成员：",
                "select_customer_for_customer_member",
                candidates,
                {"customer_member": member, "missing_fields": missing_fields},
            )
        return self.rules.customer_not_found_response(customer_name), None

    @staticmethod
    def _customer_selection(
        prefix: str,
        action: str,
        candidates: List[Dict[str, Any]],
        payload: Dict[str, Any],
    ):
        candidate_lines = [
            f"{index}. {customer.get('account_name')}"
            for index, customer in enumerate(candidates, start=1)
        ]
        return prefix + "；".join(candidate_lines), {
            "action": action,
            "customers": candidates,
            "payload": payload,
        }

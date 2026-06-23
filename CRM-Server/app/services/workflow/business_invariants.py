"""
业务不变式定义

硬编码的业务规则校验，确保数据一致性。
"""
from typing import Dict, Any, Tuple, Callable, List


class BusinessInvariants:
    """业务不变式定义"""

    # 不变式注册表
    INVARIANTS: Dict[str, Dict[str, Any]] = {

        # ==================== 金额约束 ====================
        "contract_amount_le_opportunity_amount": {
            "description": "合同金额不能超过商机金额",
            "validate": lambda contract, opportunity: (
                float(contract.get("amount", 0)) <= float(opportunity.get("amount", 0))
            ),
            "error_message": "合同金额 {contract_amount} 超过商机金额 {opp_amount}，是否确认？",
            "severity": "warning",  # warning = 可询问用户确认，error = 强制拦截
            "on_violation": "ask_user_confirm"
        },

        "payment_amount_le_contract_amount": {
            "description": "回款金额不能超过合同金额",
            "validate": lambda payment, contract: (
                float(payment.get("amount", 0)) <= float(contract.get("amount", 0))
            ),
            "error_message": "回款金额超过合同金额，是否确认？",
            "severity": "warning",
            "on_violation": "ask_user_confirm"
        },

        "invoice_amount_le_contract_amount": {
            "description": "发票金额不能超过合同金额",
            "validate": lambda invoice, contract: (
                float(invoice.get("amount", 0)) <= float(contract.get("amount", 0))
            ),
            "error_message": "发票金额超过合同金额，是否确认？",
            "severity": "warning",
            "on_violation": "ask_user_confirm"
        },

        # ==================== 关联约束 ====================
        "win_requires_opportunity": {
            "description": "赢单必须关联商机",
            "validate": lambda session: len(session.get("entity_context", {}).get("opportunities", [])) > 0,
            "error_message": "客户无商机记录，无法标记赢单",
            "severity": "error",
            "on_violation": "ask_create_opportunity"
        },

        "contract_requires_won_opportunity": {
            "description": "合同必须关联已赢单商机",
            "validate": lambda session: any(
                opp.get("status") == 1  # 1 = WON
                for opp in session.get("entity_context", {}).get("opportunities", [])
            ),
            "error_message": "客户无已赢单商机，无法创建合同",
            "severity": "error",
            "on_violation": "ask_win_opportunity_first"
        },

        "payment_requires_contract": {
            "description": "回款必须关联合同",
            "validate": lambda session: len(session.get("entity_context", {}).get("contracts", [])) > 0,
            "error_message": "客户无合同记录，无法登记回款",
            "severity": "error",
            "on_violation": "ask_create_contract_first"
        },

        # ==================== 必填字段约束 ====================
        "opportunity_create_requires_amount": {
            "description": "创建商机必须有金额",
            "validate": lambda params: params.get("total_amount") is not None and float(params.get("total_amount", 0)) > 0,
            "error_message": "创建商机需要填写预计金额",
            "severity": "error",
            "on_violation": "ask_missing_field"
        },

        "contract_create_requires_opportunity_id": {
            "description": "创建合同必须关联商机",
            "validate": lambda params: params.get("opportunity_id") is not None,
            "error_message": "创建合同需要关联已赢单商机",
            "severity": "error",
            "on_violation": "ask_select_opportunity"
        },

        # ==================== 业务流程约束 ====================
        "lead_convert_requires_not_converted": {
            "description": "线索转化前状态不能是已转化",
            "validate": lambda session: session.get("entity_context", {}).get("status") != "CONVERTED",
            "error_message": "线索已转化，无法再次转化",
            "severity": "error",
            "on_violation": "workflow_complete_with_message"
        },

        "opportunity_win_requires_following_status": {
            "description": "商机赢单前状态必须是跟进中",
            "validate": lambda session: session.get("entity_context", {}).get("status") == "FOLLOWING",
            "error_message": "商机状态不是跟进中，无法标记赢单",
            "severity": "error",
            "on_violation": "workflow_complete_with_error"
        }
    }

    def validate(
        self,
        invariant_name: str,
        *args
    ) -> Tuple[bool, str, str]:
        """校验业务不变式

        Args:
            invariant_name: 不变式名称
            *args: 校验参数（根据不变式定义）

        Returns:
            (是否通过, 错误消息, 处理方式)
        """
        invariant = self.INVARIANTS.get(invariant_name)
        if not invariant:
            return True, "", ""

        try:
            result = invariant["validate"](*args)
            if result:
                return True, "", ""

            error_msg = invariant.get("error_message", "业务规则校验失败")
            severity = invariant.get("severity", "error")
            on_violation = invariant.get("on_violation", "block")

            return False, error_msg, on_violation

        except Exception as e:
            return False, f"不变式校验异常: {str(e)}", "block"

    def validate_all_for_action(
        self,
        action_type: str,
        session: Dict[str, Any],
        params: Dict[str, Any]
    ) -> List[Tuple[str, bool, str, str]]:
        """校验某个操作的所有相关不变式

        Args:
            action_type: 操作类型（如 "win_opportunity", "create_contract"）
            session: Session 状态
            params: 操作参数

        Returns:
            校验结果列表：[(不变式名称, 是否通过, 错误消息, 处理方式)]
        """
        # 根据操作类型确定需要校验的不变式
        action_invariants: Dict[str, List[str]] = {
            "win_opportunity": ["win_requires_opportunity"],
            "create_contract": ["contract_requires_won_opportunity", "contract_create_requires_opportunity_id"],
            "create_payment": ["payment_requires_contract"],
            "create_invoice": ["invoice_amount_le_contract_amount"],
            "create_opportunity": ["opportunity_create_requires_amount"]
        }

        invariants_to_check = action_invariants.get(action_type, [])
        results = []

        for invariant_name in invariants_to_check:
            invariant = self.INVARIANTS.get(invariant_name)
            if not invariant:
                continue

            # 根据不变式定义确定参数
            if "win_requires" in invariant_name:
                is_valid, error_msg, on_violation = self.validate(invariant_name, session)
            elif "contract_requires" in invariant_name:
                is_valid, error_msg, on_violation = self.validate(invariant_name, session)
            elif "payment_requires" in invariant_name:
                is_valid, error_msg, on_violation = self.validate(invariant_name, session)
            elif "requires_amount" in invariant_name or "requires_opportunity_id" in invariant_name:
                is_valid, error_msg, on_violation = self.validate(invariant_name, params)
            else:
                is_valid, error_msg, on_violation = True, "", ""

            results.append((invariant_name, is_valid, error_msg, on_violation))

        return results

    def get_severity(self, invariant_name: str) -> str:
        """获取不变式的严重程度

        Args:
            invariant_name: 不变式名称

        Returns:
            严重程度（"error" 或 "warning"）
        """
        invariant = self.INVARIANTS.get(invariant_name)
        return invariant.get("severity", "error") if invariant else "error"

    def should_ask_user(self, invariant_name: str) -> bool:
        """判断是否需要询问用户

        Args:
            invariant_name: 不变式名称

        Returns:
            是否需要询问用户
        """
        invariant = self.INVARIANTS.get(invariant_name)
        if not invariant:
            return False

        severity = invariant.get("severity", "error")
        on_violation = invariant.get("on_violation", "block")

        return severity == "warning" and on_violation == "ask_user_confirm"
"""SafetyGateway

读取风险分级，判断是否需人工确认。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.4
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 3.3
"""

from typing import Dict, Any, Optional  # B4: 加 Optional
from dataclasses import dataclass
import httpx


@dataclass
class SafetyResult:
    """安全检查结果"""

    requires_confirmation: bool  # 是否需人工确认
    reason: str  # 原因说明
    allowed: bool  # 是否允许执行
    risk_level: Optional[str] = None  # 风险等级


class SafetyGateway:
    """安全网关

    根据 /ai/metadata/rules 判断操作是否安全。
    """

    # TODO: 从配置获取 base_url
    AI_BASE_URL = "http://localhost:8000/ai"

    # 风险分级配置
    RISK_CONFIG = {
        "LOW": {
            "auto_threshold": 0.85,
            "force_confirm": False,
            "dry_run_only": False,
        },
        "MEDIUM": {
            "auto_threshold": 0.90,
            "force_confirm": False,
            "dry_run_only": False,
        },
        "HIGH": {
            "auto_threshold": 1.0,
            "force_confirm": True,
            "dry_run_only": False,
        },
        "CRITICAL": {
            "auto_threshold": 1.0,
            "force_confirm": True,
            "dry_run_only": True,  # 禁止执行
        },
    }

    # Intent 风险等级映射
    INTENT_RISK_MAP = {
        "create_follow_up": "LOW",
        "set_reminder": "LOW",
        "init_opportunity": "MEDIUM",
        "update_amount": "MEDIUM",
        "update_stage": "MEDIUM",
        "win_opportunity": "HIGH",
        "lose_opportunity": "HIGH",
    }

    async def check(self, intent: str, plan: Dict[str, Any], confidence: float = 0.9) -> SafetyResult:
        """安全检查

        Args:
            intent: 意图类型
            plan: ActionPlan 数据
            confidence: 置信度

        Returns:
            SafetyResult: 检查结果
        """
        # 1. 获取风险等级
        risk_level = self.INTENT_RISK_MAP.get(intent, "MEDIUM")
        config = self.RISK_CONFIG.get(risk_level, self.RISK_CONFIG["MEDIUM"])

        # 2. 检查是否禁止执行（CRITICAL）
        if config.get("dry_run_only"):
            return SafetyResult(
                requires_confirmation=True,
                reason="该操作风险过高，禁止通过 AI 执行。",
                allowed=False,
                risk_level=risk_level,
            )

        # 3. 检查是否强制确认（HIGH）
        if config.get("force_confirm"):
            return SafetyResult(
                requires_confirmation=True,
                reason=f"该操作风险等级为 {risk_level}，需人工确认。",
                allowed=True,
                risk_level=risk_level,
            )

        # 4. 检查置信度是否足够
        if confidence < config.get("auto_threshold", 0.9):
            return SafetyResult(
                requires_confirmation=True,
                reason="置信度不足，需人工确认。",
                allowed=True,
                risk_level=risk_level,
            )

        # 5. 允许执行
        return SafetyResult(
            requires_confirmation=False,
            reason="置信度足够，可自动执行。",
            allowed=True,
            risk_level=risk_level,
        )

    async def fetch_rules(self) -> Dict[str, Any]:
        """获取业务规则"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.AI_BASE_URL}/metadata/rules")
                response.raise_for_status()
                return response.json()
        except Exception:
            return {}


__all__ = [
    "SafetyResult",
    "SafetyGateway",
]
"""AI OpenAPI 动作层路由

职责：纯 HTTP 适配层（R-B 合规）
- 仅负责 HTTP 请求解析 → ActionEntry 入口函数调用 → HTTP 响应转换
- 不写业务校验、权限判断、数据变换逻辑

GUARDRAIL（红线约束）：
- 本文件为纯 HTTP 适配层，禁止写业务校验/权限/数据变换
- 所有裁决逻辑 → ActionEntry 入口函数
- 所有审计日志 → Entry 内部/下游

整改要点（R-1~R-5 合规）：
- R-1: 端点调用入口函数，末级是 action_entry → CRUD
- R-2: Preview 逻辑统一在入口函数，端点不自建
- R-3: 使用入口函数签名 (preview: bool) → ActionEntryResult
- R-4: action_id 从入口函数获取（统一归因）
- R-D: 使用 UserExecCtx 替代裸 User 参数

参见: CRM-Docs/plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md Phase 3
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 17.3 R-B, R-D
"""

from typing import Dict, Any, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.ai.deps import get_ai_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai.common import AIRequestBase, AIResponseBase, ActionPlan, FieldChange, generate_action_id
from app.constants.ai_rules import RiskLevel, requires_confirmation, get_action_risk
from app.services.ai.action_entry import ActionEntry, ActionEntryResult, UserExecCtx


router = APIRouter()


# ==================== 创建跟进 ====================

class CreateFollowUpRequest(AIRequestBase):
    """创建跟进请求"""

    customer_id: int
    content: str
    follow_up_time: Optional[str] = None  # ISO datetime string
    method: Optional[str] = "电话"
    next_action: Optional[str] = None
    opportunity_id: Optional[int] = None


@router.post("/create-follow-up", summary="创建跟进记录")
async def create_follow_up(
    request: CreateFollowUpRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """创建跟进记录

    风险等级: LOW (置信度 ≥ 0.85 自动执行)
    """
    # R-D: 创建 UserExecCtx（干净的参数接口）
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")

    # 创建入口函数实例
    entry = ActionEntry(db, user_ctx)

    # 解析跟进时间
    follow_up_time = None
    if request.follow_up_time:
        try:
            follow_up_time = datetime.fromisoformat(request.follow_up_time.replace("Z", "+00:00"))
        except ValueError:
            follow_up_time = None

    # 调用入口函数
    result = entry.create_follow_up(
        customer_id=request.customer_id,
        content=request.content,
        follow_up_time=follow_up_time,
        method=request.method,
        next_action=request.next_action,
        opportunity_id=request.opportunity_id,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 设置提醒 ====================

class SetReminderRequest(AIRequestBase):
    """设置提醒请求"""

    customer_id: int
    reminder_time: str  # ISO datetime string
    content: str
    opportunity_id: Optional[int] = None


@router.post("/set-reminder", summary="设置跟进提醒")
async def set_reminder(
    request: SetReminderRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """设置跟进提醒

    风险等级: LOW (置信度 ≥ 0.85 自动执行)
    """
    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # 解析提醒时间
    try:
        reminder_time = datetime.fromisoformat(request.reminder_time.replace("Z", "+00:00"))
    except ValueError:
        return AIResponseBase(
            action_id=request.action_id or generate_action_id(),
            status="failed",
            confidence=0.9,
            requires_confirmation=False,
            message="提醒时间格式无效",
            error="reminder_time must be ISO datetime format",
        )

    # 调用入口函数
    result = entry.set_reminder(
        customer_id=request.customer_id,
        reminder_time=reminder_time,
        content=request.content,
        opportunity_id=request.opportunity_id,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 初始化商机 ====================

class InitOpportunityRequest(AIRequestBase):
    """初始化商机请求（最小字段集）"""

    customer_id: int
    opportunity_name: str
    procurement_method_id: Optional[int] = None


@router.post("/init-opportunity", summary="初始化商机")
async def init_opportunity(
    request: InitOpportunityRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """初始化商机（最小字段集）

    风险等级: MEDIUM (置信度 ≥ 0.90 自动执行)
    """
    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # 调用入口函数
    result = entry.init_opportunity(
        customer_id=request.customer_id,
        opportunity_name=request.opportunity_name,
        procurement_method_id=request.procurement_method_id,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 更新金额 ====================

class UpdateAmountRequest(AIRequestBase):
    """更新商机金额请求"""

    opportunity_id: int
    amount: float
    user_count: Optional[int] = None


@router.post("/update-amount", summary="更新商机金额")
async def update_amount(
    request: UpdateAmountRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """更新商机金额

    风险等级: MEDIUM (置信度 ≥ 0.90 自动执行)
    """
    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # 调用入口函数
    result = entry.update_amount(
        opportunity_id=request.opportunity_id,
        amount=request.amount,
        user_count=request.user_count,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 更新阶段 ====================

class UpdateStageRequest(AIRequestBase):
    """更新商机阶段请求"""

    opportunity_id: int
    target_stage_template_id: int


@router.post("/update-stage", summary="更新商机阶段")
async def update_stage(
    request: UpdateStageRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """更新商机阶段（自动带赢率）

    风险等级: MEDIUM (置信度 ≥ 0.90 自动执行)
    """
    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # 调用入口函数
    result = entry.update_stage(
        opportunity_id=request.opportunity_id,
        target_stage_template_id=request.target_stage_template_id,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 赢单（高风险） ====================

class WinOpportunityRequest(AIRequestBase):
    """赢单请求"""

    opportunity_id: int
    actual_amount: Optional[float] = None
    actual_closing_date: Optional[str] = None  # ISO date string


@router.post("/win-opportunity", summary="标记商机赢单")
async def win_opportunity(
    request: WinOpportunityRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """标记商机赢单

    风险等级: HIGH (强制人工确认)
    """
    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # 解析日期
    closing_date = None
    if request.actual_closing_date:
        try:
            closing_date = date.fromisoformat(request.actual_closing_date)
        except ValueError:
            closing_date = None

    # 调用入口函数
    result = entry.win_opportunity(
        opportunity_id=request.opportunity_id,
        actual_amount=request.actual_amount,
        actual_closing_date=closing_date,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 输单（高风险） ====================

class LoseOpportunityRequest(AIRequestBase):
    """输单请求"""

    opportunity_id: int
    loss_reason: Optional[str] = None


@router.post("/lose-opportunity", summary="标记商机输单")
async def lose_opportunity(
    request: LoseOpportunityRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AIResponseBase:
    """标记商机输单

    风险等级: HIGH (强制人工确认)
    """
    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # 调用入口函数
    result = entry.lose_opportunity(
        opportunity_id=request.opportunity_id,
        loss_reason=request.loss_reason,
        preview=request.preview,
        action_id=request.action_id,
    )

    # 转换为响应
    return _convert_entry_result_to_response(result)


# ==================== 辅助函数 ====================

def _convert_entry_result_to_response(result: ActionEntryResult) -> AIResponseBase:
    """将 ActionEntryResult 转换为 AIResponseBase

    Args:
        result: 入口函数返回结果

    Returns:
        AIResponseBase: HTTP 响应
    """
    if result.status == "preview":
        return AIResponseBase(
            action_id=result.action_id,
            status="preview",
            plan=result.plan,
            confidence=result.confidence,
            requires_confirmation=result.requires_confirmation,
            message="预览：即将执行操作",
        )
    elif result.status == "completed":
        return AIResponseBase(
            action_id=result.action_id,
            status="completed",
            confidence=1.0,
            requires_confirmation=False,
            message="操作已完成",
            data=result.data,
        )
    else:  # failed
        return AIResponseBase(
            action_id=result.action_id,
            status="failed",
            confidence=0.0,
            requires_confirmation=False,
            message=result.error or "操作失败",
            error=result.error,
        )


# ==================== 多动作编排 ====================

from typing import List
from pydantic import BaseModel
from app.services.ai.idempotency import idempotency_manager


class OrchestrateStep(BaseModel):
    """编排步骤"""

    action: str  # action_type: create_follow_up, init_opportunity, etc.
    params: Dict[str, Any]
    order: int = 0


class OrchestrateRequest(AIRequestBase):
    """编排请求"""

    steps: List[OrchestrateStep]
    stop_on_failure: bool = True  # 失败时是否停止


class OrchestrateResult(BaseModel):
    """单个步骤执行结果"""

    step_order: int
    action: str
    status: str  # "success", "failed", "skipped"
    action_id: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class OrchestrateResponse(AIResponseBase):
    """编排响应"""

    results: List[OrchestrateResult] = []
    total_steps: int = 0
    success_count: int = 0
    failed_count: int = 0


@router.post("/orchestrate", summary="编排执行多动作")
async def orchestrate_actions(
    request: OrchestrateRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> OrchestrateResponse:
    """编排执行多个动作

    支持幂等性检查和事务性执行。
    - preview=true: 返回执行计划
    - preview=false: 按顺序执行

    幂等性:
    - action_id 已存在时返回已执行的结果
    """
    orchestrate_id = request.action_id or generate_action_id()

    # 幂等性检查
    if not request.preview:
        if not idempotency_manager.check_or_lock(orchestrate_id):
            cached_result = idempotency_manager.get_result(orchestrate_id)
            if cached_result:
                return OrchestrateResponse(
                    action_id=orchestrate_id,
                    status=cached_result.get("status", "completed"),
                    confidence=1.0,
                    requires_confirmation=False,
                    message="编排已执行（幂等性缓存）",
                    results=cached_result.get("data", {}).get("results", []),
                    total_steps=cached_result.get("data", {}).get("total_steps", 0),
                    success_count=cached_result.get("data", {}).get("success_count", 0),
                    failed_count=cached_result.get("data", {}).get("failed_count", 0),
                )
            return OrchestrateResponse(
                action_id=orchestrate_id,
                status="failed",
                confidence=0.0,
                requires_confirmation=False,
                message="action_id 已被锁定，请稍后重试",
                error="idempotency lock conflict",
            )

    # 按 order 排序
    sorted_steps = sorted(request.steps, key=lambda s: s.order)

    # R-D: 创建 UserExecCtx
    user_ctx = UserExecCtx.from_user(user, is_ai=True, source="ai")
    entry = ActionEntry(db, user_ctx)

    # Preview 模式
    if request.preview:
        preview_results = []
        for step in sorted_steps:
            step_action_id = generate_action_id(f"{orchestrate_id}:{step.order}")
            # 调用入口函数 preview 态
            result = _execute_single_step_preview(entry, step.action, step.params)
            preview_results.append(OrchestrateResult(
                step_order=step.order,
                action=step.action,
                status="preview",
                action_id=step_action_id,
                data={"plan": result.plan.model_dump() if result.plan else None},
            ))

        return OrchestrateResponse(
            action_id=orchestrate_id,
            status="preview",
            confidence=0.9,
            requires_confirmation=False,
            message=f"预览：即将执行 {len(sorted_steps)} 个动作",
            results=preview_results,
            total_steps=len(sorted_steps),
            success_count=0,
            failed_count=0,
        )

    # 执行模式
    results: List[OrchestrateResult] = []
    success_count = 0
    failed_count = 0

    for step in sorted_steps:
        step_action_id = generate_action_id(f"{orchestrate_id}:{step.order}")

        try:
            result = _execute_single_step(entry, step.action, step.params, step_action_id)

            if result.status == "completed":
                results.append(OrchestrateResult(
                    step_order=step.order,
                    action=step.action,
                    status="success",
                    action_id=step_action_id,
                    data=result.data,
                ))
                success_count += 1
            else:
                results.append(OrchestrateResult(
                    step_order=step.order,
                    action=step.action,
                    status="failed",
                    action_id=step_action_id,
                    error=result.error,
                ))
                failed_count += 1

                if request.stop_on_failure:
                    # 标记后续步骤为 skipped
                    for remaining in sorted_steps[step.order + 1:]:
                        results.append(OrchestrateResult(
                            step_order=remaining.order,
                            action=remaining.action,
                            status="skipped",
                            action_id=generate_action_id(f"{orchestrate_id}:{remaining.order}"),
                            error="Skipped due to previous failure",
                        ))
                    break

        except Exception as e:
            results.append(OrchestrateResult(
                step_order=step.order,
                action=step.action,
                status="failed",
                action_id=step_action_id,
                error=str(e),
            ))
            failed_count += 1

            if request.stop_on_failure:
                break

    # 记录幂等性结果
    final_status = "completed" if failed_count == 0 else "partial_completed"
    idempotency_manager.record_result(orchestrate_id, {
        "status": final_status,
        "data": {
            "results": [r.model_dump() for r in results],
            "total_steps": len(sorted_steps),
            "success_count": success_count,
            "failed_count": failed_count,
        },
    })

    return OrchestrateResponse(
        action_id=orchestrate_id,
        status=final_status,
        confidence=1.0 if failed_count == 0 else 0.8,
        requires_confirmation=False,
        message=f"编排完成: {success_count} 成功, {failed_count} 失败",
        results=results,
        total_steps=len(sorted_steps),
        success_count=success_count,
        failed_count=failed_count,
    )


def _execute_single_step_preview(
    entry: ActionEntry,
    action: str,
    params: Dict[str, Any],
) -> ActionEntryResult:
    """执行单个编排步骤的 preview"""
    action_map = {
        "create_follow_up": lambda: entry.create_follow_up(
            customer_id=params.get("customer_id"),
            content=params.get("content"),
            follow_up_time=_parse_datetime(params.get("follow_up_time")),
            method=params.get("method", "电话"),
            next_action=params.get("next_action"),
            opportunity_id=params.get("opportunity_id"),
            preview=True,
        ),
        "set_reminder": lambda: entry.set_reminder(
            customer_id=params.get("customer_id"),
            reminder_time=_parse_datetime(params.get("reminder_time")),
            content=params.get("content"),
            opportunity_id=params.get("opportunity_id"),
            preview=True,
        ),
        "init_opportunity": lambda: entry.init_opportunity(
            customer_id=params.get("customer_id"),
            opportunity_name=params.get("opportunity_name"),
            procurement_method_id=params.get("procurement_method_id"),
            preview=True,
        ),
        "update_amount": lambda: entry.update_amount(
            opportunity_id=params.get("opportunity_id"),
            amount=float(params.get("amount", 0)),
            user_count=params.get("user_count"),
            preview=True,
        ),
        "update_stage": lambda: entry.update_stage(
            opportunity_id=params.get("opportunity_id"),
            target_stage_template_id=params.get("target_stage_template_id"),
            preview=True,
        ),
        "win_opportunity": lambda: entry.win_opportunity(
            opportunity_id=params.get("opportunity_id"),
            actual_amount=params.get("actual_amount"),
            actual_closing_date=_parse_date(params.get("actual_closing_date")),
            preview=True,
        ),
        "lose_opportunity": lambda: entry.lose_opportunity(
            opportunity_id=params.get("opportunity_id"),
            loss_reason=params.get("loss_reason"),
            preview=True,
        ),
    }

    if action not in action_map:
        return ActionEntryResult(action_id="", status="failed", error=f"未知的 action 类型: {action}")

    return action_map[action]()


def _execute_single_step(
    entry: ActionEntry,
    action: str,
    params: Dict[str, Any],
    action_id: str,
) -> ActionEntryResult:
    """执行单个编排步骤"""
    action_map = {
        "create_follow_up": lambda: entry.create_follow_up(
            customer_id=params.get("customer_id"),
            content=params.get("content"),
            follow_up_time=_parse_datetime(params.get("follow_up_time")),
            method=params.get("method", "电话"),
            next_action=params.get("next_action"),
            opportunity_id=params.get("opportunity_id"),
            preview=False,
            action_id=action_id,
        ),
        "set_reminder": lambda: entry.set_reminder(
            customer_id=params.get("customer_id"),
            reminder_time=_parse_datetime(params.get("reminder_time")),
            content=params.get("content"),
            opportunity_id=params.get("opportunity_id"),
            preview=False,
            action_id=action_id,
        ),
        "init_opportunity": lambda: entry.init_opportunity(
            customer_id=params.get("customer_id"),
            opportunity_name=params.get("opportunity_name"),
            procurement_method_id=params.get("procurement_method_id"),
            preview=False,
            action_id=action_id,
        ),
        "update_amount": lambda: entry.update_amount(
            opportunity_id=params.get("opportunity_id"),
            amount=float(params.get("amount", 0)),
            user_count=params.get("user_count"),
            preview=False,
            action_id=action_id,
        ),
        "update_stage": lambda: entry.update_stage(
            opportunity_id=params.get("opportunity_id"),
            target_stage_template_id=params.get("target_stage_template_id"),
            preview=False,
            action_id=action_id,
        ),
        "win_opportunity": lambda: entry.win_opportunity(
            opportunity_id=params.get("opportunity_id"),
            actual_amount=params.get("actual_amount"),
            actual_closing_date=_parse_date(params.get("actual_closing_date")),
            preview=False,
            action_id=action_id,
        ),
        "lose_opportunity": lambda: entry.lose_opportunity(
            opportunity_id=params.get("opportunity_id"),
            loss_reason=params.get("loss_reason"),
            preview=False,
            action_id=action_id,
        ),
    }

    if action not in action_map:
        return ActionEntryResult(action_id=action_id, status="failed", error=f"未知的 action 类型: {action}")

    return action_map[action]()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """解析 datetime 字符串"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    """解析 date 字符串"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


__all__ = ["router"]
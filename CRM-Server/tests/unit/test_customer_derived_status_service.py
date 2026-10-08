"""客户派生状态服务测试。

规则(自上而下,命中即停):
1. 公海(Customer.status == 3)→ PUBLIC_POOL
2. 存在进行中旅程(ACTIVE / WON 未闭环)→ 无成交史 FOLLOWING / 有成交史 REPURCHASING
3. 存在闭环旅程(COMPLETED / WON)且无进行中 → WON
4. 旅程全输单(LOST),或人工流失(Customer.status == 2 且无成交史)→ LOST
5. 名下无任何旅程 → NOT_STARTED
"""

from types import SimpleNamespace

from app.models.deal_journey import DealJourneyStatus
from app.services.customer_derived_status import (
    CUSTOMER_DERIVED_STATUS_LABELS,
    CustomerDerivedStatus,
    derive_customer_status,
    stage_rank,
)
from app.services.deal_journey_stage import BoardStageKey


def _journey(status: str, stage: BoardStageKey = "early_communication", purchase_type: str = "NEW"):
    return SimpleNamespace(status=status, stage=stage, purchase_type=purchase_type)


def _customer(status: int = 0):
    return SimpleNamespace(status=status)


# ---------- 优先级 1:公海 ----------

def test_public_pool_customer_overrides_everything():
    journeys = [_journey(DealJourneyStatus.ACTIVE, "contract_processing")]
    result = derive_customer_status(_customer(status=3), journeys)
    assert result.status == CustomerDerivedStatus.PUBLIC_POOL
    assert result.stage_hint == ""


def test_public_pool_with_no_journeys():
    result = derive_customer_status(_customer(status=3), [])
    assert result.status == CustomerDerivedStatus.PUBLIC_POOL


# ---------- 优先级 2:进行中旅程 ----------

def test_active_journey_without_won_history_is_following():
    result = derive_customer_status(_customer(status=0), [_journey(DealJourneyStatus.ACTIVE, "active_progress")])
    assert result.status == CustomerDerivedStatus.FOLLOWING
    assert result.stage_hint == "新购 · 持续推进"


def test_active_journey_with_completed_history_is_repurchasing():
    journeys = [
        _journey(DealJourneyStatus.COMPLETED, "completed"),
        _journey(DealJourneyStatus.ACTIVE, "contract_processing", "EXPANSION"),
    ]
    result = derive_customer_status(_customer(status=0), journeys)
    assert result.status == CustomerDerivedStatus.REPURCHASING
    assert result.stage_hint == "增购 · 签约中"


def test_won_not_closed_journey_counts_as_active():
    """商机赢单但合同/回款/发票未闭环(WON 状态)= 进行中,不是已成交。"""
    journeys = [
        _journey(DealJourneyStatus.WON, "closing_soon"),
    ]
    result = derive_customer_status(_customer(status=0), journeys)
    assert result.status == CustomerDerivedStatus.FOLLOWING
    assert result.stage_hint == "新购 · 即将签约"


def test_archived_journey_is_ignored_as_active():
    result = derive_customer_status(_customer(status=0), [_journey(DealJourneyStatus.ARCHIVED)])
    assert result.status == CustomerDerivedStatus.NOT_STARTED


def test_deepest_active_journey_wins_stage_hint():
    journeys = [
        _journey(DealJourneyStatus.ACTIVE, "early_communication"),
        _journey(DealJourneyStatus.ACTIVE, "payment_processing", "RENEWAL"),
    ]
    result = derive_customer_status(_customer(status=0), journeys)
    assert result.status == CustomerDerivedStatus.FOLLOWING
    assert result.stage_hint == "续购 · 回款中"


def test_stage_rank_orders_by_depth():
    assert stage_rank("early_communication") < stage_rank("active_progress")
    assert stage_rank("active_progress") < stage_rank("closing_soon")
    assert stage_rank("closing_soon") < stage_rank("contract_processing")
    assert stage_rank("contract_processing") < stage_rank("payment_processing")
    assert stage_rank("payment_processing") < stage_rank("invoice_processing")


# ---------- 优先级 3:闭环 → 已成交 ----------

def test_all_completed_journeys_is_won():
    result = derive_customer_status(
        _customer(status=0),
        [_journey(DealJourneyStatus.COMPLETED, "completed"), _journey(DealJourneyStatus.COMPLETED, "completed")],
    )
    assert result.status == CustomerDerivedStatus.WON
    assert result.stage_hint == ""


def test_lost_then_completed_history_is_won():
    """输单历史不遮盖成交事实:无进行中时存在闭环旅程 → 已成交。"""
    journeys = [
        _journey(DealJourneyStatus.LOST, "lost"),
        _journey(DealJourneyStatus.COMPLETED, "completed"),
    ]
    result = derive_customer_status(_customer(status=0), journeys)
    assert result.status == CustomerDerivedStatus.WON


# ---------- 优先级 4:已流失 ----------

def test_all_lost_journeys_is_lost():
    result = derive_customer_status(_customer(status=0), [_journey(DealJourneyStatus.LOST, "lost")])
    assert result.status == CustomerDerivedStatus.LOST


def test_manual_lost_without_history_is_lost():
    """人工标记流失(从没开过商机的死单)。"""
    result = derive_customer_status(_customer(status=2), [])
    assert result.status == CustomerDerivedStatus.LOST


def test_manual_lost_does_not_override_won_history():
    """已确认决策:历史成交不被人工流失遮盖。"""
    journeys = [_journey(DealJourneyStatus.COMPLETED, "completed")]
    result = derive_customer_status(_customer(status=2), journeys)
    assert result.status == CustomerDerivedStatus.WON


def test_manual_lost_superseded_by_new_active_journey():
    """人工流失后新开旅程 → 自动翻回进行中。"""
    journeys = [_journey(DealJourneyStatus.ACTIVE, "active_progress")]
    result = derive_customer_status(_customer(status=2), journeys)
    assert result.status == CustomerDerivedStatus.FOLLOWING


# ---------- 优先级 5:未启动 ----------

def test_no_journeys_is_not_started():
    result = derive_customer_status(_customer(status=0), [])
    assert result.status == CustomerDerivedStatus.NOT_STARTED
    assert result.stage_hint == ""


def test_old_won_status_without_journeys_stays_not_started():
    """旧数据 status=1 但没有旅程:按旅程事实派生(读时派生的意义)。"""
    result = derive_customer_status(_customer(status=1), [])
    assert result.status == CustomerDerivedStatus.NOT_STARTED


# ---------- 词表 ----------

def test_labels_cover_all_six_statuses():
    assert CUSTOMER_DERIVED_STATUS_LABELS == {
        CustomerDerivedStatus.NOT_STARTED: "未启动",
        CustomerDerivedStatus.FOLLOWING: "跟进中",
        CustomerDerivedStatus.REPURCHASING: "复购中",
        CustomerDerivedStatus.WON: "已成交",
        CustomerDerivedStatus.LOST: "已流失",
        CustomerDerivedStatus.PUBLIC_POOL: "公海",
    }


# ---------- SQL 表达式与纯函数规则一致性 ----------

def test_derived_status_expression_matches_python_rules_shape():
    """SQL case 表达式可编译,且分支覆盖 6 个大类。"""
    from sqlalchemy.dialects import mysql

    from app.services.customer_derived_status import derived_status_expression

    compiled = str(derived_status_expression().compile(dialect=mysql.dialect()))
    assert "CASE WHEN" in compiled
    assert compiled.count("EXISTS") >= 4  # active/completed/lost/any 四个存在性分支
    assert "crm_customers.status" in compiled


def test_derived_status_predicate_maps_enum_values():
    from types import SimpleNamespace

    from app.services.customer_derived_status import (
        CustomerDerivedStatus,
        derived_status_predicate,
    )

    condition = SimpleNamespace(op="in")
    clause = derived_status_predicate(
        condition, SimpleNamespace(key="status"), None, [CustomerDerivedStatus.WON]
    )
    assert clause is not None
    compiled = str(clause)
    assert "CASE WHEN" in compiled
    assert "EXISTS" in compiled
    assert "IN" in compiled

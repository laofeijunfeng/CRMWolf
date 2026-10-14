"""新建合同关联商机的可见范围。"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, Numeric, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.approval_phase import ApprovalPhase
from app.crud import opportunity as opportunity_module
from app.models.opportunity import OpportunityStatus

Base = declarative_base()


class Opportunity(Base):
    __tablename__ = "crm_opportunities"
    id = Column(Integer, primary_key=True)
    team_id = Column(BigInteger, nullable=False)
    opportunity_name = Column(String(255), nullable=False)
    customer_id = Column(BigInteger, nullable=False)
    win_probability = Column(Integer, nullable=False)
    status = Column(Integer, nullable=False)
    approval_phase = Column(String(20), nullable=False)
    created_time = Column(DateTime, nullable=False)


class Contract(Base):
    __tablename__ = "crm_contracts"
    id = Column(Integer, primary_key=True)
    team_id = Column(BigInteger, nullable=False)
    opportunity_id = Column(BigInteger, nullable=False)
    deleted_at = Column(DateTime, nullable=True)


def _rows(db, customer_id, team_id):
    import app.models.contract as contract_model
    import app.models.opportunity as opportunity_model

    original_opportunity = opportunity_model.Opportunity
    original_contract = contract_model.Contract
    opportunity_model.Opportunity = Opportunity
    contract_model.Contract = Contract
    opportunity_module.Opportunity = Opportunity
    try:
        return opportunity_module.opportunity_crud.get_available_for_contract(db, customer_id, team_id)
    finally:
        opportunity_model.Opportunity = original_opportunity
        contract_model.Contract = original_contract
        opportunity_module.Opportunity = original_opportunity


def _opportunity(db, customer_id, team_id, name, status, approval, probability, created):
    row = Opportunity(
        team_id=team_id,
        opportunity_name=name,
        customer_id=customer_id,
        win_probability=probability,
        status=status,
        approval_phase=approval,
        created_time=created,
    )
    db.add(row)
    db.flush()
    return row


def test_contract_picker_query_keeps_following_and_approved_won_only():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    selectable = _opportunity(db, 101, 2, "可创建", OpportunityStatus.WON.value, ApprovalPhase.APPROVED.value, 100, datetime(2026, 10, 4))
    below = _opportunity(db, 101, 2, "未到100", OpportunityStatus.FOLLOWING.value, ApprovalPhase.APPROVED.value, 40, datetime(2026, 10, 3))
    historical = _opportunity(db, 101, 2, "赢率100但仍跟进", OpportunityStatus.FOLLOWING.value, ApprovalPhase.APPROVED.value, 100, datetime(2026, 10, 2))
    lost = _opportunity(db, 101, 2, "已输单", OpportunityStatus.LOST.value, ApprovalPhase.APPROVED.value, 0, datetime(2026, 10, 1))
    contracted = _opportunity(db, 101, 2, "已有合同", OpportunityStatus.WON.value, ApprovalPhase.APPROVED.value, 100, datetime(2026, 9, 30))
    unapproved = _opportunity(db, 101, 2, "赢单未审批", OpportunityStatus.WON.value, ApprovalPhase.PENDING_REVIEW.value, 100, datetime(2026, 9, 29))
    other_team = _opportunity(db, 101, 3, "其他团队", OpportunityStatus.FOLLOWING.value, ApprovalPhase.APPROVED.value, 20, datetime(2026, 10, 5))
    deleted_contract_target = _opportunity(db, 101, 2, "合同已删除", OpportunityStatus.WON.value, ApprovalPhase.APPROVED.value, 100, datetime(2026, 10, 5))
    db.add(Contract(team_id=2, opportunity_id=contracted.id, deleted_at=None))
    db.add(Contract(team_id=2, opportunity_id=deleted_contract_target.id, deleted_at=datetime(2026, 10, 1)))
    db.commit()

    rows = _rows(db, 101, 2)

    assert [row.opportunity_name for row in rows] == ["合同已删除", "可创建", "未到100", "赢率100但仍跟进"]
    assert {row.id for row in rows} == {deleted_contract_target.id, selectable.id, below.id, historical.id}
    assert lost.id not in {row.id for row in rows}
    assert contracted.id not in {row.id for row in rows}
    assert unapproved.id not in {row.id for row in rows}
    assert other_team.id not in {row.id for row in rows}

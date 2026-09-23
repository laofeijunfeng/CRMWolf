# ruff: noqa: B008, ARG001

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_team, require_permission
from app.models.reminder_rule import ReminderRule
from app.models.reminder_rule_run import ReminderRuleRun
from app.models.team import UserTeam
from app.models.user import User, UserStatus
from app.schemas.reminder_rule import (
    ReminderCatalogObject,
    ReminderRecipientUser,
    ReminderRuleEnabledUpdate,
    ReminderRuleRunView,
    ReminderRuleUpdate,
    ReminderRuleView,
    ReminderRuleWrite,
)
from app.services.reminder_rule_dsl import describe_reminder_rule, reminder_rule_catalog, validate_reminder_rule
from app.services.reminder_rule_execution import LEGACY_RULE_HANDLERS

router = APIRouter(prefix="/v1/reminder-rules", tags=["提醒规则"])


def _stored_rule(payload: ReminderRuleWrite) -> dict[str, Any]:
    return payload.model_dump(exclude={"expected_revision"})


def _view(rule: ReminderRule) -> ReminderRuleView:
    stored = dict(rule.rule)
    return ReminderRuleView(
        id=int(rule.id),
        enabled=bool(rule.enabled),
        revision=int(rule.revision),
        sentence=describe_reminder_rule(stored),
        created_time=cast(datetime, rule.created_time),  # noqa: TC006
        last_modified_time=cast(datetime, rule.last_modified_time),  # noqa: TC006
        **stored,
    )


def _get_or_404(db: Session, rule_id: int, team_id: int) -> ReminderRule:
    rule = db.query(ReminderRule).filter(ReminderRule.id == rule_id, ReminderRule.team_id == team_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提醒规则不存在")
    return rule


def _ensure_valid(payload: ReminderRuleWrite, db: Session, team_id: int) -> None:
    errors = validate_reminder_rule(_stored_rule(payload))
    if payload.version == 1 and (payload.object_type, payload.trigger) not in LEGACY_RULE_HANDLERS:
        errors.append("该触发方式没有可执行的提醒规则")
    if payload.version == 2:
        explicit_ids = {
            int(recipient[5:])
            for recipient in payload.recipients
            if recipient.startswith("user:") and recipient[5:].isdigit()
        }
        if explicit_ids:
            members = {
                user_id
                for (user_id,) in db.query(User.id)
                .join(
                    UserTeam,
                    UserTeam.user_id == User.id,
                )
                .filter(
                    User.id.in_(explicit_ids),
                    User.status == UserStatus.ACTIVE,
                    UserTeam.team_id == team_id,
                )
                .all()
            }
            if explicit_ids != members:
                errors.append("指定成员必须是本团队的有效成员")
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "提醒规则无效", "errors": errors},
        )


@router.get("/catalog", response_model=list[ReminderCatalogObject])
def get_reminder_rule_catalog(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("automation:read")),
) -> list[ReminderCatalogObject]:
    return [ReminderCatalogObject.model_validate(item) for item in reminder_rule_catalog()]


@router.get("/recipients", response_model=list[ReminderRecipientUser])
def list_reminder_recipients(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:read")),
) -> list[ReminderRecipientUser]:
    users = db.query(User).join(UserTeam, UserTeam.user_id == User.id).filter(
        UserTeam.team_id == team_id, User.status == UserStatus.ACTIVE,
    ).order_by(User.id).all()
    return [ReminderRecipientUser(id=str(user.id), name=str(user.name)) for user in users]


@router.get("", response_model=list[ReminderRuleView], include_in_schema=False)
@router.get("/", response_model=list[ReminderRuleView])
def list_reminder_rules(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:read")),
) -> list[ReminderRuleView]:
    rules = db.query(ReminderRule).filter(ReminderRule.team_id == team_id).order_by(ReminderRule.id.desc()).all()
    return [_view(rule) for rule in rules]


@router.get("/runs", response_model=list[ReminderRuleRunView])
def list_reminder_rule_runs(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:read")),
) -> list[ReminderRuleRunView]:
    runs = (
        db.query(ReminderRuleRun)
        .filter(ReminderRuleRun.team_id == team_id)
        .order_by(ReminderRuleRun.created_time.desc())
        .all()
    )
    return [
        ReminderRuleRunView(
            id=int(run.id),
            rule_id=int(run.rule_id),
            object_type=str(run.object_type),
            object_id=int(run.object_id),
            message=str(run.message),
            sent_count=int(run.sent_count),
            skipped_count=int(run.skipped_count),
            created_time=cast(datetime, run.created_time),  # noqa: TC006
        )
        for run in runs
    ]


@router.post("", response_model=ReminderRuleView, status_code=status.HTTP_201_CREATED)
def create_reminder_rule(
    payload: ReminderRuleWrite,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:create")),
    publish_user: User = Depends(require_permission("automation:publish")),
) -> ReminderRuleView:
    _ensure_valid(payload, db, team_id)
    rule = ReminderRule(
        team_id=team_id,
        name=payload.name,
        object_type=payload.object_type,
        trigger=payload.trigger,
        rule=_stored_rule(payload),
        enabled=True,
        created_by=current_user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _view(rule)


@router.put("/{rule_id}", response_model=ReminderRuleView)
def update_reminder_rule(
    payload: ReminderRuleUpdate,
    rule_id: int = Path(...),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:edit")),
) -> ReminderRuleView:
    rule = _get_or_404(db, rule_id, team_id)
    if rule.revision != payload.expected_revision:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="提醒规则已被他人修改, 请刷新后重试")
    if dict(rule.rule).get("version", 1) != 2 or payload.version != 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="旧版提醒规则不可编辑")
    _ensure_valid(payload, db, team_id)
    updated = (
        db.query(ReminderRule)
        .filter(
            ReminderRule.id == rule_id,
            ReminderRule.team_id == team_id,
            ReminderRule.revision == payload.expected_revision,
        )
        .update(
            {
                ReminderRule.name: payload.name,
                ReminderRule.object_type: payload.object_type,
                ReminderRule.trigger: payload.trigger,
                ReminderRule.rule: _stored_rule(payload),
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="提醒规则已被他人修改, 请刷新后重试")
    db.commit()
    db.refresh(rule)
    return _view(rule)

@router.put("/{rule_id}/enabled", response_model=ReminderRuleView)
def update_reminder_rule_enabled(
    payload: ReminderRuleEnabledUpdate,
    rule_id: int = Path(...),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:publish")),
) -> ReminderRuleView:
    rule = _get_or_404(db, rule_id, team_id)
    updated = (
        db.query(ReminderRule)
        .filter(
            ReminderRule.id == rule_id,
            ReminderRule.team_id == team_id,
            ReminderRule.revision == payload.expected_revision,
        )
        .update({ReminderRule.enabled: payload.enabled}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="提醒规则已被他人修改, 请刷新后重试")
    db.commit()
    db.refresh(rule)
    return _view(rule)

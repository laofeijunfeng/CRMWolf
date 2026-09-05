"""Read-only recovery endpoints for non-Agent command outcomes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User
from app.schemas.command import CommandExecutionResponse
from app.services.command_execution_service import command_execution_service

router = APIRouter(prefix="/v1/operations", tags=["操作结果"])


@router.get(
    "/{operation_id}",
    response_model=CommandExecutionResponse,
    summary="查询操作最终结果",
    description="用于写操作超时、断网或页面刷新后的结果确认。不会重放原命令。",
)
def get_operation(
    operation_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> CommandExecutionResponse:
    # Keep the query explicit here rather than exposing an unscoped lookup.
    from app.models.command_execution import CommandExecution

    execution = (
        db.query(CommandExecution)
        .filter(CommandExecution.operation_id == operation_id, CommandExecution.team_id == team_id)
        .first()
    )
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="操作记录不存在")
    if execution.actor_id != str(current_user.id):
        # Team members may inspect a result only when the resource permission
        # is handled by the owning command.  Until that registry exists, keep
        # operation records private to the initiating user.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该操作结果")
    return CommandExecutionResponse.model_validate(command_execution_service.to_response_payload(execution))

"""IM webhook APIs."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.im_feishu import FeishuBotEventError, feishu_bot_service


router = APIRouter(prefix="/v1/im", tags=["IM机器人"])


@router.post("/feishu/events")
async def handle_feishu_event(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    try:
        result = await feishu_bot_service.handle_event(db, payload, await request.body())
    except FeishuBotEventError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.get("challenge"):
        return {"challenge": result["challenge"]}
    return {"code": 0, "msg": result.get("message") or "ok"}

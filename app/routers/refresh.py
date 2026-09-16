from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import config
from ..db import connect
from ..util import quota_date
from ..services import refresh as refresh_service
from ..services import scheduler

router = APIRouter(prefix="/api/refresh", tags=["refresh"])


class RefreshRequest(BaseModel):
    scope: str = "all"          # all | group | channel
    group_id: Optional[int] = None
    channel_id: Optional[int] = None


@router.post("")
def start_refresh(data: RefreshRequest):
    if data.scope not in ("all", "group", "channel"):
        raise HTTPException(status_code=400, detail="scope 는 all/group/channel 중 하나여야 합니다")
    with connect() as conn:
        keys = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1").fetchone()[0]
        if not keys:
            raise HTTPException(status_code=400, detail="API 키가 없습니다. 설정에서 API 키를 먼저 등록하세요.")
    try:
        refresh_service.start_refresh_in_background(
            scope=data.scope, group_id=data.group_id, channel_id=data.channel_id, trigger="manual"
        )
    except refresh_service.RefreshAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"started": True}


@router.get("/status")
def refresh_status():
    state = refresh_service.STATE.snapshot()
    with connect() as conn:
        runs = refresh_service.last_runs(conn, limit=1)
        last_success = refresh_service.last_successful_run(conn)
        today = quota_date()
        used = conn.execute("SELECT COALESCE(SUM(used_today), 0) FROM api_keys WHERE used_date = ?", (today,)).fetchone()[0]
        key_count = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1").fetchone()[0]
        next_run = scheduler.next_run_iso(conn)
    return {
        "state": state,
        "last_run": runs[0] if runs else None,
        "last_success": last_success,
        "next_run_at": next_run,
        "quota": {"used_today": used, "daily_quota": config.DAILY_QUOTA * max(key_count, 1),
                  "per_key": config.DAILY_QUOTA, "key_count": key_count, "quota_date": today},
    }


@router.get("/runs")
def refresh_runs(limit: int = Query(20, ge=1, le=200)):
    with connect() as conn:
        return {"runs": refresh_service.last_runs(conn, limit)}

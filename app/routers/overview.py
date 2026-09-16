from fastapi import APIRouter, Query

from ..db import connect
from ..services.insights import build_overview

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview")
def get_overview(group_id: int = 0, days: int = Query(7, ge=1, le=365), include_inactive: bool = False):
    with connect() as conn:
        return build_overview(conn, group_id=group_id, days=days, include_inactive=include_inactive)

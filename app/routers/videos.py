from fastapi import APIRouter, Query

from ..db import connect, get_settings, typed_settings
from ..util import utc_now, ago_iso
from ..services import insights

router = APIRouter(prefix="/api/videos", tags=["videos"])

SORTS = {
    "published": lambda v: v["published_at"] or "",
    "views": lambda v: v["view_count"] or 0,
    "views_per_day": lambda v: v["views_per_day"] or 0,
    "delta": lambda v: v["view_delta"] or 0,
    "likes": lambda v: v["like_count"] or 0,
    "comments": lambda v: v["comment_count"] or 0,
    "ratio": lambda v: v["ratio"] or 0,
}


def query_videos(conn, group_id: int = 0, channel_id: int = 0, days: int = 30, kind: str = "all",
                 q: str = "", sort: str = "published", include_inactive: bool = False):
    now = utc_now()
    settings = typed_settings(get_settings(conn))
    where, params = insights.channel_where(group_id, include_inactive)
    if channel_id:
        where += " AND c.id = ?"
        params.append(channel_id)
    if days:
        where += " AND v.published_at >= ?"
        params.append(ago_iso(days=days, now=now))
    if kind == "short":
        where += " AND v.is_short = 1"
    elif kind == "long":
        where += " AND v.is_short = 0"
    if q.strip():
        where += " AND v.title LIKE ?"
        params.append(f"%{q.strip()}%")

    rows = conn.execute(
        f"""SELECT v.*, c.title AS channel_title, c.thumbnail_url AS channel_thumbnail, c.group_id, g.name AS group_name
            FROM videos v JOIN channels c ON c.id = v.channel_id JOIN groups g ON g.id = c.group_id
            WHERE {where} ORDER BY v.published_at DESC LIMIT 5000""",
        params,
    ).fetchall()
    channel_ids = list({row["channel_id"] for row in rows})
    medians = insights.channel_medians(conn, channel_ids, settings["video_stats_window_days"], now)

    items = []
    for row in rows:
        item = insights.video_dict(row, now)
        item["channel_title"] = row["channel_title"]
        item["channel_thumbnail"] = row["channel_thumbnail"]
        item["group_id"] = row["group_id"]
        item["group_name"] = row["group_name"]
        med = medians.get(row["channel_id"])
        item["ratio"] = round(item["views_per_day"] / med, 2) if med and item["views_per_day"] else None
        items.append(item)
    items.sort(key=SORTS.get(sort, SORTS["published"]), reverse=True)
    return items


@router.get("")
def list_videos(group_id: int = 0, channel_id: int = 0, days: int = Query(30, ge=0, le=3650),
                kind: str = "all", q: str = "", sort: str = "published",
                limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), include_inactive: bool = False):
    with connect() as conn:
        items = query_videos(conn, group_id, channel_id, days, kind, q, sort, include_inactive)
    total = len(items)
    page = items[offset:offset + limit]
    return {"videos": page, "total": total, "limit": limit, "offset": offset,
            "short_count": sum(1 for v in items if v["is_short"]),
            "long_count": sum(1 for v in items if not v["is_short"])}

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import connect, get_settings, typed_settings, DEFAULT_GROUP_ID
from ..util import utc_now, utc_now_iso, ago_iso, days_since
from ..services import insights
from ..services.refresh import make_client, persist_key_usage, apply_channel_info, upsert_video, compact_snapshots
from ..services.resolver import resolve_inputs
from ..services.youtube import AllKeysExhausted, YouTubeError

router = APIRouter(prefix="/api/channels", tags=["channels"])


class AddChannelsRequest(BaseModel):
    inputs: List[str] = Field(default_factory=list)
    group_id: int = DEFAULT_GROUP_ID
    fetch_videos: bool = True


class ChannelPatch(BaseModel):
    group_id: Optional[int] = None
    is_active: Optional[bool] = None
    memo: Optional[str] = None


class BulkRequest(BaseModel):
    ids: List[int]
    action: str  # move | activate | deactivate | delete
    group_id: Optional[int] = None


def _group_exists(conn, group_id: int) -> bool:
    return conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone() is not None


def _get_channel(conn, channel_id: int):
    row = conn.execute(
        "SELECT c.*, g.name AS group_name FROM channels c JOIN groups g ON g.id = c.group_id WHERE c.id = ?",
        (channel_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")
    return row


@router.get("")
def list_channels(group_id: int = 0, q: str = "", include_inactive: bool = True):
    where, params = insights.channel_where(group_id, include_inactive)
    if q.strip():
        where += " AND (c.title LIKE ? OR c.handle LIKE ? OR c.youtube_id LIKE ?)"
        like = f"%{q.strip()}%"
        params += [like, like, like]
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT c.*, g.name AS group_name,
                       (SELECT MAX(published_at) FROM videos v WHERE v.channel_id = c.id) AS last_published_at
                FROM channels c JOIN groups g ON g.id = c.group_id
                WHERE {where} ORDER BY c.subscriber_count DESC, c.id ASC""",
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = insights.channel_dict(row)
            item["last_published_at"] = row["last_published_at"]
            item["days_since_upload"] = days_since(row["last_published_at"])
            items.append(item)
        return {"channels": items, "total": len(items)}


@router.post("")
def add_channels(data: AddChannelsRequest):
    inputs = [line for line in (s.strip() for s in data.inputs) if line]
    if not inputs:
        raise HTTPException(status_code=400, detail="추가할 채널을 입력하세요")
    if len(inputs) > 200:
        raise HTTPException(status_code=400, detail="한 번에 200개까지 추가할 수 있습니다")

    with connect() as conn:
        if not _group_exists(conn, data.group_id):
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
        client = make_client(conn)
        settings = typed_settings(get_settings(conn))
    if not client.pool.keys:
        raise HTTPException(status_code=400, detail="사용 가능한 API 키가 없습니다. 설정에서 API 키를 먼저 등록하세요.")

    added, skipped, failed = [], [], []
    try:
        resolutions = resolve_inputs(client, inputs)
        now = utc_now_iso()
        new_rows = []
        with connect() as conn:
            for res in resolutions:
                if res.error == "빈 줄":
                    continue
                if res.error or not res.info:
                    failed.append({"input": res.raw, "error": res.error or "알 수 없는 오류"})
                    continue
                existing = conn.execute("SELECT id, title FROM channels WHERE youtube_id = ?", (res.youtube_id,)).fetchone()
                if existing:
                    skipped.append({"input": res.raw, "channel_id": existing["id"], "title": existing["title"],
                                    "reason": "이미 등록된 채널입니다"})
                    continue
                cur = conn.execute(
                    "INSERT INTO channels (youtube_id, group_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (res.youtube_id, data.group_id, now, now),
                )
                channel_id = cur.lastrowid
                apply_channel_info(conn, channel_id, res.info, now)
                added.append({"input": res.raw, "channel_id": channel_id, "title": res.info["title"],
                              "subscriber_count": res.info["subscriber_count"], "note": res.note})
                new_rows.append((channel_id, res.info))

        # 새 채널의 최근 영상을 바로 수집 (채널당 1 unit + 영상 50개당 1 unit)
        if data.fetch_videos and new_rows:
            pending = {}
            for channel_id, info in new_rows:
                playlist_id = info.get("uploads_playlist_id")
                if not playlist_id:
                    continue
                try:
                    for video_id in client.playlist_video_ids(playlist_id, settings["max_videos_per_channel"]):
                        pending[video_id] = channel_id
                except YouTubeError:
                    continue
            if pending:
                details = client.videos_by_ids(list(pending.keys()), settings["shorts_max_seconds"])
                stamp = utc_now_iso()
                with connect() as conn:
                    for video in details:
                        upsert_video(conn, pending[video["youtube_id"]], video, stamp)
    except AllKeysExhausted as exc:
        persist_key_usage(client.pool)
        raise HTTPException(status_code=429, detail=str(exc))
    except YouTubeError as exc:
        persist_key_usage(client.pool)
        raise HTTPException(status_code=502, detail=str(exc))

    persist_key_usage(client.pool)
    return {"added": added, "skipped": skipped, "failed": failed, "quota_used": client.pool.total_usage}


@router.get("/{channel_id}")
def get_channel(channel_id: int, days: int = Query(7, ge=1, le=365)):
    now = utc_now()
    period_start = ago_iso(days=days, now=now)
    with connect() as conn:
        row = _get_channel(conn, channel_id)
        settings = typed_settings(get_settings(conn))
        item = insights.channel_dict(row)

        base = insights.load_baselines(conn, [channel_id], period_start).get(channel_id)
        if base and not (base["partial"] and base["captured_at"] == item["stats_updated_at"]):
            item["delta"] = {
                "subscriber_count": insights._delta(item["subscriber_count"], base["subscriber_count"]),
                "view_count": insights._delta(item["view_count"], base["view_count"]),
                "video_count": insights._delta(item["video_count"], base["video_count"]),
                "baseline_at": base["captured_at"], "partial": base["partial"],
            }
        else:
            item["delta"] = {"subscriber_count": None, "view_count": None, "video_count": None,
                             "baseline_at": None, "partial": bool(base)}

        agg = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(view_count), 0) AS views FROM videos WHERE channel_id = ? AND published_at >= ?",
            (channel_id, period_start),
        ).fetchone()
        item["uploads_in_period"] = agg["n"]
        item["period_upload_views"] = agg["views"]
        item["avg_views_per_upload"] = round(agg["views"] / agg["n"]) if agg["n"] else None

        latest = conn.execute(
            "SELECT * FROM videos WHERE channel_id = ? ORDER BY published_at DESC LIMIT 1", (channel_id,)
        ).fetchone()
        item["latest_video"] = insights.video_dict(latest, now) if latest else None
        item["days_since_upload"] = item["latest_video"]["days_since_published"] if latest else None
        item["video_rows"] = conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", (channel_id,)).fetchone()[0]
        item["snapshot_rows"] = conn.execute("SELECT COUNT(*) FROM snapshots WHERE channel_id = ?", (channel_id,)).fetchone()[0]
        item["median_views_per_day"] = insights.channel_medians(conn, [channel_id], settings["video_stats_window_days"], now).get(channel_id)
        item["period_days"] = days
        return item


@router.patch("/{channel_id}")
def patch_channel(channel_id: int, data: ChannelPatch):
    with connect() as conn:
        _get_channel(conn, channel_id)
        updates, params = [], []
        if data.group_id is not None:
            if not _group_exists(conn, data.group_id):
                raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
            updates.append("group_id = ?")
            params.append(data.group_id)
        if data.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if data.is_active else 0)
        if data.memo is not None:
            updates.append("memo = ?")
            params.append(data.memo[:5000])
        if not updates:
            raise HTTPException(status_code=400, detail="변경할 내용이 없습니다")
        updates.append("updated_at = ?")
        params.append(utc_now_iso())
        params.append(channel_id)
        conn.execute(f"UPDATE channels SET {', '.join(updates)} WHERE id = ?", params)
        return insights.channel_dict(_get_channel(conn, channel_id))


@router.delete("/{channel_id}")
def delete_channel(channel_id: int):
    with connect() as conn:
        _get_channel(conn, channel_id)
        conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        return {"ok": True}


@router.post("/bulk")
def bulk_channels(data: BulkRequest):
    if not data.ids:
        raise HTTPException(status_code=400, detail="선택된 채널이 없습니다")
    placeholders = ",".join("?" * len(data.ids))
    now = utc_now_iso()
    with connect() as conn:
        if data.action == "move":
            if not data.group_id or not _group_exists(conn, data.group_id):
                raise HTTPException(status_code=404, detail="이동할 그룹을 선택하세요")
            cur = conn.execute(f"UPDATE channels SET group_id = ?, updated_at = ? WHERE id IN ({placeholders})",
                               (data.group_id, now, *data.ids))
        elif data.action in ("activate", "deactivate"):
            cur = conn.execute(f"UPDATE channels SET is_active = ?, updated_at = ? WHERE id IN ({placeholders})",
                               (1 if data.action == "activate" else 0, now, *data.ids))
        elif data.action == "delete":
            cur = conn.execute(f"DELETE FROM channels WHERE id IN ({placeholders})", data.ids)
        else:
            raise HTTPException(status_code=400, detail="알 수 없는 작업입니다")
        return {"ok": True, "affected": cur.rowcount}


@router.get("/{channel_id}/history")
def get_history(channel_id: int, days: int = Query(30, ge=1, le=365)):
    with connect() as conn:
        _get_channel(conn, channel_id)
        history = insights.channel_history(conn, channel_id, days)
        return {"channel_id": channel_id, "days": days, "history": history}


@router.get("/{channel_id}/videos")
def get_channel_videos(channel_id: int, limit: int = Query(50, ge=1, le=500), sort: str = "published"):
    now = utc_now()
    with connect() as conn:
        _get_channel(conn, channel_id)
        settings = typed_settings(get_settings(conn))
        med = insights.channel_medians(conn, [channel_id], settings["video_stats_window_days"], now).get(channel_id)
        rows = conn.execute("SELECT * FROM videos WHERE channel_id = ? ORDER BY published_at DESC LIMIT ?",
                            (channel_id, limit)).fetchall()
        items = []
        for row in rows:
            item = insights.video_dict(row, now)
            item["ratio"] = round(item["views_per_day"] / med, 2) if med and item["views_per_day"] else None
            items.append(item)
        key = {
            "views": lambda v: -(v["view_count"] or 0),
            "views_per_day": lambda v: -(v["views_per_day"] or 0),
            "delta": lambda v: -(v["view_delta"] or 0),
            "likes": lambda v: -(v["like_count"] or 0),
            "comments": lambda v: -(v["comment_count"] or 0),
        }.get(sort)
        if key:
            items.sort(key=key)
        return {"channel_id": channel_id, "videos": items, "median_views_per_day": med}

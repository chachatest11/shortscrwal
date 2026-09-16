"""
채널 대시보드 API

여러 채널의 현황(구독자/조회수/영상 수/최근 업로드)을 한눈에 보기 위한 라우터.

- POST /api/dashboard/refresh   : YouTube Data API로 모든 활성 채널 통계를 갱신하고 스냅샷 저장
- GET  /api/dashboard/overview  : 대시보드 데이터 (현재 통계 + 기간 대비 증감 + 최근 업로드 + 추이)
- GET  /api/dashboard/channels/{channel_id}/videos  : 채널의 최근 영상 목록 (DB)
- GET  /api/dashboard/channels/{channel_id}/history : 채널 통계 스냅샷 이력 (DB)

쿼터 비용 (YouTube Data API v3, 일일 기본 10,000 units):
- channels.list      : 호출당 1 unit (채널 50개까지 한 번에)
- playlistItems.list : 호출당 1 unit (채널당 1회)
- videos.list        : 호출당 1 unit (영상 50개까지 한 번에)
=> 채널 30개 + 채널당 최근 영상 10개 갱신 시 약 1 + 30 + 6 = 37 units
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from ..db import get_db
from .youtube import YouTubeAPI, QuotaExceededException
from .channels import get_available_api_key, mark_api_key_quota_exceeded

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

SPARKLINE_DAYS = 30          # 추이 그래프에 사용할 일수
SNAPSHOT_KEEP_ALL_DAYS = 2   # 이 기간 내 스냅샷은 모두 보관, 이후는 하루 1개만 보관


class RefreshRequest(BaseModel):
    category_id: int = 0                      # 0 = 전체
    include_videos: bool = True               # 최근 업로드 영상도 수집할지
    max_videos: int = Field(default=10, ge=1, le=50)  # 채널당 최근 영상 수
    api_key: Optional[str] = None             # 없으면 DB의 활성 키 사용


def _uploads_playlist_id(channel_id: str, info: Dict) -> Optional[str]:
    """업로드 플레이리스트 ID (API 응답 우선, 없으면 UC -> UU 규칙으로 유추)"""
    playlist_id = info.get("uploads_playlist_id")
    if playlist_id:
        return playlist_id
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return None


def _upsert_videos(video_rows: List[Dict]) -> int:
    """영상 메타데이터를 videos 테이블에 upsert (기존 영상은 통계/제목 갱신)"""
    if not video_rows:
        return 0

    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        for v in video_rows:
            cursor.execute("SELECT id FROM videos WHERE video_id = ?", (v["video_id"],))
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE videos
                    SET title = ?, view_count = ?, like_count = ?, comment_count = ?,
                        thumbnail_url = ?, duration_seconds = ?, is_short = ?, updated_at = ?
                    WHERE video_id = ?
                """, (
                    v["title"], v["view_count"], v["like_count"], v["comment_count"],
                    v["thumbnail_url"], v["duration_seconds"], v["is_short"], now,
                    v["video_id"]
                ))
            else:
                cursor.execute("""
                    INSERT INTO videos (
                        channel_id, video_id, title, published_at,
                        view_count, like_count, comment_count, thumbnail_url,
                        duration_seconds, is_short, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    v["channel_id"], v["video_id"], v["title"], v["published_at"],
                    v["view_count"], v["like_count"], v["comment_count"], v["thumbnail_url"],
                    v["duration_seconds"], v["is_short"], now, now
                ))
        conn.commit()

    return len(video_rows)


def _compact_snapshots(cursor) -> None:
    """오래된 스냅샷은 채널별로 하루 마지막 1개만 남기고 삭제 (DB 비대화 방지)"""
    cutoff = (datetime.now() - timedelta(days=SNAPSHOT_KEEP_ALL_DAYS)).isoformat()
    cursor.execute("""
        DELETE FROM channel_snapshots
        WHERE captured_at < ?
          AND id NOT IN (
              SELECT MAX(id)
              FROM channel_snapshots
              WHERE captured_at < ?
              GROUP BY channel_id, substr(captured_at, 1, 10)
          )
    """, (cutoff, cutoff))


@router.post("/refresh")
def refresh_dashboard(data: RefreshRequest):
    """
    활성 채널 전체의 현황을 YouTube API에서 갱신

    1. 대상 채널 로드 (유튜브 채널 ID 기준 중복 제거)
    2. channels.list 배치 호출로 통계 갱신 + 스냅샷 저장
    3. (옵션) 채널별 최근 업로드 영상 수집
    """
    api_key = get_available_api_key(data.api_key)
    youtube_api = YouTubeAPI(api_key)

    # 1. 대상 채널 로드
    with get_db() as conn:
        cursor = conn.cursor()
        if data.category_id > 0:
            cursor.execute("""
                SELECT DISTINCT channel_id FROM channels
                WHERE is_active = 1 AND category_id = ?
            """, (data.category_id,))
        else:
            cursor.execute("SELECT DISTINCT channel_id FROM channels WHERE is_active = 1")
        channel_ids = [row[0] for row in cursor.fetchall()]

    if not channel_ids:
        return {
            "updated": 0,
            "failed": 0,
            "videos_upserted": 0,
            "quota_used": 0,
            "quota_exceeded": False,
            "errors": [],
            "refreshed_at": None,
            "message": "활성화된 채널이 없습니다"
        }

    errors: List[Dict] = []
    quota_exceeded = False
    infos: Dict[str, Dict] = {}

    # 2. 채널 통계 배치 조회
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i + 50]
        try:
            infos.update(youtube_api.get_channels_batch(batch))
        except QuotaExceededException:
            mark_api_key_quota_exceeded(api_key)
            quota_exceeded = True
            errors.append({
                "channel_id": None,
                "channel_title": "YouTube API",
                "error": "API 쿼터가 초과되었습니다. 다른 API 키를 추가하거나 내일 다시 시도하세요."
            })
            break
        except Exception as e:
            errors.append({
                "channel_id": None,
                "channel_title": "YouTube API",
                "error": f"채널 정보 조회 실패: {str(e)}"
            })

    refreshed_at = datetime.now().isoformat()
    updated = 0

    # 3. DB 갱신 + 스냅샷 저장
    with get_db() as conn:
        cursor = conn.cursor()
        for channel_id in channel_ids:
            info = infos.get(channel_id)
            if not info:
                if not quota_exceeded and infos:
                    errors.append({
                        "channel_id": channel_id,
                        "channel_title": channel_id,
                        "error": "YouTube에서 채널을 찾을 수 없습니다 (삭제 또는 비공개)"
                    })
                continue

            cursor.execute("""
                UPDATE channels
                SET title = ?, description = ?, subscriber_count = ?, subscriber_hidden = ?,
                    country = ?, view_count = ?, video_count = ?, thumbnail_url = ?,
                    uploads_playlist_id = ?, custom_url = ?, published_at = ?,
                    stats_updated_at = ?, updated_at = ?
                WHERE channel_id = ?
            """, (
                info["title"], info.get("description"), info["subscriber_count"],
                1 if info.get("subscriber_hidden") else 0,
                info.get("country"), info["view_count"], info["video_count"],
                info.get("thumbnail_url"), info.get("uploads_playlist_id"),
                info.get("custom_url"), info.get("published_at"),
                refreshed_at, refreshed_at, channel_id
            ))

            cursor.execute("""
                INSERT INTO channel_snapshots
                    (channel_id, subscriber_count, view_count, video_count, captured_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                channel_id, info["subscriber_count"], info["view_count"],
                info["video_count"], refreshed_at
            ))
            updated += 1

        _compact_snapshots(cursor)
        conn.commit()

    # 4. 최근 업로드 영상 수집
    videos_upserted = 0
    if data.include_videos and not quota_exceeded and infos:
        pending_video_ids: List[str] = []

        for channel_id, info in infos.items():
            playlist_id = _uploads_playlist_id(channel_id, info)
            if not playlist_id:
                continue
            try:
                pending_video_ids.extend(
                    youtube_api.get_videos_from_playlist(playlist_id, max_results=data.max_videos)
                )
            except QuotaExceededException:
                mark_api_key_quota_exceeded(api_key)
                quota_exceeded = True
                errors.append({
                    "channel_id": channel_id,
                    "channel_title": info.get("title"),
                    "error": "최근 영상 수집 중 API 쿼터가 초과되었습니다 (채널 통계는 갱신됨)"
                })
                break
            except Exception as e:
                errors.append({
                    "channel_id": channel_id,
                    "channel_title": info.get("title"),
                    "error": f"최근 영상 조회 실패: {str(e)}"
                })

        if pending_video_ids and not quota_exceeded:
            try:
                details = youtube_api.get_video_details(pending_video_ids)
                videos_upserted = _upsert_videos(details)
            except QuotaExceededException:
                mark_api_key_quota_exceeded(api_key)
                quota_exceeded = True
                errors.append({
                    "channel_id": None,
                    "channel_title": "YouTube API",
                    "error": "영상 상세 조회 중 API 쿼터가 초과되었습니다 (채널 통계는 갱신됨)"
                })

    return {
        "updated": updated,
        "failed": len(channel_ids) - updated,
        "videos_upserted": videos_upserted,
        "quota_used": youtube_api.quota_used,
        "quota_exceeded": quota_exceeded,
        "errors": errors,
        "refreshed_at": refreshed_at
    }


def _delta(current: Optional[int], baseline: Optional[int]) -> Optional[int]:
    if current is None or baseline is None:
        return None
    return current - baseline


@router.get("/overview")
def get_overview(
    category_id: int = 0,
    days: int = Query(7, ge=1, le=365),
    include_inactive: bool = False
):
    """
    대시보드 데이터 조회 (API 호출 없음, DB만 사용)

    - 채널별 현재 통계와 기간(days) 시작 시점 스냅샷 대비 증감
    - 기간 내 업로드 수, 최근 업로드 영상, 구독자 추이(스파크라인)
    - 전체 합계
    """
    now = datetime.now()
    period_start_local = (now - timedelta(days=days)).isoformat()
    # videos.published_at은 YouTube가 주는 UTC ISO 문자열(...Z)이므로 UTC 기준으로 비교
    period_start_utc = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sparkline_start = (now - timedelta(days=SPARKLINE_DAYS)).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. 채널 목록 (같은 유튜브 채널이 여러 카테고리에 있으면 하나로 합침)
        conditions = []
        params: List = []
        if not include_inactive:
            conditions.append("c.is_active = 1")
        if category_id > 0:
            conditions.append("c.category_id = ?")
            params.append(category_id)
        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cursor.execute(f"""
            SELECT c.id, c.channel_id, c.title, c.thumbnail_url, c.custom_url, c.country,
                   c.subscriber_count, c.view_count, c.video_count, c.published_at,
                   c.stats_updated_at, c.is_active, c.category_id, cat.name,
                   c.subscriber_hidden
            FROM channels c
            LEFT JOIN categories cat ON cat.id = c.category_id
            {where_clause}
            ORDER BY c.subscriber_count DESC, c.id ASC
        """, params)

        channels: Dict[str, Dict] = {}
        for row in cursor.fetchall():
            channel_id = row[1]
            if channel_id in channels:
                if row[13] and row[13] not in channels[channel_id]["categories"]:
                    channels[channel_id]["categories"].append(row[13])
                continue
            channels[channel_id] = {
                "id": row[0],
                "channel_id": channel_id,
                "title": row[2] or channel_id,
                "thumbnail_url": row[3],
                "custom_url": row[4],
                "country": row[5],
                "subscriber_count": row[6],
                "subscriber_hidden": bool(row[14]),
                "view_count": row[7],
                "video_count": row[8],
                "published_at": row[9],
                "stats_updated_at": row[10],
                "is_active": row[11],
                "category_id": row[12],
                "categories": [row[13]] if row[13] else [],
                "delta": {
                    "subscriber_count": None,
                    "view_count": None,
                    "video_count": None,
                    "baseline_at": None,
                    "baseline_is_partial": False
                },
                "uploads_in_period": 0,
                "period_upload_views": 0,
                "latest_video": None,
                "days_since_upload": None,
                "sparkline": []
            }

        channel_ids = list(channels.keys())
        if not channel_ids:
            return {
                "generated_at": now.isoformat(),
                "period_days": days,
                "last_refresh_at": None,
                "summary": _empty_summary(),
                "channels": []
            }

        placeholders = ",".join("?" * len(channel_ids))

        # 2. 기준 스냅샷: 기간 시작 시점 이전의 마지막 스냅샷
        cursor.execute(f"""
            SELECT s.channel_id, s.subscriber_count, s.view_count, s.video_count, s.captured_at
            FROM channel_snapshots s
            JOIN (
                SELECT channel_id, MAX(captured_at) AS captured_at
                FROM channel_snapshots
                WHERE captured_at <= ? AND channel_id IN ({placeholders})
                GROUP BY channel_id
            ) latest ON latest.channel_id = s.channel_id AND latest.captured_at = s.captured_at
        """, (period_start_local, *channel_ids))
        baselines = {row[0]: (row[1], row[2], row[3], row[4], False) for row in cursor.fetchall()}

        # 기간 시작 이전 스냅샷이 없는 채널은 가장 오래된 스냅샷을 기준으로 사용 (부분 기간)
        missing = [cid for cid in channel_ids if cid not in baselines]
        if missing:
            missing_placeholders = ",".join("?" * len(missing))
            cursor.execute(f"""
                SELECT s.channel_id, s.subscriber_count, s.view_count, s.video_count, s.captured_at
                FROM channel_snapshots s
                JOIN (
                    SELECT channel_id, MIN(captured_at) AS captured_at
                    FROM channel_snapshots
                    WHERE channel_id IN ({missing_placeholders})
                    GROUP BY channel_id
                ) first ON first.channel_id = s.channel_id AND first.captured_at = s.captured_at
            """, missing)
            for row in cursor.fetchall():
                baselines[row[0]] = (row[1], row[2], row[3], row[4], True)

        for channel_id, base in baselines.items():
            ch = channels[channel_id]
            base_subs, base_views, base_videos, base_at, partial = base
            # 기준 스냅샷이 현재 통계와 같은 시각이면 비교 대상이 아직 없는 것
            if partial and base_at == ch["stats_updated_at"]:
                continue
            ch["delta"] = {
                "subscriber_count": _delta(ch["subscriber_count"], base_subs),
                "view_count": _delta(ch["view_count"], base_views),
                "video_count": _delta(ch["video_count"], base_videos),
                "baseline_at": base_at,
                "baseline_is_partial": partial
            }

        # 3. 스파크라인: 최근 30일, 하루 마지막 스냅샷
        cursor.execute(f"""
            SELECT s.channel_id, s.captured_at, s.subscriber_count, s.view_count
            FROM channel_snapshots s
            JOIN (
                SELECT channel_id, substr(captured_at, 1, 10) AS day, MAX(captured_at) AS captured_at
                FROM channel_snapshots
                WHERE captured_at >= ? AND channel_id IN ({placeholders})
                GROUP BY channel_id, day
            ) d ON d.channel_id = s.channel_id AND d.captured_at = s.captured_at
            ORDER BY s.channel_id, s.captured_at
        """, (sparkline_start, *channel_ids))
        for row in cursor.fetchall():
            channels[row[0]]["sparkline"].append({
                "captured_at": row[1],
                "subscriber_count": row[2],
                "view_count": row[3]
            })

        # 4. 기간 내 업로드 수 / 업로드 영상 조회수 합
        cursor.execute(f"""
            SELECT channel_id, COUNT(*), COALESCE(SUM(view_count), 0)
            FROM videos
            WHERE channel_id IN ({placeholders}) AND published_at >= ?
            GROUP BY channel_id
        """, (*channel_ids, period_start_utc))
        for row in cursor.fetchall():
            channels[row[0]]["uploads_in_period"] = row[1]
            channels[row[0]]["period_upload_views"] = row[2]

        # 5. 최근 업로드 영상
        cursor.execute(f"""
            SELECT v.channel_id, v.video_id, v.title, v.thumbnail_url, v.published_at,
                   v.view_count, v.like_count, v.comment_count, v.is_short, v.duration_seconds
            FROM videos v
            JOIN (
                SELECT channel_id, MAX(published_at) AS published_at
                FROM videos
                WHERE channel_id IN ({placeholders})
                GROUP BY channel_id
            ) m ON m.channel_id = v.channel_id AND m.published_at = v.published_at
        """, channel_ids)
        utc_now = datetime.now(timezone.utc)
        for row in cursor.fetchall():
            ch = channels[row[0]]
            if ch["latest_video"]:
                continue
            ch["latest_video"] = {
                "video_id": row[1],
                "title": row[2],
                "thumbnail_url": row[3],
                "published_at": row[4],
                "view_count": row[5],
                "like_count": row[6],
                "comment_count": row[7],
                "is_short": row[8],
                "duration_seconds": row[9]
            }
            ch["days_since_upload"] = _days_since(row[4], utc_now)

    # 6. 합계
    channel_list = list(channels.values())
    summary = _build_summary(channel_list)
    last_refresh_at = max(
        (ch["stats_updated_at"] for ch in channel_list if ch["stats_updated_at"]),
        default=None
    )

    return {
        "generated_at": now.isoformat(),
        "period_days": days,
        "last_refresh_at": last_refresh_at,
        "summary": summary,
        "channels": channel_list
    }


def _days_since(published_at: Optional[str], utc_now: datetime) -> Optional[float]:
    """YouTube ISO 시각(...Z)으로부터 경과 일수"""
    if not published_at:
        return None
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return round((utc_now - published).total_seconds() / 86400, 2)
    except ValueError:
        return None


def _empty_summary() -> Dict:
    return {
        "channel_count": 0,
        "subscriber_count": 0,
        "view_count": 0,
        "video_count": 0,
        "subscriber_delta": None,
        "view_delta": None,
        "video_delta": None,
        "channels_with_baseline": 0,
        "uploads_in_period": 0,
        "period_upload_views": 0,
        "channels_without_upload": 0,
        "channels_never_refreshed": 0,
        "channels_subscriber_hidden": 0
    }


def _build_summary(channel_list: List[Dict]) -> Dict:
    summary = _empty_summary()
    summary["channel_count"] = len(channel_list)
    summary["channels_subscriber_hidden"] = sum(1 for ch in channel_list if ch["subscriber_hidden"])

    subs_delta = views_delta = videos_delta = 0
    with_baseline = 0

    for ch in channel_list:
        summary["subscriber_count"] += ch["subscriber_count"] or 0
        summary["view_count"] += ch["view_count"] or 0
        summary["video_count"] += ch["video_count"] or 0
        summary["uploads_in_period"] += ch["uploads_in_period"]
        summary["period_upload_views"] += ch["period_upload_views"]
        if ch["uploads_in_period"] == 0:
            summary["channels_without_upload"] += 1
        if not ch["stats_updated_at"]:
            summary["channels_never_refreshed"] += 1

        d = ch["delta"]
        if d["subscriber_count"] is not None:
            with_baseline += 1
            subs_delta += d["subscriber_count"]
            views_delta += d["view_count"] or 0
            videos_delta += d["video_count"] or 0

    summary["channels_with_baseline"] = with_baseline
    if with_baseline > 0:
        summary["subscriber_delta"] = subs_delta
        summary["view_delta"] = views_delta
        summary["video_delta"] = videos_delta

    return summary


@router.get("/channels/{channel_id}/videos")
def get_channel_videos(channel_id: str, limit: int = Query(20, ge=1, le=100)):
    """채널의 최근 영상 목록 (DB에 수집된 것만, API 호출 없음)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT video_id, title, thumbnail_url, published_at, view_count,
                   like_count, comment_count, duration_seconds, is_short
            FROM videos
            WHERE channel_id = ?
            ORDER BY published_at DESC
            LIMIT ?
        """, (channel_id, limit))
        rows = cursor.fetchall()

    videos = [
        {
            "video_id": row[0],
            "title": row[1],
            "thumbnail_url": row[2],
            "published_at": row[3],
            "view_count": row[4],
            "like_count": row[5],
            "comment_count": row[6],
            "duration_seconds": row[7],
            "is_short": row[8]
        }
        for row in rows
    ]
    return {"channel_id": channel_id, "videos": videos, "total": len(videos)}


@router.get("/channels/{channel_id}/history")
def get_channel_history(channel_id: str, days: int = Query(30, ge=1, le=365)):
    """채널 통계 스냅샷 이력"""
    start = (datetime.now() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM channels WHERE channel_id = ? LIMIT 1", (channel_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        cursor.execute("""
            SELECT captured_at, subscriber_count, view_count, video_count
            FROM channel_snapshots
            WHERE channel_id = ? AND captured_at >= ?
            ORDER BY captured_at ASC
        """, (channel_id, start))
        rows = cursor.fetchall()

    history = [
        {
            "captured_at": row[0],
            "subscriber_count": row[1],
            "view_count": row[2],
            "video_count": row[3]
        }
        for row in rows
    ]
    return {"channel_id": channel_id, "days": days, "history": history, "total": len(history)}

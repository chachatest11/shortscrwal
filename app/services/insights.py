"""대시보드 데이터: 요약, 증감, 추이, 인사이트(업로드 공백·감소·급상승·마일스톤)"""
from typing import Dict, List, Optional, Tuple

from .. import config
from ..db import get_settings, typed_settings
from ..util import utc_now, ago_iso, local_day, days_since, median, parse_iso

MILESTONES = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000, 100_000_000]


def _delta(current, baseline):
    if current is None or baseline is None:
        return None
    return current - baseline


def next_milestone(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    for m in MILESTONES:
        if value < m:
            return m
    return None


def views_per_day(view_count: Optional[int], published_at: Optional[str], now=None) -> Optional[float]:
    """하루 평균 조회수. 게시 후 1일이 안 된 영상은 1일로 나눠 초기 급증이 부풀려지지 않게 한다."""
    age = days_since(published_at, now)
    if view_count is None or age is None:
        return None
    return round(view_count / max(age, 1.0), 1)


def channel_where(group_id: int, include_inactive: bool, alias: str = "c") -> Tuple[str, list]:
    conditions = []
    params: list = []
    if not include_inactive:
        conditions.append(f"{alias}.is_active = 1")
    if group_id and group_id > 0:
        conditions.append(f"{alias}.group_id = ?")
        params.append(group_id)
    return (" AND ".join(conditions) if conditions else "1 = 1"), params


def load_baselines(conn, channel_ids: List[int], period_start: str) -> Dict[int, dict]:
    """기간 시작 시점 직전 스냅샷. 없으면 가장 오래된 스냅샷(부분 기간)."""
    if not channel_ids:
        return {}
    placeholders = ",".join("?" * len(channel_ids))
    baselines: Dict[int, dict] = {}
    rows = conn.execute(
        f"""SELECT s.channel_id, s.subscriber_count, s.view_count, s.video_count, s.captured_at
            FROM snapshots s
            JOIN (SELECT channel_id, MAX(captured_at) AS captured_at FROM snapshots
                  WHERE captured_at <= ? AND channel_id IN ({placeholders}) GROUP BY channel_id) m
              ON m.channel_id = s.channel_id AND m.captured_at = s.captured_at""",
        (period_start, *channel_ids),
    ).fetchall()
    for row in rows:
        baselines[row["channel_id"]] = {**dict(row), "partial": False}

    missing = [cid for cid in channel_ids if cid not in baselines]
    if missing:
        placeholders = ",".join("?" * len(missing))
        rows = conn.execute(
            f"""SELECT s.channel_id, s.subscriber_count, s.view_count, s.video_count, s.captured_at
                FROM snapshots s
                JOIN (SELECT channel_id, MIN(captured_at) AS captured_at FROM snapshots
                      WHERE channel_id IN ({placeholders}) GROUP BY channel_id) m
                  ON m.channel_id = s.channel_id AND m.captured_at = s.captured_at""",
            missing,
        ).fetchall()
        for row in rows:
            baselines[row["channel_id"]] = {**dict(row), "partial": True}
    return baselines


def load_daily_series(conn, channel_ids: List[int], start: str) -> Dict[int, List[dict]]:
    """채널별 로컬 날짜별 마지막 스냅샷 (오래된 순)"""
    series: Dict[int, List[dict]] = {cid: [] for cid in channel_ids}
    if not channel_ids:
        return series
    placeholders = ",".join("?" * len(channel_ids))
    rows = conn.execute(
        f"""SELECT channel_id, subscriber_count, view_count, video_count, captured_at
            FROM snapshots WHERE captured_at >= ? AND channel_id IN ({placeholders})
            ORDER BY channel_id, captured_at""",
        (start, *channel_ids),
    ).fetchall()
    last_by_day: Dict[Tuple[int, str], dict] = {}
    for row in rows:
        last_by_day[(row["channel_id"], local_day(row["captured_at"]))] = dict(row)
    for (cid, day), row in sorted(last_by_day.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        row["day"] = day
        series[cid].append(row)
    return series


def channel_dict(row, group_name: Optional[str] = None) -> dict:
    return {
        "id": row["id"],
        "youtube_id": row["youtube_id"],
        "title": row["title"] or row["youtube_id"],
        "handle": row["handle"],
        "thumbnail_url": row["thumbnail_url"],
        "country": row["country"],
        "published_at": row["published_at"],
        "group_id": row["group_id"],
        "group_name": group_name if group_name is not None else row["group_name"] if "group_name" in row.keys() else None,
        "is_active": row["is_active"],
        "memo": row["memo"],
        "subscriber_count": row["subscriber_count"],
        "subscriber_hidden": bool(row["subscriber_hidden"]),
        "view_count": row["view_count"],
        "video_count": row["video_count"],
        "stats_updated_at": row["stats_updated_at"],
        "created_at": row["created_at"],
    }


def video_dict(row, now=None) -> dict:
    vpd = views_per_day(row["view_count"], row["published_at"], now)
    delta = None
    if row["view_count_prev"] is not None and row["view_count"] is not None:
        delta = row["view_count"] - row["view_count_prev"]
    return {
        "id": row["id"],
        "youtube_id": row["youtube_id"],
        "channel_id": row["channel_id"],
        "title": row["title"],
        "published_at": row["published_at"],
        "duration_seconds": row["duration_seconds"],
        "is_short": bool(row["is_short"]),
        "thumbnail_url": row["thumbnail_url"],
        "view_count": row["view_count"],
        "like_count": row["like_count"],
        "comment_count": row["comment_count"],
        "views_per_day": vpd,
        "view_delta": delta,
        "stats_prev_at": row["stats_prev_at"],
        "stats_updated_at": row["stats_updated_at"],
        "days_since_published": days_since(row["published_at"], now),
    }


MIN_AGE_HOURS_FOR_BASELINE = 24  # 급상승 판정에 쓰는 영상은 게시 후 하루 이상 지난 것만


def channel_medians(conn, channel_ids: List[int], window_days: int, now=None) -> Dict[int, Optional[float]]:
    """채널별 '조회수/일' 중앙값 (게시 후 하루 이상 지난 영상, 최근 window_days 일, 표본 3개 이상)"""
    if not channel_ids:
        return {}
    now = now or utc_now()
    placeholders = ",".join("?" * len(channel_ids))
    rows = conn.execute(
        f"""SELECT channel_id, view_count, published_at FROM videos
            WHERE channel_id IN ({placeholders}) AND published_at >= ? AND published_at <= ?""",
        (*channel_ids, ago_iso(days=window_days, now=now), ago_iso(hours=MIN_AGE_HOURS_FOR_BASELINE, now=now)),
    ).fetchall()
    values: Dict[int, List[float]] = {}
    for row in rows:
        vpd = views_per_day(row["view_count"], row["published_at"], now)
        if vpd is not None:
            values.setdefault(row["channel_id"], []).append(vpd)
    return {cid: (round(median(v)) if len(v) >= 3 else None) for cid, v in values.items()}


def build_overview(conn, group_id: int = 0, days: int = 7, include_inactive: bool = False) -> dict:
    now = utc_now()
    settings = typed_settings(get_settings(conn))
    period_start = ago_iso(days=days, now=now)
    where, params = channel_where(group_id, include_inactive)

    rows = conn.execute(
        f"""SELECT c.*, g.name AS group_name FROM channels c JOIN groups g ON g.id = c.group_id
            WHERE {where} ORDER BY c.subscriber_count DESC, c.id ASC""",
        params,
    ).fetchall()
    channels = [channel_dict(row) for row in rows]
    ids = [c["id"] for c in channels]
    by_id = {c["id"]: c for c in channels}

    empty_insights = {"stale": [], "declining": [], "rising": [], "milestones": [], "uploaded_today": []}
    if not ids:
        return {
            "generated_at": now.isoformat(timespec="seconds"),
            "period_days": days,
            "last_refresh_at": None,
            "summary": _summary([], days),
            "channels": [],
            "insights": empty_insights,
            "latest_videos": [],
        }

    placeholders = ",".join("?" * len(ids))

    # 증감
    baselines = load_baselines(conn, ids, period_start)
    for cid, base in baselines.items():
        ch = by_id[cid]
        if base["partial"] and base["captured_at"] == ch["stats_updated_at"]:
            ch["delta"] = {"subscriber_count": None, "view_count": None, "video_count": None,
                           "baseline_at": None, "partial": True}
            continue
        ch["delta"] = {
            "subscriber_count": _delta(ch["subscriber_count"], base["subscriber_count"]),
            "view_count": _delta(ch["view_count"], base["view_count"]),
            "video_count": _delta(ch["video_count"], base["video_count"]),
            "baseline_at": base["captured_at"],
            "partial": base["partial"],
        }
    for ch in channels:
        ch.setdefault("delta", {"subscriber_count": None, "view_count": None, "video_count": None,
                                "baseline_at": None, "partial": False})

    # 추이
    series = load_daily_series(conn, ids, ago_iso(days=config.SPARKLINE_DAYS, now=now))
    for cid, points in series.items():
        by_id[cid]["sparkline"] = [
            {"day": p["day"], "subscriber_count": p["subscriber_count"], "view_count": p["view_count"]} for p in points
        ]

    # 기간 내 업로드
    rows = conn.execute(
        f"""SELECT channel_id, COUNT(*) AS n, COALESCE(SUM(view_count), 0) AS views
            FROM videos WHERE channel_id IN ({placeholders}) AND published_at >= ? GROUP BY channel_id""",
        (*ids, period_start),
    ).fetchall()
    for ch in channels:
        ch["uploads_in_period"] = 0
        ch["period_upload_views"] = 0
    for row in rows:
        by_id[row["channel_id"]]["uploads_in_period"] = row["n"]
        by_id[row["channel_id"]]["period_upload_views"] = row["views"]

    # 최신 영상
    rows = conn.execute(
        f"""SELECT v.* FROM videos v
            JOIN (SELECT channel_id, MAX(published_at) AS published_at FROM videos
                  WHERE channel_id IN ({placeholders}) GROUP BY channel_id) m
              ON m.channel_id = v.channel_id AND m.published_at = v.published_at""",
        ids,
    ).fetchall()
    for ch in channels:
        ch["latest_video"] = None
        ch["days_since_upload"] = None
    for row in rows:
        ch = by_id[row["channel_id"]]
        if ch["latest_video"] is None:
            ch["latest_video"] = video_dict(row, now)
            ch["days_since_upload"] = ch["latest_video"]["days_since_published"]

    # 최근 업로드 피드
    rows = conn.execute(
        f"""SELECT v.*, c.title AS channel_title, c.thumbnail_url AS channel_thumbnail
            FROM videos v JOIN channels c ON c.id = v.channel_id
            WHERE v.channel_id IN ({placeholders}) ORDER BY v.published_at DESC LIMIT 8""",
        ids,
    ).fetchall()
    latest_videos = []
    for row in rows:
        item = video_dict(row, now)
        item["channel_title"] = row["channel_title"]
        item["channel_thumbnail"] = row["channel_thumbnail"]
        latest_videos.append(item)

    insights = build_insights(conn, channels, ids, settings, now)
    summary = _summary(channels, days)
    last_refresh = max((c["stats_updated_at"] for c in channels if c["stats_updated_at"]), default=None)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "period_days": days,
        "last_refresh_at": last_refresh,
        "summary": summary,
        "channels": channels,
        "insights": insights,
        "latest_videos": latest_videos,
    }


def _summary(channels: List[dict], days: int) -> dict:
    summary = {
        "channel_count": len(channels),
        "subscriber_count": 0, "view_count": 0, "video_count": 0,
        "subscriber_delta": None, "view_delta": None, "video_delta": None,
        "channels_with_baseline": 0,
        "uploads_in_period": 0, "period_upload_views": 0,
        "channels_without_upload": 0, "channels_never_refreshed": 0, "channels_subscriber_hidden": 0,
        "period_days": days,
    }
    sd = vd = nd = 0
    for ch in channels:
        summary["subscriber_count"] += ch["subscriber_count"] or 0
        summary["view_count"] += ch["view_count"] or 0
        summary["video_count"] += ch["video_count"] or 0
        summary["uploads_in_period"] += ch.get("uploads_in_period", 0)
        summary["period_upload_views"] += ch.get("period_upload_views", 0)
        if ch.get("uploads_in_period", 0) == 0:
            summary["channels_without_upload"] += 1
        if not ch["stats_updated_at"]:
            summary["channels_never_refreshed"] += 1
        if ch["subscriber_hidden"]:
            summary["channels_subscriber_hidden"] += 1
        d = ch.get("delta") or {}
        if d.get("subscriber_count") is not None:
            summary["channels_with_baseline"] += 1
            sd += d["subscriber_count"]
            vd += d.get("view_count") or 0
            nd += d.get("video_count") or 0
    if summary["channels_with_baseline"]:
        summary["subscriber_delta"], summary["view_delta"], summary["video_delta"] = sd, vd, nd
    return summary


def build_insights(conn, channels: List[dict], ids: List[int], settings: dict, now) -> dict:
    stale_days = settings["stale_days"]
    multiplier = settings["outlier_multiplier"]
    window_days = settings["video_stats_window_days"]
    by_id = {c["id"]: c for c in channels}

    stale, declining, milestones, uploaded_today = [], [], [], []
    for ch in channels:
        d = ch.get("days_since_upload")
        if ch["stats_updated_at"]:
            if d is None:
                stale.append({"channel_id": ch["id"], "title": ch["title"], "thumbnail_url": ch["thumbnail_url"],
                              "days_since_upload": None, "has_videos": False})
            elif d >= stale_days:
                stale.append({"channel_id": ch["id"], "title": ch["title"], "thumbnail_url": ch["thumbnail_url"],
                              "days_since_upload": d, "has_videos": True})
        if d is not None and d < 1 and ch.get("latest_video"):
            uploaded_today.append({"channel_id": ch["id"], "title": ch["title"], "thumbnail_url": ch["thumbnail_url"],
                                   "video_title": ch["latest_video"]["title"],
                                   "video_youtube_id": ch["latest_video"]["youtube_id"],
                                   "published_at": ch["latest_video"]["published_at"],
                                   "view_count": ch["latest_video"]["view_count"]})
        delta = (ch.get("delta") or {}).get("subscriber_count")
        if delta is not None and delta < 0:
            declining.append({"channel_id": ch["id"], "title": ch["title"], "thumbnail_url": ch["thumbnail_url"],
                              "subscriber_delta": delta, "subscriber_count": ch["subscriber_count"]})
        if not ch["subscriber_hidden"] and ch["subscriber_count"]:
            subs = ch["subscriber_count"]
            base = (ch.get("delta") or {})
            baseline_subs = None
            if base.get("subscriber_count") is not None:
                baseline_subs = subs - base["subscriber_count"]
            achieved = None
            if baseline_subs is not None:
                for m in MILESTONES:
                    if baseline_subs < m <= subs:
                        achieved = m
            nxt = next_milestone(subs)
            if achieved:
                milestones.append({"channel_id": ch["id"], "title": ch["title"], "thumbnail_url": ch["thumbnail_url"],
                                   "subscriber_count": subs, "milestone": achieved, "remaining": 0, "achieved": True})
            elif nxt and subs >= nxt * 0.95:
                milestones.append({"channel_id": ch["id"], "title": ch["title"], "thumbnail_url": ch["thumbnail_url"],
                                   "subscriber_count": subs, "milestone": nxt, "remaining": nxt - subs, "achieved": False})

    stale.sort(key=lambda x: -(x["days_since_upload"] or 10_000))
    declining.sort(key=lambda x: x["subscriber_delta"])
    milestones.sort(key=lambda x: (not x["achieved"], x["remaining"]))

    # 급상승: (a) 채널 평소 대비 배수, (b) 최근 갱신 간 증가
    rising: List[dict] = []
    seen = set()
    medians = channel_medians(conn, ids, window_days, now)
    if ids:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""SELECT * FROM videos WHERE channel_id IN ({placeholders}) AND published_at >= ? AND published_at <= ?""",
            (*ids, ago_iso(days=window_days, now=now), ago_iso(hours=MIN_AGE_HOURS_FOR_BASELINE, now=now)),
        ).fetchall()
        candidates = []
        for row in rows:
            med = medians.get(row["channel_id"])
            if not med:
                continue
            item = video_dict(row, now)
            if item["views_per_day"] is None:
                continue
            ratio = item["views_per_day"] / med
            if ratio >= multiplier:
                item["ratio"] = round(ratio, 2)
                item["reason"] = "baseline"
                candidates.append(item)
        candidates.sort(key=lambda x: -x["ratio"])
        for item in candidates[:5]:
            item["channel_title"] = by_id[item["channel_id"]]["title"]
            rising.append(item)
            seen.add(item["youtube_id"])

        rows = conn.execute(
            f"""SELECT * FROM videos WHERE channel_id IN ({placeholders})
                AND view_count_prev IS NOT NULL AND view_count > view_count_prev
                ORDER BY (view_count - view_count_prev) DESC LIMIT 10""",
            ids,
        ).fetchall()
        added = 0
        for row in rows:
            if row["youtube_id"] in seen or added >= 5:
                continue
            item = video_dict(row, now)
            med = medians.get(row["channel_id"])
            item["ratio"] = round(item["views_per_day"] / med, 2) if med and item["views_per_day"] else None
            item["reason"] = "delta"
            item["channel_title"] = by_id[item["channel_id"]]["title"]
            rising.append(item)
            seen.add(row["youtube_id"])
            added += 1

    return {"stale": stale, "declining": declining, "rising": rising,
            "milestones": milestones, "uploaded_today": uploaded_today}


def channel_history(conn, channel_id: int, days: int) -> List[dict]:
    """일별 스냅샷 + 전일 대비 증감"""
    series = load_daily_series(conn, [channel_id], ago_iso(days=days + 1))[channel_id]
    out = []
    prev = None
    for point in series:
        item = {
            "day": point["day"],
            "captured_at": point["captured_at"],
            "subscriber_count": point["subscriber_count"],
            "view_count": point["view_count"],
            "video_count": point["video_count"],
            "subscriber_delta": _delta(point["subscriber_count"], prev["subscriber_count"]) if prev else None,
            "view_delta": _delta(point["view_count"], prev["view_count"]) if prev else None,
            "video_delta": _delta(point["video_count"], prev["video_count"]) if prev else None,
        }
        out.append(item)
        prev = point
    # days+1 일치를 가져와 첫날 증감을 계산했으므로 요청한 일수만 돌려준다
    return out[-days:] if len(out) > days else out

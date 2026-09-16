"""갱신 엔진: 채널 통계 → 스냅샷 → 최근 영상 수집. 진행률과 실행 기록을 남긴다."""
import threading
import traceback
from typing import Dict, List, Optional

from .. import config
from ..db import connect, get_settings, typed_settings
from ..util import utc_now, utc_now_iso, to_iso, ago_iso, local_day, quota_date, parse_iso
from .youtube import KeyPool, YouTubeClient, YouTubeError, AllKeysExhausted


class RefreshAlreadyRunning(Exception):
    pass


class RefreshState:
    """현재 실행 상태 (진행률 표시용, 스레드 안전)"""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.running = False
            self.run_id = None
            self.phase = None
            self.done = 0
            self.total = 0
            self.message = ""
            self.started_at = None
            self.scope = None

    def start(self, run_id: int, scope: str):
        with self._lock:
            self.running = True
            self.run_id = run_id
            self.phase = "prepare"
            self.done = 0
            self.total = 0
            self.message = "준비 중"
            self.started_at = utc_now_iso()
            self.scope = scope

    def update(self, phase: Optional[str] = None, done: Optional[int] = None,
               total: Optional[int] = None, message: Optional[str] = None):
        with self._lock:
            if phase is not None:
                self.phase = phase
            if done is not None:
                self.done = done
            if total is not None:
                self.total = total
            if message is not None:
                self.message = message

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "run_id": self.run_id,
                "phase": self.phase,
                "done": self.done,
                "total": self.total,
                "message": self.message,
                "started_at": self.started_at,
                "scope": self.scope,
            }


STATE = RefreshState()
_RUN_LOCK = threading.Lock()


def load_key_rows(conn) -> List[dict]:
    """활성 키 로드. 쿼터 날짜가 바뀌었으면 사용량/초과 표시를 초기화한다."""
    today = quota_date()
    rows = conn.execute("SELECT * FROM api_keys ORDER BY id ASC").fetchall()
    keys = []
    for row in rows:
        key = dict(row)
        if key["used_date"] != today:
            conn.execute(
                "UPDATE api_keys SET used_today = 0, used_date = ?, quota_exceeded = 0, quota_exceeded_at = NULL WHERE id = ?",
                (today, key["id"]),
            )
            key["used_today"] = 0
            key["used_date"] = today
            key["quota_exceeded"] = 0
        keys.append(key)
    return keys


def persist_key_usage(pool: KeyPool) -> None:
    """키별 사용량·쿼터 초과 상태 저장"""
    now = utc_now_iso()
    today = quota_date()
    with connect() as conn:
        for key_id, used in pool.usage.items():
            if used <= 0 and key_id not in pool.exhausted:
                continue
            conn.execute(
                """UPDATE api_keys
                   SET used_today = CASE WHEN used_date = ? THEN used_today + ? ELSE ? END,
                       used_date = ?, last_used_at = ?
                   WHERE id = ?""",
                (today, used, used, today, now, key_id),
            )
        for key_id in pool.exhausted:
            conn.execute(
                "UPDATE api_keys SET quota_exceeded = 1, quota_exceeded_at = ? WHERE id = ?",
                (now, key_id),
            )


def make_client(conn) -> YouTubeClient:
    """라우터(채널 추가 등)에서 쓰는 클라이언트"""
    keys = load_key_rows(conn)
    pool = KeyPool(keys)
    return YouTubeClient(pool)


def select_target_channels(conn, scope: str, group_id: Optional[int], channel_id: Optional[int]) -> List[dict]:
    sql = "SELECT * FROM channels WHERE 1 = 1"
    params: list = []
    if scope == "channel" and channel_id:
        sql += " AND id = ?"
        params.append(channel_id)
    else:
        sql += " AND is_active = 1"
        if scope == "group" and group_id:
            sql += " AND group_id = ?"
            params.append(group_id)
    sql += " ORDER BY id ASC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def compact_snapshots(conn) -> int:
    """오래된 스냅샷은 채널별·로컬 날짜별 마지막 1개만 남긴다."""
    cutoff = ago_iso(days=config.SNAPSHOT_KEEP_ALL_DAYS)
    rows = conn.execute(
        "SELECT id, channel_id, captured_at FROM snapshots WHERE captured_at < ? ORDER BY channel_id, captured_at",
        (cutoff,),
    ).fetchall()
    keep: Dict[tuple, int] = {}
    for row in rows:
        keep[(row["channel_id"], local_day(row["captured_at"]))] = row["id"]  # 마지막 것이 남음
    keep_ids = set(keep.values())
    delete_ids = [row["id"] for row in rows if row["id"] not in keep_ids]
    for start in range(0, len(delete_ids), 500):
        batch = delete_ids[start:start + 500]
        conn.execute(f"DELETE FROM snapshots WHERE id IN ({','.join('?' * len(batch))})", batch)
    return len(delete_ids)


def upsert_video(conn, channel_db_id: int, video: dict, now: str) -> None:
    existing = conn.execute(
        "SELECT id, view_count, stats_updated_at FROM videos WHERE youtube_id = ?", (video["youtube_id"],)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE videos
               SET channel_id = ?, title = ?, published_at = ?, duration_seconds = ?, is_short = ?,
                   thumbnail_url = ?, view_count = ?, like_count = ?, comment_count = ?,
                   view_count_prev = ?, stats_prev_at = ?, stats_updated_at = ?
               WHERE id = ?""",
            (
                channel_db_id, video["title"], video["published_at"], video["duration_seconds"], video["is_short"],
                video["thumbnail_url"], video["view_count"], video["like_count"], video["comment_count"],
                existing["view_count"], existing["stats_updated_at"], now, existing["id"],
            ),
        )
    else:
        conn.execute(
            """INSERT INTO videos (channel_id, youtube_id, title, published_at, duration_seconds, is_short,
                                   thumbnail_url, view_count, like_count, comment_count,
                                   view_count_prev, stats_prev_at, stats_updated_at, first_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
            (
                channel_db_id, video["youtube_id"], video["title"], video["published_at"], video["duration_seconds"],
                video["is_short"], video["thumbnail_url"], video["view_count"], video["like_count"],
                video["comment_count"], now, now,
            ),
        )


def apply_channel_info(conn, channel_db_id: int, info: dict, now: str) -> None:
    conn.execute(
        """UPDATE channels
           SET title = ?, handle = ?, description = ?, thumbnail_url = ?, country = ?, published_at = ?,
               uploads_playlist_id = ?, subscriber_count = ?, subscriber_hidden = ?, view_count = ?,
               video_count = ?, stats_updated_at = ?, updated_at = ?
           WHERE id = ?""",
        (
            info["title"], info.get("handle"), info.get("description"), info.get("thumbnail_url"),
            info.get("country"), info.get("published_at"), info.get("uploads_playlist_id"),
            info["subscriber_count"], info["subscriber_hidden"], info["view_count"], info["video_count"],
            now, now, channel_db_id,
        ),
    )
    conn.execute(
        "INSERT INTO snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?, ?, ?, ?, ?)",
        (channel_db_id, info["subscriber_count"], info["view_count"], info["video_count"], now),
    )


def is_running() -> bool:
    return STATE.snapshot()["running"]


def run_refresh(scope: str = "all", group_id: Optional[int] = None, channel_id: Optional[int] = None,
                trigger: str = "manual") -> dict:
    """갱신 실행 (동기). 실행 중이면 RefreshAlreadyRunning."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise RefreshAlreadyRunning("이미 갱신이 진행 중입니다")

    started_at = utc_now_iso()
    errors: List[dict] = []
    result = {
        "run_id": None, "status": "failed", "scope": scope, "trigger": trigger,
        "started_at": started_at, "finished_at": None,
        "channels_total": 0, "channels_updated": 0, "videos_updated": 0,
        "quota_used": 0, "errors": errors, "message": "",
    }
    pool: Optional[KeyPool] = None

    try:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO refresh_runs (started_at, status, scope, trigger) VALUES (?, 'running', ?, ?)",
                (started_at, scope, trigger),
            )
            result["run_id"] = cur.lastrowid
            settings = typed_settings(get_settings(conn))
            keys = load_key_rows(conn)
            channels = select_target_channels(conn, scope, group_id, channel_id)
        STATE.start(result["run_id"], scope)
        result["channels_total"] = len(channels)

        pool = KeyPool(keys)
        if not pool.keys:
            result["message"] = "사용 가능한 API 키가 없습니다. 설정에서 키를 추가하거나 쿼터 상태를 확인하세요."
            errors.append({"scope": "global", "error": result["message"]})
            return result
        if not channels:
            result["status"] = "success"
            result["message"] = "갱신할 활성 채널이 없습니다"
            return result

        client = YouTubeClient(pool)
        now = utc_now_iso()

        # ---------- 1. 채널 통계 ----------
        STATE.update(phase="channels", done=0, total=len(channels), message="채널 통계 갱신 중")
        by_youtube_id = {c["youtube_id"]: c for c in channels}
        infos: Dict[str, dict] = {}
        quota_exhausted = False
        try:
            infos = client.channels_by_ids(list(by_youtube_id.keys()))
        except AllKeysExhausted as exc:
            quota_exhausted = True
            errors.append({"scope": "global", "error": str(exc)})
        except YouTubeError as exc:
            errors.append({"scope": "global", "error": f"채널 통계 조회 실패: {exc}"})

        updated = 0
        with connect() as conn:
            for yt_id, channel in by_youtube_id.items():
                info = infos.get(yt_id)
                if not info:
                    if infos:  # 응답은 왔는데 이 채널만 없음
                        errors.append({"scope": "channel", "channel_id": channel["id"], "title": channel["title"],
                                       "error": "YouTube에서 채널을 찾을 수 없습니다 (삭제/정지/비공개)"})
                    continue
                apply_channel_info(conn, channel["id"], info, now)
                updated += 1
            compact_snapshots(conn)
        result["channels_updated"] = updated
        STATE.update(done=len(channels))

        if quota_exhausted or not infos:
            return result

        # ---------- 2. 최근 업로드 영상 ID ----------
        max_videos = settings["max_videos_per_channel"]
        STATE.update(phase="playlists", done=0, total=len(infos), message="최근 영상 목록 수집 중")
        pending: Dict[str, int] = {}  # video youtube_id -> channel db id
        for index, (yt_id, info) in enumerate(infos.items(), start=1):
            channel = by_youtube_id[yt_id]
            playlist_id = info.get("uploads_playlist_id") or ("UU" + yt_id[2:] if yt_id.startswith("UC") else None)
            if playlist_id:
                try:
                    for video_id in client.playlist_video_ids(playlist_id, max_videos):
                        pending[video_id] = channel["id"]
                except AllKeysExhausted as exc:
                    quota_exhausted = True
                    errors.append({"scope": "global", "error": f"최근 영상 수집 중 쿼터 초과: {exc}"})
                    break
                except YouTubeError as exc:
                    errors.append({"scope": "channel", "channel_id": channel["id"], "title": info.get("title"),
                                   "error": f"최근 영상 목록 조회 실패: {exc}"})
            STATE.update(done=index)

        # ---------- 3. 영상 통계 (신규 + 재수집 대상 기간 내 기존 영상) ----------
        if not quota_exhausted:
            window_start = ago_iso(days=settings["video_stats_window_days"])
            with connect() as conn:
                placeholders = ",".join("?" * len(by_youtube_id))
                rows = conn.execute(
                    f"""SELECT v.youtube_id, v.channel_id FROM videos v
                        WHERE v.channel_id IN (SELECT id FROM channels WHERE youtube_id IN ({placeholders}))
                          AND v.published_at >= ?
                        ORDER BY v.published_at DESC LIMIT 2000""",
                    (*by_youtube_id.keys(), window_start),
                ).fetchall()
            for row in rows:
                pending.setdefault(row["youtube_id"], row["channel_id"])

            video_ids = list(pending.keys())
            STATE.update(phase="videos", done=0, total=len(video_ids), message="영상 통계 갱신 중")
            videos_updated = 0
            for start in range(0, len(video_ids), 50):
                batch = video_ids[start:start + 50]
                try:
                    details = client.videos_by_ids(batch, settings["shorts_max_seconds"])
                except AllKeysExhausted as exc:
                    quota_exhausted = True
                    errors.append({"scope": "global", "error": f"영상 통계 갱신 중 쿼터 초과: {exc}"})
                    break
                except YouTubeError as exc:
                    errors.append({"scope": "global", "error": f"영상 통계 조회 실패: {exc}"})
                    break
                stamp = utc_now_iso()
                with connect() as conn:
                    for video in details:
                        channel_db_id = pending.get(video["youtube_id"])
                        if channel_db_id is None:
                            # 채널 ID 로 다시 매핑
                            row = conn.execute("SELECT id FROM channels WHERE youtube_id = ?",
                                               (video["channel_youtube_id"],)).fetchone()
                            if not row:
                                continue
                            channel_db_id = row["id"]
                        upsert_video(conn, channel_db_id, video, stamp)
                        videos_updated += 1
                STATE.update(done=min(start + 50, len(video_ids)))
            result["videos_updated"] = videos_updated

        return result

    except Exception as exc:  # 예상치 못한 오류도 기록으로 남긴다
        errors.append({"scope": "global", "error": f"{exc.__class__.__name__}: {exc}"})
        traceback.print_exc()
        return result
    finally:
        finished_at = utc_now_iso()
        result["finished_at"] = finished_at
        if pool is not None:
            result["quota_used"] = pool.total_usage
            try:
                persist_key_usage(pool)
            except Exception:
                traceback.print_exc()

        if result["status"] != "success":
            if result["channels_updated"] > 0:
                result["status"] = "partial" if errors else "success"
            elif not errors:
                result["status"] = "success"
            else:
                result["status"] = "failed"
        if not result["message"]:
            if result["status"] == "success":
                result["message"] = f"채널 {result['channels_updated']}개, 영상 {result['videos_updated']}개 갱신"
            elif result["status"] == "partial":
                result["message"] = f"일부만 갱신됨 (채널 {result['channels_updated']}/{result['channels_total']}, 오류 {len(errors)}건)"
            else:
                result["message"] = errors[0]["error"] if errors else "갱신 실패"

        if result["run_id"] is not None:
            try:
                with connect() as conn:
                    conn.execute(
                        """UPDATE refresh_runs SET finished_at = ?, status = ?, channels_total = ?, channels_updated = ?,
                                  videos_updated = ?, quota_used = ?, error = ? WHERE id = ?""",
                        (finished_at, result["status"], result["channels_total"], result["channels_updated"],
                         result["videos_updated"], result["quota_used"],
                         "; ".join(e["error"] for e in errors)[:2000] if errors else None, result["run_id"]),
                    )
            except Exception:
                traceback.print_exc()
        STATE.reset()
        _RUN_LOCK.release()


def start_refresh_in_background(**kwargs) -> None:
    """스레드에서 갱신 실행 (실행 중이면 RefreshAlreadyRunning)"""
    if is_running() or _RUN_LOCK.locked():
        raise RefreshAlreadyRunning("이미 갱신이 진행 중입니다")
    thread = threading.Thread(target=run_refresh, kwargs=kwargs, daemon=True)
    thread.start()


def last_runs(conn, limit: int = 20) -> List[dict]:
    rows = conn.execute("SELECT * FROM refresh_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def last_successful_run(conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM refresh_runs WHERE status IN ('success', 'partial') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None

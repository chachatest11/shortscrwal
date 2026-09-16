"""자동 갱신 스케줄러: 1분마다 실행 시점을 확인하고 due 이면 백그라운드 갱신"""
import asyncio
import traceback
from datetime import timedelta
from typing import Optional

from ..db import connect, get_settings, typed_settings
from ..util import utc_now, parse_iso, to_iso
from . import refresh as refresh_service

CHECK_INTERVAL_SECONDS = 60


def compute_next_run(settings: dict, last_success_at: Optional[str], has_targets: bool, now=None):
    """다음 자동 갱신 예정 시각 (비활성/대상 없음이면 None, 한 번도 안 돌았으면 지금)"""
    if not settings.get("auto_refresh_enabled") or not has_targets:
        return None
    interval = timedelta(hours=int(settings.get("auto_refresh_interval_hours", 6)))
    last = parse_iso(last_success_at)
    if last is None:
        return now or utc_now()
    return last + interval


def is_due(settings: dict, last_success_at: Optional[str], has_targets: bool, now=None) -> bool:
    now = now or utc_now()
    nxt = compute_next_run(settings, last_success_at, has_targets, now)
    if nxt is None:
        return False
    return now >= nxt


def has_refresh_targets(conn) -> bool:
    keys = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1").fetchone()[0]
    channels = conn.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1").fetchone()[0]
    return keys > 0 and channels > 0


def next_run_iso(conn) -> Optional[str]:
    settings = typed_settings(get_settings(conn))
    last = refresh_service.last_successful_run(conn)
    nxt = compute_next_run(settings, last["started_at"] if last else None, has_refresh_targets(conn))
    return to_iso(nxt) if nxt else None


async def check_once() -> bool:
    if refresh_service.is_running():
        return False
    with connect() as conn:
        settings = typed_settings(get_settings(conn))
        last = refresh_service.last_successful_run(conn)
        # 실패한 실행이 반복되지 않도록 마지막 실행(성공/실패 무관) 기준으로 최소 간격을 둔다
        last_any = conn.execute("SELECT started_at FROM refresh_runs ORDER BY id DESC LIMIT 1").fetchone()
        due = is_due(settings, last["started_at"] if last else None, has_refresh_targets(conn))
    if not due:
        return False
    if last_any:
        last_dt = parse_iso(last_any["started_at"])
        if last_dt and (utc_now() - last_dt) < timedelta(minutes=10):
            return False
    await asyncio.to_thread(refresh_service.run_refresh, "all", None, None, "auto")
    return True


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(5)  # 서버 기동 직후 잠깐 대기
    while not stop_event.is_set():
        try:
            await check_once()
        except refresh_service.RefreshAlreadyRunning:
            pass
        except Exception:
            traceback.print_exc()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

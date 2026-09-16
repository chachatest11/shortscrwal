"""시간·숫자·문자열 유틸리티"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from . import config

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """UTC ISO 8601 문자열 (초 단위, +00:00). 문자열 비교로 시간 순서를 판단할 수 있게 형식을 고정한다."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def utc_now_iso() -> str:
    return to_iso(utc_now())


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """ISO 문자열 → aware datetime (naive 는 UTC 로 간주). 실패 시 None."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def normalize_iso(value: Optional[str]) -> Optional[str]:
    dt = parse_iso(value)
    return to_iso(dt) if dt else None


def local_day(value: Union[str, datetime, None]) -> Optional[str]:
    """서버(사용자 PC) 로컬 시간 기준 날짜 'YYYY-MM-DD'"""
    dt = parse_iso(value) if isinstance(value, str) else value
    if dt is None:
        return None
    return dt.astimezone().strftime("%Y-%m-%d")


def days_since(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    dt = parse_iso(value)
    if dt is None:
        return None
    now = now or utc_now()
    return round((now - dt).total_seconds() / 86400, 3)


def ago_iso(days: float = 0, hours: float = 0, now: Optional[datetime] = None) -> str:
    now = now or utc_now()
    return to_iso(now - timedelta(days=days, hours=hours))


def quota_date(now: Optional[datetime] = None) -> str:
    """YouTube 쿼터가 초기화되는 기준 날짜 (태평양 시간)"""
    now = now or utc_now()
    if ZoneInfo is not None:
        try:
            return now.astimezone(ZoneInfo(config.QUOTA_TIMEZONE)).strftime("%Y-%m-%d")
        except Exception:  # tz 데이터가 없는 환경
            pass
    return now.astimezone(UTC).strftime("%Y-%m-%d")


_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_duration(value: Optional[str]) -> int:
    """ISO 8601 기간(PT1H2M3S) → 초"""
    if not value:
        return 0
    match = _DURATION_RE.match(value.strip())
    if not match:
        return 0
    parts = {k: int(v) for k, v in match.groupdict().items() if v}
    return (
        parts.get("days", 0) * 86400
        + parts.get("hours", 0) * 3600
        + parts.get("minutes", 0) * 60
        + parts.get("seconds", 0)
    )


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return key[:2] + "…" + key[-2:]
    return key[:6] + "…" + key[-4:]


def to_int(value, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2

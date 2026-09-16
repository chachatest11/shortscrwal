"""경로와 상수 설정"""
import os
from pathlib import Path

APP_NAME = "ChannelBoard"
VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CHANNELBOARD_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("CHANNELBOARD_DB", DATA_DIR / "app.db"))
LEGACY_DB_PATH = Path(os.environ.get("CHANNELBOARD_LEGACY_DB", BASE_DIR / "app" / "database.db"))
STATIC_DIR = BASE_DIR / "app" / "static"

# 스케줄러(자동 갱신 루프) 사용 여부 - 테스트에서는 끈다
SCHEDULER_ENABLED = os.environ.get("CHANNELBOARD_SCHEDULER", "1") != "0"

# YouTube Data API v3 기본 일일 쿼터
DAILY_QUOTA = 10000
# 쿼터가 초기화되는 시간대 (태평양 시간 자정)
QUOTA_TIMEZONE = "America/Los_Angeles"

# 스냅샷 보관 정책: 최근 N일은 모두 보관, 이후는 채널별 하루 1개
SNAPSHOT_KEEP_ALL_DAYS = 2
# 추이 스파크라인 일수
SPARKLINE_DAYS = 30

DEFAULT_SETTINGS = {
    "auto_refresh_enabled": "1",
    "auto_refresh_interval_hours": "6",
    "max_videos_per_channel": "10",
    "video_stats_window_days": "90",
    "stale_days": "7",
    "outlier_multiplier": "1.75",
    "shorts_max_seconds": "180",
    "theme": "system",
}

SETTING_RULES = {
    "auto_refresh_enabled": {"type": "bool"},
    "auto_refresh_interval_hours": {"type": "int", "choices": [1, 3, 6, 12, 24]},
    "max_videos_per_channel": {"type": "int", "min": 1, "max": 50},
    "video_stats_window_days": {"type": "int", "min": 7, "max": 365},
    "stale_days": {"type": "int", "min": 1, "max": 90},
    "outlier_multiplier": {"type": "float", "min": 1.1, "max": 10},
    "shorts_max_seconds": {"type": "int", "min": 30, "max": 600},
    "theme": {"type": "str", "choices": ["system", "light", "dark"]},
}

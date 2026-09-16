"""SQLite 연결, 스키마, 설정 접근"""
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from . import config
from .util import utc_now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_id TEXT NOT NULL UNIQUE,
    title TEXT,
    handle TEXT,
    description TEXT,
    thumbnail_url TEXT,
    country TEXT,
    published_at TEXT,
    uploads_playlist_id TEXT,
    group_id INTEGER NOT NULL DEFAULT 1 REFERENCES groups(id),
    is_active INTEGER NOT NULL DEFAULT 1,
    memo TEXT NOT NULL DEFAULT '',
    subscriber_count INTEGER,
    subscriber_hidden INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER,
    video_count INTEGER,
    stats_updated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_channels_group ON channels(group_id);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    subscriber_count INTEGER,
    view_count INTEGER,
    video_count INTEGER,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_channel_captured ON snapshots(channel_id, captured_at);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    youtube_id TEXT NOT NULL UNIQUE,
    title TEXT,
    published_at TEXT,
    duration_seconds INTEGER,
    is_short INTEGER NOT NULL DEFAULT 0,
    thumbnail_url TEXT,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    view_count_prev INTEGER,
    stats_prev_at TEXT,
    stats_updated_at TEXT,
    first_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_videos_channel_published ON videos(channel_id, published_at);
CREATE INDEX IF NOT EXISTS idx_videos_published ON videos(published_at);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT NOT NULL UNIQUE,
    name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    quota_exceeded INTEGER NOT NULL DEFAULT 0,
    quota_exceeded_at TEXT,
    used_today INTEGER NOT NULL DEFAULT 0,
    used_date TEXT,
    last_used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    scope TEXT NOT NULL,
    trigger TEXT NOT NULL,
    channels_total INTEGER NOT NULL DEFAULT 0,
    channels_updated INTEGER NOT NULL DEFAULT 0,
    videos_updated INTEGER NOT NULL DEFAULT 0,
    quota_used INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""

DEFAULT_GROUP_ID = 1
DEFAULT_GROUP_NAME = "기본"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """연결 컨텍스트: 정상 종료 시 commit, 예외 시 rollback"""
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """테이블 생성, 기본 그룹/설정 삽입"""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        conn.executescript(SCHEMA)

        row = conn.execute("SELECT id FROM groups WHERE id = ?", (DEFAULT_GROUP_ID,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO groups (id, name, sort_order, created_at) VALUES (?, ?, 0, ?)",
                (DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME, utc_now_iso()),
            )

        for key, value in config.DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

        # 비정상 종료로 남은 '실행 중' 기록 정리
        conn.execute(
            "UPDATE refresh_runs SET status = 'failed', finished_at = ?, error = ? WHERE status = 'running'",
            (utc_now_iso(), "서버가 갱신 도중 종료되었습니다"),
        )


# ---------- 설정 ----------

def get_settings(conn: sqlite3.Connection) -> Dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    merged = dict(config.DEFAULT_SETTINGS)
    merged.update({row["key"]: row["value"] for row in rows})
    return merged


def get_setting(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return config.DEFAULT_SETTINGS.get(key, default)
    return row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def typed_settings(raw: Dict[str, str]) -> Dict[str, Any]:
    """문자열 설정 → 타입 변환"""
    out: Dict[str, Any] = {}
    for key, rule in config.SETTING_RULES.items():
        value = raw.get(key, config.DEFAULT_SETTINGS.get(key))
        kind = rule["type"]
        try:
            if kind == "bool":
                out[key] = str(value).lower() in ("1", "true", "yes", "on")
            elif kind == "int":
                out[key] = int(value)
            elif kind == "float":
                out[key] = float(value)
            else:
                out[key] = str(value)
        except (TypeError, ValueError):
            default = config.DEFAULT_SETTINGS[key]
            out[key] = {"bool": default == "1", "int": int(default) if kind == "int" else float(default)}.get(kind, default) if kind != "str" else default
    return out


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None

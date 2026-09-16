"""이전 버전(쇼츠 수집기, app/database.db)의 채널·카테고리·API 키·스냅샷 가져오기"""
import sqlite3
from pathlib import Path
from typing import Dict

from ..db import connect, DEFAULT_GROUP_ID, set_setting, get_setting
from ..util import utc_now_iso, normalize_iso


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def import_legacy(path: Path) -> Dict[str, int]:
    """레거시 DB 가져오기. 이미 있는 채널/키/그룹은 건너뛴다."""
    counts = {"groups": 0, "channels": 0, "api_keys": 0, "snapshots": 0}
    if not path.exists():
        return counts

    legacy = sqlite3.connect(str(path))
    legacy.row_factory = sqlite3.Row
    now = utc_now_iso()
    try:
        with connect() as conn:
            group_map: Dict[int, int] = {}
            if _table_exists(legacy, "categories"):
                cols = _columns(legacy, "categories")
                order_col = "display_order" if "display_order" in cols else "id"
                for row in legacy.execute(f"SELECT * FROM categories ORDER BY {order_col}, id").fetchall():
                    name = (row["name"] or "").strip() or f"그룹 {row['id']}"
                    existing = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
                    if existing:
                        group_map[row["id"]] = existing["id"]
                        continue
                    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM groups").fetchone()[0]
                    cur = conn.execute(
                        "INSERT INTO groups (name, sort_order, created_at) VALUES (?, ?, ?)",
                        (name, max_order + 1, now),
                    )
                    group_map[row["id"]] = cur.lastrowid
                    counts["groups"] += 1

            channel_map: Dict[str, int] = {}
            if _table_exists(legacy, "channels"):
                cols = _columns(legacy, "channels")
                for row in legacy.execute("SELECT * FROM channels ORDER BY id").fetchall():
                    yt_id = row["channel_id"]
                    if not yt_id or yt_id in channel_map:
                        continue
                    existing = conn.execute("SELECT id FROM channels WHERE youtube_id = ?", (yt_id,)).fetchone()
                    if existing:
                        channel_map[yt_id] = existing["id"]
                        continue
                    group_id = group_map.get(row["category_id"], DEFAULT_GROUP_ID) if "category_id" in cols else DEFAULT_GROUP_ID
                    cur = conn.execute(
                        """INSERT INTO channels (youtube_id, title, handle, description, thumbnail_url, country,
                                                 uploads_playlist_id, group_id, is_active, subscriber_count,
                                                 view_count, video_count, stats_updated_at, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            yt_id, row["title"], row["custom_url"] if "custom_url" in cols else None,
                            row["description"] if "description" in cols else None,
                            row["thumbnail_url"] if "thumbnail_url" in cols else None,
                            row["country"] if "country" in cols else None,
                            row["uploads_playlist_id"] if "uploads_playlist_id" in cols else None,
                            group_id, row["is_active"] if "is_active" in cols else 1,
                            row["subscriber_count"] if "subscriber_count" in cols else None,
                            row["view_count"] if "view_count" in cols else None,
                            row["video_count"] if "video_count" in cols else None,
                            normalize_iso(row["stats_updated_at"]) if "stats_updated_at" in cols else None,
                            now, now,
                        ),
                    )
                    channel_map[yt_id] = cur.lastrowid
                    counts["channels"] += 1

            if _table_exists(legacy, "api_keys"):
                for row in legacy.execute("SELECT * FROM api_keys ORDER BY priority, id").fetchall():
                    key = (row["api_key"] or "").strip()
                    if not key:
                        continue
                    existing = conn.execute("SELECT id FROM api_keys WHERE api_key = ?", (key,)).fetchone()
                    if existing:
                        continue
                    conn.execute(
                        "INSERT INTO api_keys (api_key, name, is_active, created_at) VALUES (?, ?, ?, ?)",
                        (key, row["name"], row["is_active"] if "is_active" in row.keys() else 1, now),
                    )
                    counts["api_keys"] += 1

            if _table_exists(legacy, "channel_snapshots"):
                for row in legacy.execute("SELECT * FROM channel_snapshots ORDER BY id").fetchall():
                    cid = channel_map.get(row["channel_id"])
                    captured = normalize_iso(row["captured_at"])
                    if not cid or not captured:
                        continue
                    conn.execute(
                        "INSERT INTO snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?, ?, ?, ?, ?)",
                        (cid, row["subscriber_count"], row["view_count"], row["video_count"], captured),
                    )
                    counts["snapshots"] += 1

            set_setting(conn, "legacy_imported_at", now)
    finally:
        legacy.close()
    return counts


def maybe_import_on_startup(path: Path) -> Dict[str, int]:
    """새 DB가 비어 있고 레거시 DB가 있으면 한 번만 가져온다."""
    if not path.exists():
        return {}
    with connect() as conn:
        if get_setting(conn, "legacy_imported_at"):
            return {}
        channels = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        keys = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        if channels or keys:
            return {}
    counts = import_legacy(path)
    print(f"[ChannelBoard] 이전 버전 데이터 가져오기: {counts}")
    return counts

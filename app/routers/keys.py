from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..db import connect
from ..util import utc_now_iso, mask_key, quota_date
from ..services.refresh import load_key_rows
from ..services.youtube import KeyPool, YouTubeClient, YouTubeError, AllKeysExhausted

router = APIRouter(prefix="/api/keys", tags=["keys"])

TEST_CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"  # Google Developers (키 검증용, 1 unit)


class KeyCreate(BaseModel):
    api_key: str
    name: Optional[str] = None
    verify: bool = True


class KeyPatch(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize(row: dict, today: str) -> dict:
    used = row["used_today"] if row.get("used_date") == today else 0
    return {
        "id": row["id"],
        "masked": mask_key(row["api_key"]),
        "name": row["name"],
        "is_active": bool(row["is_active"]),
        "quota_exceeded": bool(row["quota_exceeded"]),
        "quota_exceeded_at": row["quota_exceeded_at"],
        "used_today": used,
        "last_used_at": row["last_used_at"],
        "created_at": row["created_at"],
    }


def _test_key(api_key: str) -> dict:
    pool = KeyPool([{"id": 0, "api_key": api_key, "is_active": 1, "quota_exceeded": 0}])
    client = YouTubeClient(pool)
    try:
        client.request("channels", {"part": "id", "id": TEST_CHANNEL_ID})
        return {"ok": True}
    except AllKeysExhausted:
        return {"ok": False, "error": "이 키는 오늘 쿼터를 모두 사용했습니다"}
    except YouTubeError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("")
def list_keys():
    today = quota_date()
    with connect() as conn:
        rows = load_key_rows(conn)
    keys = [_serialize(r, today) for r in rows]
    return {"keys": keys, "used_today_total": sum(k["used_today"] for k in keys),
            "daily_quota_per_key": config.DAILY_QUOTA, "quota_date": today}


@router.post("")
def create_key(data: KeyCreate):
    api_key = data.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키를 입력하세요")
    if len(api_key) < 20 or " " in api_key:
        raise HTTPException(status_code=400, detail="API 키 형식이 올바르지 않습니다")
    verified = None
    if data.verify:
        verified = _test_key(api_key)
        if not verified["ok"]:
            raise HTTPException(status_code=400, detail=f"키 확인 실패: {verified['error']}")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM api_keys WHERE api_key = ?", (api_key,)).fetchone():
            raise HTTPException(status_code=400, detail="이미 등록된 API 키입니다")
        today = quota_date()
        cur = conn.execute(
            "INSERT INTO api_keys (api_key, name, used_today, used_date, created_at) VALUES (?, ?, ?, ?, ?)",
            (api_key, (data.name or "").strip() or None, 1 if data.verify else 0, today, utc_now_iso()),
        )
        row = dict(conn.execute("SELECT * FROM api_keys WHERE id = ?", (cur.lastrowid,)).fetchone())
    return {"key": _serialize(row, today), "verified": verified}


@router.post("/{key_id}/test")
def test_key(key_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
    result = _test_key(row["api_key"])
    with connect() as conn:
        today = quota_date()
        conn.execute(
            """UPDATE api_keys SET used_today = CASE WHEN used_date = ? THEN used_today + 1 ELSE 1 END,
                      used_date = ?, last_used_at = ? WHERE id = ?""",
            (today, today, utc_now_iso(), key_id),
        )
        if result["ok"]:
            conn.execute("UPDATE api_keys SET quota_exceeded = 0, quota_exceeded_at = NULL WHERE id = ?", (key_id,))
    return result


@router.patch("/{key_id}")
def patch_key(key_id: int, data: KeyPatch):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM api_keys WHERE id = ?", (key_id,)).fetchone():
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
        if data.name is not None:
            conn.execute("UPDATE api_keys SET name = ? WHERE id = ?", (data.name.strip() or None, key_id))
        if data.is_active is not None:
            conn.execute("UPDATE api_keys SET is_active = ? WHERE id = ?", (1 if data.is_active else 0, key_id))
        row = dict(conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone())
    return {"key": _serialize(row, quota_date())}


@router.post("/{key_id}/reset")
def reset_key(key_id: int):
    with connect() as conn:
        cur = conn.execute("UPDATE api_keys SET quota_exceeded = 0, quota_exceeded_at = NULL WHERE id = ?", (key_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
    return {"ok": True}


@router.delete("/{key_id}")
def delete_key(key_id: int):
    with connect() as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
    return {"ok": True}

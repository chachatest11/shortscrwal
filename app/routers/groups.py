from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connect, DEFAULT_GROUP_ID
from ..util import utc_now_iso

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupCreate(BaseModel):
    name: str


class GroupPatch(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class ReorderRequest(BaseModel):
    ids: List[int]


def _list(conn):
    rows = conn.execute(
        """SELECT g.*, COUNT(c.id) AS channel_count,
                  SUM(CASE WHEN c.is_active = 1 THEN 1 ELSE 0 END) AS active_count
           FROM groups g LEFT JOIN channels c ON c.group_id = g.id
           GROUP BY g.id ORDER BY g.sort_order ASC, g.id ASC"""
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "sort_order": r["sort_order"], "created_at": r["created_at"],
             "channel_count": r["channel_count"], "active_count": r["active_count"] or 0,
             "is_default": r["id"] == DEFAULT_GROUP_ID} for r in rows]


@router.get("")
def list_groups():
    with connect() as conn:
        return {"groups": _list(conn)}


@router.post("")
def create_group(data: GroupCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="그룹 이름을 입력하세요")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM groups WHERE name = ?", (name,)).fetchone():
            raise HTTPException(status_code=400, detail="이미 있는 그룹 이름입니다")
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM groups").fetchone()[0]
        cur = conn.execute("INSERT INTO groups (name, sort_order, created_at) VALUES (?, ?, ?)",
                           (name, max_order + 1, utc_now_iso()))
        group_id = cur.lastrowid
        return {"group": next(g for g in _list(conn) if g["id"] == group_id)}


@router.patch("/{group_id}")
def patch_group(group_id: int, data: GroupPatch):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
        if data.name is not None:
            name = data.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="그룹 이름을 입력하세요")
            dup = conn.execute("SELECT id FROM groups WHERE name = ? AND id != ?", (name, group_id)).fetchone()
            if dup:
                raise HTTPException(status_code=400, detail="이미 있는 그룹 이름입니다")
            conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
        if data.sort_order is not None:
            conn.execute("UPDATE groups SET sort_order = ? WHERE id = ?", (data.sort_order, group_id))
        return {"group": next(g for g in _list(conn) if g["id"] == group_id)}


@router.post("/reorder")
def reorder_groups(data: ReorderRequest):
    with connect() as conn:
        for order, group_id in enumerate(data.ids):
            conn.execute("UPDATE groups SET sort_order = ? WHERE id = ?", (order, group_id))
        return {"groups": _list(conn)}


@router.delete("/{group_id}")
def delete_group(group_id: int):
    if group_id == DEFAULT_GROUP_ID:
        raise HTTPException(status_code=400, detail="기본 그룹은 삭제할 수 없습니다")
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
        moved = conn.execute("UPDATE channels SET group_id = ?, updated_at = ? WHERE group_id = ?",
                             (DEFAULT_GROUP_ID, utc_now_iso(), group_id)).rowcount
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        return {"ok": True, "moved_channels": moved}

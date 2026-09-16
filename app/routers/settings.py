from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..db import connect, get_settings, typed_settings, set_setting
from ..services import refresh as refresh_service
from ..services import scheduler
from ..services.legacy_import import import_legacy

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdate(BaseModel):
    values: Dict[str, Any]


def _validate(key: str, value: Any) -> str:
    rule = config.SETTING_RULES.get(key)
    if rule is None:
        raise HTTPException(status_code=400, detail=f"알 수 없는 설정: {key}")
    kind = rule["type"]
    try:
        if kind == "bool":
            if isinstance(value, str):
                value = value.lower() in ("1", "true", "yes", "on")
            return "1" if bool(value) else "0"
        if kind == "int":
            number = int(value)
        elif kind == "float":
            number = float(value)
        else:
            text = str(value)
            if "choices" in rule and text not in rule["choices"]:
                raise HTTPException(status_code=400, detail=f"{key}: 허용되지 않는 값입니다")
            return text
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key}: 숫자여야 합니다")
    if "choices" in rule and number not in rule["choices"]:
        raise HTTPException(status_code=400, detail=f"{key}: {rule['choices']} 중 하나여야 합니다")
    if "min" in rule and number < rule["min"]:
        raise HTTPException(status_code=400, detail=f"{key}: 최소 {rule['min']}")
    if "max" in rule and number > rule["max"]:
        raise HTTPException(status_code=400, detail=f"{key}: 최대 {rule['max']}")
    return str(number)


def _info(conn) -> dict:
    counts = {
        "channels": conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0],
        "active_channels": conn.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1").fetchone()[0],
        "videos": conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
        "snapshots": conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
        "keys": conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0],
        "groups": conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0],
    }
    db_size = config.DB_PATH.stat().st_size if config.DB_PATH.exists() else 0
    return {
        "app_name": config.APP_NAME,
        "version": config.VERSION,
        "db_path": str(config.DB_PATH),
        "db_size_bytes": db_size,
        "counts": counts,
        "legacy_db_exists": config.LEGACY_DB_PATH.exists(),
        "legacy_db_path": str(config.LEGACY_DB_PATH),
        "legacy_imported_at": get_settings(conn).get("legacy_imported_at"),
        "last_run": refresh_service.last_successful_run(conn),
        "next_run_at": scheduler.next_run_iso(conn),
        "scheduler_enabled": config.SCHEDULER_ENABLED,
        "daily_quota": config.DAILY_QUOTA,
    }


@router.get("/settings")
def get_settings_view():
    with connect() as conn:
        raw = get_settings(conn)
        return {"settings": typed_settings(raw), "info": _info(conn)}


@router.put("/settings")
def update_settings(data: SettingsUpdate):
    if not data.values:
        raise HTTPException(status_code=400, detail="변경할 설정이 없습니다")
    normalized = {key: _validate(key, value) for key, value in data.values.items()}
    with connect() as conn:
        for key, value in normalized.items():
            set_setting(conn, key, value)
        raw = get_settings(conn)
        return {"settings": typed_settings(raw), "info": _info(conn)}


@router.post("/settings/import-legacy")
def import_legacy_view():
    if not config.LEGACY_DB_PATH.exists():
        raise HTTPException(status_code=404, detail="이전 버전 데이터베이스 파일이 없습니다")
    counts = import_legacy(config.LEGACY_DB_PATH)
    return {"imported": counts}


@router.get("/meta")
def meta():
    return {"app_name": config.APP_NAME, "version": config.VERSION}

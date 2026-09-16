import os
import pathlib
import tempfile

TMP = pathlib.Path(tempfile.mkdtemp(prefix="channelboard-test-"))
os.environ["CHANNELBOARD_DB"] = str(TMP / "test.db")
os.environ["CHANNELBOARD_SCHEDULER"] = "0"
os.environ["CHANNELBOARD_LEGACY_DB"] = str(TMP / "no-legacy.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import refresh as refresh_service  # noqa: E402
from tests import mock_youtube  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    for suffix in ("", "-wal", "-shm"):
        path = pathlib.Path(str(config.DB_PATH) + suffix)
        if path.exists():
            path.unlink()
    mock_youtube.reset()
    mock_youtube.install(monkeypatch)
    refresh_service.STATE.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(client):
    """API 키 1개 + 그룹 2개 + 채널 6개 등록"""
    client.post("/api/keys", json={"api_key": "AIzaFAKE-KEY-0000000000000001", "name": "key-1"})
    g1 = client.post("/api/groups", json={"name": "내 채널"}).json()["group"]["id"]
    g2 = client.post("/api/groups", json={"name": "서브 채널"}).json()["group"]["id"]
    ids = list(mock_youtube.CHANNELS)
    r1 = client.post("/api/channels", json={"inputs": [f"https://www.youtube.com/channel/{c}" for c in ids[:4]], "group_id": g1})
    r2 = client.post("/api/channels", json={"inputs": ids[4:], "group_id": g2})
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    mock_youtube.STATE["calls"].clear()
    return {"client": client, "g1": g1, "g2": g2,
            "channel_ids": {c["input"].split("/")[-1]: c["channel_id"] for c in r1.json()["added"] + r2.json()["added"]}}

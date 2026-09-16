import sqlite3
import time
from datetime import datetime, timedelta, timezone

from app import config
from app.db import connect
from app.services import refresh as refresh_service
from app.services.scheduler import is_due, compute_next_run
from app.services.legacy_import import import_legacy
from app.services.resolver import parse_input
from app.util import to_iso, utc_now
from tests import mock_youtube as mock

cid = mock.cid


def seed_snapshots(days=30, step_subs=120, step_views=50_000, hours_offset=1):
    """모든 채널에 과거 스냅샷 삽입 (d일 전: subs - d*step)"""
    with connect() as conn:
        rows = conn.execute("SELECT id, youtube_id FROM channels").fetchall()
        for row in rows:
            ch = mock.CHANNELS[row["youtube_id"]]
            for d in range(days, 0, -1):
                at = to_iso(utc_now() - timedelta(days=d, hours=hours_offset))
                conn.execute(
                    "INSERT INTO snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?,?,?,?,?)",
                    (row["id"], max(0, ch["subs"] - d * step_subs), max(0, ch["views"] - d * step_views),
                     max(0, ch["videos"] - d // 3), at),
                )


# ---------- 기본 ----------

def test_health_and_empty_state(client):
    assert client.get("/health").json()["status"] == "ok"
    data = client.get("/api/overview").json()
    assert data["channels"] == [] and data["summary"]["channel_count"] == 0
    assert client.get("/api/groups").json()["groups"][0]["is_default"] is True
    r = client.post("/api/refresh", json={})
    assert r.status_code == 400 and "API 키" in r.json()["detail"]


def test_parse_input_variants():
    assert parse_input(cid(1)).kind == "channel_id"
    assert parse_input("@dailyshorts").kind == "handle"
    assert parse_input("https://www.youtube.com/@dailyshorts/videos").value == "dailyshorts"
    assert parse_input(f"https://youtube.com/channel/{cid(2)}").value == cid(2)
    assert parse_input("https://www.youtube.com/watch?v=v0100xxxxxx&t=10s").kind == "video"
    assert parse_input("https://youtu.be/v0100xxxxxx").kind == "video"
    assert parse_input("https://www.youtube.com/shorts/v0100xxxxxx").kind == "video"
    assert parse_input("https://www.youtube.com/c/SomeName").kind == "custom"
    assert parse_input("https://www.youtube.com/user/SomeUser").kind == "user"
    assert parse_input("youtube.com/somename").kind == "name"
    assert parse_input("dailyshorts").kind == "name"
    assert parse_input("# 주석") is None
    assert parse_input("not a channel at all !!!") is None


# ---------- 채널 추가 ----------

def test_add_channels_all_input_kinds(client):
    client.post("/api/keys", json={"api_key": "AIzaFAKE-KEY-0000000000000001"})
    inputs = [
        f"https://www.youtube.com/channel/{cid(1)}",
        "@moneymotion",
        cid(3),
        "https://www.youtube.com/watch?v=v0400xxxxxx",      # → 채널 4
        "https://www.youtube.com/user/brandnewuser",         # → 채널 5
        "https://www.youtube.com/c/hiddenstats",             # 핸들로 해석
        "@does-not-exist",
        "https://www.youtube.com/watch?v=zzzzzzzzzzz",
        "not a channel !!!",
        "",
        "@moneymotion",                                      # 같은 요청 안 중복 → 이미 등록됨
    ]
    r = client.post("/api/channels", json={"inputs": inputs, "group_id": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    added = {a["title"] for a in body["added"]}
    assert added == {mock.CHANNELS[cid(n)]["title"] for n in range(1, 7)}
    assert len(body["skipped"]) == 1 and body["skipped"][0]["reason"].startswith("이미")
    failed_inputs = {f["input"] for f in body["failed"]}
    assert failed_inputs == {"@does-not-exist", "https://www.youtube.com/watch?v=zzzzzzzzzzz", "not a channel !!!"}
    assert body["quota_used"] > 0

    # 새 채널의 최근 영상이 바로 수집됨 (채널당 최대 10개)
    channels = client.get("/api/channels").json()["channels"]
    assert len(channels) == 6
    videos = client.get("/api/videos?days=0").json()
    expected = sum(min(10, ch["uploads"]) for ch in mock.CHANNELS.values())
    assert videos["total"] == expected
    # 통계 스냅샷 1개씩 생성
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 6
    # 키 사용량 저장
    keys = client.get("/api/keys").json()
    assert keys["used_today_total"] == body["quota_used"] + 1  # +1: 키 등록 시 검증 호출


def test_add_channels_requires_key_and_group(client):
    r = client.post("/api/channels", json={"inputs": [cid(1)], "group_id": 1})
    assert r.status_code == 400 and "API 키" in r.json()["detail"]
    client.post("/api/keys", json={"api_key": "AIzaFAKE-KEY-0000000000000001"})
    r = client.post("/api/channels", json={"inputs": [cid(1)], "group_id": 999})
    assert r.status_code == 404
    r = client.post("/api/channels", json={"inputs": ["   "], "group_id": 1})
    assert r.status_code == 400


# ---------- 갱신 ----------

def test_refresh_batches_and_quota(seeded):
    client = seeded["client"]
    result = refresh_service.run_refresh("all", trigger="manual")
    assert result["status"] == "success", result
    assert result["channels_updated"] == 6
    ep = [c[0] for c in mock.calls()]
    assert ep.count("channels") == 1          # 채널 6개 → 배치 1회
    assert ep.count("playlistItems") == 6     # 채널당 1회
    assert ep.count("videos") == 1            # 영상 44개 → 배치 1회
    assert result["quota_used"] == 8
    status = client.get("/api/refresh/status").json()
    assert status["last_run"]["status"] == "success" and status["state"]["running"] is False
    assert status["quota"]["used_today"] >= 8
    runs = client.get("/api/refresh/runs").json()["runs"]
    assert runs[0]["quota_used"] == 8 and runs[0]["trigger"] == "manual"


def test_refresh_endpoint_runs_in_background(seeded):
    client = seeded["client"]
    r = client.post("/api/refresh", json={"scope": "all"})
    assert r.status_code == 200 and r.json()["started"]
    for _ in range(100):
        s = client.get("/api/refresh/status").json()
        if not s["state"]["running"] and s["last_run"] and s["last_run"]["status"] != "running":
            break
        time.sleep(0.05)
    assert s["last_run"]["status"] == "success"
    r = client.post("/api/refresh", json={"scope": "group", "group_id": seeded["g2"]})
    assert r.status_code == 200
    for _ in range(100):
        s = client.get("/api/refresh/status").json()
        if not s["state"]["running"] and s["last_run"]["channels_total"] == 2:
            break
        time.sleep(0.05)
    assert s["last_run"]["channels_total"] == 2


def test_refresh_tracks_previous_video_views(seeded):
    client = seeded["client"]
    mock.STATE["view_bump"] = 500
    result = refresh_service.run_refresh("all")
    assert result["status"] == "success"
    videos = client.get("/api/videos?days=0&sort=delta").json()["videos"]
    assert videos[0]["view_delta"] == 500 and videos[0]["stats_prev_at"] is not None


def test_refresh_key_rotation_on_quota_exceeded(seeded):
    client = seeded["client"]
    client.post("/api/keys", json={"api_key": "AIzaFAKE-KEY-0000000000000002", "name": "key-2"})
    mock.STATE["exhausted_keys"] = {"AIzaFAKE-KEY-0000000000000001"}
    result = refresh_service.run_refresh("all")
    assert result["status"] == "success", result
    assert result["channels_updated"] == 6
    keys = {k["name"]: k for k in client.get("/api/keys").json()["keys"]}
    assert keys["key-1"]["quota_exceeded"] is True
    assert keys["key-2"]["quota_exceeded"] is False and keys["key-2"]["used_today"] >= 8
    # 모든 키 초과 → 실패 기록
    mock.STATE["exhausted_keys"] = {"AIzaFAKE-KEY-0000000000000001", "AIzaFAKE-KEY-0000000000000002"}
    result = refresh_service.run_refresh("all")
    assert result["status"] == "failed" and "쿼터" in result["message"]
    # 키 초기화 후 다시 성공
    mock.STATE["exhausted_keys"] = set()
    for k in keys.values():
        client.post(f"/api/keys/{k['id']}/reset")
    assert refresh_service.run_refresh("all")["status"] == "success"


def test_refresh_partial_when_channel_missing(seeded, monkeypatch):
    monkeypatch.setattr(mock, "CHANNELS", {k: v for k, v in mock.CHANNELS.items() if k != cid(3)})
    result = refresh_service.run_refresh("all")
    assert result["status"] == "partial" and result["channels_updated"] == 5
    assert any("찾을 수 없습니다" in e["error"] for e in result["errors"])


def test_refresh_without_keys_fails_gracefully(client):
    with connect() as conn:
        conn.execute("INSERT INTO channels (youtube_id, group_id, created_at, updated_at) VALUES (?, 1, 'x', 'x')", (cid(1),))
    result = refresh_service.run_refresh("all")
    assert result["status"] == "failed" and "API 키" in result["message"]


def test_snapshot_compaction(seeded):
    old_day = utc_now() - timedelta(days=5)
    with connect() as conn:
        ch = conn.execute("SELECT id FROM channels LIMIT 1").fetchone()["id"]
        for hour in (9, 12, 18):
            conn.execute("INSERT INTO snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?,1,1,1,?)",
                         (ch, to_iso(old_day.replace(hour=hour))))
    refresh_service.run_refresh("all")
    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM snapshots WHERE channel_id = ? AND captured_at < ?",
                         (ch, to_iso(utc_now() - timedelta(days=2)))).fetchone()[0]
        recent = conn.execute("SELECT COUNT(*) FROM snapshots WHERE channel_id = ? AND captured_at >= ?",
                              (ch, to_iso(utc_now() - timedelta(hours=1)))).fetchone()[0]
    assert n == 1 and recent == 2  # 등록 시 1개 + 갱신 1개


# ---------- 대시보드 ----------

def test_overview_deltas_uploads_and_insights(seeded):
    client = seeded["client"]
    seed_snapshots()
    refresh_service.run_refresh("all")
    data = client.get("/api/overview?days=7").json()
    s = data["summary"]
    by = {c["youtube_id"]: c for c in data["channels"]}
    assert s["channel_count"] == 6 and s["channels_never_refreshed"] == 0
    c1 = by[cid(1)]
    assert c1["delta"]["subscriber_count"] == 7 * 120 and c1["delta"]["partial"] is False
    assert c1["uploads_in_period"] == 7 and c1["days_since_upload"] < 1
    assert len(c1["sparkline"]) >= 30
    assert c1["latest_video"]["is_short"] is True
    assert by[cid(6)]["subscriber_hidden"] is True and s["channels_subscriber_hidden"] == 1
    assert by[cid(5)]["latest_video"] is None
    assert s["uploads_in_period"] == sum(c["uploads_in_period"] for c in data["channels"])
    assert s["subscriber_delta"] == sum(min(840, mock.CHANNELS[c]["subs"]) for c in by)
    assert len(data["latest_videos"]) == 8 and data["latest_videos"][0]["published_at"] >= data["latest_videos"][-1]["published_at"]

    ins = data["insights"]
    stale_ids = {x["channel_id"] for x in ins["stale"]}
    assert by[cid(3)]["id"] in stale_ids and by[cid(5)]["id"] in stale_ids and by[cid(1)]["id"] not in stale_ids
    assert {x["channel_id"] for x in ins["uploaded_today"]} == {by[cid(1)]["id"], by[cid(4)]["id"]}
    # 급상승: 채널1의 이상치 영상이 배수 기준으로 잡힘
    rising = ins["rising"]
    assert rising and rising[0]["youtube_id"] == "v0103xxxxxx" and rising[0]["ratio"] >= 1.75 and rising[0]["reason"] == "baseline"
    # 마일스톤: Money Motion 9,820 → 1만 임박 (180 남음)
    ms = {m["channel_id"]: m for m in ins["milestones"]}
    assert ms[by[cid(2)]["id"]]["milestone"] == 10_000 and ms[by[cid(2)]["id"]]["remaining"] == 180
    assert ins["declining"] == []

    # 24시간: 1일+1시간 전 스냅샷 기준
    c1 = {c["youtube_id"]: c for c in client.get("/api/overview?days=1").json()["channels"]}[cid(1)]
    assert c1["delta"]["subscriber_count"] == 120


def test_overview_declining_and_achieved_milestone(seeded):
    client = seeded["client"]
    with connect() as conn:
        rows = {r["youtube_id"]: r["id"] for r in conn.execute("SELECT id, youtube_id FROM channels")}
        at = to_iso(utc_now() - timedelta(days=8))
        # 채널 3: 8일 전 구독자가 지금보다 많았음 → 감소
        conn.execute("INSERT INTO snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?,?,?,?,?)",
                     (rows[cid(3)], 41_250 + 500, 9_870_000, 180, at))
        # 채널 1: 8일 전 99,000 → 지금 152,300 → 10만 달성
        conn.execute("INSERT INTO snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?,?,?,?,?)",
                     (rows[cid(1)], 99_000, 40_000_000, 400, at))
    refresh_service.run_refresh("all")
    ins = client.get("/api/overview?days=7").json()["insights"]
    assert [d["channel_id"] for d in ins["declining"]] == [rows[cid(3)]]
    achieved = [m for m in ins["milestones"] if m["achieved"]]
    assert achieved and achieved[0]["channel_id"] == rows[cid(1)] and achieved[0]["milestone"] == 100_000


def test_overview_group_filter_and_inactive(seeded):
    client = seeded["client"]
    g1, g2 = seeded["g1"], seeded["g2"]
    assert len(client.get(f"/api/overview?group_id={g1}").json()["channels"]) == 4
    assert len(client.get(f"/api/overview?group_id={g2}").json()["channels"]) == 2
    ch = client.get(f"/api/overview?group_id={g2}").json()["channels"][0]
    client.patch(f"/api/channels/{ch['id']}", json={"is_active": False})
    assert len(client.get(f"/api/overview?group_id={g2}").json()["channels"]) == 1
    assert len(client.get(f"/api/overview?group_id={g2}&include_inactive=true").json()["channels"]) == 2


def test_first_refresh_has_no_delta(seeded):
    client = seeded["client"]
    data = client.get("/api/overview?days=7").json()
    c1 = data["channels"][0]
    assert c1["delta"]["subscriber_count"] is None and c1["stats_updated_at"] is not None


# ---------- 채널 상세 / 관리 ----------

def test_channel_detail_history_videos_patch_delete(seeded):
    client = seeded["client"]
    seed_snapshots()
    refresh_service.run_refresh("all")
    ch_id = seeded["channel_ids"][cid(1)]
    detail = client.get(f"/api/channels/{ch_id}?days=7").json()
    assert detail["title"] == "데일리 쇼츠 스튜디오" and detail["delta"]["subscriber_count"] == 840
    assert detail["uploads_in_period"] == 7 and detail["avg_views_per_upload"] > 0
    assert detail["median_views_per_day"] is not None

    hist = client.get(f"/api/channels/{ch_id}/history?days=30").json()["history"]
    assert 29 <= len(hist) <= 31
    assert hist[-1]["subscriber_delta"] is not None and hist[-1]["subscriber_count"] == 152_300

    vids = client.get(f"/api/channels/{ch_id}/videos?sort=views").json()
    assert vids["videos"][0]["view_count"] == 2_500_000 and vids["videos"][0]["ratio"] >= 1.75

    r = client.patch(f"/api/channels/{ch_id}", json={"memo": "주력 채널", "group_id": seeded["g2"]})
    assert r.status_code == 200 and r.json()["memo"] == "주력 채널" and r.json()["group_id"] == seeded["g2"]
    assert client.patch(f"/api/channels/{ch_id}", json={}).status_code == 400
    assert client.patch(f"/api/channels/{ch_id}", json={"group_id": 999}).status_code == 404

    assert client.delete(f"/api/channels/{ch_id}").status_code == 200
    assert client.get(f"/api/channels/{ch_id}").status_code == 404
    with connect() as conn:  # CASCADE
        assert conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", (ch_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM snapshots WHERE channel_id = ?", (ch_id,)).fetchone()[0] == 0


def test_channel_list_search_and_bulk(seeded):
    client = seeded["client"]
    assert client.get("/api/channels?q=money").json()["total"] == 1
    ids = list(seeded["channel_ids"].values())
    r = client.post("/api/channels/bulk", json={"ids": ids[:2], "action": "move", "group_id": seeded["g2"]})
    assert r.json()["affected"] == 2
    assert client.get(f"/api/channels?group_id={seeded['g2']}").json()["total"] == 4
    r = client.post("/api/channels/bulk", json={"ids": ids[:3], "action": "deactivate"})
    assert r.json()["affected"] == 3
    assert client.get("/api/channels?include_inactive=false").json()["total"] == 3
    assert client.post("/api/channels/bulk", json={"ids": ids[:3], "action": "activate"}).json()["affected"] == 3
    assert client.post("/api/channels/bulk", json={"ids": ids[:1], "action": "delete"}).json()["affected"] == 1
    assert client.get("/api/channels").json()["total"] == 5
    assert client.post("/api/channels/bulk", json={"ids": [], "action": "delete"}).status_code == 400
    assert client.post("/api/channels/bulk", json={"ids": ids, "action": "nope"}).status_code == 400


# ---------- 그룹 ----------

def test_groups_crud(seeded):
    client = seeded["client"]
    groups = client.get("/api/groups").json()["groups"]
    assert [g["name"] for g in groups] == ["기본", "내 채널", "서브 채널"]
    assert groups[1]["channel_count"] == 4
    assert client.post("/api/groups", json={"name": "내 채널"}).status_code == 400
    assert client.post("/api/groups", json={"name": " "}).status_code == 400
    g = client.post("/api/groups", json={"name": "테스트"}).json()["group"]
    assert client.patch(f"/api/groups/{g['id']}", json={"name": "참고 채널"}).json()["group"]["name"] == "참고 채널"
    order = client.post("/api/groups/reorder", json={"ids": [g["id"], seeded["g2"], seeded["g1"], 1]}).json()["groups"]
    assert [x["id"] for x in order] == [g["id"], seeded["g2"], seeded["g1"], 1]
    assert client.delete("/api/groups/1").status_code == 400
    r = client.delete(f"/api/groups/{seeded['g2']}")
    assert r.json()["moved_channels"] == 2
    assert client.get("/api/groups").json()["groups"][-1]["channel_count"] == 2  # 기본 그룹으로 이동 (마지막 정렬)
    assert client.delete("/api/groups/999").status_code == 404


# ---------- 영상 ----------

def test_videos_filters_sort_pagination(seeded):
    client = seeded["client"]
    refresh_service.run_refresh("all")
    all_videos = client.get("/api/videos?days=0&limit=500").json()
    assert all_videos["total"] == 44 and all_videos["short_count"] + all_videos["long_count"] == 44
    shorts = client.get("/api/videos?days=0&kind=short&limit=500").json()
    assert shorts["total"] == all_videos["short_count"] and all(v["is_short"] for v in shorts["videos"])
    week = client.get("/api/videos?days=7&limit=500").json()
    assert 0 < week["total"] < 44
    top = client.get("/api/videos?days=0&sort=views&limit=1").json()["videos"][0]
    assert top["view_count"] == 2_500_000 and top["ratio"] >= 1.75
    page2 = client.get("/api/videos?days=0&sort=views&limit=10&offset=10").json()
    assert len(page2["videos"]) == 10 and page2["videos"][0]["view_count"] <= top["view_count"]
    ch = client.get("/api/videos?days=0&channel_id=%d&limit=500" % seeded["channel_ids"][cid(4)]).json()
    assert ch["total"] == 10
    q = client.get("/api/videos?days=0&q=Quiet&limit=500").json()
    assert q["total"] == 10
    grp = client.get(f"/api/videos?days=0&group_id={seeded['g2']}&limit=500").json()
    assert grp["total"] == 8


# ---------- 키 / 설정 / 내보내기 ----------

def test_keys_add_verify_patch_delete(client):
    mock.STATE["invalid_keys"] = {"AIzaINVALID-KEY-000000000000"}
    r = client.post("/api/keys", json={"api_key": "AIzaINVALID-KEY-000000000000"})
    assert r.status_code == 400 and "키 확인 실패" in r.json()["detail"]
    assert client.post("/api/keys", json={"api_key": "short"}).status_code == 400
    r = client.post("/api/keys", json={"api_key": "AIzaFAKE-KEY-0000000000000001", "name": "메인"})
    assert r.status_code == 200 and r.json()["key"]["masked"].startswith("AIzaFA") and r.json()["verified"]["ok"]
    assert client.post("/api/keys", json={"api_key": "AIzaFAKE-KEY-0000000000000001"}).status_code == 400
    key_id = r.json()["key"]["id"]
    assert client.post(f"/api/keys/{key_id}/test").json()["ok"] is True
    assert client.patch(f"/api/keys/{key_id}", json={"name": "보조", "is_active": False}).json()["key"]["is_active"] is False
    listing = client.get("/api/keys").json()
    assert listing["keys"][0]["name"] == "보조" and listing["used_today_total"] == 2
    assert client.delete(f"/api/keys/{key_id}").status_code == 200
    assert client.delete(f"/api/keys/{key_id}").status_code == 404


def test_settings_validation_and_update(client):
    r = client.put("/api/settings", json={"values": {"auto_refresh_interval_hours": 3, "stale_days": 5,
                                                      "auto_refresh_enabled": False, "theme": "dark"}})
    assert r.status_code == 200
    s = r.json()["settings"]
    assert s["auto_refresh_interval_hours"] == 3 and s["stale_days"] == 5 and s["auto_refresh_enabled"] is False and s["theme"] == "dark"
    assert client.put("/api/settings", json={"values": {"auto_refresh_interval_hours": 5}}).status_code == 400
    assert client.put("/api/settings", json={"values": {"max_videos_per_channel": 999}}).status_code == 400
    assert client.put("/api/settings", json={"values": {"theme": "neon"}}).status_code == 400
    assert client.put("/api/settings", json={"values": {"unknown": 1}}).status_code == 400
    info = client.get("/api/settings").json()["info"]
    assert info["counts"]["channels"] == 0 and info["version"] == config.VERSION
    assert client.post("/api/settings/import-legacy").status_code == 404


def test_export_csv(seeded):
    client = seeded["client"]
    refresh_service.run_refresh("all")
    r = client.get("/api/export/channels.csv?days=7")
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf")
    text = r.content.decode("utf-8-sig")
    assert "채널명" in text.splitlines()[0] and "Money Motion" in text
    assert len(text.strip().splitlines()) == 7
    shorts = client.get("/api/videos?days=0&kind=short&limit=500").json()["total"]
    r = client.get("/api/export/videos.csv?days=0&kind=short")
    assert r.status_code == 200 and len(r.content.decode("utf-8-sig").strip().splitlines()) == 1 + shorts


# ---------- 스케줄러 ----------

def test_scheduler_due_logic():
    settings = {"auto_refresh_enabled": True, "auto_refresh_interval_hours": 6}
    now = utc_now()
    assert is_due(settings, None, True, now) is True
    assert is_due(settings, None, False, now) is False
    assert is_due({**settings, "auto_refresh_enabled": False}, None, True, now) is False
    assert is_due(settings, to_iso(now - timedelta(hours=5)), True, now) is False
    assert is_due(settings, to_iso(now - timedelta(hours=7)), True, now) is True
    nxt = compute_next_run(settings, to_iso(now - timedelta(hours=2)), True)
    assert abs((nxt - (now + timedelta(hours=4))).total_seconds()) < 2


# ---------- 이전 버전 가져오기 ----------

def test_legacy_import(client, tmp_path):
    legacy = tmp_path / "database.db"
    conn = sqlite3.connect(str(legacy))
    conn.executescript("""
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE, display_order INTEGER, created_at TEXT);
        CREATE TABLE channels (id INTEGER PRIMARY KEY, category_id INTEGER, channel_input TEXT, channel_id TEXT, title TEXT,
            description TEXT, subscriber_count INTEGER, country TEXT, language_hint TEXT, is_active INTEGER,
            created_at TEXT, updated_at TEXT, view_count INTEGER, video_count INTEGER, thumbnail_url TEXT,
            uploads_playlist_id TEXT, custom_url TEXT, published_at TEXT, stats_updated_at TEXT);
        CREATE TABLE api_keys (id INTEGER PRIMARY KEY, api_key TEXT UNIQUE, name TEXT, is_active INTEGER, priority INTEGER,
            quota_exceeded INTEGER, last_used_at TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE channel_snapshots (id INTEGER PRIMARY KEY, channel_id TEXT, subscriber_count INTEGER, view_count INTEGER,
            video_count INTEGER, captured_at TEXT);
    """)
    conn.executemany("INSERT INTO categories VALUES (?,?,?,?)", [(1, "기본", 0, "x"), (2, "쇼츠 소싱", 1, "x"), (3, "기본2", 2, "x")])
    conn.executemany("INSERT INTO channels (id, category_id, channel_input, channel_id, title, subscriber_count, is_active, created_at, updated_at, custom_url) VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (1, 2, "@a", "UCaaaaaaaaaaaaaaaaaaaaaa", "A 채널", 1000, 1, "x", "x", "@a"),
        (2, 1, "@a", "UCaaaaaaaaaaaaaaaaaaaaaa", "A 채널", 1000, 1, "x", "x", "@a"),   # 중복 (다른 카테고리)
        (3, 3, "@b", "UCbbbbbbbbbbbbbbbbbbbbbb", "B 채널", 50, 0, "x", "x", None),
    ])
    conn.executemany("INSERT INTO api_keys (api_key, name, is_active, priority, quota_exceeded, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                     [("AIzaOLD-KEY-00000000000000001", "old", 1, 0, 0, "x", "x")])
    conn.executemany("INSERT INTO channel_snapshots (channel_id, subscriber_count, view_count, video_count, captured_at) VALUES (?,?,?,?,?)",
                     [("UCaaaaaaaaaaaaaaaaaaaaaa", 900, 100, 10, "2026-09-01T09:00:00"), ("UCzzzzzzzzzzzzzzzzzzzzzz", 1, 1, 1, "2026-09-01T09:00:00")])
    conn.commit()
    conn.close()

    counts = import_legacy(legacy)
    assert counts == {"groups": 2, "channels": 2, "api_keys": 1, "snapshots": 1}
    groups = {g["name"]: g for g in client.get("/api/groups").json()["groups"]}
    assert set(groups) == {"기본", "쇼츠 소싱", "기본2"}
    channels = {c["youtube_id"]: c for c in client.get("/api/channels").json()["channels"]}
    assert channels["UCaaaaaaaaaaaaaaaaaaaaaa"]["group_name"] == "쇼츠 소싱" and channels["UCaaaaaaaaaaaaaaaaaaaaaa"]["handle"] == "@a"
    assert channels["UCbbbbbbbbbbbbbbbbbbbbbb"]["is_active"] == 0
    assert client.get("/api/keys").json()["keys"][0]["name"] == "old"
    # 두 번째 가져오기는 중복 없이 0
    assert import_legacy(legacy) == {"groups": 0, "channels": 0, "api_keys": 0, "snapshots": 1}

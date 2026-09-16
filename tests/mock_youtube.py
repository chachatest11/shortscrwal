"""YouTube Data API v3 가짜 응답 (테스트용). app.services.youtube._http_get 을 대체한다."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

NOW = datetime.now(timezone.utc)


def cid(n: int) -> str:
    return "UC" + (f"mock{n:02d}" * 5)[:22]


def data_uri(text: str, bg: str) -> str:
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='160' height='90'>"
           f"<rect width='100%' height='100%' fill='{bg}'/>"
           f"<text x='50%' y='58%' font-size='30' text-anchor='middle' fill='white' font-family='sans-serif'>{text}</text></svg>")
    return "data:image/svg+xml;utf8," + quote(svg)


# 채널 6개: 활발/보통/업로드 공백/새 채널/영상 없음/구독자 비공개
CHANNELS = {
    cid(1): dict(title="데일리 쇼츠 스튜디오", handle="dailyshorts", username="dailyshortsuser", subs=152_300, views=48_210_000,
                 videos=412, country="KR", color="#2a78d6", uploads=12, last_upload_days_ago=0.3, interval_days=1.0),
    cid(2): dict(title="Money Motion", handle="moneymotion", username="moneymotionuser", subs=9_820, views=21_900_000,
                 videos=265, country="US", color="#eb6834", uploads=12, last_upload_days_ago=2.1, interval_days=1.5),
    cid(3): dict(title="밈 아카이브", handle="memearchive", username="memearchiveuser", subs=41_250, views=9_870_000,
                 videos=180, country="KR", color="#1baf7a", uploads=6, last_upload_days_ago=12.0, interval_days=3.0),
    cid(4): dict(title="Quiet Cooking", handle="quietcooking", username="quietcookinguser", subs=12_800, views=1_320_000,
                 videos=64, country="JP", color="#4a3aa7", uploads=10, last_upload_days_ago=0.8, interval_days=2.0),
    cid(5): dict(title="새 채널 (영상 없음)", handle="brandnew", username="brandnewuser", subs=0, views=0, videos=0,
                 country=None, color="#777", uploads=0, last_upload_days_ago=None, interval_days=1),
    cid(6): dict(title="Hidden Stats Channel", handle="hiddenstats", username="hiddenuser", subs=0, hidden=True,
                 views=5_600_000, videos=98, country="GB", color="#c98500", uploads=8, last_upload_days_ago=5.5, interval_days=4.0),
}

VIDEOS = {}
PLAYLISTS = {}


def _build():
    VIDEOS.clear()
    PLAYLISTS.clear()
    for n, (channel_id, ch) in enumerate(CHANNELS.items(), start=1):
        ids = []
        for k in range(ch["uploads"]):
            vid = f"v{n:02d}{k:02d}" + "x" * 6  # 11자
            published = NOW - timedelta(days=ch["last_upload_days_ago"] + k * ch["interval_days"])
            is_short = k % 3 != 2
            views = 120_000 // (k + 1) + n * 1_000
            if n == 1 and k == 3:
                views = 2_500_000  # 급상승(채널 평소 대비 이상치)
            VIDEOS[vid] = {
                "id": vid,
                "snippet": {
                    "title": f"{ch['title']} 영상 #{ch['uploads'] - k}" + (" (쇼츠)" if is_short else " (롱폼)"),
                    "channelId": channel_id,
                    "channelTitle": ch["title"],
                    "publishedAt": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "thumbnails": {"medium": {"url": data_uri(f"#{ch['uploads'] - k}", ch["color"])}},
                },
                "contentDetails": {"duration": "PT48S" if is_short else "PT6M12S"},
                "statistics": {"viewCount": str(views), "likeCount": str(max(1, views // 40)),
                               "commentCount": str(max(0, views // 1000))},
            }
            ids.append(vid)
        PLAYLISTS["UU" + channel_id[2:]] = ids


_build()

STATE = {
    "calls": [],            # (endpoint, params)
    "exhausted_keys": set(),  # 이 키로 오면 403 quotaExceeded
    "invalid_keys": set(),    # 이 키로 오면 400 keyInvalid
    "view_bump": 0,           # 영상 조회수에 더할 값 (갱신 간 증가 테스트)
    "fail_endpoint": None,    # 이 엔드포인트는 500
}


def reset():
    STATE["calls"].clear()
    STATE["exhausted_keys"] = set()
    STATE["invalid_keys"] = set()
    STATE["view_bump"] = 0
    STATE["fail_endpoint"] = None


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _error(status, reason, message=""):
    return FakeResponse(status, {"error": {"code": status, "message": message or reason, "errors": [{"reason": reason}]}})


def channel_item(channel_id):
    ch = CHANNELS[channel_id]
    stats = {"viewCount": str(ch["views"]), "videoCount": str(ch["videos"]),
             "hiddenSubscriberCount": bool(ch.get("hidden"))}
    if not ch.get("hidden"):
        stats["subscriberCount"] = str(ch["subs"])
    return {
        "id": channel_id,
        "snippet": {
            "title": ch["title"], "description": f"{ch['title']} 설명", "customUrl": "@" + ch["handle"],
            "publishedAt": "2021-03-01T00:00:00Z", "country": ch["country"],
            "thumbnails": {"default": {"url": data_uri(ch["title"][0], ch["color"])},
                           "medium": {"url": data_uri(ch["title"][0], ch["color"])}},
        },
        "statistics": stats,
        "contentDetails": {"relatedPlaylists": {"uploads": "UU" + channel_id[2:]}},
    }


def fake_http_get(url, params=None, timeout=None):
    params = dict(params or {})
    endpoint = url.rstrip("/").split("/")[-1]
    STATE["calls"].append((endpoint, params))
    key = params.get("key")

    if key in STATE["invalid_keys"]:
        return _error(400, "badRequest", "API key not valid. Please pass a valid API key.")
    if key in STATE["exhausted_keys"]:
        return _error(403, "quotaExceeded", "The request cannot be completed because you have exceeded your quota.")
    if STATE["fail_endpoint"] == endpoint:
        return _error(500, "backendError", "Backend Error")

    if endpoint == "channels":
        items = []
        if "id" in params:
            for channel_id in params["id"].split(","):
                if channel_id in CHANNELS:
                    items.append(channel_item(channel_id))
                elif channel_id == "UC_x5XG1OV2P6uZZ5FSM9Ttw":  # 키 검증용
                    items.append({"id": channel_id})
        elif "forHandle" in params:
            for channel_id, ch in CHANNELS.items():
                if ch["handle"].lower() == params["forHandle"].lstrip("@").lower():
                    items.append({"id": channel_id})
        elif "forUsername" in params:
            for channel_id, ch in CHANNELS.items():
                if ch["username"].lower() == params["forUsername"].lower():
                    items.append({"id": channel_id})
        return FakeResponse(200, {"items": items})

    if endpoint == "search":
        q = params.get("q", "").lower()
        for channel_id, ch in CHANNELS.items():
            if q and (q in ch["title"].lower() or q in ch["handle"].lower()):
                return FakeResponse(200, {"items": [{"snippet": {"channelId": channel_id}}]})
        return FakeResponse(200, {"items": []})

    if endpoint == "playlistItems":
        playlist_id = params.get("playlistId")
        if playlist_id not in PLAYLISTS:
            return _error(404, "playlistNotFound", "The playlist identified with the request's playlistId parameter cannot be found.")
        ids = PLAYLISTS[playlist_id]
        max_results = int(params.get("maxResults", 50))
        return FakeResponse(200, {"items": [{"contentDetails": {"videoId": v}} for v in ids[:max_results]]})

    if endpoint == "videos":
        items = []
        for vid in params.get("id", "").split(","):
            if vid in VIDEOS:
                item = json.loads(json.dumps(VIDEOS[vid]))
                if STATE["view_bump"]:
                    item["statistics"]["viewCount"] = str(int(item["statistics"]["viewCount"]) + STATE["view_bump"])
                items.append(item)
        return FakeResponse(200, {"items": items})

    return _error(400, "unknownEndpoint")


def install(monkeypatch):
    import app.services.youtube as yt
    monkeypatch.setattr(yt, "_http_get", fake_http_get)


def calls(endpoint=None):
    return [c for c in STATE["calls"] if endpoint is None or c[0] == endpoint]

"""YouTube Data API v3 클라이언트 (여러 API 키 자동 교대 + 쿼터 집계)"""
from typing import Dict, List, Optional

import requests

from ..util import parse_duration, normalize_iso

BASE_URL = "https://www.googleapis.com/youtube/v3"
QUOTA_COST = {"search": 100}  # 그 외 엔드포인트는 1 unit
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}


class YouTubeError(Exception):
    """API 오류 (키 오류, 네트워크 오류 등)"""


class AllKeysExhausted(YouTubeError):
    """사용 가능한 API 키가 모두 쿼터를 초과함"""


def _http_get(url: str, params: dict, timeout: int = 30):
    """테스트에서 교체할 수 있도록 분리한 HTTP GET"""
    return requests.get(url, params=params, timeout=timeout)


class KeyPool:
    """활성 API 키 목록. 쿼터 초과 키는 건너뛰고 다음 키를 쓴다."""

    def __init__(self, keys: List[dict]):
        self.keys = [dict(k) for k in keys if k.get("is_active", 1) and not k.get("quota_exceeded", 0)]
        self.usage: Dict[int, int] = {k["id"]: 0 for k in self.keys}
        self.exhausted: List[int] = []
        self.index = 0

    def current(self) -> Optional[dict]:
        while self.index < len(self.keys):
            key = self.keys[self.index]
            if key["id"] in self.exhausted:
                self.index += 1
                continue
            return key
        return None

    def mark_exhausted(self, key_id: int) -> None:
        if key_id not in self.exhausted:
            self.exhausted.append(key_id)

    def add_usage(self, key_id: int, cost: int) -> None:
        self.usage[key_id] = self.usage.get(key_id, 0) + cost

    @property
    def total_usage(self) -> int:
        return sum(self.usage.values())


class YouTubeClient:
    def __init__(self, pool: KeyPool):
        self.pool = pool

    # ---------- 저수준 ----------

    def request(self, endpoint: str, params: dict) -> dict:
        cost = QUOTA_COST.get(endpoint, 1)
        while True:
            key = self.pool.current()
            if key is None:
                raise AllKeysExhausted("사용 가능한 API 키가 없습니다 (모든 키가 쿼터 초과)")

            query = dict(params)
            query["key"] = key["api_key"]
            try:
                response = _http_get(f"{BASE_URL}/{endpoint}", query)
            except requests.RequestException as exc:
                raise YouTubeError(f"네트워크 오류: {exc}") from exc

            self.pool.add_usage(key["id"], cost)

            if response.status_code == 200:
                return response.json()

            reason, message = self._error_info(response)
            if response.status_code == 403 and reason in QUOTA_REASONS:
                self.pool.mark_exhausted(key["id"])
                continue  # 다음 키로 재시도
            if response.status_code in (400, 403) and reason in ("keyInvalid", "badRequest") and "API key" in message:
                raise YouTubeError(f"API 키가 올바르지 않습니다 ({message})")
            if response.status_code == 403:
                raise YouTubeError(f"접근 거부: {message or reason or response.status_code}")
            raise YouTubeError(f"YouTube API 오류 {response.status_code}: {message or reason}")

    @staticmethod
    def _error_info(response):
        try:
            data = response.json()
        except ValueError:
            return "", response.text[:200] if hasattr(response, "text") else ""
        error = data.get("error", {}) if isinstance(data, dict) else {}
        errors = error.get("errors") or []
        reason = errors[0].get("reason", "") if errors else error.get("status", "")
        message = error.get("message", "")
        return reason, message

    # ---------- 채널 ----------

    def channels_by_ids(self, youtube_ids: List[str]) -> Dict[str, dict]:
        """채널 정보/통계 (50개씩, 배치당 1 unit)"""
        result: Dict[str, dict] = {}
        ids = [i for i in dict.fromkeys(youtube_ids) if i]
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            data = self.request("channels", {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "maxResults": 50,
            })
            for item in data.get("items", []):
                info = self._parse_channel(item)
                result[info["youtube_id"]] = info
        return result

    def channel_id_by_handle(self, handle: str) -> Optional[str]:
        data = self.request("channels", {"part": "id", "forHandle": handle.lstrip("@")})
        items = data.get("items") or []
        return items[0]["id"] if items else None

    def channel_id_by_username(self, username: str) -> Optional[str]:
        data = self.request("channels", {"part": "id", "forUsername": username})
        items = data.get("items") or []
        return items[0]["id"] if items else None

    def channel_id_by_search(self, query: str) -> Optional[str]:
        """search.list 는 100 units - 마지막 수단"""
        data = self.request("search", {"part": "snippet", "q": query, "type": "channel", "maxResults": 1})
        items = data.get("items") or []
        return items[0]["snippet"]["channelId"] if items else None

    def channel_ids_by_video_ids(self, video_ids: List[str]) -> Dict[str, str]:
        """영상 ID → 채널 ID"""
        result: Dict[str, str] = {}
        ids = [i for i in dict.fromkeys(video_ids) if i]
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            data = self.request("videos", {"part": "snippet", "id": ",".join(batch), "maxResults": 50})
            for item in data.get("items", []):
                result[item["id"]] = item.get("snippet", {}).get("channelId")
        return result

    @staticmethod
    def _parse_channel(item: dict) -> dict:
        snippet = item.get("snippet", {}) or {}
        stats = item.get("statistics", {}) or {}
        content = item.get("contentDetails", {}) or {}
        thumbs = snippet.get("thumbnails", {}) or {}
        thumbnail = (thumbs.get("medium") or thumbs.get("default") or thumbs.get("high") or {}).get("url")
        handle = snippet.get("customUrl") or None
        if handle and not handle.startswith("@"):
            handle = "@" + handle
        return {
            "youtube_id": item["id"],
            "title": snippet.get("title"),
            "handle": handle,
            "description": snippet.get("description"),
            "thumbnail_url": thumbnail,
            "country": snippet.get("country"),
            "published_at": normalize_iso(snippet.get("publishedAt")),
            "uploads_playlist_id": (content.get("relatedPlaylists") or {}).get("uploads"),
            "subscriber_count": int(stats.get("subscriberCount") or 0),
            "subscriber_hidden": 1 if stats.get("hiddenSubscriberCount") else 0,
            "view_count": int(stats.get("viewCount") or 0),
            "video_count": int(stats.get("videoCount") or 0),
        }

    # ---------- 영상 ----------

    def playlist_video_ids(self, playlist_id: str, max_results: int = 10) -> List[str]:
        """업로드 플레이리스트의 최신 영상 ID (최신순, 페이지당 1 unit)"""
        ids: List[str] = []
        page_token = None
        while len(ids) < max_results:
            params = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(50, max_results - len(ids)),
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                data = self.request("playlistItems", params)
            except YouTubeError as exc:
                # 영상이 없는 채널은 404 playlistNotFound 를 돌려준다
                if "404" in str(exc) or "playlistNotFound" in str(exc):
                    break
                raise
            for item in data.get("items", []):
                video_id = (item.get("contentDetails") or {}).get("videoId")
                if video_id:
                    ids.append(video_id)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids[:max_results]

    def videos_by_ids(self, video_ids: List[str], shorts_max_seconds: int = 180) -> List[dict]:
        """영상 상세 (50개씩, 배치당 1 unit)"""
        result: List[dict] = []
        ids = [i for i in dict.fromkeys(video_ids) if i]
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            data = self.request("videos", {
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(batch),
                "maxResults": 50,
            })
            for item in data.get("items", []):
                result.append(self._parse_video(item, shorts_max_seconds))
        return result

    @staticmethod
    def _parse_video(item: dict, shorts_max_seconds: int) -> dict:
        snippet = item.get("snippet", {}) or {}
        content = item.get("contentDetails", {}) or {}
        stats = item.get("statistics", {}) or {}
        thumbs = snippet.get("thumbnails", {}) or {}
        thumbnail = (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url")
        duration = parse_duration(content.get("duration"))
        return {
            "youtube_id": item["id"],
            "channel_youtube_id": snippet.get("channelId"),
            "title": snippet.get("title"),
            "published_at": normalize_iso(snippet.get("publishedAt")),
            "duration_seconds": duration,
            "is_short": 1 if 0 < duration <= shorts_max_seconds else 0,
            "thumbnail_url": thumbnail,
            "view_count": int(stats.get("viewCount") or 0),
            "like_count": int(stats.get("likeCount") or 0),
            "comment_count": int(stats.get("commentCount") or 0),
        }

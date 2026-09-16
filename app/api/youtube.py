import re
import requests
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import isodate


class QuotaExceededException(Exception):
    """YouTube API 쿼터 초과 예외"""
    pass


class YouTubeAPI:
    """YouTube Data API v3 래퍼"""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    # 엔드포인트별 쿼터 비용 (search.list만 100 units, 나머지는 1 unit)
    QUOTA_COST = {"search": 100}

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.quota_used = 0  # 이 인스턴스로 소모한 쿼터 (추정치)

    def _request(self, endpoint: str, params: dict) -> dict:
        """API 요청 헬퍼"""
        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"
        self.quota_used += self.QUOTA_COST.get(endpoint, 1)
        response = requests.get(url, params=params, timeout=30)

        # 쿼터 초과 에러 체크
        if response.status_code == 403:
            try:
                error_data = response.json()
                if error_data.get("error", {}).get("errors", [{}])[0].get("reason") == "quotaExceeded":
                    raise QuotaExceededException("YouTube API 쿼터가 초과되었습니다")
            except (ValueError, KeyError):
                pass

        response.raise_for_status()
        return response.json()

    def normalize_channel_input(self, channel_input: str) -> Optional[str]:
        """
        다양한 형태의 채널 입력을 channelId로 정규화

        지원 형식:
        - https://youtube.com/@handle
        - https://www.youtube.com/channel/UCxxxx
        - https://www.youtube.com/c/CustomName
        - UCxxxx (직접 channelId)
        """
        channel_input = channel_input.strip()

        # 이미 channelId 형식인 경우 (UC로 시작하는 24자)
        if re.match(r"^UC[\w-]{22}$", channel_input):
            return channel_input

        # URL에서 채널 정보 추출
        # @handle 형식
        handle_match = re.search(r"@([\w-]+)", channel_input)
        if handle_match:
            handle = handle_match.group(1)
            return self._resolve_handle_to_channel_id(handle)

        # /channel/UCxxxx 형식
        channel_match = re.search(r"/channel/(UC[\w-]{22})", channel_input)
        if channel_match:
            return channel_match.group(1)

        # /c/CustomName 형식
        custom_match = re.search(r"/c/([\w-]+)", channel_input)
        if custom_match:
            custom_name = custom_match.group(1)
            return self._resolve_custom_url_to_channel_id(custom_name)

        # /user/username 형식
        user_match = re.search(r"/user/([\w-]+)", channel_input)
        if user_match:
            username = user_match.group(1)
            return self._resolve_username_to_channel_id(username)

        return None

    def _resolve_handle_to_channel_id(self, handle: str) -> Optional[str]:
        """핸들(@handle)을 channelId로 변환"""
        try:
            # YouTube Data API v3의 forHandle 파라미터 사용
            result = self._request("channels", {
                "part": "id",
                "forHandle": handle  # @ 없이 핸들명만
            })

            if result.get("items"):
                return result["items"][0]["id"]
        except Exception as e:
            print(f"Error resolving handle {handle}: {e}")
            pass
        return None

    def _resolve_custom_url_to_channel_id(self, custom_name: str) -> Optional[str]:
        """커스텀 URL을 channelId로 변환"""
        try:
            result = self._request("search", {
                "part": "snippet",
                "q": custom_name,
                "type": "channel",
                "maxResults": 1
            })

            if result.get("items"):
                return result["items"][0]["snippet"]["channelId"]
        except Exception:
            pass
        return None

    def _resolve_username_to_channel_id(self, username: str) -> Optional[str]:
        """사용자명을 channelId로 변환"""
        try:
            result = self._request("channels", {
                "part": "id",
                "forUsername": username
            })

            if result.get("items"):
                return result["items"][0]["id"]
        except Exception:
            pass
        return None

    def get_channel_info(self, channel_id: str) -> Optional[Dict]:
        """채널 정보 가져오기"""
        try:
            result = self._request("channels", {
                "part": "snippet,statistics",
                "id": channel_id
            })

            if not result.get("items"):
                return None

            item = result["items"][0]
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})

            return {
                "channel_id": channel_id,
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "subscriber_count": int(statistics.get("subscriberCount", 0)),
                "country": snippet.get("country"),
                "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url")
            }
        except QuotaExceededException:
            raise
        except Exception as e:
            print(f"Error getting channel info: {e}")
            return None

    def get_channels_batch(self, channel_ids: List[str]) -> Dict[str, Dict]:
        """
        여러 채널의 정보/통계를 한 번에 가져오기 (대시보드용)

        channels.list는 한 번에 최대 50개 ID를 받고 호출당 쿼터 1 unit만 소모하므로
        채널 수가 많아도 매우 저렴하게 현황을 갱신할 수 있다.

        Returns: {channel_id: {...}} (응답에 없는 채널은 포함되지 않음 - 삭제/비공개 등)
        """
        result_map: Dict[str, Dict] = {}

        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i:i + 50]
            result = self._request("channels", {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "maxResults": 50
            })

            for item in result.get("items", []):
                snippet = item.get("snippet", {})
                statistics = item.get("statistics", {})
                content_details = item.get("contentDetails", {})
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = (
                    thumbnails.get("medium", {}).get("url") or
                    thumbnails.get("default", {}).get("url")
                )

                result_map[item["id"]] = {
                    "channel_id": item["id"],
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "custom_url": snippet.get("customUrl"),
                    "published_at": snippet.get("publishedAt"),
                    "country": snippet.get("country"),
                    "thumbnail_url": thumbnail_url,
                    "subscriber_count": int(statistics.get("subscriberCount") or 0),
                    "subscriber_hidden": bool(statistics.get("hiddenSubscriberCount", False)),
                    "view_count": int(statistics.get("viewCount") or 0),
                    "video_count": int(statistics.get("videoCount") or 0),
                    "uploads_playlist_id": (
                        content_details.get("relatedPlaylists", {}).get("uploads")
                    ),
                }

        return result_map

    def get_channel_uploads_playlist_id(self, channel_id: str) -> Optional[str]:
        """채널의 업로드 플레이리스트 ID 가져오기"""
        try:
            result = self._request("channels", {
                "part": "contentDetails",
                "id": channel_id
            })

            if result.get("items"):
                return result["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except Exception:
            pass
        return None

    def get_videos_from_playlist(
        self,
        playlist_id: str,
        max_results: int = 50
    ) -> List[str]:
        """플레이리스트에서 비디오 ID 목록 가져오기"""
        video_ids = []
        page_token = None

        try:
            while len(video_ids) < max_results:
                params = {
                    "part": "contentDetails",
                    "playlistId": playlist_id,
                    "maxResults": min(50, max_results - len(video_ids))
                }
                if page_token:
                    params["pageToken"] = page_token

                result = self._request("playlistItems", params)

                for item in result.get("items", []):
                    video_id = item["contentDetails"]["videoId"]
                    video_ids.append(video_id)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

        except QuotaExceededException:
            raise
        except Exception as e:
            print(f"Error getting videos from playlist: {e}")

        return video_ids

    def get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """비디오 상세 정보 가져오기 (최대 50개씩)"""
        all_videos = []

        # YouTube API는 한 번에 최대 50개까지만 조회 가능
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                result = self._request("videos", {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(batch)
                })

                for item in result.get("items", []):
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    statistics = item.get("statistics", {})

                    # duration 파싱
                    duration_iso = content_details.get("duration", "PT0S")
                    try:
                        duration = isodate.parse_duration(duration_iso)
                        duration_seconds = int(duration.total_seconds())
                    except Exception:
                        duration_seconds = 0

                    # 쇼츠 여부 판별 (60초 이하)
                    is_short = 1 if duration_seconds <= 60 and duration_seconds > 0 else 0

                    # 썸네일 우선순위: maxres > high > medium > default
                    thumbnails = snippet.get("thumbnails", {})
                    thumbnail_url = (
                        thumbnails.get("maxres", {}).get("url") or
                        thumbnails.get("high", {}).get("url") or
                        thumbnails.get("medium", {}).get("url") or
                        thumbnails.get("default", {}).get("url")
                    )

                    video_data = {
                        "video_id": item["id"],
                        "channel_id": snippet.get("channelId"),
                        "title": snippet.get("title"),
                        "published_at": snippet.get("publishedAt"),
                        "view_count": int(statistics.get("viewCount", 0)),
                        "like_count": int(statistics.get("likeCount", 0)),
                        "comment_count": int(statistics.get("commentCount", 0)),
                        "thumbnail_url": thumbnail_url,
                        "duration_seconds": duration_seconds,
                        "is_short": is_short,
                        "channel_title": snippet.get("channelTitle")
                    }
                    all_videos.append(video_data)

            except QuotaExceededException:
                raise
            except Exception as e:
                print(f"Error getting video details: {e}")

        return all_videos

    def get_channel_shorts(
        self,
        channel_id: str,
        max_results: int = 50
    ) -> List[Dict]:
        """채널의 쇼츠 영상 가져오기"""
        # 업로드 플레이리스트 ID 가져오기
        uploads_playlist_id = self.get_channel_uploads_playlist_id(channel_id)
        if not uploads_playlist_id:
            return []

        # 최근 영상 ID 목록 가져오기 (쇼츠 필터링을 위해 충분히 많이 가져옴)
        # 일반 영상과 쇼츠가 섞여있으므로 5배로 가져와서 안전하게 확보
        fetch_count = min(max_results * 5, 200)  # 최대 200개까지만
        video_ids = self.get_videos_from_playlist(
            uploads_playlist_id,
            max_results=fetch_count
        )

        if not video_ids:
            return []

        # 비디오 상세 정보 가져오기
        videos = self.get_video_details(video_ids)

        # 쇼츠만 필터링
        shorts = [v for v in videos if v["is_short"] == 1]

        # max_results만큼만 반환
        return shorts[:max_results]

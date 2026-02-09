from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from ..db import get_db
from ..models import Video
from .youtube import YouTubeAPI, QuotaExceededException
from .channels import get_available_api_key, mark_api_key_quota_exceeded

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    category_id: int
    api_key: Optional[str] = None  # Optional: DB에서 자동 가져오기
    max_videos: int = 50
    min_views_man: int = 0  # 만 단위 (10 => 100,000)
    sort: str = "latest"  # latest or views


@router.post("/")
def search_videos(data: SearchRequest):
    """
    카테고리의 활성 채널에서 쇼츠 영상 수집

    1. 해당 카테고리의 활성 채널 로드
    2. 각 채널에서 최근 N개 쇼츠 수집
    3. DB에 upsert
    4. 필터/정렬 적용 후 반환
    """
    # API 키 가져오기 (제공된 키 또는 DB에서 자동)
    api_key = get_available_api_key(data.api_key)
    youtube_api = YouTubeAPI(api_key)

    # 1. 활성 채널 로드
    with get_db() as conn:
        cursor = conn.cursor()

        # category_id가 0이면 전체 채널, 아니면 해당 카테고리만
        if data.category_id == 0:
            cursor.execute("""
                SELECT id, channel_id, title
                FROM channels
                WHERE is_active = 1
            """)
        else:
            cursor.execute("""
                SELECT id, channel_id, title
                FROM channels
                WHERE category_id = ? AND is_active = 1
            """, (data.category_id,))

        channels = cursor.fetchall()

    if not channels:
        return {
            "message": "활성화된 채널이 없습니다",
            "videos": [],
            "total": 0
        }

    # 2. 각 채널에서 쇼츠 수집
    all_videos = []
    errors = []
    fetched_video_ids = []  # 이번 검색에서 가져온 video_id 추적

    # 각 채널에서 max_videos 개수만큼 가져오기
    for channel_row in channels:
        db_channel_id = channel_row[0]
        youtube_channel_id = channel_row[1]
        channel_title = channel_row[2]

        try:
            # YouTube API로 쇼츠 가져오기 (채널당 max_videos개)
            shorts = youtube_api.get_channel_shorts(
                youtube_channel_id,
                max_results=data.max_videos
            )

            # DB에 upsert
            with get_db() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                for video_data in shorts:
                    # 이번 검색에서 가져온 video_id 기록
                    fetched_video_ids.append(video_data["video_id"])

                    # 기존 영상 확인
                    cursor.execute("""
                        SELECT id FROM videos WHERE video_id = ?
                    """, (video_data["video_id"],))
                    existing = cursor.fetchone()

                    if existing:
                        # UPDATE
                        cursor.execute("""
                            UPDATE videos
                            SET view_count = ?,
                                like_count = ?,
                                comment_count = ?,
                                updated_at = ?
                            WHERE video_id = ?
                        """, (
                            video_data["view_count"],
                            video_data["like_count"],
                            video_data["comment_count"],
                            now,
                            video_data["video_id"]
                        ))
                    else:
                        # INSERT
                        cursor.execute("""
                            INSERT INTO videos (
                                channel_id, video_id, title, published_at,
                                view_count, like_count, comment_count, thumbnail_url, duration_seconds,
                                is_short, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            video_data["channel_id"],
                            video_data["video_id"],
                            video_data["title"],
                            video_data["published_at"],
                            video_data["view_count"],
                            video_data["like_count"],
                            video_data["comment_count"],
                            video_data["thumbnail_url"],
                            video_data["duration_seconds"],
                            video_data["is_short"],
                            now,
                            now
                        ))

                conn.commit()

            all_videos.extend(shorts)

        except QuotaExceededException as e:
            # API 키 쿼터 초과 처리
            mark_api_key_quota_exceeded(api_key)
            errors.append({
                "channel_title": channel_title,
                "error": f"API 쿼터가 초과되었습니다: {str(e)}"
            })
            break  # 쿼터 초과 시 더 이상 진행하지 않음
        except Exception as e:
            errors.append({
                "channel_title": channel_title,
                "error": str(e)
            })

    # 3. DB에서 결과 조회 (필터/정렬 적용)
    # 이번 검색에서 가져온 영상만 반환
    if not fetched_video_ids:
        return {
            "videos": [],
            "total": 0,
            "errors": errors if errors else None
        }

    with get_db() as conn:
        cursor = conn.cursor()

        # 조회수 필터링
        min_views = data.min_views_man * 10000

        # 정렬 조건
        sort_options = {
            "latest": "v.published_at DESC",
            "oldest": "v.published_at ASC",
            "views_desc": "v.view_count DESC",
            "views_asc": "v.view_count ASC",
            "likes_desc": "v.like_count DESC",
            "likes_asc": "v.like_count ASC",
            "comments_desc": "v.comment_count DESC",
            "comments_asc": "v.comment_count ASC"
        }
        order_by = sort_options.get(data.sort, "v.published_at DESC")

        # 이번 검색에서 가져온 영상만 조회
        placeholders = ','.join('?' * len(fetched_video_ids))
        cursor.execute(f"""
            SELECT v.id, v.channel_id, v.video_id, v.title, v.published_at,
                   v.view_count, v.like_count, v.comment_count, v.thumbnail_url, v.duration_seconds,
                   v.is_short, v.created_at, v.updated_at, c.title as channel_title
            FROM videos v
            INNER JOIN channels c ON v.channel_id = c.channel_id
            WHERE v.video_id IN ({placeholders})
              AND v.is_short = 1
              AND v.view_count >= ?
            ORDER BY {order_by}
        """, (*fetched_video_ids, min_views))

        rows = cursor.fetchall()
        videos = [Video.from_row(row).to_dict() for row in rows]

    return {
        "videos": videos,
        "total": len(videos),
        "errors": errors if errors else None
    }


@router.get("/videos")
def get_videos(
    category_id: Optional[int] = None,
    min_views_man: int = 0,
    sort: str = "latest"
):
    """
    저장된 영상 조회 (API 호출 없이)

    프론트엔드에서 필터/정렬만 변경할 때 사용
    """
    with get_db() as conn:
        cursor = conn.cursor()

        min_views = min_views_man * 10000

        # 정렬 조건
        sort_options = {
            "latest": "v.published_at DESC",
            "oldest": "v.published_at ASC",
            "views_desc": "v.view_count DESC",
            "views_asc": "v.view_count ASC",
            "likes_desc": "v.like_count DESC",
            "likes_asc": "v.like_count ASC",
            "comments_desc": "v.comment_count DESC",
            "comments_asc": "v.comment_count ASC"
        }
        order_by = sort_options.get(sort, "v.published_at DESC")

        if category_id:
            cursor.execute(f"""
                SELECT v.id, v.channel_id, v.video_id, v.title, v.published_at,
                       v.view_count, v.like_count, v.comment_count, v.thumbnail_url, v.duration_seconds,
                       v.is_short, v.created_at, v.updated_at, c.title as channel_title
                FROM videos v
                INNER JOIN channels c ON v.channel_id = c.channel_id
                WHERE c.category_id = ?
                  AND c.is_active = 1
                  AND v.is_short = 1
                  AND v.view_count >= ?
                ORDER BY {order_by}
            """, (category_id, min_views))
        else:
            cursor.execute(f"""
                SELECT v.id, v.channel_id, v.video_id, v.title, v.published_at,
                       v.view_count, v.like_count, v.comment_count, v.thumbnail_url, v.duration_seconds,
                       v.is_short, v.created_at, v.updated_at, c.title as channel_title
                FROM videos v
                INNER JOIN channels c ON v.channel_id = c.channel_id
                WHERE v.is_short = 1
                  AND v.view_count >= ?
                ORDER BY {order_by}
            """, (min_views,))

        rows = cursor.fetchall()
        videos = [Video.from_row(row).to_dict() for row in rows]

        return {"videos": videos, "total": len(videos)}

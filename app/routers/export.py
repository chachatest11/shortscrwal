import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..db import connect
from ..util import utc_now
from ..services.insights import build_overview
from .videos import query_videos

router = APIRouter(prefix="/api/export", tags=["export"])


def _csv_response(rows, header, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8-sig")  # 엑셀 한글 깨짐 방지 BOM
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/channels.csv")
def export_channels(group_id: int = 0, days: int = Query(7, ge=1, le=365), include_inactive: bool = True):
    with connect() as conn:
        data = build_overview(conn, group_id=group_id, days=days, include_inactive=include_inactive)
    rows = []
    for ch in data["channels"]:
        d = ch.get("delta") or {}
        latest = ch.get("latest_video") or {}
        rows.append([
            ch["title"], ch["handle"] or "", f"https://www.youtube.com/channel/{ch['youtube_id']}", ch["group_name"] or "",
            "활성" if ch["is_active"] else "비활성",
            "비공개" if ch["subscriber_hidden"] else (ch["subscriber_count"] if ch["subscriber_count"] is not None else ""),
            d.get("subscriber_count") if d.get("subscriber_count") is not None else "",
            ch["view_count"] if ch["view_count"] is not None else "",
            d.get("view_count") if d.get("view_count") is not None else "",
            ch["video_count"] if ch["video_count"] is not None else "",
            ch.get("uploads_in_period", 0),
            latest.get("title", ""), latest.get("published_at", ""), latest.get("view_count", ""),
            ch["stats_updated_at"] or "",
        ])
    header = ["채널명", "핸들", "URL", "그룹", "상태", "구독자", f"구독자 증감({days}일)", "총 조회수",
              f"조회수 증감({days}일)", "영상 수", f"업로드 수({days}일)", "최근 영상", "최근 영상 게시일",
              "최근 영상 조회수", "통계 갱신 시각"]
    return _csv_response(rows, header, f"channels_{utc_now().strftime('%Y%m%d_%H%M')}.csv")


@router.get("/videos.csv")
def export_videos(group_id: int = 0, channel_id: int = 0, days: int = Query(30, ge=0, le=3650),
                  kind: str = "all", q: str = "", sort: str = "published"):
    with connect() as conn:
        items = query_videos(conn, group_id, channel_id, days, kind, q, sort)
    rows = [[
        v["title"], v["channel_title"], v["group_name"], f"https://www.youtube.com/watch?v={v['youtube_id']}",
        v["published_at"], "쇼츠" if v["is_short"] else "롱폼", v["duration_seconds"],
        v["view_count"], v["views_per_day"], v["view_delta"] if v["view_delta"] is not None else "",
        v["like_count"], v["comment_count"], v["ratio"] if v["ratio"] is not None else "",
    ] for v in items]
    header = ["제목", "채널", "그룹", "URL", "게시일", "유형", "길이(초)", "조회수", "조회수/일", "최근 증가",
              "좋아요", "댓글", "평소 대비 배수"]
    return _csv_response(rows, header, f"videos_{utc_now().strftime('%Y%m%d_%H%M')}.csv")

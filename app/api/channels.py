from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import re
import json
import io
import csv
import pandas as pd
from ..db import get_db
from ..models import Channel
from .youtube import YouTubeAPI, QuotaExceededException

router = APIRouter(prefix="/api/channels", tags=["channels"])


class BulkUpsertRequest(BaseModel):
    category_id: int
    channel_inputs: List[str]
    api_key: Optional[str] = None  # Optional: DB에서 자동 가져오기


def get_available_api_key(provided_key: Optional[str] = None) -> str:
    """사용 가능한 API 키 가져오기"""
    if provided_key:
        return provided_key

    # DB에서 사용 가능한 API 키 가져오기
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT api_key FROM api_keys
            WHERE is_active = 1 AND quota_exceeded = 0
            ORDER BY priority ASC, created_at ASC
            LIMIT 1
        """)
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=400,
                detail="사용 가능한 API 키가 없습니다. API 키를 추가하거나 쿼터를 초기화하세요."
            )

        return row[0]


def mark_api_key_quota_exceeded(api_key: str):
    """API 키를 쿼터 초과 상태로 표시"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE api_keys
            SET quota_exceeded = 1, updated_at = ?
            WHERE api_key = ?
        """, (datetime.now().isoformat(), api_key))
        conn.commit()


@router.get("/")
def get_channels(category_id: Optional[int] = None):
    """채널 목록 조회"""
    with get_db() as conn:
        cursor = conn.cursor()
        if category_id and category_id > 0:
            # 특정 카테고리의 채널만
            cursor.execute("""
                SELECT c.id, c.category_id, c.channel_input, c.channel_id, c.title,
                       c.description, c.subscriber_count, c.country, c.language_hint, c.is_active,
                       c.created_at, c.updated_at, cat.name as category_name
                FROM channels c
                LEFT JOIN categories cat ON c.category_id = cat.id
                WHERE c.category_id = ?
                ORDER BY c.created_at DESC
            """, (category_id,))
        else:
            # 모든 채널 (전체 탭)
            cursor.execute("""
                SELECT c.id, c.category_id, c.channel_input, c.channel_id, c.title,
                       c.description, c.subscriber_count, c.country, c.language_hint, c.is_active,
                       c.created_at, c.updated_at, cat.name as category_name
                FROM channels c
                LEFT JOIN categories cat ON c.category_id = cat.id
                ORDER BY c.created_at DESC
            """)
        rows = cursor.fetchall()

        channels = []
        for row in rows:
            channel_dict = {
                "id": row[0],
                "category_id": row[1],
                "channel_input": row[2],
                "channel_id": row[3],
                "title": row[4],
                "description": row[5],
                "subscriber_count": row[6],
                "country": row[7],
                "language_hint": row[8],
                "is_active": row[9],
                "created_at": row[10],
                "updated_at": row[11],
                "category_name": row[12]
            }
            channels.append(channel_dict)

        return {"channels": channels}


@router.post("/bulk_upsert")
def bulk_upsert_channels(data: BulkUpsertRequest):
    """
    채널 일괄 저장/업데이트

    1. 각 채널 입력을 channelId로 정규화
    2. YouTube API로 채널 정보 가져오기
    3. DB에 upsert (없으면 INSERT, 있으면 UPDATE)
    """
    if not data.channel_inputs:
        raise HTTPException(status_code=400, detail="채널 입력이 비어있습니다")

    # API 키 가져오기 (제공된 키 또는 DB에서 자동)
    api_key = get_available_api_key(data.api_key)
    youtube_api = YouTubeAPI(api_key)
    results = []
    errors = []

    for channel_input in data.channel_inputs:
        channel_input = channel_input.strip()
        if not channel_input:
            continue

        try:
            # 1. channelId 정규화
            channel_id = youtube_api.normalize_channel_input(channel_input)
            if not channel_id:
                errors.append({
                    "input": channel_input,
                    "error": "채널 ID를 찾을 수 없습니다"
                })
                continue

            # 2. 채널 정보 가져오기
            channel_info = youtube_api.get_channel_info(channel_id)
            if not channel_info:
                errors.append({
                    "input": channel_input,
                    "error": "채널 정보를 가져올 수 없습니다"
                })
                continue

            # 3. DB에 upsert
            with get_db() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                # 기존 채널 확인
                cursor.execute("""
                    SELECT id FROM channels
                    WHERE category_id = ? AND channel_id = ?
                """, (data.category_id, channel_id))
                existing = cursor.fetchone()

                if existing:
                    # UPDATE
                    cursor.execute("""
                        UPDATE channels
                        SET title = ?,
                            description = ?,
                            subscriber_count = ?,
                            country = ?,
                            updated_at = ?
                        WHERE category_id = ? AND channel_id = ?
                    """, (
                        channel_info["title"],
                        channel_info.get("description"),
                        channel_info["subscriber_count"],
                        channel_info.get("country"),
                        now,
                        data.category_id,
                        channel_id
                    ))
                    action = "updated"
                else:
                    # INSERT
                    cursor.execute("""
                        INSERT INTO channels (
                            category_id, channel_input, channel_id, title,
                            description, subscriber_count, country, is_active,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """, (
                        data.category_id,
                        channel_input,
                        channel_id,
                        channel_info["title"],
                        channel_info.get("description"),
                        channel_info["subscriber_count"],
                        channel_info.get("country"),
                        now,
                        now
                    ))
                    action = "created"

                conn.commit()

                results.append({
                    "input": channel_input,
                    "channel_id": channel_id,
                    "title": channel_info["title"],
                    "action": action
                })

        except QuotaExceededException as e:
            # API 키 쿼터 초과 처리
            mark_api_key_quota_exceeded(api_key)
            errors.append({
                "input": channel_input,
                "error": f"API 쿼터가 초과되었습니다: {str(e)}"
            })
            break  # 쿼터 초과 시 더 이상 진행하지 않음
        except Exception as e:
            errors.append({
                "input": channel_input,
                "error": str(e)
            })

    return {
        "success": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }


@router.put("/{channel_id}/toggle_active")
def toggle_channel_active(channel_id: int):
    """채널 활성/비활성 토글"""
    with get_db() as conn:
        cursor = conn.cursor()

        # 현재 상태 확인
        cursor.execute("SELECT is_active FROM channels WHERE id = ?", (channel_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        current_status = row[0]
        new_status = 0 if current_status == 1 else 1

        # 상태 업데이트
        cursor.execute("""
            UPDATE channels
            SET is_active = ?, updated_at = ?
            WHERE id = ?
        """, (new_status, datetime.now().isoformat(), channel_id))
        conn.commit()

        return {
            "success": True,
            "channel_id": channel_id,
            "is_active": new_status
        }


@router.delete("/{channel_id}")
def delete_channel(channel_id: int):
    """채널 삭제"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM channels WHERE id = ?", (channel_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        conn.commit()

        return {"success": True, "message": "채널이 삭제되었습니다"}


class MoveChannelRequest(BaseModel):
    new_category_id: int


class BulkMoveChannelsRequest(BaseModel):
    channel_ids: List[int]
    new_category_id: int


@router.put("/bulk/move_category")
async def bulk_move_channels(request: Request, data: BulkMoveChannelsRequest):
    """여러 채널을 다른 카테고리로 한번에 이동"""
    try:
        if not data.channel_ids:
            raise HTTPException(status_code=400, detail="이동할 채널을 선택하세요")

        if not data.new_category_id:
            raise HTTPException(status_code=400, detail="이동할 카테고리를 선택하세요")

        with get_db() as conn:
            cursor = conn.cursor()

            # 카테고리 존재 확인
            cursor.execute("SELECT id FROM categories WHERE id = ?", (data.new_category_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")

            # 각 채널 이동
            moved_count = 0
            for channel_id in data.channel_ids:
                cursor.execute("""
                    UPDATE channels
                    SET category_id = ?, updated_at = ?
                    WHERE id = ?
                """, (data.new_category_id, datetime.now().isoformat(), channel_id))
                if cursor.rowcount > 0:
                    moved_count += 1

            conn.commit()

            return {
                "success": True,
                "moved_count": moved_count,
                "total_requested": len(data.channel_ids),
                "new_category_id": data.new_category_id
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"채널 이동 중 오류 발생: {str(e)}")


class BulkDeleteChannelsRequest(BaseModel):
    channel_ids: List[int]


@router.delete("/bulk/delete")
def bulk_delete_channels(data: BulkDeleteChannelsRequest):
    """여러 채널을 한번에 삭제"""
    with get_db() as conn:
        cursor = conn.cursor()

        deleted_count = 0
        for channel_id in data.channel_ids:
            cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
            if cursor.rowcount > 0:
                deleted_count += 1

        conn.commit()

        return {
            "success": True,
            "deleted_count": deleted_count,
            "total_requested": len(data.channel_ids)
        }


@router.put("/{channel_id}/move_category")
def move_channel_category(channel_id: int, data: MoveChannelRequest):
    """채널을 다른 카테고리로 이동"""
    with get_db() as conn:
        cursor = conn.cursor()

        # 채널 존재 확인
        cursor.execute("SELECT id FROM channels WHERE id = ?", (channel_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        # 카테고리 존재 확인
        cursor.execute("SELECT id FROM categories WHERE id = ?", (data.new_category_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")

        # 카테고리 변경
        cursor.execute("""
            UPDATE channels
            SET category_id = ?, updated_at = ?
            WHERE id = ?
        """, (data.new_category_id, datetime.now().isoformat(), channel_id))
        conn.commit()

        return {
            "success": True,
            "channel_id": channel_id,
            "new_category_id": data.new_category_id
        }


class RefreshChannelRequest(BaseModel):
    api_key: Optional[str] = None


@router.post("/{channel_id}/refresh")
def refresh_channel_info(channel_id: int, data: RefreshChannelRequest):
    """채널 정보 새로고침 (구독자수, 설명 등 업데이트)"""
    # API 키 가져오기
    api_key = get_available_api_key(data.api_key)
    youtube_api = YouTubeAPI(api_key)

    with get_db() as conn:
        cursor = conn.cursor()

        # 채널 조회
        cursor.execute("""
            SELECT channel_id FROM channels WHERE id = ?
        """, (channel_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        youtube_channel_id = row[0]

        try:
            # YouTube API로 최신 정보 가져오기
            channel_info = youtube_api.get_channel_info(youtube_channel_id)
            if not channel_info:
                raise HTTPException(status_code=404, detail="채널 정보를 가져올 수 없습니다")

            # DB 업데이트
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE channels
                SET title = ?,
                    description = ?,
                    subscriber_count = ?,
                    country = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                channel_info["title"],
                channel_info.get("description"),
                channel_info["subscriber_count"],
                channel_info.get("country"),
                now,
                channel_id
            ))
            conn.commit()

            return {
                "success": True,
                "title": channel_info["title"],
                "description": channel_info.get("description"),
                "subscriber_count": channel_info["subscriber_count"],
                "country": channel_info.get("country")
            }

        except QuotaExceededException as e:
            mark_api_key_quota_exceeded(api_key)
            raise HTTPException(status_code=429, detail=f"API 쿼터가 초과되었습니다: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"채널 정보 업데이트 실패: {str(e)}")


def extract_youtube_identifiers_from_text(text: str) -> set:
    """텍스트에서 YouTube URL, 채널ID, 핸들 추출"""
    # YouTube URL 패턴
    url_patterns = [
        r'https?://(?:www\.)?youtube\.com/channel/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtube\.com/@([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtube\.com/c/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtube\.com/user/([a-zA-Z0-9_-]+)',
    ]

    # 채널 ID 패턴 (UC로 시작하는 24자)
    channel_id_pattern = r'\b(UC[a-zA-Z0-9_-]{22})\b'

    # 핸들 패턴 (@로 시작)
    handle_pattern = r'@([a-zA-Z0-9_-]+)'

    identifiers = set()

    # URL 매칭
    for pattern in url_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            identifiers.add(match.group(0))

    # 채널 ID 매칭
    matches = re.finditer(channel_id_pattern, text)
    for match in matches:
        identifiers.add(match.group(1))

    # 핸들 매칭 (URL이 아닌 경우만)
    matches = re.finditer(handle_pattern, text)
    for match in matches:
        full_match = match.group(0)
        # URL 패턴에 이미 포함되지 않은 경우만 추가
        if not any(full_match in identifier for identifier in identifiers):
            identifiers.add(full_match)

    return identifiers


def parse_file_content(content: bytes, filename: str) -> str:
    """파일 형식에 따라 텍스트 추출"""
    file_ext = filename.lower().split('.')[-1]

    try:
        if file_ext in ['md', 'txt']:
            # Markdown/텍스트 파일
            return content.decode('utf-8')

        elif file_ext == 'csv':
            # CSV 파일
            df = pd.read_csv(io.BytesIO(content), header=None)
            # 모든 셀을 문자열로 변환하여 합치기
            text_parts = []
            for col in df.columns:
                text_parts.extend(df[col].astype(str).tolist())
            return ' '.join(text_parts)

        elif file_ext in ['xlsx', 'xls']:
            # Excel 파일
            df = pd.read_excel(io.BytesIO(content), header=None)
            # 모든 셀을 문자열로 변환하여 합치기
            text_parts = []
            for col in df.columns:
                text_parts.extend(df[col].astype(str).tolist())
            return ' '.join(text_parts)

        else:
            raise ValueError(f"지원하지 않는 파일 형식: {file_ext}")

    except Exception as e:
        raise ValueError(f"파일 파싱 오류: {str(e)}")


@router.post("/upload_md")
async def upload_md_file(
    file: UploadFile = File(...),
    category_id: int = Form(...),
    api_key: Optional[str] = Form(None)
):
    """
    파일에서 YouTube URL/채널ID/핸들 추출하여 채널 등록
    지원 형식: MD, TXT, CSV, Excel (xlsx, xls)
    """
    # 파일 내용 읽기
    content = await file.read()

    # 파일 형식에 따라 텍스트 추출
    try:
        text = parse_file_content(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # YouTube 식별자 추출
    identifiers = extract_youtube_identifiers_from_text(text)

    if not identifiers:
        raise HTTPException(status_code=400, detail="파일에서 YouTube URL, 채널ID, 핸들을 찾을 수 없습니다")

    # API 키 가져오기
    api_key = get_available_api_key(api_key)
    youtube_api = YouTubeAPI(api_key)

    results = []
    errors = []

    for identifier in identifiers:
        try:
            # 식별자를 channelId로 정규화
            channel_id = youtube_api.normalize_channel_input(identifier)
            if not channel_id:
                errors.append({
                    "input": identifier,
                    "error": "채널 ID를 찾을 수 없습니다"
                })
                continue

            # 채널 정보 가져오기
            channel_info = youtube_api.get_channel_info(channel_id)
            if not channel_info:
                errors.append({
                    "input": identifier,
                    "error": "채널 정보를 가져올 수 없습니다"
                })
                continue

            # DB에 upsert
            with get_db() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                # 기존 채널 확인
                cursor.execute("""
                    SELECT id FROM channels
                    WHERE category_id = ? AND channel_id = ?
                """, (category_id, channel_id))
                existing = cursor.fetchone()

                if existing:
                    # UPDATE
                    cursor.execute("""
                        UPDATE channels
                        SET title = ?,
                            description = ?,
                            subscriber_count = ?,
                            country = ?,
                            updated_at = ?
                        WHERE category_id = ? AND channel_id = ?
                    """, (
                        channel_info["title"],
                        channel_info.get("description"),
                        channel_info["subscriber_count"],
                        channel_info.get("country"),
                        now,
                        category_id,
                        channel_id
                    ))
                    action = "updated"
                else:
                    # INSERT
                    cursor.execute("""
                        INSERT INTO channels (
                            category_id, channel_input, channel_id, title,
                            description, subscriber_count, country, is_active,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """, (
                        category_id,
                        identifier,
                        channel_id,
                        channel_info["title"],
                        channel_info.get("description"),
                        channel_info["subscriber_count"],
                        channel_info.get("country"),
                        now,
                        now
                    ))
                    action = "created"

                conn.commit()

                results.append({
                    "input": identifier,
                    "channel_id": channel_id,
                    "title": channel_info["title"],
                    "action": action
                })

        except QuotaExceededException as e:
            mark_api_key_quota_exceeded(api_key)
            errors.append({
                "input": identifier,
                "error": f"API 쿼터가 초과되었습니다: {str(e)}"
            })
            break
        except Exception as e:
            errors.append({
                "input": identifier,
                "error": str(e)
            })

    return {
        "success": len(results),
        "failed": len(errors),
        "identifiers_found": len(identifiers),
        "results": results,
        "errors": errors
    }


@router.get("/export/csv")
def export_channels_csv(category_id: Optional[int] = None):
    """채널 목록을 CSV 파일로 내보내기"""
    with get_db() as conn:
        cursor = conn.cursor()

        if category_id and category_id != 0:
            cursor.execute("""
                SELECT c.title, c.channel_id, c.subscriber_count, c.country,
                       cat.name as category_name
                FROM channels c
                LEFT JOIN categories cat ON c.category_id = cat.id
                WHERE c.category_id = ?
                ORDER BY c.title
            """, (category_id,))
        else:
            cursor.execute("""
                SELECT c.title, c.channel_id, c.subscriber_count, c.country,
                       cat.name as category_name
                FROM channels c
                LEFT JOIN categories cat ON c.category_id = cat.id
                ORDER BY c.title
            """)

        rows = cursor.fetchall()

    # CSV 생성
    output = io.StringIO()
    writer = csv.writer(output)

    # 헤더
    writer.writerow(["채널명", "채널ID", "구독자수", "국가", "카테고리"])

    # 데이터
    for row in rows:
        title, channel_id, subscriber_count, country, category_name = row
        writer.writerow([
            title or "",
            f"https://www.youtube.com/channel/{channel_id}",
            subscriber_count or 0,
            country or "",
            category_name or ""
        ])

    # UTF-8 BOM으로 인코딩 (Excel에서 한글 깨짐 방지)
    csv_bytes = output.getvalue().encode('utf-8-sig')

    filename = f"channels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

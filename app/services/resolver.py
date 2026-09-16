"""사용자 입력(URL / @핸들 / 채널 ID / 영상 URL)을 YouTube 채널 ID로 변환"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from .youtube import YouTubeClient, YouTubeError, AllKeysExhausted

CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")
HANDLE_RE = re.compile(r"^@?([\w.\-]{3,30})$")


@dataclass
class Parsed:
    kind: str          # channel_id | handle | user | custom | video | name
    value: str
    raw: str


@dataclass
class Resolution:
    raw: str
    youtube_id: Optional[str] = None
    error: Optional[str] = None
    info: Optional[dict] = None
    note: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)


def parse_input(raw: str) -> Optional[Parsed]:
    text = raw.strip()
    if not text or text.startswith("#"):
        return None

    if CHANNEL_ID_RE.match(text):
        return Parsed("channel_id", text, raw)

    if text.startswith("@"):
        match = HANDLE_RE.match(text)
        return Parsed("handle", match.group(1), raw) if match else None

    looks_like_url = "youtube.com" in text or "youtu.be" in text or text.startswith(("http://", "https://"))
    if looks_like_url:
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        parsed = urlparse(text)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        segments = [s for s in path.split("/") if s]

        if host.endswith("youtu.be") and segments:
            return Parsed("video", segments[0], raw)

        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return Parsed("video", query["v"][0], raw)

        if not segments:
            return None
        head = segments[0]
        if head.startswith("@"):
            match = HANDLE_RE.match(head)
            return Parsed("handle", match.group(1), raw) if match else None
        if head == "channel" and len(segments) > 1:
            return Parsed("channel_id", segments[1], raw) if CHANNEL_ID_RE.match(segments[1]) else None
        if head == "c" and len(segments) > 1:
            return Parsed("custom", segments[1], raw)
        if head == "user" and len(segments) > 1:
            return Parsed("user", segments[1], raw)
        if head in ("shorts", "live", "embed", "v") and len(segments) > 1:
            return Parsed("video", segments[1], raw)
        if head == "watch":
            return None
        # youtube.com/이름 (레거시 커스텀 URL) → 핸들로 먼저 시도
        return Parsed("name", head, raw)

    match = HANDLE_RE.match(text)
    if match and " " not in text:
        return Parsed("name", match.group(1), raw)
    return None


def resolve_inputs(client: YouTubeClient, inputs: List[str]) -> List[Resolution]:
    """입력 목록을 채널 ID와 채널 정보로 변환 (API 호출 최소화)"""
    results: List[Resolution] = []
    parsed_list: List[Optional[Parsed]] = []
    for raw in inputs:
        parsed = parse_input(raw)
        parsed_list.append(parsed)
        results.append(Resolution(raw=raw))

    # 1) 영상 ID 는 한 번에 채널 ID 로 변환
    video_ids = [p.value for p in parsed_list if p and p.kind == "video"]
    video_map: Dict[str, str] = {}
    if video_ids:
        try:
            video_map = client.channel_ids_by_video_ids(video_ids)
        except AllKeysExhausted:
            raise
        except YouTubeError as exc:
            for res, p in zip(results, parsed_list):
                if p and p.kind == "video":
                    res.error = f"영상 조회 실패: {exc}"

    # 2) 항목별 채널 ID 결정
    for res, parsed in zip(results, parsed_list):
        if parsed is None:
            if res.raw.strip() and not res.raw.strip().startswith("#"):
                res.error = "채널 URL, @핸들, 채널 ID, 영상 URL 형식이 아닙니다"
            else:
                res.error = "빈 줄"
            continue
        if res.error:
            continue
        try:
            if parsed.kind == "channel_id":
                res.youtube_id = parsed.value
            elif parsed.kind == "video":
                res.youtube_id = video_map.get(parsed.value)
                if not res.youtube_id:
                    res.error = "영상을 찾을 수 없습니다 (삭제되었거나 비공개)"
            elif parsed.kind == "handle":
                res.youtube_id = client.channel_id_by_handle(parsed.value)
                if not res.youtube_id:
                    res.error = f"@{parsed.value} 핸들의 채널을 찾을 수 없습니다"
            elif parsed.kind == "user":
                res.youtube_id = client.channel_id_by_username(parsed.value)
                if not res.youtube_id:
                    res.error = f"사용자명 {parsed.value} 의 채널을 찾을 수 없습니다"
            elif parsed.kind in ("custom", "name"):
                res.youtube_id = client.channel_id_by_handle(parsed.value)
                if not res.youtube_id:
                    res.youtube_id = client.channel_id_by_username(parsed.value)
                if not res.youtube_id:
                    res.youtube_id = client.channel_id_by_search(parsed.value)
                    if res.youtube_id:
                        res.note = "검색으로 찾았습니다 (쿼터 100 units 사용). 결과가 맞는지 확인하세요."
                if not res.youtube_id:
                    res.error = f"'{parsed.value}' 에 해당하는 채널을 찾을 수 없습니다"
        except AllKeysExhausted:
            raise
        except YouTubeError as exc:
            res.error = str(exc)

    # 3) 채널 정보 일괄 조회
    ids = [r.youtube_id for r in results if r.youtube_id]
    if ids:
        try:
            infos = client.channels_by_ids(ids)
        except AllKeysExhausted:
            raise
        except YouTubeError as exc:
            for res in results:
                if res.youtube_id:
                    res.error = f"채널 정보 조회 실패: {exc}"
            return results
        for res in results:
            if res.youtube_id:
                info = infos.get(res.youtube_id)
                if info:
                    res.info = info
                else:
                    res.error = "YouTube에서 채널을 찾을 수 없습니다 (삭제 또는 비공개)"
                    res.youtube_id = None
    return results

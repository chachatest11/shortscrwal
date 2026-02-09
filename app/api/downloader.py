import os
import subprocess
from typing import Optional, Dict
from datetime import datetime
from pathlib import Path


class VideoDownloader:
    """yt-dlp를 사용한 비디오 다운로더"""

    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        Path(download_dir).mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        """파일명에서 특수문자 제거"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        return filename

    def download_video(
        self,
        video_id: str,
        channel_title: Optional[str] = None
    ) -> Dict:
        """
        단일 비디오 다운로드

        Returns:
            {
                "success": bool,
                "file_path": str or None,
                "error_message": str or None
            }
        """
        try:
            # 채널명 폴더 생성
            if channel_title:
                safe_channel = self._sanitize_filename(channel_title)
                output_dir = os.path.join(self.download_dir, safe_channel)
            else:
                output_dir = self.download_dir

            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # 출력 파일 경로
            output_template = os.path.join(output_dir, f"{video_id}.mp4")

            # yt-dlp 명령어
            command = [
                "yt-dlp",
                # 1080p 우선, 없으면 그 이하 화질 (세로 영상의 경우 height=1920이 1080p)
                "-f", "bestvideo[height<=1920]+bestaudio/best[height<=1920]",
                # 병합 출력 형식을 MP4로 지정
                "--merge-output-format", "mp4",
                # YouTube 제한 우회 (Android 클라이언트 사용)
                "--extractor-args", "youtube:player_client=android",
                # 모바일 User-Agent 사용
                "--user-agent", "com.google.android.youtube/17.36.4 (Linux; U; Android 12; GB) gzip",
                # 출력 파일 경로
                "-o", output_template,
                f"https://www.youtube.com/watch?v={video_id}"
            ]

            # 실행
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "file_path": output_template,
                    "error_message": None
                }
            else:
                return {
                    "success": False,
                    "file_path": None,
                    "error_message": result.stderr or "다운로드 실패"
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "file_path": None,
                "error_message": "다운로드 시간 초과 (5분)"
            }
        except Exception as e:
            return {
                "success": False,
                "file_path": None,
                "error_message": str(e)
            }

    def check_yt_dlp_installed(self) -> bool:
        """yt-dlp 설치 여부 확인"""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_video_info(self, video_id: str) -> Optional[Dict]:
        """비디오 정보 가져오기 (yt-dlp 사용)"""
        try:
            command = [
                "yt-dlp",
                "--dump-json",
                f"https://www.youtube.com/watch?v={video_id}"
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            return None

        except Exception:
            return None

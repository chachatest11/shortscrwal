@echo off
REM ChannelBoard 실행 스크립트 (Windows)
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.9 이상을 https://www.python.org/downloads/ 에서 설치하세요. "Add Python to PATH"를 체크하세요. & pause & exit /b 1)
if not exist venv (
    echo [1/3] 가상환경 생성 중...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo [2/3] 패키지 설치 확인 중...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if "%PORT%"=="" set PORT=8000
echo [3/3] 서버 시작: http://localhost:%PORT%   (종료: Ctrl + C)
start "" http://localhost:%PORT%
python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
pause

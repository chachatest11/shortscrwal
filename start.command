#!/bin/bash
# ChannelBoard 실행 스크립트 (macOS / Linux)
# - 가상환경(venv)이 없으면 만들고, 패키지를 설치한 뒤 서버를 띄웁니다.
# - 사용법: ./start.sh            (기본 포트 8000)
#           PORT=8001 ./start.sh  (다른 포트)
set -e
cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
        PY="$candidate"; break
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.9 이상이 필요합니다."
    echo "  macOS: 터미널에서  xcode-select --install  또는  brew install python  을 실행한 뒤 다시 시도하세요."
    echo "  또는 https://www.python.org/downloads/ 에서 설치하세요."
    exit 1
fi

if [ ! -d venv ]; then
    echo "[1/3] 가상환경 생성 중..."
    "$PY" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "[2/3] 패키지 설치 확인 중..."
python -m pip install -q --disable-pip-version-check -r requirements.txt

PORT="${PORT:-8000}"
echo "[3/3] 서버 시작: http://localhost:${PORT}   (종료: Ctrl + C)"
if command -v open >/dev/null 2>&1; then
    (sleep 2 && open "http://localhost:${PORT}") >/dev/null 2>&1 &
fi
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"

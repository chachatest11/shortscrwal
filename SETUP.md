# 설치·실행 가이드 (처음부터)

## 0. 준비물 확인 (macOS 기준)

터미널(응용 프로그램 → 유틸리티 → 터미널)을 열고 아래를 입력합니다.

```bash
git --version
python3 --version
```

- `git`이 없다고 나오면: `xcode-select --install` 을 실행해 설치 창에서 "설치"를 누릅니다 (Python 3도 같이 설치됩니다).
- `python3`가 3.9보다 낮거나 없으면: <https://www.python.org/downloads/> 에서 최신 버전을 설치하거나, Homebrew가 있다면 `brew install python`.
- macOS에서는 `python`, `pip`가 아니라 **`python3`, `pip3`** 명령을 씁니다. (가상환경을 켠 뒤에는 `python`도 됩니다.)

Windows는 <https://www.python.org/downloads/> 에서 설치할 때 **"Add Python to PATH"** 를 꼭 체크하세요.

## 1. 폴더 만들고 코드 받기

원하는 위치(예: 홈 폴더)에서:

```bash
cd ~
git clone -b claude/gifted-dijkstra-kp7mxv https://github.com/chachatest11/shortscrwal.git channelboard
cd channelboard
```

`channelboard` 폴더가 생기고 그 안에 코드가 들어옵니다. (폴더 이름은 마음대로 바꿔도 됩니다.)
`-b claude/gifted-dijkstra-kp7mxv` 는 새 버전이 들어 있는 브랜치 이름이며, main에 합쳐진 뒤에는 생략해도 됩니다.

이미 이 저장소를 받아 둔 폴더가 있다면 그 폴더에서:

```bash
git fetch origin
git checkout claude/gifted-dijkstra-kp7mxv
git pull
```

## 2. 실행

```bash
./start.sh
```

처음 실행하면 가상환경을 만들고 패키지를 설치하느라 1~2분 걸립니다. 끝나면 브라우저가 자동으로 <http://localhost:8000> 을 엽니다.
Finder에서 `start.command`를 더블클릭해도 같은 동작을 합니다. Windows는 `start.bat`.

"권한이 없습니다(permission denied)"가 나오면 `chmod +x start.sh start.command` 를 한 번 실행하세요.

## 3. 첫 설정

첫 화면의 **시작하기** 카드를 따라갑니다.

1. **설정 → YouTube API 키**: [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 만들기 → "API 및 서비스 → 라이브러리"에서 *YouTube Data API v3* 사용 설정 → "사용자 인증 정보 → API 키" 만들기 → 복사해서 붙여넣기
2. **채널 관리 → 채널 추가**: 운영 채널 주소를 한 줄에 하나씩 (예: `https://www.youtube.com/@내채널`)
3. 오른쪽 위 **지금 업데이트**

## 4. 종료와 재실행

- 종료: 터미널에서 `Ctrl + C`
- 다시 실행: 폴더로 이동 후 `./start.sh` (또는 `start.command` 더블클릭)

## 5. 이전 버전(쇼츠 수집기)을 쓰던 경우

예전 폴더의 `app/database.db` 파일을 새 폴더의 `app/` 안에 복사한 뒤 처음 실행하면 채널·카테고리(→그룹)·API 키를 자동으로 가져옵니다.
이미 한 번 실행했다면 설정 → 데이터 → "이전 버전 데이터 가져오기"를 누르세요.

## 백그라운드에서 계속 돌리기 (자동 갱신용)

자동 갱신은 서버가 켜져 있을 때만 동작합니다. 터미널을 닫아도 유지하려면:

```bash
nohup ./start.sh > channelboard.log 2>&1 &
```

끄려면 `pkill -f "uvicorn app.main:app"`.

## 데이터 위치

- DB: `data/app.db` (자동 생성). 백업하려면 이 파일만 복사하면 됩니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `command not found: python` / `pip` | macOS는 `python3`, `pip3`를 씁니다. `./start.sh`를 쓰면 신경 쓸 필요 없습니다 |
| `pathspec ... did not match` | 그 폴더가 이 저장소가 아니거나 원격을 아직 안 받은 상태입니다. 1번처럼 새로 클론하거나 `git fetch origin` 후 다시 시도 |
| `ModuleNotFoundError: fastapi` | 가상환경이 꺼져 있습니다. `./start.sh`로 실행하거나 `source venv/bin/activate` 후 실행 |
| 포트가 이미 사용 중 | `PORT=8001 ./start.sh` |
| 키 추가 시 "키 확인 실패" | Google Cloud에서 *YouTube Data API v3*가 사용 설정됐는지, 키에 리퍼러/IP 제한이 없는지 |
| "API 쿼터 초과" | 설정 → API 키에서 사용량 확인. 키를 하나 더 추가하면 자동 교대. 쿼터는 태평양 시간 자정에 초기화 |
| 증감이 "기준 없음" | 갱신이 1회뿐입니다. 다음 갱신부터 표시됩니다 |
| 차트가 안 보임 | 이틀 이상 기록이 쌓여야 표시됩니다 |

# ChannelBoard — YouTube 다채널 운영 대시보드

운영 중인 여러 YouTube 채널의 **구독자 · 조회수 · 영상 수 · 최근 업로드 · 증감 · 추이**를 한 화면에서 보고,
업로드가 끊긴 채널, 구독자가 줄어드는 채널, 평소보다 잘 나가는 영상, 마일스톤 임박 같은 **운영 신호**를 자동으로 띄워 주는
로컬 실행형 웹 앱입니다. YouTube 공식 **Data API v3** 키 하나면 동작하며, 채널 50개를 갱신하는 데 API 쿼터 1 unit만 씁니다.

> 기획안: [docs/PLAN.md](docs/PLAN.md) · 참고한 서비스/오픈소스도 기획안 2장에 정리되어 있습니다.

## 화면

| 화면 | 내용 |
|---|---|
| **대시보드** | 기간(24시간/7일/30일/90일)·그룹 필터, KPI 5개(채널·총 구독자·총 조회수·총 영상·기간 업로드), 인사이트(업로드 공백·구독자 감소·급상승 영상·마일스톤·오늘 업로드), 최근 업로드 피드, 채널 현황 표(증감·30일 추이 스파크라인, 정렬) |
| **채널 상세** | KPI, 구독자 추이 차트, 일별 조회수 증가 차트, 일별 증감표(Social Blade 방식), 최근 영상 표(조회수/일·최근 증가·평소 대비 배수), 운영 메모 |
| **채널 관리** | 채널 URL/@핸들/채널 ID/영상 URL 일괄 추가, 그룹(내 채널·서브 채널·참고 채널 …), 인라인 그룹 변경·활성 토글, 일괄 이동/삭제, CSV |
| **영상** | 전체 채널 영상을 기간·유형(쇼츠/롱폼)·그룹·채널·정렬·검색으로 탐색, CSV |
| **설정** | API 키 여러 개(자동 교대, 오늘 사용량), 자동 갱신 주기, 채널당 최근 영상 수, 급상승/업로드 공백 기준, 테마, 이전 버전 데이터 가져오기, 갱신 기록 |

라이트/다크 테마, 모바일 레이아웃을 지원합니다.

## 요구 사항

- Python 3.9 이상 (macOS는 `python3`, Windows는 `python` 명령)
- YouTube Data API v3 키 ([만드는 방법](#youtube-api-키-만들기))
- 인터넷 연결 (YouTube API 호출용)

## 설치와 실행

가장 쉬운 방법은 시작 스크립트입니다. 가상환경 생성, 패키지 설치, 서버 실행, 브라우저 열기까지 한 번에 합니다.

```bash
git clone -b claude/gifted-dijkstra-kp7mxv https://github.com/chachatest11/shortscrwal.git channelboard
cd channelboard
./start.sh            # macOS / Linux  (Windows: start.bat 더블클릭)
```

(`-b claude/gifted-dijkstra-kp7mxv` 는 새 버전이 들어 있는 브랜치입니다. main에 합쳐진 뒤에는 생략해도 됩니다.)

macOS에서는 Finder에서 `start.command`를 더블클릭해도 됩니다. 이후에도 실행할 때마다 같은 스크립트를 쓰면 됩니다.

직접 실행하려면:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 <http://localhost:8000> 을 엽니다. 단계별 설명과 문제 해결은 [SETUP.md](SETUP.md)에 있습니다.

처음 열면 대시보드에 **시작하기** 카드가 뜹니다.

1. **설정 → YouTube API 키**에 키를 추가 (등록할 때 1 unit으로 동작을 확인합니다)
2. **채널 관리 → 채널 추가**에 운영 채널을 한 줄에 하나씩 붙여넣기
   - `https://www.youtube.com/@handle`, `https://www.youtube.com/channel/UC…`, `@handle`, `UC…`, 영상 링크(`watch?v=`, `youtu.be`, `/shorts/`) 모두 인식
3. 오른쪽 위 **지금 업데이트** — 구독자·조회수·최근 영상을 수집합니다

갱신할 때마다 통계 스냅샷이 쌓이고, 두 번째 갱신부터 기간 대비 증감과 추이가 표시됩니다.
자동 갱신(기본 6시간)을 켜 두면 브라우저를 닫아도 서버가 주기적으로 갱신합니다.

## YouTube API 키 만들기

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 만들거나 선택
2. **API 및 서비스 → 라이브러리**에서 *YouTube Data API v3* 를 사용 설정
3. **사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키**
4. 만든 키를 ChannelBoard **설정**에 추가

키마다 하루 10,000 units를 쓸 수 있습니다. 키를 여러 개 등록하면 하나가 쿼터를 다 쓸 때 자동으로 다음 키를 사용하고,
쿼터일(태평양 시간 자정)이 바뀌면 사용량이 자동으로 초기화됩니다.

### 쿼터 비용

| 작업 | 비용 |
|---|---|
| 채널 통계 갱신 (`channels.list`) | 채널 50개당 1 unit |
| 최근 영상 목록 (`playlistItems.list`) | 채널당 1 unit |
| 영상 통계 (`videos.list`) | 영상 50개당 1 unit |
| 채널 추가 | 채널당 약 1~3 units (커스텀 URL `/c/이름` 은 검색이 필요해 100 units) |

예: 채널 30개, 채널당 최근 영상 10개, 재수집 대상 영상 300개 → 1회 갱신 약 **37 units**. 6시간마다 갱신해도 하루 150 units 수준입니다.

## 인사이트 규칙

| 인사이트 | 규칙 (설정에서 조정 가능) |
|---|---|
| 업로드 공백 | 최신 영상이 N일(기본 7) 이상 지났거나 수집된 영상이 없음 |
| 구독자 감소 | 선택한 기간 시작 시점보다 구독자가 줄어듦 |
| 급상승 영상 | 채널의 최근 90일 영상 "조회수/일" 중앙값의 1.75배 이상, 또는 최근 두 갱신 사이 조회수 증가 상위 |
| 마일스톤 | 다음 라운드 숫자(1천·5천·1만·5만·10만·50만·100만…)의 95% 이상이거나 기간 내 달성 |
| 오늘 업로드 | 24시간 내 새 영상 |

"조회수/일"은 조회수 ÷ max(게시 후 경과일, 1)입니다.

## 프로젝트 구조

```
app/
  main.py                 FastAPI 앱, 정적 파일, 스케줄러 시작
  config.py               경로·상수·설정 규칙
  db.py                   SQLite 스키마·연결·설정
  util.py                 시간·숫자 유틸
  services/
    youtube.py            Data API 클라이언트 (키 자동 교대, 쿼터 집계)
    resolver.py           입력(URL/@핸들/ID/영상 링크) → 채널 ID
    refresh.py            갱신 엔진 (진행률, 실행 기록, 스냅샷 압축)
    insights.py           대시보드 데이터·인사이트 계산
    scheduler.py          자동 갱신 루프
    legacy_import.py      이전 버전(app/database.db) 데이터 가져오기
  routers/                REST API (overview, channels, groups, videos, refresh, keys, settings, export)
  static/                 프론트엔드 (index.html, css/, js/, vendor/chartjs)
docs/PLAN.md              기획안
tests/                    pytest (가짜 YouTube API)
data/app.db               런타임 DB (자동 생성, git 제외)
```

기술 스택: Python · FastAPI · SQLite · 바닐라 JavaScript(ES 모듈) · Chart.js 4 (MIT, 동봉). 빌드 도구가 필요 없습니다.

## API

모든 응답은 JSON입니다. 서버 실행 후 <http://localhost:8000/docs> 에서 전체 스키마를 볼 수 있습니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/overview?group_id&days` | 대시보드 데이터 (요약·채널·인사이트·최근 업로드) |
| GET / POST | `/api/channels` | 채널 목록 / 일괄 추가 `{inputs: [...], group_id}` |
| GET / PATCH / DELETE | `/api/channels/{id}` | 상세(`?days`) / 그룹·활성·메모 수정 / 삭제 |
| POST | `/api/channels/bulk` | `{ids, action: move|activate|deactivate|delete, group_id}` |
| GET | `/api/channels/{id}/history?days` · `/videos` | 일별 증감 · 영상 목록 |
| GET / POST / PATCH / DELETE | `/api/groups` | 그룹 CRUD, `POST /api/groups/reorder` |
| GET | `/api/videos?group_id&channel_id&days&kind&sort&q&limit&offset` | 영상 탐색 |
| POST / GET | `/api/refresh` · `/api/refresh/status` · `/api/refresh/runs` | 갱신 시작(`{scope: all|group|channel}`) · 진행 상태 · 기록 |
| GET / POST / PATCH / DELETE | `/api/keys` | API 키 관리, `POST /api/keys/{id}/test`, `/reset` |
| GET / PUT | `/api/settings` | 설정 조회/저장 `{values: {...}}`, `POST /api/settings/import-legacy` |
| GET | `/api/export/channels.csv` · `/api/export/videos.csv` | CSV 내보내기 |

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `CHANNELBOARD_DB` | `data/app.db` | SQLite 파일 위치 |
| `CHANNELBOARD_LEGACY_DB` | `app/database.db` | 이전 버전 DB 위치 (있으면 첫 실행 때 자동 가져오기) |
| `CHANNELBOARD_SCHEDULER` | `1` | `0`이면 자동 갱신 루프를 끔 |

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

테스트는 가짜 YouTube API 응답을 사용하므로 실제 키나 쿼터가 필요 없습니다.

## 이전 버전(쇼츠 수집기)에서 올라온 경우

기존 `app/database.db`가 있으면 첫 실행 때 카테고리 → 그룹, 채널, API 키, 통계 스냅샷을 자동으로 가져옵니다
(설정 → 데이터에서 다시 실행할 수도 있습니다). 쇼츠 수집·다운로드 기능은 이번 버전의 범위에서 제외했습니다.

## 알아둘 점

- 공개 API 키만 사용하므로 **공개 통계**(구독자·조회수·영상 수, 영상별 조회수·좋아요·댓글)만 다룹니다.
  시청 시간, 수익, 트래픽 소스, 유지율 같은 YouTube 애널리틱스 데이터는 채널 소유자 OAuth가 필요한 YouTube Analytics API 영역이라 포함되어 있지 않습니다.
- 채널 소유자가 구독자 수를 비공개로 설정한 채널은 "비공개"로 표시됩니다.
- 쇼츠 여부는 영상 길이(기본 180초 이하)로 판정합니다.
- 기간 내 업로드 수는 "채널당 최근 영상 수" 설정만큼만 수집하므로, 그보다 많이 올리는 채널은 설정값을 높이세요.

## 라이선스

개인·팀 운영 용도로 자유롭게 사용하세요. YouTube API 서비스 약관을 준수해야 합니다. Chart.js는 MIT 라이선스입니다.

# Assets to the Money

해외 양산형 쇼츠 채널의 영상을 수집하고 다운로드할 수 있는 웹 애플리케이션입니다.

## 주요 기능

- **채널 대시보드** (`/dashboard`): 운영 중인 여러 채널의 구독자·조회수·영상 수·최근 업로드를 한 화면에서 확인
  - 기간(24시간/7일/30일/90일) 대비 증감, 30일 구독자 추이, 기간 내 업로드 수, 업로드가 끊긴 채널 경고
  - "지금 업데이트" 한 번으로 모든 활성 채널 갱신 (채널 50개당 API 쿼터 1 unit), 자동 업데이트(10분/30분/1시간)
- **카테고리 관리**: 채널을 그룹별로 분류하여 관리
- **채널 저장**: YouTube 채널 URL, 핸들(@), 채널 ID를 DB에 영구 저장
- **실시간 영상 수집**: YouTube Data API v3를 통한 최신 쇼츠 메타데이터 수집
- **필터링 및 정렬**: 조회수 필터, 최신순/조회수순 정렬
- **일괄 다운로드**: 선택한 영상을 yt-dlp로 일괄 다운로드
- **다크 테마 UI**: 카드형 그리드 레이아웃

## 기술 스택

- **Backend**: Python, FastAPI
- **Frontend**: Jinja2, Vanilla JavaScript, Custom CSS
- **Database**: SQLite
- **Video Download**: yt-dlp
- **YouTube API**: YouTube Data API v3

## 요구사항

- Python 3.8+
- yt-dlp (영상 다운로드용)
- YouTube Data API v3 Key

## 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd shortscrwal
```

### 2. Python 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. yt-dlp 설치

**macOS (Homebrew):**
```bash
brew install yt-dlp
```

**Linux (apt):**
```bash
sudo apt install yt-dlp
```

또는 pip으로 설치:
```bash
pip install yt-dlp
```

**Windows:**
- [yt-dlp GitHub Releases](https://github.com/yt-dlp/yt-dlp/releases)에서 다운로드
- 실행 파일을 PATH에 추가

### 4. YouTube API Key 준비

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. "API 및 서비스" > "라이브러리"로 이동
4. "YouTube Data API v3" 검색 및 활성화
5. "사용자 인증 정보" > "사용자 인증 정보 만들기" > "API 키" 선택
6. 생성된 API 키 복사

## 실행 방법

### 서버 시작

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

또는:

```bash
cd app
python main.py
```

### 브라우저 접속

```
http://localhost:8000
```

## 사용 방법

### 1. API Key 입력
- 메인 화면 상단에 YouTube API Key 입력
- 입력한 키는 브라우저 로컬 스토리지에 저장됩니다

### 2. 카테고리 관리
- "카테고리 관리" 버튼 클릭
- 새 카테고리 추가, 수정, 삭제 가능
- 기본 카테고리는 자동 생성됩니다

### 3. 채널 등록
- 채널 입력란에 YouTube 채널 정보 입력 (여러 줄 가능)
- 지원 형식:
  - `https://youtube.com/@channelname`
  - `https://www.youtube.com/channel/UCxxxx`
  - `UCxxxx` (채널 ID 직접 입력)
- "검색" 버튼 클릭으로 채널 저장 및 영상 수집

### 4. 영상 검색 및 필터링
- 최대 영상 수 설정 (기본: 50개)
- 검색 후 정렬 방식 선택 (최신순/조회수순)
- 최소 조회수 필터 (만 단위)

### 5. 영상 다운로드
- 원하는 영상의 "영상추출" 체크박스 선택
- "선택 영상 다운로드" 버튼 클릭
- 다운로드된 파일은 `downloads/{채널명}/{video_id}.mp4` 경로에 저장

### 6. 채널 대시보드 (다채널 현황 한눈에 보기)
- 상단의 "📊 채널 대시보드" 버튼 또는 `http://localhost:8000/dashboard` 접속
- 운영 중인 채널을 먼저 메인 페이지에서 등록하세요 (예: "내 채널" 카테고리를 만들고 채널 URL/@핸들/채널 ID 입력)
- "🔄 지금 업데이트"를 누르면 YouTube Data API로 활성 채널 전체의 통계와 최근 영상을 가져와 저장합니다
  - 갱신할 때마다 통계 스냅샷이 쌓이며, 이 스냅샷으로 기간 대비 증감과 30일 추이를 계산합니다
  - 최초 1회 갱신 후에는 "기준 없음"으로 표시되고, 두 번째 갱신부터 증감이 표시됩니다
- 필터: 기간(24시간/7일/30일/90일), 카테고리, 정렬(구독자/증가량/최근 업로드/업로드 오래된순 등), 채널명 검색
- 채널 행을 클릭하면 최근 영상 목록(조회수/좋아요/댓글)이 펼쳐집니다
- "자동 업데이트"를 켜면 브라우저가 열려 있는 동안 주기적으로 갱신합니다 (페이지를 열어둔 경우에만 동작)
- 대시보드는 API 키 관리 모달의 활성 키를 자동으로 사용합니다 (키는 메인 페이지 "API 키 관리"에서 등록)

## 프로젝트 구조

```
shortscrwal/
├── app/
│   ├── main.py                 # FastAPI 메인 앱
│   ├── db.py                   # 데이터베이스 초기화 및 연결
│   ├── api/
│   │   ├── youtube.py          # YouTube API 유틸리티
│   │   ├── downloader.py       # yt-dlp 다운로더
│   │   ├── categories.py       # 카테고리 API 라우터
│   │   ├── channels.py         # 채널 API 라우터
│   │   ├── search.py           # 검색/수집 API 라우터
│   │   ├── downloads.py        # 다운로드 API 라우터
│   │   ├── settings.py         # 설정 API 라우터
│   │   ├── api_keys.py         # API 키 관리 라우터
│   │   └── dashboard.py        # 채널 대시보드 API 라우터
│   ├── models/
│   │   ├── category.py         # 카테고리 모델
│   │   ├── channel.py          # 채널 모델
│   │   ├── video.py            # 비디오 모델
│   │   └── download.py         # 다운로드 모델
│   ├── templates/
│   │   ├── base.html           # 베이스 템플릿
│   │   ├── index.html          # 메인 페이지
│   │   └── dashboard.html      # 채널 대시보드 페이지
│   ├── static/
│   │   ├── css/style.css       # 스타일시트
│   │   ├── css/dashboard.css   # 대시보드 스타일시트
│   │   ├── js/app.js           # JavaScript 클라이언트
│   │   └── js/dashboard.js     # 대시보드 클라이언트
│   └── database.db             # SQLite 데이터베이스
├── downloads/                  # 다운로드된 영상 저장 폴더
├── requirements.txt            # Python 패키지 목록
└── README.md                   # 프로젝트 문서
```

## 데이터베이스 스키마

### categories (카테고리)
- `id`: PRIMARY KEY
- `name`: 카테고리 이름 (UNIQUE)
- `created_at`: 생성 일시

### channels (채널)
- `id`: PRIMARY KEY
- `category_id`: 카테고리 ID (FK)
- `channel_input`: 사용자 입력값
- `channel_id`: YouTube 채널 ID
- `title`: 채널명
- `subscriber_count`: 구독자 수
- `subscriber_hidden`: 구독자 수 비공개 여부
- `country`: 국가
- `is_active`: 활성 상태
- `view_count`, `video_count`: 채널 총 조회수 / 영상 수 (대시보드 갱신 시 저장)
- `thumbnail_url`, `custom_url`, `uploads_playlist_id`, `published_at`: 채널 프로필 정보
- `stats_updated_at`: 대시보드 통계 마지막 갱신 일시
- `created_at`: 생성 일시
- `updated_at`: 수정 일시

### channel_snapshots (채널 통계 이력)
- `id`: PRIMARY KEY
- `channel_id`: YouTube 채널 ID
- `subscriber_count`, `view_count`, `video_count`: 갱신 시점의 통계
- `captured_at`: 갱신 일시
- 최근 2일은 모든 스냅샷을 보관하고, 그 이전은 채널별로 하루 1개만 남깁니다

### videos (영상)
- `id`: PRIMARY KEY
- `channel_id`: YouTube 채널 ID
- `video_id`: YouTube 영상 ID (UNIQUE)
- `title`: 영상 제목
- `published_at`: 업로드 일시
- `view_count`: 조회수
- `thumbnail_url`: 썸네일 URL
- `duration_seconds`: 영상 길이
- `is_short`: 쇼츠 여부
- `created_at`: 생성 일시
- `updated_at`: 수정 일시

### downloads (다운로드)
- `id`: PRIMARY KEY
- `video_id`: YouTube 영상 ID
- `status`: 상태 (queued/running/done/failed)
- `file_path`: 파일 경로
- `error_message`: 에러 메시지
- `created_at`: 생성 일시
- `updated_at`: 수정 일시

## API 엔드포인트

### 카테고리
- `GET /api/categories/` - 카테고리 목록 조회
- `POST /api/categories/` - 카테고리 생성
- `PUT /api/categories/{id}` - 카테고리 수정
- `DELETE /api/categories/{id}` - 카테고리 삭제

### 채널
- `GET /api/channels/` - 채널 목록 조회
- `POST /api/channels/bulk_upsert` - 채널 일괄 저장/업데이트
- `PUT /api/channels/{id}/toggle_active` - 채널 활성/비활성 토글
- `DELETE /api/channels/{id}` - 채널 삭제

### 검색/수집
- `POST /api/search/` - 영상 검색 및 수집
- `GET /api/search/videos` - 저장된 영상 조회

### 다운로드
- `POST /api/downloads/start` - 다운로드 시작
- `GET /api/downloads/status` - 다운로드 상태 조회
- `GET /api/downloads/file/{video_id}` - 파일 다운로드
- `GET /api/downloads/history` - 다운로드 히스토리

### 채널 대시보드
- `POST /api/dashboard/refresh` - 활성 채널 통계/최근 영상 갱신 (`category_id`, `include_videos`, `max_videos`)
- `GET /api/dashboard/overview?category_id=0&days=7` - 대시보드 데이터 (현재 통계, 기간 대비 증감, 최근 업로드, 30일 추이, 합계)
- `GET /api/dashboard/channels/{channel_id}/videos` - 채널의 최근 영상 목록 (DB)
- `GET /api/dashboard/channels/{channel_id}/history?days=30` - 채널 통계 스냅샷 이력 (DB)

## 주의사항

### YouTube API 쿼터
- YouTube Data API v3는 일일 쿼터 제한이 있습니다 (기본: 10,000 units/day)
- 쿼터를 초과하면 API 호출이 실패합니다
- 쇼츠 검색은 채널당 약 100-200 units 소모됩니다
- 대시보드 갱신은 저렴합니다: `channels.list`는 채널 50개당 1 unit, 최근 영상 수집은 채널당 1 unit + 영상 50개당 1 unit
  (예: 채널 30개 + 채널당 최근 영상 10개 = 약 37 units)

### 대시보드에서 볼 수 있는 것 / 없는 것
- 공개 API 키만으로 동작하므로 **공개 통계**(구독자 수, 총 조회수, 영상 수, 영상별 조회수/좋아요/댓글)만 조회합니다
- 시청 시간, 수익, 트래픽 소스, 시청자 유지율 같은 **YouTube 애널리틱스 데이터**는 채널 소유자 OAuth 인증이 필요한
  YouTube Analytics API 영역이라 현재 대시보드에는 포함되어 있지 않습니다

### 저작권 및 이용 약관
- **이 도구는 권한이 있는 콘텐츠만 다운로드하는 용도로 사용하세요**
- YouTube 서비스 약관을 준수하세요
- 타인의 저작권을 침해하지 마세요
- 교육, 연구, 백업 목적으로만 사용하세요

### yt-dlp 요구사항
- yt-dlp가 시스템에 설치되어 있어야 합니다
- ffmpeg가 설치되어 있으면 더 나은 품질로 다운로드할 수 있습니다

## 문제 해결

### "yt-dlp가 설치되어 있지 않습니다"
```bash
pip install yt-dlp
# 또는
brew install yt-dlp  # macOS
```

### "YouTube API Key가 필요합니다"
- Google Cloud Console에서 YouTube Data API v3를 활성화하고 API 키를 생성하세요

### "채널 ID를 찾을 수 없습니다"
- 채널 URL 형식을 확인하세요
- @핸들, 채널 ID (UCxxxx), 또는 전체 URL을 입력하세요

### 다운로드 실패
- 네트워크 연결을 확인하세요
- 영상이 비공개 또는 삭제되지 않았는지 확인하세요
- yt-dlp를 최신 버전으로 업데이트하세요: `pip install -U yt-dlp`

## 라이선스

이 프로젝트는 교육 및 연구 목적으로 제공됩니다. 저작권법과 YouTube 서비스 약관을 준수하여 사용하세요.

## 기여

버그 리포트나 기능 제안은 이슈로 등록해 주세요.

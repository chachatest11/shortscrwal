# 설치·실행 가이드

## 1. Python 확인

```bash
python --version      # 3.9 이상
```

Windows에서 `python`이 없으면 `py --version` 또는 `python3 --version`으로 확인하세요.

## 2. 가상환경 만들기 (최초 1회)

```bash
cd shortscrwal
python -m venv venv
```

## 3. 가상환경 활성화

- macOS / Linux: `source venv/bin/activate`
- Windows (PowerShell): `venv\Scripts\Activate.ps1`
- Windows (cmd): `venv\Scripts\activate.bat`

프롬프트 앞에 `(venv)`가 보이면 활성화된 것입니다.

## 4. 패키지 설치 (최초 1회, 이후 업데이트 시)

```bash
pip install -r requirements.txt
```

## 5. 서버 실행

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 코드를 고치면서 쓰려면 `--reload`를 붙이세요.
- 같은 네트워크의 다른 기기(휴대폰 등)에서 보려면 `--host 0.0.0.0`으로 실행하고 PC의 IP로 접속하세요.
  이 앱에는 로그인이 없으니 신뢰할 수 있는 네트워크에서만 여세요.
- 포트가 이미 사용 중이면 `--port 8001`처럼 바꾸세요.

## 6. 브라우저 접속

<http://localhost:8000>

첫 화면의 **시작하기** 카드를 따라가면 됩니다: API 키 등록 → 채널 추가 → 지금 업데이트.

## 7. 종료

터미널에서 `Ctrl + C`, 가상환경은 `deactivate`.

---

## 두 번째 실행부터

```bash
cd shortscrwal
source venv/bin/activate      # Windows: venv\Scripts\activate
python -m uvicorn app.main:app --port 8000
```

## 백그라운드에서 계속 돌리기 (자동 갱신용)

자동 갱신은 서버가 켜져 있을 때만 동작합니다.

- macOS / Linux: `nohup python -m uvicorn app.main:app --port 8000 > channelboard.log 2>&1 &`
- Windows: 작업 스케줄러에 "로그온 시" 실행으로 `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` 등록

## 데이터 위치

- DB: `data/app.db` (자동 생성). 백업하려면 이 파일만 복사하면 됩니다.
- 이전 버전 DB `app/database.db`가 있으면 첫 실행 때 채널·그룹·API 키를 자동으로 가져옵니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `ModuleNotFoundError: fastapi` | 가상환경이 활성화됐는지, `pip install -r requirements.txt`를 실행했는지 |
| 키 추가 시 "키 확인 실패" | Google Cloud에서 *YouTube Data API v3*가 사용 설정됐는지, 키 제한(HTTP 리퍼러/IP)이 걸려 있지 않은지 |
| "API 쿼터 초과" | 설정 → API 키에서 사용량 확인. 키를 하나 더 만들어 추가하면 자동으로 교대합니다. 쿼터는 태평양 시간 자정에 초기화 |
| 채널을 찾을 수 없음 | @핸들 철자, 채널 URL 형식 확인. 영상 링크를 붙여넣어도 됩니다 |
| 증감이 "기준 없음" | 아직 갱신이 1회뿐입니다. 다음 갱신부터 표시됩니다 |
| 차트가 안 보임 | 이틀 이상 기록이 쌓여야 표시됩니다 |

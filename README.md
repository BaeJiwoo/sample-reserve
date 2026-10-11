# 룸픽 · 회의실 예약

FastAPI + SQLite + HTML/CSS/JavaScript로 만든 독립 실행형 한국어 회의실 예약 샘플입니다. **이 폴더만 복사해 실행할 수 있습니다.** 한 서버에서 화면, 정적 파일, API를 제공하며 다른 프로젝트, 외부 API, CDN, 웹폰트, Node.js 빌드가 필요하지 않습니다. 최초 Python 의존성 설치에는 인터넷이 필요합니다.

## 로컬 실행

Python **3.12 이상**을 권장합니다. 다음 명령은 `roompick` 폴더에서 실행합니다.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements.lock
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

가상환경을 활성화하지 않고 실행하므로 PowerShell 실행 정책을 바꿀 필요가 없습니다. `python`을 찾지 못하면 Python을 설치한 후 터미널을 다시 열거나 설치된 Python 실행 파일의 전체 경로를 사용하세요.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -c requirements.lock
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 **http://127.0.0.1:8000**을 엽니다. `Ctrl+C`로 종료합니다. 개발 중 자동 재시작이 필요하면 실행 명령 끝에 `--reload`를 붙입니다.

이 작업 환경에는 `.venv`와 의존성이 이미 준비되어 있어 위의 서버 실행 명령만 실행하면 됩니다. 다른 컴퓨터로 복사할 때에는 `.venv`를 제외하고 새로 생성하세요.

## Docker 실행

Docker가 설치된 환경에서 실행합니다. 로컬 접근만 허용하도록 포트를 `127.0.0.1`에 연결합니다.

```bash
docker build -t roompick .
docker volume create roompick-data
docker run --rm --name roompick -p 127.0.0.1:8000:8000 -v roompick-data:/app/data roompick
```

http://127.0.0.1:8000 에 접속합니다. 중지는 별도 터미널에서 `docker stop roompick`으로 할 수 있습니다. 같은 `docker run` 명령으로 컨테이너를 다시 만들면 **동일한 볼륨에 저장된 예약이 유지됩니다.** 볼륨을 삭제하면 데이터도 삭제되므로 유지해야 합니다. 이미 로컬 서버가 8000번 포트를 사용 중이면 먼저 종료하거나 호스트 포트를 바꾸세요.

컨테이너는 일반 사용자로 실행되며 `/api/health`를 이용한 헬스 체크가 포함되어 있습니다. 실행 환경에 Docker가 없어 이미지 빌드와 컨테이너 실행은 직접 검증하지 못했습니다.

## 화면과 사용 방법

[데스크톱 화면](docs/screenshots/desktop.jpg) · [모바일 화면](docs/screenshots/mobile.jpg)

- 상단 날짜 영역에서 날짜를 고르거나 이전·다음·오늘 버튼으로 이동합니다.
- 포커스룸(4인), 아이디어룸(8인), 라운지룸(12인)의 이름, 시설, 일정을 표시합니다.
- 데스크톱은 세 회의실의 하루 일정을 나란히, 폭 620px 이하에서는 선택한 회의실 하나를 표시합니다.
- 빈 시간은 해당 회의실·날짜·30분 구간이 입력된 예약창을 엽니다. 예약 추가 버튼으로 직접 선택할 수도 있습니다.
- 예약 블록을 누르면 상세 정보를 봅니다. 예약 취소 → 확인창에서 취소 완료 후 시간이 즉시 다시 열립니다.
- 서울 시계를 항상 표시하며, 오늘 09:00~18:00에는 현재 시간선을 표시합니다. 지난 시간의 빈 슬롯은 비활성화됩니다.
- 완료·취소 토스트, 입력 오류, 시간 충돌, 빈 일정, 로딩, 서버 오류와 재시도를 처리합니다.
- 화면은 30초 간격 및 탭으로 돌아왔을 때 일정을 새로 조회합니다. 생성·취소 직후에는 즉시 갱신합니다.
- Tab/Shift+Tab, Enter/Space로 조작할 수 있습니다. 모달 내 포커스 순환, Escape로 닫기, 닫은 뒤 포커스 복귀를 지원합니다. 요청 중에는 닫기와 중복 제출을 잠급니다.

## 예약 규칙

모든 날짜·시간 계산은 **Asia/Seoul**을 기준으로 합니다. 서버 시간으로 화면 시계를 동기화하며 최종 판정은 서버에서 수행합니다.

| 항목 | 규칙 |
| --- | --- |
| 운영 시간 | 매일 09:00~18:00 |
| 시간 단위 | 시작·종료 모두 30분 단위 |
| 예약 길이 | 최소 30분, 최대 120분 |
| 과거 시간 | 시작 시각이 서버의 현재 시각보다 이르면 거부 |
| 경계 | 기존 종료 시각과 새 시작 시각이 같으면 허용 |
| 충돌 | 같은 회의실·날짜의 시간이 조금이라도 겹치면 거부 |
| 정원 | 1명 이상, 회의실 정원 이하의 정수 |
| 필수 입력 | 회의실, 날짜, 시작·종료 시간, 제목, 예약자, 참석 인원 |
| 입력 길이 | 제목 1~80자, 예약자 이름 1~30자. 앞뒤 공백 제거 |

UI 제한을 우회해 API를 직접 호출해도 규칙을 다시 검증합니다. 본문의 알 수 없는 필드, 소수·문자열·불리언 인원, 비정상 날짜와 시간도 거부합니다.

## 저장과 동시 요청

기본 DB는 **`roompick/data/roompick.sqlite3`**입니다. 실행 위치와 상관없이 프로젝트 폴더를 기준으로 잡습니다. 데이터 경로는 `ROOMPICK_DB` 환경변수로 바꿀 수 있습니다.

```powershell
$env:ROOMPICK_DB = 'C:\roompick-data\roompick.sqlite3'
```

- SQLite WAL 모드와 요청별 별도 DB 연결을 사용합니다.
- `BEGIN IMMEDIATE`로 쓰기 잠금을 먼저 획득하고, 충돌 검사와 예약 저장을 한 트랜잭션에서 수행합니다. 여러 서버 프로세스가 같은 DB 파일을 쓰는 경우에도 적용됩니다.
- 회의실·날짜·30분 슬롯 조합을 DB 기본키로 지정해 중복 슬롯을 추가로 방지합니다.
- 취소는 예약과 연결된 슬롯을 외래키 `ON DELETE CASCADE`로 한 번에 제거합니다.
- 충돌은 이해하기 쉬운 한국어 메시지와 HTTP 409를 반환합니다. 잠금 대기 5초를 넘으면 HTTP 503과 재시도 안내를 반환합니다.
- 첫 초기화에만 기본 회의실과 **첫 실행일의 서울 날짜에 예시 예약 6건**을 만듭니다. 예시는 과거에 생성된 예약을 표현하므로 첫 실행 시각보다 이전 구간도 있을 수 있습니다.
- 초기화 표식을 예약 수와 별도로 저장합니다. 재실행, 날짜 변경, 모든 예약 취소 이후에도 예시를 다시 만들거나 기존 데이터를 덮어쓰지 않습니다.
- `data/`와 SQLite 파일은 Git 및 Docker 빌드에서 제외됩니다. 백업할 때는 서버를 종료하고 `data` 디렉터리 전체를 복사하세요.

설계 참고: [SQLite 트랜잭션 문서](https://www.sqlite.org/lang_transaction.html), [FastAPI lifespan 문서](https://fastapi.tiangolo.com/advanced/events/).

## API

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| GET | `/api/schedule?date=YYYY-MM-DD` | 회의실·예약·서버 시간 통합 조회, 날짜 생략 시 서울의 오늘 |
| GET | `/api/rooms` | 회의실 목록 |
| GET | `/api/reservations?date=YYYY-MM-DD` | 날짜별 예약 목록 |
| GET | `/api/reservations/{id}` | 예약 상세 |
| POST | `/api/reservations` | 예약 생성, 성공 시 201 |
| DELETE | `/api/reservations/{id}` | 예약 취소, 성공 시 204 |
| GET | `/api/health` | DB 연결 및 서버 상태 |
| GET | `/openapi.json` | API 스키마 |

생성 요청 JSON 예시입니다. `date`는 실행하는 시점의 오늘 또는 미래 날짜로 바꿔 주세요.

```json
{
  "room_id": 1,
  "date": "2030-05-06",
  "start_time": "09:00",
  "end_time": "10:00",
  "title": "제품 아이디어 회의",
  "organizer": "테스트 사용자",
  "attendees": 4
}
```

입력 오류 422, 충돌 409, 없는 예약 404, 서버 오류 500/503의 응답 본문은 `{ "detail": "한국어 안내" }` 형태입니다. 대화형 API 문서는 외부 CDN 의존성을 없애기 위해 제공하지 않습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -c requirements.lock
.\.venv\Scripts\python.exe -m pytest -q
```

macOS/Linux는 Python 실행 경로를 `.venv/bin/python`으로 바꿉니다. 테스트마다 임시 DB를 사용하므로 실제 예약 데이터는 바뀌지 않습니다. 프로세스 통합 테스트는 사용 가능한 임시 로컬 포트에서 서버를 띄우며 종료 후 정리합니다.

임시 폴더나 로컬 소켓 접근이 제한된 샌드박스에서는 접근 가능한 테스트 경로와 로컬 서버 실행 권한이 필요합니다. 임시 경로 변경 예:

```powershell
New-Item -ItemType Directory -Force test-results | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp test-results/local-pytest
```

`--basetemp`는 pytest가 정리하는 테스트 전용 폴더만 지정하세요. 실제 데이터 폴더를 지정하면 안 됩니다.

### 확인한 결과

- **52개 자동 테스트 통과**: 생성·조회·상세·취소·즉시 재예약, 모든 필수 항목, 공백·길이·타입, 운영 시간·30분 단위·최대 2시간, 인원 제한, 모든 겹침 형태와 인접 경계.
- UTC와 서울 날짜가 다른 경우, 현재 시각과 정확히 같은 시작, 1초 지난 시작을 검증했습니다.
- 앱 인스턴스 2개에서 동시 요청 12건 → **1건 생성, 11건 충돌**.
- 실제 독립 서버 프로세스 2개에서 동시 HTTP 요청 10건 → **1건 생성, 9건 충돌**.
- 실제 서버 프로세스를 모두 종료한 후 재시작 → 예약 보존, 예시 중복 없음, 취소 후 재예약 확인.
- DB 잠금 오류 응답, DB 슬롯 중복 제약, 취소 시 슬롯 정리, SQLite 무결성을 확인했습니다.
- 브라우저에서 데스크톱과 모바일(390px, 320px), 빈 시간 자동 입력, 생성·상세·취소 확인/중단/완료, 정원 제한, 충돌 안내, 빈 날짜, 서버 중단·복구, 모달 포커스와 안전한 텍스트 표시를 확인했습니다.
- 테스트 시 사용한 Starlette에서 httpx TestClient 지원에 관한 사용 중단 예정 경고 1건이 표시됩니다. 테스트 실패나 앱 실행 오류는 아닙니다.

## 구성

```text
roompick/
├── app/main.py                 # API, DB 초기화, 트랜잭션, 서버 검증
├── static/                     # HTML, CSS, JS, 로컬 SVG 파비콘
├── tests/test_reservations.py   # API 및 동시성 테스트
├── tests/test_process_persistence.py # 실제 프로세스·재시작 테스트
├── requirements.txt            # 실행 의존성
├── requirements-dev.txt        # 테스트 의존성
├── requirements.lock           # 검증한 전체 의존성 버전 제약
├── Dockerfile
├── .dockerignore
├── .gitignore
├── pytest.ini
└── README.md
```

## 데모 범위와 제한

- 로그인과 권한 확인이 없습니다. 모든 사용자가 예약자 이름을 볼 수 있고 모든 예약을 취소할 수 있습니다. 실제 운영용 인증이나 개인정보 보호 모델을 갖춘 서비스가 아닙니다.
- 반복 예약, 이메일 알림, 관리자 화면, 예약 수정은 포함하지 않습니다. 변경은 취소 후 새 예약으로 처리합니다.
- 다른 사용자의 변경은 최대 30초 뒤 화면에 반영됩니다. 그 사이 충돌하는 요청은 서버에서 차단합니다.
- 단일 머신의 로컬 SQLite 파일을 사용하는 샘플입니다. 네트워크 공유 파일시스템이나 여러 머신에 DB 파일을 공유하는 운영 구성은 검증하지 않았습니다.
- Docker 및 실제 iOS/Android 기기 검증은 수행하지 못했습니다. 모바일 검증은 Chromium의 브라우저 뷰포트 변경으로 수행했습니다.
- 외부에 배포하지 않았습니다.

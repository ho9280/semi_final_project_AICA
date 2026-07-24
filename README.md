# semi_final_project_AICA

## 메뉴(식단) Agent

```python
from app.menu_agent_tool import get_menu

answer = get_menu("오늘 KT 메뉴 알려줘")
```

주간 식단표 이미지를 OCR로 읽어 업체·날짜·요일별 메뉴로 정리하고, 사용자
질문("오늘 KT 메뉴 뭐야?")에 답변하는 로컬 MVP입니다.

> 이 Menu Tool은 SQLite DB 없이 실제 식단표 이미지와 TXT를 원본으로
> 사용한다. 새로운 이미지가 들어오면 PaddleOCR와 Tesseract를 이용해 텍스트를
> 추출하고, 불확실한 필드는 다중 OCR 후보·문맥·기존 메뉴 용어를 바탕으로
> 최선의 값을 추정한다. 추정 여부와 신뢰도는 별도 OCR 메타데이터에 기록한다.
> OCR이 설치되지 않았거나 실패해도 기존 TXT 기반 메뉴 조회는 정상 동작한다.

### 가장 빠른 설치 방법

```powershell
uv sync
powershell -ExecutionPolicy Bypass -File scripts/setup_menu_ocr.ps1
powershell -ExecutionPolicy Bypass -File scripts/check_menu_ocr.ps1
```

`setup_menu_ocr.ps1`은 Tesseract-OCR 설치(winget), PaddlePaddle/PaddleOCR/
pytesseract 확인, `eng`/`kor`/`osd` 언어 모델 준비, 간단한 한국어 OCR 실행
확인까지 한 번에 처리합니다. 실패해도 아래 "OCR 없이 기존 TXT만 사용하는
방법"에 설명한 대로 기존 챗봇 기능은 그대로 동작합니다.

**원본 데이터는 관계형 DB가 아니라 `data/menu/` 폴더의 이미지 + 같은 이름의
`.txt`(sidecar) 파일입니다.** 최종 정의서 기준으로 메뉴 데이터를 별도의 DB
테이블로 관리하지 않기 때문에, Menu Tool을 기본값으로 실행해도 `menu.db`가
생기지 않습니다. 관리자가 새 식단표를 등록하는 절차도 "이미지 폴더에 파일을
넣고 `reload_menu_data()`를 부르는 것"뿐이라, 별도 DB 담당자가 없어도 됩니다.
(예전에 있던 SQLite 호환 코드는 실제 실행 경로 어디에서도 쓰이지 않아
완전히 제거했습니다. `MenuRepository`/`register_menu_image`는 더 이상 존재하지
않고, `menu.db`는 만들지도 참조하지도 않습니다.)

### 생성된 파일과 역할

Menu Agent의 Python 구현 원본은 `app/menu_agent_tool.py` 한 파일입니다
(과거 `app/menu/` 패키지의 `menu_data.py`/`menu_tool.py`/`__init__.py` 3개
파일을 이 파일 하나로 통합했고, 기존 패키지는 삭제했습니다). 다른 팀 코드는
이 파일이 공개하는 함수/Tool 객체만 사용하면 되고, 내부가 어떤 구역으로
나뉘어 있는지 알 필요가 없습니다.

| 파일/폴더 | 역할 |
|---|---|
| `app/menu_agent_tool.py` | **유일한 Python 구현 원본.** 구역: Configuration(경로·업체 목록·상수) / Data models / OCR and sidecar TXT loading(`MockOCRProvider`(기본), `TesseractOCRProvider`, `PaddleOCRProvider`, 경로 자동 탐색) / Menu text parsing(`parse_ocr_text`) / File-based storage(**기본 데이터 원본** `MenuFileStore`, `get_store()`, `reload_menu_data()`) / Embedding and vector search(`VectorStore`) / Query planning and search(`parse_query`, `plan_menu_search`, `hybrid_search_menu`, `query_menu`) / OCR import pipeline(`preview_menu_ocr`, `infer_menu_fields`, `import_menu_image`) / Public Tool interface(`get_menu`, `get_current_menu`, `reload_menu_data`, `check_ocr_status`, `handle_chat_message`, `menu_agent_tool`, `menu_current_tool`, `menu_image_import_tool`, `MENU_AGENT_TOOLS`, `MENU_ADMIN_TOOLS`, `ChatRequest`, `ChatResponse`, `menu_router`, `chat_endpoint`) |
| `app/main.py` | FastAPI 앱 진입점. `app/menu_agent_tool.py`의 `menu_router`(`POST /chat` 포함)를 `include_router`만 함 |
| `scripts/setup_menu_ocr.ps1` | 다른 팀원이 한 번만 실행하는 OCR 환경 자동 설치 스크립트 |
| `scripts/check_menu_ocr.ps1` | OCR 환경이 준비됐는지 읽기 전용으로 점검하는 스크립트 |
| `data/menu/{daesung,kt,kt_salad}/*.png,*.jpg` + 같은 이름의 `.txt` | **실제 운영 데이터.** 업체별 실제 주간 식단표 이미지와 그 내용을 옮겨 적은 sidecar 텍스트 (업체당 1세트) |
| `tests/menu/*` | pytest 테스트. 모두 `tmp_path`에 자체 더미 이미지를 만들어 쓰므로 `data/menu`의 실제 데이터를 읽거나 바꾸지 않음 |

### 환경설정

```bash
uv sync
```

`numpy`, `pillow`, `tzdata`(Windows에서 `zoneinfo` 사용을 위해 필요)가 의존성에 포함되어 있습니다.
`pytesseract`, `paddlepaddle`, `paddleocr`(선택적 실제 OCR용 Python 패키지)도
`pyproject.toml`에 포함되어 있어 `uv sync`로 함께 설치됩니다. 다만 Menu Tool의
기본 동작(`MockOCRProvider`, sidecar `.txt`)에는 필요하지 않으며, 실제로
Tesseract/PaddleOCR을 쓰려는 경우에만 아래 "OCR" 절의 준비가 필요합니다.
Tesseract는 Python 패키지와 별개로 **Windows 프로그램 설치가 추가로 필요**합니다.

### 챗봇 질의 vs 대시보드 자동 표시

이 프로젝트는 두 가지 서로 다른 목적의 조회를 분리해서 제공합니다.

| | `get_menu(query, now=None)` (챗봇) | `get_current_menu(now=None)` (대시보드) |
|---|---|---|
| 입력 | 사용자 질문 문자열 | 없음(시간만 기준) |
| 끼니 미지정 시 | **항상 점심(중식)** — 시각과 무관 | 시각대별로 달라짐(아래 표) |
| 날짜 미지정 시 | 항상 오늘 | 시각대별로 오늘/내일 |
| 업체 미지정 시 | 대성학원 + KT + KT 샐러드 모두 | 시각대별 업체 조합(아래 표) |

`get_current_menu()`(대시보드)의 시간대 기본값:

| 시각(KST) | 기본 끼니 | 기본 업체 |
|---|---|---|
| 00:00 ~ 12:59 | 당일 점심 | 대성학원 + KT + KT 샐러드 |
| 13:00 ~ 18:59 | 당일 저녁 | 대성학원만 (KT/KT 샐러드는 저녁 데이터 없음) |
| 19:00 ~ 23:59 | 다음날 점심 | 대성학원 + KT + KT 샐러드 |

두 함수 모두 조회 결과가 없으면 다른 날짜/업체 메뉴로 대체하지 않고
`"해당 날짜에는 등록된 식단이 없습니다."`를 반환합니다. 외부 공휴일 API는
쓰지 않으므로, 주말/공휴일처럼 데이터가 없는 날짜는 이 안내를 그대로 받게 됩니다.

### 끼니 동의어

사용자가 끼니를 다르게 표현해도 같은 결과를 받도록 동의어를 표준값으로
정규화합니다 (`app/menu_agent_tool.py`의 `MEAL_TYPE_SYNONYMS`). SQLite/파일 저장소
모두 이 표준값으로 조회됩니다.

- `점심`, `중식`, `런치` -> `점심`
- `저녁`, `석식`, `디너` -> `저녁`
- `아침`, `조식` -> `아침`

### 원본 이미지 위치와 파일명 규칙

`data/menu/kt/`, `data/menu/daesung/`, `data/menu/kt_salad/` 폴더에 업체별 이미지를 넣습니다.
지원 확장자: `.png`, `.jpg`, `.jpeg`. 이미지와 **같은 이름**의 `.txt` 파일이 있어야
해당 이미지가 조회 가능한 데이터로 인식됩니다.

```
data/menu/kt/kt_menu_2026-07-20_2026-07-26.jpg   <- 이미지
data/menu/kt/kt_menu_2026-07-20_2026-07-26.txt   <- 같은 이름의 sidecar 텍스트
```

현재 저장소에는 업체별 실제 주간 식단표 1세트만 커밋되어 있습니다. 테스트용
더미 이미지는 `data/menu/`에 두지 않고, 각 테스트가 `tmp_path`에 그때그때
만들어 씁니다(아래 "테스트 실행 방법" 참고). `data/menu/`에 이미지를 추가로
넣을 때는 이 실제 운영 데이터와 섞이지 않도록 주의해 주세요.

`.txt` 파일의 각 줄은 다음 형식을 따라야 파서가 인식합니다.

```
2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치
```

- 항목 구분자로 쉼표(`,`), 가운뎃점(`·`), 슬래시(`/`)를 쓸 수 있습니다. 메뉴
  이름 안에 이 문자들이 들어가야 한다면(예: "분짜(돼지불고기 쌀국수)") 쉼표 대신
  공백으로 묶어 하나의 항목처럼 보이게 적어주세요.
- 파일 인코딩은 UTF-8이어야 합니다.

### OCR: 기본은 sidecar 텍스트, 실제 엔진(Tesseract/PaddleOCR)은 선택 사항

Menu Tool의 **기본 데이터 원본은 여전히 사람이 검수한 sidecar `.txt`**입니다
(`MockOCRProvider`). `reload_menu_data()`/`get_menu()`/`get_current_menu()`는
Provider를 지정하지 않으면 이 방식을 그대로 씁니다. 실제 OCR 엔진 결과를
사람이 검수 없이 바로 메뉴로 등록하지 않는 이유는, OCR이 "날짜 요일 끼니:
항목..." 형식으로 자동 구조화해 주지 않기 때문입니다(아래 한계 참고).

`app/menu_agent_tool.py`의 `OCRProvider` 인터페이스를 구현하면 다른 OCR
엔진으로 교체할 수 있습니다. 이 프로젝트에는 이미 두 가지 실제 엔진 Provider가
구현돼 있고, 관련 Python 패키지도 `pyproject.toml`에 포함되어 있습니다.

| Provider | 엔진 | 특징 |
|---|---|---|
| `MockOCRProvider` | 없음(사람이 검수한 sidecar `.txt`) | **기본값.** 안정적이고 재현 가능 |
| `TesseractOCRProvider` | Tesseract 5 (`pytesseract`) | 가볍고 빠름, 별도 프로그램 설치 필요 |
| `PaddleOCRProvider` | PaddleOCR | 한국어 인식·복잡한 표 레이아웃에 강점, Python 패키지만 설치하면 됨 |

```python
from app.menu_agent_tool import PaddleOCRProvider, TesseractOCRProvider, reload_menu_data

# 실제 엔진으로 다시 스캔하고 싶을 때만 provider를 지정한다.
reload_menu_data(ocr_provider=PaddleOCRProvider())
# 또는
reload_menu_data(ocr_provider=TesseractOCRProvider(lang="kor+eng"))
```

**Tesseract 5 준비 (Windows)** — 아래 3가지를 구분해서 준비해야 합니다.

1. Python 패키지: `pytesseract` (이미 `pyproject.toml`에 포함, `uv sync`로 설치됨)
2. 별도 프로그램 설치: [Tesseract-OCR(Windows, UB-Mannheim 배포판)](https://github.com/UB-Mannheim/tesseract/wiki) 5.x + 한국어 언어팩(`kor.traineddata`)
   ```powershell
   winget install --id UB-Mannheim.TesseractOCR -e
   ```
   설치 폴더(`Program Files`)에 관리자 권한 없이 언어팩을 추가할 수 없다면,
   `eng.traineddata`/`kor.traineddata`(공식 [tessdata 저장소](https://github.com/tesseract-ocr/tessdata))를
   사용자 폴더(예: `%LOCALAPPDATA%\tessdata`)에 모아두고 `TESSDATA_PREFIX`로 가리키면 됩니다.
3. 환경변수 설정(선택): `tesseract.exe`가 PATH에 없으면 `TESSERACT_CMD`에 실행 파일 전체 경로를,
   언어팩을 기본 폴더가 아닌 곳에 두었으면 `TESSDATA_PREFIX`에 그 폴더 경로를 지정합니다.

`find_tesseract_cmd()`가 `TESSERACT_CMD` -> PATH -> Windows 기본 설치 경로
순으로 자동 탐색하므로, 개인 PC의 절대경로를 코드에 고정하지 않아도 됩니다.
찾지 못하면 어떻게 해결해야 하는지 알려주는 에러를 반환합니다.

**PaddleOCR 준비** — Python 패키지(`paddlepaddle`, `paddleocr`, 둘 다
`pyproject.toml`에 포함)만 설치하면 됩니다. 별도 프로그램 설치는 필요
없습니다. 텍스트 검출/인식 모델은 **처음 실행할 때 자동으로 다운로드**되어
로컬 캐시에 저장되고, 이후에는 다시 받지 않습니다(인터넷 연결은 첫 실행
시점에만 필요). 이번 MVP는 GPU 없이 CPU로 동작하도록 구성했습니다(GPU가
없는 다른 팀원 PC에서도 동일하게 동작).

**CPU 전용, GPU는 선택 사항**: 이 프로젝트는 PaddlePaddle CPU 배포판으로
구성했습니다. GPU가 없는 팀원 PC에서도 동일하게 동작하며, GPU를 쓰고 싶다면
`paddlepaddle-gpu`로 직접 교체할 수 있지만 이번 MVP의 기본 경로는 아닙니다.

**환경변수와 자동 경로 탐색**: 개인 PC의 절대경로를 코드에 고정하지
않습니다. 실행 시점에 다음 순서로 자동 탐색합니다.

- Tesseract 실행 파일: `TESSERACT_CMD` 환경변수 -> 시스템 PATH -> Windows
  기본 설치 경로(`C:\Program Files\Tesseract-OCR\tesseract.exe` 등)
- 언어팩(tessdata) 폴더: `TESSDATA_PREFIX` 환경변수 -> 사용자 OCR 캐시 폴더
  (`%LOCALAPPDATA%\tessdata`, `scripts/setup_menu_ocr.ps1`이 여기에 준비함)
  -> Tesseract 자체 기본 tessdata 폴더

**모델 캐시 위치**: PaddleOCR 모델은 `%USERPROFILE%\.paddlex\official_models`에
캐시됩니다(첫 실행 시 자동 다운로드, 이후 재사용). Tesseract 언어팩은
`%LOCALAPPDATA%\tessdata`에 캐시됩니다. 둘 다 Git에 커밋하지 않습니다.

### `check_ocr_status()` — OCR 환경 점검

```python
from app.menu_agent_tool import check_ocr_status

status = check_ocr_status()
# {
#   "paddleocr_available": True, "paddlepaddle_available": True,
#   "pytesseract_available": True, "tesseract_available": True,
#   "tesseract_version": "tesseract v5.4.0.20240606",
#   "tesseract_executable_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
#   "languages": {"kor": True, "eng": True, "osd": True},
#   "tessdata_prefix": "C:\\Users\\...\\AppData\\Local\\tessdata",
#   "pillow_available": True, "opencv_available": True,
#   "paddleocr_model_cache_dir": "C:\\Users\\...\\.paddlex\\official_models",
#   "paddle_ready": True, "tesseract_ready": True, "any_engine_ready": True,
#   "errors": [], "resolutions": [],
# }
```

패키지·프로그램이 하나도 없어도 예외 없이 위 구조를 반환하며, `errors`/
`resolutions`에 무엇이 없고 어떻게 해결해야 하는지 안내합니다.

### `preview_menu_ocr()` — 이미지 하나 미리 읽어보기 (읽기 전용)

```python
from app.menu_agent_tool import preview_menu_ocr

result = preview_menu_ocr("data/menu/kt/new_menu.png")
# {"success": True, "image_path": "...", "paddle_text": "...", "tesseract_text": "...",
#  "selected_text": "...", "agreement": True, "confidence": 0.93,
#  "preview_path": "data/_ocr_previews/new_menu_preview.png", "warnings": [], "error": None}
```

PaddleOCR와 Tesseract(`kor+eng`)를 모두 실행해 비교하고, 미리보기 이미지를
`data/_ocr_previews/`(Git 제외)에 저장합니다. 실제 메뉴 데이터에는 아무
영향을 주지 않습니다 — 등록 전에 결과를 먼저 확인하고 싶을 때 씁니다.

### `import_menu_image()` — 이미지 하나로 자동 등록

```python
from app.menu_agent_tool import import_menu_image, get_menu

result = import_menu_image("data/menu/kt/new_menu.png")
answer = get_menu("오늘 KT 메뉴 알려줘")
```

흐름: 이미지 검사 -> 업체/기간 판별 -> PaddleOCR+Tesseract 실행 -> 결과 비교
-> 불확실한 필드 추정 -> 임시 위치에 TXT/메타데이터 생성 -> `menu_parser`로
검증 -> **검증을 통과한 경우에만** 정식 위치로 원자적 이동 -> `reload_menu_data()`
-> `get_menu()` 재조회로 확인.

반환 상태값:

- `"imported"`: 추정 없이 정상 반영
- `"imported_with_inference"`: 일부 필드를 추정해서 반영(추정 개수·경고 포함)
- `"rejected"`: 반영하지 않음(`failed_stage`에 어느 단계에서 막혔는지, `error`에 사유)

### 추정 데이터의 의미와 `.ocr_meta.json`

OCR 신뢰도가 낮거나 두 엔진 결과가 다르더라도 메뉴 항목 자체를 통째로
누락하지 않습니다. 이미지 위치·기존 메뉴 용어 사전(`build_known_vocabulary`)과
비교해 가장 가능성 높은 텍스트를 추정하고, **추정한 값은 확정된 OCR
결과처럼 숨기지 않습니다.** 새 이미지에 정식 `.txt`가 아직 없을 때만 다음
두 파일을 만듭니다.

```text
new_menu.txt              # Menu Agent가 바로 쓰는 메뉴 문장
new_menu.ocr_meta.json    # 필드별 추정 여부·신뢰도·후보·선택 근거 기록
```

`.ocr_meta.json`에는 필드별로 PaddleOCR/Tesseract 각각의 인식 결과와
신뢰도, 최종 선택값과 그 이유, 추정 여부(`inferred`)가 남습니다. 완전히
판독할 수 없는 필드만 `"확인불가"`로 저장하며, 빈 문자열이나 통째로 빠진
날짜/메뉴 행은 만들지 않습니다.

### `확인불가` 처리 방식

- 이미지에서 날짜 자체를 인식하지 못하면(핵심 정보 부재) 아예 반영을
  거부합니다(`status: "rejected"`, 데이터 변경 없음).
- 날짜는 인식했지만 특정 날짜의 메뉴 글자를 전혀 읽을 수 없으면, 그 날짜
  행은 지우지 않고 메뉴 항목을 `"확인불가"`로 남깁니다.
- 사람에게 전체 OCR 결과를 다시 검수하게 만들지 않습니다 — 확실한 필드는
  자동 확정, 애매한 필드는 최선값 추정 후 메타데이터 기록, 완전히 불가능한
  경우만 `확인불가`로 최소화합니다.

### 기존 TXT 보호 방식 (Golden Data)

- 이미지와 같은 이름의 `.txt`가 이미 있으면 `import_menu_image()`는
  **덮어쓰지 않고 바로 중단**합니다(`failed_stage: "existing_txt_protection"`).
- 새로 만드는 TXT는 임시 위치에서 `menu_parser`로 파싱 검증을 통과한 뒤에만
  정식 위치로 옮깁니다. 검증에 실패하면 임시 파일을 지우고 기존 데이터는
  그대로 둡니다.
- 이미지 SHA-256 해시로 이미 처리한 이미지를 다시 처리하지 않습니다
  (`data/_ocr_previews/processed_images.json`, Git 제외).
- 같은 업체·날짜·끼니가 다른 이미지로 이미 등록돼 있으면 충돌로 보고
  반영하지 않습니다.
- 성공적으로 반영된 경우에만 `reload_menu_data()`를 호출합니다(검색 캐시는
  성공 시에만 갱신).

### OCR 없이 기존 TXT만 사용하는 방법

아무것도 설치하지 않아도 됩니다. `check_ocr_status`/`preview_menu_ocr`/
`import_menu_image`만 설치 안내가 담긴 구조화된 오류를 반환할 뿐,
`get_menu`/`get_current_menu`/`reload_menu_data`는 항상 sidecar `.txt` 기반으로
정상 동작합니다.

### 복잡한 이미지 처리 방식 (레이아웃/전처리)

`preview_menu_ocr`/`import_menu_image`는 이미지를 한 번에 문자열로 읽지 않고,
다음을 거칩니다.

1. 이미지 품질 확인(해상도 등)
2. 여러 전처리 변형 생성(원본/2배 확대/그레이스케일/대비 강화/선명도 강화/
   적응형 이진화/노이즈 제거/기울기 보정 — OpenCV가 없으면 Pillow만으로
   가능한 범위까지)
3. PaddleOCR·Tesseract 각각 단어 단위 텍스트+좌표+신뢰도로 실행
4. 좌표 기반으로 원래 읽기 순서(위->아래, 왼쪽->오른쪽) 복원
5. 두 엔진 결과 비교(일치 여부, 신뢰도 비교)
6. 업체별 레이아웃 프로필(`ORGANIZATION_LAYOUT_PROFILES`)로 날짜별 영역을
   근사적으로 나누고, 기존 메뉴 용어 사전과 비교해 후보를 보정

레이아웃 프로필은 **절대 픽셀 좌표가 아니라 이미지 크기 대비 비율**과
"추천 전처리/엔진" 정보를 담습니다(대성학원=표 형태, KT/KT 샐러드=카드
형태). 등록된 프로필이 없는 새 업체·레이아웃은 자동으로 범용(whole-image)
분석으로 대체됩니다. 정밀한 표 셀 좌표 추출(표 선 인식 등)까지는 하지
않으며, 이는 알려진 한계로 아래에 남겨둡니다.

### 문제 해결

| 증상 | 원인 | 확인 방법 | 해결 방법 |
|---|---|---|---|
| `uv` 또는 Python 미설치 | uv/Python이 PATH에 없음 | `uv --version` | https://docs.astral.sh/uv/ 설치 후 재시도 |
| `paddleocr` import 오류 | 패키지 미설치 | `check_ocr_status()`의 `paddleocr_available` | `uv sync` 또는 `uv add paddlepaddle paddleocr` |
| PaddlePaddle 버전 충돌 | 다른 패키지가 요구하는 numpy 등과 충돌 | `uv sync` 로그 확인 | `pyproject.toml`의 `numpy>=2.3.5` 제약을 그대로 유지(이미 paddleocr와 호환되도록 낮춰둠) |
| 모델 다운로드 실패 | 네트워크 문제, 방화벽 | `scripts/check_menu_ocr.ps1` 실행 결과 | 네트워크 확인 후 `scripts/setup_menu_ocr.ps1` 재실행(이미 받은 파일은 다시 받지 않음) |
| Tesseract PATH 오류 | 설치했지만 PATH에 없음 | `check_ocr_status()`의 `tesseract_executable_path` | `TESSERACT_CMD` 환경변수 설정 또는 `scripts/setup_menu_ocr.ps1` 재실행 |
| `kor.traineddata` 누락 | 언어팩 미설치 | `check_ocr_status()["languages"]["kor"]` | `scripts/setup_menu_ocr.ps1` 실행(자동 준비) |
| Tesseract 한글 인식 실패 | 언어팩은 있지만 인식률이 낮음 | `preview_menu_ocr()`로 직접 확인 | 전처리 결과(확대/대비) 비교, 그래도 낮으면 PaddleOCR 결과 사용 |
| PaddleOCR 모델 준비 실패 | 모델 캐시 손상 또는 이 환경 특유의 추론 엔진 오류 | `check_ocr_status()`의 `paddle_ready`(패키지 확인)와 실제 `preview_menu_ocr()` 실행 결과(런타임 확인)를 함께 봐야 함 | 캐시 폴더(`%USERPROFILE%\.paddlex`) 삭제 후 재시도. 그래도 안 되면 Tesseract만으로도 전체 파이프라인은 정상 동작함 |
| 표 읽기 순서 오류 | 글자가 한 글자씩 인식되는 특수 글꼴 등에서 좌표 잡음 발생 | `.ocr_meta.json`의 `paddle_text`/`tesseract_text` 원문 비교 | 알려진 한계(아래 참고), 큰 글꼴/고해상도 이미지일수록 안정적 |
| 이미지가 흐리거나 잘림 | 촬영 품질 | `preview_menu_ocr()`의 `warnings` | 더 선명한 이미지로 재촬영/재스캔 |
| 날짜와 메뉴 연결 오류 | 레이아웃 프로필과 실제 이미지가 다름 | `.ocr_meta.json`의 `field`별 날짜 확인 | 해당 업체의 `ORGANIZATION_LAYOUT_PROFILES` 조정 또는 범용 분석 결과 확인 |
| Windows 한글·공백 경로 | 사용자 이름에 한글이 있으면 일부 라이브러리가 경로를 잘못 디코딩 | Tesseract 호출 시 `UnicodeDecodeError` | 이 프로젝트는 `TESSDATA_PREFIX`를 커맨드라인 인자 대신 환경변수로 전달해 이 문제를 피함(코드에 이미 반영됨) |
| 쓰기 권한 문제 | `Program Files`에 언어팩 추가 시도 | 설치 로그의 "Access is denied" | 관리자 권한 대신 `%LOCALAPPDATA%\tessdata` 사용(스크립트 기본값) |
| 메모리 부족 | 큰 이미지 다중 전처리 동시 실행 | OS 작업 관리자 | 이미지를 나눠서 처리하거나 전처리 변형 수를 줄임 |
| GPU·CUDA 충돌 | GPU 버전 paddlepaddle과 드라이버 불일치 | `check_ocr_status()` | 이 프로젝트는 CPU 버전만 사용하므로 기본 설치에서는 발생하지 않음 |
| OCR 추정 필드가 너무 많음 | 이미지 품질이 낮거나 레이아웃이 특이함 | `import_menu_image()`의 `inferred_field_count` | 더 선명한 이미지 사용, 또는 결과를 사람이 확인 후 정식 `.txt`로 직접 정리 |
| 기존 TXT가 있어 자동 등록 중단 | 안전장치가 정상 동작한 것 | `failed_stage: "existing_txt_protection"` | 의도적으로 다시 등록하려면 기존 `.txt`를 먼저 확인 후 직접 정리 |
| 실패 후 기존 메뉴로 복구하는 방법 | — | `import_menu_image()`가 `success: False`면 애초에 아무것도 바뀌지 않음 | 별도 복구 불필요(원자적 반영이라 실패 시 변경 없음) |

### 다른 팀원이 병합 후 해야 할 작업

```powershell
uv sync
powershell -ExecutionPolicy Bypass -File scripts/setup_menu_ocr.ps1   # 실제 OCR을 쓰고 싶다면(선택)
uv run pytest tests/menu -v
```

OCR을 쓰지 않고 기존 sidecar `.txt`만으로 충분하다면 `setup_menu_ocr.ps1`은
생략해도 됩니다.

### Git에 포함할 파일 / 제외할 파일

**포함**: `app/menu_agent_tool.py`, `app/main.py`, `scripts/*.ps1`, `data/menu/{업체}/*.png,*.jpg,*.txt`
(실제 검수된 원본), `tests/menu/*.py`, `README.md`, `pyproject.toml`, `uv.lock`.

**제외** (`.gitignore`에 이미 등록):
- `data/menu/menu.db` — 이 프로젝트는 만들지도 참조하지도 않음(SQLite 코드 완전 제거됨)
- `data/menu/vector_store.json` — 실행 시 생성되는 검색 캐시
- `data/_ocr_previews/` — OCR 미리보기 이미지, 처리 이력(`processed_images.json`)
- `.paddlex_cache/` — PaddleOCR 모델 캐시(프로젝트 루트 아래, 비 ASCII 사용자 경로 문제를 피하려고 여기 둠)
- `%LOCALAPPDATA%\tessdata`, `%USERPROFILE%\.paddlex` — 프로젝트 밖 사용자별 모델 캐시(애초에 저장소 안에 없음)
- `.venv/`, `.pytest_cache/`

### 새 식단표 추가 및 다시 불러오는 방법

코드를 고치지 않고도 새 식단표를 반영할 수 있습니다.

```text
새 이미지와 같은 이름의 .txt 추가 (data/menu/{업체}/ 아래)
→ reload_menu_data() 실행
→ 새 식단 조회 가능
```

```python
from app.menu_agent_tool import reload_menu_data

summary = reload_menu_data()
print(summary)
# {"entry_count": 31, "errors": []}
```

- 같은 (업체, 메뉴종류, 날짜, 식사종류) 조합은 나중에 스캔한 값으로 자동
  덮어써져 중복으로 쌓이지 않습니다.
- `.txt`가 없거나 형식이 안 맞는 파일이 있어도 전체 실행이 중단되지 않고,
  `errors` 목록에 어떤 파일에 어떤 문제가 있는지 모아서 알려줍니다.
- 이미지 폴더 경로는 프로젝트 루트를 기준으로 계산되므로(`app/menu_agent_tool.py`의
  `BASE_DIR`), 다른 컴퓨터에 클론해도 그대로 동작합니다. 결과의
  `source_image_path`도 가능하면 프로젝트 루트 기준 상대 경로로 저장됩니다.

### 다른 팀원이 Menu Tool을 호출하는 방법

다른 Agent, FastAPI 라우터, LangGraph Router 등 다른 팀 코드에서는
`app/menu_agent_tool.py`가 공개하는 함수/Tool 객체만 import해서 사용하면
됩니다(단일 파일이라 내부 구역을 알 필요가 없습니다). `POST /chat`으로
붙이는 방법은 위 "`POST /chat`" 절을 참고하세요.

```python
from app.menu_agent_tool import get_menu, get_current_menu, reload_menu_data

reload_menu_data()  # 새 이미지를 추가했을 때만 다시 부르면 됩니다.

result = get_menu("오늘 KT 메뉴 뭐야?")       # 챗봇 질문
dashboard_result = get_current_menu()          # 대시보드 자동 표시
```

두 함수 모두 예외가 발생해도 항상 다음과 같은 고정된 딕셔너리 구조를 반환합니다.

```python
{
    "success": True,
    "query": "오늘 KT 메뉴 뭐야?",
    "conditions": {
        "organization": "KT",
        "menu_date": "2026-07-22",
        "weekday": None,
        "meal_type": "점심",
        "search_mode": "condition",  # "condition" | "semantic" | "dashboard"
    },
    "results": [
        {
            "organization": "KT",
            "menu_type": "general",
            "menu_date": "2026-07-22",
            "weekday": "수요일",
            "meal_type": "점심",
            "menu_items": ["제육볶음", "미역국", "배추김치"],
            "source_image_path": "data/menu/kt/kt_menu_2026-07-20_2026-07-26.jpg",
        }
    ],
    "answer": "오늘 KT 점심 메뉴는 제육볶음, 미역국, 배추김치입니다.",
    "error": None,
}
```

- `conditions`: 실제로 어떤 업체/날짜/요일/끼니 조건으로 조회했는지 보여줍니다
  (기본값이 적용된 경우에도 실제 적용된 값이 나옵니다).
- `results`의 각 항목에는 업체명, 식단 날짜·요일, 식사 종류, 메뉴 목록, 원본
  이미지 경로가 항상 포함됩니다.
- `error`: 정상 조회(결과가 없는 경우 포함)에서는 `None`이고, 예외가 발생했을
  때만 오류 메시지 문자열이 들어갑니다.
- `now=datetime(...)`으로 기준 시각을 고정해서 전달할 수 있습니다(테스트용).
  생략하면 한국 시간(KST) 기준 현재 시각을 사용합니다.

`get_menu()`/`get_current_menu()`는 새로운 검색 로직을 만들지 않고
`app/menu_agent_tool.py` 안의 `query_menu()`/`plan_menu_search()`를 그대로
재사용합니다.

### 검색 방식: 조건 검색 vs 하이브리드(메뉴명·재료) 검색

업체·날짜(또는 요일)가 질문에 명확히 있으면(`search_mode: "condition"`)
`MenuFileStore`를 조건으로 바로 조회합니다. 그렇지 않고 "오렌지치킨텐더샐러드",
"방울토마토"처럼 메뉴명/재료로 보이는 검색어가 남으면(`search_mode: "hybrid"`)
다음 순서로 검색합니다. 앞 단계에서 찾으면 뒤 단계는 시도하지 않습니다.

1. **정확 일치** — 메뉴 이름이 검색어와 완전히 같음
2. **포함** — 메뉴 문자열(재료·드레싱·열량·원산지 포함)에 검색어가 포함됨
3. **조건 일치** — 요일/끼니 조건이 있으면 그 조건으로 조회
4. **벡터 유사도(의미 검색)** — 위 방법으로 못 찾았을 때만 쓰는 보조 수단
5. 그래도 못 찾으면 `"관련 메뉴를 찾지 못했습니다."`를 반환합니다(임의 추천 없음).

업체명이 질문에 포함되면(예: "KT 샐러드 방울토마토 메뉴") 처음부터 해당
업체 데이터로만 검색 범위를 좁힙니다. 벡터 유사도는 1~3단계로 못 찾았을 때만
쓰는 보조 수단이며, `vector_store.json`은 실행 중 생성되는 캐시 파일이라
Git에 커밋하지 않습니다.

> **알려진 제약(후속 개선 과제)**: "KT"만 언급하고 "샐러드"를 언급하지 않은
> 질문은 KT(일반) 데이터로만 범위를 좁힙니다. 예를 들어 "KT 참깨흑임자드레싱
> 나오는 날"은 그 재료가 KT 샐러드에만 있고 KT 일반에는 없어서
> `"관련 메뉴를 찾지 못했습니다."`를 반환합니다 — 업체명 스코프를 있는 그대로
> 지킨 정상 동작이지만, "KT"와 "KT 샐러드"의 상·하위 관계를 더 똑똑하게
> 처리(예: KT로 범위를 좁혀 못 찾으면 KT 샐러드까지 확장)하는 것은 다음 개선
> 과제로 남겨두었습니다.

### `POST /chat` — 다른 Agent와 동일한 규격의 챗봇 엔드포인트

`app/main.py`에 FastAPI로 구현되어 있습니다. 입력/출력 필드는 다른 Agent
(예: 출결 Agent)와 동일하게 고정되어 있습니다.

```bash
uv run uvicorn app.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_input": "오늘 KT 메뉴 뭐야?", "thread_id": "t-1"}'
```

요청/응답 스키마:

```jsonc
// 요청
{"user_input": "오늘 KT 메뉴 뭐야?", "thread_id": "t-1"}

// 응답
{"text": "오늘 KT 점심 메뉴는 ...입니다.", "action": null, "show_buttons": true}
```

- `user_input`(str, 필수): 사용자 질문
- `thread_id`(str, 필수): 대화 스레드 식별자(메뉴 조회는 무상태라 현재는
  라우팅/로깅 용도로만 받고 조회 로직에는 쓰지 않습니다)
- `text`(str): 사용자에게 보여줄 답변
- `action`(str | null): 메뉴 Agent는 현재 별도 액션이 없어 항상 `null`
- `show_buttons`(bool, 항상 `true`): 처음으로/더 질문하기 버튼을 노출할지 여부(현재
  버전은 목록이 아니라 단순 on/off 플래그입니다)

`ChatRequest.user_input`은 최대 500자(`Field(..., max_length=500)`)까지만
받습니다. `user_input`/`thread_id` 중 하나라도 빠지거나 500자를 넘으면
`422 Unprocessable Entity`를 반환합니다.

`app/main.py`는 라우팅 로직을 직접 갖지 않습니다. `ChatRequest`/`ChatResponse`/
`menu_router`/`chat_endpoint`는 모두 `app/menu_agent_tool.py`에 구현되어
공개되고, `app/main.py`는 그 라우터를 import해 `app.include_router(menu_router)`만
수행합니다.

### 다른 Agent/라우터에서 Tool로 연결하는 방법

실제로 지원하는 호출 방식은 두 가지입니다(`MenuTool.invoke`/`MenuTool.run`,
둘 다 같은 핸들러를 호출하므로 결과는 동일합니다). LangChain 등 다른
오케스트레이션 코드의 `Runnable.invoke(...)` 관례에 맞추고 싶다면
`invoke({...})`를, 파이썬 코드에서 직접 부르고 싶다면 `run(**kwargs)`를
쓰면 됩니다.

```python
from app.menu_agent_tool import menu_agent_tool, MENU_AGENT_TOOLS, MENU_ADMIN_TOOLS

# 방식 1: invoke({...}) — dict 하나로 인자를 전달
response = menu_agent_tool.invoke({"user_input": "오늘 KT 메뉴 뭐야?", "thread_id": "t-1"})

# 방식 2: run(**kwargs) — 키워드 인자로 직접 전달
response = menu_agent_tool.run(user_input="오늘 KT 메뉴 뭐야?", thread_id="t-1")

# 둘 다 결과는 동일: {"text": "...", "action": None, "show_buttons": True}
```

`menu_agent_tool` 외에도 관리자/대시보드 전용 Tool이 두 개 더 있습니다.

| Tool 객체 | 용도 | invoke 인자 |
|---|---|---|
| `menu_agent_tool` | 일반 사용자 챗봇 질문(`POST /chat`에서 사용) | `{"user_input": str, "thread_id": str}` |
| `menu_current_tool` | 대시보드 자동 표시(현재 시각 기준) | `{}` 또는 `{"now": datetime}` |
| `menu_image_import_tool` | 새 식단표 이미지 자동 등록(관리자 전용) | `{"image_path": str}` |

```python
menu_current_tool.invoke({})
menu_image_import_tool.invoke({"image_path": "data/menu/kt/new_menu.png"})
```

일반 사용자 대화 흐름에는 `MENU_AGENT_TOOLS`(=`[menu_agent_tool]`)만 연결하고,
관리자/대시보드 쪽에는 `MENU_ADMIN_TOOLS`(=`[menu_current_tool, menu_image_import_tool]`)를
연결하면 됩니다. 저수준 함수(`get_menu`, `get_current_menu`, `reload_menu_data`,
`check_ocr_status`, `preview_menu_ocr`, `import_menu_image`)도 필요하면 그대로
import해서 쓸 수 있습니다.

### 테스트 실행 방법

```bash
uv run pytest tests/menu -v
```

모든 테스트는 pytest의 `tmp_path`(테스트별 임시 폴더)에 자체 더미 이미지/텍스트를
만들어 `MenuFileStore(data_dir=tmp_path)`처럼 별도 인스턴스로 주입해서 씁니다.
`data/menu`의 실제 운영 데이터나 `menu.db`/`vector_store.json`을 읽거나 만들지
않으므로, 테스트를 실행해도 실제 데이터가 오염되지 않습니다.

### 자주 발생하는 오류

- `ModuleNotFoundError: No module named 'app'` : `uv sync` 후 `uv run pytest`/`uv run python -m ...` 형태로 실행해야 합니다. (`pyproject.toml`에 `pythonpath = ["."]`가 설정되어 있습니다.)
- `zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key Asia/Seoul'` : Windows에는 IANA 시간대 데이터가 기본으로 없습니다. `uv sync`로 `tzdata`가 설치되어 있는지 확인하세요.
- `OCR 결과 없음` : 이미지와 같은 이름의 `.txt` sidecar 파일이 없거나 비어 있습니다. `reload_menu_data()`의 반환값 `errors`에서 어떤 파일인지 확인할 수 있습니다.
- `메뉴 구조화 실패` : `.txt` 내용이 `YYYY-MM-DD 요일 식사종류: 항목, 항목` 형식과 맞지 않습니다.
- 메뉴 항목이 `메뉴명 확인 필요`로 나오는 경우 : 오류가 아닙니다. 원본 이미지 글자를
  확실하게 읽지 못해 임의로 메뉴를 만들어내지 않도록 표시해 둔 상태입니다. 원본을
  대조해 정확한 이름을 확인한 뒤 `.txt`에서 이 문구를 실제 메뉴명으로 바꿔주세요.
- KT/KT 샐러드는 중식(점심) 데이터만 있어도 정상입니다. 저녁 데이터가 없다고
  임의로 채우지 않으며, 저녁을 물으면 "해당 날짜에는 등록된 식단이 없습니다."를 받습니다.

### MVP의 한계

- 현재는 실제 식단표 이미지를 기준으로 사람이 검수·정리한 sidecar `.txt`를 파싱해서
  사용하며, 실시간 OCR 자동 추출은 아직 연동하지 않았습니다. 따라서 임의로 생성한
  Mock 데이터가 아니라 실제 자료를 기반으로 검수된 텍스트 데이터입니다. 다만 사람이
  옮겨 적는 과정이라 OCR을 실제로 연동했을 때의 자동 인식 정확도는 별도로 검증해야
  합니다(한글 인식 정확도, 표 구조 인식 등).
- `app/menu_agent_tool.py`의 메뉴 텍스트 파싱 구역(`parse_ocr_text`)은 "날짜 요일 식사종류: 항목..." 한 줄 형식만 처리하는 단순 정규식 파서입니다.
  업체마다 실제 식단표 레이아웃이 다르면 업체별 전처리(사람이 sidecar 텍스트를 작성)가 필요합니다.
  괄호 `(...)` 안의 쉼표/슬래시는 항목 구분자로 취급하지 않으므로, "메뉴명 (구성재료: A, B / 드레싱: C)"
  처럼 상세 정보를 괄호로 묶으면 하나의 메뉴 항목으로 안전하게 저장됩니다.
- 텍스트 임베딩은 외부 모델 없이 해싱 기반 단어 빈도(TF) 벡터를 사용합니다.
  실제 의미 이해보다는 키워드 중복에 가까워, 동의어/유사 표현 검색에는 한계가 있습니다.
  다만 정확 일치/포함 매칭이 먼저 시도되므로(위 "하이브리드 검색" 참고), 실제 메뉴
  텍스트에 있는 단어로 검색하면 이 한계의 영향을 크게 받지 않습니다.
- 하이브리드 검색의 업체 스코프는 "KT"와 "KT 샐러드"를 별개 업체로 다룹니다.
  "KT"만 언급한 질문은 KT 샐러드 데이터를 검색하지 않습니다(위 "알려진 제약" 참고).
- 하이브리드 검색의 키워드 추출은 "메뉴"/"알려줘"/"나오는"/"날" 같은 정해진 불용어
  목록으로 판단하는 단순 규칙이라, 목록에 없는 조사·표현이 붙으면 검색어에 불필요한
  말이 섞여 정확/포함 매칭에 실패하고 벡터 유사도(4단계)로 넘어갈 수 있습니다.
- `get_current_menu()`의 "다음날"은 외부 공휴일 API 없이 단순히 다음 날짜를
  사용합니다. 주말·공휴일에는 데이터가 없을 수 있으며, 이 경우에도 다른 날짜로
  대체하지 않고 안내 문구를 반환합니다.
- 관리자 웹 화면, 인증/권한, LangGraph Router 통합은 이번 MVP 범위에
  포함되지 않았습니다(`POST /chat`은 연결되어 있습니다).
- **PaddleOCR 실제 추론은 이 개발 환경에서 두 가지 환경 원인 때문에 실패했으나,
  둘 다 원인을 특정해 코드로 우회했고 실제 한국어 추론 성공을 확인했습니다.**
  1) Windows 사용자 계정명에 비 ASCII 문자(한글)가 있으면 PaddleX 기본 모델
     캐시 경로(`~/.paddlex/official_models/`)에서 Paddle 추론 엔진의 C++ 레벨
     파일 읽기가 실패해 `RuntimeError: ... attempting to parse an empty input`가
     발생합니다 — `PADDLE_PDX_CACHE_HOME`을 프로젝트 루트 아래 ASCII 경로
     (`.paddlex_cache/`)로 자동 설정해 우회합니다(`_prepare_paddleocr_environment()`).
  2) 이 환경의 paddlepaddle CPU 빌드는 oneDNN(MKL-DNN) 경로의 일부 PIR 연산자
     속성 변환이 구현되어 있지 않아 `NotImplementedError:
     ConvertPirAttribute2RuntimeAttribute ...`가 발생합니다 —
     `PaddleOCR(..., enable_mkldnn=False)`로 우회합니다.
  두 우회 모두 Python 3.13/3.12 양쪽에서 동일하게 재현·해결을 확인했으므로
  Python 버전 문제가 아니었습니다(별도의 3.12 전용 환경은 필요 없습니다).
  실제 KT 식단표 이미지(`data/menu/kt/kt_menu_2026-07-20_2026-07-26.jpg`)로
  `PaddleOCRProvider().extract_text(...)`가 `success=True`, 626자 한국어 텍스트를
  반환하는 것을 확인했습니다. 다른 PC(다른 사용자 계정명, 다른 CPU/빌드)에서는
  결과가 다를 수 있으므로 각자 `check_ocr_status()`/`scripts/check_menu_ocr.ps1`로
  확인해 주세요. 이 우회가 통하지 않는 환경에서도 전체 파이프라인은
  Tesseract만으로 정상 동작하도록 설계되어 있습니다(두 엔진 중 하나만
  성공해도 계속 진행).
- **레이아웃 분석은 정밀한 표 셀 좌표 추출이 아니라 비율 기반 근사치**입니다.
  실제 골든 이미지 3장으로 측정한 Tesseract 단독 정확도는 이미지 스타일에
  따라 크게 갈렸습니다(글자가 크고 단순한 KT 샐러드는 메뉴명 인식률 약
  100%, 표 형태의 대성학원은 약 76%, 사진·장식이 많은 KT 일반식은 약
  20%). PaddleOCR이 정상 동작하는 환경이라면 사진 배경이 섞인 이미지에서
  더 나은 결과를 기대할 수 있습니다.
- OCR이 단어를 한 글자씩 인식하는 특이한 글꼴에서는(이번 검증 중 관찰됨),
  요일 글자("월"/"화"/"수"...)가 "OO요일" 전체 문자열로 필터링되지 않아
  추정된 메뉴 텍스트 앞에 섞여 들어갈 수 있습니다. 이 경우에도 값 자체를
  숨기지 않고 `.ocr_meta.json`에 `inferred: true`로 남기므로, 사람이 필요할
  때만 확인해 고치면 됩니다.
- `import_menu_image()`의 날짜별 필드 추정은 이미지 안의 모든 날짜 후보를
  x좌표로만 그룹화하는 근사 방식이라, 세로로 배치된 날짜나 매우 촘촘한
  레이아웃에서는 정확도가 떨어질 수 있습니다.

### 실제 식단표 이미지 관련 확인 필요 사항

`data/menu/kt/`와 `data/menu/kt_salad/`의 실제 브랜드 식단표 사진 2장은 폴더
배치와 실제 내용이 바뀌어 있던 것을 확인하고 올바르게 재배치했습니다
(`kt_salad/kt_salad_menu_2026-07-20_2026-07-26.jpg` = "헬씨 샐러드" 샐러드
전용 메뉴, `kt/kt_menu_2026-07-20_2026-07-26.jpg` = 조식·중식·석식이 아니라
중식(점심) 위주의 KT 일반 식단표). 두 이미지 모두 `.txt` sidecar를 작성해
연결했습니다.

다음 항목은 이미지의 글자 스타일(작은 글씨/장식체)이 독특해 완전히 확신하지
못했습니다. 원본 이미지와 대조 확인을 부탁드립니다.

- **대성학원** (`daesung_menu_2026-07-20_2026-07-26`): `란퐁유엔`(7/24 조식),
  `밀쐐유나베`(7/25 조식), `니뽕내뽕*s크뽕`(7/26 중식)
- **KT** (`kt_menu_2026-07-20_2026-07-26`, 중식): `예망정병튀김`(7/20),
  `토토킥옥통깨무침`(7/22), `청경채굴소스덮밥`(7/23), `김팔이튀김`(7/23),
  `삼계쌈무`(7/24). 이 이미지는 원산지 표기, 드레싱/소스 종류, "샐러드&비빔코너"
  칸처럼 아주 작은 글씨의 부가 정보도 있는데, 메뉴 이름으로 보기 어려운 표기라
  판단해 `.txt`에는 포함하지 않았습니다.

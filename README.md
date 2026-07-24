# semi_final_project_AICA

## 메뉴(식단) Agent

주간 식단표 이미지를 OCR로 읽어 업체·날짜·요일별 메뉴로 정리하고,
사용자 질문("오늘 KT 메뉴 뭐야?")에 답변하는 로컬 MVP입니다.

**원본 데이터는 관계형 DB가 아니라 `data/menu/` 폴더의 이미지 + 같은 이름의
`.txt`(sidecar) 파일입니다.** 최종 정의서 기준으로 메뉴 데이터를 별도의 DB
테이블로 관리하지 않기 때문에, Menu Tool을 기본값으로 실행해도 `menu.db`가
생기지 않습니다. 관리자가 새 식단표를 등록하는 절차도 "이미지 폴더에 파일을
넣고 `reload_menu_data()`를 부르는 것"뿐이라, 별도 DB 담당자가 없어도 됩니다.
(SQLite 코드는 삭제하지 않고 호환용으로 남아 있습니다 — 아래 "SQLite(호환용)"
절 참고.)

### 생성된 파일과 역할

| 파일 | 역할 |
|---|---|
| `app/menu/config.py` | 데이터 경로, 지원 업체(대성학원/KT/KT 샐러드) 별칭, 공통 상수 |
| `app/menu/menu_ocr.py` | 이미지 -> 텍스트. `MockOCRProvider`(기본, `.txt` sidecar 사용), `TesseractOCRProvider`(선택적 실제 OCR) |
| `app/menu/menu_parser.py` | OCR 원문 텍스트 -> 날짜·요일·식사종류·메뉴 목록으로 구조화 |
| `app/menu/menu_file_store.py` | **기본 데이터 원본.** `data/menu/{업체}/` 폴더를 스캔해 이미지+`.txt`를 메모리에 올려두는 `MenuFileStore`, 기본 싱글턴 `get_store()`, 다시 불러오는 `reload_menu_data()` |
| `app/menu/menu_embedding.py` | 해싱 기반 텍스트 임베딩 + JSON 기반 로컬 벡터 스토어(의미 검색 보조용, 필수 아님) |
| `app/menu/menu_agent.py` | 질문 분석(`parse_query`), 조건/하이브리드 검색 판단(`plan_menu_search`), 하이브리드 매칭(`hybrid_search_menu`), 챗봇 검색 엔진 `query_menu()` |
| `app/menu/menu_tool.py` | **다른 팀이 import해서 쓰는 공개 Menu Tool** — `get_menu()`(챗봇), `get_current_menu()`(대시보드), `reload_menu_data`(재export) |
| `app/menu/menu_repository.py`, `menu_agent.register_menu_image()` | **호환용 SQLite 경로.** `get_menu()`/`get_current_menu()`의 기본 실행에서는 쓰이지 않음 |
| `data/menu/{daesung,kt,kt_salad}/*.png,*.jpg` + 같은 이름의 `.txt` | **실제 운영 데이터.** 업체별 실제 주간 식단표 이미지와 그 내용을 옮겨 적은 sidecar 텍스트 (업체당 1세트) |
| `tests/menu/*` | 각 모듈에 대한 pytest 테스트. 모두 `tmp_path`에 자체 더미 이미지를 만들어 쓰므로 `data/menu`의 실제 데이터를 읽거나 바꾸지 않음 |

### 환경설정

```bash
uv sync
```

`numpy`, `pillow`, `tzdata`(Windows에서 `zoneinfo` 사용을 위해 필요)가 의존성에 포함되어 있습니다.
실제 OCR 엔진(Tesseract, EasyOCR 등)은 필수 의존성으로 추가하지 않았습니다.

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
정규화합니다 (`app/menu/config.py`의 `MEAL_TYPE_SYNONYMS`). SQLite/파일 저장소
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

### OCR은 현재 sidecar 텍스트 방식입니다 (Provider 교체 가능)

이번 MVP는 **실제 OCR 엔진을 설치하지 않고** `MockOCRProvider`가 이미지와 같은
이름의 `.txt` 파일을 읽는 방식으로 동작합니다. 이렇게 한 이유는 (1) 실제 OCR
정확도가 검증되지 않은 상태에서 잘못된 메뉴를 만들어내지 않기 위해서이고,
(2) 별도 프로그램 설치 없이 모든 팀원이 같은 환경을 재현할 수 있게 하기
위해서입니다.

실제 OCR이 필요해지면 `app/menu/menu_ocr.py`의 `OCRProvider` 인터페이스를
구현하는 새 Provider(또는 이미 있는 `TesseractOCRProvider`)를 `MenuFileStore`/
`reload_menu_data(ocr_provider=...)`에 전달하기만 하면 됩니다. 아래 3가지를
구분해서 준비해야 합니다.

1. Python 패키지 설치: `uv add pytesseract`
2. 별도 프로그램 설치: [Tesseract-OCR(Windows)](https://github.com/UB-Mannheim/tesseract/wiki) + 한국어 언어팩(`kor.traineddata`)
3. 환경변수 설정: `tesseract.exe`가 PATH에 없다면 `TESSERACT_CMD`에 실행 파일 경로 지정

### 새 식단표 추가 및 다시 불러오는 방법

코드를 고치지 않고도 새 식단표를 반영할 수 있습니다.

```text
새 이미지와 같은 이름의 .txt 추가 (data/menu/{업체}/ 아래)
→ reload_menu_data() 실행
→ 새 식단 조회 가능
```

```python
from app.menu.menu_tool import reload_menu_data

summary = reload_menu_data()
print(summary)
# {"entry_count": 31, "errors": []}
```

- 같은 (업체, 메뉴종류, 날짜, 식사종류) 조합은 나중에 스캔한 값으로 자동
  덮어써져 중복으로 쌓이지 않습니다.
- `.txt`가 없거나 형식이 안 맞는 파일이 있어도 전체 실행이 중단되지 않고,
  `errors` 목록에 어떤 파일에 어떤 문제가 있는지 모아서 알려줍니다.
- 이미지 폴더 경로는 프로젝트 루트를 기준으로 계산되므로(`app/menu/config.py`의
  `BASE_DIR`), 다른 컴퓨터에 클론해도 그대로 동작합니다. 결과의
  `source_image_path`도 가능하면 프로젝트 루트 기준 상대 경로로 저장됩니다.

### 다른 팀원이 Menu Tool을 호출하는 방법

다른 Agent, FastAPI 라우터, LangGraph Router 등 다른 팀 코드에서는
`app/menu/menu_tool.py`를 공개 인터페이스로 사용하면 됩니다.

```python
from app.menu.menu_tool import get_menu, get_current_menu, reload_menu_data

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
`app/menu/menu_agent.py`의 `query_menu()`/`plan_menu_search()`를 그대로
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

### SQLite 경로 (호환용, 기본 실행에서는 쓰이지 않음)

`app/menu/menu_repository.py`(SQLite)와 `menu_agent.register_menu_image()`는
이전 단계에서 쓰던 저장 방식으로, 삭제하지 않고 호환용으로 남겨두었습니다.
`get_menu()`/`get_current_menu()`/`reload_menu_data()`는 이 코드를 전혀
호출하지 않으므로 기본 실행에서는 `data/menu/menu.db`가 생기지 않습니다.
필요하면 직접 `MenuRepository`/`register_menu_image()`를 호출해 SQLite에
등록할 수 있지만, Menu Tool의 기본 데이터 원본은 아닙니다.

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
- `menu_parser.py`는 "날짜 요일 식사종류: 항목..." 한 줄 형식만 처리하는 단순 정규식 파서입니다.
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
- 관리자 웹 화면, 인증/권한, FastAPI 라우터 연결, LangGraph Router 통합은 이번 MVP
  범위에 포함되지 않았습니다.

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

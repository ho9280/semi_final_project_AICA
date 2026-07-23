"""메뉴 Agent 공통 설정.

데이터 저장 경로, 지원 업체(기관) 목록, 이미지 확장자 등
여러 모듈에서 공통으로 쓰는 값을 모아둔다.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

# 프로젝트 루트 (semi_final_project_AICA/) 기준 경로.
BASE_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = BASE_DIR / "data" / "menu"
DB_PATH = DATA_DIR / "menu.db"
VECTOR_STORE_PATH = DATA_DIR / "vector_store.json"

# OCR로 처리 가능한 이미지 확장자 (소문자 기준).
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

KST = ZoneInfo("Asia/Seoul")

WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# 업체(기관) 코드 -> 별칭 / 메뉴 종류 / 이미지 저장 폴더.
# 새 업체가 추가되면 이 딕셔너리에만 항목을 더하면 된다.
ORGANIZATIONS: dict[str, dict] = {
    "daesung": {
        "display_name": "대성학원",
        "menu_type": "general",
        "aliases": ["대성학원", "대성"],
        "dir": DATA_DIR / "daesung",
    },
    "kt_salad": {
        "display_name": "KT 샐러드",
        "menu_type": "salad",
        # "kt_salad"가 "kt"보다 먼저 매칭되도록 parse_query에서 순서를 보장한다.
        "aliases": ["kt 샐러드", "kt샐러드", "케이티 샐러드", "샐러드"],
        "dir": DATA_DIR / "kt_salad",
    },
    "kt": {
        "display_name": "KT",
        "menu_type": "general",
        "aliases": ["kt", "케이티"],
        "dir": DATA_DIR / "kt",
    },
}

MEAL_TYPES = ["아침", "점심", "저녁"]

# 사용자가 끼니를 지정하지 않았을 때 사용하는 기본값(중식 = 점심).
DEFAULT_MEAL_TYPE = "점심"

# 사용자(또는 대시보드)가 식당을 지정하지 않았을 때 기본으로 함께 조회할 업체.
# 최종 정의서 기준: 대성학원 + KT + KT 샐러드 모두 조회한다.
DEFAULT_ORGANIZATION_CODES = ["daesung", "kt", "kt_salad"]

# 저녁 메뉴를 제공하는 업체. KT/KT 샐러드는 저녁 데이터가 없으므로
# 사용자가 저녁을 지정하지 않았는데 저녁이 기본값으로 선택된 경우
# 대성학원만 기본 조회 대상으로 삼는다 (임의로 KT 저녁을 만들어내지 않는다).
DINNER_ORGANIZATION_CODES = ["daesung"]

# 사용자가 다양한 표현으로 끼니를 말해도 SQLite에는 표준값("점심"/"저녁"/"아침")으로
# 저장·조회하기 위한 동의어 매핑. parse_query()에서 사용자의 질문을 표준값으로 변환한다.
MEAL_TYPE_SYNONYMS: dict[str, str] = {
    "점심": "점심",
    "중식": "점심",
    "런치": "점심",
    "저녁": "저녁",
    "석식": "저녁",
    "디너": "저녁",
    "아침": "아침",
    "조식": "아침",
}

# 업체별 주간 식단 갱신 기준(관리자가 다음 주 식단표를 새로 등록하는 기준 요일).
# 실제 "다음 식단 제공일" 계산에는 쓰지 않지만(공휴일 API 없이 캘린더 전체를
# 알 수 없으므로), 갱신 주기를 코드 여러 곳에 반복해서 적지 않도록 한 곳에서 관리한다.
MENU_REFRESH_SCHEDULE: dict[str, dict] = {
    "daesung": {"weekday": "일요일", "meal_type": "저녁"},
    "kt": {"weekday": "금요일"},
    "kt_salad": {"weekday": "금요일"},
}

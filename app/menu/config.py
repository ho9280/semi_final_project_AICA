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

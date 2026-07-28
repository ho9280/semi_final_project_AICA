"""메뉴 Agent의 단일 파일 구현: 설정, 데이터 모델, OCR, 파싱, 파일 기반
저장소, 임베딩/벡터 검색과 질문 분석/검색/답변 생성, 공개 Tool 인터페이스를
전부 이 한 파일에 모아둔다.

과거에는 app/menu/menu_data.py(데이터 계층)와 app/menu/menu_tool.py(질문
분석/검색 계층)로 나뉘어 있었으나, 팀 인수인계를 단순화하기 위해 이 파일
하나로 통합했다. app/menu/ 패키지는 더 이상 존재하지 않는다.

원본 데이터는 SQLite가 아니라 data/menu/ 폴더의 이미지 + 같은 이름의
.txt(sidecar)이다. 이 파일은 menu.db를 만들거나 참조하지 않는다.

공개 Tool 인터페이스:
    from app.menu_agent_tool import get_menu, get_current_menu, reload_menu_data
    from app.menu_agent_tool import check_ocr_status, preview_menu_ocr, import_menu_image
    from app.menu_agent_tool import menu_agent_tool  # POST /chat 라우터에서 사용하는 Tool 객체

구역 구성:
    # Configuration               - 경로, 업체 목록, 공통 상수
    # Data models                 - OCR/파싱/파일 로드 결과를 표현하는 dataclass
    # OCR and sidecar TXT loading - 이미지 -> 텍스트 (Mock/Tesseract/PaddleOCR Provider)
    # Menu text parsing           - OCR 원문 텍스트 -> 구조화된 항목
    # File-based storage          - data/menu 폴더 스캔 + 메모리 저장소 (기본 데이터 원본)
    # Embedding and vector search - 해싱 기반 임베딩 + 로컬 벡터 스토어 (의미 검색 보조)
    # Query planning and search   - 질문 분석, 조건 검색, 하이브리드 검색
    # OCR import pipeline         - 이미지 미리보기/필드 추론/자동 등록(import_menu_image)
    # Public Tool interface       - get_menu/get_current_menu/reload_menu_data, menu_agent_tool
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

import numpy as np
from dotenv import load_dotenv
from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - pillow는 필수 의존성으로 설치되어 있어야 함
    Image = None
    UnidentifiedImageError = Exception

# 이 파일이 단독 실행(python -m app.menu_agent_tool)되는 경우를 대비해
# 여기서도 .env를 로드한다 (chat_router.py에서 이미 로드했어도 중복 호출 안전).
load_dotenv()


# =============================================================================
# Configuration
# =============================================================================

# 프로젝트 루트 (semi_final_project_AICA/) 기준 경로.
BASE_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BASE_DIR / "data" / "menu"
VECTOR_STORE_PATH = DATA_DIR / "vector_store.json"

# OCR 미리보기/등록 파이프라인이 만드는 임시 산출물(미리보기 이미지, OCR 원문
# 캐시)을 두는 폴더. data/menu/{업체}/ 와는 분리되어 있어 MenuFileStore가
# 스캔하는 원본 데이터에 섞이지 않는다(정식 검수 TXT를 덮어쓰지 않기 위함).
OCR_PREVIEW_DIR = BASE_DIR / "data" / "_ocr_previews"

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

# 업체별로 실제 필요한 데이터 범위 정의.
#   - meal_types: 이 업체에서 실제로 채택할 끼니 (표준값: 아침/점심/저녁)
#   - weekdays_only: True면 토/일요일 데이터는 표에 있어도 버린다
ORG_MENU_POLICY: dict[str, dict] = {
    "daesung": {"meal_types": ["점심", "저녁"], "weekdays_only": True},  # 조식 제외, 주말 제외
    "kt": {"meal_types": ["점심"], "weekdays_only": True},
    "kt_salad": {"meal_types": ["점심"], "weekdays_only": True},
}

# 이번 주 이미지를 실측하여 얻은 표 격자 좌표. (업체명, 이미지 픽셀크기) 조합이
# 정확히 일치할 때만 사용된다. 이미지 크기가 달라지면(예: 다음 주 새 이미지,
# 지난주 이미지) 자동으로 폴백(extract_menu_entries_via_vision)으로 넘어간다.
CROP_LAYOUTS: dict[tuple[str, tuple[int, int]], dict] = {
    ("daesung", (1005, 671)): {
        "day_x_bounds": [42, 173, 303, 447, 577, 719],  # 월~금 경계 6개(칸 5개)
        "meal_y_bounds": {"점심": (242, 390), "저녁": (390, 527)},
    },
    ("kt", (1005, 767)): {
        "day_x_bounds": [88, 268, 451, 628, 797, 973],
        "meal_y_bounds": {"점심": (40, 760)},  # 끼니 구분 없이 칸 전체
    },
    ("kt_salad", (1197, 847)): {
        "day_x_bounds": [147, 357, 567, 777, 987, 1197],
        "meal_y_bounds": {"점심": (63, 700)},
    },
}

# 위 정책 적용 후 예상되는 항목 개수 (sanity check용)
EXPECTED_ENTRY_COUNTS: dict[str, int] = {
    "daesung": 10,   # 평일 5일 x (점심/저녁)
    "kt": 5,         # 평일 5일 x 점심
    "kt_salad": 5,   # 평일 5일 x 점심
}

# 요일 판별용 (이미지에 적힌 요일 라벨을 그대로 신뢰)
WEEKDAY_LABELS = ["월요일", "화요일", "수요일", "목요일", "금요일"]
WEEKEND_LABELS = ["토요일", "일요일"]

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

# 사용자가 다양한 표현으로 끼니를 말해도 표준값("점심"/"저녁"/"아침")으로
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


# =============================================================================
# Data models
# =============================================================================


@dataclass
class OCRResult:
    """OCR 처리 결과. 실패해도 항상 이 형태로 반환한다."""

    success: bool
    text: str | None
    error: str | None
    image_path: str


@dataclass
class ParseResult:
    """OCR 원문 텍스트를 구조화한 결과."""

    success: bool
    entries: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class LoadError:
    """MenuFileStore가 이미지 하나를 처리하다 실패했을 때의 기록."""

    image_path: str
    error: str


@dataclass
class LoadResult:
    """MenuFileStore.load() 한 번의 결과 요약."""

    entry_count: int
    errors: list[LoadError] = field(default_factory=list)


# =============================================================================
# Vision-based menu extraction (신규 — 표 안에 사진이 섞여 있어 기존 OCR로는
# 정확도가 낮은 문제를 해결하기 위해 추가함)
# =============================================================================
#
# 기존 방식(OCR로 글자만 추출 -> 정규식/좌표 기반 파싱)은 사진이 섞인 식단표
# 표에서 정확도가 크게 떨어진다(실측 확인됨). 대신 이 함수는 이미지를
# GPT-4o-mini에게 통째로 보여주고, 사람이 표를 읽듯 날짜별/끼니별로
# 구조화된 결과를 직접 받는다. OCR 엔진(Tesseract 등)을 거치지 않는다.
#
# 할루시네이션 방지 장치:
#   1) 프롬프트에서 "모르면 확인불가로 표시, 추측 금지"를 명시
#   2) 자유 텍스트가 아닌 고정 Pydantic 스키마로만 응답받음
#   3) 업체별 예상 개수(EXPECTED_ENTRY_COUNTS)와 실제 개수를 비교해 경고 출력
#   4) 원본 이미지 경로(source_image_path)를 항상 함께 저장해 추적 가능


class MenuDayEntry(BaseModel):
    """이미지 한 장에서 추출된 하루치 식단.

    조식/중식/석식을 하나의 리스트가 아니라 각각 별도 필드로 강제한다.
    이렇게 해야 모델이 특정 끼니(특히 석식) 행 자체를 조용히 빼먹는
    문제를 막을 수 있다 — 필드가 존재하는 이상 모델은 반드시 값을
    채우거나(내용) 빈 리스트로라도 명시해야 한다.
    """

    menu_date: str = Field(..., description="YYYY-MM-DD 형식의 날짜")
    weekday: str = Field(..., description="월요일/화요일/... 형식의 요일")
    breakfast_items: list[str] = Field(
        default_factory=list,
        description="조식(아침) 메뉴. 이미지에 조식 행이 아예 없으면 빈 리스트.",
    )
    lunch_items: list[str] = Field(
        default_factory=list,
        description="중식(점심) 메뉴. 판독 불가한 글자는 '확인불가'로 표기.",
    )
    dinner_items: list[str] = Field(
        default_factory=list,
        description="석식(저녁) 메뉴. 판독 불가한 글자는 '확인불가'로 표기. "
        "이미지에 석식 행이 있는데 읽지 못했다고 빈 리스트로 두지 말고 "
        "반드시 ['확인불가']로 표기하세요.",
    )


class MenuExtractionResult(BaseModel):
    """이미지 한 장 전체에서 추출된 모든 날짜 항목."""

    entries: list[MenuDayEntry] = Field(default_factory=list)


def _parse_week_start_date(image_path: Path) -> date | None:
    """파일명(예: daesung_menu_2026-07-27_2026-08-02.png)에서 그 주의 시작일(월요일)을
    추출한다. 날짜를 LLM에게 읽히지 않고 코드로 직접 계산하기 위함 — 더 정확하다.
    """
    match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", image_path.stem)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def extract_items_from_cell_image(cell_image: "Image.Image", context_hint: str) -> list[str]:
    """표에서 잘라낸 칸 하나(이미지)에서 메뉴 항목 리스트만 뽑아낸다.
    칸이 이미 하나의 요일·끼니로 좁혀져 있으므로, 프롬프트가 훨씬 단순해지고
    "행을 통째로 빼먹는" 문제가 구조적으로 발생할 수 없다(칸마다 개별 호출이므로).
    """
    buffer = io.BytesIO()
    cell_image.save(buffer, format="PNG")
    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = (
        f"이 이미지는 급식 식단표에서 '{context_hint}' 칸 하나만 잘라낸 것입니다.\n"
        "이 칸에 적힌 음식 메뉴 이름을 모두 리스트로 뽑아주세요.\n"
        "규칙:\n"
        "- 실제로 이미지에 적힌 메뉴 이름만 사용하세요. 추측해서 지어내지 마세요.\n"
        "- 괄호로 된 원산지 표기(예: '(돈육:국내산)')는 메뉴 이름에서 제외하세요.\n"
        "- 글자를 전혀 읽을 수 없으면 '확인불가' 하나만 담긴 리스트를 반환하세요.\n"
        "- '비빔코너', 칼로리 숫자, 해시태그 등 메뉴 이름이 아닌 문구는 제외하세요."
    )

    class CellExtraction(BaseModel):
        menu_items: list[str] = Field(default_factory=list)

    try:
        vision_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = vision_llm.with_structured_output(CellExtraction)
        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_data}", "detail": "high"},
            },
        ])
        result: CellExtraction = structured_llm.invoke([message])
        return result.menu_items
    except Exception as exc:
        print(f"[경고] 셀 인식 실패({context_hint}): {exc}")
        return []


def extract_menu_via_crop(image_path: Path, org_code: str, org_info: dict) -> list[dict] | None:
    """미리 계측한 좌표로 표를 요일x끼니 칸 단위로 잘라, 칸마다 Vision에게 개별 질문한다.
    CROP_LAYOUTS에 등록된 (업체, 이미지크기) 조합일 때만 동작한다.
    등록되지 않은 이미지(예: 지난주 이미지, 다음 주 새 이미지)라면 None을 반환해
    MenuFileStore.load()가 기존 방식(extract_menu_entries_via_vision)으로
    자동 전환하도록 한다.
    """
    img = Image.open(image_path)
    layout = CROP_LAYOUTS.get((org_code, img.size))
    if layout is None:
        return None  # 계측되지 않은 이미지 -> 상위에서 폴백 처리

    week_start = _parse_week_start_date(image_path)
    if week_start is None:
        print(f"[경고] {image_path.name}: 파일명에서 시작일을 못 찾아 크롭 방식을 건너뜁니다.")
        return None

    policy = ORG_MENU_POLICY.get(org_code, {"meal_types": ["점심"]})
    entries = []
    day_bounds = layout["day_x_bounds"]

    for day_idx, weekday in enumerate(WEEKDAY_LABELS):
        x0, x1 = day_bounds[day_idx], day_bounds[day_idx + 1]
        menu_date = (week_start + timedelta(days=day_idx)).isoformat()

        for meal_label, (y0, y1) in layout["meal_y_bounds"].items():
            if meal_label not in policy["meal_types"]:
                continue

            cell = img.crop((x0, y0, x1, y1))
            context_hint = f"{org_info['display_name']} {menu_date}({weekday}) {meal_label}"
            items = extract_items_from_cell_image(cell, context_hint)
            if not items:
                continue

            entries.append({
                "organization": org_info["display_name"],
                "menu_type": org_info["menu_type"],
                "menu_date": menu_date,
                "weekday": weekday,
                "meal_type": meal_label,
                "menu_items": items,
                "source_image_path": str(image_path),
            })

    expected = EXPECTED_ENTRY_COUNTS.get(org_code)
    if expected is not None and len(entries) != expected:
        print(
            f"[검수 필요] {image_path.name}: 예상 {expected}개 항목, "
            f"실제 {len(entries)}개 추출됨(크롭 방식). 이미지와 대조해 확인해 주세요."
        )

    return entries

def extract_menu_entries_via_vision(image_path: Path, org_code: str, org_info: dict) -> list[dict]:
    """GPT-4o-mini Vision으로 식단표 이미지 한 장을 구조화된 항목 리스트로 변환한다.

    조식/중식/석식을 별도 필드로 강제 요청하여(MenuDayEntry 참고),
    특정 끼니 행이 통째로 누락되는 문제를 구조적으로 방지한다.
    ORG_MENU_POLICY에 정의된 업체별 필요 범위(끼니/평일 여부)만 남기고
    나머지는 걸러낸다.
    """
    try:
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
    except OSError as exc:
        print(f"[경고] 이미지를 읽을 수 없습니다: {image_path} ({exc})")
        return []

    policy = ORG_MENU_POLICY.get(org_code, {"meal_types": ["점심"], "weekdays_only": False})
    meal_types_kr = "/".join(policy["meal_types"])

    prompt = (
        f"당신은 급식 식단표 이미지를 읽어 구조화하는 도우미입니다.\n"
        f"이 이미지는 '{org_info['display_name']}'의 주간 식단표입니다.\n"
        "현재 연도는 2026년입니다. 이미지 속 월/일 정보를 이용해 각 날짜를 "
        "YYYY-MM-DD 형식으로 만드세요.\n\n"
        "반드시 지킬 규칙:\n"
        "- breakfast_items/lunch_items/dinner_items 세 필드를 매 날짜마다 "
        "빠짐없이 채우세요. 해당 끼니 행이 이미지에 아예 없으면 빈 리스트로, "
        "행은 있는데 글자를 못 읽겠으면 반드시 ['확인불가']로 표기하세요. "
        "절대로 행을 통째로 건너뛰지 마세요.\n"
        "- 이미지에 실제로 적혀 있는 메뉴만 사용하세요. 추측해서 메뉴를 지어내지 마세요.\n"
        "- 메뉴명 옆에 괄호로 붙은 원산지 표기(예: '(돈육:국내산)')는 메뉴 이름이 "
        "아니므로 제외하세요.\n"
        "- 표에 있는 모든 열(요일)을 하나도 빠짐없이 확인하세요. 특히 표의 "
        "오른쪽 끝 열(마지막 요일)을 놓치지 않도록 주의하세요.\n"
        f"- 최종적으로 실제 사용할 끼니는 {meal_types_kr}뿐이지만, 그와 무관하게 "
        "위 규칙대로 3개 필드 모두 우선 채워주세요 (필요 없는 끼니는 이후 "
        "저희 쪽에서 걸러냅니다).\n"
        + ("- 토요일과 일요일 데이터는 추출하지 마세요 (월~금만).\n" if policy["weekdays_only"] else "")
    )

    try:
        vision_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = vision_llm.with_structured_output(MenuExtractionResult)

        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_data}",
                    "detail": "high",  # 작은 글씨 표 인식 정확도를 위해 고해상도로 요청
                },
            },
        ])

        result: MenuExtractionResult = structured_llm.invoke([message])
    except Exception as exc:
        print(f"[경고] {image_path.name} Vision 인식 실패: {exc}")
        return []

    # 끼니 필드명 -> 표준 한글 라벨 매핑
    MEAL_FIELD_MAP = [
        ("breakfast_items", "아침"),
        ("lunch_items", "점심"),
        ("dinner_items", "저녁"),
    ]

    entries = []
    for day in result.entries:
        if day.weekday not in WEEKDAY_LABELS:
            continue  # 토/일요일 등은 여기서 확실히 제외

        for field_name, meal_label in MEAL_FIELD_MAP:
            if meal_label not in policy["meal_types"]:
                continue  # 이 업체 정책에 없는 끼니는 애초에 건너뜀

            items = getattr(day, field_name)
            if not items:
                continue  # 이미지에 해당 끼니 행 자체가 없었던 경우

            # 이 업체가 끼니 1종류만 취급한다면(KT/KT샐러드), 값은 이미
            # meal_label 하나로 고정되어 있으므로 별도 처리가 필요 없다.
            entries.append({
                "organization": org_info["display_name"],
                "menu_type": org_info["menu_type"],
                "menu_date": day.menu_date,
                "weekday": day.weekday,
                "meal_type": meal_label,
                "menu_items": items,
                "source_image_path": str(image_path),
            })

    expected = EXPECTED_ENTRY_COUNTS.get(org_code)
    if expected is not None and len(entries) != expected:
        print(
            f"[검수 필요] {image_path.name}: 예상 {expected}개 항목, "
            f"실제 {len(entries)}개 추출됨. 이미지와 대조해 확인해 주세요."
        )

    return entries

# =============================================================================
# OCR and sidecar TXT loading
# =============================================================================
#
# 실제 OCR 엔진이 없어도 개발/테스트를 진행할 수 있도록 MockOCRProvider를
# 기본으로 제공한다. 이미지 파일과 같은 이름의 .txt 파일(sidecar)이 있으면
# 그 내용을 "OCR로 읽은 결과"처럼 사용한다.
#
# 예) data/menu/kt/kt_2026-07-20.png  <-  이미지
#     data/menu/kt/kt_2026-07-20.txt  <-  사람이 검수해 정리한 OCR 결과 텍스트
#
# 실제 OCR이 필요해지면 TesseractOCRProvider를 쓰거나, 같은 인터페이스
# (OCRProvider)를 구현하는 새 클래스를 추가하면 된다. 이 파일의 나머지
# 코드나 menu_tool.py는 provider 종류와 무관하게 동작한다.


def validate_image(image_path: str | Path) -> str | None:
    """이미지 파일이 OCR을 시도할 수 있는 상태인지 확인한다.

    문제가 없으면 None, 문제가 있으면 사람이 읽을 수 있는 에러 메시지를 반환한다.
    """
    path = Path(image_path)

    if not path.exists():
        return "이미지 없음"

    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return "지원하지 않는 확장자"

    if Image is not None:
        try:
            with Image.open(path) as img:
                img.verify()
        except (UnidentifiedImageError, OSError):
            return "손상된 이미지"

    return None


class OCRProvider(Protocol):
    """OCR 제공자가 구현해야 하는 인터페이스."""

    def extract_text(self, image_path: str | Path) -> OCRResult: ...


# Windows에 Tesseract-OCR을 기본 설치했을 때 흔히 쓰이는 경로들.
# 개인 PC의 절대경로를 코드에 고정하는 것이 아니라, "있을 법한 표준 위치"만
# 후보로 나열해두고 실제로 존재하는지 확인한다.
_TESSERACT_DEFAULT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def find_tesseract_cmd() -> str | None:
    """Tesseract 실행 파일 경로를 다음 순서로 찾는다.

    1. ``TESSERACT_CMD`` 환경변수
    2. 시스템 PATH (``shutil.which("tesseract")``)
    3. Windows 기본 설치 후보 경로

    찾지 못하면 None을 반환한다(에러 메시지는 호출하는 쪽에서 구성한다).
    """
    import os
    import shutil

    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and Path(env_cmd).exists():
        return env_cmd

    which_cmd = shutil.which("tesseract")
    if which_cmd:
        return which_cmd

    for candidate in _TESSERACT_DEFAULT_CANDIDATES:
        if Path(candidate).exists():
            return candidate

    return None


def get_local_ocr_cache_dir() -> Path:
    """관리자 권한 없이 쓸 수 있는 사용자별 OCR 캐시 폴더 경로를 반환한다.

    ``%LOCALAPPDATA%\\tessdata`` (Windows) 또는 홈 디렉터리 아래
    ``.cache/menu_ocr/tessdata``를 쓴다. 개인 사용자 이름이 포함된 경로를
    코드에 하드코딩하지 않고, 실행 시점의 표준 환경변수로 계산한다.
    """
    import os

    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "tessdata"
    return Path.home() / ".cache" / "menu_ocr" / "tessdata"


def find_tessdata_prefix() -> str | None:
    """언어팩(tessdata) 폴더를 다음 순서로 찾는다.

    1. ``TESSDATA_PREFIX`` 환경변수
    2. 사용자 OCR 캐시 폴더(``get_local_ocr_cache_dir()``, 관리자 권한 불필요)
       에 ``kor.traineddata``가 있으면 그 폴더
    3. 못 찾으면 None(Tesseract 자체 기본 tessdata 폴더를 그대로 쓴다)

    이렇게 하면 ``scripts/setup_menu_ocr.ps1``로 사용자 캐시 폴더에 언어팩을
    받아두기만 하면, 환경변수를 따로 설정하지 않아도 자동으로 인식된다.
    """
    import os

    env_value = os.environ.get("TESSDATA_PREFIX")
    if env_value:
        return env_value

    local_cache = get_local_ocr_cache_dir()
    if (local_cache / "kor.traineddata").exists():
        return str(local_cache)

    return None


@contextmanager
def _tessdata_prefix_env(tessdata_prefix: str | None):
    """``TESSDATA_PREFIX``를 프로세스 환경변수로 임시 설정한다.

    pytesseract의 ``--tessdata-dir`` 커맨드라인 옵션 대신 이 방식을 쓰는
    이유는, 사용자 이름에 한글이 섞인 Windows 경로(예: ``C:\\Users\\홍길동\\...``)
    를 커맨드라인 인자로 넘기면 pytesseract가 tesseract 실행 결과를 디코딩할
    때 ``UnicodeDecodeError``가 나는 경우가 있기 때문이다. 환경변수로
    넘기면 이 문제를 피할 수 있다.
    """
    import os

    if not tessdata_prefix:
        yield
        return

    previous = os.environ.get("TESSDATA_PREFIX")
    os.environ["TESSDATA_PREFIX"] = tessdata_prefix
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TESSDATA_PREFIX", None)
        else:
            os.environ["TESSDATA_PREFIX"] = previous


class MockOCRProvider:
    """실제 OCR 없이 테스트/개발용으로 사용하는 기본 구현.

    이미지와 같은 경로/이름의 .txt 파일 내용을 OCR 결과처럼 반환한다.
    sidecar 파일이 없으면 "OCR 결과 없음" 에러를 반환한다.
    """

    def extract_text(self, image_path: str | Path) -> OCRResult:
        path = Path(image_path)
        image_path_str = str(path)

        error = validate_image(path)
        if error:
            return OCRResult(success=False, text=None, error=error, image_path=image_path_str)

        sidecar = path.with_suffix(".txt")
        if not sidecar.exists():
            return OCRResult(
                success=False,
                text=None,
                error="OCR 결과 없음",
                image_path=image_path_str,
            )

        text = sidecar.read_text(encoding="utf-8").strip()
        if not text:
            return OCRResult(
                success=False,
                text=None,
                error="OCR 결과 없음",
                image_path=image_path_str,
            )

        return OCRResult(success=True, text=text, error=None, image_path=image_path_str)


class TesseractOCRProvider:
    """Tesseract 엔진을 사용하는 실제 OCR 구현 (선택 사항).

    사용하려면 아래 3가지를 구분해서 준비해야 한다.

    1. Python 패키지 설치: ``uv add pytesseract`` (이 프로젝트에는 이미 포함됨)
    2. 별도 프로그램 설치: Windows용 Tesseract-OCR 설치 프로그램
       (https://github.com/UB-Mannheim/tesseract/wiki) + 한국어 언어팩(kor.traineddata)
    3. 환경변수 설정(선택): tesseract.exe가 PATH에 없다면 ``TESSERACT_CMD``에
       실행 파일 전체 경로를, 언어팩을 별도 폴더에 두었다면 ``TESSDATA_PREFIX``에
       그 폴더 경로를 지정한다.

    실행 파일 경로는 ``find_tesseract_cmd()``(TESSERACT_CMD -> PATH -> Windows
    기본 설치 경로 순)로 자동 탐색한다. 개인 PC의 절대경로를 코드에 고정하지
    않으므로 다른 컴퓨터에 그대로 옮겨도 각자의 설치 위치를 찾아 쓴다.

    이 클래스는 이번 MVP의 기본 경로가 아니며(sidecar `.txt`가 기본), 실제
    OCR이 준비된 팀원만 선택적으로 사용한다. 준비물이 없는 상태로 호출하면
    무엇이 부족한지 알려주는 명확한 에러를 낸다.

    OCR 원문은 표/사진 레이아웃을 그대로 텍스트로 옮길 뿐, "날짜 요일 끼니:
    항목..." 형식으로 자동 구조화하지 않는다. 실제 식단표에 쓰려면 이 결과를
    사람이 검수해 sidecar `.txt`로 다듬는 과정이 여전히 필요하다.
    """

    def __init__(self, lang: str = "kor+eng", tesseract_cmd: str | None = None) -> None:
        self.lang = lang
        self.tesseract_cmd = tesseract_cmd

    def extract_text(self, image_path: str | Path) -> OCRResult:
        path = Path(image_path)
        image_path_str = str(path)

        error = validate_image(path)
        if error:
            return OCRResult(success=False, text=None, error=error, image_path=image_path_str)

        try:
            import pytesseract
        except ImportError:
            return OCRResult(
                success=False,
                text=None,
                error=(
                    "pytesseract 패키지가 설치되어 있지 않습니다. "
                    "'uv add pytesseract' 및 Tesseract-OCR 프로그램 설치가 필요합니다."
                ),
                image_path=image_path_str,
            )

        cmd = self.tesseract_cmd or find_tesseract_cmd()
        if not cmd:
            return OCRResult(
                success=False,
                text=None,
                error=(
                    "Tesseract 실행 파일을 찾지 못했습니다. TESSERACT_CMD 환경변수를 "
                    "설정하거나, PATH에 tesseract를 추가하거나, "
                    "https://github.com/UB-Mannheim/tesseract/wiki 에서 설치해 주세요."
                ),
                image_path=image_path_str,
            )
        pytesseract.pytesseract.tesseract_cmd = cmd

        try:
            with _tessdata_prefix_env(find_tessdata_prefix()), Image.open(path) as img:
                text = pytesseract.image_to_string(img, lang=self.lang)
        except Exception as exc:  # pytesseract가 던지는 예외는 다양하므로 넓게 처리
            return OCRResult(
                success=False,
                text=None,
                error=f"OCR 실행 실패: {exc}",
                image_path=image_path_str,
            )

        text = text.strip()
        if not text:
            return OCRResult(
                success=False,
                text=None,
                error="OCR 결과 없음",
                image_path=image_path_str,
            )

        return OCRResult(success=True, text=text, error=None, image_path=image_path_str)


def _prepare_paddleocr_environment() -> None:
    """PaddleOCR/PaddleX 런타임이 이 Windows 환경에서 실제로 동작하도록
    두 가지 환경 원인을 미리 우회한다(진단 완료, Python 버전과는 무관함).

    1) PaddleX는 기본적으로 모델 캐시를 사용자 홈 디렉터리
       (``~/.paddlex/official_models/``)에 둔다. Windows 사용자 계정명에
       비 ASCII 문자(한글 등)가 있으면, PaddleX/Paddle 추론 엔진 C++ 레벨의
       파일 읽기가 그 경로에서 실패해 모델 설정 JSON을 빈 문자열로 읽고
       ``RuntimeError: ... attempting to parse an empty input``이 발생한다.
       프로젝트 루트(항상 ASCII 경로)아래 캐시 폴더로 옮겨서 우회한다.
    2) 이 환경에 설치된 paddlepaddle CPU 빌드는 oneDNN(MKL-DNN) 경로에서
       일부 PIR 연산자 속성 변환이 구현되어 있지 않아
       ``NotImplementedError: ConvertPirAttribute2RuntimeAttribute ...``로
       실패한다. ``enable_mkldnn=False``로 oneDNN을 끄면 문제없이 동작한다
       (``PaddleOCR(..., enable_mkldnn=False)`` 쪽에서 적용).

    사용자가 이미 ``PADDLE_PDX_CACHE_HOME``을 직접 설정했다면 그 값을
    존중하고 덮어쓰지 않는다.
    """

    import os

    if "PADDLE_PDX_CACHE_HOME" not in os.environ:
        cache_dir = BASE_DIR / ".paddlex_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)


class PaddleOCRProvider:
    """PaddleOCR 엔진을 사용하는 실제 OCR 구현 (선택 사항).

    한국어 텍스트 인식과 복잡한 표/레이아웃 탐지에 강점이 있다. 사용하려면
    Python 패키지만 설치하면 된다(``uv add paddlepaddle paddleocr``, 이
    프로젝트에는 이미 포함됨). 별도 프로그램 설치는 필요 없다.

    모델 파일(텍스트 검출/인식 모델)은 처음 사용할 때 PaddleOCR이 자동으로
    다운로드해 로컬 캐시(기본적으로 사용자 홈 디렉터리 아래)에 저장한다.
    이후 실행부터는 다시 받지 않는다. 인터넷 연결이 필요한 시점은 "처음
    한 번"뿐이며, 코드에 모델 경로를 고정하지 않는다.

    PaddleOCR 인스턴스 생성(모델 로딩)에 시간이 걸리므로, 같은 프로세스에서
    여러 이미지를 처리할 계획이면 Provider 하나를 재사용하는 것이 좋다.

    Tesseract와 마찬가지로 표/사진 레이아웃을 텍스트로 옮길 뿐, "날짜 요일
    끼니: 항목..." 형식으로 자동 구조화하지는 않는다.
    """

    def __init__(self, lang: str = "korean") -> None:
        self.lang = lang
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            _prepare_paddleocr_environment()
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(
                lang=self.lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
        return self._engine

    def extract_text(self, image_path: str | Path) -> OCRResult:
        path = Path(image_path)
        image_path_str = str(path)

        error = validate_image(path)
        if error:
            return OCRResult(success=False, text=None, error=error, image_path=image_path_str)

        # paddleocr/paddlex는 import되는 순간 캐시 경로(PADDLE_PDX_CACHE_HOME)를
        # 읽어서 고정하므로, 아래 "설치 확인용" import보다도 먼저 환경을
        # 준비해야 한다(그렇지 않으면 이 함수 안에서만 다시 import해도 이미
        # 늦어서 비 ASCII 사용자 경로 캐시로 굳어진다).
        _prepare_paddleocr_environment()

        try:
            import paddleocr  # noqa: F401
        except ImportError:
            return OCRResult(
                success=False,
                text=None,
                error=(
                    "paddleocr 패키지가 설치되어 있지 않습니다. "
                    "'uv add paddlepaddle paddleocr'로 설치해 주세요."
                ),
                image_path=image_path_str,
            )

        try:
            engine = self._get_engine()
            results = engine.predict(str(path))
        except Exception as exc:  # PaddleOCR 예외는 다양하므로 넓게 처리
            return OCRResult(
                success=False,
                text=None,
                error=f"OCR 실행 실패: {exc}",
                image_path=image_path_str,
            )

        lines: list[str] = []
        for result in results:
            lines.extend(result.get("rec_texts", []))
        text = "\n".join(line.strip() for line in lines if line and line.strip())

        if not text:
            return OCRResult(
                success=False,
                text=None,
                error="OCR 결과 없음",
                image_path=image_path_str,
            )

        return OCRResult(success=True, text=text, error=None, image_path=image_path_str)


# -----------------------------------------------------------------------------
# OCR status check
# -----------------------------------------------------------------------------


def _tesseract_status() -> dict:
    """Tesseract 실행 파일/버전/언어팩 상태를 확인한다."""
    cmd = find_tesseract_cmd()
    status = {
        "available": False,
        "executable_path": cmd,
        "version": None,
        "languages": [],
        "has_kor": False,
        "has_eng": False,
        "has_osd": False,
        "tessdata_prefix": find_tessdata_prefix(),
        "error": None,
    }
    if not cmd:
        status["error"] = (
            "Tesseract 실행 파일을 찾지 못했습니다. TESSERACT_CMD 환경변수를 설정하거나, "
            "PATH에 tesseract를 추가하거나, scripts/setup_menu_ocr.ps1을 실행해 주세요."
        )
        return status

    import subprocess

    try:
        env = None
        if status["tessdata_prefix"]:
            import os

            env = dict(os.environ)
            env["TESSDATA_PREFIX"] = status["tessdata_prefix"]

        version_result = subprocess.run(
            [cmd, "--version"], capture_output=True, text=True, timeout=10, env=env
        )
        first_line = (version_result.stdout or version_result.stderr).splitlines()
        status["version"] = first_line[0].strip() if first_line else None

        langs_result = subprocess.run(
            [cmd, "--list-langs"], capture_output=True, text=True, timeout=10, env=env
        )
        langs = [
            line.strip()
            for line in langs_result.stdout.splitlines()
            if line.strip() and "List of" not in line
        ]
        status["languages"] = langs
        status["has_kor"] = "kor" in langs
        status["has_eng"] = "eng" in langs
        status["has_osd"] = "osd" in langs
        status["available"] = bool(langs)
        if not status["has_kor"]:
            status["error"] = (
                "kor.traineddata가 없습니다. scripts/setup_menu_ocr.ps1을 실행하거나 "
                "TESSDATA_PREFIX가 가리키는 폴더에 kor.traineddata를 추가해 주세요."
            )
    except Exception as exc:
        status["error"] = f"Tesseract 상태 확인 실패: {exc}"

    return status


def _paddle_status() -> dict:
    """PaddlePaddle/PaddleOCR 패키지 설치 및 모델 캐시 상태를 확인한다."""
    status = {
        "paddlepaddle_available": False,
        "paddlepaddle_version": None,
        "paddleocr_available": False,
        "paddleocr_version": None,
        "model_cache_dir": None,
        "error": None,
    }
    # extract_text()와 마찬가지로, paddle/paddleocr를 import하는 순간
    # 캐시 경로가 고정되므로 어떤 import보다도 먼저 환경을 준비한다.
    _prepare_paddleocr_environment()

    try:
        import paddle

        status["paddlepaddle_available"] = True
        status["paddlepaddle_version"] = getattr(paddle, "__version__", None)
    except ImportError:
        status["error"] = "paddlepaddle 패키지가 설치되어 있지 않습니다. 'uv add paddlepaddle'로 설치해 주세요."
        return status

    try:
        import paddleocr

        status["paddleocr_available"] = True
        status["paddleocr_version"] = getattr(paddleocr, "__version__", None)
    except ImportError:
        status["error"] = "paddleocr 패키지가 설치되어 있지 않습니다. 'uv add paddleocr'로 설치해 주세요."
        return status

    import os

    cache_dir = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", str(Path.home() / ".paddlex"))) / "official_models"
    status["model_cache_dir"] = str(cache_dir)
    return status


def _pytesseract_status() -> dict:
    try:
        import pytesseract

        return {"available": True, "version": str(pytesseract.get_tesseract_version.__module__ and "installed"), "error": None}
    except ImportError:
        return {
            "available": False,
            "version": None,
            "error": "pytesseract 패키지가 설치되어 있지 않습니다. 'uv add pytesseract'로 설치해 주세요.",
        }


def _pillow_opencv_status() -> dict:
    status = {"pillow_available": Image is not None, "pillow_version": None, "opencv_available": False, "opencv_version": None}
    try:
        import PIL

        status["pillow_version"] = getattr(PIL, "__version__", None)
    except ImportError:
        pass
    try:
        import cv2

        status["opencv_available"] = True
        status["opencv_version"] = getattr(cv2, "__version__", None)
    except ImportError:
        status["opencv_available"] = False
    return status


def check_ocr_status() -> dict:
    """PaddleOCR/Tesseract 실제 OCR 환경이 준비되어 있는지 종합 점검한다.

    OCR 패키지·프로그램이 하나도 없어도 예외를 던지지 않고, 각 항목의 사용
    가능 여부와 해결 방법을 구조화된 dict로 반환한다. 이 함수 자체는 기존
    Menu Tool(``get_menu``/``get_current_menu``/``reload_menu_data``)에
    영향을 주지 않는다(읽기 전용 점검).
    """
    tesseract = _tesseract_status()
    paddle = _paddle_status()
    pytesseract_status = _pytesseract_status()
    pillow_opencv = _pillow_opencv_status()

    paddle_ready = paddle["paddlepaddle_available"] and paddle["paddleocr_available"]
    tesseract_ready = tesseract["available"] and tesseract["has_kor"] and tesseract["has_eng"]

    resolutions = []
    if not paddle_ready:
        resolutions.append("PaddleOCR: 'uv add paddlepaddle paddleocr' 실행 후 재시도")
    if not tesseract_ready:
        if not tesseract["executable_path"]:
            resolutions.append(
                "Tesseract: scripts/setup_menu_ocr.ps1 실행 또는 "
                "'winget install --id UB-Mannheim.TesseractOCR -e'로 설치"
            )
        if tesseract["executable_path"] and not tesseract["has_kor"]:
            resolutions.append(
                "Tesseract 한국어 언어팩: scripts/setup_menu_ocr.ps1 실행 (kor.traineddata 자동 준비)"
            )

    return {
        "paddleocr_available": paddle["paddleocr_available"],
        "paddlepaddle_available": paddle["paddlepaddle_available"],
        "pytesseract_available": pytesseract_status["available"],
        "tesseract_available": tesseract["available"],
        "tesseract_version": tesseract["version"],
        "tesseract_executable_path": tesseract["executable_path"],
        "languages": {
            "kor": tesseract["has_kor"],
            "eng": tesseract["has_eng"],
            "osd": tesseract["has_osd"],
        },
        "tessdata_prefix": tesseract["tessdata_prefix"],
        "pillow_available": pillow_opencv["pillow_available"],
        "pillow_version": pillow_opencv["pillow_version"],
        "opencv_available": pillow_opencv["opencv_available"],
        "opencv_version": pillow_opencv["opencv_version"],
        "paddleocr_model_cache_dir": paddle["model_cache_dir"],
        "paddle_ready": paddle_ready,
        "tesseract_ready": tesseract_ready,
        "any_engine_ready": paddle_ready or tesseract_ready,
        "errors": [e for e in [paddle["error"], tesseract["error"]] if e],
        "resolutions": resolutions,
    }


# -----------------------------------------------------------------------------
# Image preprocessing variants
# -----------------------------------------------------------------------------


def generate_preprocess_variants(image: "Image.Image") -> dict:
    """OCR 정확도를 높이기 위한 여러 전처리 결과를 만든다.

    OpenCV가 설치되어 있으면(이 프로젝트는 paddleocr 의존성으로 자동 설치됨)
    적응형 이진화·노이즈 제거·기울기 보정까지 시도하고, 없으면 Pillow만으로
    가능한 전처리(그레이스케일·확대·대비·선명도)까지만 만든다. 한 가지
    결과만 무조건 쓰지 않고, 호출하는 쪽(``compare_ocr_engines`` 등)에서
    OCR 신뢰도를 비교해 가장 안정적인 결과를 선택한다.
    """
    from PIL import ImageEnhance, ImageFilter

    variants: dict[str, "Image.Image"] = {"original": image.convert("RGB")}

    w, h = image.size
    variants["upscale_2x"] = image.resize((w * 2, h * 2), Image.LANCZOS)

    gray = image.convert("L")
    variants["grayscale"] = gray

    variants["contrast"] = ImageEnhance.Contrast(image.convert("RGB")).enhance(1.8)
    variants["sharpen"] = image.convert("RGB").filter(ImageFilter.SHARPEN)

    try:
        import cv2
        import numpy as _np

        cv_gray = _np.array(gray)

        # 적응형 이진화: 표 선/배경 얼룩에 덜 민감하게 글자만 도드라지게 한다.
        adaptive = cv2.adaptiveThreshold(
            cv_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
        )
        variants["adaptive_threshold"] = Image.fromarray(adaptive)

        # 노이즈 제거 (사진 배경, 압축 아티팩트 등).
        denoised = cv2.fastNlMeansDenoising(cv_gray, h=10)
        variants["denoise"] = Image.fromarray(denoised)

        # 기울기 보정: 이진화된 글자 영역의 최소 회전 사각형 각도를 추정해 되돌린다.
        variants["deskew"] = _deskew_with_opencv(cv_gray)
    except ImportError:
        pass  # OpenCV 없이도 위 Pillow 전처리 결과만으로 동작한다.
    except Exception:
        pass  # 전처리 실패는 해당 변형만 건너뛰고 나머지는 계속 사용한다.

    return variants


def _deskew_with_opencv(cv_gray) -> "Image.Image":
    import cv2
    import numpy as _np

    thresh = cv2.threshold(cv_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = _np.column_stack(_np.where(thresh > 0))
    if coords.shape[0] < 10:
        return Image.fromarray(cv_gray)

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    # 너무 큰 회전(글자와 무관한 잡음일 가능성)은 적용하지 않는다.
    if abs(angle) > 15:
        return Image.fromarray(cv_gray)

    (h, w) = cv_gray.shape[:2]
    center = (w // 2, h // 2)
    rot_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        cv_gray, rot_matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return Image.fromarray(rotated)


# -----------------------------------------------------------------------------
# Multi-engine OCR execution (word/line-level, with confidence and position)
# -----------------------------------------------------------------------------


def run_tesseract_with_boxes(image: "Image.Image", lang: str = "kor+eng") -> dict:
    """Tesseract로 단어 단위 텍스트/신뢰도/좌표를 뽑는다.

    반환: {"text": str, "confidence": float, "words": [{"text","conf","left","top","width","height"}, ...]}
    엔진을 쓸 수 없으면 {"text": "", "confidence": 0.0, "words": [], "error": "..."}.
    """
    try:
        import pytesseract
    except ImportError:
        return {"text": "", "confidence": 0.0, "words": [], "error": "pytesseract 미설치"}

    cmd = find_tesseract_cmd()
    if not cmd:
        return {"text": "", "confidence": 0.0, "words": [], "error": "Tesseract 실행 파일을 찾지 못함"}
    pytesseract.pytesseract.tesseract_cmd = cmd

    try:
        with _tessdata_prefix_env(find_tessdata_prefix()):
            data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        return {"text": "", "confidence": 0.0, "words": [], "error": f"Tesseract 실행 실패: {exc}"}

    words = []
    confs = []
    for i, word in enumerate(data.get("text", [])):
        word = word.strip()
        if not word:
            continue
        conf = data["conf"][i]
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = -1.0
        words.append(
            {
                "text": word,
                "conf": conf,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            }
        )
        if conf >= 0:
            confs.append(conf)

    ordered = _order_words_by_position(words)
    text = " ".join(w["text"] for w in ordered)
    confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return {"text": text, "confidence": confidence, "words": ordered, "error": None}


def run_paddleocr_with_boxes(engine, image_path: str | Path) -> dict:
    """PaddleOCR로 텍스트/신뢰도/좌표를 뽑는다 (``PaddleOCRProvider``와 별개로
    좌표·신뢰도까지 필요한 미리보기/등록 파이프라인에서 사용한다).

    반환 형태는 ``run_tesseract_with_boxes``와 동일하게 맞춘다.
    """
    try:
        results = engine.predict(str(image_path))
    except Exception as exc:
        return {"text": "", "confidence": 0.0, "words": [], "error": f"PaddleOCR 실행 실패: {exc}"}

    words = []
    confs = []
    for result in results:
        texts = result.get("rec_texts", [])
        scores = result.get("rec_scores", [])
        polys = result.get("rec_polys") or result.get("dt_polys") or [None] * len(texts)
        for text, score, poly in zip(texts, scores, polys):
            text = (text or "").strip()
            if not text:
                continue
            if poly is not None:
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                left, top = min(xs), min(ys)
                width, height = max(xs) - left, max(ys) - top
            else:
                left = top = width = height = 0
            words.append(
                {"text": text, "conf": float(score) * 100, "left": left, "top": top, "width": width, "height": height}
            )
            confs.append(float(score) * 100)

    ordered = _order_words_by_position(words)
    text = " ".join(w["text"] for w in ordered)
    confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return {"text": text, "confidence": confidence, "words": ordered, "error": None}


def _order_words_by_position(words: list[dict], row_tolerance: int = 15) -> list[dict]:
    """좌표 정보를 이용해 "위에서 아래, 왼쪽에서 오른쪽" 원래 읽기 순서로 정렬한다.

    같은 행으로 볼 수 있도록 top 좌표가 ``row_tolerance`` 픽셀 이내면 같은
    줄로 묶고, 그 안에서는 left 좌표로 정렬한다.
    """
    if not words:
        return []

    sorted_by_top = sorted(words, key=lambda w: w["top"])
    rows: list[list[dict]] = []
    for word in sorted_by_top:
        placed = False
        for row in rows:
            if abs(row[0]["top"] - word["top"]) <= row_tolerance:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])

    rows.sort(key=lambda row: min(w["top"] for w in row))
    ordered = []
    for row in rows:
        row.sort(key=lambda w: w["left"])
        ordered.extend(row)
    return ordered


# -----------------------------------------------------------------------------
# Organization layout profiles (approximate, ratio-based — not fixed pixels)
# -----------------------------------------------------------------------------
#
# 현재 확보된 업체별 실제 이미지 3장을 관찰해 만든 "근사" 프로필이다. 정밀한
# 셀 좌표 추출(표 선 검출 등)까지는 하지 않고, 업체별로 이미지 크기 대비
# 대략적인 영역 비율과 추천 전처리/엔진만 담는다. 해상도가 달라져도 "비율"
# 기준이라 크게 어긋나지 않지만, 완전히 다른 디자인의 새 이미지가 들어오면
# 프로필이 맞지 않을 수 있다 — 이 경우 아래 값들을 참고용으로만 쓰고
# 범용(whole-image) OCR로 자동 대체한다(``resolve_layout_profile`` 참고).
ORGANIZATION_LAYOUT_PROFILES: dict[str, dict] = {
    "daesung": {
        "description": "7일(월~일) x 3끼(조식/중식/석식) 격자표. 상단 헤더 행에 날짜, "
        "좌측 헤더 열에 끼니, 표 선으로 셀이 구분됨.",
        "layout_type": "grid_table",
        "header_row_ratio": (0.0, 0.12),  # 날짜가 있는 상단 헤더 영역(세로 비율)
        "header_col_ratio": (0.0, 0.06),  # 끼니가 있는 좌측 헤더 영역(가로 비율)
        "grid": {"rows": 3, "cols": 7},
        "has_table_lines": True,
        "recommended_preprocessing": ["grayscale", "contrast", "denoise", "adaptive_threshold"],
        "recommended_engine": "tesseract",
    },
    "kt": {
        "description": "요일별 카드 5개. 각 카드 상단에 메인 메뉴 헤드라인, 중앙에 음식 사진, "
        "하단에 작은 글씨의 반찬/차 목록. 표 선 없이 색상 박스로 구획.",
        "layout_type": "card_row",
        "card_count": 5,
        "header_row_ratio": (0.0, 0.08),
        "has_table_lines": False,
        "recommended_preprocessing": ["upscale_2x", "sharpen", "contrast"],
        "recommended_engine": "paddleocr",
    },
    "kt_salad": {
        "description": "요일별 카드 5개. 상단 날짜, 사진, 샐러드명(파란 글씨), "
        "원산지 체크리스트, 칼로리, 하단 해시태그(재료+드레싱).",
        "layout_type": "card_row",
        "card_count": 5,
        "sections": ["date", "photo", "name", "origin", "calorie", "hashtags"],
        "has_table_lines": False,
        "recommended_preprocessing": ["upscale_2x", "contrast", "sharpen"],
        "recommended_engine": "paddleocr",
    },
}


def resolve_layout_profile(organization_code: str, image: "Image.Image | None" = None) -> dict:
    """업체 코드에 맞는 레이아웃 프로필을 반환한다.

    프로필이 없는(모르는) 업체거나 이미지 형태가 프로필과 크게 다르면(이번
    MVP에서는 "프로필이 아예 없는 경우"만 자동 판별한다) 범용 프로필로
    대체한다. 완벽한 레이아웃 자동 판별은 이번 범위를 벗어나므로, 새 업체를
    추가할 때는 ``ORGANIZATION_LAYOUT_PROFILES``에 프로필을 등록해 주면 된다.
    """
    profile = ORGANIZATION_LAYOUT_PROFILES.get(organization_code)
    if profile is not None:
        return profile
    return {
        "description": "등록된 레이아웃 프로필이 없어 범용(whole-image) 분석으로 대체함.",
        "layout_type": "generic_fallback",
        "has_table_lines": None,
        "recommended_preprocessing": ["upscale_2x", "grayscale", "contrast", "denoise"],
        "recommended_engine": "paddleocr",
    }


# -----------------------------------------------------------------------------
# Known vocabulary (기존 검수 데이터의 메뉴/재료/드레싱 용어) 기반 후보 보정
# -----------------------------------------------------------------------------


def build_known_vocabulary(store: "MenuFileStore") -> set[str]:
    """현재 등록된 메뉴 데이터에서 이미 검수된 메뉴/재료 용어 사전을 만든다.

    OCR 후보가 여러 개이거나 신뢰도가 낮을 때, 이미 알려진 용어와 얼마나
    비슷한지를 후보 선택의 근거로 쓴다(외부 LLM 없이도 동작하는 규칙 기반
    보정). 메뉴 항목 문자열의 괄호 앞부분(메뉴 이름)과, 괄호 안 "구성재료"/
    "드레싱" 값들도 함께 모은다.
    """
    vocabulary: set[str] = set()
    for entry in store.get_all():
        for item in entry["menu_items"]:
            name_part = item.split(" (")[0].strip()
            if name_part:
                vocabulary.add(name_part)
            if "(" in item:
                detail = item.split("(", 1)[1].rstrip(")")
                for chunk in re.split(r"[,，/]", detail):
                    chunk = chunk.strip()
                    if ":" in chunk:
                        chunk = chunk.split(":", 1)[1].strip()
                    for token in chunk.split():
                        token = token.strip()
                        if len(token) >= 2:
                            vocabulary.add(token)
    return vocabulary


def closest_known_terms(candidate: str, vocabulary: set[str], cutoff: float = 0.72, n: int = 3) -> list[str]:
    """기존 용어 사전에서 OCR 후보와 가장 비슷한 용어를 찾는다(외부 LLM 불필요)."""
    import difflib

    if not candidate or not vocabulary:
        return []
    return difflib.get_close_matches(candidate, vocabulary, n=n, cutoff=cutoff)


# -----------------------------------------------------------------------------
# Multi-engine comparison and field-level selection
# -----------------------------------------------------------------------------


def compare_ocr_engines(image_path: str | Path, paddle_provider: "PaddleOCRProvider | None" = None) -> dict:
    """같은 이미지에 대해 PaddleOCR와 Tesseract(kor+eng)를 모두 실행하고 비교한다.

    두 엔진이 모두 실패해도 예외를 던지지 않고 각 엔진의 오류를 담아 반환한다.
    """
    path = Path(image_path)
    error = validate_image(path)
    if error:
        return {
            "success": False,
            "image_path": str(path),
            "paddle": {"text": "", "confidence": 0.0, "words": [], "error": error},
            "tesseract": {"text": "", "confidence": 0.0, "words": [], "error": error},
            "error": error,
        }

    with Image.open(path) as img:
        img = img.convert("RGB")

        tesseract_result = run_tesseract_with_boxes(img, lang="kor+eng")

        paddle_provider = paddle_provider or PaddleOCRProvider()
        try:
            engine = paddle_provider._get_engine()
            paddle_result = run_paddleocr_with_boxes(engine, path)
        except Exception as exc:
            paddle_result = {"text": "", "confidence": 0.0, "words": [], "error": f"PaddleOCR 초기화 실패: {exc}"}

    both_failed = bool(paddle_result.get("error")) and bool(tesseract_result.get("error"))
    return {
        "success": not both_failed,
        "image_path": str(path),
        "paddle": paddle_result,
        "tesseract": tesseract_result,
        "error": None if not both_failed else "PaddleOCR와 Tesseract 모두 실행하지 못했습니다.",
    }


def select_best_text(paddle_result: dict, tesseract_result: dict) -> dict:
    """두 엔진 결과를 비교해 하나를 선택한다.

    우선순위: (1) 두 엔진 텍스트가 사실상 같으면 일치로 채택 (2) 신뢰도가
    더 높은 쪽 (3) 한쪽만 결과가 있으면 그쪽.
    """
    p_text = (paddle_result.get("text") or "").strip()
    t_text = (tesseract_result.get("text") or "").strip()
    p_conf = paddle_result.get("confidence") or 0.0
    t_conf = tesseract_result.get("confidence") or 0.0

    if p_text and t_text:
        agreement = _normalize_for_compare(p_text) == _normalize_for_compare(t_text)
        if agreement:
            return {
                "selected_text": p_text if p_conf >= t_conf else t_text,
                "confidence": max(p_conf, t_conf),
                "agreement": True,
                "reason": "PaddleOCR와 Tesseract 결과가 일치함",
            }
        if p_conf >= t_conf:
            return {
                "selected_text": p_text,
                "confidence": p_conf,
                "agreement": False,
                "reason": f"PaddleOCR 신뢰도({p_conf:.2f})가 Tesseract({t_conf:.2f})보다 높음",
            }
        return {
            "selected_text": t_text,
            "confidence": t_conf,
            "agreement": False,
            "reason": f"Tesseract 신뢰도({t_conf:.2f})가 PaddleOCR({p_conf:.2f})보다 높음",
        }

    if p_text:
        return {"selected_text": p_text, "confidence": p_conf, "agreement": False, "reason": "PaddleOCR만 결과가 있음"}
    if t_text:
        return {"selected_text": t_text, "confidence": t_conf, "agreement": False, "reason": "Tesseract만 결과가 있음"}
    return {"selected_text": "", "confidence": 0.0, "agreement": False, "reason": "두 엔진 모두 결과 없음"}


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


# -----------------------------------------------------------------------------
# Image hashing (중복 처리 방지용)
# -----------------------------------------------------------------------------


def compute_image_hash(image_path: str | Path) -> str:
    """이미지 파일 내용의 SHA-256 해시를 계산한다 (동일 이미지 재처리 감지용)."""
    path = Path(image_path)
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# =============================================================================
# Menu text parsing
# =============================================================================
#
# 식단표마다 실제 레이아웃이 다르기 때문에, 모든 형식을 완벽히 처리하는
# 범용 파서를 만들지 않는다. 대신 아래처럼 "한 줄 = 하루/한 끼" 형태의
# 단순한 표준 포맷을 정의하고, OCR(또는 사람이 검수한) 결과가 이 포맷에
# 맞게 정리되어 있다고 가정한다.
#
# 기대하는 한 줄 형식:
#     2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치
#
# 괄호 `(...)`/`（...）` 안의 쉼표·슬래시는 항목 구분자로 취급하지 않으므로,
# "메뉴명 (구성재료: A, B / 드레싱: C)"처럼 상세 정보를 괄호로 묶으면 하나의
# 메뉴 항목으로 안전하게 저장된다.

_LINE_PATTERN = re.compile(
    r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<weekday>\S+요일)\s+(?P<meal_type>\S+)\s*[:：]\s*(?P<items>.+?)\s*$"
)

_ITEM_SEPARATORS = set(",，·/")
_PAREN_OPEN = set("(（")
_PAREN_CLOSE = set(")）")


def _split_items(raw_items: str) -> list[str]:
    """메뉴 항목을 구분자(쉼표, 가운뎃점, 슬래시) 기준으로 나눈다.

    괄호 안에 있는 구분자는 항목을 나누지 않는다.
    """
    parts: list[str] = []
    current: list[str] = []
    depth = 0

    for ch in raw_items:
        if ch in _PAREN_OPEN:
            depth += 1
            current.append(ch)
        elif ch in _PAREN_CLOSE:
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch in _ITEM_SEPARATORS and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)

    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def parse_ocr_text(
    raw_text: str,
    organization: str,
    menu_type: str,
    source_image_path: str,
) -> ParseResult:
    """OCR 원문 텍스트를 MenuEntry 딕셔너리 리스트로 변환한다.

    organization: 표시용 업체명 (예: "KT", "대성학원")
    menu_type: "general" 또는 "salad" 등 ORGANIZATIONS의 menu_type 값
    """
    if not raw_text or not raw_text.strip():
        return ParseResult(success=False, error="OCR 결과 없음")

    entries: list[dict] = []
    for line in raw_text.splitlines():
        match = _LINE_PATTERN.match(line)
        if not match:
            continue

        weekday = match.group("weekday")
        if weekday not in WEEKDAYS:
            continue

        items = _split_items(match.group("items"))
        if not items:
            continue

        entries.append(
            {
                "organization": organization,
                "menu_type": menu_type,
                "menu_date": match.group("date"),
                "weekday": weekday,
                "meal_type": match.group("meal_type"),
                "menu_items": items,
                "source_image_path": source_image_path,
                "ocr_raw_text": raw_text,
            }
        )

    if not entries:
        return ParseResult(success=False, error="메뉴 구조화 실패")

    return ParseResult(success=True, entries=entries)


# =============================================================================
# File-based storage
# =============================================================================
#
# 최종 정의서 기준으로 메뉴 데이터는 별도의 관계형 DB 테이블로 관리하지
# 않는다. data/menu/{daesung,kt,kt_salad}/ 폴더의 이미지 + 같은 이름의
# .txt(sidecar)가 원본 데이터이며, MenuFileStore가 이를 스캔해 메모리에
# 올려둔다. get_menu()/get_current_menu()의 기본 실행 경로는 이 구역만
# 사용하며 menu.db는 만들지 않는다.


def make_entry_id(organization: str, menu_type: str, menu_date: str, meal_type: str) -> str:
    """업체·메뉴종류·날짜·식사종류로 고유 id를 만든다.

    같은 조합으로 다시 등록하면 같은 id가 나와 upsert 시 자동으로 덮어써진다
    (중복 저장 방지). 파일 기반 저장소와 호환용 SQLite 저장소가 이 함수를
    공유해서 쓴다.
    """
    return f"{organization}_{menu_type}_{menu_date}_{meal_type}"


def _to_display_path(image_path: Path) -> str:
    """가능하면 프로젝트 루트 기준 상대 경로로 저장한다 (컴퓨터마다 다른
    절대 경로를 데이터/결과에 고정하지 않기 위함).
    """
    try:
        return str(image_path.relative_to(BASE_DIR))
    except ValueError:
        return str(image_path)


class MenuFileStore:
    """업체 폴더를 스캔해 메모리에 올려두는 저장소. 인스턴스마다 독립적이다."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        ocr_provider: OCRProvider | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.ocr_provider = ocr_provider or MockOCRProvider()
        self._entries: dict[str, dict] = {}
        self._errors: list[LoadError] = []

    def _organization_folder(self, org_code: str) -> Path:
        if self.data_dir is not None:
            return self.data_dir / org_code
        return ORGANIZATIONS[org_code]["dir"]

    def load(self, vector_store: "VectorStore | None" = None) -> LoadResult:
        """모든 업체 폴더를 다시 스캔해 메모리 데이터를 새로 만든다.

        기존 데이터는 이번에 스캔한 결과로 완전히 교체된다(재조회 시 지워진
        이미지의 옛 데이터가 남지 않는다). 같은 (업체, 메뉴종류, 날짜, 식사종류)
        조합은 같은 id로 계산되므로 나중에 읽은 값이 앞의 값을 덮어써
        중복이 쌓이지 않는다.

        이미지가 없거나(OCR 실패), 형식에 맞지 않는(.txt 파싱 실패) 파일이
        있어도 전체 스캔을 중단하지 않고 errors 목록에 모아 반환한다.
        """
        entries: dict[str, dict] = {}
        errors: list[LoadError] = []

        for org_code, org_info in ORGANIZATIONS.items():
            folder = self._organization_folder(org_code)
            if not folder.exists():
                continue

            for image_path in sorted(folder.iterdir()):
                if not image_path.is_file():
                    continue
                if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                    continue  # .txt, .db 등 이미지가 아닌 파일은 조용히 건너뛴다

                try:
                    # 1순위: 좌표 크롭 방식 (이번 주 이미지처럼 계측된 경우만 동작)
                    vision_entries = extract_menu_via_crop(image_path, org_code, org_info)
                    if vision_entries is None:
                        # 계측되지 않은 이미지(예: 지난주 이미지) -> 기존 방식으로 전환
                        vision_entries = extract_menu_entries_via_vision(image_path, org_code, org_info)

                    if not vision_entries:
                        errors.append(LoadError(str(image_path), "인식 결과 없음"))
                        continue

                    for entry in vision_entries:
                        entry_id = make_entry_id(
                            entry["organization"],
                            entry["menu_type"],
                            entry["menu_date"],
                            entry["meal_type"],
                        )
                        entries[entry_id] = entry
                except Exception as exc:  # 파일 하나가 잘못돼도 전체 실행은 계속한다.
                    errors.append(LoadError(str(image_path), f"처리 중 오류: {exc}"))

        self._entries = entries
        self._errors = errors

        if vector_store is not None:
            for entry_id, entry in entries.items():
                text = (
                    f"{entry['organization']} {entry['menu_type']} {entry['menu_date']} "
                    f"{entry['weekday']} {entry['meal_type']}: {', '.join(entry['menu_items'])}"
                )
                vector_store.upsert(
                    entry_id,
                    text,
                    metadata={
                        "organization": entry["organization"],
                        "menu_date": entry["menu_date"],
                        "weekday": entry["weekday"],
                        "meal_type": entry["meal_type"],
                        "source_image_path": entry["source_image_path"],
                    },
                )

        return LoadResult(entry_count=len(entries), errors=errors)

    @property
    def errors(self) -> list[LoadError]:
        return list(self._errors)

    def get_by_id(self, entry_id: str) -> dict | None:
        return self._entries.get(entry_id)

    def get_by_condition(
        self,
        organization: str | None = None,
        menu_date: str | None = None,
        weekday: str | None = None,
        meal_type: str | None = None,
    ) -> list[dict]:
        results = []
        for entry in self._entries.values():
            if organization is not None and entry["organization"] != organization:
                continue
            if menu_date is not None and entry["menu_date"] != menu_date:
                continue
            if weekday is not None and entry["weekday"] != weekday:
                continue
            if meal_type is not None and entry["meal_type"] != meal_type:
                continue
            results.append(entry)
        results.sort(key=lambda e: (e["menu_date"], e["organization"], e["meal_type"]))
        return results

    def get_all(self) -> list[dict]:
        return sorted(
            self._entries.values(), key=lambda e: (e["menu_date"], e["organization"], e["meal_type"])
        )

    def count(self) -> int:
        return len(self._entries)


_default_store: MenuFileStore | None = None


def get_store() -> MenuFileStore:
    """기본(data/menu 전체) MenuFileStore 싱글턴을 반환한다. 처음 호출될 때만 스캔한다."""
    global _default_store
    if _default_store is None:
        _default_store = MenuFileStore()
        _default_store.load(vector_store=get_vector_store())
    return _default_store


def reload_menu_data(ocr_provider: OCRProvider | None = None) -> dict:
    """data/menu 폴더를 다시 스캔해 최신 이미지/텍스트를 반영한다.

    새 식단표 이미지(.png/.jpg/.jpeg)와 같은 이름의 .txt를 폴더에 추가한 뒤
    이 함수를 호출하면, 코드를 다시 고치지 않아도 바로 조회할 수 있다.

    반환값:
        {
            "entry_count": int,          # 새로 인식된 식단 항목 수
            "errors": [                  # 처리하지 못한 파일 목록(전체 실행은 중단하지 않음)
                {"image_path": str, "error": str}, ...
            ],
        }
    """
    global _default_store
    _default_store = MenuFileStore(ocr_provider=ocr_provider) if ocr_provider else MenuFileStore()
    result = _default_store.load(vector_store=get_vector_store())
    return {
        "entry_count": result.entry_count,
        "errors": [{"image_path": e.image_path, "error": e.error} for e in result.errors],
    }


# =============================================================================
# Embedding and vector search
# =============================================================================
#
# 이번 MVP는 외부 임베딩 모델(OpenAI, sentence-transformers 등)이나
# Pinecone 같은 유료 서비스를 쓰지 않는다. 대신 다음과 같이 가볍게 구현한다.
#
# - 임베딩: 해싱 트릭(hashing trick) 기반 단어 빈도(TF) 벡터. 인터넷 연결이나
#   모델 다운로드 없이 결정적으로(같은 입력 -> 같은 벡터) 동작한다. 실제 의미
#   이해보다는 "단어가 얼마나 겹치는가"에 가깝다는 한계가 있다.
# - 저장소: JSON 파일에 {id: {vector, document, metadata}}를 저장하는 직접
#   구현 벡터 스토어. chromadb 같은 전용 라이브러리 대신 사용했으며, 이유는
#   이번 MVP 규모에서는 무거운 의존성(onnxruntime 등)을 설치하지 않고도
#   "영구 저장 + 유사도 검색" 요구사항을 충분히 만족하기 때문이다.
#
# 의미 검색(벡터 유사도)은 정확한 날짜/업체 조회의 필수 조건이 아니라 보조
# 수단이다. menu_tool.py의 하이브리드 검색에서 정확 일치/포함/조건 일치로
# 못 찾았을 때만 이 모듈을 사용한다.

EMBEDDING_DIM = 256

_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """텍스트를 해싱 트릭 기반 TF 벡터로 변환한다.

    같은 텍스트는 항상 같은 벡터를 반환한다(결정적).
    """
    vector = np.zeros(dim, dtype=np.float64)
    for token in _tokenize(text):
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(digest, 16) % dim
        vector[idx] += 1.0

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class VectorStore:
    """id -> (임베딩, 원문, 메타데이터)를 JSON 파일에 영구 저장하는 간단한 벡터 스토어."""

    def __init__(self, store_path: str | Path | None = None, dim: int = EMBEDDING_DIM) -> None:
        self.store_path = Path(store_path) if store_path is not None else VECTOR_STORE_PATH
        self.dim = dim
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.store_path.exists():
            return {}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # 파일이 손상된 경우 빈 상태로 새로 시작한다 (기존 데이터는 덮어쓰기 전까지 유지).
            return {}

    def _save(self) -> None:
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)

    def upsert(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """텍스트를 임베딩해 저장(또는 갱신)한다. 같은 id는 덮어쓴다(중복 방지)."""
        self._data[doc_id] = {
            "vector": embed_text(text, self.dim),
            "document": text,
            "metadata": metadata or {},
        }
        self._save()

    def delete(self, doc_id: str) -> None:
        if doc_id in self._data:
            del self._data[doc_id]
            self._save()

    def count(self) -> int:
        return len(self._data)

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """질의 텍스트와 유사한 문서를 코사인 유사도 순으로 반환한다.

        metadata_filter를 주면 저장된 metadata가 해당 키/값을 모두 포함하는
        항목만 후보로 삼는다(예: {"organization": "KT"}).
        """
        query_vector = np.array(embed_text(query_text, self.dim))

        candidates = []
        for doc_id, item in self._data.items():
            metadata = item.get("metadata", {})
            if metadata_filter:
                if any(metadata.get(k) != v for k, v in metadata_filter.items()):
                    continue
            score = _cosine_similarity(query_vector, np.array(item["vector"]))
            candidates.append(
                {
                    "id": doc_id,
                    "score": score,
                    "document": item["document"],
                    "metadata": metadata,
                }
            )

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:top_k]


_default_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """기본(영구 저장) VectorStore 싱글턴을 반환한다.

    의미 검색은 정확한 날짜·업체 조회의 필수 조건이 아니라 보조 수단이므로,
    이 싱글턴은 실제로 검색이 필요할 때(또는 reload_menu_data() 호출 시)만
    쓰이며, 읽기만 해서는 vector_store.json 파일을 새로 만들지 않는다
    (upsert가 호출될 때만 파일이 생성/갱신된다).
    """
    global _default_vector_store
    if _default_vector_store is None:
        _default_vector_store = VectorStore()
    return _default_vector_store


# =============================================================================
# Query planning, search, and public Tool interface (formerly menu_tool.py)
# =============================================================================

import shutil
import tempfile
from datetime import date, datetime, timedelta

_WEEKDAY_PATTERN = re.compile(r"[월화수목금토일]요일")
_DATE_PATTERN = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?")

# 하이브리드 검색용 키워드를 뽑아낼 때, 업체/날짜/요일/끼니를 제거하고 남은
# 토큰 중 이런 일반적인 질문 표현은 "메뉴 이름/재료"가 아니므로 제외한다.
_SEARCH_STOPWORDS = {
    "메뉴",
    "알려줘",
    "알려주세요",
    "줘",
    "주세요",
    "뭐야",
    "뭐지",
    "뭐예요",
    "궁금해",
    "있어",
    "있나요",
    "좀",
    "이번",
    "주에",
    "이번주",
    "언제",
    "나오는",
    "나온다",
    "나와",
    "날",
    "날짜",
    "혹시",
    "그",
}

# "방울토마토 들어간 메뉴", "참깨흑임자드레싱 들어있는 메뉴"처럼 재료 포함 여부를
# 묻는 표현. 토큰이 아니라 문구 단위로 제거해야 "들어 있는"처럼 띄어쓰기가 있는
# 표현도 처리할 수 있다.
_INGREDIENT_INCLUSION_PHRASES = [
    "들어있는",
    "들어 있는",
    "들어가는",
    "들어간",
    "포함된",
    "포함하는",
]


# =============================================================================
# 질문 분석 (사용자 질문 -> 업체/날짜/요일/끼니)
# =============================================================================


def get_now_kst() -> datetime:
    """한국 시간(KST) 기준 현재 시각을 반환한다."""
    return datetime.now(KST)


def get_today_kst() -> date:
    """한국 시간(KST) 기준 오늘 날짜를 반환한다."""
    return get_now_kst().date()


@dataclass
class QueryFilters:
    organization_code: str | None = None
    organization_display: str | None = None
    menu_date: str | None = None
    weekday: str | None = None
    meal_type: str | None = None


def _extract_organization(text: str) -> tuple[str | None, str | None]:
    lowered = text.lower()
    # dict 순서대로 검사한다. menu_data.py에서 "kt_salad"가 "kt"보다 먼저
    # 오도록 정의해두었기 때문에 "KT 샐러드"가 "KT"보다 먼저 매칭된다.
    for code, info in ORGANIZATIONS.items():
        for alias in info["aliases"]:
            if alias.lower() in lowered:
                return code, info["display_name"]
    return None, None


def _extract_date(text: str, today: date) -> str | None:
    if "오늘" in text:
        return today.isoformat()
    if "내일" in text:
        return (today + timedelta(days=1)).isoformat()
    if "모레" in text:
        return (today + timedelta(days=2)).isoformat()

    match = _DATE_PATTERN.search(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None


def _extract_weekday(text: str) -> str | None:
    match = _WEEKDAY_PATTERN.search(text)
    if match and match.group(0) in WEEKDAYS:
        return match.group(0)
    return None


def _extract_meal_type(text: str) -> str | None:
    """질문에서 끼니를 추출하고 표준값("점심"/"저녁"/"아침")으로 변환한다.

    "중식"/"런치" -> "점심", "석식"/"디너" -> "저녁" 처럼 다양한 표현을
    표준값 하나로 정규화한다.
    """
    for word, standard in MEAL_TYPE_SYNONYMS.items():
        if word in text:
            return standard
    return None


def _extract_search_keyword(query: str, filters: QueryFilters) -> str:
    """질문에서 업체/날짜/요일/끼니/일반 질문 표현을 제거하고 남는 "메뉴 이름이나
    재료 이름으로 보이는" 핵심 검색어를 뽑아낸다.

    예) "KT 샐러드 방울토마토 메뉴" -> "방울토마토"
        "이번 주에 돈가스 나오는 날이 언제야?" -> "돈가스"
        "KT 메뉴 알려줘" -> "" (남는 키워드가 없으면 하이브리드 검색을 쓰지 않는다)
    """
    text = query

    if filters.organization_code is not None:
        alias_list = ORGANIZATIONS[filters.organization_code]["aliases"]
        lowered = text.lower()
        # 가장 긴 별칭부터 검사해야 "kt 샐러드"가 "kt"보다 먼저 제거된다.
        for alias in sorted(alias_list, key=len, reverse=True):
            idx = lowered.find(alias.lower())
            if idx != -1:
                text = text[:idx] + text[idx + len(alias) :]
                break

    for word in ("오늘", "내일", "모레"):
        text = text.replace(word, "")

    if filters.weekday:
        text = text.replace(filters.weekday, "")

    for word in MEAL_TYPE_SYNONYMS:
        text = text.replace(word, "")

    for phrase in _INGREDIENT_INCLUSION_PHRASES:
        text = text.replace(phrase, "")

    tokens = [t.strip("?!.,~ ") for t in re.split(r"\s+", text)]
    tokens = [t for t in tokens if t and t not in _SEARCH_STOPWORDS]
    return " ".join(tokens).strip()


def parse_query(query: str, today: date | None = None) -> QueryFilters:
    """사용자 질문에서 업체/날짜/요일/식사종류를 추출한다.

    MVP에서는 복잡한 LLM 호출 대신 키워드 매칭과 간단한 날짜 계산만 사용한다.
    """
    today = today or get_today_kst()
    org_code, org_display = _extract_organization(query)

    return QueryFilters(
        organization_code=org_code,
        organization_display=org_display,
        menu_date=_extract_date(query, today),
        weekday=_extract_weekday(query),
        meal_type=_extract_meal_type(query),
    )


# =============================================================================
# 조건/하이브리드 검색 계획 및 실행
# =============================================================================


def _resolve_meal_type(filters: QueryFilters) -> str:
    """끼니를 지정하지 않으면 현재 시각과 무관하게 항상 중식(점심)을 기본값으로 쓴다.

    시간대별 기본값(00~13시 점심 / 13~19시 저녁 / 19시 이후 다음날 점심)은
    챗봇이 아니라 대시보드(``get_current_menu()``)에서만 적용된다. 사용자가
    끼니를 직접 말한 경우에는 그 값을 그대로 쓴다.
    """
    return filters.meal_type or DEFAULT_MEAL_TYPE


def _resolve_menu_date(filters: QueryFilters, today: date) -> str | None:
    """조건 검색에 사용할 날짜를 정한다.

    사용자가 날짜(오늘/내일/특정 날짜)를 직접 언급했으면 그대로 쓰고,
    요일만 언급한 경우에는 요일 조건만으로 조회하도록 날짜를 비워둔다(None).
    둘 다 없으면 항상 오늘 날짜를 사용한다.
    """
    if filters.menu_date:
        return filters.menu_date
    if filters.weekday:
        return None
    return today.isoformat()


def _resolve_organization_codes(filters: QueryFilters) -> list[str]:
    """조회 대상 업체 코드를 정한다.

    사용자가 업체를 지정하면 그 업체만, 지정하지 않으면 기본 업체 조합
    (대성학원 + KT + KT 샐러드) 전체를 조회한다. KT/KT 샐러드에 저녁 데이터가
    없으면(끼니가 저녁인 경우) 해당 업체는 결과가 없을 뿐, 대신 다른 메뉴를
    임의로 채우지 않는다.
    """
    if filters.organization_code is not None:
        return [filters.organization_code]
    return DEFAULT_ORGANIZATION_CODES


def plan_menu_search(query: str, filters: QueryFilters, today: date) -> dict:
    """이 질문을 조건 검색으로 처리할지 하이브리드(메뉴명/재료) 검색으로 처리할지,
    어떤 조건으로 검색할지 결정한다. ``query_menu()``와 ``get_menu()``가 똑같은
    판단 로직을 공유하도록 이 함수 하나로 모아둔다 (로직 중복 방지).

    반환값:
        {
            "search_mode": "condition" | "hybrid",
            "organization_codes": list[str] | None,  # hybrid에서 None이면 전체 업체 대상
            "menu_date": str | None,
            "weekday": str | None,
            "meal_type": str | None,
            "keyword": str | None,  # "hybrid"일 때만 의미 있음
        }
    """
    if filters.menu_date or filters.weekday:
        # 업체/날짜(또는 요일)가 명확하므로 조건 검색을 그대로 쓴다(기존 동작 유지).
        meal_type = _resolve_meal_type(filters)
        org_codes = _resolve_organization_codes(filters)
        return {
            "search_mode": "condition",
            "organization_codes": org_codes,
            "menu_date": filters.menu_date,
            "weekday": filters.weekday,
            "meal_type": meal_type,
            "keyword": None,
        }

    keyword = _extract_search_keyword(query, filters)
    if keyword:
        # "방울토마토", "오렌지치킨텐더샐러드", "KT 참깨흑임자드레싱 나오는 날"처럼
        # 메뉴 이름/재료로 보이는 검색어가 남으면 하이브리드 검색을 쓴다.
        return {
            "search_mode": "hybrid",
            "organization_codes": [filters.organization_code] if filters.organization_code else None,
            "menu_date": None,
            "weekday": filters.weekday,
            "meal_type": filters.meal_type,
            "keyword": keyword,
        }

    # 남는 키워드가 없는 일반적인 질문("메뉴 알려줘" 등)은 오늘 날짜 기본 조건 검색.
    meal_type = _resolve_meal_type(filters)
    menu_date = _resolve_menu_date(filters, today)
    org_codes = _resolve_organization_codes(filters)

    return {
        "search_mode": "condition",
        "organization_codes": org_codes,
        "menu_date": menu_date,
        "weekday": filters.weekday,
        "meal_type": meal_type,
        "keyword": None,
    }


def _menu_name_part(item: str) -> str:
    """메뉴 항목 문자열에서 괄호로 시작하는 상세 설명 앞의 "메뉴 이름" 부분만 뽑는다.

    예) "오렌지치킨텐더샐러드 (구성재료: ...)" -> "오렌지치킨텐더샐러드"
    괄호가 없으면 항목 전체가 그대로 이름이다.
    """
    return item.split(" (")[0].strip()


def hybrid_search_menu(
    keyword: str,
    organization_codes: list[str] | None,
    weekday: str | None,
    meal_type: str | None,
    store: MenuFileStore,
    vector_store: VectorStore,
    top_k: int = 5,
) -> tuple[list[dict], str, dict | None]:
    """메뉴 이름/재료 키워드로 검색한다. 다음 우선순위를 순서대로 시도하고,
    앞 단계에서 하나라도 찾으면 그 결과를 바로 반환한다(뒤 단계는 시도하지 않는다).

        1. 정확 일치: 메뉴 이름이 키워드와 완전히 같음
        2. 포함: 메뉴 문자열에 키워드가 포함됨
        3. 조건 일치: 요일/끼니 조건이 있으면 그 조건으로 조회
        4. 벡터 유사도(의미 검색) - 정확한 조회의 필수 조건이 아닌 보조 수단
        5. 위에서 아무것도 못 찾으면 빈 결과

    업체가 지정된 경우(organization_codes가 비어있지 않음) 처음부터 그 업체
    데이터로만 범위를 좁혀서 검색한다.

    반환값: (결과 목록, 매칭 단계 이름, 벡터 검색이면 {entry_id: score} 아니면 None)
    """
    org_displays = (
        [ORGANIZATIONS[code]["display_name"] for code in organization_codes]
        if organization_codes
        else None
    )

    def in_scope(entry: dict) -> bool:
        return org_displays is None or entry["organization"] in org_displays

    scoped_entries = [e for e in store.get_all() if in_scope(e)]

    # 1) 정확 일치
    exact = [
        e
        for e in scoped_entries
        if any(_menu_name_part(item) == keyword for item in e["menu_items"])
    ]
    if exact:
        return exact, "exact_match", None

    # 2) 포함
    contains = [e for e in scoped_entries if any(keyword in item for item in e["menu_items"])]
    if contains:
        return contains, "contains_match", None

    # 3) 조건 일치 (요일/끼니)
    if weekday or meal_type:
        condition_hits = [
            e
            for e in store.get_by_condition(weekday=weekday, meal_type=meal_type)
            if in_scope(e)
        ]
        if condition_hits:
            return condition_hits, "condition_match", None

    # 4) 벡터 유사도 (보조 수단)
    metadata_filter = {"organization": org_displays[0]} if org_displays and len(org_displays) == 1 else None
    hits = vector_store.search(keyword, top_k=top_k, metadata_filter=metadata_filter)
    scores: dict[str, float] = {}
    vector_hits = []
    for hit in hits:
        if hit["score"] <= 0:
            continue
        entry = store.get_by_id(hit["id"])
        if entry and in_scope(entry):
            vector_hits.append(entry)
            scores[hit["id"]] = hit["score"]
    if vector_hits:
        return vector_hits, "vector_fallback", scores

    # 5) 관련성 기준을 충족하지 못함
    return [], "no_match", None


# =============================================================================
# 답변 생성
# =============================================================================


def _strip_internal_fields(entry: dict) -> dict:
    return {
        "organization": entry["organization"],
        "menu_type": entry["menu_type"],
        "menu_date": entry["menu_date"],
        "weekday": entry["weekday"],
        "meal_type": entry["meal_type"],
        "menu_items": entry["menu_items"],
        "source_image_path": entry["source_image_path"],
    }


def _date_phrase(filters: QueryFilters, today: date) -> str:
    if filters.menu_date:
        if filters.menu_date == today.isoformat():
            return "오늘"
        if filters.menu_date == (today + timedelta(days=1)).isoformat():
            return "내일"
        return filters.menu_date
    if filters.weekday:
        return filters.weekday
    return "요청하신"


def _build_answer(
    filters: QueryFilters, results: list[dict], today: date, search_mode: str
) -> str:
    if not results:
        if search_mode == "condition":
            # 날짜(또는 요일) 조건으로 조회했는데 결과가 없는 경우.
            # 다른 날짜의 메뉴로 대체하지 않고, 정해진 안내 문구만 반환한다.
            return "해당 날짜에는 등록된 식단이 없습니다."
        # 하이브리드(메뉴명/재료) 검색에서 관련성 기준을 충족하는 메뉴를 못 찾은 경우.
        return "관련 메뉴를 찾지 못했습니다."

    if len(results) == 1:
        r = results[0]
        items = ", ".join(r["menu_items"])
        date_phrase = _date_phrase(filters, today)
        if date_phrase == "요청하신":
            date_phrase = r["menu_date"]
        return f"{date_phrase} {r['organization']} {r['meal_type']} 메뉴는 {items}입니다."

    lines = [
        f"[{r['menu_date']} {r['weekday']}] {r['organization']} {r['meal_type']}: {', '.join(r['menu_items'])}"
        for r in results
    ]
    return "\n".join(lines)


# =============================================================================
# 챗봇 검색 엔진 (내부용)
# =============================================================================


def query_menu(
    query: str,
    store: MenuFileStore | None = None,
    vector_store: VectorStore | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> dict:
    """사용자의 메뉴 질문을 처리하고 통일된 결과를 반환한다.

    store: 원본 데이터를 담고 있는 MenuFileStore. 생략하면 data/menu 폴더 전체를
        읽어들인 기본 싱글턴을 쓴다(menu.db는 만들지 않는다). 테스트에서는
        tmp 디렉터리를 가리키는 MenuFileStore를 만들어 주입할 수 있다.
    vector_store: 의미 검색에만 쓰는 보조 저장소. 생략하면 기본(영구 저장)
        싱글턴을 쓴다. 정확한 날짜/업체 조회에는 관여하지 않는다.
    now/today: 기준 시각/날짜. 생략하면 한국 시간 기준 현재 값을 쓴다.

    반환값은 항상 다음 형태를 유지한다 (예외가 발생해도 동일).
    {"success": bool, "query": str, "results": list[dict], "answer": str}
    """
    store = store or get_store()
    vector_store = vector_store or get_vector_store()
    now = now or get_now_kst()
    today = today or now.date()

    try:
        filters = parse_query(query, today=today)
        plan = plan_menu_search(query, filters, today)
        search_mode = plan["search_mode"]

        if search_mode == "hybrid":
            raw_results, _match_tier, _scores = hybrid_search_menu(
                plan["keyword"],
                plan["organization_codes"],
                plan["weekday"],
                plan["meal_type"],
                store,
                vector_store,
            )
        else:
            # 해당 조건에 데이터가 없어도 다른 날짜/끼니/업체로 대체하지 않는다.
            org_display_list = [
                ORGANIZATIONS[code]["display_name"] for code in plan["organization_codes"]
            ]
            raw_results = []
            for org_display in org_display_list:
                raw_results.extend(
                    store.get_by_condition(
                        organization=org_display,
                        menu_date=plan["menu_date"],
                        weekday=plan["weekday"],
                        meal_type=plan["meal_type"],
                    )
                )

        results = [_strip_internal_fields(r) for r in raw_results]
        answer = _build_answer(filters, results, today, search_mode)

        return {
            "success": len(results) > 0,
            "query": query,
            "results": results,
            "answer": answer,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 구조를 유지한다.
        return {
            "success": False,
            "query": query,
            "results": [],
            "answer": f"메뉴 조회 중 오류가 발생했습니다: {exc}",
        }


# =============================================================================
# 공개 Tool 함수
# =============================================================================


def _organization_names(codes: list[str] | None) -> list[str] | None:
    if not codes:
        return None
    return [ORGANIZATIONS[code]["display_name"] for code in codes]


def _build_conditions(query: str, today: date) -> dict:
    """query_menu()가 실제로 어떤 조건(업체/날짜/요일/끼니)으로 조회했는지
    설명하는 정보를 만든다. 검색 로직 자체는 plan_menu_search()를 그대로
    재사용하므로 여기서 다시 구현하지 않는다.
    """
    filters = parse_query(query, today=today)
    plan = plan_menu_search(query, filters, today)

    organization = (
        filters.organization_display
        if filters.organization_code
        else _organization_names(plan["organization_codes"])
    )

    return {
        "organization": organization,
        "menu_date": plan["menu_date"],
        "weekday": plan["weekday"],
        "meal_type": plan["meal_type"],
        "search_mode": plan["search_mode"],
    }


def get_menu(
    query: str,
    now: datetime | None = None,
    store: MenuFileStore | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """사용자의 메뉴 질문(챗봇)을 처리하고, 팀 간 계약에 맞는 고정된 결과를 반환한다.

    query: 사용자 질문 문자열 (예: "오늘 KT 메뉴 뭐야?")
    now: 검색 기준 시각(선택). 테스트에서 특정 시각을 고정하고 싶을 때 전달한다.
         생략하면 한국 시간 기준 현재 시각을 사용한다.
    store/vector_store: 테스트용 의존성 주입(선택). 생략하면 data/menu 폴더 전체를
         읽어들인 기본 싱글턴을 사용하며, menu.db는 만들지 않는다.

    끼니를 지정하지 않으면 현재 시각과 무관하게 항상 "점심"(중식)을 기본값으로
    조회한다. 시간대별 기본값이 필요하면 ``get_current_menu()``(대시보드용)를
    사용한다.

    반환값은 예외가 발생해도 항상 다음 형태를 유지한다.
        {
            "success": bool,
            "query": str,
            "conditions": {
                "organization": str | list[str] | None,
                "menu_date": str | None,
                "weekday": str | None,
                "meal_type": str | None,
                "search_mode": "condition" | "hybrid",
            },
            "results": [
                {
                    "organization": str, "menu_type": str, "menu_date": str,
                    "weekday": str, "meal_type": str, "menu_items": list[str],
                    "source_image_path": str,
                },
                ...
            ],
            "answer": str,
            "error": str | None,
        }
    """
    now = now or get_now_kst()
    today = now.date()

    try:
        conditions = _build_conditions(query, today)
        result = query_menu(query, store=store, vector_store=vector_store, today=today, now=now)

        return {
            "success": result["success"],
            "query": result["query"],
            "conditions": conditions,
            "results": result["results"],
            "answer": result["answer"],
            "error": None,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 스키마를 유지한다.
        return {
            "success": False,
            "query": query,
            "conditions": {},
            "results": [],
            "answer": f"메뉴 조회 중 오류가 발생했습니다: {exc}",
            "error": str(exc),
        }


def get_current_menu(now: datetime | None = None, store: MenuFileStore | None = None) -> dict:
    """대시보드에 자동으로 표시할 "지금 시각 기준" 메뉴를 반환한다.

    챗봇 질문(``get_menu``)과는 목적이 달라 시간대별 기본값을 따로 적용한다.

        00:00 ~ 12:59  당일 점심,  대성학원 + KT + KT 샐러드
        13:00 ~ 18:59  당일 저녁,  대성학원만 (KT/KT 샐러드는 저녁 데이터 없음)
        19:00 ~ 23:59  다음날 점심, 대성학원 + KT + KT 샐러드

    now: 기준 시각(선택). 테스트에서 특정 시각을 고정할 때 전달한다. 생략하면
        한국 시간 기준 현재 시각을 사용한다.
    store: 테스트용 의존성 주입(선택). 생략하면 기본 싱글턴을 사용한다.

    반환값 스키마는 ``get_menu()``와 동일하게 유지한다
    (success/query/conditions/results/answer/error).
    """
    now = now or get_now_kst()
    today = now.date()
    store = store or get_store()

    try:
        hour = now.hour
        if 0 <= hour < 13:
            meal_type = "점심"
            menu_date = today.isoformat()
            org_codes = DEFAULT_ORGANIZATION_CODES
        elif 13 <= hour < 19:
            meal_type = "저녁"
            menu_date = today.isoformat()
            org_codes = DINNER_ORGANIZATION_CODES
        else:
            meal_type = "점심"
            menu_date = (today + timedelta(days=1)).isoformat()
            org_codes = DEFAULT_ORGANIZATION_CODES

        raw_results = []
        for code in org_codes:
            org_display = ORGANIZATIONS[code]["display_name"]
            raw_results.extend(
                store.get_by_condition(organization=org_display, menu_date=menu_date, meal_type=meal_type)
            )

        results = [_strip_internal_fields(r) for r in raw_results]

        conditions = {
            "organization": _organization_names(org_codes),
            "menu_date": menu_date,
            "weekday": None,
            "meal_type": meal_type,
            "search_mode": "dashboard",
        }

        if not results:
            answer = "해당 날짜에는 등록된 식단이 없습니다."
        else:
            lines = [
                f"[{r['organization']}] {r['meal_type']}: {', '.join(r['menu_items'])}" for r in results
            ]
            answer = "\n".join(lines)

        return {
            "success": len(results) > 0,
            "query": "(대시보드 자동 조회)",
            "conditions": conditions,
            "results": results,
            "answer": answer,
            "error": None,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 스키마를 유지한다.
        return {
            "success": False,
            "query": "(대시보드 자동 조회)",
            "conditions": {},
            "results": [],
            "answer": f"메뉴 조회 중 오류가 발생했습니다: {exc}",
            "error": str(exc),
        }


# =============================================================================
# OCR 미리보기 (선택 기능 — PaddleOCR/Tesseract가 필요하다)
# =============================================================================
#
# 아래 함수들은 실제 OCR 엔진이 설치되어 있을 때만 의미가 있다. 설치되어
# 있지 않거나 실행에 실패해도 챗봇/대시보드 조회(get_menu, get_current_menu,
# reload_menu_data)에는 전혀 영향을 주지 않는다 — 구조화된 오류만 반환한다.
#
# 기존에 사람이 검수한 sidecar `.txt`는 이 파이프라인이 절대 덮어쓰지 않는다.
# "정식 .txt가 아직 없는 새 이미지"에만 동작하며, 결과는 검증을 통과한 뒤에만
# 원자적으로 정식 파일 위치에 반영된다(``import_menu_image`` 참고).


def preview_menu_ocr(image_path: str | Path) -> dict:
    """이미지 하나에 PaddleOCR/Tesseract를 모두 실행해 비교하고 미리보기를 만든다.

    실제 메뉴 데이터에는 아무 영향을 주지 않는 읽기 전용 확인 기능이다.

    반환값은 예외가 발생해도 항상 다음 형태를 유지한다.
        {
            "success": bool, "image_path": str, "paddle_text": str,
            "tesseract_text": str, "selected_text": str, "agreement": bool,
            "confidence": float, "preview_path": str | None,
            "warnings": list[str], "error": str | None,
        }
    """
    path = Path(image_path)
    try:
        error = validate_image(path)
        if error:
            return {
                "success": False,
                "image_path": str(path),
                "paddle_text": "",
                "tesseract_text": "",
                "selected_text": "",
                "agreement": False,
                "confidence": 0.0,
                "preview_path": None,
                "warnings": [],
                "error": error,
            }

        warnings: list[str] = []
        with Image.open(path) as img:
            w, h = img.size
        if min(w, h) < 200:
            warnings.append("이미지 해상도가 낮아 인식률이 떨어질 수 있습니다.")

        comparison = compare_ocr_engines(path)
        if comparison.get("paddle", {}).get("error"):
            warnings.append(f"PaddleOCR 실패: {comparison['paddle']['error']}")
        if comparison.get("tesseract", {}).get("error"):
            warnings.append(f"Tesseract 실패: {comparison['tesseract']['error']}")

        if not comparison["success"]:
            return {
                "success": False,
                "image_path": str(path),
                "paddle_text": "",
                "tesseract_text": "",
                "selected_text": "",
                "agreement": False,
                "confidence": 0.0,
                "preview_path": None,
                "warnings": warnings,
                "error": comparison["error"],
            }

        selection = select_best_text(comparison["paddle"], comparison["tesseract"])
        if not selection["agreement"] and comparison["paddle"]["text"] and comparison["tesseract"]["text"]:
            warnings.append("PaddleOCR와 Tesseract의 인식 결과가 서로 다릅니다.")

        preview_path = None
        try:
            OCR_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
            preview_path = OCR_PREVIEW_DIR / f"{path.stem}_preview.png"
            with Image.open(path) as img:
                img.convert("RGB").save(preview_path)
        except Exception:
            preview_path = None

        return {
            "success": True,
            "image_path": str(path),
            "paddle_text": comparison["paddle"]["text"],
            "tesseract_text": comparison["tesseract"]["text"],
            "selected_text": selection["selected_text"],
            "agreement": selection["agreement"],
            "confidence": round(selection["confidence"], 4),
            "preview_path": str(preview_path) if preview_path else None,
            "warnings": warnings,
            "error": None,
        }
    except Exception as exc:  # 어떤 예외가 나도 동일한 스키마를 유지한다.
        return {
            "success": False,
            "image_path": str(path),
            "paddle_text": "",
            "tesseract_text": "",
            "selected_text": "",
            "agreement": False,
            "confidence": 0.0,
            "preview_path": None,
            "warnings": [],
            "error": f"OCR 미리보기 중 오류가 발생했습니다: {exc}",
        }


# =============================================================================
# 새 이미지 -> 구조화된 필드 추정 (선택 기능)
# =============================================================================

_DATE_TOKEN_PATTERN = re.compile(r"(\d{1,2})\s*[./월]\s*(\d{1,2})\s*일?")
_MEAL_TOKEN_TO_STANDARD = {**MEAL_TYPE_SYNONYMS, "조식": "아침", "중식": "점심", "석식": "저녁"}


def _guess_organization_code(image_path: Path) -> str | None:
    """이미지가 속한 폴더로 업체를 추정한다(``data/menu/{업체}/파일`` 구조 기준)."""
    parent = image_path.resolve().parent
    for code, info in ORGANIZATIONS.items():
        try:
            if info["dir"].resolve() == parent:
                return code
        except OSError:
            continue
    # 폴더 구조를 벗어난 경우(테스트 등) 폴더 이름 자체가 업체 코드와 같은지도 확인한다.
    if parent.name in ORGANIZATIONS:
        return parent.name
    return None


def _extract_date_candidates(words: list[dict], today: date) -> list[dict]:
    """단어 목록에서 날짜로 보이는 토큰을 찾아 (날짜, 요일, 위치) 후보를 만든다."""
    candidates = []
    seen_dates: set[str] = set()
    for w in words:
        match = _DATE_TOKEN_PATTERN.search(w["text"])
        if not match:
            continue
        month, day = int(match.group(1)), int(match.group(2))
        for year in (today.year, today.year - 1, today.year + 1):
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            if abs((d - today).days) <= 200:
                break
        else:
            continue
        if d.isoformat() in seen_dates:
            continue
        seen_dates.add(d.isoformat())
        candidates.append(
            {
                "menu_date": d.isoformat(),
                "weekday": WEEKDAYS[d.weekday()],
                "x": w["left"] + w["width"] / 2,
                "y": w["top"] + w["height"] / 2,
            }
        )
    candidates.sort(key=lambda c: c["x"])
    return candidates


def _assign_words_to_day_groups(words: list[dict], date_candidates: list[dict]) -> dict:
    """날짜 후보의 x좌표를 기준으로 각 단어를 가장 가까운 날짜 그룹에 배정한다.

    실제 식단표는 요일별로 좌우로 배열되는 경우가 대부분이라(대성학원 표,
    KT/KT 샐러드 카드) x축 최근접 배정만으로도 근사적으로 동작한다. 완벽한
    셀 단위 분리는 아니며, 프로필이 다른 새 레이아웃에서는 부정확할 수 있다.
    """
    groups: dict[str, dict] = {
        c["menu_date"]: {"weekday": c["weekday"], "words": []} for c in date_candidates
    }
    for w in words:
        wx = w["left"] + w["width"] / 2
        nearest = min(date_candidates, key=lambda c: abs(c["x"] - wx))
        groups[nearest["menu_date"]]["words"].append(w)
    return groups


def _detect_meal_type(words: list[dict], default: str) -> str:
    for w in words:
        standard = _MEAL_TOKEN_TO_STANDARD.get(w["text"])
        if standard:
            return standard
    return default


def infer_menu_fields(image_path: str | Path, store: MenuFileStore | None = None) -> dict:
    """새 이미지에서 OCR로 메뉴 항목을 추정한다.

    PaddleOCR/Tesseract 결과를 모두 모아, 인식된 단어의 좌표를 이용해
    날짜별로 묶고(``_assign_words_to_day_groups``), 각 날짜 그룹의 텍스트를
    기존 메뉴 용어 사전과 비교해 후보를 보정한다(``closest_known_terms``).
    완전히 판독할 수 없는 항목만 "확인불가"로 남기고, 어려운 항목이라고
    행 자체를 지우지 않는다.

    반환값:
        {
            "success": bool,
            "organization_code": str | None,
            "entries": [MenuEntry 형태 dict, ...],
            "fields": [필드별 OCR 기록 dict, ...],
            "overall_confidence": float,
            "inferred_field_count": int,
            "unreadable_field_count": int,
            "warnings": list[str],
            "error": str | None,
        }
    """
    path = Path(image_path)
    warnings: list[str] = []

    error = validate_image(path)
    if error:
        return {
            "success": False,
            "organization_code": None,
            "entries": [],
            "fields": [],
            "overall_confidence": 0.0,
            "inferred_field_count": 0,
            "unreadable_field_count": 0,
            "warnings": [],
            "error": error,
        }

    org_code = _guess_organization_code(path)
    if org_code is None:
        return {
            "success": False,
            "organization_code": None,
            "entries": [],
            "fields": [],
            "overall_confidence": 0.0,
            "inferred_field_count": 0,
            "unreadable_field_count": 0,
            "warnings": [],
            "error": (
                "이미지가 속한 업체를 판별하지 못했습니다. "
                "data/menu/{daesung|kt|kt_salad}/ 폴더 아래에 이미지를 두어 주세요."
            ),
        }
    org_info = ORGANIZATIONS[org_code]
    profile = resolve_layout_profile(org_code)

    comparison = compare_ocr_engines(path)
    if comparison.get("paddle", {}).get("error"):
        warnings.append(f"PaddleOCR 실패: {comparison['paddle']['error']}")
    if comparison.get("tesseract", {}).get("error"):
        warnings.append(f"Tesseract 실패: {comparison['tesseract']['error']}")
    if not comparison["success"]:
        return {
            "success": False,
            "organization_code": org_code,
            "entries": [],
            "fields": [],
            "overall_confidence": 0.0,
            "inferred_field_count": 0,
            "unreadable_field_count": 0,
            "warnings": warnings,
            "error": comparison["error"],
        }

    paddle_words = comparison["paddle"]["words"]
    tesseract_words = comparison["tesseract"]["words"]
    # 좌표 기반 그룹핑에는 신뢰도가 더 높은 엔진의 단어 목록을 기준으로 쓴다.
    primary_words = paddle_words if comparison["paddle"]["confidence"] >= comparison["tesseract"]["confidence"] else tesseract_words
    primary_words = primary_words or paddle_words or tesseract_words

    today = get_now_kst().date()
    date_candidates = _extract_date_candidates(primary_words, today)
    if not date_candidates:
        return {
            "success": False,
            "organization_code": org_code,
            "entries": [],
            "fields": [],
            "overall_confidence": 0.0,
            "inferred_field_count": 0,
            "unreadable_field_count": 0,
            "warnings": warnings,
            "error": "이미지에서 날짜를 인식하지 못했습니다(날짜와 메뉴 영역이 잘렸거나 화질이 낮을 수 있습니다).",
        }

    day_groups = _assign_words_to_day_groups(primary_words, date_candidates)

    store = store or get_store()
    vocabulary = build_known_vocabulary(store)

    entries: list[dict] = []
    field_records: list[dict] = []
    confidences: list[float] = []
    inferred_count = 0
    unreadable_count = 0

    for menu_date, group in day_groups.items():
        # group["words"]는 _assign_words_to_day_groups()가 이미 올바른 읽기
        # 순서(order_words_by_position로 행 단위 클러스터링된 순서)를 유지한
        # primary_words를 그대로 필터링해 만든 것이므로 다시 정렬하지 않는다.
        # 여기서 (top, left) 단순 튜플로 재정렬하면, 한 글자씩 분리 인식된
        # 경우(예: 특이한 글꼴) 좌표 잡음 때문에 오히려 순서가 깨질 수 있다.
        words = group["words"]
        meal_type = _detect_meal_type(words, default=DEFAULT_MEAL_TYPE)

        # 날짜/요일/끼니 토큰을 제외한 나머지를 메뉴 후보 텍스트로 본다.
        item_words = [
            w
            for w in words
            if not _DATE_TOKEN_PATTERN.search(w["text"])
            and w["text"] not in _MEAL_TOKEN_TO_STANDARD
            and w["text"] not in WEEKDAYS
            and len(w["text"]) >= 1
        ]

        if not item_words:
            unreadable_count += 1
            field_records.append(
                {
                    "field": f"{menu_date}_menu_items",
                    "paddle_text": None,
                    "paddle_confidence": None,
                    "tesseract_text": None,
                    "tesseract_confidence": None,
                    "selected_text": "확인불가",
                    "selection_reason": "해당 날짜 영역에서 메뉴로 보이는 글자를 찾지 못함",
                    "agreement": False,
                    "inferred": True,
                }
            )
            entries.append(
                {
                    "organization": org_info["display_name"],
                    "menu_type": org_info["menu_type"],
                    "menu_date": menu_date,
                    "weekday": group["weekday"],
                    "meal_type": meal_type,
                    "menu_items": ["확인불가"],
                    "source_image_path": str(path),
                    "ocr_raw_text": "",
                }
            )
            continue

        raw_candidate = " ".join(w["text"] for w in item_words)
        avg_conf = sum(w["conf"] for w in item_words if w["conf"] >= 0) / max(
            1, len([w for w in item_words if w["conf"] >= 0])
        ) / 100.0

        matches = closest_known_terms(raw_candidate, vocabulary)
        if matches:
            selected = matches[0]
            reason = "기존 메뉴 용어 사전과 유사한 후보로 보정"
            inferred = True
            inferred_count += 1
        else:
            selected = raw_candidate
            reason = "OCR 원문을 그대로 사용(용어 사전에서 유사 후보를 찾지 못함)"
            inferred = True
            inferred_count += 1

        confidences.append(avg_conf)
        field_records.append(
            {
                "field": f"{menu_date}_menu_items",
                "paddle_text": comparison["paddle"]["text"] or None,
                "paddle_confidence": comparison["paddle"]["confidence"],
                "tesseract_text": comparison["tesseract"]["text"] or None,
                "tesseract_confidence": comparison["tesseract"]["confidence"],
                "selected_text": selected,
                "selection_reason": reason,
                "agreement": raw_candidate.strip() == selected.strip(),
                "inferred": inferred,
                "candidates": matches,
            }
        )
        entries.append(
            {
                "organization": org_info["display_name"],
                "menu_type": org_info["menu_type"],
                "menu_date": menu_date,
                "weekday": group["weekday"],
                "meal_type": meal_type,
                "menu_items": [selected],
                "source_image_path": str(path),
                "ocr_raw_text": raw_candidate,
            }
        )

    overall_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

    return {
        "success": True,
        "organization_code": org_code,
        "entries": entries,
        "fields": field_records,
        "overall_confidence": overall_confidence,
        "inferred_field_count": inferred_count,
        "unreadable_field_count": unreadable_count,
        "warnings": warnings,
        "error": None,
    }


def _entries_to_sidecar_text(entries: list[dict]) -> str:
    lines = []
    for entry in sorted(entries, key=lambda e: (e["menu_date"], e["meal_type"])):
        items = ", ".join(entry["menu_items"])
        lines.append(f"{entry['menu_date']} {entry['weekday']} {entry['meal_type']}: {items}")
    return "\n".join(lines) + "\n"


# =============================================================================
# 새 이미지 하나로 자동 등록 (선택 기능)
# =============================================================================

_PROCESSED_IMAGES_LOG = OCR_PREVIEW_DIR / "processed_images.json"


def _load_processed_log() -> dict:
    if not _PROCESSED_IMAGES_LOG.exists():
        return {}
    try:
        return json.loads(_PROCESSED_IMAGES_LOG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_processed_log(log: dict) -> None:
    OCR_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    _PROCESSED_IMAGES_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def import_menu_image(
    image_path: str | Path,
    store: MenuFileStore | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """새 식단표 이미지 한 장을 OCR로 읽어 자동으로 Menu Agent에 반영한다.

    흐름: 이미지 검사 -> 업체 판별 -> OCR(PaddleOCR+Tesseract) -> 불확실한
    필드 추정 -> 임시 위치에 TXT/메타데이터 생성 -> 파서로 검증 -> 검증
    통과 시에만 정식 위치로 원자적 이동 -> ``reload_menu_data()`` ->
    ``get_menu()`` 재조회로 확인.

    안전장치:
        - 이미지와 같은 이름의 ``.txt``(정식 sidecar)가 이미 있으면 그대로
          두고 실패 처리한다(덮어쓰지 않음).
        - 임시 파일에 먼저 쓰고, ``menu_parser``로 파싱이 성공해야만 정식
          위치로 옮긴다. 검증에 실패하면 임시 파일을 지우고 아무 것도
          바꾸지 않는다.
        - 이미지 해시로 이미 처리한 이미지를 다시 처리하지 않는다.
        - SQLite는 전혀 쓰지 않는다.

    반환값 예시는 모듈 docstring과 요구사항 문서를 참고. 상태값:
        - "imported": 추정 없이 정상 반영
        - "imported_with_inference": 일부 필드를 추정해서 반영(경고 포함)
        - "rejected": 반영하지 않음(``failed_stage``/``error``에 사유)
    """
    path = Path(image_path)

    def _rejected(stage: str, error: str) -> dict:
        return {
            "success": False,
            "status": "rejected",
            "failed_stage": stage,
            "data_changed": False,
            "error": error,
        }

    try:
        img_error = validate_image(path)
        if img_error:
            return _rejected("image_validation", img_error)

        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            return _rejected(
                "existing_txt_protection",
                f"이미 정식 sidecar TXT가 있어 자동 등록을 중단했습니다: {sidecar}",
            )

        image_hash = compute_image_hash(path)
        processed_log = _load_processed_log()
        if image_hash in processed_log:
            return _rejected(
                "duplicate_image",
                f"이미 처리된 이미지입니다(이전 처리: {processed_log[image_hash].get('image_path')}).",
            )

        inference = infer_menu_fields(path, store=store)
        if not inference["success"]:
            return _rejected("ocr_inference", inference["error"])

        org_code = inference["organization_code"]
        org_info = ORGANIZATIONS[org_code]
        entries = inference["entries"]

        store_for_conflict_check = store or get_store()
        conflicts = []
        for entry in entries:
            entry_id = make_entry_id(
                entry["organization"], entry["menu_type"], entry["menu_date"], entry["meal_type"]
            )
            existing = store_for_conflict_check.get_by_id(entry_id)
            if existing and existing.get("source_image_path") not in (str(path), entry["source_image_path"]):
                conflicts.append(entry_id)
        if conflicts:
            return _rejected(
                "duplicate_date_conflict",
                f"이미 다른 이미지로 등록된 업체·날짜·끼니와 충돌합니다: {', '.join(conflicts)}",
            )

        sidecar_text = _entries_to_sidecar_text(entries)
        metadata = {
            "source_image": str(path),
            "overall_confidence": inference["overall_confidence"],
            "fields": inference["fields"],
            "inferred_field_count": inference["inferred_field_count"],
            "unreadable_field_count": inference["unreadable_field_count"],
        }
        meta_path = path.with_suffix(".ocr_meta.json")

        # 임시 파일에 먼저 쓰고 파서로 검증한 뒤에만 정식 위치로 옮긴다(원자적 반영).
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_txt = Path(tmp_dir) / "candidate.txt"
            tmp_txt.write_text(sidecar_text, encoding="utf-8")

            parse_result = parse_ocr_text(
                sidecar_text,
                organization=org_info["display_name"],
                menu_type=org_info["menu_type"],
                source_image_path=str(path),
            )
            if not parse_result.success or not parse_result.entries:
                return _rejected(
                    "txt_validation",
                    f"생성한 TXT가 파서 검증을 통과하지 못했습니다: {parse_result.error}",
                )

            shutil.copyfile(tmp_txt, sidecar)

        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        reload_summary = reload_menu_data()

        verify_result = get_menu(f"{org_info['display_name']} 메뉴")
        reloaded_ok = reload_summary["entry_count"] > 0

        processed_log[image_hash] = {"image_path": str(path), "processed_at": get_now_kst().isoformat()}
        _save_processed_log(processed_log)

        warnings = []
        status = "imported"
        if inference["inferred_field_count"] > 0:
            status = "imported_with_inference"
            warnings.append(
                f"{inference['inferred_field_count']}개 필드를 OCR 후보 및 문맥으로 추정했습니다."
            )
        if inference["unreadable_field_count"] > 0:
            warnings.append(f"{inference['unreadable_field_count']}개 필드는 판독하지 못해 '확인불가'로 저장했습니다.")

        return {
            "success": True,
            "status": status,
            "organization": org_info["display_name"],
            "image_path": str(path),
            "text_path": str(sidecar),
            "metadata_path": str(meta_path),
            "entry_count": len(entries),
            "ocr_confidence": inference["overall_confidence"],
            "inferred_field_count": inference["inferred_field_count"],
            "unreadable_field_count": inference["unreadable_field_count"],
            "reloaded": reloaded_ok,
            "warnings": warnings,
            "error": None,
        }
    except Exception as exc:  # 어떤 예외가 나도 기존 데이터는 바뀌지 않는다.
        return {
            "success": False,
            "status": "rejected",
            "failed_stage": "unexpected_error",
            "data_changed": False,
            "error": f"자동 등록 중 예상치 못한 오류가 발생했습니다: {exc}",
        }


# =============================================================================
# Public Tool interface (POST /chat 라우터 등 다른 팀이 연결하는 지점)
# =============================================================================


def handle_chat_message(user_input: str, thread_id: str | None = None) -> dict:
    """``POST /chat`` 규격(고정 입출력 필드)에 맞춰 메뉴 질문에 답한다.

    입력: user_input(질문 문자열), thread_id(대화 스레드 식별자, 현재는 세션
    구분 용도로만 받고 내부 로직에서는 사용하지 않는다 - 메뉴 조회는
    무상태(stateless)라 대화 이력에 의존하지 않는다).

    출력은 항상 다음 고정된 3개 필드를 갖는다(예외가 발생해도 동일):
        {"text": str, "action": str | None, "show_buttons": bool}
    """

    del thread_id  # 메뉴 조회는 무상태이므로 현재는 사용하지 않는다.

    result = get_menu(user_input)

    return {
        "text": result["answer"],
        "action": None,
        "show_buttons": True,
    }


@dataclass
class MenuTool:
    """다른 Agent/라우터/오케스트레이션 코드가 import해서 쓰는 공개 Tool 객체.

    실제로 지원하는 호출 방식은 다음 두 가지뿐이다(둘 다 같은 함수를 부른다).

        tool.invoke({"user_input": "오늘 KT 메뉴 뭐야?", "thread_id": "t-1"})
        tool.run(user_input="오늘 KT 메뉴 뭐야?", thread_id="t-1")

    ``invoke``는 인자를 dict 하나로 받고(LangChain 등 다른 오케스트레이션
    코드의 Runnable.invoke(...) 관례와 맞춘 것), ``run``은 같은 인자를
    키워드 인자로 받는다. 둘 다 내부적으로 같은 핸들러 함수를 호출하므로
    동작은 동일하다. 인자 이름/개수는 Tool마다 다르므로(예:
    ``menu_agent_tool``은 user_input/thread_id, ``menu_image_import_tool``은
    image_path), 실제 지원 인자는 각 Tool의 ``description``을 참고한다.
    """

    name: str
    description: str
    _handler: object  # Callable[..., dict], dataclass가 Callable 타입 힌트를 그대로 받으면 순서 문제가 생겨 object로 둠

    def invoke(self, input: dict | None = None) -> dict:
        return self._handler(**(input or {}))

    def run(self, **kwargs) -> dict:
        return self._handler(**kwargs)


menu_agent_tool = MenuTool(
    name="menu_agent",
    description=(
        "대성학원/KT 일반식당/KT 샐러드의 날짜·요일·끼니별 식단을 조회하는 챗봇용 Tool. "
        "인자: user_input(str, 필수), thread_id(str, 선택). "
        "반환: {text, action, show_buttons} (POST /chat과 동일한 고정 스키마)."
    ),
    _handler=handle_chat_message,
)

menu_current_tool = MenuTool(
    name="menu_current",
    description=(
        "대시보드에 자동 표시할 '지금 시각 기준' 메뉴를 조회하는 관리자/대시보드용 Tool. "
        "인자: now(datetime, 선택 — 생략하면 현재 KST 시각). "
        "반환: get_current_menu()와 동일한 {success, query, conditions, results, answer, error}."
    ),
    _handler=get_current_menu,
)

menu_image_import_tool = MenuTool(
    name="menu_image_import",
    description=(
        "새 식단표 이미지 한 장을 OCR로 읽어 자동 등록하는 관리자 전용 Tool. "
        "인자: image_path(str | Path, 필수). "
        "반환: import_menu_image()와 동일한 {success, status, ...}. "
        "일반 사용자 챗봇 대화에는 노출하지 않는다(MENU_ADMIN_TOOLS 참고)."
    ),
    _handler=import_menu_image,
)


# 일반 사용자 챗봇(POST /chat 등)에 연결할 Tool 목록.
MENU_AGENT_TOOLS = [menu_agent_tool]

# 관리자/대시보드 전용 Tool 목록(새 이미지 등록, 대시보드 조회). 일반 사용자
# 대화 흐름에는 노출하지 않는다.
MENU_ADMIN_TOOLS = [menu_current_tool, menu_image_import_tool]


class ChatRequest(BaseModel):
    """``POST /chat`` 요청 본문. 다른 Agent(예: 출결 Agent)와 동일한 규격."""

    user_input: str = Field(..., max_length=500, description="사용자 질문")
    thread_id: str = Field(..., description="세션 식별자")


class ChatResponse(BaseModel):
    """``POST /chat`` 응답 본문. 다른 Agent(예: 출결 Agent)와 동일한 규격."""

    text: str
    action: str | None = None
    show_buttons: bool = True


menu_router = APIRouter()


@menu_router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """다른 Agent와 동일한 입출력 규격을 쓰는 챗봇 엔드포인트.

    현재는 Menu Agent Tool 하나만 연결되어 있다. 여러 Agent를 붙이려면
    이 함수 안에서 user_input을 보고 어떤 Tool로 라우팅할지 분기하면 된다.
    ``app/main.py``는 이 라우터를 import해 ``include_router``만 수행한다.
    """

    result = menu_agent_tool.invoke({"user_input": request.user_input, "thread_id": request.thread_id})
    return ChatResponse(**result)


__all__ = [
    "get_menu",
    "get_current_menu",
    "reload_menu_data",
    "check_ocr_status",
    "preview_menu_ocr",
    "import_menu_image",
    "handle_chat_message",
    "menu_agent_tool",
    "menu_current_tool",
    "menu_image_import_tool",
    "MENU_AGENT_TOOLS",
    "MENU_ADMIN_TOOLS",
    "ChatRequest",
    "ChatResponse",
    "menu_router",
]


def print_all_menu_entries(store: "MenuFileStore | None" = None) -> None:
    """적재된 전체 식단 데이터를 사람이 눈으로 검수할 수 있도록 출력한다.
    Vision 추출 결과가 실제 이미지와 맞는지 확인할 때 사용한다.
    """
    store = store or get_store()
    entries = store.get_all()
    print(f"\n총 {len(entries)}개 항목 적재됨\n")
    for e in entries:
        items = ", ".join(e["menu_items"])
        print(f"[{e['organization']}] {e['menu_date']}({e['weekday']}) {e['meal_type']}: {items}")

    if store.errors:
        print(f"\n⚠ 처리 실패한 이미지 {len(store.errors)}건:")
        for err in store.errors:
            print(f"  - {err.image_path}: {err.error}")


if __name__ == "__main__":
    # 간단한 수동 확인용 진입점: uv run python -m app.menu_agent_tool
    reload_summary = reload_menu_data()
    print(f"적재 결과: {reload_summary['entry_count']}건, 오류 {len(reload_summary['errors'])}건\n")

    print_all_menu_entries()

    result = get_menu("오늘 KT 메뉴 뭐야?")
    print(f"\n샘플 질의 결과:\n{result['answer']}")

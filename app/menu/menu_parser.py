"""OCR로 추출한 원문 텍스트를 날짜/요일/식사종류/메뉴로 구조화한다.

식단표마다 실제 레이아웃이 다르기 때문에, 모든 형식을 완벽히 처리하는
범용 파서를 만들지 않는다. 대신 아래처럼 "한 줄 = 하루/한 끼" 형태의
단순한 표준 포맷을 정의하고, OCR(또는 Mock OCR) 결과가 이 포맷에 맞게
정리되어 있다고 가정한다.

기대하는 한 줄 형식:
    2026-07-22 수요일 점심: 제육볶음, 미역국, 배추김치

빈 줄이나 이 형식에 맞지 않는 줄은 무시한다. 실제 서비스에서는 OCR 결과가
이 형식과 다르게 나올 수 있으므로, 필요하면 업체별로 전처리 함수를
추가하거나 OCR 결과를 사람이 이 포맷으로 다듬어 저장하는 방식(JSON 수정)을
병행할 수 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.menu.config import WEEKDAYS

_LINE_PATTERN = re.compile(
    r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<weekday>\S+요일)\s+(?P<meal_type>\S+)\s*[:：]\s*(?P<items>.+?)\s*$"
)


@dataclass
class ParseResult:
    success: bool
    entries: list[dict] = field(default_factory=list)
    error: str | None = None


def _split_items(raw_items: str) -> list[str]:
    # 쉼표, 가운뎃점, 슬래시 등 흔히 쓰이는 구분자를 모두 처리한다.
    parts = re.split(r"[,，·/]", raw_items)
    return [p.strip() for p in parts if p.strip()]


def parse_ocr_text(
    raw_text: str,
    organization: str,
    menu_type: str,
    source_image_path: str,
) -> ParseResult:
    """OCR 원문 텍스트를 MenuEntry 딕셔너리 리스트로 변환한다.

    organization: 표시용 업체명 (예: "KT", "대성학원")
    menu_type: "general" 또는 "salad" 등 config.ORGANIZATIONS의 menu_type 값
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

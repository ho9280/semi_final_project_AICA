"""식단표 이미지에서 글자를 추출하는 OCR 모듈.

실제 OCR 엔진이 없어도 개발/테스트를 진행할 수 있도록
``MockOCRProvider``를 기본으로 제공한다. 이미지 파일과 같은 이름의
``.txt`` 파일(sidecar)이 있으면 그 내용을 "OCR로 읽은 결과"처럼 사용한다.

예) data/menu/kt/kt_2026-07-20.png  <-  이미지
    data/menu/kt/kt_2026-07-20.txt  <-  Mock OCR 결과(사람이 미리 적어둔 텍스트)

실제 OCR이 필요해지면 ``TesseractOCRProvider``를 사용하거나, 같은
인터페이스(``OCRProvider``)를 구현하는 새 클래스를 추가하면 된다.
``menu_agent.py``나 상위 코드는 provider 종류와 무관하게 동작한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.menu.config import SUPPORTED_IMAGE_EXTENSIONS

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - pillow는 필수 의존성으로 설치되어 있어야 함
    Image = None
    UnidentifiedImageError = Exception


@dataclass
class OCRResult:
    """OCR 처리 결과. 실패해도 항상 이 형태로 반환한다."""

    success: bool
    text: str | None
    error: str | None
    image_path: str


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


class MockOCRProvider:
    """실제 OCR 없이 테스트/개발용으로 사용하는 Mock 구현.

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

    1. Python 패키지 설치: ``uv add pytesseract``
    2. 별도 프로그램 설치: Windows용 Tesseract-OCR 설치 프로그램
       (https://github.com/UB-Mannheim/tesseract/wiki) + 한국어 언어팩(kor.traineddata)
    3. 환경변수 설정: tesseract.exe가 PATH에 없다면 ``TESSERACT_CMD``
       환경변수에 실행 파일 전체 경로를 지정해야 한다.

    이 클래스는 이번 MVP의 기본 경로가 아니며, 위 준비물이 갖춰진 팀원만
    선택적으로 사용한다. 준비물이 없는 상태로 호출하면 명확한 에러를 낸다.
    """

    def __init__(self, lang: str = "kor+eng") -> None:
        self.lang = lang

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

        try:
            with Image.open(path) as img:
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

import os
from pathlib import Path
import pymupdf4llm


def convert_raw_pdf_to_processed_md() -> None:
    """raw 폴더의 한글 PDF 파일들을 딕셔너리 매핑에 따라 processed 폴더의 영문 .md 파일로 일괄 변환합니다."""

    # 1. 경로 설정
    base_dir: Path = Path(r"C:\workspace\semi_final_project_AICA")
    raw_dir: Path = base_dir / "data" / "raw"
    processed_dir: Path = base_dir / "data" / "processed"

    # processed 디렉터리가 없을 경우 자동 생성
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 2. 파일명 1:1 영문 매핑 테이블 (한글 PDF 파일명 -> 영문 MD 파일명)
    filename_mapping: dict[str, str] = {
        "인공지능사관학교_7기 출결 기준_260417.pdf": "aica_attendance_rules.md",
        "7기 교육지원금, 입학지원금__260420.pdf": "aica_financial_support.md",
    }

    print("=== PDF to Markdown 변환 작업을 시작합니다 ===")

    # 3. 매핑된 파일 반복 변환 처리
    for raw_pdf_name, target_md_name in filename_mapping.items():
        pdf_path: Path = raw_dir / raw_pdf_name
        md_path: Path = processed_dir / target_md_name

        # RAW 폴더에 해당 PDF가 존재하는지 체크
        if not pdf_path.exists():
            print(f"[SKIP/WARNING] 원본 파일을 찾을 수 없습니다: {pdf_path}")
            continue

        try:
            # pymupdf4llm을 활용한 레이아웃/표 유지 마크다운 변환
            md_text: str = pymupdf4llm.to_markdown(str(pdf_path))

            # UTF-8 인코딩으로 마크다운 파일 저장
            md_path.write_bytes(md_text.encode("utf-8"))

            print(f"[SUCCESS] {raw_pdf_name}")
            print(f"       └─> {md_path}")

        except Exception as e:
            print(f"[ERROR] {raw_pdf_name} 변환 중 오류 발생: {e}")

    print("=== 모든 변환 작업이 완료되었습니다 ===")


if __name__ == "__main__":
    convert_raw_pdf_to_processed_md()
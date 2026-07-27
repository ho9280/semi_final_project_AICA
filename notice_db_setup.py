"""
공지사항 DB 생성 및 데이터 적재 스크립트

실행 방법:
    python notice_db_setup.py

사전 설치 필요:
    pip install python-docx
"""

import sqlite3
import os
import re
from docx import Document


# ───────────────────────────────────────────
# 경로 설정 (필요 시 수정)
# ───────────────────────────────────────────
DOCX_PATH       = "AICA_notice/notice_AICA.docx"       # 공지사항 문서 경로
ATTACHMENT_DIR  = "AICA_notice/notice_attachment"       # 첨부파일 폴더 경로
DB_PATH         = "db/notices.db"                       # DB 저장 경로

# Word numbering XML 네임스페이스
NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ───────────────────────────────────────────
# 1. DB 및 테이블 생성
# ───────────────────────────────────────────
def create_database(db_path: str) -> sqlite3.Connection:
    """DB 파일 생성 및 테이블 초기화"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # notices 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notices (
            notice_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            release_date DATE,
            content      TEXT
        )
    """)

    # notice_attachments 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notice_attachments (
            attachment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id       INTEGER NOT NULL,
            file_name       TEXT,
            attachment_path TEXT,
            file_type       TEXT,
            FOREIGN KEY (notice_id) REFERENCES notices(notice_id)
        )
    """)

    conn.commit()
    print("✅ DB 및 테이블 생성 완료")
    return conn


# ───────────────────────────────────────────
# 2. docx 파싱
# ───────────────────────────────────────────
def is_notice_title(para) -> bool:
    """Word 자동 번호 목록(ilvl=0)인지 확인 → 공지 제목 단락 판별"""
    ilvl  = para._element.find(f".//{{{NS}}}ilvl")
    numId = para._element.find(f".//{{{NS}}}numId")
    if ilvl is None or numId is None:
        return False
    return ilvl.get(f"{{{NS}}}val") == "0"


def normalize_date(raw: str) -> str:
    """
    다양한 날짜 형식을 YYYY-MM-DD로 변환
    예: 26/05/08 → 2026-05-08 / 2026/05/06 → 2026-05-06
    """
    parts = re.split(r"[/\-]", raw.strip())
    if len(parts) != 3:
        return raw
    year, month, day = parts
    if len(year) == 2:
        year = "20" + year
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def parse_title_and_date(text: str):
    """
    제목 단락에서 제목과 날짜를 분리
    예: "출석인정(공가) 서류 제출 안내 2026/05/06"
        → title="출석인정(공가) 서류 제출 안내", date="2026-05-06"
    """
    # 끝 부분의 날짜 패턴 추출
    match = re.search(r"(\d{2,4}[/\-]\d{2}[/\-]\d{2})\s*$", text)
    if match:
        raw_date = match.group(1)
        title = text[:match.start()].strip()
        return title, normalize_date(raw_date)
    return text.strip(), None


def parse_notices(docx_path: str) -> list:
    """
    docx에서 공지사항 목록을 파싱하여 반환

    반환 형태:
        [
            {
                "title": "...",
                "release_date": "2026-05-06",
                "content": "...",
                "attachments": ["파일명.pdf", ...]
            },
            ...
        ]
    """
    doc = Document(docx_path)
    notices = []
    current = None

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if is_notice_title(para):
            # 이전 공지 저장
            if current:
                notices.append(current)

            title, release_date = parse_title_and_date(text)
            current = {
                "title": title,
                "release_date": release_date,
                "content": "",
                "attachments": []
            }

        elif current:
            # [첨부] 파일명 감지
            attachment_match = re.match(r"^\[첨부\]\s+(.+)$", text)
            if attachment_match:
                current["attachments"].append(attachment_match.group(1).strip())
            else:
                # 본문 누적
                current["content"] += text + "\n"

    # 마지막 공지 저장
    if current:
        notices.append(current)

    print(f"✅ 공지사항 파싱 완료: {len(notices)}건")
    return notices


# ───────────────────────────────────────────
# 3. notices 테이블 삽입
# ───────────────────────────────────────────
def insert_notices(conn: sqlite3.Connection, notices: list) -> list:
    """
    공지사항을 notices 테이블에 삽입
    삽입된 notice_id를 각 항목에 추가하여 반환
    """
    cursor = conn.cursor()

    for notice in notices:
        cursor.execute("""
            INSERT INTO notices (title, release_date, content)
            VALUES (?, ?, ?)
        """, (
            notice["title"],
            notice["release_date"],
            notice["content"].strip()
        ))
        # 방금 삽입된 notice_id를 저장 (첨부파일 연결에 사용)
        notice["notice_id"] = cursor.lastrowid

    conn.commit()
    print(f"✅ notices 삽입 완료: {len(notices)}건")
    return notices


# ───────────────────────────────────────────
# 4. notice_attachments 테이블 삽입
# ───────────────────────────────────────────
def insert_attachments(conn: sqlite3.Connection, notices: list, attachment_dir: str):
    """
    첨부파일 정보를 notice_attachments 테이블에 삽입
    notice_id 폴더 내 실제 파일이 존재하는 경우에만 저장
    """
    cursor = conn.cursor()
    total = 0

    for notice in notices:
        notice_id = notice["notice_id"]
        folder_path = os.path.join(attachment_dir, str(notice_id))

        # 해당 notice_id 폴더가 없으면 건너뜀
        if not os.path.isdir(folder_path):
            continue

        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)

            # 파일만 처리 (하위 폴더 제외)
            if not os.path.isfile(file_path):
                continue

            file_type = os.path.splitext(file_name)[-1].lstrip(".").lower()

            cursor.execute("""
                INSERT INTO notice_attachments (notice_id, file_name, attachment_path, file_type)
                VALUES (?, ?, ?, ?)
            """, (
                notice_id,
                file_name,
                file_path,
                file_type
            ))
            total += 1

    conn.commit()
    print(f"✅ notice_attachments 삽입 완료: {total}건")


# ───────────────────────────────────────────
# 5. 검증 출력
# ───────────────────────────────────────────
def verify(conn: sqlite3.Connection):
    """적재 결과 간단 확인"""
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM notices")
    print(f"\n📋 notices 총 {cursor.fetchone()[0]}건")

    cursor.execute("SELECT COUNT(*) FROM notice_attachments")
    print(f"📎 notice_attachments 총 {cursor.fetchone()[0]}건")

    print("\n--- 샘플 (notices 상위 3건) ---")
    for row in cursor.execute("SELECT notice_id, title, release_date FROM notices LIMIT 3"):
        print(row)

    print("\n--- 샘플 (notice_attachments 상위 3건) ---")
    for row in cursor.execute("SELECT * FROM notice_attachments LIMIT 3"):
        print(row)


# ───────────────────────────────────────────
# 실행
# ───────────────────────────────────────────
if __name__ == "__main__":
    conn = create_database(DB_PATH)
    notices = parse_notices(DOCX_PATH)
    notices = insert_notices(conn, notices)
    insert_attachments(conn, notices, ATTACHMENT_DIR)
    verify(conn)
    conn.close()
    print("\n✅ 전체 완료")
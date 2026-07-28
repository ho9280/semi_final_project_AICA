import os
import sqlite3

# 상대 경로 설정 (팀원/Git 공유 시 경로 깨짐 방지)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "complaints.db")


def init_db():
    """FastAPI 서버 시작 시 호출되는 DB 초기화 함수"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 외래키(Foreign Key) 활성화
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. users 테이블
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        birth_date TEXT NOT NULL,  -- 포맷 확정: YYYY-MM-DD (동명이인 구분용, 예: '2001-01-01')
        role TEXT NOT NULL CHECK(role IN ('STUDENT', 'ADMIN'))
    );
    """
    )

    # 2. complaints 테이블 (like_count 포함)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        raw_content TEXT NOT NULL,
        summary TEXT NOT NULL,
        photo_url TEXT,
        status TEXT NOT NULL DEFAULT '접수',
        like_count INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """
    )

    # 3. complaints_likes 테이블 (complaint_id + user_id 복합 PK)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS complaints_likes (
        complaint_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (complaint_id, user_id),
        FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """
    )

    # 4. Seed 데이터 주입 (기본 계정 2개)
    cursor.execute(
        """
    INSERT OR IGNORE INTO users (id, username, password, name, birth_date, role)
    VALUES 
        (1, 'student1', '1234', '이학생', '2001-01-01', 'STUDENT'),
        (2, 'admin1', '1234', '나관리', '1990-01-01', 'ADMIN');
    """
    )
    

    conn.commit()
    conn.close()

    print(
        "✅ DB 테이블 3개(users, complaints, complaints_likes) 및 Seed 데이터 생성 완료!"
    )


if __name__ == "__main__":
    init_db()
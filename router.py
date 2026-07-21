import os
import sqlite3
from datetime import datetime
from sqlite3 import Connection
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

# ==========================================
# 2단계 요약 함수 & 3단계 DTO 클래스 임포트
# ==========================================
from llm_service import summarize_complaint
from schemas import (
    ComplaintCreateRequest,
    ComplaintResponse,
    ComplaintSummaryRequest,
    LikeRequest,
    StatusUpdateRequest,
)

# 프로젝트 상대 경로 기반 DB 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "complaints.db")

router = APIRouter(prefix="/api/complaints", tags=["Complaints"])


def get_db_connection() -> Connection:
    """SQLite DB 커넥션 생성 헬퍼 함수"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Dict 형태로 결과 반환
    return conn
# %%
# ==========================================
# 1. AI 요약 미리보기 API
# ==========================================
@router.post("/summarize", response_model=dict)
def preview_summary(req: ComplaintSummaryRequest):
    """민원 작성 폼에서 [✨ AI 요약하기] 버튼 클릭 시 호출"""
    # 2단계 모듈의 summarize_complaint 호출 (비공개는 0초 스킵, 실패시 Fallback)
    summary_result = summarize_complaint(req.category, req.raw_content)
    return {"summary": summary_result}


# ==========================================
# 2. 민원 최종 제출 API
# ==========================================
@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_complaint(req: ComplaintCreateRequest):
    """학생 작성 폼에서 [🚀 최종 제출하기] 클릭 시 DB 저장"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            INSERT INTO complaints (user_id, category, raw_content, summary, photo_url, status, like_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, '접수', 0, ?, ?)
        """,
            (
                req.user_id,
                req.category,
                req.raw_content,
                req.summary,  # 요약 안 눌렀을 시 'AI 요약을 진행하지 않은 민원입니다.' 저장됨
                req.photo_url,  # 미입력 시 None (DB에는 NULL로 저장)
                created_at,
                created_at,
            ),
        )
        conn.commit()
        complaint_id = cursor.lastrowid
        return {
            "success": True,
            "message": "민원이 정상 접수되었습니다.",
            "id": complaint_id,
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"민원 저장 중 오류 발생: {str(e)}"
        )
    finally:
        conn.close()


# ==========================================
# 3. 민원 피드 목록 조회 API
# ==========================================
@router.get("", response_model=List[ComplaintResponse])
def get_complaints(
    category: Optional[str] = Query(
        None, description="카테고리 필터 (미지정 또는 '전체' 시 전체 조회)"
    ),
    current_user_id: Optional[int] = Query(
        1, description="현재 접속한 유저 ID (공감 여부 계산용)"
    ),
):
    """공개 피드 게시판 카드 목록 조회 (최신순 정렬 + is_liked_by_me 산출)"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 기본 쿼리 (카테고리 필터링 적용)
        if category and category != "전체":
            cursor.execute(
                """
                SELECT c.*, 
                       EXISTS(SELECT 1 FROM complaints_likes l WHERE l.complaint_id = c.id AND l.user_id = ?) as is_liked
                FROM complaints c
                WHERE c.category = ?
                ORDER BY c.created_at DESC
            """,
                (current_user_id, category),
            )
        else:
            cursor.execute(
                """
                SELECT c.*, 
                       EXISTS(SELECT 1 FROM complaints_likes l WHERE l.complaint_id = c.id AND l.user_id = ?) as is_liked
                FROM complaints c
                ORDER BY c.created_at DESC
            """,
                (current_user_id,),
            )

        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append(
                ComplaintResponse(
                    id=row["id"],
                    user_id=row["user_id"],
                    category=row["category"],
                    raw_content=row["raw_content"],
                    summary=row["summary"],
                    photo_url=row["photo_url"],
                    status=row["status"],
                    like_count=row["like_count"],
                    is_liked_by_me=bool(row["is_liked"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return result
    finally:
        conn.close()


# ==========================================
# 4. 1인 1회 단방향 공감(좋아요) API
# ==========================================
@router.post("/{complaint_id}/like", response_model=dict)
def like_complaint(complaint_id: int, req: LikeRequest):
    """공감 하트 버튼 클릭 시 단방향 공감 처리 (중복 방지 및 최신 like_count 반환)"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 이미 공감했는지 확인
        cursor.execute(
            "SELECT 1 FROM complaints_likes WHERE complaint_id = ? AND user_id = ?",
            (complaint_id, req.user_id),
        )
        already_liked = cursor.fetchone()

        if already_liked:
            # 취소 없이 현재 최신 공감수만 조회하여 반환
            cursor.execute(
                "SELECT like_count FROM complaints WHERE id = ?",
                (complaint_id,),
            )
            current_count = cursor.fetchone()["like_count"]
            return {
                "success": False,
                "message": "이미 공감한 민원입니다.",
                "like_count": current_count,
            }

        # 처음 누른 경우: likes 테이블에 추가 + complaints like_count +1
        cursor.execute(
            "INSERT INTO complaints_likes (complaint_id, user_id) VALUES (?, ?)",
            (complaint_id, req.user_id),
        )
        cursor.execute(
            "UPDATE complaints SET like_count = like_count + 1 WHERE id = ?",
            (complaint_id,),
        )
        conn.commit()

        # 업데이트된 최신 like_count 조회
        cursor.execute(
            "SELECT like_count FROM complaints WHERE id = ?", (complaint_id,)
        )
        new_count = cursor.fetchone()["like_count"]

        return {
            "success": True,
            "message": "공감이 반영되었습니다.",
            "like_count": new_count,
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"공감 처리 중 오류 발생: {str(e)}"
        )
    finally:
        conn.close()


# ==========================================
# 5. 관리자 상태 변경 API
# ==========================================
@router.patch("/{complaint_id}/status", response_model=dict)
def update_complaint_status(complaint_id: int, req: StatusUpdateRequest):
    """관리자 모달에서 처리 상태 변경 (접수, 처리 중, 처리 완료, 승인 거절)"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            "UPDATE complaints SET status = ?, updated_at = ? WHERE id = ?",
            (req.status, updated_at, complaint_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail="해당 민원을 찾을 수 없습니다."
            )

        conn.commit()
        return {
            "success": True,
            "message": f"상태가 '{req.status}'(으)로 변경되었습니다.",
            "status": req.status,
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"상태 변경 중 오류 발생: {str(e)}"
        )
    finally:
        conn.close()



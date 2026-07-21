# %%
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# 1. 민원 AI 요약 요청 DTO (작성 폼에서 [✨ AI 요약하기] 버튼 클릭 시)
class ComplaintSummaryRequest(BaseModel):
    category: str = Field(..., description="선택된 카테고리")
    raw_content: str = Field(
        ..., max_length=1000, description="작성 원문 (최대 1,000자)"
    )


# 2. 민원 최종 제출 요청 DTO (학생 작성 폼 제출 시)
class ComplaintCreateRequest(BaseModel):
    user_id: int
    category: str
    raw_content: str = Field(..., max_length=1000)
    # 요약 미실행 시 확정 문구 저장
    summary: str = "AI 요약을 진행하지 않은 민원입니다."
    # 첨부파일 없으면 None (DB에는 NULL로 저장)
    photo_url: Optional[str] = None


# 3. 관리자 상태 변경 요청 DTO
class StatusUpdateRequest(BaseModel):
    status: str  # 접수, 처리 중, 처리 완료, 승인 거절


# 4. 공감/좋아요 요청 DTO
class LikeRequest(BaseModel):
    user_id: int


# 5. 민원 응답 DTO (피드/목록 출력용)
class ComplaintResponse(BaseModel):
    id: int
    user_id: int
    category: str
    raw_content: str
    summary: str = "AI 요약을 진행하지 않은 민원입니다."
    photo_url: Optional[str] = None
    status: str = "접수"
    like_count: int = 0
    is_liked_by_me: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
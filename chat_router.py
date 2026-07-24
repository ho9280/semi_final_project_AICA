"""
광주인공지능사관학교 7기 챗봇 메인 라우터
파일명: chat_router.py
포트: 8001
기존 파일 수정 없음
"""

import math
import sqlite3
import os
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel, Field

# =====================
# attendance_agent에서 workflow, AgentState import
# =====================
from attendance_agent import workflow, AgentState

# =====================
# 1. FastAPI 앱 생성 + CORS
# =====================
app = FastAPI(title="광주 AI 아카데미 챗봇 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================
# 2. SqliteSaver 연결 + workflow 재컴파일
# =====================
conn = sqlite3.connect("data/chatbot_memory.db", check_same_thread=False)
memory = SqliteSaver(conn)
attendance_agent_app = workflow.compile(checkpointer=memory)

FIXED_THREAD_ID = "aica_demo_session"

# =====================
# 3. LLM 초기화
# =====================
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# =====================
# 4. 월별 총 수업일수 (요건정의서 11.2절)
# =====================
MONTH_TOTAL_DAYS = {
    5: 17, 6: 21, 7: 22, 8: 20,
    9: 20, 10: 20, 11: 21, 12: 9
}

# =====================
# 5. 키워드 분기 설정 (우선순위: 출결 > 공지 > 식단 > 기타)
# =====================
KEYWORDS = {
    "출결": ["출결", "지각", "조퇴", "외출", "공가", "결석", "수료", "출석", "지원금"],
    "공지": ["공지", "안내", "공고"],
    "식단": ["식단", "메뉴", "점심", "저녁", "중식", "석식", "밥"],
}

def classify_intent(user_input: str) -> str:
    """키워드 매칭으로 의도 분류 (우선순위: 출결 > 공지 > 식단 > 기타)"""
    for category, keywords in KEYWORDS.items():
        for keyword in keywords:
            if keyword in user_input:
                return category
    return "기타"


# =====================
# 6. 미완성 Agent 임시 응답
# 완성 시 아래 함수 내부만 교체
# =====================

# [공지 Agent] 완성 시 이 함수 내부만 교체
def notice_agent_response(user_input: str) -> str:
    # TODO: 공지 agent 완성 시 교체
    return "공지사항 관련 질문으로 안내드릴게요.\n현재 준비 중입니다."


# [식단 Agent] 완성 시 이 함수 내부만 교체
def meal_agent_response(user_input: str) -> str:
    # TODO: 식단 agent 완성 시 교체
    return "식단 관련 질문으로 안내드릴게요.\n현재 준비 중입니다."


# =====================
# 7. 기타 Agent (OpenAI 직접 호출)
# =====================
def general_agent_response(user_input: str) -> str:
    """기타 질문 처리 - OpenAI 직접 호출"""
    system_prompt = (
        "당신은 광주인공지능사관학교 7기 학습·생활 보조 챗봇입니다.\n"
        "학생들의 앱 사용법, 메뉴 위치 안내 등 일반적인 질문에 친절하게 답변해 주세요.\n"
        "답변은 간결하고 명확하게 작성해 주세요."
    )
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ])
    return response.content


# =====================
# 8. Pydantic DTO
# =====================
class ChatRequest(BaseModel):
    user_input: str = Field(..., description="사용자 질문")
    thread_id: str = Field(default=FIXED_THREAD_ID, description="세션 식별자")

class ChatResponse(BaseModel):
    text: str
    action: str | None = None
    show_buttons: bool = True

class AttendanceCalculateRequest(BaseModel):
    absence: int = 0
    lateness: int = 0
    early_leave: int = 0
    outing: int = 0
    official_leave: int = 0


# =====================
# 9. POST /chat 엔드포인트
# =====================
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """챗봇 메인 엔드포인트 - 키워드 분기 후 agent 호출"""
    try:
        intent = classify_intent(request.user_input)
        config = {"configurable": {"thread_id": request.thread_id}}

        if intent == "출결":
            if request.user_input.strip() in ["출결"]:
                month = datetime.now().month
                return ChatResponse(
                    text=f"출결 관련 질문으로 안내드릴게요.\n출결 규정, 공가, 지각/조퇴 환산, 지원금 기준 등 궁금하신 내용을 입력해 주세요.\n\n🧮 출결 계산기는 {month}월 기준으로 자동 적용됩니다.",
                    action=None,
                    show_buttons=True
                )
            inputs = {"messages": [HumanMessage(content=request.user_input)]}
            result = attendance_agent_app.invoke(inputs, config=config)
            response_signal = result.get("response_signal", {})
            return ChatResponse(
                text=response_signal.get("text", "오류가 발생했습니다."),
                action=response_signal.get("action"),
                show_buttons=response_signal.get("show_buttons", True)
            )

        elif intent == "공지":
            text = notice_agent_response(request.user_input)
            return ChatResponse(text=text, action=None, show_buttons=True)

        elif intent == "식단":
            text = meal_agent_response(request.user_input)
            return ChatResponse(text=text, action=None, show_buttons=True)

        else:
            text = general_agent_response(request.user_input)
            return ChatResponse(text=text, action=None, show_buttons=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# 10. POST /attendance/calculate 엔드포인트 (JS 필드명 기준)
# =====================
@app.post("/attendance/calculate")
async def calculate_attendance(req: AttendanceCalculateRequest):
    """출결 계산기 모달 연동 엔드포인트 (attendance_agent_ui.js 필드명 기준)"""
    month = datetime.now().month
    total_days = MONTH_TOTAL_DAYS.get(month, 20)

    # 환산 결석일 계산 (각 항목 독립 계산)
    tardy_converted = req.lateness // 3
    early_leave_converted = req.early_leave // 3
    outing_converted = req.outing // 3
    total_absent = req.absence + tardy_converted + early_leave_converted + outing_converted

    # 인정 출석일수 계산
    temp_days = total_days - total_absent + req.official_leave
    recognized_days = min(total_days, max(0, temp_days))

    # 출석률 계산
    attendance_rate = round((recognized_days / total_days) * 100, 2)

    # 잔여 공가 계산
    max_official_leave = math.floor(total_days * 0.2)
    remaining_leave = max(0, max_official_leave - req.official_leave)

    return {
        "attendance_rate": attendance_rate,
        "recognized_days": recognized_days,
        "remaining_leave": remaining_leave
    }



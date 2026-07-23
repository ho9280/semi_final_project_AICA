"""
광주인공지능사관학교 7기 출결 Agent 백엔드 시스템
파일명: attendance_agent.py
설명: FastAPI와 LangGraph를 결합한 의도 분류 및 RAG/Tool 라우팅 구현체
"""

import operator
from typing import Annotated, Dict, Any, Literal, List
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

# -----------------------------------------------------------------------------
# 1. Pydantic DTO (Data Transfer Objects)
# -----------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """프론트엔드로부터 받는 챗봇 요청 DTO"""
    user_input: str = Field(..., max_length=500, description="사용자 질문")
    thread_id: str = Field(..., description="세션 식별자 (예: user123_session1)")

class ChatResponse(BaseModel):
    """프론트엔드로 반환하는 챗봇 응답 DTO"""
    text: str
    action: str | None = None
    show_buttons: bool = True

# -----------------------------------------------------------------------------
# 2. LangGraph State Definition
# -----------------------------------------------------------------------------
class AgentState(TypedDict):
    """LangGraph 상태 객체. 메시지 누적 및 의도(Intent) 신호 저장"""
    messages: Annotated[list[AnyMessage], operator.add]
    intent: str
    response_signal: Dict[str, Any]

# -----------------------------------------------------------------------------
# 3. LangGraph Nodes & Router
# -----------------------------------------------------------------------------
# [추론] gpt-4o-mini 모델을 사용하여 빠르고 정확한 의도 분류 수행
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def node_intent_classifier(state: AgentState) -> Dict[str, Any]:
    """사용자 질문을 분석하여 CALCULATOR 또는 RAG_RULE로 분류하는 노드"""
    messages = state.get("messages", [])
    assert len(messages) > 0, "상태에 메시지가 존재해야 합니다."
    
    user_message = messages[-1].content
    
    system_prompt = (
        "당신은 인공지능사관학교 7기 출결 의도 분류기입니다.\n"
        "사용자의 질문을 분석하여 아래 2가지 카테고리 중 하나로 정확히 분류하고, 오직 해당 영문 카테고리명만 반환하세요.\n"
        "1. CALCULATOR: 지각/조퇴/외출 횟수, 출석률 %, 50%/80% 달성일 등 수치 산출이나 계산이 필요한 질문\n"
        "2. RAG_RULE: 공가 기준, 제출 서류, 환산 규정 설명 등 단순 출결 규정/절차 안내 질문\n\n"
        "[Examples]\n"
        "User: 병공가 신청할 때 제출해야 하는 서류가 뭐야?\nCategory: RAG_RULE\n"
        "User: 나 이번 달 지각 3번 했는데 결석 며칠 처리돼?\nCategory: CALCULATOR\n"
        "User: 지원금 80% 조건 맞추려면 이번 달에 며칠 나와야 돼?\nCategory: CALCULATOR\n"
        "User: 지각 몇 번 해야 결석 1일로 환산돼?\nCategory: RAG_RULE\n"
        "User: 지각 2번에 조퇴 1번이면 출석 인정일수 몇 일이야?\nCategory: CALCULATOR\n"
        "User: 공가는 한 달에 최대 며칠까지 쓸 수 있어?\nCategory: RAG_RULE"
    )
    
    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=str(user_message))])
    intent = response.content.strip().upper()
    
    # 기본값은 RAG_RULE로 폴백(Fallback) 처리
    if intent not in ["CALCULATOR", "RAG_RULE"]:
        intent = "RAG_RULE"
        
    return {"intent": intent}

def route_intent(state: AgentState) -> Literal["node_calculator_popup", "node_rag_rule"]:
    """분류된 의도에 따라 다음 노드로 라우팅"""
    intent = state.get("intent", "RAG_RULE")
    if intent == "CALCULATOR":
        return "node_calculator_popup"
    return "node_rag_rule"

def node_calculator_popup(state: AgentState) -> Dict[str, Any]:
    """수치 계산 질문 시 팝업 유도 신호를 반환하는 노드 (할루시네이션 차단)"""
    msg_text = (
        "출결 관련 질문으로 안내드릴게요.\n"
        "정확한 수치 산출 및 지원금 기준 확인을 위해 아래 출결 계산기를 이용해 주세요!"
    )
    signal = {
        "text": msg_text,
        "action": "OPEN_CALCULATOR_POPUP",
        "show_buttons": True
    }
    return {"messages": [AIMessage(content=msg_text)], "response_signal": signal}

def node_rag_rule(state: AgentState) -> Dict[str, Any]:
    """규정 질문 시 Vector DB RAG를 수행하여 답변을 반환하는 노드"""
    messages = state.get("messages", [])
    user_query = messages[-1].content
    
    # [추론] 실제 환경에서는 retriever.invoke(user_query) 가 호출됨
    retrieved_context = "출결 규정에 따르면 공가 한도는 총 교육일수의 20% 이내이며, 질병의 경우 진료확인서를 제출해야 합니다." 
    
    rag_prompt = (
        "당신은 출결 담당 Agent입니다. 다음 [Context]를 바탕으로 질문에 답변하세요.\n"
        "답변 첫 줄에 반드시 '출결 관련 질문으로 안내드릴게요.'를 포함하세요.\n"
        "답변 마지막에 반드시 '자세한 내용은 공지사항 게시판에서 확인해 주세요.'를 포함하세요.\n"
        "절대로 URL, 하이퍼링크, 다운로드 링크를 생성하거나 [원문보기] 버튼을 만들지 마세요.\n\n"
        f"[Context]: {retrieved_context}"
    )
    
    response = llm.invoke([SystemMessage(content=rag_prompt), HumanMessage(content=str(user_query))])
    signal = {
        "text": response.content,
        "action": None,
        "show_buttons": True
    }
    return {"messages": [AIMessage(content=response.content)], "response_signal": signal}

# -----------------------------------------------------------------------------
# 4. Graph Build & Compile
# -----------------------------------------------------------------------------
workflow = StateGraph(AgentState)

workflow.add_node("node_intent_classifier", node_intent_classifier)
workflow.add_node("node_calculator_popup", node_calculator_popup)
workflow.add_node("node_rag_rule", node_rag_rule)

workflow.set_entry_point("node_intent_classifier")
workflow.add_conditional_edges(
    "node_intent_classifier",
    route_intent,
    {
        "node_calculator_popup": "node_calculator_popup",
        "node_rag_rule": "node_rag_rule"
    }
)

workflow.add_edge("node_calculator_popup", END)
workflow.add_edge("node_rag_rule", END)

# 메모리 객체는 FastAPI 생명주기 또는 의존성 주입 시 SqliteSaver()로 연결
# app = workflow.compile(checkpointer=memory) 
attendance_agent_app = workflow.compile()

# -----------------------------------------------------------------------------
# 5. FastAPI Endpoints
# -----------------------------------------------------------------------------
app = FastAPI(title="인공지능사관학교 출결 API")

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """프론트엔드로부터 자연어 입력을 받아 Agent 로직 처리 후 신호 반환"""
    try:
        inputs = {"messages": [HumanMessage(content=request.user_input)]}
        config = {"configurable": {"thread_id": request.thread_id}}
        
        # Agent 그래프 실행
        result = attendance_agent_app.invoke(inputs, config=config)
        
        response_signal = result.get("response_signal", {})
        assert "text" in response_signal, "응답 신호에 text 필드가 누락되었습니다."
        
        return ChatResponse(
            text=response_signal.get("text", "오류가 발생했습니다."),
            action=response_signal.get("action"),
            show_buttons=response_signal.get("show_buttons", True)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
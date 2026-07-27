"""
5단계: Notice Agent Tool

Supervisor가 Tool Calling으로 호출하는 공지사항 Agent.
검색(Retriever) + LLM 답변 생성까지 수행하여 완성된 답변을 반환합니다.

사용 방법 (Supervisor 쪽):

    # 방법 1: LangChain 네이티브 Tool Calling (bind_tools)
    from notice_agent_tool import notice_agent
    llm_with_tools = llm.bind_tools([notice_agent])

    # 방법 2: 직접 호출 (menu_agent_tool.py와 동일한 패턴)
    from notice_agent_tool import notice_agent_tool
    result = notice_agent_tool.invoke({"query": "공가 신청 서류가 뭐야?"})
"""

import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from notice_retriever import search  # 4단계 검색 함수 재사용

load_dotenv()

# ───────────────────────────────────────────
# 로깅 설정
# ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("notice_agent_log.txt", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ───────────────────────────────────────────
# LLM 및 프롬프트 설정
# ───────────────────────────────────────────
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

CLOSING_PHRASE = "자세한 내용은 공지사항 게시판에서 확인해 주세요."

NOTICE_SYSTEM_PROMPT = (
    "당신은 인공지능사관학교 공지사항 안내 Agent입니다.\n"
    "반드시 아래 [Context]에 있는 내용만 근거로 답변하세요.\n"
    "Context에 없는 내용은 추측하지 말고 모른다고 답하세요.\n"
    "URL, 하이퍼링크, [원문보기] 버튼은 만들지 마세요.\n\n"
    "[Context]:\n{context}"
)


# ───────────────────────────────────────────
# 유틸 함수
# ───────────────────────────────────────────
def build_context(results: list) -> str:
    """검색 결과(Pinecone match 리스트)를 LLM 프롬프트용 텍스트로 변환"""
    parts = []
    for match in results:
        meta = match.metadata
        title = meta.get("title", "-")
        date = meta.get("release_date", "-")
        text = meta.get("text", "")
        parts.append(f"[제목: {title} / 날짜: {date}]\n{text}")
    return "\n\n".join(parts)


def ensure_closing_phrase(text: str) -> str:
    """마감 문구가 없으면 강제로 추가 (LLM 누락 방지)"""
    if CLOSING_PHRASE not in text:
        text = text.rstrip() + "\n\n" + CLOSING_PHRASE
    return text


def build_sources(results: list) -> list:
    """검색 결과를 근거 메타데이터 리스트로 변환"""
    return [
        {
            "source_type"  : m.metadata.get("source_type", "-"),
            "title"        : m.metadata.get("title", "-"),
            "release_date" : m.metadata.get("release_date", "-"),
            "file_name"    : m.metadata.get("file_name", "-"),
            "score"        : round(m.score, 4),
        }
        for m in results
    ]


# ───────────────────────────────────────────
# 핵심 함수: 검색 + 답변 생성
# ───────────────────────────────────────────
def generate_notice_answer(query: str) -> dict:
    """
    공지사항 검색 후 LLM으로 최종 답변 생성
    반환: {"text": str, "action": None, "show_buttons": True, "sources": [...]}
    """
    # 1. 검색
    try:
        results = search(query)
    except Exception as e:
        logger.error(f"[검색 오류] query={query} | {e}")
        return {
            "text": ensure_closing_phrase("공지사항 검색 중 오류가 발생했습니다."),
            "action": None,
            "show_buttons": True,
            "sources": []
        }
    
    # 2. 검색 결과 없음 → LLM 호출 없이 즉시 반환 (할루시네이션 방지)
    if not results:
        logger.info(f"[검색 결과 없음] query={query}")
        return {
            "text": ensure_closing_phrase("관련된 공지사항을 찾지 못했습니다. 다른 표현으로 다시 질문해 주세요."),
            "action": None,
            "show_buttons": True,
            "sources": []
        }

    # 3. LLM 답변 생성
    context = build_context(results)
    system_prompt = NOTICE_SYSTEM_PROMPT.format(context=context)

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ])
        answer_text = ensure_closing_phrase(response.content)
    except Exception as e:
        logger.error(f"[LLM 오류] query={query} | {e}")
        answer_text = ensure_closing_phrase("답변 생성 중 오류가 발생했습니다.")

    logger.info(f"[답변 생성 완료] query={query} | 근거 {len(results)}건")

    return {
        "text": answer_text,
        "action": None,
        "show_buttons": True,
        "sources": build_sources(results)
    }


# ───────────────────────────────────────────
# Notice Agent Tool (menu_agent_tool.py 패턴과 동일)
# ───────────────────────────────────────────
@dataclass
class NoticeTool:
    name: str
    description: str

    def invoke(self, input: dict) -> dict:
        query = input.get("query") or input.get("user_input")
        return generate_notice_answer(query)

    def run(self, **kwargs) -> dict:
        query = kwargs.get("query") or kwargs.get("user_input")
        return generate_notice_answer(query)


notice_agent_tool = NoticeTool(
    name="notice_agent",
    description=(
        "인공지능사관학교 공지사항을 검색하여 답변하는 Tool. "
        "인자: query(str, 필수). "
        "반환: {text, action, show_buttons, sources}"
    )
)


# ───────────────────────────────────────────
# 단독 실행 테스트
# ───────────────────────────────────────────
if __name__ == "__main__":
    test_queries = [
        "공가 신청할 때 필요한 서류가 뭐야?",
        "7월 자격증 취득 이벤트 내용 알려줘",
        "존재하지 않는 이상한 질문입니다 아무말대잔치",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"질문: {q}")
        print(f"{'='*60}")
        result = generate_notice_answer(q)
        print(f"답변:\n{result['text']}")
        print(f"\n근거 수: {len(result['sources'])}")
        for src in result["sources"]:
            print(f"  - {src}")
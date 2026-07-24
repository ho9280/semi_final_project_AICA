# semi_final_project_AICA
**챗봇 관련 파일 정리:**

| 파일 | 역할 |
|---|---|
| `chat_router.py` | 챗봇 메인 라우터 (포트 8001), 키워드 분기, agent 호출, 출결 계산기 API |
| `chatbot.html` | 챗봇 프론트엔드, 메시지 버블, 카테고리 버튼, 계산기 모달 연동 |
| `attendance_agent.py` | 출결 agent (LangGraph), RAG/계산기 분기 |
| `attendance_agent_ui.js` | 출결 계산기 모달 UI |
| `aica_attendance_rules.md` | 출결 규정 RAG 데이터 |
| `aica_financial_support.md` | 지원금 규정 RAG 데이터 |
| `data/chatbot_memory.db` | SqliteSaver 대화 메모리 DB |

---

**실행 방법:**
```bash
# API 키 설정 후
uvicorn chat_router:app --port 8001 --reload

# chatbot.html 파일 직접 브라우저에서 열기 (Live Server 사용 금지)
```
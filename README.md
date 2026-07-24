# 광주인공지능사관학교 7기 학습·생활 보조 챗봇

## 실행 방법
```bash
pip install numpy Pillow tzdata
uvicorn chat_router:app --reload --port 8001
```
브라우저에서 chatbot.html 파일 열기

## Agent 연동 현황
| Agent | 상태 |
|---|---|
| 출결 | ✅ 완료 |
| 식단 | ✅ 완료 (2026-07-20~26 데이터) |
| 공지사항 | 🔧 stub (준비 중) |
| 기타/민원 | ⚠️ LLM 직접 응답 (앱 특화 미완료) |

## 데이터 경로
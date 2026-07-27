# semi_final_project_AICA
# 📌 [가이드] Notice Agent 실행 및 연동 방법

## 1. 실행 전 체크리스트 (파일 위치)

프로젝트 폴더에 아래 파일들이 있는지 확인합니다.

* `config.py` (경로·청킹·Pinecone 설정)
* `notice_extractor.py` (텍스트 추출)
* `notice_chunker.py` (Chunking)
* `notice_uploader.py` (Embedding + Pinecone 업로드)
* `notice_retriever.py` (Pinecone 검색)
* `notice_agent_tool.py` (Supervisor가 사용할 최종 Tool)

> 💡 **폴더 위치 관련 팁**: `AICA_notice/`, `rule/` 폴더 위치가 다르면 `config.py` 상단의 `NOTICE_DOCX`, `ATTACHMENT_DIR`, `RULE_DIR` 값만 맞춰주시면 됩니다.

---

## 2. ⚠️ 이미 완료된 작업 (재실행 불필요)

아래 두 파일은 **김대호 계정 기준으로 이미 실행 완료**되어 데이터가 Pinecone에 올라가 있습니다. 다시 실행하면 중복 데이터가 쌓이거나 불필요한 API 비용이 발생하니 **재실행하지 마세요.**

* `notice_db_setup.py` — SQLite DB 생성 및 데이터 적재 완료
* `notice_uploader.py` — Pinecone Index(`aica-notice`)에 벡터 151개 업로드 완료

> ⚠️ 단, 이 내용이 유효하려면 **4번(.env 설정)에서 반드시 김대호의 Pinecone API Key를 전달받아 사용**해야 합니다. 본인의 Pinecone Key를 쓰면 Index 자체가 없어서 검색이 항상 0건으로 나옵니다.

> 공지사항 원본 데이터가 새로 추가되는 경우에만 위 두 파일을 순서대로 재실행합니다. (이 경우 Pinecone Index를 먼저 비운 뒤 재업로드해야 합니다.)

---

## 3. 패키지 설치

VSCode 터미널(`Ctrl + ~`)에서 아래 명령어를 실행합니다.

```bash
pip install pinecone langchain-pinecone python-docx pymupdf pytesseract pillow python-dotenv langchain-openai
```

**Windows에서 OCR 사용 시 추가 설치 필요**
* Tesseract-OCR 프로그램: https://github.com/UB-Mannheim/tesseract/wiki
* (첨부파일 재처리 시에만 필요, 현재는 이미 처리 완료되어 불필요)

---

## 4. API Key 설정 (.env 파일)

⚠️ **Pinecone Key는 본인 것을 쓰면 안 됩니다.**

`aica-notice` Index(벡터 151개)는 **김대호 계정의 Pinecone에만 존재**합니다. Pinecone Index는 계정 단위로 분리되어 있어서, 본인 Pinecone Key로 접속하면 같은 이름의 Index가 없거나 비어 있어 검색 결과가 항상 0건이 됩니다.

프로젝트 루트에 `.env` 파일을 만들고 아래 내용을 채웁니다.

```
OPENAI_API_KEY=본인의_OPENAI_API_KEY
PINECONE_API_KEY=김대호에게_전달받은_PINECONE_API_KEY
```

* `OPENAI_API_KEY` → 각자 본인 Key 사용 (LLM 답변 생성·질문 임베딩에 사용, 개인 비용 청구)
* `PINECONE_API_KEY` → **반드시 김대호의 Key를 전달받아 사용** (이미 데이터가 적재된 Index를 함께 조회하기 위함)

> ⚠️ `.env` 파일은 Git에 절대 올리지 않습니다. (`.gitignore`에 포함 확인)
> ⚠️ Pinecone Key는 메신저 등으로 안전하게 별도 전달받으세요.

---

## 5. Supervisor 연동 방법

Notice Agent는 **독립 서버(FastAPI app)가 아니라, Python에서 바로 import해서 쓰는 Tool 객체**입니다.

```python
from notice_agent_tool import notice_agent_tool

result = notice_agent_tool.invoke({"query": "공가 신청할 때 필요한 서류가 뭐야?"})

print(result)
# {
#     "text": "...",             # 사용자에게 보여줄 최종 답변
#     "action": None,            # 추가 동작 신호 (Notice Agent는 항상 None)
#     "show_buttons": True,      # 버튼 노출 여부
#     "sources": [               # 검색 근거 (title, score 등)
#         {"source_type": "notice", "title": "...", "release_date": "...", "score": 0.56},
#         ...
#     ]
# }
```

* `text`, `action`, `show_buttons`는 다른 Agent(출결·식단)와 동일한 필드입니다.
* `sources`는 Notice Agent만 추가로 제공하는 필드로, 출처를 표시하고 싶을 때 활용하면 됩니다.

---

## 6. 동작 확인 (단독 테스트)

```bash
python notice_agent_tool.py
```

터미널에 질문 3개(정상 질문 2개 + 무관한 질문 1개)에 대한 답변과 근거가 출력되면 정상입니다.

**확인 체크리스트**
* [ ] 정상 질문 → 답변 + 근거(sources) 출력
* [ ] 무관한 질문 → "관련된 공지사항을 찾지 못했습니다" 안내 (LLM 호출 없이 즉시 응답)
* [ ] 모든 답변 끝에 "자세한 내용은 공지사항 게시판에서 확인해 주세요." 포함
* [ ] `notice_agent_log.txt` 생성 확인

---

## 7. 참고 — 청킹 실험 시 (보고서용)

`config.py`의 `CHUNK_SIZE`, `CHUNK_OVERLAP` 값을 변경하며 검색 품질을 비교할 경우:

```
1. config.py에서 CHUNK_SIZE, CHUNK_OVERLAP 변경
2. Pinecone 콘솔(app.pinecone.io)에서 Index 전체 데이터 삭제
3. notice_uploader.py 재실행 (새 청크로 재업로드)
4. notice_retriever.py 재실행 (동일 질의로 결과 비교)
```
"""
청킹 실험 스크립트

3가지 (chunk_size, chunk_overlap, Pinecone Index) 조합을 자동으로 순회하며
업로드하고, 동일한 질의 5개로 검색 정확도를 비교한다.

주의:
- config.py 파일은 수정하지 않는다 (이 스크립트 프로세스 안에서만 값을 바꿔 쓴다).
- 데모용 서버(chat_router.py)는 별도 프로세스이므로 영향받지 않는다.
- 실행 전 Pinecone 콘솔에서 아래 Index를 미리 만들어야 한다 (1536, cosine):
    aica-notice100080
    aica-notice30050

실행 방법:
    python notice_chunk_experiment.py
"""

import os
import config
from notice_extractor import extract_all
from notice_chunker import chunk_documents
from notice_uploader import init_pinecone, upload_to_pinecone
from notice_retriever import search
from langchain_openai import OpenAIEmbeddings

EXPERIMENTS = [
    {"name": "500/50 (기존)", "chunk_size": 500,  "chunk_overlap": 50, "index_name": "aica-notice",       "skip_upload": True},
    {"name": "1000/80",       "chunk_size": 1000, "chunk_overlap": 80, "index_name": "aica-notice100080", "skip_upload": False},
    {"name": "300/50",        "chunk_size": 300,  "chunk_overlap": 50, "index_name": "aica-notice30050",  "skip_upload": False},
]

TEST_QUERIES = [
    "공가 신청할 때 필요한 서류가 뭐야?",
    "7월 자격증 취득 이벤트 내용 알려줘",
    "강의장 이용 수칙이 뭐야?",
    "AI 도약과정 핸드북 내용 알려줘",
    "이번 달 우수 교육생 선발 기준이 뭐야?",
]


def run_experiment(exp: dict) -> dict:
    print(f"\n{'='*60}\n실험: {exp['name']} (index={exp['index_name']})\n{'='*60}")

    # config 값을 이 프로세스 안에서만 임시로 바꿔 쓴다 (파일 저장 없음)
    config.CHUNK_SIZE = exp["chunk_size"]
    config.CHUNK_OVERLAP = exp["chunk_overlap"]

    if not exp["skip_upload"]:
        documents = extract_all()
        chunks = chunk_documents(documents)
        embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
        pc = init_pinecone()
        config.PINECONE_INDEX_NAME = exp["index_name"]  # upload_to_pinecone이 참조
        upload_to_pinecone(pc, chunks, embeddings)
        print(f"업로드 완료: {len(chunks)}개 청크 -> {exp['index_name']}")
    else:
        print("기존 Index 재사용 (업로드 생략)")

    rows = []
    for i, query in enumerate(TEST_QUERIES, start=1):
        results = search(query, index_name=exp["index_name"])
        top = results[0] if results else None
        rows.append({
            "query": query,
            "결과수": len(results),
            "최고점수": round(top.score, 4) if top else 0.0,
            "1위_title": top.metadata.get("title", "-") if top else "-",
        })
        print(f"  [{i}] {query}")
        print(f"      결과 {len(results)}건 | 최고 score={rows[-1]['최고점수']} | 1위={rows[-1]['1위_title']}")

    return {"experiment": exp["name"], "index": exp["index_name"], "rows": rows}


if __name__ == "__main__":
    all_results = [run_experiment(exp) for exp in EXPERIMENTS]

    print(f"\n\n{'='*60}\n전체 비교 요약\n{'='*60}")
    for r in all_results:
        print(f"\n[{r['experiment']}] (index={r['index']})")
        for row in r["rows"]:
            print(f"  {row['query'][:25]:25s} | 결과 {row['결과수']}건 | score {row['최고점수']}")
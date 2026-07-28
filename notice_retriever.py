"""
4단계: Retriever

Pinecone에 저장된 벡터를 직접 검색하는 함수를 구성합니다.
테스트 질의 5개로 검색 품질을 확인합니다.

실행 방법:
    python notice_retriever.py

추후 청킹 실험 시:
    1. config.py에서 CHUNK_SIZE, CHUNK_OVERLAP 변경
    2. Pinecone 콘솔에서 Index 전체 삭제
    3. notice_uploader.py 재실행
    4. notice_retriever.py 재실행 후 결과 비교
"""

import os
import logging
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings

import config

load_dotenv()

# ───────────────────────────────────────────
# 로깅 설정
# ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("retriever_log.txt", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ───────────────────────────────────────────
# 1. Pinecone 검색 함수
# ───────────────────────────────────────────
ALL_NAMESPACES = [
    config.PINECONE_NAMESPACE_NOTICE,
    config.PINECONE_NAMESPACE_ATTACHMENT,
    config.PINECONE_NAMESPACE_REFERENCE,
]

def search(query: str, namespaces: list = None, index_name: str | None = None) -> list:
    if namespaces is None:
        namespaces = ALL_NAMESPACES
    index_name = index_name or config.PINECONE_INDEX_NAME  # 실험 시 다른 Index 지정 가능

    embeddings = OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        api_key=os.getenv("OPENAI_API_KEY")
    )

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(index_name)

    # 질문 임베딩 (여러 namespace에 재사용)
    query_vector = embeddings.embed_query(query)

    # 각 namespace에서 검색 후 결과 합치기
    all_matches = []
    for ns in namespaces:
        results = index.query(
            vector=query_vector,
            top_k=config.RETRIEVER_K,
            namespace=ns,
            include_metadata=True
        )
        all_matches.extend(results.matches)

    # score threshold 필터링
    filtered = [m for m in all_matches if m.score >= config.RETRIEVER_SCORE_THRESHOLD]

    # score 기준 내림차순 정렬 후 상위 k개만 유지
    filtered.sort(key=lambda m: m.score, reverse=True)
    filtered = filtered[:config.RETRIEVER_K]

    logger.info(
        f"[검색] query={query} | "
        f"전체={len(all_matches)} | "
        f"필터후={len(filtered)} | "
        f"threshold={config.RETRIEVER_SCORE_THRESHOLD}"
    )
    return filtered


# ───────────────────────────────────────────
# 2. 검색 결과 출력
# ───────────────────────────────────────────
def search_and_print(query: str, query_num: int):
    """질의 실행 후 결과 출력"""
    print(f"\n{'='*60}")
    print(f"[질의 {query_num}] {query}")
    print(f"{'='*60}")

    results = search(query)

    if not results:
        print("  ※ 검색 결과 없음 (score_threshold 이하)")
        return

    for i, match in enumerate(results):
        print(f"\n  [결과 {i+1}] score: {match.score:.4f}")
        print(f"  source_type  : {match.metadata.get('source_type', '-')}")
        print(f"  title        : {match.metadata.get('title', '-')}")
        print(f"  release_date : {match.metadata.get('release_date', '-')}")
        print(f"  file_name    : {match.metadata.get('file_name', '-')}")
        print(f"  chunk_index  : {match.metadata.get('chunk_index', '-')} / {match.metadata.get('chunk_total', '-')}")
        print(f"  내용 미리보기 : {match.metadata.get('text', '')[:150]}...")


# ───────────────────────────────────────────
# 3. 테스트 질의
# ───────────────────────────────────────────
TEST_QUERIES = [
    "공가 신청할 때 필요한 서류가 뭐야?",
    "7월 자격증 취득 이벤트 내용 알려줘",
    "강의장 이용 수칙이 뭐야?",
    "AI 도약과정 핸드북 내용 알려줘",
    "이번 달 우수 교육생 선발 기준이 뭐야?",
]


# ───────────────────────────────────────────
# 실행
# ───────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=== Retriever 검색 테스트 시작 ===")

    print("\n" + "="*60)
    print("Retriever 설정")
    print("="*60)
    print(f"  Index           : {config.PINECONE_INDEX_NAME}")
    print(f"  chunk_size      : {config.CHUNK_SIZE}")
    print(f"  chunk_overlap   : {config.CHUNK_OVERLAP}")
    print(f"  k               : {config.RETRIEVER_K}")
    print(f"  score_threshold : {config.RETRIEVER_SCORE_THRESHOLD}")

    for i, query in enumerate(TEST_QUERIES, start=1):
        search_and_print(query, i)

    print(f"\n{'='*60}")
    print("테스트 완료")
    print(f"{'='*60}")
    logger.info("=== Retriever 검색 테스트 완료 ===")
    
"""
3단계: Embedding + Pinecone 업로드

2단계(notice_chunker.py)에서 생성한 청크를
OpenAI Embedding으로 변환하고 Pinecone에 업로드합니다.

실행 방법:
    python notice_uploader.py

사전 준비:
    1. pip install pinecone
    2. .env 파일에 OPENAI_API_KEY, PINECONE_API_KEY 설정
    3. Pinecone 콘솔에서 Index 생성
       - Index name : aica-notice
       - Dimensions : 1536  (text-embedding-3-small 기준)
       - Metric     : cosine
"""

import os
import logging
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

import config
from notice_extractor import extract_all
from notice_chunker import chunk_documents

# 환경변수 로드
load_dotenv()

# ───────────────────────────────────────────
# 로깅 설정
# ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("upload_log.txt", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ───────────────────────────────────────────
# 1. Pinecone 초기화
# ───────────────────────────────────────────
def init_pinecone() -> Pinecone:
    """Pinecone 클라이언트 초기화"""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError(".env 파일에 PINECONE_API_KEY가 없습니다.")

    pc = Pinecone(api_key=api_key)
    logger.info("[Pinecone] 초기화 완료")
    return pc


# ───────────────────────────────────────────
# 2. Namespace 결정
# ───────────────────────────────────────────
def get_namespace(source_type: str) -> str:
    """source_type에 따라 Pinecone Namespace 반환"""
    mapping = {
        "notice"     : config.PINECONE_NAMESPACE_NOTICE,
        "attachment" : config.PINECONE_NAMESPACE_ATTACHMENT,
        "reference"  : config.PINECONE_NAMESPACE_REFERENCE,
    }
    return mapping.get(source_type, "notice")


# ───────────────────────────────────────────
# 3. 청크를 Namespace별로 분리
# ───────────────────────────────────────────
def group_by_namespace(chunks: list[Document]) -> dict[str, list[Document]]:
    """청크를 source_type 기준으로 Namespace별 그룹으로 분리"""
    groups: dict[str, list[Document]] = {}

    for chunk in chunks:
        source_type = chunk.metadata.get("source_type", "notice")
        ns = get_namespace(source_type)
        if ns not in groups:
            groups[ns] = []
        groups[ns].append(chunk)

    return groups


# ───────────────────────────────────────────
# 4. Pinecone에 업로드
# ───────────────────────────────────────────
def upload_to_pinecone(pc: Pinecone, chunks: list[Document], embeddings: OpenAIEmbeddings):
    """
    청크를 Namespace별로 분리하여 Pinecone에 업로드
    EMBEDDING_BATCH_SIZE 단위로 나눠서 업로드 (API 제한 방지)
    """
    index = pc.Index(config.PINECONE_INDEX_NAME)
    groups = group_by_namespace(chunks)

    total_uploaded = 0

    for namespace, ns_chunks in groups.items():
        logger.info(f"[업로드] Namespace={namespace} | {len(ns_chunks)}개 청크 시작")

        # 배치 단위로 업로드
        for batch_start in range(0, len(ns_chunks), config.EMBEDDING_BATCH_SIZE):
            batch = ns_chunks[batch_start: batch_start + config.EMBEDDING_BATCH_SIZE]

            # 텍스트 추출
            texts = [chunk.page_content for chunk in batch]

            # Embedding 생성
            vectors = embeddings.embed_documents(texts)

            # Pinecone에 upsert할 데이터 구성
            upsert_data = []
            for i, (chunk, vector) in enumerate(zip(batch, vectors)):
                # Pinecone 메타데이터는 문자열/숫자/불리언만 허용
                metadata = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                            for k, v in chunk.metadata.items()}
                # 검색 후 원문 복원을 위해 텍스트도 메타데이터에 저장
                metadata["text"] = chunk.page_content

                vector_id = f"{namespace}_{batch_start + i}"
                upsert_data.append({
                    "id"       : vector_id,
                    "values"   : vector,
                    "metadata" : metadata
                })

            index.upsert(vectors=upsert_data, namespace=namespace)
            total_uploaded += len(batch)
            logger.info(f"[업로드] {namespace} | {batch_start + len(batch)}/{len(ns_chunks)}개 완료")

        logger.info(f"[업로드] Namespace={namespace} 완료")

    logger.info(f"[업로드] 전체 완료 | 총 {total_uploaded}개 업로드")
    return total_uploaded


# ───────────────────────────────────────────
# 5. 업로드 검증
# ───────────────────────────────────────────
def verify_upload(pc: Pinecone):
    """업로드 후 Pinecone Index 상태 확인"""
    index = pc.Index(config.PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()

    print("\n" + "="*50)
    print("Pinecone 업로드 결과")
    print("="*50)
    for namespace, ns_stats in stats.namespaces.items():
        print(f"  Namespace [{namespace}] : {ns_stats.vector_count}개")
    print(f"  전체 벡터 수 : {stats.total_vector_count}개")
    print("="*50)


# ───────────────────────────────────────────
# 실행
# ───────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=== Embedding + Pinecone 업로드 시작 ===")

    # 1단계: 텍스트 추출
    documents = extract_all()

    # 2단계: 청킹
    chunks = chunk_documents(documents)

    # Embedding 모델 초기화
    embeddings = OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        api_key=os.getenv("OPENAI_API_KEY")
    )

    # Pinecone 초기화
    pc = init_pinecone()

    # 업로드
    upload_to_pinecone(pc, chunks, embeddings)

    # 검증
    verify_upload(pc)

    logger.info("=== 전체 완료 ===")
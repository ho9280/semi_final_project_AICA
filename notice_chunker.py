"""
2단계: Chunking

1단계(notice_extractor.py)에서 생성한 Document 리스트를
청크로 분할하고 메타데이터를 유지합니다.

실행 방법:
    python notice_chunker.py

chunk_size, chunk_overlap 변경 시 config.py만 수정하면 됩니다.
"""

import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

import config
from notice_extractor import extract_all


# ───────────────────────────────────────────
# 로깅 설정
# ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("chunk_log.txt", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ───────────────────────────────────────────
# Chunking
# ───────────────────────────────────────────
def chunk_documents(documents: list[Document]) -> list[Document]:
    """
    Document 리스트를 청크로 분할하여 반환
    - chunk_size, chunk_overlap은 config.py에서 관리
    - 원본 메타데이터는 모든 청크에 그대로 유지
    - chunk_index: 해당 Document 내 청크 순서 (0부터 시작)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        length_function=len,
    )

    all_chunks = []

    for doc in documents:
        chunks = splitter.split_documents([doc])

        # 청크별 추가 메타데이터 부착
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i          # 문서 내 청크 순서
            chunk.metadata["chunk_total"] = len(chunks) # 해당 문서의 총 청크 수

        all_chunks.extend(chunks)

    logger.info(
        f"[Chunking] 완료 | "
        f"문서:{len(documents)} → 청크:{len(all_chunks)} | "
        f"chunk_size={config.CHUNK_SIZE} overlap={config.CHUNK_OVERLAP}"
    )
    return all_chunks


# ───────────────────────────────────────────
# 검증 출력
# ───────────────────────────────────────────
def print_chunk_stats(chunks: list[Document], documents: list[Document]):
    """Chunking 결과 통계 출력"""
    lengths = [len(chunk.page_content) for chunk in chunks]

    print("\n" + "="*50)
    print("Chunking 결과")
    print("="*50)
    print(f"1. 총 문서 수        : {len(documents)}개")
    print(f"2. 총 Chunk 수       : {len(chunks)}개")
    print(f"3. chunk_size        : {config.CHUNK_SIZE}")
    print(f"   chunk_overlap     : {config.CHUNK_OVERLAP}")
    print(f"4. 평균 Chunk 길이   : {sum(lengths) / len(lengths):.1f}자")
    print(f"5. 가장 긴 Chunk     : {max(lengths)}자")
    print(f"6. 가장 짧은 Chunk   : {min(lengths)}자")

    print("\n--- 샘플 Chunk 3개 ---")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n[샘플 {i+1}]")
        print(f"  Metadata : {chunk.metadata}")
        print(f"  내용 미리보기 : {chunk.page_content[:100]}...")
    print("="*50)


# ───────────────────────────────────────────
# 실행
# ───────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=== Chunking 시작 ===")

    # 1단계: 텍스트 추출
    documents = extract_all()

    # 2단계: 청킹
    chunks = chunk_documents(documents)

    # 결과 출력
    print_chunk_stats(chunks, documents)
    
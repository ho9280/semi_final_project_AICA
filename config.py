# ───────────────────────────────────────────
# 프로젝트 전체 설정
# 경로나 청킹 값 변경 시 이 파일만 수정합니다.
# ───────────────────────────────────────────

# 경로
NOTICE_DOCX    = "AICA_notice/notice_AICA.docx"
ATTACHMENT_DIR = "AICA_notice/notice_attachment"
RULE_DIR       = "rule"

# 청킹 설정 (실험 시 이 두 값만 변경하면 됩니다)
CHUNK_SIZE     = 500
CHUNK_OVERLAP  = 50

# Pinecone 설정
PINECONE_INDEX_NAME           = "aica-notice"
PINECONE_NAMESPACE_NOTICE     = "notice"
PINECONE_NAMESPACE_ATTACHMENT = "attachment"
PINECONE_NAMESPACE_REFERENCE  = "reference"

# Embedding 설정
EMBEDDING_MODEL      = "text-embedding-3-small"
EMBEDDING_BATCH_SIZE = 100

# Retriever 설정
RETRIEVER_K               = 5
RETRIEVER_SCORE_THRESHOLD = 0.4

import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("aica-notice")

# Index 상태 확인
stats = index.describe_index_stats()
print(f"전체 벡터 수: {stats.total_vector_count}")
print(f"Namespace 목록: {stats.namespaces}")

# 벡터 1개 직접 fetch 테스트
try:
    result = index.fetch(ids=["notice_0"], namespace="notice")
    print(f"\nfetch 결과: {result}")
except Exception as e:
    print(f"\nfetch 오류: {e}")
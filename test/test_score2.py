import os
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY")
)

# 질문을 직접 임베딩
query_vector = embeddings.embed_query("공가 신청 서류")
print(f"임베딩 벡터 차원: {len(query_vector)}")
print(f"벡터 앞 5개 값: {query_vector[:5]}")

# Pinecone 직접 검색
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("aica-notice")

results = index.query(
    vector=query_vector,
    top_k=3,
    namespace="notice",
    include_metadata=True
)

print(f"\n검색 결과:")
for match in results.matches:
    print(f"score: {match.score}")
    print(f"title: {match.metadata.get('title', '-')}")
    print()
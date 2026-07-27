import os
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY")
)

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("aica-notice")

query_vector = embeddings.embed_query("공가 신청 서류")

# namespace 각각 테스트
for ns in ["notice", "attachment", "reference"]:
    results = index.query(
        vector=query_vector,
        top_k=3,
        namespace=ns,
        include_metadata=True
    )
    print(f"namespace={ns} | 결과 수={len(results.matches)}")
    for match in results.matches:
        print(f"  score={match.score:.4f} | title={match.metadata.get('title', '-')}")
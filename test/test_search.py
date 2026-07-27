import os
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY")
)

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("aica-notice")

vectorstore = PineconeVectorStore(
    index=index,
    embedding=embeddings,
    text_key="text"
)

# similarity로 직접 검색 (score 포함)
results = vectorstore.similarity_search_with_score("공가 신청 서류", k=3)

for doc, score in results:
    print(f"score: {score}")
    print(f"metadata: {doc.metadata}")
    print(f"내용: {doc.page_content[:100]}")
    print()

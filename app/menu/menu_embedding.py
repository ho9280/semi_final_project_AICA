"""메뉴 텍스트에 대한 간단한 로컬 임베딩과 벡터 검색 기능.

이번 MVP는 외부 임베딩 모델(OpenAI, sentence-transformers 등)이나
Pinecone 같은 유료 서비스를 쓰지 않는다. 대신 다음과 같이 가볍게 구현한다.

- 임베딩: 해싱 트릭(hashing trick) 기반 단어 빈도(TF) 벡터.
  인터넷 연결이나 모델 다운로드 없이 결정적으로(같은 입력 -> 같은 벡터) 동작한다.
  실제 의미 이해보다는 "단어가 얼마나 겹치는가"에 가깝다는 한계가 있다.
- 저장소: JSON 파일에 {id: {vector, document, metadata}}를 저장하는
  직접 구현 벡터 스토어. chromadb 같은 전용 라이브러리 대신 사용했으며,
  이유는 이번 MVP 규모에서는 무거운 의존성(onnxruntime 등)을 설치하지
  않고도 "영구 저장 + 유사도 검색" 요구사항을 충분히 만족하기 때문이다.
  나중에 데이터가 커지면 이 파일의 VectorStore 클래스만 chromadb 등으로
  교체하면 되고, menu_agent.py 쪽 코드는 바꿀 필요가 없다.

정확한 업체/날짜 조건이 있는 질문은 menu_repository.py의 조건 검색을
우선 사용하고, "돈가스 나오는 날" 같은 의미 검색이 필요한 질문에서만
이 모듈을 보조로 사용한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from app.menu.config import VECTOR_STORE_PATH

EMBEDDING_DIM = 256

_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """텍스트를 해싱 트릭 기반 TF 벡터로 변환한다.

    같은 텍스트는 항상 같은 벡터를 반환한다(결정적).
    """
    vector = np.zeros(dim, dtype=np.float64)
    for token in _tokenize(text):
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(digest, 16) % dim
        vector[idx] += 1.0

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class VectorStore:
    """id -> (임베딩, 원문, 메타데이터)를 JSON 파일에 영구 저장하는 간단한 벡터 스토어."""

    def __init__(self, store_path: str | Path | None = None, dim: int = EMBEDDING_DIM) -> None:
        self.store_path = Path(store_path) if store_path is not None else VECTOR_STORE_PATH
        self.dim = dim
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.store_path.exists():
            return {}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # 파일이 손상된 경우 빈 상태로 새로 시작한다 (기존 데이터는 덮어쓰기 전까지 유지).
            return {}

    def _save(self) -> None:
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)

    def upsert(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """텍스트를 임베딩해 저장(또는 갱신)한다. 같은 id는 덮어쓴다(중복 방지)."""
        self._data[doc_id] = {
            "vector": embed_text(text, self.dim),
            "document": text,
            "metadata": metadata or {},
        }
        self._save()

    def delete(self, doc_id: str) -> None:
        if doc_id in self._data:
            del self._data[doc_id]
            self._save()

    def count(self) -> int:
        return len(self._data)

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """질의 텍스트와 유사한 문서를 코사인 유사도 순으로 반환한다.

        metadata_filter를 주면 저장된 metadata가 해당 키/값을 모두 포함하는
        항목만 후보로 삼는다(예: {"organization": "KT"}).
        """
        query_vector = np.array(embed_text(query_text, self.dim))

        candidates = []
        for doc_id, item in self._data.items():
            metadata = item.get("metadata", {})
            if metadata_filter:
                if any(metadata.get(k) != v for k, v in metadata_filter.items()):
                    continue
            score = _cosine_similarity(query_vector, np.array(item["vector"]))
            candidates.append(
                {
                    "id": doc_id,
                    "score": score,
                    "document": item["document"],
                    "metadata": metadata,
                }
            )

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:top_k]


_default_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """기본(영구 저장) VectorStore 싱글턴을 반환한다.

    의미 검색은 정확한 날짜·업체 조회의 필수 조건이 아니라 보조 수단이므로,
    이 싱글턴은 실제로 검색이 필요할 때(또는 reload_menu_data() 호출 시)만
    쓰이며, 읽기만 해서는 vector_store.json 파일을 새로 만들지 않는다
    (upsert가 호출될 때만 파일이 생성/갱신된다).
    """
    global _default_vector_store
    if _default_vector_store is None:
        _default_vector_store = VectorStore()
    return _default_vector_store

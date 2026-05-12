from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ports.vector_search import SearchHit, VectorSearchPort


class ChromaVectorSearchAdapter(VectorSearchPort):
    def __init__(
        self,
        data_dir: Path | None = None,
        collection_name: str = "project_zero",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self._data_dir = data_dir or Path(__file__).resolve().parents[3] / "data"
        self._collection_name = collection_name
        self._embedding_model = embedding_model
        self._client: Any | None = None
        self._model: Any | None = None
        self._collection: Any | None = None

    def search(self, query: str, n: int = 5) -> list[SearchHit]:
        collection, model = self._get_collection()
        query_vector = model.encode(query).tolist()
        raw = collection.query(
            query_embeddings=[query_vector],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[SearchHit] = []
        for idx, item_id in enumerate(raw["ids"][0]):
            distance = raw["distances"][0][idx]
            metadata = raw["metadatas"][0][idx] or {}
            hits.append(
                SearchHit(
                    id=item_id,
                    content=raw["documents"][0][idx],
                    score=round(1 - distance, 4),
                    source=str(metadata.get("source", "")),
                )
            )
        return hits

    def _get_collection(self) -> tuple[Any, Any]:
        if self._collection is not None and self._model is not None:
            return self._collection, self._model

        import chromadb
        from sentence_transformers import SentenceTransformer

        self._client = chromadb.Client()
        self._model = SentenceTransformer(self._embedding_model)
        self._collection = self._client.get_or_create_collection(
            self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._seed_collection()
        return self._collection, self._model

    def _seed_collection(self) -> None:
        if self._collection is None or self._model is None:
            raise RuntimeError("Chroma collection is not initialized")
        if self._collection.count() > 0:
            return

        records = self._load_records()
        ids = [record["id"] for record in records]
        texts = [record["content"] for record in records]
        metadatas = [{"source": record["source"]} for record in records]
        embeddings = self._model.encode(texts).tolist()
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def _load_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for filename, source in [
            ("external.json", "external"),
            ("internal.json", "internal"),
            ("persons.json", "persons"),
        ]:
            rows = json.loads((self._data_dir / filename).read_text(encoding="utf-8"))
            for row in rows:
                records.append({**row, "source": source})
        return records
